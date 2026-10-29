export const meta = {
  name: 'gold-review',
  description: 'Reviewer agents correct the tags of Austrian gold-set paragraphs (first pass before human review)',
  phases: [{ title: 'Review' }],
}
// args: { n: number of reviewers, assignments?: TSV "<i>\t<path>" (default data/gold/at/assignments.tsv),
//         extra?: additional instructions (e.g. for RIS paragraphs) }
const root = '/home/user/protoype_redaction'
const assignments = args.assignments || 'data/gold/at/assignments.tsv'
const RESULT = {
  type: 'object',
  properties: {
    reviewed: { type: 'array', items: { type: 'string' } },
    changes: { type: 'array', items: { type: 'object', properties: {
      file: { type: 'string' }, kind: { type: 'string', enum: ['added', 'removed', 'relabelled', 'boundary', 'text'] },
      label: { type: 'string' }, surface: { type: 'string' } }, required: ['file', 'kind', 'surface'] } },
    unsure: { type: 'array', items: { type: 'string' }, description: 'file: question for the human reviewer' },
  },
  required: ['reviewed', 'changes', 'unsure'],
}
const results = await parallel(Array.from({ length: args.n }, (_, i) => () => agent(
`You review annotations for a gold evaluation set of an NER model for legal texts. Precision matters more than speed.
Working directory: ${root}.

1. Read ${root}/data/synthetic/GENERATION.md completely: the labels, the "Do not tag" list, all annotation rules and the
   "Gold-set decisions" are the gold standard.${args.extra ? '\n' + args.extra : ''}
2. For each file below (inline tags [[label|surface]]), read the whole paragraph and check EVERY entity:
   missed entities (incl. repeats, bare surnames, genitive forms, dates, places in closing lines, act names),
   wrong labels (judge/lawyer vs person; organization vs court; address vs street vs location; identifier types),
   wrong boundaries (titles like Herr/Hofrat outside, degrees inside, articles outside, full address incl. postcode
   and city), and spurious tags. Correct the tags in place with the Edit tool. Never change the text outside the
   tags (except to fix an obvious tag artefact such as a duplicated "FN FN").
3. In the header, set "review: convention-pass". Then move the file from data/gold/at/pending/ to data/gold/at/reviewed/
   (mkdir -p first, use git mv is NOT needed; plain mv).
4. After each file run \`python3 -m legalner.tagged data/gold/at/reviewed -o /tmp/gold_${i}.jsonl --max-chars 0 --strict\`
   and fix any error or warning that concerns your files (other reviewers write to the same directory; ignore theirs).
5. Report every change you made and list cases you were unsure about as questions for the human reviewer.

Your files are the paths in ${assignments} whose first column is ${i}:
\`awk -F'\\t' '$1 == ${i} {print $2}' ${assignments}\` (paths are under pending/; once moved they are in reviewed/).`,
  { label: `gold:${i}`, phase: 'Review', schema: RESULT, model: 'sonnet' })
))
return results
