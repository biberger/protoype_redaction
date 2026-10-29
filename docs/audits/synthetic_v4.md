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
