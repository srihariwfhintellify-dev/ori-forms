import React from "react";

const dependsMet = (f, v) => {
  if (!f.depends) return true;
  if (f.depends.includes("=")) {
    const [k, want] = f.depends.split("=");
    return String(v[k] ?? "").toLowerCase() === want;
  }
  const [t, r, c] = f.depends.split(".");
  return !!(v[t]?.[r]?.[c]);
};

function Source({ s, edited }) {
  if (!s) return null;
  if (s.origin === "account") return edited ? <div className="src edited">Edited by you</div> : <div className="src">From your account. Please confirm.</div>;
  if (s.rows) {
    return (
      <details className="src paper">
        <summary>Rows filled from your documents. Check sources{edited ? " (you have edited this table)" : ""}.</summary>
        {s.rows.map((r, i) => (
          <div key={i} className="srcrow">
            <strong>{r.label}</strong> <span className="muted small">({r.doc})</span>
            {r.inferred && <div className="inferred">Worked out from context. Please confirm.</div>}
            {(r.quotes || []).map((q, j) => <blockquote key={j}>“{q}”</blockquote>)}
          </div>
        ))}
      </details>
    );
  }
  if (edited) return <div className="src edited">Edited by you</div>;
  const quotes = s.quotes && s.quotes.length ? s.quotes : [s.quote];
  return (
    <details className="src paper">
      <summary>{s.inferred ? "Worked out from your document. Please confirm." : "Found in your document. Check source."}{s.doc ? ` (${s.doc})` : ""}</summary>
      {quotes.map((q, j) => <blockquote key={j}>“{q}”</blockquote>)}
    </details>
  );
}

function Input({ f, value, onChange, invalid }) {
  const cls = invalid ? "invalid" : "";
  switch (f.type) {
    case "longtext":
      return <textarea className={cls} rows={4} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
    case "date":
      return (
        <div className="row">
          <input className={cls} type="date" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
          {f.key === "date" && (
            <button type="button" className="link" onClick={() => onChange(new Date().toISOString().slice(0, 10))}>
              Use today
            </button>
          )}
        </div>
      );
    case "number":
      return <input className={cls} type="number" min="0" step="any" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />;
    case "yesno":
      return (
        <div className={"choices " + cls}>
          {["yes", "no"].map((o) => (
            <label key={o}><input type="radio" checked={value === o} onChange={() => onChange(o)} /> {o === "yes" ? "Yes" : "No"}</label>
          ))}
        </div>
      );
    case "choice":
      return (
        <div className={"choices " + cls}>
          {f.options.map((o) => (
            <label key={o}><input type="radio" checked={value === o} onChange={() => onChange(o)} /> {o}</label>
          ))}
        </div>
      );
    default:
      return <input className={cls} type="text" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
  }
}

function CellInput({ c, value, onChange, invalid }) {
  if (c.type === "checkbox")
    return <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />;
  if (c.type === "choice")
    return (
      <select value={value ?? ""} className={invalid ? "invalid" : ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select…</option>
        {c.options.map((o) => <option key={o}>{o}</option>)}
      </select>
    );
  return <Input f={c} value={value} onChange={onChange} invalid={invalid} />;
}

function TableEditor({ f, value, onChange, missingKeys }) {
  const cols = f.columns;
  if (f.fixed_rows) {
    const v = value || {};
    const set = (rk, ck, nv) => onChange({ ...v, [rk]: { ...(v[rk] || {}), [ck]: nv } });
    return (
      <div className="tablewrap">
        <table>
          <thead><tr><th>Head</th>{cols.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
          <tbody>
            {f.fixed_rows.map((r) => (
              <tr key={r.key}>
                <td className="rowlabel">{r.label}</td>
                {cols.map((c) => (
                  <td key={c.key}>
                    <CellInput c={c} value={v[r.key]?.[c.key]} onChange={(nv) => set(r.key, c.key, nv)}
                      invalid={missingKeys.has(`${f.key}.${r.key}.${c.key}`)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  const rows = value || [];
  const setCell = (i, ck, nv) => onChange(rows.map((r, j) => (j === i ? { ...r, [ck]: nv } : r)));
  const canAdd = !f.max_rows || rows.length < f.max_rows;
  return (
    <div className="tablewrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c.key}>{c.label}</th>)}<th /></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c.key}><CellInput c={c} value={r[c.key]} onChange={(nv) => setCell(i, c.key, nv)} /></td>
              ))}
              <td><button type="button" className="link danger" onClick={() => onChange(rows.filter((_, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={cols.length + 1} className="empty">No rows added.</td></tr>}
        </tbody>
      </table>
      {canAdd && <button type="button" className="secondary small" onClick={() => onChange([...rows, {}])}>+ Add row</button>}
      {f.max_rows && <span className="muted"> (max {f.max_rows} rows on the form)</span>}
    </div>
  );
}

export default function FormEditor({ form, values, setValues, sources, setSources, missing, computed, notFound }) {
  const missingKeys = new Set(missing.map((m) => m.key));
  const nf = new Set(notFound);
  const [edited, setEdited] = React.useState({});

  const update = (key, v) => {
    setValues((p) => ({ ...p, [key]: v }));
    if (sources[key]) setEdited((e) => ({ ...e, [key]: true }));
  };

  return (
    <div className="editor">
      {form.fields.map((f) => {
        if (f.blank) {
          return (
            <div key={f.key} className="field blankfield">
              <label>{f.label}</label>
              <div className="muted">Left blank on the form (office use / signature).</div>
            </div>
          );
        }
        if (!dependsMet(f, values)) return null;
        if (f.computed) {
          return (
            <div key={f.key} className="field computed">
              <label>{f.label}</label>
              <div className="calc">₹ {Number(computed[f.key] ?? 0).toLocaleString("en-IN")}</div>
              <div className="muted">Calculated automatically from the amounts you entered.</div>
            </div>
          );
        }
        const invalid = missingKeys.has(f.key);
        return (
          <div key={f.key} className={"field" + (invalid ? " needs" : "")}>
            <label>
              {f.label}{f.required || f.depends === "expenses.travel.selected" ? <span className="req"> *</span> : null}
            </label>
            {f.type === "table" ? (
              <TableEditor f={f} value={values[f.key]} onChange={(v) => update(f.key, v)} missingKeys={missingKeys} />
            ) : (
              <Input f={f} value={values[f.key]} onChange={(v) => update(f.key, v)} invalid={invalid} />
            )}
            <Source s={sources[f.key]} edited={edited[f.key]} />
            {nf.has(f.key) && !values[f.key] && <div className="hint">Not found in your documents. Please enter it.</div>}
            {invalid && <div className="err">Required</div>}
          </div>
        );
      })}
    </div>
  );
}
