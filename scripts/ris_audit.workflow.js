export const meta = {
  name: 'ris-rule-audit',
  description: 'Count misses of the RIS annotation rules in inline-tagged decision excerpts',
  phases: [{ title: 'Audit' }],
}
// args: { files: [absolute paths of inline-tagged excerpts, one decision each] }
const SCHEMA = {
  type: 'object',
  properties: {
    file: { type: 'string' },
    mentions: { type: 'object', description: 'number of true mentions per label in the excerpt (tagged or not)',
      properties: { person: { type: 'integer' }, address: { type: 'integer' }, date: { type: 'integer' },
        case_number: { type: 'integer' }, court: { type: 'integer' } },
      required: ['person', 'address', 'date', 'case_number', 'court'] },
    misses: { type: 'array', items: { type: 'object', properties: {
      label: { type: 'string', enum: ['person', 'address', 'date', 'case_number', 'court'] },
      kind: { type: 'string', enum: ['missed', 'boundary', 'wrong_label', 'spurious', 'role'] },
      surface: { type: 'string' }, note: { type: 'string' } }, required: ['label', 'kind', 'surface'] } },
  },
  required: ['file', 'mentions', 'misses'],
}
const results = await parallel(args.files.map(f => () => agent(
`You audit rule-based NER annotations of an Austrian court decision from RIS. Do NOT modify any file.
Read /home/user/protoype_redaction/data/synthetic/GENERATION.md (labels, annotation rules, "Gold-set decisions").
The excerpt ${f} is inline-tagged ([[label|surface]]); pseudonymised placeholders were already replaced by invented
values. Only these labels are in scope: person (incl. judge and lawyer role labels), address, date, case_number,
court. Read the excerpt completely and:
1. Count every true mention of each in-scope label (tagged or not); judge/lawyer count as person.
2. List every error: missed (untagged mention), boundary (span cut or over-extended, e.g. leftover placeholder
   letters, degree outside, title inside), wrong_label (e.g. address vs location), spurious (tagged but not an
   entity), role (judge/lawyer/person role wrong per the Gold-set decisions: officials, clerks, Schriftführer,
   experts, prosecutors -> person; representatives not called Rechtsanwalt/notary -> person).
Be precise and conservative; count each occurrence separately. Other labels (organization, location, legal_norm) are
out of scope and must not be reported.`,
  { label: `ris-audit:${f.split('/').pop()}`, phase: 'Audit', schema: SCHEMA, model: 'sonnet' })))
return results.filter(Boolean)
