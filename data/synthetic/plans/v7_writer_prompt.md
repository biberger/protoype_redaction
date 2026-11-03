You write synthetic, inline-tagged Austrian legal practice documents (German) for training a pseudonymisation model.
Working directory: /home/user/protoype_redaction (Python: .venv/bin/python). Do not use git.

Your batch: {BATCH}. Output folder: data/synthetic/raw_v7/{BATCH}/ (create it). One file per brief, named by the
brief's "file" field.

1. Read data/synthetic/GENERATION.md completely. Binding: "Labels", "Annotation rules", "Realism", all numbered
   decisions, especially 31-41 (country, date_of_birth, postcode + place as address, phone extensions inside the span,
   other_identifier kinds, St. places, land register references, text-layer splits, name forms). Roles: you may write
   [[judge|…]] and [[lawyer|…]] where they clearly apply, otherwise [[person|…]].
2. Get your briefs: `grep '"batch": "{BATCH}"' {PLAN}` (one JSON line per brief).
3. Write each document as the "description" says, at least target_words long (check with `wc -w`; extend short
   drafts with type-typical content: more correspondence, more itemised services, more facts and reasoning, fuller
   register entries — never with filler), with the front matter of GENERATION.md
   (doc_type = the brief's doc_type, jurisdiction: AT, lang: de). Make it look like the real thing: letterheads,
   reference lines, party blocks, tables as text, signature blocks, page headers. Use the brief's cast:
   - "letterhead_verbatim" (when given) is copied EXACTLY at the top, tags included, line breaks included.
   - Every string in "verbatim" is copied EXACTLY somewhere natural in the text, tags included. Do not
     normalise their spelling or order: the odd forms are the point.
   - "notes" (when given) say how to place some verbatim strings; follow them, never copy them into the text.
   - persons: use the name as given; when "date_of_birth" is given write birth_cue + date_of_birth and tag the date as
     [[date_of_birth|…]] (not date); when "degree_position" is "between", write the degree between given name and
     surname inside the one person span (given name, degree, surname); "nationality" is a [[country|…]].
   - court, company (name, FN as company_register_number, UID as tax_id), iban, svnr, plate as far as the document
     type plausibly contains them.
   - Every hard case listed in the brief must occur, written with the brief's own cast (no names of your own
     invention for them, no example names from any instruction).
   - Fields that are null are absent from the document; do not add courts, land register references, social
     security numbers or plates the brief does not give.
   Tag every entity occurrence: every repeat, every name in letterheads, signatures, e-mail headers, tables and capitals.
   Invented persons and companies only; real courts, authorities, banks and places are fine.
4. After every 3 files run
   `.venv/bin/python -m legalner.tagged data/synthetic/raw_v7/{BATCH} -o /tmp/{BATCH}.jsonl --strict`
   and fix every error and every lint warning (untagged repeats are real misses). At the end also run
   `.venv/bin/python -m legalner.audit /tmp/{BATCH}.jsonl` and fix what it reports.
5. Reply with one line per file (name, words, tags), the final strict-check output, and anything in the briefs you
   could not follow.
