# Austrian gold set: agent review (first pass)

Date: 2026-10-29. 400 paragraphs from 141 held-out synthetic v3 documents (49 doc types), selected with
`python -m legalner.goldset select` (see `data/gold/at/doc_ids.txt`, excluded from training with
`legalner.build --exclude-docs`). 20 Sonnet reviewer agents checked every span against `GENERATION.md`
(`scripts/gold_review.workflow.js`) and set `review: agent`. **No human has reviewed the set yet**; until then
report gold-set numbers as "agent-reviewed".

Spans (without role duplicates): 5410. Agent corrections: 76 (≈1.4% of spans): 39 added (22 locations,
mostly places in closing lines or before addresses; act names; case numbers), 32 boundary fixes (mostly
`FN` prefix and degree boundaries), 2 relabelled, 1 removed, 2 text artefacts.

## Convention pass (2026-10-29)

The "Gold-set decisions" in `data/synthetic/GENERATION.md` (settled with the project lead) were applied to all 400
paragraphs by 20 Sonnet agents (`scripts/gold_convention.workflow.js`; all paragraphs of a document went to the same
agent, which read the full source document in `data/synthetic/raw_v3` for roles and names; candidate lists from a
pattern scan in `data/gold/at/convention_hints.txt`). Every file now has `review: convention-pass`;
`python -m legalner.goldset export` writes 400 records to `data/canonical/gold_at.jsonl` without warnings.

Net change against the agent-reviewed set: 5,374 tags, 145 removed and 109 added in 95 files; the text of 37
files was edited (decision 13).

| Decision | Change | Count |
|---|---|---|
| 1-3 roles | lawyer -> person for representatives whose profession is never stated in the source document (Bevollmächtigter, "Vertreter", Rechtsvertreter of insurers, tax representatives); judge -> person for signatures under "Für die Richtigkeit der Ausfertigung" (except a signer identified as Rechtspfleger, who stays judge) | 31 + 4 + 1 |
| 4 degrees | degree after the name moved inside the span | 1 |
| 5/6 authorities | bare `BFA` and `Bundesamt für Fremdenwesen und Asyl` tagged; one generic word untagged | 3 |
| 7 places in unit names | `Regionaldirektion [Steiermark/Salzburg]`, `Außenstelle [Graz/Linz]`, `Dienststelle …`, `Werkes Reichersberg`: location removed | 6 |
| 8 date ranges | two date spans merged into one (`[[date|1. September 2025 bis 31. Dezember 2025]]`) or boundary fixed | 25 |
| 9 identifiers | prefixes (SNR, GZ) out of the span; invoice/delivery numbers untagged | 4 |
| 10 norm chains | reviewers merged 20 chains whose citations each name the act; split back to match LER (60 such chains split in LER train, none merged); decision 10 now says so | 0 net |
| 11 act names | `UN-Kaufrecht` tagged | 1 |
| 13 artefacts (text) | one person under two names (e.g. 0300 judge Haid/Sommer, 0371 Perner/Grill, 0464 Kalsdorf/Lederer, 0966 Toth/Kaltenegger); garbled names (0300 "Reich Edler" -> Ernst Reiterer, 0537 "Da D Bahjat" -> Dalia Bahjat, 0072 "Adtrid" -> Astrid, 0360 Cyrillic-Latin mix, 0678 "umaru"); doubled degree (0588 "MBA V***** T*****, MBA"); impossible chronology (Rechtskraft 5 days after a Zahlungsbefehl, signatures after 2026-10-29, contracts describing later events); wrong court (0563 außerordentliche Revision to the VwGH); gender of a lawyer or party made consistent | 40 |

Rules added with this pass: `legalner.tagged` lint no longer flags a place name right after a unit word
(Regionaldirektion, Außenstelle, Dienststelle, Werk, Standort …), per decision 7.

Remaining doubts (not changed, for the human reviewer):
- 0300 p0: "Richterin Edna Haid" (ran the hearing) was merged with the deciding judge Dr. Romi Sommer; revert if a
  handover between two judges was intended.
- 0298 p0, 0132, 0915, 0994 …: degrees written before the name in an unusual form ("MBA Lex Alexander",
  "BSc Mine Schönwiese") stay inside the span; the generator produced them, real documents write them after the name.
- 0662 p1, 0168, 0171: legal inconsistencies in the facts (deadlines, "nicht Folge gegeben" vs "zurückgewiesen") were
  left; they do not affect the tags.
- 0685 p4: "zwischen dem 21. März 2025 und dem 8. Mai 2025" stays two date spans (a range with "und dem" in the middle).
- 0407 p0: the redundant location `Hirschbach` before the address of the same town stays tagged.
- 0893 p1: "am Standort [[location|Flachau]]" stays tagged (descriptive, not a unit name).

The open questions of the first pass below are answered by the decisions; they are kept for the record.

## Human review (first pass, questions now settled)

Files: `data/gold/at/reviewed/*.md`. Correct tags in place, set `review: human` in the header, then run
`python -m legalner.goldset export`. The questions below are what the reviewers were unsure about, grouped by
topic; several are convention questions that should be settled once in `GENERATION.md`.

### officials, clerks, agents: person or judge/lawyer (35)

- synthetic__AT_v3_0011_bescheid_bfa_p0: 'Dr. Della Czech' is a BFA Referentin. I kept her as person, not judge, since she is an official.
- synthetic__AT_v3_0316_klage_p2.md: Loidls is tagged lawyer (a Schreiben to the Beklagter), but the paragraph has no introduction of the person. Please confirm the role from the full document.
- synthetic__AT_v3_0394_exekutionsantrag_p1.md: Hopfenbank-Verbindung is a compound that contains a bank name and was left untagged, while Hopfenbank Retz eGen is an organization. Gerichtsvollzieher Heino Hummel is labelled person, not judge. Please confirm both.
- synthetic__AT_v3_0292_vollmacht_p0.md: MMag. Kunigunde Losert is the Vollmachtnehmerin (agent) but is never called a lawyer, so I kept her as person. Should she be lawyer?
- synthetic__AT_v3_0774_olg_beschluss_p3.md: Ilse Walla signs under 'Für die Richtigkeit der Ausfertigung', which is normally done by court office staff, not a judge. I relabelled judge to person. Is that the intended convention?
- synthetic__AT_v3_0173_berufung_p1.md: the closing signature Roselinde Morgenstern is tagged person. The text calls the appellant 'Berufungswerberin' and names the Hauptmieterin as Muchitsch, so she could be the party's lawyer (lawyer label) or an inconsistent name. I left person.
- synthetic__AT_v3_0736_bescheid_dsb_p1.md: 'Hanna-Lore Oberhumer' (Sachbearbeiterin of the DSB, also signatory) kept as person (official), not judge; confirm.
- synthetic__AT_v3_0360_strafverfuegung_p5.md: the closing signature 'Egnatius Klar' (official, 'Für die Behörde') is tagged person (official). OK?
- synthetic__AT_v3_0190_vollmacht_p2.md: Is 'Bevollmächtigter Zdenko Rennert' (and Ersatzbevollmächtigter Larbi Allewaert) an attorney (lawyer) or a lay representative (person)? The first part of the document is not in this excerpt; left as person.
- synthetic__AT_v3_0915_testament_p1.md: 'Herrn Patek' as Testamentsvollstrecker is tagged lawyer, but the excerpt does not say he is an attorney or notary; person may be correct.
- synthetic__AT_v3_0071_bescheid_bfa_p1.md: 'Sachbearbeiterin Dina Ruprecht' (BFA official) tagged person per the official rule; judge is not appropriate.
- synthetic__AT_v3_0190_vollmacht_p3.md: 'Rennert' is the Bevollmächtigter. The chunk does not show whether he is an attorney (lawyer) or a private agent (person). I left it as person.
- synthetic__AT_v3_0688_bg_beschluss_verlassenschaft_p1.md: Is Verlassenschaftskuratorin Kollanyi correctly labelled lawyer (curators are often lawyers or notaries, but the text does not say so)?
- synthetic__AT_v3_0339_ogh_beschluss_p4.md: Leni Unlue is tagged judge although she appears to act at the Versammlung (a meeting), which is semantically odd. Keep judge, or change to person?
- synthetic__AT_v3_0155_bfg_erkenntnis_p1.md: DI Lawrence Schmied is tagged lawyer because he is the representative who signed the statement, but his profession is not stated. Keep lawyer?
- synthetic__AT_v3_0201_arztbrief_p0.md: Dr. med. Maria Marcelina Arce (admitting physician) was kept as person, since doctors are neither judge nor lawyer.
- synthetic__AT_v3_0277_bescheid_finanzamt_p0.md: Dr. Constantin Kienast (Steuerberater) was kept as person, since Steuerberater is not in the lawyer label definition.
- synthetic__AT_v3_0155_bfg_erkenntnis_p3.md: 'Der Vertreter DI Lawrence Schmied' is tagged lawyer. Is the representative really an attorney, or perhaps a tax adviser or other non-lawyer who should be person?
- synthetic__AT_v3_0662_firmenbuch_beschluss_p2.md: 'Stellungnahme von Lina Capoušek' is tagged lawyer. The paragraph does not say she is counsel. Should it be person? Left unchanged.
- synthetic__AT_v3_0340_vollmacht_p0.md: Ing. Tina Helm, Harmen Schleicher and Dr. Gundhild Riedmann are authorised representatives with no stated profession, so they stay person. Confirm none of them is a lawyer.
- synthetic__AT_v3_0072_bvwg_erkenntnis_p2.md: Roža Raguž is only called 'Vertreter' of the mitbeteiligte Partei; kept as lawyer, but should it be person (non-lawyer representative)?
- synthetic__AT_v3_0340_vollmacht_p1.md: Meir Mahler 'bestätigt die Echtheit der Unterschrift' - possibly a notary/lawyer; kept as person.
- synthetic__AT_v3_0670_testament_p1.md: 'Österreichische Zentrale Testamentsregister' kept as organization (register run by the Notariatskammer); could alternatively be untagged or legal_norm-like; confirm.
- synthetic__AT_v3_0300_bg_beschluss_pflegschaft_p0.md: 'Mag. Berend Schiffer' (Kinderbeistand) and 'Dr. Maia Kalchenko' (psychological expert) are tagged person. Is a Kinderbeistand a court-appointed role that would count as judge or lawyer?
- synthetic__AT_v3_0556_notariatsakt_p9.md: I removed the tag from '31. März' because it has no year. I did not check whether the rule 'day-precise date' was meant to cover recurring annual dates.
- synthetic__AT_v3_0279_versicherungsschreiben_p2.md: 'MMag. Bent Liska' is tagged lawyer, but the paragraph never states his role (could be Rechtsvertreter or the insured's person). Please check against the full document.
- synthetic__AT_v3_0300_bg_beschluss_pflegschaft_p1.md: 'Reich Edler' is tagged judge. It looks like a name inverted or an artefact. Please confirm. 'Schiffer' (Kinderbeistand) kept as person.
- synthetic__AT_v3_0132_mietvertrag_p1.md: 'Falkners' (genitive) tagged person. The paragraph does not show whether Falkner is a Mieter or a lawyer.
- synthetic__AT_v3_0347_lvwg_erkenntnis_p2.md: 'Buess' (bare surname, vertreten durch) kept as lawyer. The attorney role is not confirmed in this paragraph.
- synthetic__AT_v3_0052_bg_beschluss_exekution_p1.md: the Gerichtsvollzieherin 'B***** K*****' is kept as person. Should an enforcement officer be judge-like? The label list does not cover it.
- synthetic__AT_v3_0141_sachverstaendigengutachten_p0.md: lawyer 'Dr. Schahin Jahromi' is described as 'Rechtsanwältin', a first name usually male. Is this a gender inconsistency in the source text? I did not change it.
- synthetic__AT_v3_0077_bfg_erkenntnis_p2.md: the signer of 'Für die Richtigkeit der Ausfertigung' (MMag. Golda Ammann) is tagged judge; this could be a Kanzlei clerk rather than a judge. I left it unchanged.
- synthetic__AT_v3_0678_bfg_erkenntnis_p0.md: 'Dr. med. Placidus Höller' is a Rechtsanwalt with a medical degree. I kept the lawyer label and the degree inside the span.
- synthetic__AT_v3_0537_bvwg_erkenntnis_p3.md: Judge name 'Da D Bahjat' looks like an odd or garbled name. Kept as one judge span.
- synthetic__AT_v3_0141_sachverstaendigengutachten_p9.md: Expert 'DI Gunner Arifaj' is tagged person (court-appointed expert). Not judge or lawyer, so person seems right.

### post-nominal degree (MBA, BSc after the name) (22)

- synthetic__AT_v3_0679_polizeiliche_anzeige_p0: Is the degree 'BSc' used as a prefix inside the person and lawyer spans, as I assumed?
- synthetic__AT_v3_0735_anklageschrift_p0.md: Postnominal degree with comma inside the person span (Nele Löw, MBA; likewise Ricarda Tintner, MBA in 0774) was left as is. Should postnominal degrees stay inside the span?
- synthetic__AT_v3_0090_polizeiliche_anzeige_p1.md and synthetic__AT_v3_0774_olg_beschluss_p1.md: the post-nominal degree 'MBA' is inside the span (Mathilda Salzer, MBA; Ricarda Tintner, MBA). GENERATION.md only gives pre-nominal degrees as examples, so is that boundary right?
- synthetic__AT_v3_0090_polizeiliche_anzeige_p2.md: 'Mathilda Salzer, MBA' has the degree after the name inside the span, and 'BSc Dorthe Keller' has the degree before the name inside the span. Both are consistent with 'degrees inside', left unchanged.
- synthetic__AT_v3_0588_asg_urteil_p2.md: the tag [[person|MBA V***** T*****, MBA]] has MBA both before and after the name, which looks like a generation artefact. Left unchanged. Should it be reduced to one MBA?
- synthetic__AT_v3_0320_bvwg_erkenntnis_p1.md: 'Seilern, MBA' is tagged lawyer although listed among the Beschwerdeführer who attended 'persönlich bzw. vertretungsbefugt'. Is this person a lawyer or a party representative (person)? The degree MBA is inside the span, as for judges like 'Běla Hamáček, MBA'; please confirm that this convention is wanted.
- synthetic__AT_v3_0360_strafverfuegung_p2.md: 'MBA Friedhelm Buchegger' has the degree before the name and is tagged as one person span. Is that the intended handling?
- synthetic__AT_v3_0153_kaufvertrag_kfz_p0.md: 'Vittore Wertheim, MBA' has the degree after the name and inside the span. Is a trailing degree inside the span correct?
- synthetic__AT_v3_0915_testament_p0.md: 'Frau [[person|BSc Mine Schönwiese]]' has the degree before the first name. The degree is inside the span per rule. Is 'BSc' as a prefix intended, or is it a generator artefact?
- synthetic__AT_v3_0371_notariatsakt_p0.md: 'MBA Jodokus Langer' represents the Übernehmer under a Vollmacht; left as person (not stated to be a lawyer).
- synthetic__AT_v3_0107_mietvertrag_p0.md: 'MBA Pavel Červenka' keeps MBA inside the span as an academic degree; confirm that MBA counts as a degree.
- synthetic__AT_v3_0298_sachverstaendigengutachten_p0.md: 'MBA Lex Alexander' is tagged with MBA inside the span. Is MBA an academic degree for this purpose? The spec lists Dr., Mag., DI, Ing., MMag. and LL.M. only.
- synthetic__AT_v3_0426_arbeitsvertrag_p2.md: 'BSc Marge Iroha' is tagged lawyer with BSc inside the span. It is odd for an attorney, but the text says Rechtsanwältin, so it stays. Confirm.
- synthetic__AT_v3_0991_bg_beschluss_verlassenschaft_p0.md: MBA Adrian Hofmann conducts the Todesfallaufnahme (a Gerichtskommissär, typically a notary) but is tagged judge; role label judge vs lawyer unclear.
- synthetic__AT_v3_0991_bg_beschluss_verlassenschaft_p1.md: 'BSc' in '[[person|BSc Rajāʾ Ghezielle]]' kept inside the span as an academic degree, although the rule lists only Dr., Mag., DI, Ing., MMag., LL.M.; confirm.
- synthetic__AT_v3_0132_mietvertrag_p0.md: 'BSc Nicoline Kurth' is tagged lawyer with BSc inside the span. I treated BSc as an academic degree under the rules.
- synthetic__AT_v3_0052_bg_beschluss_exekution_p1.md: is the degree suffix in 'E***** M*****, BSc' meant to sit inside the person span? I left it inside. The first mention of the same person has no BSc.
- synthetic__AT_v3_0132_mietvertrag_p2.md: 'MBA Josephine Zeiner' has the degree as a prefix, which is unusual. I kept it inside the person span as an academic degree.
- synthetic__AT_v3_0168_ogh_urteil_p0.md: 'BSc Wimon Stucky' as Rechtsanwältin is labelled lawyer with the degree inside. I kept this, but BSc for a lawyer is odd.
- synthetic__AT_v3_0464_vfgh_erkenntnis_p0.md: judge 'BSc Aurica Schwab' has the degree inside the span, which matches the rule. Is a Bachelor degree meant to count as an academic degree here?
- synthetic__AT_v3_0678_bfg_erkenntnis_p0.md: 'Valeska Moritz, MBA' has the trailing degree outside the span. Should a trailing degree after a comma be inside? Left unchanged.
- synthetic__AT_v3_0994_bg_beschluss_pflegschaft_p1.md: Degree 'MBA' placed before the name ('MBA Pascale Windisch-Grätz') and 'BSc' before 'Dževdet Šantić' are kept inside the spans per the degrees-inside rule. Is that intended for these unusual prefixed degrees?

### other (19)

- synthetic__AT_v3_0735_anklageschrift_p0.md: OCR noise (Lo1bner, 8O93) is kept inside the spans. The hyphenated line break in Ge-/schäftsführerin is a role word and was left untagged.
- synthetic__AT_v3_0735_anklageschrift_p2.md: 'Staatsanwalt Dr. Ferdinand Lechner' is tagged person because there is no prosecutor label. Confirm this is intended.
- synthetic__AT_v3_0090_polizeiliche_anzeige_p3.md: the sentence 'Der Schaden wird vorläufig Die Anzeige stützt sich ...' is truncated in the source. Text left unchanged.
- synthetic__AT_v3_0681_bg_beschluss_pflegschaft_p2.md: the OCR-noise address '[[address|Hadikgas-\nse 44, 6l67 Neustift im Stubaital]]' was kept as written, per the OCR rule.
- synthetic__AT_v3_0915_testament_p0.md: 'Gemälde "Sommerabend am Traunsee"' leaves Traunsee untagged because it is part of a work title. Confirm.
- Fully tagged and unchanged: nothing else in the 20 files looked missed or mislabelled. 0071_p0 ends at 'II. Beweiswürdigung' and 0190_p0 at '**Vorgeschichte**' (truncated paragraphs), left as is.
- synthetic__AT_v3_0413_bg_urteil_p1.md: Court span 'Bezirksgerichts Feldbach' contains the genitive -s in the middle of the name; confirm this is wanted rather than 'Bezirksgericht'.
- synthetic__AT_v3_0030_grundbuchsauszug_p1.md: Is Vermessungsamtes Zwettl (genitive, authority) an organization, or should it stay untagged?
- Convention: FN with the 'FN' prefix inside the span (per the GENERATION.md example 'FN 531927x'); I changed two files to match, the other files already followed it.
- synthetic__AT_v3_0279_versicherungsschreiben_p0.md: address 'Dorfplatz 9, 2better Pottenste1n' contains the OCR-style typo 'Pottenste1n' kept inside the span, while the body says 'Pottenstein'; confirm that this is intended OCR noise and not a generation error.
- synthetic__AT_v3_0377_versicherungsschreiben_p0.md: the address 'Anna-Bastel-Gasse 3,\n5310 Innerschwand am Mondsee' spans a line break. I kept it as one address span; it passed --strict. Is that the intended handling?
- synthetic__AT_v3_0463_olg_urteil_p0.md: 'Landesgericht St. Pölten' stays one court span (case form 'des Landesgericht' is ungrammatical but the text is outside the tags).
- synthetic__AT_v3_0992_gesellschaftsvertrag_p1.md: 'Breit Instal1ations e.U.' contains an OCR-like digit. I kept it inside the span as written. Please confirm it is intended noise.
- Strict validator run produced no errors or warnings for my 20 files. The mv to reviewed/ and the 'review: agent' header were applied to all 20.
- Not strictly mine: the git diff reports 320 files deleted, because other reviewers are moving files out of pending. The validator run covers the whole reviewed directory (360 documents) with no errors or warnings.
- synthetic__AT_v3_0464_vfgh_erkenntnis_p0.md: the Mitbeteiligte is 'Ruperta Kalsdorf', but a later sentence says '[[person|Lederer]] bestätigte diese Angaben...'. The surname is inconsistent. I left the tag and text as they are. Should the text be fixed?
- synthetic__AT_v3_0563_lvwg_erkenntnis_p6.md: the text says 'außerordentliche Revision ... beim Verfassungsgerichtshof'. The court tag is right, but the content is odd. Should the text be fixed?
- synthetic__AT_v3_0678_bfg_erkenntnis_p0.md: the address 'Rudolf-Biebl-Straße 15/16,\n5164 Seeham' contains a line break inside the span. I kept it as OCR-style noise.
- synthetic__AT_v3_0060_anklageschrift_p0.md: the bare 'Martynez' preceded by 'Dr. med.' now takes the degree inside the span. Please confirm this convention for bare surnames with a degree.

### own file/reference numbers: case_number vs other_identifier (10)

- synthetic__AT_v3_0171_protokoll_tagsatzung_p3: Is 'RE 2025/0712' (Frachtbrief reference) an other_identifier? Left untagged.
- synthetic__AT_v3_0394_exekutionsantrag_p0: 'GF-2026-0417' is the party's own file number, tagged other_identifier. Should it be case_number?
- synthetic__AT_v3_0893_revision_p0.md: IR-2026/014 (internal audit report number) is tagged other_identifier. Is that right, or should it stay untagged?
- synthetic__AT_v3_0187_bg_beschluss_verlassenschaft_p4.md: 'Geschäftszahl 2 A' is a partial case reference. I did not tag it. Is that right?
- synthetic__AT_v3_0293_protokoll_tagsatzung_p1.md: Delivery-note numbers 'LS-2025-0113' and similar in the table are not tagged. Should they be other_identifier?
- synthetic__AT_v3_0190_vollmacht_p2.md: 'Versicherungsnummer 7686 231007' is formatted like an SV number but is a policy number; relabelled to other_identifier.
- synthetic__AT_v3_0128_versicherungsschreiben_p0.md: Whether the 'SNR' prefix belongs inside the other_identifier span for 'SNR 2026-0418-7731' (left as is).
- synthetic__AT_v3_0076_vfgh_erkenntnis_p0.md: 'Vizepräsident' is unnamed, so nothing was tagged. 'LVwG-S-1123/2025' kept as one case_number.
- General: for 'GZ' / 'Zl.' prefixes I followed the corpus convention of leaving them outside the case_number span. I changed 0168 to match.
- synthetic__AT_v3_0171_protokoll_tagsatzung_p2.md: Is the invoice/position reference 'RE 2025/0712' an other_identifier? Left untagged because it is neither a case reference nor a personal identifier.

### norm chains and act names (10)

- synthetic__AT_v3_0479_revision_p1.md: The chain '§ 33 Abs 1 iVm § 35 Abs 1 ASVG' is kept as one span (same act), followed by a separate '§ 43 Abs 1 ASVG'. Please confirm this reading of the chain rule.
- synthetic__AT_v3_0962_bescheid_magistrat_p1.md: the chain '§ 19 Abs 2 iVm § 20 Abs 1 NÖ BO 2014' is one span (same act). Is that the right reading of the chain rule?
- synthetic__AT_v3_0792_berufung_p2.md, synthetic__AT_v3_0915_testament_p0.md: chains like '§ 922 Abs 1 iVm § 932 Abs 4 iVm § 1167 ABGB' and '§ 553 iVm § 577 Abs 1 ABGB iVm § 578 ABGB' are one span each (act named only once). Left as is per the 'same convention as LER' rule; should they be split per paragraph?
- synthetic__AT_v3_0296_arbeitsvertrag_p4.md: is 'UN-Kaufrecht' (CISG) a bare act name that counts as legal_norm? I tagged it.
- synthetic__AT_v3_0553_polizeiliche_anzeige_p0.md: '§ 146 iVm § 147 Abs 3 StGB' is kept as one span because it is one act. Confirm this is intended.
- synthetic__AT_v3_0201_arztbrief_p2.md: patient appears as Werndl and Spautz (inconsistent names, apparently a generation artefact); both left tagged as person.
- synthetic__AT_v3_0375_bescheid_finanzamt_p1.md: Scheidl is tagged person and appears unrelated to the other named persons (generation artefact); left as is.
- synthetic__AT_v3_0077_bfg_erkenntnis_p1.md: the chain was split into three legal_norm spans (the GENERATION.md chain rule). Should the second and third citations keep their own 'EStG' suffix when the act repeats? I kept it.
- synthetic__AT_v3_0464_vfgh_erkenntnis_p0.md: '§ 14 Abs 2' has no act name and is tagged as legal_norm. Is that right?
- synthetic__AT_v3_0992_gesellschaftsvertrag_p3.md: the contract section headings '§ 10' and '§ 11' are not tagged because they cite no act. Is that correct?

### organization subunits, generic authority words, compounds (7)

- synthetic__AT_v3_0011_bescheid_bfa_p0: Is 'Regionaldirektion Steiermark' an organization subunit where Steiermark should stay untagged, or a location? I tagged Steiermark as location.
- synthetic__AT_v3_0637_vfgh_erkenntnis_p1.md: 'des Finanzamtes' has no place name, so I left it untagged as a generic authority word. Correct?
- synthetic__AT_v3_0735_anklageschrift_p1.md and synthetic__AT_v3_0679_polizeiliche_anzeige_p4.md: 'der Bank' and 'Kontenöffnung' are left untagged because they are generic. Correct?
- synthetic__AT_v3_0320_bvwg_erkenntnis_p1.md: bare names of the Haftung norms are fine, but 'Finanzamt Wiener Neustadt' is tagged organization (authority); confirm this is not meant as a court-like entity.
- synthetic__AT_v3_0834_bescheid_bfa_p0.md: Is 'Steiermark' in 'Regionaldirektion Steiermark' a separate location, or part of the unit name and left untagged? I left it untagged.
- General: 'Berufungsvertretung' and 'Rechtsvertretung' are generic role words and were left untagged. In 0141 the unnamed Sachverständiger is not tagged.
- synthetic__AT_v3_0577_lvwg_erkenntnis_p2.md: 'Landesverwaltungsgericht' appears without a place and is left untagged per the generic-court rule.

### abbreviation in parentheses after the full name (7)

- synthetic__AT_v3_0011_bescheid_bfa_p0: I split '(BFA)' into its own organization span. Should the long form and the abbreviation be one span or two?
- synthetic__AT_v3_0866_anwaltsschreiben_p2.md: BH Weiz is tagged organization (Bezirkshauptmannschaft abbreviation) and Bezirksgericht Weiz as court. Please confirm.
- synthetic__AT_v3_0090_polizeiliche_anzeige_p3.md: I split the parenthetical abbreviation 'Landespolizeidirektion Niederösterreich (LPD NÖ)' into two organization spans, as the other files do for AMS and FA. Is a single span preferred?
- synthetic__AT_v3_0320_bvwg_erkenntnis_p5.md and 0103_ogh_beschluss_p2.md: 'Verwaltungsgerichtshofes' and 'Obersten Gerichtshof' are tagged as court (inflected forms, no abbreviation). I assumed this is intended.
- synthetic__AT_v3_0072_bvwg_erkenntnis_p1.md: I tagged 'Güterbeförderungsgesetz' (a long act name, no abbreviation) as legal_norm per the bare-act-names rule. Confirm that long act names without a citation also count.
- synthetic__AT_v3_0804_email_kanzlei_p1.md: 'das [[organization|BH]]' is tagged as organization (Bezirkshauptmannschaft abbreviation, as BFA); confirm that a bare abbreviation without place is wanted. Also the address span contains a line break (Anemonenweg 32/24,\n2432 Schwadorf), kept as is.
- synthetic__AT_v3_0804_email_kanzlei_p2.md: bare 'BH' is tagged organization with no place name. Should a bare authority abbreviation count as an entity, or is it generic like 'Erstgericht'?

### date ranges and partial dates (6)

- synthetic__AT_v3_0626_asg_urteil_p7: 'vom 1. bis 15. Juni 2025' has only 15. Juni 2025 tagged. Should '1.' count as a day-precise date or the whole range be one date?
- synthetic__AT_v3_0681_bg_beschluss_pflegschaft_p3.md: date 'am 9. Ju1i 2026' contains OCR noise (1 for l) and is kept as a date span as written; confirm.
- synthetic__AT_v3_0070_arbeitsvertrag_p2.md: The signing date '18. November 2026' is after today (2026-10-29). I left it unchanged. Is that acceptable for the gold set?
- synthetic__AT_v3_0548_datenschutzauskunft_p2.md: is a bare 'Datenschutzbehörde' (no place, 'bei der Datenschutzbehörde eingebracht') an organization? I tagged it, consistent with the tagged 'Datenschutzbehörde' in 0975_p0 and 'DSB' in 0024_p1.
- synthetic__AT_v3_0107_mietvertrag_p1.md: is '1. März' (day and month, no year) a day-precise date to tag? I left it tagged as date.
- synthetic__AT_v3_0301_bg_beschluss_exekution_p1.md: the Zahlungsbefehl is dated 9 March 2026 and became final on 14 March 2026. That is not a tagging issue, but the dates look inconsistent. I changed nothing.

### places: location vs part of a name (5)

- synthetic__AT_v3_0407_grundbuchsauszug_p0.md: the bare 'Hirschbach,' in front of the address 'Krankenhausstraße 5, 3942 Hirschbach' is now a separate location. Should it instead be treated as redundant or part of the address?
- synthetic__AT_v3_0834_bescheid_bfa_p0.md: 'Hartberg' in 'im Bezirk Hartberg' is now a location (district). Is the bare place name tagged even when 'Bezirk' stays outside?
- synthetic__AT_v3_0438_firmenbuchauszug_p0.md: 'Wirtschaftskammer' (no place) newly tagged organization; should a bare chamber name be tagged?
- synthetic__AT_v3_0622_dienstzeugnis_p2.md: is 'Werkes Reichersberg' (a plant named after a municipality) a location, as I tagged it, or should it stay untagged?
- synthetic__AT_v3_0537_bvwg_erkenntnis_p1.md: I tagged 'Republik Moldau' as location in full, as in 'Staatsangehörige der Republik Moldau'. Should the span be only 'Moldau' with 'Republik' outside?
