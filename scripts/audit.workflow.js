export const meta = {
  name: 'audit-synthetic',
  description: 'Audit groups of synthetic documents against GENERATION.md',
  phases: [{ title: 'Audit' }],
}
// args: { groups: { name: [repo-relative paths] } }
const SAMPLES = args.groups
const SCHEMA = {
  type: 'object',
  properties: {
    docs: { type: 'array', items: { type: 'object', properties: {
      file: { type: 'string' },
      errors: { type: 'array', items: { type: 'object', properties: {
        kind: { type: 'string', enum: ['missed', 'wrong_label', 'wrong_boundary', 'spurious'] },
        label: { type: 'string' }, surface: { type: 'string' }, note: { type: 'string' },
      }, required: ['kind', 'label', 'surface'] } },
      realism_issues: { type: 'array', items: { type: 'string' } },
    }, required: ['file', 'errors', 'realism_issues'] } },
  },
  required: ['docs'],
}
const root = '/home/user/protoype_redaction'
const results = await parallel(Object.entries(SAMPLES).map(([batch, files]) => () =>
  agent(`You are auditing synthetic, inline-tagged legal documents used to train a NER model. Do NOT modify any file.

Read the annotation spec first: ${root}/data/synthetic/GENERATION.md (labels, "Do not tag" list, annotation rules, Gold-set decisions).
Then read each of these documents in full (tags are [[label|surface]]):
${files.map(f => `- ${root}/${f}`).join('\n')}

For each document, list every annotation error against the spec:
- missed: an entity that should be tagged but is not (give the gold label). Check every occurrence, incl. repeats, bare surnames, abbreviations, dates, identifiers, places, letterheads, datelines, ALL-CAPS and lower-case passages.
- wrong_label: tagged with the wrong label (give the correct label in "label", the used label in "note").
- wrong_boundary: right label but the span is too long/short.
- spurious: tagged but should not be tagged at all per spec.
Note: date ranges written as two date spans are merged automatically by the parser; do not report them.
Be precise and conservative: only report clear violations of the spec, not matters of taste. Count each occurrence separately.
Also list realism_issues briefly (chronology, geography/competence, wrong register for the jurisdiction, implausible structure).`,
    { label: `audit:${batch}`, phase: 'Audit', schema: SCHEMA, model: 'sonnet' })
    .then(r => ({ batch, ...r }))
))
return results