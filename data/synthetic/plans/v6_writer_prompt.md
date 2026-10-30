You write synthetic, inline-tagged EU legal documents (German or French) for training a legal NER model.
Working directory: /home/user/protoype_redaction (Python: .venv/bin/python). Do not use git.

Your batch: {BATCH}. Output folder: data/synthetic/raw_v6/{BATCH}/ (create it). Write exactly one file per brief,
named by the brief's "file" field.

1. Read data/synthetic/GENERATION.md completely, especially "Labels", "Annotation rules", decisions 1-30 and the
   section "EU documents (synthetic v6)". Those rules are binding.
2. Get your briefs: `grep '"batch": "{BATCH}"' data/synthetic/plans/v6.jsonl` (15 JSON lines).
3. For each brief write one document of about target_words words in the brief's language and doc_type, with the
   front matter from GENERATION.md (doc_type, jurisdiction: EU, lang). Use the cast from the brief:
   - parties: persons with "cited_as_initials" appear only by those initials (the CJEU anonymises them; tag as
     person); companies use the given name, and where "acronym" is given, define it once in parentheses and then use
     the acronym alone; companies without a legal form keep that bare name.
   - member_state_of_origin, referring_court, national_authority, governments_observations, eu_bodies, judges,
     advocate_general (label judge, decision 30), representatives (lawyer), agents (person), cited_cases (cite each
     by short name with date and case number; the short name gets the party's label, decision 27).
   - Every hard case listed in the brief must occur.
   - Tag every entity occurrence, including headings in capitals ("URTEIL DES [[court|GERICHTSHOFS]]") and every
     repeat of acronyms and short names. States acting as parties or submitting observations are organization;
     the same country as a territory is location (decision 25).
4. After every 3 files run
   `.venv/bin/python -m legalner.tagged data/synthetic/raw_v6/{BATCH} -o /tmp/{BATCH}.jsonl --strict`
   and fix every error and every lint warning (untagged repeats are real misses: tag them). At the end also run
   `.venv/bin/python -m legalner.audit /tmp/{BATCH}.jsonl` and fix what it reports.
5. Self-check each document before moving on: dates in order, the same person keeps one name and gender, case
   numbers match the court (C- for the Court of Justice, T- for the General Court), labels match GENERATION.md.

Reply at the end with one line per file: file name, word count, number of tags; then the final output of the
strict check (must show no errors and no lint warnings).
