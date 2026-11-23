import datetime as dt
import json
import os
import re
import uuid
from pathlib import Path

import bcrypt
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .extract import LABEL, ExtractionError, configured, extract_documents, extractable_fields
from .forms import FORMS
from .logic import missing_fields, with_computed
from .render import render
from .textutil import extract_text

BASE = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("ORI_DATA_DIR", BASE / "data"))
(DATA / "outputs").mkdir(parents=True, exist_ok=True)
SECRET = os.environ.get("ORI_JWT_SECRET")
if not SECRET:  # no default: a hard-coded secret would let anyone forge logins
    SECRET_FILE = DATA / ".jwt_secret"
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
    SECRET = SECRET_FILE.read_text()
ALLOWED_DOMAIN = os.environ.get("ORI_ALLOWED_EMAIL_DOMAIN", "spjimr.org")  # set to "" to allow any email
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ORI_ADMIN_EMAILS", "").split(",") if e.strip()}
RETENTION_DAYS = int(os.environ.get("ORI_RETENTION_DAYS", "1826"))  # 5 years
MAX_UPLOAD = 25 * 1024 * 1024

engine = create_engine(f"sqlite:///{DATA/'app.db'}", connect_args={"check_same_thread": False})
Session = sessionmaker(engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    pw_hash = Column(String, nullable=False)


class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    form_code = Column(String, nullable=False)
    created = Column(DateTime, default=dt.datetime.utcnow)
    papers = Column(Text, default="[]")
    values = Column(Text, nullable=False)
    sources = Column(Text, default="{}")
    filename = Column(String, nullable=False)


Base.metadata.create_all(engine)
app = FastAPI(title="SPJIMR ORI Forms")
bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not cred:
        raise HTTPException(401, "Not signed in")
    try:
        uid = int(jwt.decode(cred.credentials, SECRET, algorithms=["HS256"])["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Session expired, please sign in again")
    with Session() as s:
        u = s.get(User, uid)
    if not u:
        raise HTTPException(401, "Unknown user")
    return u


def token_for(u):
    exp = dt.datetime.utcnow() + dt.timedelta(hours=12)
    return jwt.encode({"sub": str(u.id), "exp": exp}, SECRET, algorithm="HS256")


class Register(BaseModel):
    email: str
    password: str
    full_name: str


class Login(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
def register(r: Register):
    email = r.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Enter a valid email address")
    if ALLOWED_DOMAIN and not email.endswith("@" + ALLOWED_DOMAIN.lower()):
        raise HTTPException(400, f"Only @{ALLOWED_DOMAIN} email addresses can register")
    if len(r.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if not r.full_name.strip():
        raise HTTPException(400, "Full name is required")
    with Session() as s:
        if s.query(User).filter_by(email=email).first():
            raise HTTPException(400, "An account with this email already exists")
        u = User(email=email, full_name=r.full_name.strip(),
                 pw_hash=bcrypt.hashpw(r.password.encode(), bcrypt.gensalt()).decode())
        s.add(u)
        s.commit()
        s.refresh(u)
        return {"token": token_for(u), "full_name": u.full_name, "email": u.email, "is_admin": u.email in ADMIN_EMAILS}


@app.post("/api/auth/login")
def login(r: Login):
    with Session() as s:
        u = s.query(User).filter_by(email=r.email.strip().lower()).first()
    if not u or not bcrypt.checkpw(r.password.encode(), u.pw_hash.encode()):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": token_for(u), "full_name": u.full_name, "email": u.email, "is_admin": u.email in ADMIN_EMAILS}


@app.get("/api/me")
def me(u: User = Depends(current_user)):
    return {"full_name": u.full_name, "email": u.email, "is_admin": u.email in ADMIN_EMAILS}


@app.get("/api/forms")
def forms(u: User = Depends(current_user)):
    return FORMS


def _account_fill(form_code, name, values, sources):
    """The signed-in user's name goes into the name field of the form, shown for confirmation, never silent."""
    for key in ("faculty_name", "name"):
        if any(f["key"] == key for f in FORMS[form_code]["fields"]):
            values[key] = name
            sources[key] = {"quote": "Your account name", "origin": "account"}


@app.post("/api/extract")
def extract(form_code: str = Form(...), files: list[UploadFile] = File(default=[]),
            faculty_name: str = Form(""), u: User = Depends(current_user)):
    if form_code not in FORMS:
        raise HTTPException(404, "Unknown form")
    name = faculty_name.strip() or u.full_name
    notes, docs = [], []
    for f in files:
        data = f.file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"{f.filename} is larger than 25 MB")
        print(f"[extract] reading {f.filename} ({len(data)} bytes)", flush=True)
        try:
            text, n = extract_text(f.filename, data)
        except ValueError as e:
            raise HTTPException(400, str(e))
        notes += n
        if not text.strip():
            notes.append(f"{f.filename}: no readable text was found in this file.")
        docs.append((f.filename, text))
    values, sources = {}, {}
    not_found = [f["key"] for f in extractable_fields(form_code)]
    if any(t.strip() for _, t in docs):
        ok, why = configured()
        if not ok:
            raise HTTPException(503, why)
        print(f"[extract] reading {len(docs)} document(s) with {LABEL}", flush=True)
        try:
            r = extract_documents(form_code, [(n_, t_) for n_, t_ in docs if t_.strip()], name)
        except Exception as e:
            print(f"[extract] error: {e!r}", flush=True)
            raise HTTPException(502, str(e) if isinstance(e, ExtractionError) else f"Could not read the documents: {e}")
        values, sources, not_found, notes = r["values"], r["sources"], r["not_found"], notes + r["notes"]
        print("[extract] done", flush=True)
    _account_fill(form_code, name, values, sources)
    return {"values": values, "sources": sources, "not_found": not_found, "notes": notes, "papers": [n for n, _ in docs]}


class Submit(BaseModel):
    form_code: str
    values: dict
    sources: dict = {}
    papers: list[str] = []




@app.post("/api/extract-stream")
def extract_stream(form_code: str = Form(...), files: list[UploadFile] = File(default=[]),
                   faculty_name: str = Form(""), u: User = Depends(current_user)):
    if form_code not in FORMS:
        raise HTTPException(404, "Unknown form")
    name = faculty_name.strip() or u.full_name
    raw_files = []
    for f in files:
        data = f.file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"{f.filename} is larger than 25 MB")
        raw_files.append((f.filename, data))

    import queue, threading
    q = queue.Queue()

    def worker():
        try:
            values, sources, notes, docs = {}, {}, [], []
            total_files = max(len(raw_files), 1)
            for fi, (fname, data) in enumerate(raw_files):
                q.put({"pct": 5 + int(20 * fi / total_files), "msg": f"Opening {fname}..."})
                def on_page(page_no, total_pages, is_ocr, _fn=fname, _fi=fi):
                    pct = 5 + int(20 * (_fi + page_no / max(total_pages, 1)) / total_files)
                    action = "Running OCR on scanned page" if is_ocr else "Reading page"
                    q.put({"pct": pct, "msg": f"{action} {page_no} of {total_pages} ({_fn})..."})
                text, n = extract_text(fname, data, on_progress=on_page)
                notes += n
                if not text.strip():
                    notes.append(f"{fname}: no readable text was found in this file.")
                docs.append((fname, text))
            not_found = [f["key"] for f in extractable_fields(form_code)]
            readable = [(n_, t_) for n_, t_ in docs if t_.strip()]
            if readable:
                ok, why = configured()
                if not ok:
                    q.put({"error": why})
                    return
                done = {"n": 0}

                def on_status(m):
                    if m.startswith("Reading document"):
                        done["n"] += 1
                    pct = 30 + int(60 * min(done["n"], len(readable)) / len(readable))
                    q.put({"pct": pct, "msg": m})

                q.put({"pct": 30, "msg": f"Reading with {LABEL}..."})
                r = extract_documents(form_code, readable, name, on_status=on_status)
                values, sources, not_found, notes = r["values"], r["sources"], r["not_found"], notes + r["notes"]
                q.put({"pct": 95, "msg": "Checking every value against your documents..."})
            _account_fill(form_code, name, values, sources)
            q.put({"pct": 100, "msg": "Done!", "result": {
                "values": values, "sources": sources, "not_found": not_found, "notes": notes,
                "papers": [n_ for n_, _ in docs],
            }})
        except Exception as e:
            print(f"[extract-stream] error: {e!r}", flush=True)
            q.put({"error": str(e) if isinstance(e, ExtractionError) else f"Could not read the documents: {e}"})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            item = q.get()
            if item is None:
                break
            yield json.dumps(item) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/missing")
def missing(s: Submit, u: User = Depends(current_user)):
    if s.form_code not in FORMS:
        raise HTTPException(404, "Unknown form")
    return {"missing": missing_fields(s.form_code, s.values), "computed": with_computed(s.form_code, s.values)}


@app.post("/api/applications")
def create(s: Submit, u: User = Depends(current_user)):
    if s.form_code not in FORMS:
        raise HTTPException(404, "Unknown form")
    miss = missing_fields(s.form_code, s.values)
    if miss:
        raise HTTPException(422, {"message": "Some details are still missing", "missing": miss})
    blob, ext = render(s.form_code, s.values)
    fname = f"{uuid.uuid4().hex}.{ext}"
    (DATA / "outputs" / fname).write_bytes(blob)
    with Session() as db:
        a = Application(user_id=u.id, form_code=s.form_code, papers=json.dumps(s.papers),
                        values=json.dumps(s.values), sources=json.dumps(s.sources), filename=fname)
        db.add(a)
        db.commit()
        db.refresh(a)
        return {"id": a.id}


def _owned(db, app_id, u):
    a = db.get(Application, app_id)
    if not a or a.user_id != u.id:  # users only ever see their own applications
        raise HTTPException(404, "Not found")
    return a


@app.get("/api/applications")
def history(u: User = Depends(current_user)):
    with Session() as db:
        rows = db.query(Application).filter_by(user_id=u.id).order_by(Application.created.desc()).all()
        return [{"id": a.id, "form_code": a.form_code, "title": FORMS[a.form_code]["title"],
                 "created": a.created.isoformat() + "Z", "papers": json.loads(a.papers)} for a in rows]


@app.get("/api/applications/{app_id}")
def one(app_id: int, u: User = Depends(current_user)):
    with Session() as db:
        a = _owned(db, app_id, u)
        return {"id": a.id, "form_code": a.form_code, "values": json.loads(a.values),
                "sources": json.loads(a.sources), "papers": json.loads(a.papers)}


@app.get("/api/applications/{app_id}/download")
def download(app_id: int, u: User = Depends(current_user)):
    with Session() as db:
        a = _owned(db, app_id, u)
        path = DATA / "outputs" / a.filename
        code = FORMS[a.form_code]["code"]
        stamp = a.created.strftime("%Y%m%d")
    ext = path.suffix
    return FileResponse(path, filename=f"Annexure_{code}_{stamp}{ext}")


@app.delete("/api/applications/{app_id}")
def delete(app_id: int, u: User = Depends(current_user)):
    with Session() as db:
        a = _owned(db, app_id, u)
        (DATA / "outputs" / a.filename).unlink(missing_ok=True)
        db.delete(a)
        db.commit()
    return {"ok": True}


def admin_user(u: User = Depends(current_user)):
    if u.email not in ADMIN_EMAILS:
        raise HTTPException(403, "Admin access required")
    return u


@app.get("/api/admin/applications")
def admin_apps(form_code: str = "", q: str = "", a: User = Depends(admin_user)):
    with Session() as db:
        rows = (db.query(Application, User).join(User, User.id == Application.user_id)
                .order_by(Application.created.desc()).all())
    out = []
    for ap, us in rows:
        if form_code and ap.form_code != form_code:
            continue
        if q and q.lower() not in (us.full_name + " " + us.email).lower():
            continue
        out.append({"id": ap.id, "form_code": ap.form_code, "title": FORMS[ap.form_code]["title"],
                    "created": ap.created.isoformat() + "Z", "faculty": us.full_name, "email": us.email,
                    "papers": json.loads(ap.papers)})
    return out


@app.get("/api/admin/applications/{app_id}/download")
def admin_download(app_id: int, a: User = Depends(admin_user)):
    with Session() as db:
        ap = db.get(Application, app_id)
        if not ap:
            raise HTTPException(404, "Not found")
        path, code, stamp = DATA / "outputs" / ap.filename, FORMS[ap.form_code]["code"], ap.created.strftime("%Y%m%d")
    return FileResponse(path, filename=f"Annexure_{code}_{stamp}{path.suffix}")


@app.get("/api/admin/users")
def admin_users(a: User = Depends(admin_user)):
    with Session() as db:
        return [{"id": x.id, "full_name": x.full_name, "email": x.email} for x in db.query(User).order_by(User.full_name)]


class ResetPw(BaseModel):
    new_password: str


@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset(user_id: int, r: ResetPw, a: User = Depends(admin_user)):
    if len(r.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    with Session() as db:
        x = db.get(User, user_id)
        if not x:
            raise HTTPException(404, "Not found")
        x.pw_hash = bcrypt.hashpw(r.new_password.encode(), bcrypt.gensalt()).decode()
        db.commit()
    return {"ok": True}


def purge_old(now=None):
    """Delete applications (and their files) older than the retention period."""
    cutoff = (now or dt.datetime.utcnow()) - dt.timedelta(days=RETENTION_DAYS)
    n = 0
    with Session() as db:
        for ap in db.query(Application).filter(Application.created < cutoff).all():
            (DATA / "outputs" / ap.filename).unlink(missing_ok=True)
            db.delete(ap)
            n += 1
        db.commit()
    return n


def _purge_loop():
    import time
    while True:
        try:
            purge_old()
        except Exception:
            pass
        time.sleep(24 * 3600)


@app.on_event("startup")
def _start_purge():
    import threading
    threading.Thread(target=_purge_loop, daemon=True).start()


DIST = BASE.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
