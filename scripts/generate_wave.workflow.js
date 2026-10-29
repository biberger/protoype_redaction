export const meta = {
  name: 'synthetic-generation-wave',
  description: 'Haiku agents write tagged synthetic legal documents from genplan briefs, validated with --strict and legalner.audit',
  phases: [{ title: 'Generate' }],
}
// args: { plan: "data/synthetic/plans/v3.jsonl", out: "data/synthetic/raw_v3", batches: ["v3_b000", ...] }
const root = '/home/user/protoype_redaction'
const RESULT = {
  type: 'object',
  properties: {
    files: { type: 'array', items: { type: 'string' } },
    strict_passed: { type: 'boolean' },
    audit_clean: { type: 'boolean' },
    notes: { type: 'string' },
  },
  required: ['files', 'strict_passed', 'audit_clean'],
}
const results = await parallel(args.batches.map(batch => () => agent(
`You write synthetic, fictitious legal documents with inline entity tags, as training data for a NER model.
Working directory: ${root}. Use Python via \`python3\` from the repository root.

1. Read the spec ${root}/data/synthetic/GENERATION.md completely and follow it exactly.
2. Your briefs are the lines of ${root}/${args.plan} whose "batch" field is "${batch}" (get them with
   \`grep '"batch": "${batch}"' ${args.plan}\`). Write one document per brief to
   ${root}/${args.out}/${batch}/<file> (the brief's "file" field), with the header block
   (doc_type, jurisdiction, lang from the brief).
3. Each brief gives a cast: use ALL its persons, judges, lawyers, companies (with their register/VAT numbers),
   addresses and identifiers, with exactly these spellings (degrees go inside the person span). Use the
   roles that fit the document type. You may add further entities (courts, authorities, places, dates,
   case numbers, extra persons), but new persons need varied, realistic names, never well-known names.
   An address that says "(invent ...)" is a placeholder: invent a realistic one in that city.
   Further identifiers with check digits come from \`python3 -m legalner.fake_ids <kind>\` (kinds: iban AT,
   svnr, fn, uid_at, ust_idnr_de, steuernummer_de, rvnr, hrb, ahv, che_uid, nir, siren, siret, tva_fr, be_enterprise,
   be_nrn, lu_matricule, plate_at/_de/_ch/_fr, passport_/id_card_/driving_licence_ + at/de/ch/fr).
   A person with "degree" and "degree_after" is written with the whole chain inside the span, e.g.
   [[person|Prof. Dr. Dr. Max Muster, MBA PhD (New York)]] (at least at the first mention).
   "rare_entities" MUST all appear, tagged with exactly these labels: license_plate, id_document_number (the
   number only, e.g. "Reisepass Nr. [[id_document_number|P1234567]]"), street (the street name WITHOUT a house
   number, e.g. the scene of an incident: "auf der [[street|Heiliggeiststraße]]"), phone_number, email.
   A hard case asking for ALL CAPS or lower case: write that passage so (keep ß as ß or write SS as the document
   would) and tag its entities as usual, e.g. [[organization|HUBER BAU GMBH]].
   Every document is new: never copy sentences, facts, amounts, vehicles, dates or clauses from another document
   (also not from the other documents of your batch). Vary structure, wording and facts per document type.
   Licence plates: the district/canton code should fit the holder's residence or the registering company.
   Use the law that fits the parties (no KSchG/consumer rules between two companies).
4. Respect "target_words" (±25%), "pseudonymised" (RIS style: A*****, *****, tagged with the label of what was
   replaced; then the cast persons are replaced by placeholders), "ocr_noise" (hyphenation across line breaks,
   O/0 and l/1 swaps, stray spaces, kept inside spans; ONLY when ocr_noise is true) and work the two "hard_cases" into the text.
   French documents are written entirely in French, German ones in German (CH: no ß).
5. After every document run
   \`python3 -m legalner.tagged ${args.out}/${batch} -o /tmp/${batch}.jsonl --strict && python3 -m legalner.audit /tmp/${batch}.jsonl\`
   and fix EVERY error, lint warning and audit finding before writing the next document. Lint warnings
   about untagged occurrences mean: tag that occurrence (or rephrase), never delete tags to silence them.
6. Before finishing, run the command once more over the whole batch directory. Report the files you wrote
   and whether --strict passed and the audit was clean.`,
  { label: `gen:${batch}`, phase: 'Generate', schema: RESULT, model: 'haiku' })
  .then(r => ({ batch, ...r }))
  .catch(e => ({ batch, files: [], strict_passed: false, audit_clean: false, notes: String(e) }))
))
return results
