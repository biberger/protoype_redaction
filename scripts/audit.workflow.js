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
        label: { type: 'string', description: 'gold label (for missed/wrong_label/wrong_boundary) or the tagged label (for spurious)' },
        surface: { type: 'string' },
        note: { type: 'string' },
      }, required: ['kind', 'label', 'surface'] } },
      realism_issues: { type: 'array', items: { type: 'string' } },
    }, required: ['file', 'errors', 'realism_issues'] } },
  },
  required: ['docs'],
}
const root = '/home/user/protoype_redaction'
const results = await parallel(Object.entries(SAMPLES).map(([batch, files]) => () =>
  agent(`You are auditing synthetic, inline-tagged legal documents used to train a NER model. Do NOT modify any file.

Read the annotation spec first: ${root}/data/synthetic/GENERATION.md (labels, "Do not tag" list, annotation rules).
Then read each of these documents in full (tags are [[label|surface]]):
${files.map(f => `- ${root}/${f}`).join('\n')}

For each document, list every annotation error against the spec:
- missed: an entity that should be tagged but is not (give the gold label). Check every occurrence, incl. repeats, bare surnames, abbreviations, dates, identifiers, places.
- wrong_label: tagged with the wrong label (give the correct label in "label", the used label in "note").
- wrong_boundary: right label but the span is too long/short (e.g. title "Herr" inside, postcode cut off, chain of norms merged into one span when the spec wants them separate, list within one act split).
- spurious: tagged but should not be tagged at all per spec (e.g. bare act name, year-only date, generic court word).
Be precise and conservative: only report clear violations of the spec, not matters of taste. Count each occurrence separately.
Also list realism_issues briefly (wrong legal register for the jurisdiction, implausible structure, anachronisms, wrong court names, factual impossibilities like an OGH case number format used for a Landesgericht).`,
    { label: `audit:${batch}`, phase: 'Audit', schema: SCHEMA, model: 'sonnet' })
    .then(r => ({ batch, ...r }))
))
return results
