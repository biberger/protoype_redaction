You correct model pre-annotations in REAL EU court texts so they follow our annotation conventions exactly.
Working directory: /home/user/protoype_redaction (Python: .venv/bin/python). Do not use git.

Set: {SET}. Your files: {FILES}
They are in {DIR}/ . Chunk source for the integrity check: {CHUNKS}.

1. Read data/synthetic/GENERATION.md completely: "Labels", "Annotation rules", decisions 1-30 and "EU documents
   (synthetic v6)". Those rules are binding. Tags are `[[label|surface]]`, no nesting.
2. Each file holds a real judgment, opinion or order, split into chunks by blank lines. A model has pre-tagged it;
   it is often wrong on organisations (acronyms, companies without legal form, EU institutions, states acting as
   parties), on court self-references ("der Gerichtshof", "la Cour"), and it misses some persons and case numbers.
   Go through every chunk and fix the tags with the Edit tool:
   - add missing tags (every occurrence, incl. headings in capitals, repeats, acronyms, party initials),
   - remove wrong ones (generic words, "die Stiftung", ABl./JO references, amounts),
   - change wrong labels (country as party -> organization, as territory -> location; Advocate General -> judge;
     agents/Bevollmächtigte -> person; lawyers (Rechtsanwalt, avocat, Solicitor, Barrister) -> lawyer;
     judges of the chamber and the President -> judge; the referring national court -> court),
   - fix span boundaries (titles and articles outside; "e.a."/"u. a." inside party spans as written; a norm chain
     inside one act stays one legal_norm span; "C-378/17", "C ‑ 378/17" and ECLI ids are case_number).
   NEVER change, add or delete any character of the text itself: only the `[[label|` and `]]` parts. Real names are
   real: do not anonymise or rename anything.
3. After each file run
   `.venv/bin/python -m legalner.pretag --check {CHUNKS} {DIR}`  (must say "ok" for your files)
   `.venv/bin/python -m legalner.tagged {DIR} -o /tmp/{SET}_check.jsonl --strict`
   Fix every error, every text change and every lint warning that concerns your files (untagged repeats of a tagged
   string are usually real misses; if a warning is a false alarm, e.g. a word that is an entity only in another
   sense, leave it and list it in your reply).
4. Reply with one line per file: name, tags before/after, the main kinds of corrections, and any lint warnings you
   left on purpose with the reason.
