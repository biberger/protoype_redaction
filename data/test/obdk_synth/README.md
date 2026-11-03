# Synthetic OBDK test set (`synthetic_obdk`)

A synthetic stand-in for the Reisswolf OBDK decisions (kept outside this repo): 200 invented Austrian lawyer-disciplinary
decisions (OBDK 1973-2013, OGH as Disziplinargericht from 2014), annotated with all 21 legalner v2 labels. The real
decisions may not be used for training, so this set exists to score models; it is **test-only** and must not be
used for training either if it is meant to stay a clean benchmark.

## How it was made

- `tools/make_plan.py` → `plan.jsonl`: 200 briefs in 20 batches by era (b01-b03 1973-79, b04-b07 1980s,
  b08-b12 1990s, b13-b16 2000-09, b17-b18 2010-13, b19-b20 2014-24). Each brief fixes the year, decision type,
  topic, required rare labels, check-digit-valid identifiers (IBAN mod-97, AT SVNR, FN check letter, UID), two
  hard cases, name origins, RIS pseudonymisation (10 %) and typescript/OCR style (pre-1995, 60 %).
- 20 Claude Sonnet sub-agents (one per batch, run from Claude Code) wrote the documents in inline-tag format
  (`[[label|surface]]`) following `GUIDE.md`. They never had access to anything outside their working folder.
- `tools/check.py` validates and converts: tag syntax, header, lint for untagged repeats, dates, IBANs, phones,
  e-mails, act names and norm citations, degree/prefix boundaries, check digits. Every document passes `--strict`.
- `tools/leak_check.py` compares all person, address, organization and identifier spans verbatim against the
  3,318 real decisions. 28 person names that coincided with names in the real corpus were renamed
  (`tools/fix_leaks.py`). Remaining matches (`build/leak_check.json`) are real public institutions (banks,
  insurers, the OBDK's phone number), common street names and four short numbers.

## Files

| file | content |
|---|---|
| `raw/bNN/*.md` | the 200 source documents with inline tags and a YAML header (doc_type, year) |
| `obdk_synth_test.jsonl` | canonical legalner records, chunked to ≤ 1500 chars (1,337 records) |
| `obdk_synth_test.docs.jsonl` | the same, one record per whole document (200 records) |
| `eval/` | model predictions and `report.json` from `tools/eval_model.py` |
| `GUIDE.md`, `plan.jsonl`, `tools/` | writer guide, briefs and scripts, to extend or regenerate the set |

Canonical record: `{id, source, doc_id, lang, jurisdiction, text, spans: [{label, start, end, text}], meta}`;
judge and lawyer spans also emit a `person` span, date ranges are merged (GENERATION.md conventions).

## Statistics

209,219 words; spans per label (whole documents):

| label | n | label | n | label | n |
|---|---|---|---|---|---|
| person | 4957 | organization | 873 | id_document_number | 86 |
| date | 2646 | case_number | 798 | company_register_number | 80 |
| court | 1746 | address | 313 | social_security_number | 78 |
| lawyer | 1500 | phone_number | 232 | license_plate | 74 |
| judge | 1147 | other_identifier | 208 | tax_id | 64 |
| legal_norm | 1101 | land_register_id | 174 | street | 52 |
| location | 875 | bank_account | 146 | email | 20 |

## Known limitations

- Written by one model family: style is more regular than the real scans, OCR noise is mild compared with the
  real typescripts (the real RTFs contain heavy OCR garbage in old decisions).
- Statute section numbers are plausible but partly invented; irrelevant for NER, wrong as law.
- Some briefs combine decision types and topics loosely; writers adapted the facts.
- Literature citations reuse a few real commentary authors (e.g. Feil/Wennig), as the briefs prescribe.
- Rare labels (email, street, tax_id) have small support; read their scores as indicative.
