"""Contextual reading + verification for C-1, C-2 and D-II (AI replies are stubbed)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ["ORI_DATA_DIR"] = tempfile.mkdtemp()
os.environ.pop("GEMINI_API_KEY", None)
from app import extract as X
from app.forms import FORMS
from app.logic import missing_fields
from app.render import render
X.time.sleep = lambda s: None

CAT_ONLINE = "Attending courses offered online"
ALL = {"funding": [], "expenses": []}

# ---------------------------------------------------------------- C-1: facts live inside sentences
EMAIL = """Subject: Invitation: Faculty Development Programme on Case Teaching
Dear Dr. Rao,
We are pleased to invite you to our three-day Faculty Development Programme on Case Teaching, to be held at IIM Indore from 12 to 14 January 2027. The programme fee is Rs. 15,000/- per participant, inclusive of GST. Accommodation can be arranged on campus at Rs. 2,500 per night.
Regards, Prof. Mehta"""
reply = {"fields": {}, "tables": {"funding": [
    {"row": "fdp", "details": "Faculty Development Programme on Case Teaching, IIM Indore, 12 to 14 January 2027, fee Rs. 15,000/-",
     "quotes": ["Faculty Development Programme on Case Teaching, to be held at IIM Indore from 12 to 14 January 2027",
                "The programme fee is Rs. 15,000/- per participant"], "inferred": True},
    {"row": "training", "details": "Invented seminar", "quotes": ["this sentence is not in the document"]},          # fake quote
    {"row": "software", "details": "Licence Rs. 50,000", "quotes": ["The programme fee is Rs. 15,000/- per participant"]},  # invented amount
    {"row": "not-a-row", "details": "x", "quotes": ["The programme fee is Rs. 15,000/- per participant"]},          # bad row key
]}}
r = X.extract_documents("C1", [("invite.eml", EMAIL)], "Asha Rao", generate=lambda p, m: json.dumps(reply))
assert set(r["values"]["funding"]) == {"fdp"}, r["values"]
assert r["values"]["funding"]["fdp"]["selected"] is True and "15,000" in r["values"]["funding"]["fdp"]["details"]
src = r["sources"]["funding"]["rows"]
assert len(src) == 1 and src[0]["inferred"] is True and src[0]["doc"] == "invite.eml" and len(src[0]["quotes"]) == 2
assert "outcomes" not in r["values"]          # not read from documents: it is the faculty member's own statement
print("C1 OK")

# ---------------------------------------------------------------- C-2: invoices, no conversion, no invented numbers
INV1 = """COURSERA INC.   Invoice No: CI-77231   Date: 03 November 2026
Billed to: Asha Rao
Item: Data Science Specialization (annual)     Amount: USD 49.00
Total paid: USD 49.00"""
INV2 = """SPJ Software Pvt Ltd - Tax Invoice SW/2026/118 dated 5 November 2026
NVivo licence (1 year)   Total: ₹ 12,500.00"""
q1 = ["COURSERA INC.   Invoice No: CI-77231   Date: 03 November 2026", "Total paid: USD 49.00"]
q2 = ["Tax Invoice SW/2026/118 dated 5 November 2026", "NVivo licence (1 year)   Total: ₹ 12,500.00"]
def c2_reply(prompt, model):
    if "coursera.pdf" in prompt:
        return json.dumps({"tables": {"expenses": [
            {"category": CAT_ONLINE, "invoice": "CI-77231, Coursera Inc., Data Science Specialization, USD 49.00",
             "dated": "2026-11-03", "total_inr": 4100, "conversion_rate": None, "quotes": q1, "inferred": True},   # 4100 = converted by the model
            {"category": CAT_ONLINE, "invoice": "CI-77231 again", "dated": "2026-12-03", "quotes": q1},                # wrong month: date rejected
        ]}})
    return json.dumps({"tables": {"expenses": [
        {"category": "Purchasing software", "invoice": "SW/2026/118, SPJ Software Pvt Ltd, NVivo licence",
         "dated": "2026-11-05", "total_inr": "12,500.00", "quotes": q2}]}})        # category not an exact option
r = X.extract_documents("C2", [("coursera.pdf", INV1), ("software.pdf", INV2)], "Asha Rao", generate=c2_reply)
rows = r["values"]["expenses"]
assert len(rows) == 3, rows
assert rows[0] == {"category": CAT_ONLINE, "invoice": "CI-77231, Coursera Inc., Data Science Specialization, USD 49.00", "dated": "2026-11-03"}, rows[0]   # no total_inr: never converted
assert "dated" not in rows[1] and "category" not in rows[2] and rows[2]["total_inr"] == 12500 and rows[2]["dated"] == "2026-11-05", rows
assert [x["doc"] for x in r["sources"]["expenses"]["rows"]] == ["coursera.pdf", "coursera.pdf", "software.pdf"]
print("C2 OK")

# ---------------------------------------------------------------- D-II: event facts from prose + bills from several files
CONF = """Dear Dr. Rao, I am delighted to confirm that your paper has been accepted for presentation at the International Conference on Marketing Analytics (ICMA 2027), which will be held at the Marina Bay Convention Centre, Singapore, from 12 to 14 March 2027. The registration fee is SGD 450."""
HOTEL = "Hotel Lion City, 22 Bay Road, Singapore. Check-in: 11 March 2027  Check-out: 15 March 2027. 4 nights. Total SGD 1,240.00"
FLIGHT = "IndiGo 6E-1021 Mumbai (BOM) to Singapore (SIN) 11 Mar 2027  Economy  Fare INR 38,500"
def d2_reply(prompt, model):
    if "conference.eml" in prompt:
        return json.dumps({"fields": {
            "event_date": {"value": "12 to 14 March 2027", "quotes": ["from 12 to 14 March 2027"]},
            "purpose": {"value": "Presenting an accepted paper at ICMA 2027", "quotes": ["your paper has been accepted for presentation at the International Conference on Marketing Analytics (ICMA 2027)"], "inferred": True},
            "location": {"value": "Singapore", "quotes": ["held at the Marina Bay Convention Centre, Singapore"]},
            "scope": {"value": "INTERNATIONAL", "quotes": ["held at the Marina Bay Convention Centre, Singapore"], "inferred": True}},
            "tables": {"others": [{"row": "registration", "details": "ICMA 2027 registration fee", "currency": "SGD", "value": 450,
                                   "quotes": ["The registration fee is SGD 450."]}]}})
    if "hotel.pdf" in prompt:
        return json.dumps({"tables": {"accommodation": [{"hotel": "Hotel Lion City, Singapore", "from_date": "2027-03-11", "to_date": "2027-03-15",
                           "days": 4, "currency": "SGD", "value": 1240, "quotes": [HOTEL]}]}})
    return json.dumps({"fields": {"location": {"value": "Mumbai", "quotes": ["Mumbai (BOM) to Singapore (SIN)"]}},      # disagrees with the email
                       "tables": {"travel": [{"mode": "Flight", "date": "2027-03-11", "from": "Mumbai", "to": "Singapore",
                                              "currency": "INR", "value": 38500, "quotes": [FLIGHT]}] +
                                   [{"mode": "Taxi", "date": "2027-03-11", "from": "A", "to": "B", "currency": "INR", "value": 38500, "quotes": [FLIGHT]}] * 0}})
status = []
r = X.extract_documents("D2", [("conference.eml", CONF), ("hotel.pdf", HOTEL), ("ticket.pdf", FLIGHT)], "Asha Rao",
                        generate=d2_reply, on_status=status.append)
v = r["values"]
assert v["event_date"] == "12 to 14 March 2027" and v["location"] == "Singapore" and v["scope"] == "INTERNATIONAL", v
assert r["sources"]["scope"]["inferred"] is True and r["sources"]["event_date"].get("inferred") is False
assert v["accommodation"] == [{"hotel": "Hotel Lion City, Singapore", "from_date": "2027-03-11", "to_date": "2027-03-15", "days": 4, "currency": "Other", "value": 1240}]
assert v["travel"] == [{"mode": "Flight", "date": "2027-03-11", "from": "Mumbai", "to": "Singapore", "currency": "INR", "value": 38500}]
assert v["others"]["registration"] == {"details": "ICMA 2027 registration fee", "currency": "Other", "value": 450}
assert "bill" not in v["travel"][0] and "food" not in v          # 'Bill attached' is never pre-filled; no food bills uploaded
assert any("different value" in n for n in r["notes"]), r["notes"]  # the ticket disagreed about the location
assert len([s for s in status if s.startswith("Reading document")]) == 3
# filling the rest by hand makes the claim complete and the Excel file renders
v.update(name="Asha Rao", purpose=v["purpose"])
assert not missing_fields("D2", v), missing_fields("D2", v)
blob, ext = render("D2", v); assert ext == "xlsx" and len(blob) > 5000
print("D2 OK")

# ---------------------------------------------------------------- one bad file must not lose the others; all bad -> clear error
def flaky(prompt, model):
    if "bad.pdf" in prompt: raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDay (RPD)")
    return d2_reply(prompt, model)
r = X.extract_documents("D2", [("conference.eml", CONF), ("bad.pdf", "some text")], "Asha Rao", generate=flaky)
assert r["values"]["location"] == "Singapore" and any("bad.pdf could not be read" in n for n in r["notes"]), r["notes"]
try: X.extract_documents("D2", [("bad.pdf", "some text")], "Asha Rao", generate=flaky); raise SystemExit("should fail")
except X.ExtractionError as e: assert "daily request limit" in str(e)
print("partial failure OK")

# ---------------------------------------------------------------- row caps, bad JSON retry, long documents
LINES = [f"Taxi ride {i} Mumbai to Pune 11 Mar 2027 INR {1000+i}" for i in range(7)]
many = lambda p, m: json.dumps({"tables": {"travel": [
    {"mode": "Taxi", "date": "2027-03-11", "from": "Mumbai", "to": "Pune", "currency": "INR", "value": 1000 + i, "quotes": [LINES[i]]} for i in range(7)]}})
r = X.extract_documents("D2", [("taxis.pdf", "\n".join(LINES))], "Asha Rao", generate=many)
assert len(r["values"]["travel"]) == 5 and any("2 more item(s)" in n for n in r["notes"]), (r["values"], r["notes"])
calls = []
def bad_then_good(p, m):
    calls.append(1)
    return "Sorry, here you go: {\"fields\": {" if len(calls) == 1 else d2_reply("conference.eml", m)
r = X.extract_documents("D2", [("conference.eml", CONF)], "Asha Rao", generate=bad_then_good)
assert len(calls) == 2 and r["values"]["location"] == "Singapore"
long_doc = ("Lorem ipsum dolor sit amet. " * 900) + "\n\nThe registration fee is USD 300 and the venue is Lisbon.\n\n" + ("Dolor sit amet. " * 200)
cut, was_cut = X.select_text(long_doc, 6000)
assert was_cut and "registration fee is USD 300" in cut and len(cut) <= 6000
print("caps / retry / long documents OK")

# ---------------------------------------------------------------- helpers that guard against invented facts
assert X._date_in("2027-03-12", "from 12 to 14 March 2027") and not X._date_in("2027-04-12", "from 12 to 14 March 2027")
assert X._date_in("2026-11-05", "dated 5/11/2026") and not X._date_in("2026-02-30", "30 Feb 2026")
assert X.numbers_in("Rs. 15,000/- and USD 49.00") == {15000.0, 49.0}
assert X._norm_choice({"key": "currency", "options": ["INR", "USD", "EURO", "GBP", "AED", "Other"]}, "EUR") == "EURO"
assert X._norm_choice({"key": "currency", "options": ["INR", "USD", "EURO", "GBP", "AED", "Other"]}, "$") is None   # ambiguous symbol: left blank
print("helpers OK")

# ---------------------------------------------------------------- B, D-I and A now read documents too
INV = "Tax Invoice RT/55 dated 7 October 2026. Transcription of 12 interviews, Rs. 18,000. Issued by Verbatim Services."
r = X.extract_documents("B", [("inv.pdf", INV)], "Asha Rao", generate=lambda p, m: json.dumps({"tables": {"expenses": [
    {"head": "Copy-editing and transcription services", "invoice": "RT/55, Verbatim Services, transcription of 12 interviews",
     "dated": "2026-10-07", "amount": 18000, "quotes": [INV]}]}}))
assert r["values"]["expenses"] == [{"head": "Copy-editing and transcription services", "invoice": "RT/55, Verbatim Services, transcription of 12 interviews", "dated": "2026-10-07", "amount": 18000}], r["values"]
MAIL = ("Dear Asha, your abstract is accepted for oral presentation at the Global Marketing Conference 2027, organised by the "
        "Academy of Marketing Science, to be held in Lisbon, Portugal on 9-11 July 2027. Registration fee: EUR 400.")
DQ = ["organised by the Academy of Marketing Science", "to be held in Lisbon, Portugal on 9-11 July 2027", "Registration fee: EUR 400"]
r = X.extract_documents("D1", [("accept.eml", MAIL)], "Asha Rao", generate=lambda p, m: json.dumps({"fields": {
    "conference_name": {"value": "Global Marketing Conference 2027", "quotes": ["Global Marketing Conference 2027"]},
    "organizer": {"value": "Academy of Marketing Science", "quotes": [DQ[0]]},
    "dates": {"value": "9-11 July 2027", "quotes": [DQ[1]]},
    "city_country": {"value": "Lisbon, Portugal", "quotes": [DQ[1]]},
    "registration_fee": {"value": 400, "quotes": [DQ[2]]},                      # EUR amount: must be rejected for the INR field
    "submission_type": {"value": "An extended abstract", "quotes": ["your abstract is accepted"], "inferred": True}}}))
v = r["values"]
assert v["conference_name"] == "Global Marketing Conference 2027" and v["organizer"] == "Academy of Marketing Science" and v["city_country"] == "Lisbon, Portugal", v
assert v["submission_type"] == "An extended abstract" and r["sources"]["submission_type"]["inferred"] is True
assert "registration_fee" not in v, v
print("B / D1 OK")

# ---------------------------------------------------------------- the date written on a filled-in form (e.g. "Date: __11.04.2026__")
FORM_A = "Faculty Name: _XXXXXXX_ Date: __11.04.2026__\nName of the research project: Growth stories of a transport provider"
r = X.extract_documents("A", [("a.pdf", FORM_A)], "Asha Rao", generate=lambda p, m: json.dumps(
    {"fields": {"date": {"value": "2026-04-11", "quotes": ["Date: __11.04.2026__"]}}}))
assert r["values"]["date"] == "2026-04-11" and r["sources"]["date"]["inferred"] is True   # day/month order must be confirmed
r = X.extract_documents("A", [("a.pdf", "Date: 25.04.2026")], "Asha Rao", generate=lambda p, m: json.dumps(
    {"fields": {"date": {"value": "2026-04-25", "quotes": ["Date: 25.04.2026"]}}}))
assert r["sources"]["date"]["inferred"] is False
r = X.extract_documents("A", [("a.pdf", "Date: 11.04.2026")], "Asha Rao", generate=lambda p, m: json.dumps(
    {"fields": {"date": {"value": "2026-07-11", "quotes": ["Date: 11.04.2026"]}}}))
assert "date" not in r["values"]                                                         # wrong month: rejected
print("form date OK")
