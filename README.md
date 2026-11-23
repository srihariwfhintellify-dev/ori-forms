# SPJIMR ORI Forms

Faculty pick one of six forms (A, B, C-1, C-2, D-I, D-II), optionally upload supporting documents (papers, CVs, invoices, invitation emails), review what was
found (with the exact source passage), fill what the paper did not contain, and download a Word/Excel file.

## Run (SPJIMR server)
    sudo apt install tesseract-ocr            # needed for scanned PDFs/images
    cd backend && pip install -r requirements.txt
    export GEMINI_API_KEY=...                 # required to read papers (to be confirmed by SPJIMR)
    export GEMINI_MODEL=gemini-2.5-flash      # confirm the model name with SPJIMR IT
    export ORI_ADMIN_EMAILS=a@spjimr.org,b@spjimr.org   # who can open the Admin screen
    # optional: ORI_ALLOWED_EMAIL_DOMAIN (default spjimr.org), ORI_RETENTION_DAYS (default 1826 = 5 years),
    #           ORI_DATA_DIR (database + generated files), ORI_JWT_SECRET
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    cd ../frontend && npm install && npm run build   # served by the backend from frontend/dist
Put it behind HTTPS (e.g. nginx) before faculty use it. Back up ORI_DATA_DIR.

## No-guess rule
A value from a paper is accepted only if the model also returns a quote that appears verbatim in the paper
text (`backend/app/extract.py::verify`). Otherwise the field stays empty and the user must enter it.
Signatures, PID, internal-use tables, the approval/remark box and the D-II "Eligible" column are never filled.

## Layouts
`backend/app/docx_forms.py` reproduces Annexures A, B, C-1, C-2 and D-I; D-II fills the original Excel file
(`backend/templates/D2_expense_claim.xlsx`). Field definitions: `backend/app/forms.py`.

## Tests
    python3 tests/test_backend.py

## Choosing the AI service for reading papers
Set `EXTRACT_PROVIDER` to `groq`, `gemini` (default) or `huggingface`.
- Groq: `GROQ_API_KEY`, optional `GROQ_MODEL` (default `openai/gpt-oss-120b`; Groq retired the free-tier Llama models on 2026-08-16), `GROQ_FALLBACK_MODEL`.
  Free plan caps tokens per minute, so only the first ~14,000 characters are sent (`GROQ_MAX_CHARS`).
- Gemini: `GEMINI_API_KEY`, `GEMINI_MODEL`, optional `GEMINI_FALLBACK_MODEL`.
- Hugging Face: `HF_TOKEN`, `HF_MODEL` (no default), optional `HF_FALLBACK_MODEL`.
Whatever the service, a value is used only if its quote appears verbatim in the paper.

## Reading documents (all six forms)
Every form accepts documents: invoices, receipts, tickets, programme invitations, saved emails.
Accepted: PDF (text or scanned), Word, images, `.eml`, `.txt`, `.md`, `.html`. Outlook `.msg` must be saved as PDF or `.eml`.
Each file is read in its own request, using the whole text: facts may sit in sentences, tables or subject lines
and are combined from context. Anything the model had to work out is marked "Worked out from your document.
Please confirm." Amounts, dates and options are still checked in code against the quoted text; currencies are
never converted and nothing is guessed.
