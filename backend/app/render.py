"""Generate the filled Word / Excel files. Anything not supplied stays blank."""
import io
from pathlib import Path

import openpyxl
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Cm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from .forms import FORMS
from .logic import depends_met, table_rows, with_computed

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
INSTITUTE = "S P Jain Institute of Management & Research"
BOX_ON, BOX_OFF = "☒", "☐"


from .docx_forms import render_docx  # noqa: E402


# ------------------------------------------------------------------ xlsx (D-II)
_ROWS = {"travel": (10, 14), "accommodation": (17, 19), "food": (22, 26)}
_COLS = {
    "travel": {"mode": "C", "date": "D", "from": "E", "to": "F", "bill": "G", "currency": "H", "value": "I"},
    "accommodation": {"hotel": "C", "from_date": "D", "to_date": "E", "days": "F", "bill": "G", "currency": "H", "value": "I"},
    "food": {"date": "C", "bill": "G", "currency": "H", "value": "I"},
}
_OTHERS = {"registration": 29, "visa_insurance": 31, "misc": 33}


def render_xlsx(form_code, values):
    wb = openpyxl.load_workbook(TEMPLATES / "D2_expense_claim.xlsx")
    ws = wb.active
    ws["D2"] = values.get("name")
    ws["D3"] = values.get("event_date")
    ws["D4"] = values.get("purpose")
    ws["D5"] = values.get("location")
    ws["H4"] = values.get("scope") == "INTERNATIONAL"
    ws["H5"] = values.get("scope") == "DOMESTIC"
    for sec, (r0, r1) in _ROWS.items():
        for i, row in enumerate((values.get(sec) or [])[: r1 - r0 + 1]):
            for k, col in _COLS[sec].items():
                if row.get(k) not in (None, ""):
                    ws[f"{col}{r0 + i}"] = row[k]
    others = values.get("others") or {}
    for key, r in _OTHERS.items():
        row = others.get(key) or {}
        for k, col in {"details": "D", "bill": "G", "currency": "H", "value": "I"}.items():
            if row.get(k) not in (None, ""):
                ws[f"{col}{r}"] = row[k]
    # totals per currency are live formulas; advances are typed by the user
    for r_tot, r_adv, r_bal, cur, akey in [(35, 38, 41, "INR", "advance_inr"), (36, 39, 42, "USD", "advance_usd"), (37, 40, 43, "EURO", "advance_eur")]:
        ws[f"I{r_tot}"] = f'=SUMIFS(I10:I34,H10:H34,"{cur}")'
        if values.get(akey) not in (None, ""):
            ws[f"I{r_adv}"] = values[akey]
        ws[f"I{r_bal}"] = f"=I{r_tot}-N(I{r_adv})"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render(form_code, values):
    if FORMS[form_code]["kind"] == "xlsx":
        return render_xlsx(form_code, values), "xlsx"
    return render_docx(form_code, values), "docx"
