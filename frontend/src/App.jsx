import React from "react";
import { api, setToken, hasToken } from "./api.js";
import FormEditor from "./FormEditor.jsx";

function Auth({ onDone }) {
  const [mode, setMode] = React.useState("login");
  const [f, setF] = React.useState({ email: "", password: "", full_name: "" });
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [progress, setProgress] = React.useState(null);
  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const r = mode === "login" ? await api.login(f) : await api.register(f);
      setToken(r.token);
      onDone({ full_name: r.full_name, email: r.email, is_admin: r.is_admin });
    } catch (x) { setErr(x.message); } finally { setBusy(false); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="authwrap">
      <form className="card auth" onSubmit={submit}>
        <h1>SPJIMR Office of Research &amp; Innovation</h1>
        <p className="muted">Faculty application forms (use your @spjimr.org email)</p>
        {mode === "register" && (
          <div className="field"><label>Full name (as it should appear on forms)</label><input value={f.full_name} onChange={set("full_name")} required /></div>
        )}
        <div className="field"><label>Email</label><input type="email" value={f.email} onChange={set("email")} required /></div>
        <div className="field"><label>Password</label><input type="password" minLength={mode === "register" ? 8 : 1} value={f.password} onChange={set("password")} required /></div>
        {err && <div className="err">{err}</div>}
        <button disabled={busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="link" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}

function Home({ forms, user, go }) {
  const [hist, setHist] = React.useState(null);
  const load = () => api.history().then(setHist).catch(() => setHist([]));
  React.useEffect(() => { load(); }, []);
  return (
    <div>
      <h2>Choose an application</h2>
      <div className="grid">
        {Object.entries(forms).map(([k, f]) => (
          <button key={k} className="card formcard" onClick={() => go({ view: "wizard", code: k })}>
            <span className="badge">{f.code}</span>
            <strong>{f.title.replace(/^Annexure [A-D](\s–\s)?/, "")}</strong>
            <span className="muted">{f.purpose}</span>
            <span className="muted small">Produces a {f.kind === "xlsx" ? "Excel" : "Word"} file</span>
          </button>
        ))}
      </div>
      <h2>Your previous applications</h2>
      {hist === null ? <p className="muted">Loading…</p> : hist.length === 0 ? <p className="muted">Nothing yet.</p> : (
        <div className="card">
          <table className="hist">
            <thead><tr><th>Form</th><th>Created</th><th>Paper(s)</th><th /></tr></thead>
            <tbody>
              {hist.map((h) => (
                <tr key={h.id}>
                  <td>{h.title}</td>
                  <td>{new Date(h.created).toLocaleString()}</td>
                  <td>{h.papers.join(", ") || "none"}</td>
                  <td className="actions">
                    <button className="secondary small" onClick={() => api.download(h.id, "application")}>Download</button>
                    <button className="secondary small" onClick={() => go({ view: "wizard", code: h.form_code, from: h.id })}>Reuse</button>
                    <button className="link danger" onClick={async () => { if (confirm("Delete this application permanently?")) { await api.remove(h.id); load(); } }}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Wizard({ forms, code, from, user, back }) {
  const form = forms[code];
  const [step, setStep] = React.useState(from ? "review" : "upload");
  const [files, setFiles] = React.useState([]);
  const [name, setName] = React.useState(user.full_name);
  const [values, setValues] = React.useState({});
  const [sources, setSources] = React.useState({});
  const [notFound, setNotFound] = React.useState([]);
  const [notes, setNotes] = React.useState([]);
  const [papers, setPapers] = React.useState([]);
  const [missing, setMissing] = React.useState([]);
  const [computed, setComputed] = React.useState({});
  const [busy, setBusy] = React.useState(false);
  const [progress, setProgress] = React.useState(null);
  const [err, setErr] = React.useState("");
  const [done, setDone] = React.useState(null);

  React.useEffect(() => {
    if (from) api.one(from).then((a) => { setValues(a.values); setSources({}); setPapers(a.papers); }).catch((e) => setErr(e.message));
  }, [from]);

  React.useEffect(() => {
    if (step !== "review") return;
    const t = setTimeout(() => {
      api.missing({ form_code: code, values }).then((r) => { setMissing(r.missing); setComputed(r.computed); }).catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [values, step, code]);

  const readPaper = async () => {
    setErr(""); setBusy(true);
    setProgress(files.length ? { pct: 5, msg: "Uploading paper..." } : null);
    try {
      const fd = new FormData();
      fd.append("form_code", code);
      fd.append("faculty_name", name);
      files.forEach((f) => fd.append("files", f));
      const r = files.length ? await api.extractStream(fd, setProgress) : await api.extract(fd);
      setValues(r.values); setSources(r.sources); setNotFound(r.not_found); setNotes(r.notes); setPapers(r.papers);
      setStep("review");
    } catch (e) { setErr(e.message); } finally { setBusy(false); setProgress(null); }
  };

  const generate = async () => {
    setErr(""); setBusy(true);
    try {
      const r = await api.create({ form_code: code, values, sources, papers });
      await api.download(r.id, "application");
      setDone(r.id);
    } catch (e) {
      if (e.status === 422) setErr("Some required details are still missing. They are highlighted below.");
      else setErr(e.message);
    } finally { setBusy(false); }
  };

  if (done) {
    return (
      <div className="card center">
        <h2>Your file has been generated</h2>
        <p>It downloaded to your device and is saved under “Your previous applications”.</p>
        <button onClick={() => api.download(done, "application")}>Download again</button>{" "}
        <button className="secondary" onClick={back}>Back to home</button>
      </div>
    );
  }

  return (
    <div>
      <button className="link" onClick={back}>← All applications</button>
      <h2>{form.title}</h2>
      {step === "upload" && (
        <div className="card">
          <div className="field">
            <label>Faculty name (used to tell you apart from co-authors)</label>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {form.can_extract ? (
            <div className="field">
              <label>Supporting documents (you can select several)</label>
              <input type="file" multiple accept=".pdf,.docx,.png,.jpg,.jpeg,.tif,.tiff,.eml,.txt,.md,.html,.htm" onChange={(e) => setFiles([...e.target.files])} />
              <div className="muted">
                {form.upload_help} Details are read from the sentences and tables in your documents. Only what the documents support is filled in; the rest is left for you. Nothing is guessed.
              </div>
            </div>
          ) : (
            <p className="muted">This form has no details that come from a document. You will fill it in on the next screen.</p>
          )}
          {err && <div className="err">{err}</div>}
          <button disabled={busy} onClick={readPaper}>
            {busy ? "Reading your documents…" : files.length ? "Read documents and continue" : "Continue without documents"}
          </button>
          {busy && progress && (
            <div className="progresswrap">
              <div className="progressbar"><div className="progressfill" style={{ width: `${progress.pct}%` }} /></div>
              <div className="muted small">{progress.msg} ({progress.pct}%)</div>
            </div>
          )}
        </div>
      )}
      {step === "review" && (
        <>
          {notes.map((n, i) => <div key={i} className="banner warn">{n}</div>)}
          {papers.length > 0 && !from && (
            <div className="banner">
              Filled from: {papers.join(", ")}. Open “Check source” under a field to see the exact passage.
              {notFound.length > 0 && ` ${notFound.length} item(s) were not in the documents and need your input.`}
            </div>
          )}
          <FormEditor form={form} values={values} setValues={setValues} sources={sources} setSources={setSources}
            missing={missing} computed={computed} notFound={notFound} />
          <div className="stickybar">
            <span className={missing.length ? "err" : "ok"}>
              {missing.length ? `${missing.length} required detail(s) still needed` : "All required details are complete"}
            </span>
            {err && <span className="err"> {err}</span>}
            <button disabled={busy || missing.length > 0} onClick={generate}>{busy ? "Generating…" : "Generate file"}</button>
          </div>
        </>
      )}
    </div>
  );
}

function Admin({ forms, back }) {
  const [rows, setRows] = React.useState(null);
  const [users, setUsers] = React.useState([]);
  const [q, setQ] = React.useState("");
  const [form, setForm] = React.useState("");
  const [msg, setMsg] = React.useState("");
  React.useEffect(() => { api.adminApps(q, form).then(setRows).catch((e) => setMsg(e.message)); }, [q, form]);
  React.useEffect(() => { api.adminUsers().then(setUsers).catch(() => {}); }, []);
  const reset = async (u) => {
    const pw = prompt(`New password for ${u.full_name} (min 8 characters). Tell them to keep it private.`);
    if (!pw) return;
    try { await api.adminReset(u.id, pw); setMsg(`Password reset for ${u.email}.`); } catch (e) { setMsg(e.message); }
  };
  return (
    <div>
      <button className="link" onClick={back}>← Back</button>
      <h2>All applications</h2>
      <div className="row" style={{ marginBottom: 12 }}>
        <input type="text" placeholder="Search faculty name or email" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={form} onChange={(e) => setForm(e.target.value)} style={{ maxWidth: 220 }}>
          <option value="">All forms</option>
          {Object.entries(forms).map(([k, f]) => <option key={k} value={k}>{f.code}</option>)}
        </select>
      </div>
      {msg && <div className="banner">{msg}</div>}
      <div className="card tablewrap">
        <table className="hist">
          <thead><tr><th>Faculty</th><th>Form</th><th>Created</th><th>Paper(s)</th><th /></tr></thead>
          <tbody>
            {(rows || []).map((h) => (
              <tr key={h.id}>
                <td>{h.faculty}<div className="muted small">{h.email}</div></td>
                <td>{h.title}</td><td>{new Date(h.created).toLocaleString()}</td><td>{h.papers.join(", ") || "none"}</td>
                <td><button className="secondary small" onClick={() => api.download(h.id, "application", true)}>Download</button></td>
              </tr>
            ))}
            {rows && rows.length === 0 && <tr><td colSpan={5} className="empty">No applications found.</td></tr>}
          </tbody>
        </table>
      </div>
      <h2>Faculty accounts</h2>
      <div className="card tablewrap">
        <table className="hist">
          <thead><tr><th>Name</th><th>Email</th><th /></tr></thead>
          <tbody>{users.map((u) => (
            <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td><button className="secondary small" onClick={() => reset(u)}>Reset password</button></td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = React.useState(null);
  const [ready, setReady] = React.useState(!hasToken());
  const [forms, setForms] = React.useState(null);
  const [route, setRoute] = React.useState({ view: "home" });

  React.useEffect(() => {
    if (!hasToken()) return;
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);
  React.useEffect(() => { if (user) api.forms().then(setForms); }, [user]);

  if (!ready) return null;
  if (!user) return <Auth onDone={setUser} />;
  return (
    <>
      <header>
        <strong>SPJIMR · Office of Research &amp; Innovation</strong>
        <span>{user.is_admin && <button className="link" onClick={() => setRoute({ view: "admin" })}>Admin</button>} {user.full_name} <button className="link" onClick={() => { setToken(null); setUser(null); setForms(null); }}>Sign out</button></span>
      </header>
      <main>
        {!forms ? <p className="muted">Loading…</p> : route.view === "admin" ? <Admin forms={forms} back={() => setRoute({ view: "home" })} />
          : route.view === "home"
          ? <Home forms={forms} user={user} go={setRoute} />
          : <Wizard key={route.code + (route.from || "")} forms={forms} code={route.code} from={route.from} user={user} back={() => setRoute({ view: "home" })} />}
      </main>
    </>
  );
}
