"""Word versions of Annexures A, B, C-1, C-2 and D-I, laid out to match the original PDFs.

Rule: nothing is invented. A field with no value keeps its blank underscores / empty cell,
exactly as on the original form.
"""
import io

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .forms import FORMS
from .logic import table_rows, with_computed

FONT = "Arial"
ON, OFF = "☒", "☐"
INSTITUTE = "S P Jain Institute of Management & Research"
SIGN_LINE = "_" * 62


# ------------------------------------------------------------------ formatting
def money(v):
    if v in (None, ""):
        return ""
    try:
        n = float(str(v).replace(",", ""))
    except ValueError:
        return str(v)
    neg, n = n < 0, abs(n)
    whole, frac = divmod(round(n * 100), 100)
    s = str(whole)
    if len(s) > 3:  # Indian digit grouping
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    if frac:
        s += f".{frac:02d}"
    return ("-" if neg else "") + s


def dmy(v):
    s = str(v or "")
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:]}/{s[5:7]}/{s[:4]}"
    return s


def txt(v):
    return "" if v is None else str(v)


# ------------------------------------------------------------------ low level helpers
def new_doc(border=True, margins=(2.4, 1.6, 1.9, 1.9)):
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.top_margin, s.bottom_margin, s.left_margin, s.right_margin = (Cm(m) for m in margins)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.paragraph_format.space_after = Pt(0)
    st.paragraph_format.space_before = Pt(0)
    if border:
        pb = OxmlElement("w:pgBorders")
        pb.set(qn("w:offsetFrom"), "page")
        for side in ("top", "left", "bottom", "right"):
            e = OxmlElement(f"w:{side}")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "6")
            e.set(qn("w:space"), "24")
            e.set(qn("w:color"), "000000")
            pb.append(e)
        s._sectPr.append(pb)
    return doc


def run(p, text, b=False, i=False, u=False, size=None, sup=False, caps=False):
    r = p.add_run(text)
    r.bold, r.italic, r.underline = b, i, u
    r.font.name = FONT
    if size:
        r.font.size = Pt(size)
    if sup:
        r.font.superscript = True
    if caps:
        r.font.small_caps = True
    return r


def para(container, *parts, align=None, before=0, after=0, indent=None, hanging=None, size=None, line=None):
    """parts: str or (str, {b,i,u,size,sup,caps})."""
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    if indent is not None:
        pf.left_indent = Cm(indent)
    if hanging is not None:
        pf.first_line_indent = Cm(-hanging)
    if line:
        pf.line_spacing = line
    if align == "c":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for part in parts:
        if isinstance(part, str):
            run(p, part, size=size)
        else:
            t, kw = part
            kw = dict(kw)
            kw.setdefault("size", size)
            run(p, t, **kw)
    return p


def border_bottom(p, style="single", sz=12):
    pPr = p._p.get_or_add_pPr()
    b = OxmlElement("w:pBdr")
    e = OxmlElement("w:bottom")
    e.set(qn("w:val"), style)
    e.set(qn("w:sz"), str(sz))
    e.set(qn("w:space"), "1")
    e.set(qn("w:color"), "000000")
    b.append(e)
    pPr.append(b)


def rule(doc, style="single", sz=12, before=2, after=4):
    p = para(doc, "", before=before, after=after, size=4)
    border_bottom(p, style, sz)
    return p


def filled(p, value, blank_len, size=None, b=False):
    """Value underlined, or the original underscores when there is no value."""
    if value not in (None, ""):
        run(p, f" {value} ", u=True, size=size, b=b)
    else:
        run(p, "_" * blank_len, size=size, b=b)


def lines_block(doc, value, n_lines, indent=0.0, width=76, size=None):
    """Original has n ruled lines; a filled value replaces them (wrapping, underlined)."""
    if value not in (None, ""):
        for ln in str(value).split("\n"):
            para(doc, (ln, {"u": True}), indent=indent, size=size)
    else:
        for _ in range(n_lines):
            para(doc, "_" * width, indent=indent, size=size)


def _fixed(tbl):
    pr = tbl._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    pr.append(lay)


def table(doc, widths, grid=True, indent=0.0):
    t = doc.add_table(rows=0, cols=len(widths))
    if grid:
        t.style = "Table Grid"
    t.autofit = False
    _fixed(t)
    t._widths = widths
    for col, w in zip(t.columns, widths):
        col.width = Cm(w)
    if indent:
        pr = t._tbl.tblPr
        ind = OxmlElement("w:tblInd")
        ind.set(qn("w:w"), str(int(indent * 567)))
        ind.set(qn("w:type"), "dxa")
        pr.append(ind)
    return t


def row(t, cells, height=None, bold=False, size=10, align=None, italic_cols=()):
    """cells: list of str | list-of-parts. '\n' in str creates new paragraphs."""
    r = t.add_row()
    if height:
        r.height = Pt(height)
        r.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    for i, (c, w) in enumerate(zip(r.cells, t._widths)):
        c.width = Cm(w)
        content = cells[i] if i < len(cells) else ""
        first = True
        items = content if isinstance(content, list) else str(content).split("\n")
        for it in items:
            p = c.paragraphs[0] if first else c.add_paragraph()
            first = False
            if align and align[i] == "c":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if isinstance(it, tuple):
                run(p, it[0], **{"size": size, **it[1]})
            elif isinstance(it, list):
                for part in it:
                    if isinstance(part, tuple):
                        run(p, part[0], **{"size": size, **part[1]})
                    else:
                        run(p, part, size=size, b=bold)
            else:
                run(p, it, b=bold, size=size, i=(i in italic_cols))
    return r


def internal_use(doc, left=1.2, label="FOR INTERNAL USE ONLY", size=10, widths=(1.1, 5.4, 3.3, 2.4, 1.6)):
    p = para(doc, (label, {"caps": True}), before=2, indent=left)
    t = table(doc, list(widths), indent=left)
    row(t, ["SN.", "Steps completed", "Name", "Signature", "Date"], bold=True, size=size, align=["l", "l", "c", "c", "c"])
    row(t, ["1.", "Entered in the database", "", "", ""], size=size)
    row(t, ["2.", "Checked", "", "", ""], size=size)
    row(t, ["3.", "Communicated to faculty and accounts", "", "", ""], size=size)


def box(doc, text, height, width, indent=0.0, size=10):
    t = table(doc, [width], indent=indent)
    row(t, [text or ""], height=height, size=size)
    return t


def head_titles(doc, title, under=True, sub=True):
    para(doc, (title, {"b": True, "u": under}), align="c", size=12)
    if sub:
        para(doc, (INSTITUTE, {"b": True}), align="c", size=10.5)


def to_bytes(doc):
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def yesno(v):
    v = str(v or "").lower()
    return [(ON if v == "yes" else OFF) + " Yes     ", (ON if v == "no" else OFF) + " No"]


# ================================================================== A
def render_A(values):
    doc = new_doc(border=True)
    head_titles(doc, "ANNEXURE A – Research Project ID- PID Generation")
    para(doc, "", size=8)
    para(doc, ("Form to inform specific projects to be undertaken by the faculty member for the purpose of obtaining Project ID (PID)", {"b": True}), before=6)
    para(doc, ("Please fill out the soft copy of the form as applicable", {"b": True, "i": True}), before=10)

    p = para(doc, "Faculty Name:", before=12)
    filled(p, txt(values.get("faculty_name")), 31)
    run(p, "  Date: ")
    filled(p, dmy(values.get("date")), 31)

    p = para(doc, ("PID:", {"b": True}), before=10)
    run(p, " __________________ (to be filled up by ORI and inform concerned faculty and accounts)")

    p = para(doc, "Name of the research project:", before=8, size=9.5)
    filled(p, txt(values.get("project_name")), 62, size=9.5)
    para(doc, " (only one research project to be indicated in one form. For multiple research projects, please use separate copies of ",
         ("ANNEXURE A", {"b": True}), ")")

    para(doc, ("Brief description:", {"b": True}), before=10)
    lines_block(doc, values.get("description"), 6)
    para(doc, ("Name of the co-researcher(s) in the project:", {"b": True}), before=10)
    lines_block(doc, values.get("co_researchers"), 1)
    rule(doc, sz=12, before=2, after=8)
    para(doc, ("Please select the following estimated expenses in relation to the research project:", {"b": True}), before=4, after=8)

    exp = {k: r for k, _, r in table_rows(next(f for f in FORMS["A"]["fields"] if f["key"] == "expenses"), values)}
    labels = {k: l for k, l in [(r["key"], r["label"]) for r in next(f for f in FORMS["A"]["fields"] if f["key"] == "expenses")["fixed_rows"]]}

    def head_block(key, body_h=52):
        r = exp.get(key) or {}
        box_ = ON if r.get("selected") else OFF
        para(doc, f"{box_}{labels[key] if key != 'others' else ' ' + labels[key]}", before=4)
        t = table(doc, [8.0, 8.4], indent=0.15)
        row(t, ["Details of expenses under the head", "Expected amount"], size=10)
        row(t, [txt(r.get("details")), money(r.get("amount"))], height=body_h, size=10)

    for k in ("copy_editing", "software_hardware", "article_submission"):
        head_block(k)
    doc.add_page_break()

    # ---- travel (page 2)
    tr = exp.get("travel") or {}
    para(doc, f"{ON if tr.get('selected') else OFF}Project-related travel (i to vii are mandatory for travel requests)", before=40)
    items = [
        ("i.", "Research Objectives:", "objectives", "lines3"),
        ("ii.", "Research Methodology:", "methodology", "lines3"),
        ("iii.", "Role of Co-Authors:", "coauthor_roles", ("box", 24, 15.6)),
        ("iv.", "Purpose of Travel:", "travel_purpose", ("box", 26, 15.4)),
        ("v.", "Necessity for the Travel (E.g.: Cannot be substituted online or by co-authors):", "travel_necessity", ("box", 54, 15.8)),
    ]
    for num, label, key, kind in items:
        para(doc, f"{num}\t{label}", before=14, indent=1.2, hanging=1.2)
        if kind == "lines3":
            lines_block(doc, values.get(key), 3, indent=1.2, width=70)
        else:
            _, h, w = kind
            box(doc, txt(values.get(key)), h, w, indent=1.2)
    para(doc, "vi.\tTravel Expense Breakup:", before=14, indent=1.2, hanging=1.2)
    t = table(doc, [3.0, 3.4, 3.4, 3.8], indent=1.2)
    row(t, ["Hotel / Lodging", "Tickets", "Local Travel", "Miscellaneous"])
    row(t, [money(values.get("travel_hotel")), money(values.get("travel_tickets")),
            money(values.get("travel_local")), money(values.get("travel_misc"))], height=46)
    para(doc, "vii.\tBenefit to the Institute:", before=14, indent=1.2, hanging=1.2)
    box(doc, txt(values.get("travel_benefit")), 62, 15.6, indent=1.2)
    doc.add_page_break()

    # ---- remaining heads (page 3)
    para(doc, "", before=24)
    for k in ("journal_fee", "ra_stipend", "survey_gifts", "others"):
        head_block(k, body_h=44)
    para(doc, "", size=6)
    t = table(doc, [8.0, 8.4], indent=0.15)
    row(t, [[("Total Amount", {"b": True})], money(values.get("total_amount"))], size=10)
    para(doc, ("Please select the appropriate option, as applicable to the concerned project (please refer to the Research Policy, "
               "Section 5- SPJIMR Research Data Ownership Policy, for eligibility criteria concerning", {"b": True}), size=10.5)
    para(doc, ("ethics review for various research data types).", {"b": True}), size=10.5)
    qs = [("1) Does your study intend to utilize the ‘SPJIMR data’ (primary or secondary) for analysis?", "q_spjimr_data"),
          ("2) Does your study require an internal ethics review coordinated by ORI?", "q_ethics"),
          ("3) Does your study require furnishing of the Self-disclosure form (Annexure F)?", "q_annexure_f")]
    for i, (q, k) in enumerate(qs):
        para(doc, q, before=0 if i == 0 else 10, size=10.5)
        para(doc, *yesno(values.get(k)), size=10)
    p = para(doc, ("Faculty signature: ", {"b": True}), size=10.5)
    run(p, "_" * 70)
    para(doc, "", size=4)
    border_bottom(doc.paragraphs[-1], "dashed", 8)
    internal_use(doc)
    return to_bytes(doc)


# ================================================================== B
B_HEIGHTS = [83, 94, 84, 83, 104, 119, 103, 119]


def render_B(values):
    doc = new_doc(border=True, margins=(2.4, 1.6, 1.3, 1.3))
    head_titles(doc, "ANNEXURE B - Research Project Related", sub=True)
    para(doc, ("Form for reimbursing research project-related expenses from the Block Fund", {"b": True}), before=10)
    para(doc, ("Please fill out the soft copy of the form as applicable", {"b": True, "i": True}), before=10)
    p = para(doc, "Faculty Name:", before=34, indent=1.2)
    filled(p, txt(values.get("faculty_name")), 34)
    run(p, "Date: ")
    filled(p, dmy(values.get("date")), 12)
    p = para(doc, ("I. Project ID (PID, only one in the form): ", {"b": True}), before=14, indent=1.2)
    filled(p, txt(values.get("pid")), 40, b=True)
    p = para(doc, ("II. Research topic/title: ", {"b": True}), before=14, indent=1.2)
    filled(p, txt(values.get("research_title")), 40, b=True)
    para(doc, ("III. Details of expenses:", {"b": True}), before=14, after=8, indent=1.2)

    f = next(x for x in FORMS["B"]["fields"] if x["key"] == "expenses")
    rows = [r for _, _, r in table_rows(f, values)]
    widths = [4.2, 1.5, 3.6, 2.3, 2.0, 3.0]
    t = table(doc, widths, indent=1.2)
    row(t, ["Head(s)", "Sl. No.", "Invoice details", "Dated", "Amount", "Comment"], bold=True, size=10)
    for h, ht in zip(f["heads"], B_HEIGHTS):
        mine = [r for r in rows if r.get("head") == h["label"]]
        cells = [h["label"],
                 "\n".join(str(i) for i, _ in enumerate(mine, 1)),
                 "\n".join(txt(r.get("invoice")) for r in mine),
                 "\n".join(dmy(r.get("dated")) for r in mine),
                 "\n".join(money(r.get("amount")) for r in mine),
                 "\n".join(txt(r.get("comment")) for r in mine)]
        row(t, cells, height=ht, size=10)
    para(doc, "", size=8)
    t = table(doc, [16.4], indent=0.6)
    row(t, [[("Total Amount   ", {"b": True}), (money(values.get("total_amount")), {"b": True})]], height=24, size=11)
    p = para(doc, ("Faculty signature: ", {"b": True}), before=24, size=10.5)
    run(p, "_" * 60)
    para(doc, "", before=6, size=4)
    border_bottom(doc.paragraphs[-1], "dashed", 8)
    para(doc, ("FOR INTERNAL USE ONLY", {"b": True}), before=12, indent=1.3, size=10)
    t = table(doc, [1.1, 5.9, 3.3, 2.4, 1.6], indent=1.3)
    row(t, ["SN.", "Steps completed", "Name", "Signature", "Date"], bold=True, size=9.5, align=["l", "l", "c", "c", "c"])
    row(t, ["1.", "Entered in the database", "", "", ""], size=9.5)
    row(t, ["2.", "Checked", "", "", ""], size=9.5)
    row(t, ["3.", "Communicated to faculty and accounts", "", "", ""], size=9.5)
    return to_bytes(doc)


# ================================================================== C-1
def render_C1(values):
    doc = new_doc(border=True, margins=(2.4, 1.4, 1.9, 1.9))
    head_titles(doc, "ANNEXURE C - Professional Development")
    para(doc, ("Please fill out the soft copy of the form as applicable", {"b": True, "i": True}), before=14)
    para(doc, ("Instructions", {"i": True}), before=10, indent=0.6, size=8)
    para(doc, ("a)\tPlease use section 1 for obtaining Dean/Associate Dean's approval (prior to incurring the expenses)", {"i": True}), indent=1.4, hanging=0.7, size=8)
    para(doc, ("b)\tPlease use section 2 for invoice reimbursement (related to approved expenses)", {"i": True}), indent=1.4, hanging=0.7, size=8)
    para(doc, ("Section 1", {"b": True, "u": True}), align="c", before=12)
    p = para(doc, ("Faculty Name: ", {"b": True}), before=14, indent=1.0)
    filled(p, txt(values.get("faculty_name")), 48, b=True)
    run(p, "Date", b=True)
    run(p, ": ")
    filled(p, dmy(values.get("date")), 16)
    para(doc, ("I. Please select the following funding options:", {"b": True}), before=14, indent=1.0)
    f = next(x for x in FORMS["C1"]["fields"] if x["key"] == "funding")
    for k, label, r in table_rows(f, values):
        para(doc, f"{ON if r.get('selected') else OFF} {label}", before=9, indent=1.0)
        p = para(doc, "Details with estimated expenses:", indent=1.0)
        if r.get("details") not in (None, ""):
            run(p, f" {r['details']}", u=True)
        else:
            p.paragraph_format.tab_stops.add_tab_stop(Cm(16.2), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.LINES)
            run(p, "\t")
        rule(doc, sz=6, before=3, after=0)
    para(doc, ("II. Briefly describe what would be the likely outcome(s)", {"b": True}), before=12, indent=1.0)
    box(doc, txt(values.get("outcomes")), 66, 15.4, indent=1.0)
    p = para(doc, ("Faculty signature:   ", {"b": True}), before=24, indent=1.0)
    run(p, "_" * 52)
    return to_bytes(doc)


# ================================================================== C-2
C2_HEIGHTS = [65, 51, 56, 26, 51, 52, 81]
C2_LABELS = {
    "membership": "Membership in professional societies",
    "training": "Professional training seminars",
    "fdp": "Faculty development workshops",
    "online_courses": "Courses offered online",
    "software": "Software to facilitate research and learning",
    "participant_only": "Workshop or conference as a participant only",
    "others": "Any other as jointly determined by the faculty and Dean",
}


def render_C2(values):
    doc = new_doc(border=True, margins=(2.4, 1.4, 2.0, 1.9))
    para(doc, "", before=24)
    para(doc, ("Section 2", {"b": True, "u": True}), align="c", before=10)
    p = para(doc, ("Faculty Name: ", {"b": True}), before=14, indent=0.3)  # added at ORI's request: original has no name field
    filled(p, txt(values.get("faculty_name")), 48, b=True)
    para(doc, ("I.\tDetails of Actual expenses incurred", {"b": True}), before=14, indent=0.9, hanging=0.9, size=10)
    f = next(x for x in FORMS["C2"]["fields"] if x["key"] == "expenses")
    rows = [r for _, _, r in table_rows(f, values)]
    widths = [2.8, 2.2, 2.2, 2.9, 3.4, 2.7]
    para(doc, "", size=8)
    t = table(doc, widths, indent=0.3)
    row(t, [[("Categories", {"b": True})], [("Invoice details", {"b": True})], [("Date", {"b": True})],
            [("TOTAL EXPENSE", {"b": True}), ("\n(INR ₹)", {"b": True, "i": True})] if False else
            [("TOTAL EXPENSE (", {"b": True}), ("INR ₹", {"b": True, "i": True}), (")", {"b": True})],
            [("Conversion Rate ", {"b": True}), ("[USD ($),Euro (€), Pound (£) etc.]", {"b": True, "i": True})],
            [("Remarks", {"b": True})]], height=64, size=10)
    for h, ht in zip(f["heads"], C2_HEIGHTS):
        mine = [r for r in rows if r.get("category") == h["label"]]
        row(t, [C2_LABELS[h["key"]],
                "\n".join(txt(r.get("invoice")) for r in mine),
                "\n".join(dmy(r.get("dated")) for r in mine),
                "\n".join(money(r.get("total_inr")) for r in mine),
                "\n".join(txt(r.get("conversion_rate")) for r in mine),
                "\n".join(txt(r.get("remarks")) for r in mine)], height=ht, size=10)
    tot = t.add_row()
    tot.height = Pt(13)
    a = tot.cells[0].merge(tot.cells[2])
    run(a.paragraphs[0], "TOTAL", b=True, size=10)
    run(tot.cells[3].paragraphs[0], money(values.get("total_amount")), b=True, size=10)
    p = para(doc, ("Faculty signature:   ", {"b": True}), before=14, indent=0.3)
    run(p, "_" * 50)
    para(doc, ("FOR INTERNAL USE ONLY:", {"b": True}), before=14, indent=0.1, size=10)
    para(doc, "", size=5)
    t = table(doc, [1.3, 5.3, 3.3, 2.7, 1.9], indent=0.8)
    row(t, ["SN.", "Steps completed", "Name", "Signature", "Date"], bold=True, size=9.5, align=["l", "c", "c", "c", "c"])
    row(t, ["1.", "Entered in the database", "", "", ""], size=9.5)
    row(t, ["2.", "Checked", "", "", ""], size=9.5)
    row(t, ["3.", "Communicated to faculty and accounts", "", "", ""], size=9.5)
    return to_bytes(doc)


# ================================================================== D-I
def render_D1(values):
    doc = new_doc(border=False, margins=(3.0, 1.2, 1.55, 1.5))
    L = lambda s: (s, {})
    para(doc, ("ANNEXURE D – Conference Application Form (Section I)", {"b": True}), align="c", size=10)
    para(doc, (INSTITUTE, {"b": True}), align="c", size=10)
    para(doc, ("Please fill out the soft copy of the form as applicable", {"b": True, "i": True}), align="c", size=10)
    para(doc, ("Instructions", {"b": True, "i": True}), before=10, indent=0.5, size=7.5)
    para(doc, ("a)\tPlease use Annexure D – Section I for obtaining Dean/Associate Dean's approval (prior to incurring the expenses)", {"b": True, "i": True}), indent=1.2, hanging=0.7, size=7.5)
    para(doc, ("b)\tPlease use Annexure D – Section II (Expense Claim Form) for invoice reimbursement (upon approval)", {"b": True, "i": True}), indent=1.2, hanging=0.7, size=7.5)
    para(doc, "", before=30)

    def line(label, key, blank=60, fmt=txt, before=5, extra=None):
        p = para(doc, label, before=before, size=10)
        filled(p, fmt(values.get(key)), blank, size=10)
        return p

    line("Date of Application: ", "date", 27, fmt=lambda v: dmy(v))
    line("FACULTY NAME: ", "faculty_name", 72)
    line("CO- AUTHORS (if any): ", "co_authors", 70)
    line("NAME OF THE CONFERENCE: ", "conference_name", 68)
    rule(doc, sz=12, before=0, after=0)
    line("CONFERENCE ORGANIZER ", "organizer", 73, before=2)
    p = para(doc, "DATES: ", before=5, size=10)
    filled(p, txt(values.get("dates")), 36, size=10)
    run(p, "    CITY/COUNTRY: ", size=10)
    filled(p, txt(values.get("city_country")), 28, size=10)
    line("PERIOD: ", "period", 14)
    p = para(doc, "REGISTRATION FEE: ", before=5, size=10)
    filled(p, money(values.get("registration_fee")), 22, size=10)
    run(p, " PUBLICATION FEE: ", size=10)
    filled(p, money(values.get("publication_fee")), 26, size=10)
    line("TITLE OF THE ARTICLE TO BE PRESENTED: ", "article_title", 55)
    line("TARGETED JOURNAL(S) FOR PUBLICATION: ", "target_journals", 45)
    line("PROBABLE MONTH & YEAR OF SENDING THE PAPER TO THE JOURNAL: ", "journal_send_month", 17)
    cv = str(values.get("courses_in_period") or "").lower()
    para(doc, "ANY COURSES YOU MAY BE HANDLING IN THAT PERIOD (CONFERENCE DATES)  ", f"{ON if cv == 'yes' else OFF} YES  {ON if cv == 'no' else OFF} NO", before=5, size=10)
    p = para(doc, "IF YES PROVIDE/ATTACH THE DETAILS: ", before=5, size=10)
    filled(p, txt(values.get("courses_details")) if cv == "yes" else "", 60, size=10)
    para(doc, "DESCRIBE HOW YOU EXPECT TO BENFIT FROM THIS PROGRAMME:", before=5, size=10)
    line("a) BENEFIT TO FACULTY: ", "benefit_faculty", 65)
    line("b) BENEFIT TO AREA/ INSTITUTE: ", "benefit_institute", 62)
    line("PROPOSED DATE OF BROWN BAG SEMINAR: ", "brown_bag_date", 55)
    ct = values.get("contribution_type")
    opts = ["Academic Research Paper", "Practitioner Article", "Teaching Case with Analysis"]
    mk = lambda cur, o: f"{ON if cur == o else OFF} {o}"
    para(doc, ("Indicate the type of contribution", {"b": True}), ": ", mk(ct, opts[0]), "    ", mk(ct, opts[1]), before=6, size=10)
    para(doc, mk(ct, opts[2]), indent=5.2, before=3, size=10)
    rule(doc, sz=12, before=2, after=2)
    st = values.get("submission_type")
    so = ["A full paper", "An extended abstract", "A short extract (<500 words)"]
    para(doc, ("Conference acceptance submission", {"b": True}), "   ", mk(st, so[0]), "    ", mk(st, so[1]), before=2, size=10)
    para(doc, ("required :", {"b": True}), "                                                     ", mk(st, so[2]), before=3, size=10)
    doc.add_page_break()

    # ---------------- page 2
    para(doc, ("CONFERENCE PARTICIPATION BUDGET (please indicate exact/estimated costs in INR)", {"b": True}), size=10)
    para(doc, ("TRAVEL REQUISITION", {"b": True}), before=4, size=10)
    para(doc, ("TICKETS", {"b": True, "u": True}), before=4, size=10)
    tw = [2.2, 2.15, 3.0, 1.75, 1.75, 2.0, 3.5, 1.65]
    tk = [("from", "From"), ("to", "To"), ("date", "Date"), ("day", "Day"), ("mode", "Flt/Train"), ("timing", "Timing"), ("cls", "Class"), ("rem", "Rem.")]
    t = table(doc, tw)
    for field_key in ("tickets_a", "tickets_b"):
        row(t, [h for _, h in tk], bold=True, size=9.5)
        rows = values.get(field_key) or []
        for i in range(2):
            r = rows[i] if i < len(rows) else {}
            row(t, [dmy(r.get(k)) if k == "date" else txt(r.get(k)) for k, _ in tk], height=17, size=9)
    para(doc, ("HOTELS", {"b": True, "u": True}), before=8, size=10)
    hw = [2.3, 4.5, 2.8, 2.8, 3.1, 2.5]
    t = table(doc, hw)
    row(t, ["City", "Hotel/Level/Area", "Room Type", "Tariff", "From (Date)", "To (Date)"], bold=True, size=9.5)
    hot = values.get("hotels") or []
    for i in range(3):
        r = hot[i] if i < len(hot) else {}
        row(t, [txt(r.get("city")), txt(r.get("hotel")), txt(r.get("room_type")), money(r.get("tariff")),
                dmy(r.get("from_date")), dmy(r.get("to_date"))], height=21, size=9)
    para(doc, ("ESTIMATED EXPENSES (For NATIONAL / INTERNATIONAL CONFERENCE – in Rs.)", {"b": True, "u": True}), before=10, after=6, size=10)
    values = with_computed("D1", values)
    t = table(doc, [5.7, 8.0, 4.3])

    def mid(*parts):
        return [[":", "\t", *parts]]

    def est(label, middle, amount, h=18, rs=True):
        r = row(t, [label, middle if isinstance(middle, str) else "", ""], height=h, size=10)
        if not isinstance(middle, str):
            c = r.cells[1]
            p = c.paragraphs[0]
            for x in list(p.runs):
                x._r.getparent().remove(x._r)
            ts = p.paragraph_format.tab_stops
            ts.add_tab_stop(Cm(3.2), WD_TAB_ALIGNMENT.CENTER)
            ts.add_tab_stop(Cm(6.9), WD_TAB_ALIGNMENT.RIGHT)
            for part in middle:
                if isinstance(part, tuple):
                    run(p, part[0], size=10, **part[1])
                else:
                    run(p, part, size=10)
        c = r.cells[2]
        run(c.paragraphs[0], ("Rs. " if rs else "") + amount, size=10)

    g = values.get
    acc_days, acc_rate = txt(g("accommodation_days")), money(g("accommodation_rate"))
    misc_days, misc_rate = txt(g("misc_days")), money(g("misc_rate"))
    est("Fare", [":", "\tTickets"], money(g("fare_tickets")))
    est("Accommodation", [":", f"\t{acc_days} Days @ {acc_rate}", "\tpd"], money(_mul(g("accommodation_days"), g("accommodation_rate"))))
    est("Conveyance", [":"], money(g("conveyance")))
    est("Miscellaneous", [":", f"\t{misc_days} Days @ {misc_rate}", "\tpd"], money(_mul(g("misc_days"), g("misc_rate"))))
    est("Others", [":", "\tVisa / Medical Insurance"], money(g("others_visa_insurance")), h=22, rs=False)
    est("Transport to & from Airport", [":"], money(g("airport_transport")), h=22, rs=False)
    r = row(t, ["", "", ""], height=22, size=10)
    p = r.cells[0].paragraphs[0]
    run(p, "Registration Fee", size=10)
    run(p, "1", size=10, sup=True)
    run(r.cells[1].paragraphs[0], ":", size=10)
    run(r.cells[2].paragraphs[0], money(g("registration_fee")), size=10)
    mode = g("advance_mode")
    adv = [":", "\t"]
    for i, o in enumerate(["Forex", "TC", "Cash"]):
        adv.append((o, {"b": True, "u": True} if mode == o else {}))
        if i < 2:
            adv.append(" / ")
    est("Advance required", adv, money(g("advance_required")), h=22)
    est("Total Amount", "", money(g("total_amount")), h=36, rs=False)

    para(doc, ("Signature of the faculty: ", {"b": True}), before=14, size=10)
    p = para(doc, "-" * 125, indent=3.2, size=7)
    para(doc, ("Approval:", {"b": True}), size=10)
    para(doc, "", size=4)
    t = table(doc, [18.0])
    row(t, [[("Remark, if any", {"size": 9})]], height=62, size=9)
    para(doc, ("Note: A copy of each of the following must be attached to this application form:", {"b": True}), before=6, size=10)
    para(doc, "1. Acceptance letter from the conference,", indent=0.3, size=10)
    para(doc, "2. Submission made by faculty to the conference", indent=0.3, size=10)
    para(doc, "3. Conference announcement showing at least the name, dates, city and venue of the conference", indent=0.3, size=10)
    para(doc, "", before=8, size=6)
    border_bottom(doc.paragraphs[-1], "single", 4)
    para(doc, ("1", {"sup": True}), "Note: For Conference / Seminar", size=8)
    return to_bytes(doc)


def _mul(a, b):
    try:
        return float(a) * float(b)
    except (TypeError, ValueError):
        return ""


RENDERERS = {"A": render_A, "B": render_B, "C1": render_C1, "C2": render_C2, "D1": render_D1}


def render_docx(form_code, values):
    return RENDERERS[form_code](with_computed(form_code, values))
