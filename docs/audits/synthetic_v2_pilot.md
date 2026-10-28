# Audit: synthetic v2 pilot (72 documents)

Date: 2026-10-28. Raw agent output: `synthetic_v2_pilot_llm_audit.json`.

## Method

1. `python -m legalner.tagged data/synthetic/raw_v2 --strict`: all 72 files parse and pass lint.
2. `python -m legalner.audit` (new, rule-based, all documents): titles inside person spans, dates without a
   day, gazette references tagged as norms, identifier check digits (IBAN, AT SV-Nr, FN, ATU, DE USt-IdNr,
   RV-Nr, AHV, CHE-UID, NIR, SIREN/SIRET, BE enterprise number) and identifier-shaped surfaces under the wrong label.
3. LLM audit (one reviewer agent per batch, 3 random documents per batch, seed 42, 18 of 72 documents)
   against `GENERATION.md`: missed, wrong-label, wrong-boundary and spurious spans; realism issues.

## Rule-based findings (all 72 documents, before fixing)

| finding | count | fix |
|---|---|---|
| form of address inside person/lawyer span (`Me`, `M.`, `Mme`; CH-fr only) | 12 spans | moved outside the tag |
| month without day tagged as date (`septembre 2023`) | 1 | untagged |
| wrong check digit (2 DE USt-IdNr, 2 RV-Nr, 1 SIRET) | 5 | replaced with `fake_ids` values |

Synthetic v1 (40 documents, written before `fake_ids` existed): 32 invalid IBAN/FN/SV-Nr, all replaced.

## LLM audit (18 documents, 923 non-role spans)

Errors per batch (errors / spans in the sampled documents):

| batch | errors | spans | rate |
|---|---|---|---|
| at_civil | 7 | 136 | 5.1% |
| at_private | 1 | 162 | 0.6% |
| at_public | 7 | 154 | 4.5% |
| ch | 26 | 182 | 14.3% |
| de | 1 | 152 | 0.7% |
| fr | 2 | 137 | 1.5% |
| **total** | **44** | **923** | **4.8%** |

By kind: 39 missed, 3 wrong boundary, 1 wrong label, 1 spurious. Almost all errors are *missed* spans,
which in training become false negatives.

Per label (sampled documents):

| label | spans | errors | rate | typical error |
|---|---|---|---|---|
| legal_norm | 148 | 23 | 15.5% | CH-fr documents leave `art. 257d CO`, `art. 90 LTF` untagged |
| court | 69 | 5 | 7.2% | the deciding court's own full name ("Der Verfassungsgerichtshof hat …") untagged |
| organization | 62 | 5 | 8.1% | repeated short form of an authority; public bodies in contract clauses |
| person | 219 | 4 | 1.8% | court clerk, first-name coreference ("vom Ricky") |
| case_number | 39 | 2 | 5.1% | lower-court number in parentheses |
| date | 208 | 2 | 1.0% | one missed, one yearless recurring date tagged |
| address | 52 | 1 | 1.9% | address without postcode |
| company_register_number | 12 | 1 | 8.3% | `FN` prefix outside the span |
| bank_account | 8 | 1 | 12.5% | the word `IBAN` inside the span |
| location, email, phone_number, identifiers | 112 | 0 | 0% | |

## Fixes applied

- Two new `--strict` lint checks, so these error classes are caught in every future batch:
  untagged norm citations (`§`/`Art.`/`article` + number + act abbreviation) and untagged full names of
  top courts (VfGH, VwGH, OGH, BVwG, BGH, BVerfG, BGer, Cour de cassation …). Together with the new
  legal_norm convention (bare act names, see `docs/PLAN.md`) this tagged 37 + 28 missed spans across the corpus.
- All errors the LLM audit reported were fixed by hand. `FN` and `IBAN` conventions were normalised
  corpus-wide (`[[company_register_number|FN 284067x]]`, `IBAN [[bank_account|DE…]]`).
- After the fixes, both synthetic sets pass `--strict` and `legalner.audit` with zero findings.

Estimated residual error rate after the fixes: about 1–2% of spans (the LLM-audit errors outside the
classes now linted were ≈1.5%).

## Realism (not label errors)

The reviewers found 60 realism issues in 18 documents, about 3 per document. Typical ones: wrong OGH senate
for the subject matter (3 Ob for a building dispute), a court outside its district (LG Krems as appeal
court for Mödling), procedural contradictions (ordinary vs. extraordinary Revision, "ohne mündliche
Verhandlung" after a hearing), dates or amounts that don't add up, wrong but existing norms
(§ 9 DSG for health data), outdated legal forms (SPRL after 2019), and contact data in judgments.

These issues don't change entity labels, so the documents stay in the training set. They should **not**
be used for the Austrian gold set without review. `GENERATION.md` now has a consistency checklist for the
scale-up.
