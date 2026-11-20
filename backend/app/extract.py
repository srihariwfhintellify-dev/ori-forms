"""Read uploaded documents with an AI model and pre-fill form fields, without guessing.

The model is asked to READ for meaning (facts are usually inside sentences, paragraphs and tables, not
next to a "Label:" heading). What it returns is then CHECKED IN CODE, so a wrong or invented value
cannot slip through just because the model sounded sure:

  * every value / table row must come with 1-3 quotes copied from the document;
    if any quote cannot be found in the document, the value is thrown away;
  * every number and date the model returns must itself appear inside those quotes;
  * choice answers must be one of the form's real options;
  * values the model had to interpret (e.g. picking a category) are flagged "inferred" so the faculty
    member is asked to confirm them;
  * anything thrown away is simply left blank, so the faculty member is asked for it.

Each uploaded document is read separately (one request each), so a long list of invoices is never cut
off, and results are merged afterwards.
"""
import collections
import datetime
import json
import os
import re
import threading
import time

from .forms import FORMS
from .textutil import normalise_loose

# ----------------------------------------------------------------------------- provider settings
# Confirm the model name with SPJIMR IT when the API key is confirmed.
PROVIDER = os.environ.get("EXTRACT_PROVIDER", "gemini").strip().lower()  # "gemini", "groq" or "huggingface"
LABEL = {"huggingface": "Hugging Face", "groq": "Groq"}.get(PROVIDER, "Gemini")
HF_URL = os.environ.get("HF_BASE_URL", "https://router.huggingface.co/v1") + "/chat/completions"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
# Used when the main model times out or its daily quota is used up. Quotas are counted per model,
# so a second model gives a separate allowance. Set to "" to disable.
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "")  # off by default; set to a model your key can use
if PROVIDER == "huggingface":  # no default model: pick one your token can use (GET /v1/models lists them)
    MODEL = os.environ.get("HF_MODEL", "")
    FALLBACK_MODEL = os.environ.get("HF_FALLBACK_MODEL", "")
MAX_CHARS = 40_000
MAX_OUTPUT_TOKENS = 4000
GROQ_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1") + "/chat/completions"
GROQ_TPM = int(os.environ.get("GROQ_TPM", "7000"))  # stay a little under the free plan's 8,000 tokens/minute
if PROVIDER == "groq":
    MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "")
    # Groq's free plan caps tokens per minute (8,000 for the openai/gpt-oss models), counting the prompt plus the
    # reply. ~12,000 characters of document (~3,000 tokens) + the instructions + a 3,000-token reply budget
    # (which includes the model's own reasoning) stays under it. Raise GROQ_MAX_CHARS only on a paid plan.
    MAX_CHARS = int(os.environ.get("GROQ_MAX_CHARS", "12000"))
    MAX_OUTPUT_TOKENS = 3000

_ctx = threading.local()  # per-request override of the reasoning effort
_usage = collections.deque()  # (time, tokens) of recent Groq calls, used to stay under the per-minute cap


def configured():
    """(ok, message) so the API can tell the user what is missing before reading anything."""
    if PROVIDER == "huggingface":
        if not os.environ.get("HF_TOKEN"):
            return False, "The server has no HF_TOKEN configured, so documents cannot be read yet. You can still fill the form by hand."
        if not MODEL:
            return False, "The server has no HF_MODEL configured, so documents cannot be read yet. You can still fill the form by hand."
        return True, ""
    if PROVIDER == "groq":
        if not os.environ.get("GROQ_API_KEY"):
            return False, "The server has no GROQ_API_KEY configured, so documents cannot be read yet. You can still fill the form by hand."
        return True, ""
    if not os.environ.get("GEMINI_API_KEY"):
        return False, "The server has no GEMINI_API_KEY configured, so documents cannot be read yet. You can still fill the form by hand."
    return True, ""


# ----------------------------------------------------------------------------- the instructions
SYSTEM = (
    "You read documents (emails, invitations, invoices, receipts, tickets, brochures, letters, research papers, "
    "CVs) to help a faculty member pre-fill an official form. Work like a careful human assistant.\n\n"
    "HOW TO READ\n"
    "1. Read the whole document before answering. The facts you need are usually inside sentences, paragraphs, "
    "tables, subject lines, headers/footers and signatures, NOT next to a heading such as \"Date:\". Combine clues "
    "from different parts of the same document (for example a subject line plus a sentence in the third paragraph).\n"
    "2. Interpret what the text means. Recognise dates written in any style (12/03/2026, 12th March, 12-14 Mar), "
    "amounts written in any style (Rs. 15,000/-, INR 15000, USD 49.00, EUR 1.200), names inside email signatures, "
    "and phrases such as 'per night' or 'economy return'. Convert dates to YYYY-MM-DD only when asked. If a numeric "
    "date such as 03/04/2026 could be read two ways and nothing in the document settles it, return null.\n"
    "3. You may choose among the form's listed options when the document clearly shows which one applies; then set "
    "\"inferred\": true. If two options fit, or it is unclear, return null for that option.\n"
    "4. Never use outside knowledge and never guess. Never calculate: do not add up amounts, convert currencies, or "
    "work out nights or days; copy only what the document states. If the document does not say it, or two passages "
    "contradict each other, return null.\n"
    "5. Evidence is mandatory. For every value or row give \"quotes\": 1 to 3 short passages (max 300 characters each) "
    "copied character-for-character from the document that support it. Every number and date you return MUST appear "
    "inside those quotes. Quote the sentences you relied on even when your value is a paraphrase.\n"
    "6. A table gets one row for each distinct item (each invoice, each ticket, each hotel bill...). Use an empty "
    "list if there is none.\n"
    "7. The text may come from OCR and contain recognition mistakes. Still copy quotes exactly as they appear.\n"
    "Reply with a single JSON object and nothing else."
)

# paragraphs worth keeping when a long document has to be cut to fit the AI service's size limit
_KEEP = re.compile(r"(?i)\b(method|objective|aim|purpose|research question|sample|dataset|journal|submit|conference|"
                   r"invoice|receipt|total|amount|payable|fee|registration|hotel|flight|train|check-?in|check-?out|"
                   r"venue|date|inr|usd|eur|gbp|rs\.?)\b|₹")


def extractable_fields(form_code):
    return [f for f in FORMS[form_code]["fields"] if f.get("extract")]


def extractable_tables(form_code):
    return [f for f in FORMS[form_code]["fields"] if f.get("extract_table")]


def select_text(text, limit):
    """Whole text if it fits; otherwise the start (title, abstract, headings) plus the later paragraphs that
    mention the things forms ask about. Returns (text_to_send, was_cut)."""
    if len(text) <= limit:
        return text, False
    head_n = int(limit * 0.6)
    head, rest = text[:head_n], text[head_n:]
    budget, used, picked = limit - head_n - 20, 0, []
    for para in re.split(r"\n\s*\n|\n(?=[A-Z0-9₹])", rest):
        p = para.strip()
        if p and _KEEP.search(p) and used + len(p) + 1 <= budget:
            picked.append(p)
            used += len(p) + 1
    return (head + ("\n[...]\n" + "\n".join(picked) if picked else ""))[:limit], True


def _type_note(col):
    t = col.get("type", "text")
    if t == "date":
        return "date as YYYY-MM-DD"
    if t == "number":
        return "number only (digits and decimal point; no currency symbol, no thousands separators)"
    if t == "choice":
        return "exactly one of: " + ", ".join(col.get("options", []))
    return "text"


def _build_prompt(form_code, doc_name, text, faculty_name, max_chars=None):
    form = FORMS[form_code]
    max_chars = max_chars or MAX_CHARS
    body, _ = select_text(text, max_chars)
    out = [f"Form being filled: {form['title']}.", form.get("extract_context", ""),
           f'The applicant (faculty member) is "{faculty_name}".', ""]
    scal = extractable_fields(form_code)
    if scal:
        out.append("SINGLE VALUES (key: label, how to give it, what to look for):")
        for f in scal:
            out.append(f'- "{f["key"]}": {f["label"]} [{_type_note(f)}]. {f.get("hint", "")}')
        out.append("")
    tabs = extractable_tables(form_code)
    if tabs:
        out.append("TABLES (a list of rows; [] if none):")
        for t in tabs:
            spec = t["extract_table"]
            out.append(f'- "{t["key"]}": {t["label"]}. {spec.get("hint", "")}')
            if t.get("fixed_rows"):
                opts = "; ".join(f'"{r["key"]}" = {r["label"]}' for r in t["fixed_rows"])
                out.append(f'    "row" (which line of the form; one of {opts}). {spec.get("row_hint", "")}')
            cols = {c["key"]: c for c in t["columns"]}
            for ck, hint in spec["fields"].items():
                out.append(f'    "{ck}" [{_type_note(cols[ck])}]: {hint}')
        out.append("")
    out.append('Reply with ONLY this JSON (include only the keys listed above; use null for anything not clearly in '
               'the document):\n{"fields": {"<key>": null or {"value": ..., "quotes": ["..."], "inferred": false}},\n'
               ' "tables": {"<key>": [{"row": "<only for tables with a row key>", "<column>": value or null, ..., '
               '"quotes": ["..."], "inferred": false}]}}')
    out.append(f'\n<document name="{doc_name}">\n{body}\n</document>')
    return "\n".join(out)


# ----------------------------------------------------------------------------- calling the model
def _default_client():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options={"timeout": 120000})


def _generate(client, prompt, model=None):
    from google.genai import types
    model = model or MODEL
    cfg_kwargs = dict(system_instruction=SYSTEM, temperature=0, response_mime_type="application/json",
                      max_output_tokens=MAX_OUTPUT_TOKENS)
    if hasattr(types, "ThinkingConfig"):
        if "2.5" in model and "flash" in model and "pro" not in model:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)  # no hidden reasoning time
        elif hasattr(types, "ThinkingLevel") and "2.5" not in model:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    resp = client.models.generate_content(model=model, contents=prompt,
                                          config=types.GenerateContentConfig(**cfg_kwargs))
    return resp.text or ""


class ExtractionError(Exception):
    """Message is safe to show to the faculty member."""


def _generate_openai_style(prompt, model):
    """Hugging Face router and Groq both speak the OpenAI chat-completions format."""
    import httpx
    if PROVIDER == "groq":
        url, key = GROQ_URL, os.environ.get("GROQ_API_KEY", "")
        extra = {"response_format": {"type": "json_object"}}
        if "gpt-oss" in model:
            # reading for meaning benefits from some reasoning; the reply budget caps how much it can use
            extra["reasoning_effort"] = getattr(_ctx, "effort", None) or os.environ.get("GROQ_REASONING_EFFORT", "medium")
    else:
        url, key, extra = HF_URL, os.environ.get("HF_TOKEN", ""), {}

    def call(opts):
        return httpx.post(url, timeout=90, headers={"Authorization": "Bearer " + key},
                          json={"model": model, "temperature": 0, "max_tokens": MAX_OUTPUT_TOKENS, **opts,
                                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})

    r = call(extra)
    if r.status_code == 400 and extra and any(k in r.text.lower() for k in ("reasoning", "response_format", "json")):
        print(f"[extract] {model} rejected an optional setting, retrying without it: {r.text[:200]!r}", flush=True)
        r = call({})  # optional settings are only helpers; the reply is parsed and checked either way
    if r.status_code == 402:
        raise ExtractionError(f"{LABEL} credits are used up for this key. Add credits or use another key. "
                              "You can still fill the form by hand.")
    if r.status_code in (401, 403):
        raise ExtractionError(f"{LABEL} rejected the API key. Check the key is correct and active.")
    if r.status_code == 404:
        raise ExtractionError(f"{LABEL} says the model \"{model}\" is not available to this key. "
                              "Set a model your key can use (see the provider's model list).")
    if r.status_code >= 400:
        err = Exception(f"{r.status_code} {r.text[:300]}")
        try:
            err.retry_after = float(r.headers.get("retry-after", 0))
        except (AttributeError, TypeError, ValueError):
            err.retry_after = 0
        raise err
    try:
        body = r.json()
        choice = body["choices"][0]
        used = (body.get("usage") or {}).get("total_tokens")
        if isinstance(used, (int, float)):
            _usage.append((time.time(), used))
        if choice.get("finish_reason") == "length":
            print(f"[extract] WARNING: {model} reply was cut off at the token limit", flush=True)
        return choice["message"]["content"] or ""
    except (KeyError, IndexError, ValueError):
        raise Exception(f"502 unexpected response from {LABEL}")


_generate_hf = _generate_openai_style  # old name


def _pace(prompt_chars):
    """Groq's free plan limits tokens per minute. Wait a little rather than get rejected between documents."""
    if PROVIDER != "groq":
        return
    now = time.time()
    while _usage and now - _usage[0][0] > 60:
        _usage.popleft()
    need = prompt_chars / 3.5 + 1500  # rough: prompt tokens + typical reply
    while _usage and sum(t for _, t in _usage) + need > GROQ_TPM:
        wait = max(60 - (time.time() - _usage[0][0]), 0) + 0.5
        time.sleep(min(wait, 30))
        now = time.time()
        while _usage and now - _usage[0][0] > 60:
            _usage.popleft()


def _is_daily_quota(err):
    s = str(err).upper()
    limited = "RESOURCE_EXHAUSTED" in s or "429" in s
    return limited and any(k in s for k in ("PERDAY", "PER DAY", "REQUESTS PER DAY", "(RPD)", "(TPD)", "TOKENS PER DAY"))


def _is_retryable(err):
    s = str(err).upper()
    return any(k in s for k in ("413", "504", "DEADLINE_EXCEEDED", "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
                                "TIMEOUT", "TIMED OUT", "CONNECTION"))


def _ask(build, generate, cl, on_status=None):
    """Send one prompt. Attempts: main model (full text), main model (shorter text), fallback model.
    A daily-quota error skips the rest of that model's attempts (retrying would only use up more quota)."""
    plan = [(MODEL, MAX_CHARS), (MODEL, max(MAX_CHARS // 2, 6_000))]
    if FALLBACK_MODEL and FALLBACK_MODEL != MODEL:
        plan.append((FALLBACK_MODEL, max(MAX_CHARS // 2, 6_000)))
    exhausted, last_err, raw = set(), None, ""
    primary_err = None  # the first real error; reported to the user even if the fallback model also fails
    for i, (model, limit) in enumerate(plan):
        if model in exhausted:
            continue
        prompt = build(limit)
        try:
            _pace(len(prompt))
            raw = (generate(prompt, model) if generate else _generate(cl, prompt, model)).strip()
            last_err = None
            break
        except ExtractionError:
            raise
        except Exception as e:
            last_err = e
            primary_err = primary_err or e
            print(f"[extract] {model} ({limit} chars) failed: {str(e)[:300]!r}", flush=True)
            if _is_daily_quota(e):
                exhausted.add(model)
            elif not _is_retryable(e):
                if model == MODEL:
                    raise ExtractionError(f"{LABEL} rejected the request: {str(e)[:300]}")
                exhausted.add(model)  # backup model unusable (e.g. 404): skip it, keep the main model's error
            if on_status and i + 1 < len(plan):
                nxt = plan[i + 1][0]
                on_status(f"{LABEL} is slow or busy, retrying" + (f" with {nxt}" if nxt != model else "") + "...")
            time.sleep(min(getattr(e, "retry_after", 0) or 2, 20))
    if last_err is not None:
        if _is_daily_quota(primary_err) or (exhausted and MODEL in exhausted and _is_daily_quota(last_err)):
            raise ExtractionError(
                f"{LABEL}'s daily request limit has been used up (" + ", ".join(sorted(exhausted)) +
                "). It resets daily; or use an API key with billing enabled. You can still fill the form by hand.")
        raise ExtractionError(f"{LABEL} did not answer in time after several tries. Please try again in a minute, "
                              "or fill the form by hand.")
    return raw


def _parse(raw):
    raw = raw.strip()
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ----------------------------------------------------------------------------- checking what came back
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_CURRENCY = {"INR": "INR", "RS": "INR", "RS.": "INR", "₹": "INR", "RUPEES": "INR", "RUPEE": "INR",
             "USD": "USD", "US$": "USD", "US DOLLAR": "USD", "US DOLLARS": "USD",
             "EUR": "EURO", "EURO": "EURO", "EUROS": "EURO", "€": "EURO",
             "GBP": "GBP", "£": "GBP", "AED": "AED"}


def numbers_in(text):
    out = set()
    for tok in _NUM.findall(str(text)):
        try:
            out.add(float(tok.replace(",", "")))
        except ValueError:
            pass
    return out


def _has_number(n, pool):
    return any(abs(n - p) < 0.005 for p in pool)


def _to_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = _NUM.search(str(v or ""))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def _date_in(iso, text):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(iso).strip())
    if not m:
        return False
    y, mo, d = (int(x) for x in m.groups())
    try:
        datetime.date(y, mo, d)
    except ValueError:
        return False
    nums = {int(x) for x in re.findall(r"\d+", text)}
    low = text.lower()
    return (y in nums or y % 100 in nums) and d in nums and (mo in nums or _MONTHS[mo - 1] in low)


def _norm_choice(col, value):
    v = str(value).strip()
    for o in col.get("options", []):
        if o.lower() == v.lower():
            return o
    if "currency" in col.get("key", ""):
        up = v.upper()
        if up in _CURRENCY and _CURRENCY[up] in col.get("options", []):
            return _CURRENCY[up]
        if re.fullmatch(r"[A-Z]{3}", up) and "Other" in col.get("options", []):
            return "Other"  # a real currency code the form has no column for
    return None


_INR_MARK = re.compile(r"\binr\b|\brs\b|\u20b9|rupee", re.I)


def _clean_value(col, value, quote_text, doc_nums):
    """The value if the document supports it, else None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    t = col.get("type", "text")
    if t == "number":
        n = _to_number(value)
        if n is None or n < 0 or not _has_number(n, numbers_in(quote_text)):
            return None
        if (col.get("inr_only") or "INR" in col.get("label", "")) and not _INR_MARK.search(quote_text):
            return None  # rupee field, but the quoted text never says rupees: never accept a foreign amount
        return int(n) if n == int(n) else round(n, 2)
    if t == "date":
        s = str(value).strip()
        return s if _date_in(s, quote_text) else None
    if t == "choice":
        return _norm_choice(col, value)
    s = str(value).strip()
    if any(not _has_number(n, doc_nums) for n in numbers_in(s)):
        return None  # a number in the text that the document never contains
    return s


def _quotes_of(item):
    if not isinstance(item, dict):
        return []
    q = item.get("quotes")
    if q is None and item.get("quote"):
        q = [item["quote"]]
    if isinstance(q, str):
        q = [q]
    return [str(x).strip() for x in (q or []) if str(x).strip()]


def _verified(quotes, hay):
    """All quotes must really occur in the document (letters/digits compared), else reject."""
    if not quotes:
        return None
    for q in quotes[:3]:
        ql = normalise_loose(q)
        if len(ql) < 4 or ql not in hay:
            return None
    return quotes[:3]


def _ambiguous_date(text):
    for a, b in re.findall(r"(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*\d{2,4}(?!\d)", text):
        if int(a) <= 12 and int(b) <= 12 and a != b:
            return True
    return False


def _clean_item(item, field, hay, doc_nums):
    quotes = _verified(_quotes_of(item), hay)
    if not quotes or not isinstance(item, dict):
        return None
    v = _clean_value(field, item.get("value"), " ".join(quotes), doc_nums)
    if v is None:
        return None
    inferred = bool(item.get("inferred"))
    if field.get("type") == "date" and _ambiguous_date(" ".join(quotes)):
        inferred = True  # 11.04.2026 could be 11 April or 4 November: make the user confirm
    return {"value": v, "quotes": quotes, "inferred": inferred}


def _match_row(t, name):
    n = str(name or "").strip().lower()
    for r in t["fixed_rows"]:
        if n in (r["key"].lower(), r["label"].lower()):
            return r["key"]
    return None


def _verify_doc(form_code, data, text):
    """Check one document's answers. Returns (scalars, tables) containing only what the document proves."""
    hay, doc_nums = normalise_loose(text), numbers_in(text)
    fdata = data.get("fields") if isinstance(data.get("fields"), dict) else data  # flat form: older/simple replies
    scalars = {}
    for f in extractable_fields(form_code):
        got = _clean_item(fdata.get(f["key"]), f, hay, doc_nums)
        if got:
            scalars[f["key"]] = got
    tdata = data.get("tables") if isinstance(data.get("tables"), dict) else {}
    tables = {}
    for t in extractable_tables(form_code):
        cols = {c["key"]: c for c in t["columns"]}
        rows = []
        for item in tdata.get(t["key"]) or []:
            quotes = _verified(_quotes_of(item), hay)
            if not quotes or not isinstance(item, dict):
                continue
            rowkey = None
            if t.get("fixed_rows"):
                rowkey = _match_row(t, item.get("row"))
                if not rowkey:
                    continue
            qtext = " ".join(quotes)
            cells = {}
            for ck in t["extract_table"]["fields"]:
                v = _clean_value(cols[ck], item.get(ck), qtext, doc_nums)
                if v is not None:
                    cells[ck] = v
            if cells:
                rows.append({"row": rowkey, "cells": cells, "quotes": quotes, "inferred": bool(item.get("inferred"))})
        tables[t["key"]] = rows
    return scalars, tables


def verify(fields, data, text):
    """Older entry point kept for simple callers: scalar fields only. Returns (values, sources, not_found)."""
    hay, doc_nums = normalise_loose(text), numbers_in(text)
    fdata = data.get("fields") if isinstance(data, dict) and isinstance(data.get("fields"), dict) else (data if isinstance(data, dict) else {})
    values, sources, not_found = {}, {}, []
    for f in fields:
        got = _clean_item(fdata.get(f["key"]), f, hay, doc_nums)
        if got:
            values[f["key"]] = got["value"]
            sources[f["key"]] = {"quote": " ... ".join(got["quotes"]), "quotes": got["quotes"], "origin": "paper",
                                 "inferred": got["inferred"]}
        else:
            not_found.append(f["key"])
    return values, sources, not_found


# ----------------------------------------------------------------------------- reading documents
def _read_one(form_code, name, text, faculty_name, generate, cl, on_status):
    _, was_cut = select_text(text, MAX_CHARS)
    build = lambda limit: _build_prompt(form_code, name, text, faculty_name, limit)
    data = _parse(_ask(build, generate, cl, on_status))
    if data is None:  # not valid JSON (often a reply cut off by the length limit): try once more, thinking less
        _ctx.effort = "low"
        try:
            data = _parse(_ask(build, generate, cl, on_status))
        finally:
            _ctx.effort = None
    return _verify_doc(form_code, data or {}, text), was_cut


def _row_label(t, r):
    if t.get("fixed_rows"):
        return next(x["label"] for x in t["fixed_rows"] if x["key"] == r["row"])
    return ", ".join(str(v) for v in list(r["cells"].values())[:3])


def extract_documents(form_code, docs, faculty_name, client=None, generate=None, on_status=None):
    """docs: list of (filename, text). Returns {"values", "sources", "not_found", "notes"}."""
    scal_fields, tabs = extractable_fields(form_code), extractable_tables(form_code)
    if (not scal_fields and not tabs) or not docs:
        return {"values": {}, "sources": {}, "not_found": [f["key"] for f in scal_fields], "notes": []}
    if not generate and PROVIDER in ("huggingface", "groq"):
        ok, msg = configured()
        if not ok:
            raise ExtractionError(msg)
        generate = _generate_openai_style
    cl = None if generate else (client or _default_client())

    values, sources, notes = {}, {}, []
    tab_src = {t["key"]: [] for t in tabs}
    overflow = collections.Counter()
    seen = {t["key"]: set() for t in tabs}
    ok_docs, first_err = 0, None

    for i, (name, text) in enumerate(docs, 1):
        if on_status:
            on_status(f"Reading document {i} of {len(docs)} ({name})...")
        try:
            (scalars, tables), was_cut = _read_one(form_code, name, text, faculty_name, generate, cl, on_status)
        except ExtractionError as e:
            first_err = first_err or e
            notes.append(f"{name} could not be read: {e}")
            continue
        ok_docs += 1
        if was_cut:
            notes.append(f"{name} is long, so only its start and the passages about dates, amounts and similar "
                         "details were read. Check any blanks against the document.")
        for key, got in scalars.items():
            if key in values:
                if str(values[key]).strip().lower() != str(got["value"]).strip().lower():
                    notes.append(f"{name} gives a different value for “{next(f['label'] for f in scal_fields if f['key'] == key)}” "
                                 f"({got['value']}). Kept the one from {sources[key]['doc']}.")
                continue
            values[key] = got["value"]
            sources[key] = {"quote": " ... ".join(got["quotes"]), "quotes": got["quotes"], "origin": "paper",
                            "inferred": got["inferred"], "doc": name}
        for t in tabs:
            rows = tables.get(t["key"], [])
            if t.get("fixed_rows"):
                cur_all = values.setdefault(t["key"], {})
                has_sel = any(c["key"] == "selected" for c in t["columns"])
                for r in rows:
                    cur = cur_all.setdefault(r["row"], {})
                    if has_sel:
                        cur["selected"] = True
                    label = _row_label(t, r)
                    for ck, v in r["cells"].items():
                        if ck not in cur or cur[ck] == v:
                            cur[ck] = v
                        elif isinstance(v, str) and isinstance(cur[ck], str):
                            cur[ck] = f"{cur[ck]}; {v}"
                        else:
                            notes.append(f"{name}: a second value ({v}) was found for “{label}”. Kept {cur[ck]}; "
                                         "please check.")
                    tab_src[t["key"]].append({"label": label, "quotes": r["quotes"], "inferred": r["inferred"], "doc": name})
            else:
                cur_rows = values.setdefault(t["key"], [])
                for r in rows:
                    sig = json.dumps(r["cells"], sort_keys=True)
                    if sig in seen[t["key"]]:
                        continue
                    seen[t["key"]].add(sig)
                    if t.get("max_rows") and len(cur_rows) >= t["max_rows"]:
                        overflow[t["key"]] += 1
                        continue
                    cur_rows.append(r["cells"])
                    tab_src[t["key"]].append({"label": _row_label(t, r), "quotes": r["quotes"],
                                              "inferred": r["inferred"], "doc": name})
    if ok_docs == 0 and first_err:
        raise first_err
    for t in tabs:
        if tab_src[t["key"]]:
            sources[t["key"]] = {"origin": "paper", "rows": tab_src[t["key"]]}
        elif t["key"] in values and not values[t["key"]]:
            del values[t["key"]]
        if overflow[t["key"]]:
            notes.append(f"{t['label']}: {overflow[t['key']]} more item(s) were found than the form has room for "
                         f"({t.get('max_rows')} rows). Only the first {t.get('max_rows')} were filled.")
    not_found = [f["key"] for f in scal_fields if f["key"] not in values]
    return {"values": values, "sources": sources, "not_found": not_found, "notes": notes}


def run_extraction(form_code, text, faculty_name, client=None, generate=None, on_status=None):
    """Single-text convenience wrapper. Returns (values, sources, not_found_keys)."""
    r = extract_documents(form_code, [("document", text)], faculty_name, client=client, generate=generate,
                          on_status=on_status)
    return r["values"], r["sources"], r["not_found"]
