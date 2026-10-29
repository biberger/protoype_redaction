export const meta = {
  name: 'gold-convention-pass',
  description: 'Apply the settled gold-set decisions (GENERATION.md) to the agent-reviewed Austrian gold paragraphs',
  phases: [{ title: 'Convention' }],
}
// args: { n: number of reviewers, assignments: repo-relative TSV "<i>\t<path>" }
// All paragraphs of one document go to the same reviewer, so text fixes stay consistent across paragraphs.
const root = '/home/user/protoype_redaction'
const RESULT = {
  type: 'object',
  properties: {
    reviewed: { type: 'array', items: { type: 'string' } },
    changes: { type: 'array', items: { type: 'object', properties: {
      file: { type: 'string' },
      kind: { type: 'string', enum: ['relabelled', 'boundary', 'added', 'removed', 'merged', 'split', 'text'] },
      decision: { type: 'integer', description: 'number of the gold-set decision (1-13), 0 for a plain annotation error' },
      before: { type: 'string' }, after: { type: 'string' } }, required: ['file', 'kind', 'decision', 'before', 'after'] } },
    unsure: { type: 'array', items: { type: 'string' } },
  },
  required: ['reviewed', 'changes', 'unsure'],
}
const assignments = args.assignments || 'data/gold/at/convention_assignments.tsv'
const results = await parallel(Array.from({ length: args.n }, (_, i) => () => agent(
`You apply settled annotation conventions to gold evaluation paragraphs of a legal NER model (Austrian German).
Precision matters more than speed. Working directory: ${root}.

1. Read ${root}/data/synthetic/GENERATION.md completely, especially "Annotation rules" and "Gold-set decisions"
   (numbered 1-13). Those decisions override any earlier convention in the files.
2. Your files: \`awk -F'\\t' '$1 == ${i} {print $2}' ${assignments}\`. All paragraphs of a document are yours.
   Each file header has "origin: synthetic/AT_v3_NNNN_<type>#k"; the full source document is
   data/synthetic/raw_v3/*/AT_v3_NNNN_<type>.md (use it to decide roles, e.g. whether a representative is called
   Rechtsanwalt/Notar anywhere, and to see which name a person has elsewhere). Never edit the source documents.
   Machine-found candidates per file: \`grep <filename> data/gold/at/convention_hints.txt\` (hints, not orders).
   Earlier open questions about your files: \`grep <NNNN> docs/audits/gold_at_review.md\`.
3. For every file, check EVERY span against the decisions, in particular:
   - judge only for persons who judge; lawyer only for Rechtsanwalt/notary (also as Gerichtskommissär/
     Verlassenschaftskurator). Officials, clerks, Gerichtsvollzieher, BFA/DSB caseworkers, experts, doctors, tax
     advisers, prosecutors, Kinderbeistand, signatures under "Für die Richtigkeit der Ausfertigung" -> person.
     Representatives (Bevollmächtigter, Vertreter, Testamentsvollstrecker) whose profession is not stated as
     Rechtsanwalt/notary anywhere in the source document -> person. A role label applies to all mentions of that
     person in the paragraph.
   - degree chains before AND after the name are inside the span ("Prof. Dr. Max Muster, MBA", "Nele Löw, MBA",
     "BSc Mine Schönwiese"); titles/forms of address (Herr, Frau, Hofrat, Senatspräsident, Staatsanwalt) outside.
   - "Long Name (ABBR)": two spans, brackets outside. Bare authority abbreviations (BH, BFA, DSB) are organization.
   - generic words without name or place untagged; unique federal bodies (Datenschutzbehörde, Bundesamt für ...) tagged.
   - a place inside a name or unit (Regionaldirektion Steiermark, Außenstelle Linz, Werk Reichersberg, a painting
     title) is NOT a separate location; "im Bezirk [[location|Hartberg]]"; "[[location|Republik Moldau]]" whole.
   - date ranges are ONE date span ("[[date|1. bis 15. Juni 2025]]", "[[date|vom ...]]" without "vom");
     day+month without year is a date; recurring yearless dates ("jeweils am 31. März") untagged.
   - a party's own file/policy/customer numbers -> other_identifier; delivery-note/invoice numbers untagged;
     prefixes GZ, Zl., SNR outside the span (FN stays inside: "FN 531927x").
   - norm chain within one act = one span; "§ 14 Abs 2" without act tagged when it cites a statute, not when it is
     a contract section heading; long act names and "UN-Kaufrecht" are legal_norm.
   - Decision 13: fix generation artefacts in the TEXT of the gold file (not only the tags): one person under two
     names (use the name the source document uses most for that role, in all your paragraphs of the document),
     doubled degrees ("MBA X, MBA" -> one), garbled names (e.g. "Reich Edler" in 0300, "Da D Bahjat" in 0537:
     replace with a plausible full name consistent with the rest of the document), impossible dates (dates after
     2026-10-29 in past events, statements describing later events). Keep edits minimal.
   Correct in place with the Edit tool. Then set the header line to "review: convention-pass" in EVERY one of your
   files (also unchanged ones).
4. Run \`python3 -m legalner.tagged data/gold/at/reviewed -o /tmp/conv_${i}.jsonl --max-chars 0 --strict\` and fix
   errors or warnings in your files (others edit the same directory; ignore theirs).
5. Report every change (with the decision number) and remaining doubts.`,
  { label: `conv:${i}`, phase: 'Convention', schema: RESULT, model: 'sonnet' })
))
return results
