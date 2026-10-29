# Synthetic v4: pilot audit

Plan: `python -m legalner.genplan --docs 2000 --wave v4 --per-batch 6 --seed 41 -o data/synthetic/plans/v4.jsonl`
(334 batches; every brief has 1-3 rare-label entities: licence plate, ID document number, street without number,
phone, e-mail; vehicle/residence/insurance/police document types drawn 4x as often; 7 % of persons with degree chains
before and after the name; hard cases include ALL-CAPS and all-lower-case passages). Writers: Haiku agents
(`scripts/generate_wave.workflow.js`).

## Pilot (60 documents, batches v4_b000-b009)

All 60 pass `--strict` and `legalner.audit` (as reported by the writers and re-run after the lint changes below).
Every rare entity of the briefs is present in its document; ALL-CAPS letterheads and lower-case chat/e-mail passages
are present where the brief asked for them.

LLM audit of 12 documents (Sonnet, `scripts/audit.workflow.js`, seed 12): **22 span errors in 578 spans = 3.8 %**
(v3 after its lint: 1.1 %).

| Error | Count | Action |
|---|---|---|
| organization missed (letterhead, sign-off, same name in other case) | 6 | lint: other-case repeats of tagged strings in ALL-CAPS/lower-case passages |
| location missed (dateline, bare place) | 4 | lint: untagged place in dateline (`Koblenz, 14.03.2026`) |
| person missed in a lower-case chat message | 3 | lint as above |
| date range split / recurring yearless date tagged | 2 + 2 | ranges are merged in `legalner.tagged` (decision 8); writer prompt |
| other_identifier missed ("Ihr Zeichen") | 2 | writer prompt |
| address, case_number, legal_norm missed | 3 | — |

The new lint rules flagged 12 more misses in 9 of the 60 pilot documents; they were fixed by hand. (On v3 they flag 50
misses in 1,000 documents; v3 is training data and is left as is.)

Realism (≈ 5.8 issues per document, more than v3's ≈ 3): chronology (letters confirming events before they happen,
appeal deadlines), geography (court not competent for the place, German-Swiss streets in Vaud, plates from other
districts), Austrian degrees and terms in German/Swiss documents, e.K./KG with HRB numbers, an identifier copied from
the spec. Fixes for the remaining waves: degree lists per country and HRA for e.K./KG in `genplan` (applied to the
unwritten briefs b010+), and a self-check step in the writer prompt (chronology, geography, roles, letterhead/
dateline/sign-off tagged, names in caps/lower-case passages, no reuse of spec examples or of text from other
documents of the batch).

## Wave 1 (batches 10-49, 240 documents)

All 240 pass `--strict` and `legalner.audit` (one Belgian huissier with "Me" inside a span fixed by hand: bailiffs are
`person`). LLM audit of 6 documents (seed 31): 7 errors reported, 1 of them wrong (a notary signing "Für die Richtigkeit
der Ausfertigung" stays `lawyer`). Remaining misses: a company never tagged in a Gesellschaftsvertrag title and § 1
(fixed), a unique federal body (Deutscher Wetterdienst, fixed), and a town of a tagged address written alone three
times. New lint rule: the town of a tagged address that appears alone elsewhere is flagged; it found 55 such misses in
the 300 v4 documents, all tagged `location` by script (`Gemeinde Himmelberg`, `in Niederthalheim`, `Gemarkung
Heringen`). Realism notes are of the same kind as in the pilot (competence of the court, chronology of enclosures),
fewer per document.

## Waves 2-3 (batches 50-129, 480 documents)

All pass `--strict` and `legalner.audit`. LLM audit of 6 documents (seed 77): 11 errors, mostly places mentioned once
after a preposition ("Steuerberater in Mannheim", "né à Alès") and an insurer named only in an ALL-CAPS letterhead.
New lint rule: a known municipality (AT/DE/CH gazetteer, ≥ 5 letters, plus larger French-speaking towns) after
in/nach/aus/bei/à/de that is not tagged; it found 28 such misses in batches 0-129, tagged `location` by script or hand.
Realism notes stay at ≈ 5 per document (competence/geography and arithmetic in claims are the most frequent kinds).

## Quality measurement after the lint rules (waves 4-7)

LLM audit of 18 documents from batches 130-291 (seed 2027, `scripts/audit.workflow.js`, Sonnet):
**13 span errors in 852 spans = 1.5 %** (pilot 3.8 %, v3 1.1 %). Errors: 4 organizations missed (a company in a
title line, an ALL-CAPS ministry letterhead, a unique federal body, a short company name), 1 IBAN in a quoted e-mail,
a court name repeated in lower case, a street, a place, a yearless date in an e-mail, an act name, 2 label errors
(a party's own reference tagged case_number, decision 9), 1 degree boundary ("Ing." outside). All 13 were fixed.
New lint rules from this round: untagged IBANs; repeats of a tagged multi-word name that differ only in the case of
the first letter. They found 5 more misses in batches 0-291 (4 IBANs, 1 court), fixed.
Realism: ≈ 6 issues per document (amounts and fines, competence, structure of the document type); these do not
affect the tags.
