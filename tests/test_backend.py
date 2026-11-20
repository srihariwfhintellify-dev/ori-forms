import os, sys, tempfile, json
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "backend"))
os.environ["ORI_DATA_DIR"] = tempfile.mkdtemp()
os.environ["ORI_ADMIN_EMAILS"] = "ori@spjimr.org"
os.environ.pop("GEMINI_API_KEY", None)
from fastapi.testclient import TestClient
from app.main import app
from app.extract import verify, extractable_fields
from app.logic import missing_fields
from app.render import render
from app.forms import FORMS

# --- no-guess rule: fabricated quote must be rejected
text = "We study mutual funds. Authors: Asha Rao and Dev Patel. Title: Flows and Fear."
fields = extractable_fields("D1")
data = {"article_title": {"value": "Flows and Fear", "quote": "Title: Flows and Fear."},
        "co_authors": {"value": "Dev Patel", "quote": "Authors: Asha Rao and Dev Patel."},
        "target_journals": {"value": "Journal of Finance", "quote": "to be submitted to the Journal of Finance"}}
vals, src, nf = verify(fields, data, text)
assert vals["article_title"] == "Flows and Fear" and vals["co_authors"] == "Dev Patel"
assert "target_journals" in nf and "target_journals" not in vals, "fabricated quote accepted!"
print("verify OK; not found:", nf)

# --- missing-field logic
m = {x["key"] for x in missing_fields("D1", {})}
assert "conference_name" in m and "signature" not in m and "total_amount" not in m
mA = {x["key"] for x in missing_fields("A", {"expenses": {"travel": {"selected": True}}})}
assert "objectives" in mA and "travel_purpose" in mA and "expenses.travel.details" in mA
mA2 = {x["key"] for x in missing_fields("A", {})}
assert "objectives" not in mA2 and "pid" not in mA2
print("missing OK")

# --- render every form with sample data
S = dict(faculty_name="Asha Rao", date="2026-11-17", pid="PID-1", research_title="Flows and Fear")
samples = {
 "A": dict(S, project_name="Flows", description="d", co_researchers="Dev", q_spjimr_data="yes", q_ethics="no", q_annexure_f="no",
           expenses={"travel": {"selected": True, "details": "Delhi", "amount": 20000}, "ra_stipend": {"selected": True, "details": "RA", "amount": "5000"}},
           objectives="o", methodology="m", coauthor_roles="r", travel_purpose="p", travel_necessity="n", travel_hotel=1, travel_tickets=2, travel_local=3, travel_misc=4, travel_benefit="b"),
 "B": dict(S, expenses=[{"head": FORMS["B"]["fields"][4]["heads"][0]["label"], "invoice": "INV1", "dated": "2026-10-01", "amount": 1500, "comment": ""},
                         {"head": FORMS["B"]["fields"][4]["heads"][0]["label"], "invoice": "INV2", "dated": "2026-10-02", "amount": 500}]),
 "C1": dict(S, funding={"membership": {"selected": True, "details": "AOM, Rs 9000"}}, outcomes="x"),
 "C2": dict(S, expenses=[{"category": FORMS["C2"]["fields"][1]["heads"][0]["label"], "invoice": "I", "dated": "2026-10-01", "total_inr": 100}]),
 "D1": dict(S, co_authors="Dev", conference_name="C", organizer="O", dates="1-3 Dec", city_country="X", period="3 days", registration_fee=100,
            publication_fee=0, article_title="T", target_journals="J", journal_send_month="Jan 2027", courses_in_period="no",
            benefit_faculty="a", benefit_institute="b", brown_bag_date="Feb", contribution_type="Academic Research Paper",
            submission_type="A full paper", tickets_a=[{"from":"BOM","to":"DEL","date":"2026-12-01","day":"Tue","mode":"Flt","timing":"08:00","cls":"Eco","rem":""}], hotels=[{"city":"Delhi","hotel":"X","room_type":"S","tariff":5000,"from_date":"2026-12-01","to_date":"2026-12-03"}], fare_tickets=1000, accommodation_days=2, accommodation_rate=500, conveyance=0, misc_days=2,
            misc_rate=100, others_visa_insurance=0, airport_transport=0, advance_required=0, advance_mode="Cash"),
 "D2": dict(name="Asha Rao", event_date="1-3 Dec", purpose="Conf", location="Delhi", scope="DOMESTIC",
            travel=[{"mode": "Flight", "date": "2026-12-01", "from": "BOM", "to": "DEL", "bill": "Yes", "currency": "INR", "value": 8000}],
            accommodation=[{"hotel": "H", "from_date": "a", "to_date": "b", "days": 2, "bill": "Yes", "currency": "INR", "value": 6000}],
            food=[], others={"registration": {"details": "reg", "bill": "Yes", "currency": "USD", "value": 100}}, advance_inr=5000),
}
out = tempfile.mkdtemp()
for code, v in samples.items():
    assert not missing_fields(code, v), (code, missing_fields(code, v))
    blob, ext = render(code, v)
    open(f"{out}/{code}.{ext}", "wb").write(blob)
print("rendered to", out)

# --- API: auth, isolation, missing -> 422, create, download
c = TestClient(app)
assert c.get("/api/forms").status_code == 401
r = c.post("/api/auth/register", json={"email": "a@spjimr.org", "password": "password1", "full_name": "Asha Rao"}); assert r.status_code == 200, r.text
tok = r.json()["token"]; H = {"Authorization": "Bearer " + tok}
r2 = c.post("/api/auth/register", json={"email": "b@spjimr.org", "password": "password1", "full_name": "B"}); H2 = {"Authorization": "Bearer " + r2.json()["token"]}
assert c.post("/api/auth/login", json={"email": "a@spjimr.org", "password": "wrong"}).status_code == 401
r = c.post("/api/applications", headers=H, json={"form_code": "B", "values": {"faculty_name": "Asha"}})
assert r.status_code == 422 and r.json()["detail"]["missing"], r.text
r = c.post("/api/applications", headers=H, json={"form_code": "B", "values": samples["B"], "papers": ["p.pdf"]}); assert r.status_code == 200, r.text
aid = r.json()["id"]
assert c.get(f"/api/applications/{aid}/download", headers=H).status_code == 200
assert c.get(f"/api/applications/{aid}/download", headers=H2).status_code == 404, "another user could download!"
assert len(c.get("/api/applications", headers=H).json()) == 1 and len(c.get("/api/applications", headers=H2).json()) == 0
# extract with no paper: nothing invented, everything reported not found
r = c.post("/api/extract", headers=H, data={"form_code": "D1"}); j = r.json()
assert {"co_authors", "article_title", "target_journals"} <= set(j["not_found"]) and j["values"] == {"faculty_name": "Asha Rao"}, j
print("API OK")

# --- sign-up limited to @spjimr.org
assert c.post("/api/auth/register", json={"email": "z@gmail.com", "password": "password1", "full_name": "Z"}).status_code == 400

# --- admin: only listed emails; sees everyone's applications; can reset a password
ra = c.post("/api/auth/register", json={"email": "ori@spjimr.org", "password": "adminpass1", "full_name": "ORI Admin"}); HA = {"Authorization": "Bearer " + ra.json()["token"]}
assert ra.json()["is_admin"] is True and tok and c.get("/api/me", headers=H).json()["is_admin"] is False
assert c.get("/api/admin/applications", headers=H).status_code == 403
rows = c.get("/api/admin/applications", headers=HA).json(); assert len(rows) == 1 and rows[0]["email"] == "a@spjimr.org"
assert c.get(f"/api/admin/applications/{rows[0]['id']}/download", headers=HA).status_code == 200
uid = [u for u in c.get("/api/admin/users", headers=HA).json() if u["email"] == "a@spjimr.org"][0]["id"]
assert c.post(f"/api/admin/users/{uid}/reset-password", headers=HA, json={"new_password": "newpass123"}).status_code == 200
assert c.post("/api/auth/login", json={"email": "a@spjimr.org", "password": "newpass123"}).status_code == 200
assert c.post("/api/auth/login", json={"email": "a@spjimr.org", "password": "password1"}).status_code == 401

# --- retention: applications older than 5 years are deleted with their files
import datetime as dt
from app import main as M
with M.Session() as db:
    ap = db.get(M.Application, aid); fn = ap.filename; ap.created = dt.datetime.utcnow() - dt.timedelta(days=1830); db.commit()
assert M.purge_old() == 1 and not (M.DATA / "outputs" / fn).exists()
assert c.get("/api/applications", headers=H).json() == []
print("admin/domain/retention OK")

# --- Gemini path (stubbed): quotes must exist in the paper, otherwise the field is returned as missing
from app.extract import run_extraction
paper = "Flows and Fear\nAsha Rao, Dev Patel\nAbstract: We study how mutual fund flows react to fear.\nMethodology: panel regression on 2010-2020 data."
reply = json.dumps({"project_name": {"value": "Flows and Fear", "quote": "Flows and Fear"},
    "description": {"value": "We study how mutual fund flows react to fear.", "quote": "We study how mutual fund flows react to fear."},
    "co_researchers": {"value": "Dev Patel", "quote": "Asha Rao, Dev Patel"},
    "objectives": {"value": "to test fear effects", "quote": "we aim to test fear effects"},
    "methodology": {"value": "panel regression on 2010-2020 data", "quote": "Methodology: panel   regression on 2010-2020 data."},
    "coauthor_roles": None})
v, s, nf = run_extraction("A", paper, "Asha Rao", generate=lambda prompt, model=None: reply)
assert set(v) == {"project_name", "description", "co_researchers", "methodology"} and {"objectives", "coauthor_roles"} <= set(nf), (v, nf)
print("gemini stub OK")

# --- 504 / daily-quota handling (stubbed Gemini)
from app import extract as X
X.MODEL, X.FALLBACK_MODEL = "main-model", "backup-model"
calls = []
def slow_then_ok(prompt, model):
    calls.append(model)
    if model == "main-model":
        raise Exception("504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.")
    return reply
v, s, nf = run_extraction("A", paper, "Asha Rao", generate=slow_then_ok)
assert calls == ["main-model", "main-model", "backup-model"] and "project_name" in v, calls
calls.clear()
def daily(prompt, model):
    calls.append(model)
    if model == "main-model":
        raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    return reply
v, s, nf = run_extraction("A", paper, "Asha Rao", generate=daily)
assert calls == ["main-model", "backup-model"], "daily quota must not be retried on the same model: %s" % calls
def both_daily(prompt, model):
    raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
try:
    run_extraction("A", paper, "Asha Rao", generate=both_daily); raise SystemExit("should have failed")
except X.ExtractionError as e:
    assert "daily request limit" in str(e)
print("fallback/quota handling OK")

# --- a dead fallback model (404) must not hide the main model's real error
def main_504_backup_404(prompt, model):
    if model == "main-model":
        raise Exception("504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.")
    raise Exception("404 NOT_FOUND. This model is no longer available")
try:
    run_extraction("A", paper, "Asha Rao", generate=main_504_backup_404); raise SystemExit("should have failed")
except X.ExtractionError as e:
    assert "did not answer in time" in str(e) and "404" not in str(e), str(e)
X.FALLBACK_MODEL = ""
calls.clear()
def always_504(prompt, model):
    calls.append(model); raise Exception("504 DEADLINE_EXCEEDED")
try:
    run_extraction("A", paper, "Asha Rao", generate=always_504)
except X.ExtractionError:
    pass
assert set(calls) == {"main-model"}, calls
print("dead-fallback handling OK")

# --- Hugging Face path (stubbed HTTP)
import httpx
X.PROVIDER, X.LABEL, X.MODEL, X.FALLBACK_MODEL = "huggingface", "Hugging Face", "hf-model", ""
os.environ["HF_TOKEN"] = "x"
class R:
    def __init__(self, code, body): self.status_code, self._b, self.text = code, body, str(body)
    def json(self): return self._b
sent = {}
def ok_post(url, **kw):
    sent.update(url=url, auth=kw["headers"]["Authorization"], model=kw["json"]["model"])
    return R(200, {"choices": [{"message": {"content": reply}}]})
httpx.post = ok_post
v, s, nf = run_extraction("A", paper, "Asha Rao")
assert sent["url"].endswith("/chat/completions") and sent["auth"] == "Bearer x" and sent["model"] == "hf-model" and "project_name" in v
# hallucinated quote still rejected on this path
bad = json.dumps({"project_name": {"value": "Invented", "quote": "not in the paper"}})
httpx.post = lambda url, **kw: R(200, {"choices": [{"message": {"content": bad}}]})
v, s, nf = run_extraction("A", paper, "Asha Rao"); assert "project_name" not in v and "project_name" in nf
httpx.post = lambda url, **kw: R(402, "payment required")
try: run_extraction("A", paper, "Asha Rao"); raise SystemExit("should fail")
except X.ExtractionError as e: assert "credits are used up" in str(e)
X.MODEL = ""
assert X.configured()[0] is False
print("huggingface path OK")

# --- Groq path (stubbed HTTP, no real waiting)
X.time.sleep = lambda s: None
X.PROVIDER, X.LABEL, X.MODEL, X.FALLBACK_MODEL, X.MAX_CHARS = "groq", "Groq", "llama-3.3-70b-versatile", "", 24000
os.environ["GROQ_API_KEY"] = "gk"
assert X.configured()[0]
class R2(R):
    def __init__(self, code, body, headers=None): super().__init__(code, body); self.headers = headers or {}
seen = []
def groq_ok(url, **kw):
    seen.append((url, kw["headers"]["Authorization"], kw["json"]["model"], kw["json"].get("response_format"), len(kw["json"]["messages"][1]["content"])))
    return R2(200, {"choices": [{"message": {"content": reply}}]})
httpx.post = groq_ok
v, s, nf = run_extraction("A", paper, "Asha Rao")
assert seen[0][:4] == ("https://api.groq.com/openai/v1/chat/completions", "Bearer gk", "llama-3.3-70b-versatile", {"type": "json_object"}), seen[0]
assert "project_name" in v
# 413 (too large for the per-minute token cap) -> retried with less text
big = paper + "\n" + ("filler words " * 4000)
seen.clear(); state = {"n": 0}
def too_large_then_ok(url, **kw):
    state["n"] += 1; seen.append(len(kw["json"]["messages"][1]["content"]))
    if state["n"] == 1: return R2(413, "Request too large ... tokens per minute (TPM)")
    return R2(200, {"choices": [{"message": {"content": reply}}]})
httpx.post = too_large_then_ok
v, s, nf = run_extraction("A", big, "Asha Rao"); assert seen[1] < seen[0] and "project_name" in v, seen
# 429 per-minute -> waits (Retry-After) and retries; daily -> stops with a clear message
state["n"] = 0
def tpm_then_ok(url, **kw):
    state["n"] += 1
    if state["n"] == 1: return R2(429, "Rate limit reached ... tokens per minute (TPM)", {"retry-after": "7"})
    return R2(200, {"choices": [{"message": {"content": reply}}]})
httpx.post = tpm_then_ok
v, s, nf = run_extraction("A", paper, "Asha Rao"); assert state["n"] == 2 and "project_name" in v
httpx.post = lambda url, **kw: R2(429, "Rate limit reached ... requests per day (RPD): Limit 1000")
try: run_extraction("A", paper, "Asha Rao"); raise SystemExit("should fail")
except X.ExtractionError as e: assert "daily request limit" in str(e) and "Groq" in str(e), str(e)
httpx.post = lambda url, **kw: R2(401, "bad key")
try: run_extraction("A", paper, "Asha Rao"); raise SystemExit("should fail")
except X.ExtractionError as e: assert "rejected the API key" in str(e)
os.environ.pop("GROQ_API_KEY"); assert X.configured()[0] is False
print("groq path OK")

# --- Groq: current default model, optional settings, and fallback when a setting is rejected
import importlib
assert 'GROQ_MODEL", "openai/gpt-oss-120b"' in open(X.__file__).read()
X.PROVIDER, X.LABEL, X.MODEL, X.FALLBACK_MODEL, X.MAX_CHARS = "groq", "Groq", "openai/gpt-oss-120b", "", 14000
os.environ["GROQ_API_KEY"] = "gk"; sent_opts = []
def strict(url, **kw):
    sent_opts.append({k: kw["json"].get(k) for k in ("response_format", "reasoning_effort")})
    if kw["json"].get("reasoning_effort"): return R2(400, "unknown parameter: reasoning_effort")
    return R2(200, {"choices": [{"message": {"content": reply}, "finish_reason": "stop"}]})
httpx.post = strict
v, s, nf = run_extraction("A", paper, "Asha Rao")
assert sent_opts[0]["reasoning_effort"] == "medium" and sent_opts[1] == {"response_format": None, "reasoning_effort": None} and "project_name" in v, sent_opts
httpx.post = lambda url, **kw: R2(404, '{"error":{"code":"model_not_found"}}')
try: run_extraction("A", paper, "Asha Rao"); raise SystemExit("should fail")
except X.ExtractionError as e: assert "not available to this key" in str(e) and "gpt-oss-120b" in str(e), str(e)
print("groq gpt-oss handling OK")
