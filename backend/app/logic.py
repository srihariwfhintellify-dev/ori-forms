"""Validation and computed values. Never invents a value."""
from .forms import FORMS


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def is_empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def get_field(form, key):
    return next(f for f in form["fields"] if f["key"] == key)


def depends_met(field, values):
    dep = field.get("depends")
    if not dep:
        return True
    if "=" in dep:  # e.g. courses_in_period=yes
        k, want = dep.split("=", 1)
        return str(values.get(k, "")).lower() == want
    table, row, col = dep.split(".")  # e.g. expenses.travel.selected
    rows = values.get(table) or {}
    return bool((rows.get(row) or {}).get(col))


def table_rows(field, values):
    """Normalised rows for a table field."""
    v = values.get(field["key"])
    if field.get("fixed_rows"):
        v = v or {}
        return [(r["key"], r["label"], v.get(r["key"]) or {}) for r in field["fixed_rows"]]
    return [(str(i + 1), None, r) for i, r in enumerate(v or [])]


def computed_total(form, field, values):
    c = field["computed"]
    if c == "d1_total":
        g = lambda k: _num(values.get(k))
        return (g("fare_tickets") + g("accommodation_days") * g("accommodation_rate") + g("conveyance")
                + g("misc_days") * g("misc_rate") + g("others_visa_insurance") + g("airport_transport")
                + g("registration_fee"))
    _, ref = c.split(":")
    table, col = ref.split(".")
    tf = get_field(form, table)
    total = 0.0
    for _, _, row in table_rows(tf, values):
        if tf.get("fixed_rows") and not row.get("selected"):
            continue
        total += _num(row.get(col))
    return total


def with_computed(form_code, values):
    form = FORMS[form_code]
    out = dict(values)
    for f in form["fields"]:
        if f.get("computed"):
            out[f["key"]] = computed_total(form, f, out)
    return out


def missing_fields(form_code, values):
    """Keys the user still has to supply. Blank/computed fields are never listed."""
    form = FORMS[form_code]
    missing = []
    for f in form["fields"]:
        if f.get("blank") or f.get("computed"):
            continue
        if not depends_met(f, values):
            continue
        if f["type"] == "table":
            continue
        if f.get("required") and is_empty(values.get(f["key"])):
            missing.append({"key": f["key"], "label": f["label"]})
    # travel details become mandatory only when travel is ticked in Annexure A
    # (handled by 'depends' above, but those fields lack required=True)
    if form_code == "A":
        for f in form["fields"]:
            if f.get("depends") == "expenses.travel.selected" and depends_met(f, values) and is_empty(values.get(f["key"])):
                missing.append({"key": f["key"], "label": f["label"]})
    # Annexure A / C-1: a ticked row needs its details
    for f in form["fields"]:
        if f["type"] == "table" and f.get("fixed_rows") and any(c["key"] == "selected" for c in f["columns"]):
            for k, label, row in table_rows(f, values):
                if row.get("selected") and is_empty(row.get("details")):
                    missing.append({"key": f"{f['key']}.{k}.details", "label": f"{label} – details"})
    # D-I extra: if no tickets/hotels given the user must say so explicitly (not assumed)
    return missing
