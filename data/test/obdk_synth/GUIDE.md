# Writer guide: synthetic OBDK disciplinary decisions (inline-tagged)

You write **invented** Austrian decisions in lawyers' disciplinary matters, in the style of the Oberste
Berufungs- und Disziplinarkommission für Rechtsanwälte und Rechtsanwaltsanwärter (OBDK, until 2013) and of
the Oberster Gerichtshof as disciplinary appeal court (from 2014). Every entity is tagged inline. The files
are a test set for a legal NER model and may later be used for training, so the tags must be exhaustive and
follow these rules exactly. This guide follows `legalner` schema v2 (data/synthetic/GENERATION.md) with the
OBDK decisions in section 4.

**Never open, list or search anything outside the `synthetic` folder.** The parent folder holds real
decisions that must not be read or copied. Every person, law firm, company, address, identifier and case
fact is invented. Do not use names of real people (no real judges, lawyers, politicians or celebrities).
Real courts, authorities, chambers, places and statutes are fine.

## 1. File format

One document per file, `raw/<batch>/<file from the brief>`, UTF-8:

```
---
doc_type: erkenntnis_berufung_schuld_strafe
jurisdiction: AT
lang: de
year: 1987
---
Die [[court|Oberste Berufungs- und Disziplinarkommission für Rechtsanwälte und Rechtsanwaltsanwärter]] hat
am [[date|14. Oktober 1987]] durch den Senatspräsidenten des [[court|Obersten Gerichtshofes]]
[[judge|Dr. Wendelin Pražak]] als Vorsitzenden ...
```

- Tags are `[[label|surface]]`. No nesting, no spaces at the inner edges, no blank line inside a tag.
  A single line break (and a hyphen) inside a tag is allowed when the typescript breaks the line there:
  `[[court|Disziplinarrat der Rechtsan-\nwaltskammer Wien]]` (written with a real line break).
- Plain text only: no Markdown headings, bold, bullet syntax or tables with pipes. Use the layout of a typed
  or printed decision (centred words become their own lines, "Begründung:", numbered points "1.", "a)").
- Tag **every** occurrence, including repeats, bare surnames, abbreviations and headings in capitals.
  Generic role words ("der Beschuldigte", "der Anzeiger", "der Disziplinarrat", "die Kommission") are
  not entities.

## 2. Labels (exactly these 21)

| label | what | OBDK examples |
|---|---|---|
| person | named natural person not acting as judge or lawyer: Anzeiger, clients, witnesses, experts, Schriftführer, Generalanwalt, officials, relatives, authors of literature; academic degrees inside; pseudonyms `Dr. N***** M*****`, `A*****` | `Mag. Franziska Holub`, `Holub`, `Ing. Kemal Aydın` |
| judge | person acting as judge: Vorsitzender/Senatspräsident, Hofräte des OGH in the panel, Anwaltsrichter (lay judges count), Vorsitzender/Mitglieder of the deciding Disziplinarrat senate, a judge who filed the Anzeige when introduced as Richter | `[[judge|Dr. Wendelin Pražak]]` |
| lawyer | Rechtsanwalt, Rechtsanwältin, Rechtsanwaltsanwärter/in, notary; the accused lawyer, the Verteidiger, Kammeranwalt and Kammeranwalt-Stellvertreter, opposing counsel, a Untersuchungskommissär when the text calls them Rechtsanwalt | `[[lawyer|Dr. Gerlinde Achleitner-Ruß]]` |
| organization | Rechtsanwaltskammer, Ausschuss der Rechtsanwaltskammer, Österreichischer Rechtsanwaltskammertag (ÖRAK), Generalprokuratur, Staatsanwaltschaft, Finanzamt, banks, insurers, companies, law firms, Versorgungseinrichtung with its chamber, Bezirkshauptmannschaft, Gemeinde as a body | `Rechtsanwaltskammer für Kärnten`, `Ausschuss der Rechtsanwaltskammer Wien`, `Generalprokuratur`, `Kanzlei Brandl & Partner Rechtsanwälte GmbH` |
| court | named courts and disciplinary bodies with their name or place: OBDK (full and short), Disziplinarrat **with** its chamber (one span), OGH, VfGH, VwGH, EGMR, BG/LG/OLG with place | `Oberste Berufungs- und Disziplinarkommission`, `OBDK`, `Disziplinarrat der Rechtsanwaltskammer für Oberösterreich`, `Obersten Gerichtshofs`, `Landesgericht für Strafsachen Graz`, `Bezirksgericht Innere Stadt Wien` |
| address | postal address with house number; whole span incl. door, postcode and city when contiguous | `Schmerlingplatz 11, 1011 Wien`, `Hauptplatz 7/2/14, 8010 Graz`, `4020 Linz, Landstraße 33` |
| street | street or square name without house number | `Kärntner Ring` in "Kanzlei am Kärntner Ring" |
| location | city, municipality, district, region, country not inside another span | `Rechtsanwalt in [[location|Bruck/Leitha]]`, `Tirol`, `Jugoslawien` |
| date | day-precise date in any spelling, noisy OCR included; ranges with "bis"/"–" become one span (written as two tags, merged by the checker) | `14. Oktober 1987`, `14.10.1987`, `2o. November 1989`, `27. 8. 85` |
| case_number | case reference of OBDK, OGH, Disziplinarrat, courts, authorities, land register Tagebuchzahl; prefixes GZ, Zl., AZ, TZ stay outside (`TZ [[case_number|4412/00]]`) | `Bkd 12/77`, `Bkv 3/85`, `D 45/03-12`, `DV 34/09`, `20 Os 4/16k`, `3 Cg 123/85`, `12 E 345/89` |
| bank_account | IBAN, BIC or old account number (only the number) | `AT48 4734 9698 8861 5213`, `Konto Nr. [[bank_account|123-456.789]]` |
| social_security_number | SV-Nummer (use the ones from your brief: they carry a valid check digit) | `SV-Nr. [[social_security_number|...]]` |
| tax_id | UID or Steuernummer (number only, prefix "UID", "Steuernummer", "St.Nr." outside) | `ATU39286303`, `St.Nr. [[tax_id|12-345/6789]]` |
| company_register_number | FN, HRB, HRA **with** the prefix inside | `FN 123456a`, `HRB 23.456` |
| license_plate | vehicle plate | `W 123.456` (before 1990), `GU-4567B`, `L 45 AB` |
| land_register_id | EZ, KG (with number and name), Gst-Nr.; "Grundstück Nr." keeps "Nr." outside | `EZ 403`, `KG 01009 Neubau`, `Gst-Nr. 211/3`, `Grundstück Nr. [[land_register_id|1430/29]]` |
| id_document_number | passport, ID card, driving licence numbers (number only) | `P1234567` |
| other_identifier | other personal identifiers: Treuhandbuch-Nr., Klientennummer, Polizzennummer, Anwaltscode, Mitgliedsnummer (number only, prefix outside) | `Treuhandbuch-Nr. [[other_identifier|666/77]]`, `Anwaltscode [[other_identifier|R482913]]` |
| phone_number | phone or fax number incl. extension | `52152 DW 3780`, `0662/87 34 21`, `+43 1 533 47 18` |
| email | e-mail address (only from 2000 on) | `kanzlei@holub-recht.at` |
| legal_norm | statute citation with §/Art incl. the act, and bare act names; a chain within one act that names the act once is one span; when each citation names its act, split | `§ 1 DSt`, `§ 9 Abs 1 RAO`, `§§ 1 und 2 DSt 1990`, `Art 6 EMRK`, `§ 10 Abs 2 RL-BA 1977`, `RAO`, `Disziplinarstatut` |

Not tagged: amounts (S 20.000,--, € 3.500), years or months without a day, BGBl./RGBl. references,
reporter references (AnwBl 1987, 123; SZ 54/12; EvBl 1991/45; JBl 1985, 33), generic words ("das Gericht",
"der Disziplinarrat", "die Kammer"), adjectives ("Wiener"), page numbers.

## 3. Annotation rules

- Forms of address and job/office titles stay outside: Herr, Frau, Senatspräsident, Hofrat, Hofrätin,
  Generalanwalt, Kammeranwalt, Rechtsanwalt, Anwaltsrichter. Academic degrees are inside, before and after
  the name: `[[lawyer|Dr. Mag. Peter Lenz, LL.M.]]`, `[[person|Ing. Josef Bauer]]`.
- A judge or lawyer keeps the role label at every mention (`[[lawyer|Lenz]]`, `[[lawyer|Dr. Lenz]]`).
- Office titles followed by an entity: "Hofrat des [[court|Obersten Gerichtshofs]] [[judge|Dr. Kern]]",
  "Präsident der [[organization|Rechtsanwaltskammer Wien]]".
- No nesting: "Disziplinarrat der Rechtsanwaltskammer für Niederösterreich" is one court span (no
  organization or location inside); "Kanzlei Dr. Brandl & Partner" is one organization span;
  "Landesgericht Linz" is one court span.
- Decisions cited as precedent: tag the parts, `[[court|OBDK]] [[date|12. 3. 1990]], [[case_number|Bkd 5/89]]`;
  the reporter reference after it stays untagged.
- Literature: authors are person, a norm inside the citation is legal_norm, the rest untagged:
  `[[person|Feil]]/[[person|Wennig]], Anwaltsrecht [[legal_norm|§ 9 RAO]] Rz 5`.
- A judge or lawyer named in another role (a Bezirksrichterin in a cited judgment, a lawyer as
  Masseverwalter who the text calls Rechtsanwalt) keeps judge/lawyer.
- Genitive -s stays inside (`[[lawyer|Dr. Lenz']]`, `[[person|Holubs]] Anzeige`).
- OCR noise and line breaks stay inside spans exactly as written.
- Pseudonymised placeholders are tagged with the label of what they replace (`[[person|A*****]]`,
  `[[address|*****]]`).
- Places in datelines are tagged (`[[location|Wien]], am [[date|14. Oktober 1987]]`).
- Every occurrence of a day-precise date is tagged, also repeats.

## 4. OBDK structure and era style

Typical OBDK decision (adapt to the decision type in your brief):

1. Head: body name (often in capitals or spaced), seat in Wien (Justizpalast, Schmerlingplatz/Museumstraße)
   with phone and extension, case number (`Bkd 9/90`), sometimes a page number.
2. "Erkenntnis" / "Beschluss" / "Im Namen der Republik" (OGH from 2014).
3. Kopf: "Die Oberste Berufungs- und Disziplinarkommission ... hat am ... durch den Senatspräsidenten des
   Obersten Gerichtshofes Dr. X als Vorsitzenden, die Anwaltsrichter Dr. Y und Dr. Z und den Hofrat des
   Obersten Gerichtshofes Dr. W als weitere Richter, in Gegenwart der Schriftführerin Mag. V in der
   Disziplinarsache gegen Dr. U, Rechtsanwalt in Ort, wegen ... über die Berufung ... gegen das Erkenntnis des
   Disziplinarrats der Rechtsanwaltskammer ... vom ..., GZ ..., nach mündlicher Verhandlung in Anwesenheit des
   Vertreters der Generalprokuratur Generalanwalt Dr. T, des Kammeranwalts Dr. S, des Beschuldigten und seines
   Verteidigers Dr. R zu Recht erkannt:" (Beschlüsse: "in nichtöffentlicher Sitzung ... beschlossen:").
4. Spruch: "Der Berufung wird (nicht) Folge gegeben." Penalty, costs (§ 54 DSt / § 38 DSt 1990).
5. "Entscheidungsgründe:" / "Begründung:": the Disziplinarrat's findings, the facts with dates, places,
   parties, amounts and identifiers; the appeal; the legal assessment with norms, earlier OBDK decisions and
   literature.
6. Closing: dateline, sometimes "Für die Richtigkeit der Ausfertigung" with a person's name.

Era:

- 1973-1989: Disziplinarstatut 1872 (`§ 2 DSt`), RAO, RL-BA 1977; penalties schriftlicher Verweis, Geldbuße
  in Schilling, Untersagung, Streichung; "daß", "muß", "gefaßt"; Handelsregister `HRB`/`HRA` instead of FN;
  black licence plates `W 123.456`; old account numbers; no e-mail, no IBAN; typewriter layout.
- 1990-1999: DSt 1990 (`§ 1 Abs 1 DSt`, `§ 16 DSt`); still Schilling and "daß"; Firmenbuch `FN` from 1991;
  UID from 1995; Anwaltscode from late 1990s.
- 2000-2013: "dass"; euro from 2002; IBAN, e-mail, Rechtsanwalts-GmbH, Geldwäscheregeln (§ 8a ff RAO),
  Treuhandbuch der Kammer.
- 2014 onward: the Oberster Gerichtshof decides ("Der Oberste Gerichtshof hat als Disziplinargericht für
  Rechtsanwälte und Rechtsanwaltsanwärter ... durch den Senatspräsidenten ... als Vorsitzenden, die Hofrätin ...
  und die Anwaltsrichter ... in der Disziplinarsache ..."); case numbers like `20 Os 4/16k`; "Im Namen der
  Republik"; Disziplinarrat GZ like `D 45/15`.
- Briefs with `ocr_typescript: true`: hard line breaks every 60-70 characters, hyphenated words across line
  ends, page numbers on their own line, a few OCR errors (o for 0, l for 1, missing umlauts) inside and
  outside entities.
- Briefs with `ocr_typescript: false` are clean digital text: no OCR errors at all, no page-number lines, no
  hard wrapping. If such a brief lists an OCR-noise, page-break or hyphenated-line-break hard case, ignore that hard case and
  pick a different one from this list instead: a date range, a pseudonymised placeholder, a genitive name, an identifier with spaces in it.
- Even in typescript briefs, OCR errors are rare: at most 3-5 per document, not in every date.

## 5. Realism and consistency

- Length: the brief's `target_words` (±20 %). Real OBDK decisions are dense with names, dates and norms.
- Names: diverse and invented, from the brief's `names_from` plus Austrian names; double-barrelled names,
  particles, accents (č, ć, ş, ő). Never reuse the same surnames across your documents.
- Name mix: about two thirds of the people in a document carry typical Austrian/German names; the
  `names_from` origins go to some parties, witnesses, clients and lawyers. Judges, Generalanwalt and
  Kammeranwalt before 2000 are almost always Austrian names. Do not take names from the guide's examples.
- Use the identifiers given in the brief (`identifiers`) where its `required_labels` ask for them; you may
  invent further numbers of the same shape (IBAN, SV-Nummer, FN and UID only from the brief, they carry
  valid check digits).
- Each `required_labels` entry must occur at least once, in a natural place (a Treuhandkonto in the facts,
  the plate of the car in a drunk-driving case, the SV-Nummer in a quoted application, the e-mail in a
  quoted letter, the Anwaltscode in the ERV context, a phone number in the head or a letterhead).
- Both `hard_cases` of the brief must occur. `ris_pseudonymised: true` means parties, witnesses and the
  accused appear pseudonymised (`Dr. N***** M*****`), judges and counsel by name.
- Internal consistency: dates in order, the Disziplinarrat of the chamber where the accused practises,
  one name and gender per person, case number years matching the filing year, the penalty matching the era.

## 6. Workflow

1. Read this guide completely.
2. Read your 10 briefs: the lines of `plan.jsonl` whose `"batch"` is yours.
3. Write the documents one by one into `raw/<batch>/`.
4. After every 3 documents and at the end, run the checker and fix **every** error and lint warning
   (an untagged repeat is a real miss; a false alarm, e.g. a surname that is also an ordinary word in a
   sentence, may stay, but say why in your final reply):

   `uv run --no-project python -I "<synthetic>\tools\check.py" "<synthetic>\raw\<batch>" -o "<synthetic>\build\<batch>.jsonl" --strict`

5. Self-check each document: labels match section 2, all occurrences tagged, consistent facts.
6. Final reply: one line per file (file, words, tags), then the last checker summary and any warnings you
   left with the reason.
