# Audit: synthetic v3 (genplan briefs, Haiku agents)

Same method as `synthetic_v2_pilot.md`: `--strict` and `legalner.audit` on every document, plus a Sonnet
reviewer agent on 12 random documents per round (`scripts/audit.workflow.js`).

| round | documents | sampled | spans | errors | rate | main error |
|---|---|---|---|---|---|---|
| v2 pilot (for comparison) | 72 | 18 | 923 | 44 | 4.8% | untagged CH-fr norm citations |
| v3 pilot (b000–b009) | 60 | 12 | 608 | 48 | 7.9% | untagged repeats of dates (29), `l'article` inside norm spans (5) |
| v3 wave 1 (b010–b049), after the new lint rules | 240 | 12 | 549 | 6 | **1.1%** | places in closing lines (3), one lawyer tagged person (3) |

Fixes from the v3 rounds:
- `--strict` now flags untagged day-precise dates (de/fr/ISO), articles inside legal_norm spans, untagged
  genitive surnames, and an identifier prefix repeated before its span (`FN [[company_register_number|FN 123a]]`
  rendered as "FN FN 123a"). Existing corpora were fixed by script (56 dates, 12 boundaries, 30+ duplicated
  prefixes) and the remaining findings by hand.
- Court briefs no longer force IBANs and social security numbers into judgments (from batch 50 on).

Realism: the reviewers still find 3–6 issues per document, e.g. case-number years that don't match filing
dates, implausible court benches, identifiers in judgment reasoning, mixed AT/DE citation style, and
geography (a German street name in a Vaud municipality). These don't affect labels; the gold set must be
reviewed by a person.
