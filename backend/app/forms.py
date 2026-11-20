"""Field definitions for the six ORI forms.

Each field has:
  key        machine name
  label      text shown to the faculty member
  type       text | longtext | date | number | yesno | checkbox | choice | table
  extract    True  -> the paper may contain this; the LLM is asked to look for it
  hint       what to look for in the paper (only used when extract=True)
  blank      True  -> never filled by the app and never asked (office use / signatures)
  required   True  -> must have a value before a file can be generated
  depends    "<table>.<row>.<col>" -> field only applies when that checkbox is ticked
  computed   "sum:<table>.<col>" -> calculated, never asked

Nothing is defaulted. If a value is not supplied by the paper (with a verbatim
quote) or typed by the user, the form cannot be generated.
"""

ANNEX_A_HEADS = [
    ("copy_editing", "Copy-editing and transcription services"),
    ("software_hardware", "Project-related specific software or hardware"),
    ("article_submission", "Article submission fee"),
    ("travel", "Project-related travel"),
    ("journal_fee", "Journal publication fee or article processing fee"),
    ("ra_stipend", "Salary/ monthly stipend of Research Assistants (RA) as per institute norms"),
    ("survey_gifts", "Compensating the respondents of surveys with token gifts"),
    ("others", "Any others (only research project-related)"),
]

ANNEX_B_HEADS = [
    ("travel", "Project-related travel"),
    ("copy_editing", "Copy-editing and transcription services"),
    ("software_hardware", "Project-related specific software or hardware"),
    ("article_submission", "Article submission fee"),
    ("journal_fee", "Journal publication fee or article processing fee"),
    ("ra_stipend", "Salary/ monthly stipend of Research Assistants (RA) as per institute norms"),
    ("survey_gifts", "Compensating the respondents of surveys with token gifts"),
    ("others", "Any other as jointly determined by the researcher and Dean"),
]

ANNEX_C_HEADS = [
    ("membership", "Membership in professional societies"),
    ("training", "Attending professional training seminars"),
    ("fdp", "Attending faculty development workshops"),
    ("online_courses", "Attending courses offered online"),
    ("software", "Purchasing software to facilitate research and learning"),
    ("participant_only", "Attending a workshop or conference as a participant only"),
    ("others", "Any other, as jointly determined by the faculty and the Dean"),
]


def _rows(heads):
    return [{"key": k, "label": l} for k, l in heads]


# --------------------------------------------------------------------------------------------
# What the AI is asked to find in uploaded documents (emails, invoices, receipts, papers ...)
# Only the columns listed under "fields" are ever pre-filled. Everything else is left for the user.
# --------------------------------------------------------------------------------------------
C1_EXTRACT = {
    "hint": ("One row for each professional-development activity or purchase the faculty member plans: a society "
             "membership, a training seminar, a faculty development workshop, an online course, software, or a "
             "workshop/conference attended as a participant only."),
    "row_hint": ("Which funding option the activity is. Decide from what the document describes (e.g. a 'workshop' "
                 "or 'FDP' = faculty development workshop; a 'Coursera/edX course' = online course). "
                 "null if it is not clear which one applies."),
    "fields": {
        "details": ("What the activity or purchase is (name, organiser/provider, place and dates if given) followed by "
                    "its estimated cost with the currency exactly as the document states it, e.g. "
                    "'Annual membership, Academy of Management, USD 125'. Do not convert or add up amounts."),
    },
}
C2_EXTRACT = {
    "hint": ("One row per invoice, receipt or payment confirmation for a professional-development expense "
             "(membership, seminar, workshop, online course, software, participant-only conference)."),
    "fields": {
        "category": "Which expense category it is (decide from what was bought). null if unclear.",
        "invoice": ("Invoice/receipt number if any, who issued it, what it was for, and the billed amount with its "
                    "original currency, e.g. 'INV-2031, Coursera, Data Science course, USD 49'."),
        "dated": "Invoice or payment date, as YYYY-MM-DD.",
        "total_inr": ("Total in Indian rupees. ONLY when the document itself states an amount in INR / Rs. / \u20b9. "
                      "If the bill is in another currency and no rupee amount is stated, null. Never convert."),
        "conversion_rate": ("The exchange rate to rupees, e.g. '1 USD = 83.2 INR', ONLY if the document states one. "
                            "Otherwise null."),
    },
}
D2_TRAVEL = {
    "hint": ("One row per ticket, fare or local transport bill (flight, train, taxi/cab, airport transfer, other)."),
    "fields": {
        "mode": "Mode of travel, e.g. Flight, Train, Taxi, Airport transfer.",
        "date": "Date of travel or of the bill, as YYYY-MM-DD.",
        "from": "Place travelled from.",
        "to": "Place travelled to.",
        "currency": "Currency of the billed amount.",
        "value": "Billed amount for this row, number only.",
    },
}
D2_ACCOMMODATION = {
    "hint": "One row per hotel/lodging bill or stay.",
    "fields": {
        "hotel": "Hotel name and its city/country.",
        "from_date": "Check-in date, as YYYY-MM-DD.",
        "to_date": "Check-out date, as YYYY-MM-DD.",
        "days": "Number of days/nights ONLY if the document states it explicitly. Copy it; do not work it out.",
        "currency": "Currency of the billed amount.",
        "value": "Total billed amount for the stay, number only.",
    },
}
D2_FOOD = {
    "hint": "One row per meal or food bill.",
    "fields": {
        "date": "Date of the bill, as YYYY-MM-DD.",
        "currency": "Currency of the billed amount.",
        "value": "Billed amount, number only.",
    },
}
D2_OTHERS = {
    "hint": "Registration fee, visa fee, travel/medical insurance, or any other conference-related expense.",
    "row_hint": ("registration = conference registration fee; visa_insurance = visa fee or travel/medical "
                 "insurance; misc = any other expense. null if unclear."),
    "fields": {
        "details": "What the expense is and who charged it.",
        "currency": "Currency of the billed amount.",
        "value": "Billed amount, number only.",
    },
}

A_EXTRACT = {
    "hint": ("Planned costs for the research project, from quotations, estimates, invoices, grant/budget notes or "
             "emails: copy-editing/transcription, software or hardware, submission fees, travel, journal "
             "publication fees, research-assistant stipend, survey gifts, other."),
    "row_hint": ("Which expense head the item belongs to. Decide from what it is (e.g. a transcription quote = "
                 "copy-editing; a SPSS/NVivo licence = software; an APC = journal fee). null if unclear."),
    "fields": {
        "details": "What the expense is and who it is from, with any currency exactly as stated.",
        "amount": ("Amount in Indian rupees, ONLY when the document itself states it in INR / Rs. / \u20b9. "
                   "Other currency and no rupee figure stated: null. Never convert or add up."),
    },
}
B_EXTRACT = {
    "hint": ("One row per invoice, receipt or payment confirmation for a research-project expense (travel, "
             "copy-editing/transcription, software/hardware, submission fee, journal fee, RA stipend, survey gifts)."),
    "fields": {
        "head": "Which expense head it falls under (decide from what was bought). null if unclear.",
        "invoice": ("Invoice/receipt number if any, who issued it and what it was for, with the billed amount in "
                    "its original currency."),
        "dated": "Invoice or payment date, as YYYY-MM-DD.",
        "amount": ("Amount in Indian rupees, ONLY when the document itself states it in INR / Rs. / \u20b9. "
                   "Otherwise null. Never convert."),
    },
}
D1_TICKETS_A = {
    "hint": ("Outward journey legs (departure towards the conference), from tickets, itineraries or booking emails."),
    "fields": {
        "from": "Departure place.", "to": "Arrival place.", "date": "Date of the leg, as YYYY-MM-DD.",
        "mode": "Flight or Train, with number if given.", "timing": "Departure time, as written.",
        "cls": "Travel class, e.g. Economy.",
    },
}
D1_TICKETS_B = {
    "hint": "Return journey legs (coming back from the conference), from tickets, itineraries or booking emails.",
    "fields": D1_TICKETS_A["fields"],
}
D1_HOTELS = {
    "hint": "Hotel stays booked or quoted, from booking confirmations or emails.",
    "fields": {
        "city": "City of the hotel.", "hotel": "Hotel name and area/level if given.", "room_type": "Room type.",
        "tariff": ("Rate per night in Indian rupees, ONLY if the document states it in INR / Rs. / \u20b9. "
                   "Otherwise null. Never convert."),
        "from_date": "Check-in date, as YYYY-MM-DD.", "to_date": "Check-out date, as YYYY-MM-DD.",
    },
}
_INR_ONLY = " Amount in Indian rupees ONLY if the document states it in INR / Rs. / \u20b9; otherwise null. Never convert or add up."


_FORM_DATE_HINT = ("The date written on the application form itself, next to 'Date' (only when the document is an "
                   "already filled-in form). Indian forms write day first: 11.04.2026 means 11 April 2026. Return "
                   "YYYY-MM-DD. null if the document is not a filled form; never use an email date, invoice date or "
                   "paper date.")


def F(key, label, type="text", **kw):
    d = {"key": key, "label": label, "type": type}
    d.update(kw)
    return d


FORMS = {
    # ------------------------------------------------------------------ A
    "A": {
        "code": "A",
        "title": "Annexure A – Research Project ID (PID) Generation",
        "purpose": "Inform a specific research project to obtain a Project ID.",
        "kind": "docx",
        "fields": [
            F("faculty_name", "Faculty name", required=True),
            F("date", "Date", "date", required=True, extract=True, hint=_FORM_DATE_HINT),
            F("pid", "PID (filled by ORI)", blank=True),
            F("project_name", "Name of the research project", required=True, extract=True,
              hint="Title of the research project / study. Use the paper title only if the paper itself describes the project."),
            F("description", "Brief description", "longtext", required=True, extract=True,
              hint="A brief description of the project, taken from the abstract/introduction."),
            F("co_researchers", "Name of the co-researcher(s) in the project", "longtext", required=True, extract=True,
              hint="Names of the co-authors/co-researchers, excluding the faculty member named in the context. If the document itself says NA / None / nil, return that as written. If it is a paper with no co-authors besides the faculty member, return null so the user can confirm 'None'."),
            F("expenses", "Estimated expenses", "table", fixed_rows=_rows(ANNEX_A_HEADS), extract_table=A_EXTRACT, columns=[
                F("selected", "Applies", "checkbox"),
                F("details", "Details of expenses under the head"),
                F("amount", "Expected amount (INR)", "number"),
            ]),
            F("objectives", "Research objectives", "longtext", extract=True, depends="expenses.travel.selected",
              hint="The research objectives / research questions of the study."),
            F("methodology", "Research methodology", "longtext", extract=True, depends="expenses.travel.selected",
              hint="Methodology: data, sample, method, as stated in the paper."),
            F("coauthor_roles", "Role of co-authors", "longtext", extract=True, depends="expenses.travel.selected",
              hint="Only if the paper explicitly states each author's role or contribution (e.g., a CRediT statement)."),
            F("travel_purpose", "Purpose of travel", "longtext", depends="expenses.travel.selected", extract=True,
              hint="Why the faculty member is travelling for the project, only if a document states it."),
            F("travel_necessity", "Necessity for the travel (e.g., cannot be substituted online or by co-authors)", "longtext",
              depends="expenses.travel.selected"),
            F("travel_hotel", "Travel expense: Hotel / Lodging (INR)", "number", depends="expenses.travel.selected", extract=True,
              hint="Hotel / lodging cost for the project trip."+_INR_ONLY),
            F("travel_tickets", "Travel expense: Tickets (INR)", "number", depends="expenses.travel.selected", extract=True,
              hint="Ticket cost for the project trip."+_INR_ONLY),
            F("travel_local", "Travel expense: Local travel (INR)", "number", depends="expenses.travel.selected", extract=True,
              hint="Local travel cost for the project trip."+_INR_ONLY),
            F("travel_misc", "Travel expense: Miscellaneous (INR)", "number", depends="expenses.travel.selected"),
            F("travel_benefit", "Benefit to the Institute", "longtext", depends="expenses.travel.selected"),
            F("total_amount", "Total amount", "number", computed="sum:expenses.amount"),
            F("q_spjimr_data", "Does your study intend to utilize the 'SPJIMR data' (primary or secondary) for analysis?", "yesno", required=True),
            F("q_ethics", "Does your study require an internal ethics review coordinated by ORI?", "yesno", required=True),
            F("q_annexure_f", "Does your study require furnishing of the Self-disclosure form (Annexure F)?", "yesno", required=True),
            F("signature", "Faculty signature", blank=True),
            F("internal_use", "For internal use only", blank=True),
        ],
    },
    # ------------------------------------------------------------------ B
    "B": {
        "code": "B",
        "title": "Annexure B – Research Project Related Expense Claim",
        "purpose": "Reimburse research project-related expenses from the Block Fund.",
        "kind": "docx",
        "fields": [
            F("faculty_name", "Faculty name", required=True),
            F("date", "Date", "date", required=True, extract=True, hint=_FORM_DATE_HINT),
            F("pid", "Project ID (PID, only one in the form)", required=True),
            F("research_title", "Research topic/title", required=True, extract=True,
              hint="Title of the research project / paper."),
            F("expenses", "Details of expenses", "table", head_column="head", heads=_rows(ANNEX_B_HEADS), extract_table=B_EXTRACT, columns=[
                F("head", "Head", "choice", options=[l for _, l in ANNEX_B_HEADS]),
                F("invoice", "Invoice details"),
                F("dated", "Dated", "date"),
                F("amount", "Amount (INR)", "number"),
                F("comment", "Comment"),
            ]),
            F("total_amount", "Total amount", "number", computed="sum:expenses.amount"),
            F("signature", "Faculty signature", blank=True),
            F("internal_use", "For internal use only", blank=True),
        ],
    },
    # ---------------------------------------------------------------- C-1
    "C1": {
        "code": "C-1",
        "title": "Annexure C – Professional Development (Section 1: Approval)",
        "purpose": "Obtain Dean/Associate Dean approval before incurring professional development expenses.",
        "kind": "docx",
        "fields": [
            F("faculty_name", "Faculty name", required=True),
            F("date", "Date", "date", required=True, extract=True, hint=_FORM_DATE_HINT),
            F("funding", "Funding options", "table", fixed_rows=_rows(ANNEX_C_HEADS), extract_table=C1_EXTRACT, columns=[
                F("selected", "Selected", "checkbox"),
                F("details", "Details with estimated expenses"),
            ]),
            F("outcomes", "Briefly describe what would be the likely outcome(s)", "longtext", required=True),
            F("signature", "Faculty signature", blank=True),
        ],
    },
    # ---------------------------------------------------------------- C-2
    "C2": {
        "code": "C-2",
        "title": "Annexure C – Professional Development (Section 2: Expense Claim)",
        "purpose": "Claim reimbursement for approved professional development expenses.",
        "kind": "docx",
        "fields": [
            F("faculty_name", "Faculty name", required=True),
            F("expenses", "Details of actual expenses incurred", "table", head_column="category", heads=_rows(ANNEX_C_HEADS), extract_table=C2_EXTRACT, columns=[
                F("category", "Category", "choice", options=[l for _, l in ANNEX_C_HEADS]),
                F("invoice", "Invoice details"),
                F("dated", "Date", "date"),
                F("total_inr", "Total expense (INR ₹)", "number"),
                F("conversion_rate", "Conversion rate (USD/Euro/Pound etc.)"),
                F("remarks", "Remarks"),
            ]),
            F("total_amount", "Total", "number", computed="sum:expenses.total_inr"),
            F("signature", "Faculty signature", blank=True),
            F("internal_use", "For internal use only", blank=True),
        ],
    },
    # ---------------------------------------------------------------- D-I
    "D1": {
        "code": "D-I",
        "title": "Annexure D – Conference Application Form (Section I)",
        "purpose": "Obtain Dean/Associate Dean approval for a conference before incurring expenses.",
        "kind": "docx",
        "fields": [
            F("date", "Date of application", "date", required=True, extract=True, hint=_FORM_DATE_HINT),
            F("faculty_name", "Faculty name", required=True),
            F("co_authors", "Co-authors (if any)", "longtext", required=True, extract=True,
              hint="Co-authors of the paper, excluding the faculty member named in the context. If none besides the faculty member, return null."),
            F("conference_name", "Name of the conference", required=True, extract=True,
              hint="Full name of the conference / event."),
            F("organizer", "Conference organizer", required=True, extract=True,
              hint="Who organises or hosts the conference (society, university, association)."),
            F("dates", "Dates", required=True, extract=True,
              hint="Conference dates as written, e.g. 12 to 14 March 2027."),
            F("city_country", "City / Country", required=True, extract=True,
              hint="City and country where the conference is held."),
            F("period", "Period", required=True),
            F("registration_fee", "Registration fee (INR)", "number", required=True, extract=True,
              hint="Registration fee."+_INR_ONLY),
            F("publication_fee", "Publication fee (INR)", "number", required=True, extract=True,
              hint="Publication fee for the conference proceedings or journal, only if stated."+_INR_ONLY),
            F("article_title", "Title of the article to be presented", required=True, extract=True,
              hint="Title of the paper."),
            F("target_journals", "Targeted journal(s) for publication", "longtext", required=True, extract=True,
              hint="Only if the paper itself names a target journal (e.g., a note such as 'to be submitted to ...')."),
            F("journal_send_month", "Probable month & year of sending the paper to the journal", required=True),
            F("courses_in_period", "Any courses you may be handling in that period (conference dates)", "yesno", required=True),
            F("courses_details", "If yes, provide the details", "longtext", depends="courses_in_period=yes"),
            F("benefit_faculty", "Benefit to faculty", "longtext", required=True),
            F("benefit_institute", "Benefit to area / institute", "longtext", required=True),
            F("brown_bag_date", "Proposed date of brown bag seminar", required=True),
            F("contribution_type", "Type of contribution", "choice", required=True,
              options=["Academic Research Paper", "Practitioner Article", "Teaching Case with Analysis"], extract=True,
              hint="Which kind of contribution it is, only if the document says (e.g. an accepted research paper, a practitioner article, a teaching case)."),
            F("submission_type", "Conference acceptance submission required", "choice", required=True,
              options=["A full paper", "An extended abstract", "A short extract (<500 words)"], extract=True,
              hint="What was submitted for acceptance (full paper, extended abstract, short extract), only if stated."),
            F("tickets_a", "Travel requisition – tickets (first table)", "table", extract_table=D1_TICKETS_A, max_rows=2, columns=[
                F("from", "From"), F("to", "To"), F("date", "Date", "date"), F("day", "Day"),
                F("mode", "Flt/Train"), F("timing", "Timing"), F("cls", "Class"), F("rem", "Rem."),
            ]),
            F("tickets_b", "Travel requisition – tickets (second table)", "table", extract_table=D1_TICKETS_B, max_rows=2, columns=[
                F("from", "From"), F("to", "To"), F("date", "Date", "date"), F("day", "Day"),
                F("mode", "Flt/Train"), F("timing", "Timing"), F("cls", "Class"), F("rem", "Rem."),
            ]),
            F("hotels", "Hotels", "table", extract_table=D1_HOTELS, max_rows=3, columns=[
                F("city", "City"), F("hotel", "Hotel/Level/Area"), F("room_type", "Room type"),
                F("tariff", "Tariff", "number"), F("from_date", "From (date)", "date"), F("to_date", "To (date)", "date"),
            ]),
            F("fare_tickets", "Fare: tickets (INR)", "number", required=True, extract=True,
              hint="Total ticket fare."+_INR_ONLY),
            F("accommodation_days", "Accommodation: number of days", "number", required=True),
            F("accommodation_rate", "Accommodation: rate per day (INR)", "number", required=True),
            F("conveyance", "Conveyance (INR)", "number", required=True),
            F("misc_days", "Miscellaneous: number of days", "number", required=True),
            F("misc_rate", "Miscellaneous: rate per day (INR)", "number", required=True),
            F("others_visa_insurance", "Others: visa / medical insurance (INR)", "number", required=True, extract=True,
              hint="Visa and/or medical insurance cost."+_INR_ONLY),
            F("airport_transport", "Transport to & from airport (INR)", "number", required=True, extract=True,
              hint="Transport to and from the airport."+_INR_ONLY),
            F("advance_required", "Advance required (INR)", "number", required=True),
            F("advance_mode", "Advance in the form of", "choice", required=True, options=["Forex", "TC", "Cash"]),
            F("total_amount", "Total amount", "number", computed="d1_total"),
            F("signature", "Signature of the faculty", blank=True),
            F("approval", "Approval and approver's remark box", blank=True),
        ],
    },
    # --------------------------------------------------------------- D-II
    "D2": {
        "code": "D-II",
        "title": "Annexure D – Conference Application Form (Section II): Expense Claim",
        "purpose": "Claim reimbursement of conference invoices after approval.",
        "kind": "xlsx",
        "fields": [
            F("name", "Name", required=True),
            F("event_date", "Date of conference / event", required=True, extract=True,
              hint="The date or dates of the conference/event, as written in the document, e.g. '12-14 March 2026'."),
            F("purpose", "Purpose", required=True, extract=True,
              hint="Why the applicant is travelling: the name of the conference/event and what the applicant does there (e.g. presents a paper), in a short phrase."),
            F("location", "Location", required=True, extract=True,
              hint="City and country where the conference/event takes place."),
            F("scope", "International or domestic", "choice", required=True, options=["INTERNATIONAL", "DOMESTIC"], extract=True,
              hint="DOMESTIC if the event is in India, INTERNATIONAL if it is outside India. Only when the location is clear from the document."),
            F("travel", "1. Travel details (incl. local transport, airport transfers, flight [economy only] / train / other)", "table",
              max_rows=5, extract_table=D2_TRAVEL, columns=[
                F("mode", "Mode of travel"), F("date", "Date", "date"), F("from", "From location"), F("to", "To location"),
                F("bill", "Bill attached", "choice", options=["Yes", "No"]),
                F("currency", "Currency", "choice", options=["INR", "USD", "EURO", "GBP", "AED", "Other"]),
                F("value", "Value", "number"),
            ]),
            F("accommodation", "2. Accommodation", "table", max_rows=3, extract_table=D2_ACCOMMODATION, columns=[
                F("hotel", "Hotel name and location"), F("from_date", "From date", "date"), F("to_date", "To date", "date"),
                F("days", "No. of days", "number"),
                F("bill", "Bill attached", "choice", options=["Yes", "No"]),
                F("currency", "Currency", "choice", options=["INR", "USD", "EURO", "GBP", "AED", "Other"]),
                F("value", "Value", "number"),
            ]),
            F("food", "3. Food", "table", max_rows=5, extract_table=D2_FOOD, columns=[
                F("date", "Date", "date"),
                F("bill", "Bill attached", "choice", options=["Yes", "No"]),
                F("currency", "Currency", "choice", options=["INR", "USD", "EURO", "GBP", "AED", "Other"]),
                F("value", "Value", "number"),
            ]),
            F("others", "4. Others", "table", fixed_rows=[
                {"key": "registration", "label": "Registration"},
                {"key": "visa_insurance", "label": "Visa, Insurance"},
                {"key": "misc", "label": "Misc"},
            ], extract_table=D2_OTHERS, columns=[
                F("details", "Details"),
                F("bill", "Bill attached", "choice", options=["Yes", "No"]),
                F("currency", "Currency", "choice", options=["INR", "USD", "EURO", "GBP", "AED", "Other"]),
                F("value", "Value", "number"),
            ]),
            F("advance_inr", "Less: advance taken (INR)", "number"),
            F("advance_usd", "Less: advance taken (USD)", "number"),
            F("advance_eur", "Less: advance taken (EURO)", "number"),
            F("eligible", "Eligible (office use)", blank=True),
        ],
    },
}


# --------------------------------------------------------------------------------------------
# Per-form wording for the upload step, and whether the form can read documents at all
# --------------------------------------------------------------------------------------------
_PAPER_CONTEXT = ("The documents are usually research papers, but may also be CVs, project notes or emails. "
                  "Facts such as the title, authors and methodology are often described in running text.")
_CONTEXT = {
    "A": ("The documents may be research papers, proposals, CVs, emails, or quotations/estimates for project costs. "
          "Titles, collaborators and costs are often described in running text."),
    "B": ("The documents are likely invoices, receipts, payment confirmations or emails for research-project "
          "expenses. Amounts, dates and invoice numbers may sit in tables, headers/footers or sentences."),
    "D1": ("The documents may be a conference invitation or acceptance email, the paper/abstract, flight or train "
           "bookings, and hotel confirmations. Conference name, organiser, dates and fees are usually inside "
           "sentences."),
    "C1": ("The documents are likely emails, invitations, brochures, quotations or web pages about a "
           "professional-development activity (membership, seminar, workshop, course, software, conference "
           "attended as a participant). Details such as fees and dates are usually written inside sentences."),
    "C2": ("The documents are likely invoices, receipts, payment confirmations or emails confirming a "
           "professional-development expense. Amounts, dates and invoice numbers may sit in tables, "
           "headers/footers or sentences."),
    "D2": ("The documents are likely conference emails/invitations, flight or train tickets, hotel bills, "
           "taxi or meal receipts, registration receipts and visa/insurance bills for one conference trip. "
           "Event details are usually written inside sentences; bills carry amounts and dates in tables."),
}
_UPLOAD_HELP = {
    "A": "Upload your paper or proposal, plus any quotations or emails about project costs (PDF, Word, text, saved email, or image).",
    "B": "Upload invoices, receipts or confirmation emails for the project expenses (PDF, Word, text, saved email, or image of the bill).",
    "D1": "Upload the conference email or invitation, your paper or abstract, and any ticket or hotel bookings (PDF, Word, text, saved email, or image).",
    "C1": "Upload emails, brochures, invitations or quotations about the activity (PDF, Word, text, saved email, or image).",
    "C2": "Upload invoices, receipts or confirmation emails for the expenses (PDF, Word, text, saved email, or image of the bill).",
    "D2": "Upload the conference email or invitation and your invoices: tickets, hotel bills, receipts (PDF, Word, text, saved email, or image).",
}
for _form in FORMS.values():
    for _f in _form["fields"]:
        if _f.get("hint") and "INR / Rs." in _f["hint"]:
            _f["inr_only"] = True
        for _c in _f.get("columns", []):
            if "Indian rupees" in (_f.get("extract_table") or {}).get("fields", {}).get(_c["key"], ""):
                _c["inr_only"] = True
for _code, _form in FORMS.items():
    _form["can_extract"] = any(f.get("extract") or f.get("extract_table") for f in _form["fields"])
    _form["extract_context"] = _CONTEXT.get(_code, _PAPER_CONTEXT)
    _form["upload_help"] = _UPLOAD_HELP.get(_code, "Upload your research paper, CV or other supporting document (PDF, Word, text, saved email, or scanned image).")
