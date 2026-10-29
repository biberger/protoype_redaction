export const meta = {
  name: 'ris-gold-artefacts',
  description: 'Fix pseudonymisation-filler artefacts in the text of RIS gold paragraphs (gold-set decision 13)',
  phases: [{ title: 'Fix' }],
}
const root = '/home/user/protoype_redaction'
const RESULT = { type: 'object', properties: {
  changes: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, before: { type: 'string' }, after: { type: 'string' } }, required: ['file', 'before', 'after'] } },
  unsure: { type: 'array', items: { type: 'string' } } }, required: ['changes', 'unsure'] }
const results = await parallel(Array.from({ length: 6 }, (_, i) => () => agent(
`You clean up gold evaluation paragraphs of a legal NER model. Working directory: ${root}.
Read ${root}/data/synthetic/GENERATION.md (labels, annotation rules, Gold-set decisions 1-13).
Your files: \`awk -F'\\t' '$1 == ${i} {print $2}' data/gold/at/assignments_ris_artefacts.tsv\` (all paragraphs of a document are yours).
They are real Austrian court decisions (RIS) whose pseudonymisation placeholders were replaced by invented values by a
rule system that sometimes inserted the wrong KIND of value: a surname where a court seat, a number, a duration, a time,
a vehicle make, a case number or a company belongs ("Landesgerichtes für Strafsachen Hinterseer", "Handelsgericht Schlögl",
"Freiheitsstrafe von Stumpf", "Zankl Uhr", "Hastert Jahren", "Euro 6.839,24 Landauer 0,05", "Rgasse", an address in a
case-number slot, impossible dates such as a birth date after the decision or a date order that cannot be). Reviewers'
notes about such spots: data/gold/at/ris_review_notes.txt.
Task (decision 13): for each such artefact, replace the filler in the TEXT with a plausible value of the right kind
(a real Austrian court seat matching the court type: LG für Strafsachen only Wien/Graz, Handelsgericht only Wien,
OLG Wien/Graz/Linz/Innsbruck; a case number like "23 Hv 112/20k"; "2 Jahren"; "14:30 Uhr"; a vehicle make; a company
name with legal form; a plausible date), keep the same value for the same filler across your paragraphs of a document,
and set the tags to match (e.g. the whole "Landesgerichtes für Strafsachen Wien" as one court span; a case number as
case_number; durations and times untagged). Do not change anything else: real RIS wording, judges' names written in
clear and correctly filled names stay. Keep header "review: convention-pass".
Then run \`python3 -m legalner.tagged data/gold/at/reviewed -o /tmp/art_${i}.jsonl --max-chars 0 --strict\` and fix
errors/warnings in your files. Report every text change.`,
  { label: `artefacts:${i}`, phase: 'Fix', schema: RESULT, model: 'sonnet' })))
return results