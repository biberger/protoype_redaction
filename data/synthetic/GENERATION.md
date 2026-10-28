# Synthetic document generation spec (schema v2)

Instructions for anyone (human or LLM agent) writing tagged synthetic legal
documents. Output feeds `python -m legalner.tagged` and must pass `--strict`.

## File format

One document per file, `data/synthetic/raw_v2/<batch>/<jurisdiction>_<batch>_<nn>_<doc_type>.md`:

```
---
doc_type: ogh_urteil
jurisdiction: AT
lang: de
---
Der [[court|Oberste Gerichtshof]] hat durch den Senatspräsidenten [[judge|Dr. Reinhold Taufner]] …
die klagende Partei [[person|Mag. Johanna Steinberger]], vertreten durch [[lawyer|Dr. Paul Huber]], Rechtsanwalt in [[location|Wien]] …
```

- `jurisdiction`: AT, DE, CH, FR, BE, LU, LI or EU. `lang`: de or fr.
- Tags are `[[label|surface]]`; no nesting; no leading or trailing spaces inside the tag.
- Tag **every** occurrence, including repeats, bare surnames ("Steinberger") and
  abbreviations. Generic role words ("die Klägerin", "le requérant") are not entities.
- Validate after every few files:
  `python3 -m legalner.tagged data/synthetic/raw_v2/<batch> -o /tmp/<batch>.jsonl --strict`
  and fix every error and lint warning before continuing.

## Labels

| label | what | examples |
|---|---|---|
| person | named natural person not acting as judge or lawyer: parties, witnesses, experts, officials, relatives; incl. academic degrees; pseudonyms (`A*****`, `Mag. B***** C*****`, `M.K.`) | `Mag. Johanna Steinberger`, `Steinberger`, `A*****` |
| judge | person acting as judge, panel member, Rechtspfleger, juge, président de chambre | `[[judge|Dr. Reinhold Taufner]]` |
| lawyer | person acting as attorney, defence counsel, notary, avocat, notaire | `[[lawyer|Dr. Paul Huber]]` |
| organization | company, association, bank, law firm, authority, ministry, police station, public body as legal entity; not courts | `Linz Textil GmbH`, `Bezirkshauptmannschaft Gmünd`, `BFA` |
| court | named court incl. abbreviations | `Landesgericht Linz`, `OGH`, `BGer`, `Cour de cassation`, `TJ de Lyon` |
| address | postal address with house number; whole span incl. door, postcode and city when contiguous | `Gumpendorfer Straße 74/3, 1060 Wien`, `12 rue de la Paix, 75002 Paris` |
| street | street or square name without house number | `Mariahilfer Straße` (in "auf der Mariahilfer Straße") |
| location | city, municipality, district, region, country, nationality country ("StA. Syrien") not inside another span | `Linz`, `Tirol`, `Syrien`, `canton de Vaud` |
| date | day-precise date in any spelling | `12.03.2025`, `5. Juli 2024`, `le 3 mars 2023` |
| case_number | case reference of court, authority, police, notary, land register | `3 Ob 123/24k`, `W123 2245678-1/12E`, `VI ZR 123/22`, `4A_123/2024`, `n° 21-12.345` |
| legal_norm | statute citation with §, Art., TP etc. incl. the act abbreviation, and bare names of acts (abbreviated or long); each citation in a chain separately | `§ 879 Abs 3 ABGB`, `Art. 8 EMRK`, `article 1240 du Code civil`, `ABGB`, `DSGVO`, `Code civil` |
| bank_account | IBAN, BIC, account number | `AT48 4734 9698 8861 5213` |
| social_security_number | SV-Nummer, AHV-Nr., NIR, Rentenversicherungsnummer | `5555 220480`, `756.9227.7917.00` |
| tax_id | Steuernummer, UID/USt-IdNr., numéro de TVA | `ATU39286303` |
| company_register_number | FN, HRB/HRA, CHE-UID, SIREN/SIRET, RCS | `FN 531927x`, `HRB 209877`, `CHE-123.456.789` |
| license_plate | vehicle plate | `W-49172L`, `AB-123-CD` |
| land_register_id | EZ, KG number, Grundstücksnummer, Flurstück, Grundbuchblatt, référence cadastrale | `EZ 403`, `KG 01009 Neubau`, `Gst-Nr. 211/3` |
| id_document_number | passport, ID card, driving licence, residence permit numbers | `P1234567` |
| other_identifier | any other personal identifier: customer, policy, member, IFA-Zahl, Anwaltscode, VIN/FIN, booking code, social-media handle | `KH-7731-0045-22`, `@pfoten_uelzen` |
| phone_number | phone or fax | `+43 664 1288 471` |
| email | e-mail address | `kanzlei@huber-law.at` |

Do **not** tag: BGBl./JO references,
RIS Rechtssatz numbers, URLs, amounts, months or years without a day, generic court words
("Erstgericht", "le tribunal") without a place, adjectives ("Wiener").

## Annotation rules

- Forms of address and job or rank titles are outside the span: Herr, Frau, M., Mme, Me, Fa., Hofrat,
  Senatspräsident, GrInsp. Academic degrees are inside: Dr., Mag., DI, Ing., MMag., LL.M., Dr. med.
- A judge or lawyer keeps the role label at every mention in the document (`[[judge|Taufner]]`).
- No nesting: "Kanzlei Dr. Hutterer & Partner Rechtsanwälte GmbH" and "Linz Textil GmbH" are one
  organization span; "Landesgericht Linz" is one court span.
- Chains: `[[legal_norm|§ 879 Abs 3 ABGB]] iVm [[legal_norm|§ 6 Abs 1 Z 1 KSchG]]`. A list or chain inside
  one act stays one span: `§§ 41, 50 ZPO`, `§ 6c iVm § 6b Abs 2 EStG` (same convention as LER).
- Bare act names are legal_norm: `das [[legal_norm|ABGB]]`, `im Vollanwendungsbereich des [[legal_norm|MRG]]`,
  `le [[legal_norm|Code civil]]`, `der [[legal_norm|Datenschutz-Grundverordnung]]`. Generic words ("das Gesetz",
  "la loi") are not. `--strict` flags untagged act names that the document cites elsewhere.
- In a citation of a decision, tag the parts: `[[court|OGH]] [[date|12.03.2024]], [[case_number|5 Ob 87/24m]]`.
- Pseudonymised placeholders are tagged with the label of what they replace (`[[address|*****]]`).
- OCR noise stays inside spans exactly as written (`Hu-\nmer`, `46OO Wels`).
- Every occurrence of a day-precise date is tagged, also the tenth repeat of the same date
  (`--strict` flags untagged dates).
- Articles stay outside spans: `l'[[legal_norm|article 1240 du Code civil]]`, `das [[legal_norm|ABGB]]`.
- Genitive -s stays inside the span (`[[person|Hubers]] Antrag`), as in LER.
- `CHE-123.456.789` is company_register_number; with the suffix `MWST`/`TVA`/`IVA` it is a tax_id.
  `RCS Lyon` without a number is not an identifier (tag only `[[location|Lyon]]`).
- Places in closing lines (`[[location|Wien]], am …`) and firm names in quotes are tagged too.

## Realism

- Authentic structure and register for the doc type and jurisdiction: AT (Kopf, Spruch, Begründung,
  Rechtliche Beurteilung, iVm, idgF), DE (Tenor, Tatbestand, Entscheidungsgründe, i.V.m.),
  CH (Sachverhalt, Erwägungen, Dispositiv; no "ß", write "ss"; "Art. 41 OR"), FR (Faits et procédure,
  Moyens, Motifs, Par ces motifs, PAR CES MOTIFS, "attendu que" only in older style).
- Lengths vary between 300 and 2500 words; some documents should be long.
- Names must be diverse, never the same 20 surnames: mix Austrian/German/Swiss/French with
  Balkan, Turkish, Czech, Polish, Hungarian, Italian, Arabic, Persian, West African, Ukrainian names;
  double-barrelled names, names with particles (von, de, van der), hyphenated first names.
- Hard cases on purpose: names that are also places or words (Frau Wien, Herr Steyr, Mme Paris),
  surname-only coreference, persons in genitive ("Steinbergers Antrag"), long chained citations,
  tables as text, lists of parties, 1 in 10 documents RIS-pseudonymised, 1 in 10 with OCR noise.
- Identifiers with valid check digits: use `python3 -m legalner.fake_ids all` (or `iban AT 3`,
  `svnr`, `fn`, `uid_at`, `ust_idnr_de`, `steuernummer_de`, `rvnr`, `hrb`, `ahv`, `che_uid`, `nir`,
  `siren`, `siret`, `tva_fr`, `be_enterprise`) instead of inventing numbers. `python -m legalner.audit`
  rejects wrong check digits.
- Internal consistency (the pilot audit found ~3 problems per document): dates in order (no statement
  describing later events), amounts that add up, court competence and district matching the places
  (Mödling → LG Wiener Neustadt), OGH senate matching the subject (5 Ob WEG/MRG, 10 Ob family, 3 Ob
  enforcement), ordinary vs. außerordentliche Revision used consistently, current legal forms (BE: SRL, not SPRL),
  no lawyer contact data at the end of judgments, gender of a person consistent across mentions.
- Case numbers carry the year of filing (a 2026 claim is not `7 Ca 1234/25`); DE/CH write `Abs.` and `i.V.m.`,
  AT writes `Abs` and `iVm`; IBANs and social security numbers appear only where the document type would
  contain them (contracts, applications, letters), not in the reasoning of a judgment.
- Real courts, authorities, places and statutes are fine. Persons, companies and case facts must be
  invented; do not reproduce real decisions or real people.
