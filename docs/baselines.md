# Zero-shot baselines (step 4)

Date: 2026-10-28. Threshold 0.5, exact-match spans, labels queried per source coverage (`legalner.evaluate`),
role labels (`judge`, `lawyer`) in a separate pass. CPU, 4 cores.

Data (1,666 records): all synthetic v2 (335) and v1 (131) records (no model has been trained on them yet),
600 sampled sentences of LER test and 600 of MAPA de/fr (seed 13). Raw reports: `out/baselines/*.json`
(not committed; rerun with `bash out/baselines/run.sh` after `legalner.build … -o data/build/v0`).

| | n | base P | base R | base F1 | PII model P | PII model R | PII model F1 |
|---|---|---|---|---|---|---|---|
| all / * | 6709 | 0.46 | 0.63 | 0.53 | 0.42 | 0.75 | 0.54 |
| all / address | 379 | 0.91 | 0.20 | 0.33 | 0.95 | 0.76 | 0.85 |
| all / bank_account | 62 | 0.22 | 0.23 | 0.22 | 0.68 | 0.71 | 0.69 |
| all / brand | 1 | 0.04 | 1.00 | 0.08 | 0.02 | 1.00 | 0.03 |
| all / case_citation | 110 | 0.02 | 0.02 | 0.02 | 0.04 | 0.06 | 0.05 |
| all / case_number | 215 | 0.65 | 0.12 | 0.20 | 0.68 | 0.42 | 0.52 |
| all / company_register_number | 56 | 0.59 | 0.29 | 0.39 | 0.36 | 0.39 | 0.38 |
| all / contract | 26 | 0.04 | 0.08 | 0.05 | 0.03 | 0.08 | 0.04 |
| all / court | 336 | 0.58 | 0.48 | 0.53 | 0.40 | 0.82 | 0.54 |
| all / date | 1191 | 0.85 | 0.92 | 0.88 | 0.81 | 0.92 | 0.86 |
| all / email | 83 | 0.88 | 1.00 | 0.94 | 0.94 | 1.00 | 0.97 |
| all / id_document_number | 18 | 0.00 | 0.00 | 0.00 | 0.21 | 0.39 | 0.27 |
| all / judge | 159 | 0.16 | 0.45 | 0.24 | 0.21 | 0.59 | 0.31 |
| all / land_register_id | 77 | 0.00 | 0.00 | 0.00 | 0.38 | 0.12 | 0.18 |
| all / lawyer | 124 | 0.12 | 0.73 | 0.20 | 0.16 | 0.84 | 0.26 |
| all / legal_norm | 1043 | 0.63 | 0.81 | 0.71 | 0.56 | 0.81 | 0.66 |
| all / license_plate | 28 | 0.64 | 0.25 | 0.36 | 0.85 | 0.79 | 0.81 |
| all / literature | 24 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| all / location | 472 | 0.42 | 0.47 | 0.44 | 0.31 | 0.91 | 0.46 |
| all / organization | 604 | 0.30 | 0.73 | 0.42 | 0.26 | 0.80 | 0.39 |
| all / other_identifier | 44 | 1.00 | 0.07 | 0.13 | 0.47 | 0.16 | 0.24 |
| all / person | 1504 | 0.48 | 0.62 | 0.54 | 0.38 | 0.65 | 0.48 |
| all / phone_number | 98 | 0.99 | 0.96 | 0.97 | 0.97 | 1.00 | 0.98 |
| all / social_security_number | 21 | 0.64 | 0.43 | 0.51 | 0.41 | 0.67 | 0.51 |
| all / street | 7 | 0.03 | 0.86 | 0.05 | 0.03 | 0.86 | 0.05 |
| all / tax_id | 27 | 0.09 | 0.52 | 0.15 | 0.43 | 0.67 | 0.52 |
| jur=AT / * | 3383 | 0.62 | 0.64 | 0.63 | 0.55 | 0.77 | 0.65 |
| jur=BE / * | 92 | 0.44 | 0.63 | 0.52 | 0.44 | 0.76 | 0.56 |
| jur=CH / * | 719 | 0.60 | 0.71 | 0.65 | 0.54 | 0.86 | 0.66 |
| jur=DE / * | 1564 | 0.32 | 0.57 | 0.41 | 0.28 | 0.66 | 0.39 |
| jur=EU / * | 412 | 0.26 | 0.71 | 0.38 | 0.20 | 0.74 | 0.32 |
| jur=FR / * | 483 | 0.40 | 0.48 | 0.44 | 0.47 | 0.71 | 0.56 |
| jur=LU / * | 56 | 0.56 | 0.71 | 0.63 | 0.55 | 0.80 | 0.65 |
| source=ler / * | 501 | 0.12 | 0.42 | 0.19 | 0.10 | 0.45 | 0.17 |
| source=mapa / * | 412 | 0.26 | 0.71 | 0.38 | 0.20 | 0.74 | 0.32 |
| source=synthetic / * | 3905 | 0.55 | 0.65 | 0.59 | 0.50 | 0.80 | 0.62 |
| source=synthetic_v1 / * | 1891 | 0.73 | 0.62 | 0.67 | 0.63 | 0.73 | 0.68 |
PII character recall (share of gold PII characters covered by any prediction): base **0.813**,
PII model **0.925**.

base = `fastino/gliner2.5-multi-v1`, PII model = `fastino/gliner2-privacy-filter-PII-multi`.

## Reading

- Both models are around F1 0.53. The PII model has better recall on identifiers and addresses
  (address F1 0.85 vs 0.33, bank_account 0.69 vs 0.22, license_plate 0.81 vs 0.36), hence its higher PII character
  recall. The base model is better on `legal_norm`, `person` and `company_register_number`.
- The base model's address recall of 0.20 is a boundary convention issue: it stops at the house number and
  tags the city separately, while our spans run `street number, postcode city`.
- Role labels are poor zero-shot (judge F1 0.24/0.31, lawyer 0.20/0.26). Precision is low because every
  person near a court gets labelled judge.
- Legal references outside `legal_norm` (case_citation, contract, literature) are ≈0. These are LER-only labels
  with LER's long-span conventions.
- LER is the weakest source (F1 0.19/0.17), with very low precision: LER sentences have few entities and
  many queried labels, and both models over-predict organization/location/person.
- Over-prediction of names, as reported for the PII model on the SPY benchmark, shows here too (person
  P 0.38).

The fine-tuned model has to beat **F1 0.54 overall and PII character recall 0.925** on this set. The decisive
number will be the Austrian gold set, which doesn't exist yet.
