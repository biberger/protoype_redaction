# Synthetic v7 pilot audit

What: span-by-span audit of 22 documents (2 per document type) from `data/synthetic/raw_v7/` against
`data/synthetic/GENERATION.md` (labels, annotation rules, decisions 1-41; role labels judge/lawyer/person not counted).
By: Sonnet agent. Date: 2026-11-03. Method: every `[[label|surface]]` read in context, plus a script that searched for
untagged repeats of tagged names; errors = wrong label, wrong boundary, tag that should not exist, missed entity.

**15 span errors in 1227 spans = 1.2 %** (0 spurious tags; 6 of the 15 are the asterisk convention, see below;
5 are the bare "Disziplinarrat" question; without those two groups: 4 errors = 0.3 %).

## Error kinds

| kind | n | example |
|---|---|---|
| `*` before a date of birth sits outside the span (decision 33 shows `[[date_of_birth\|*1970]]`; the same batch also writes it inside, e.g. 0121, so the generator is inconsistent) | 6 | 0010 `*[[date_of_birth\|1977-10-25]]` -> `[[date_of_birth\|*1977-10-25]]` |
| missed court: bare "Disziplinarrat" / "Disziplinarrats" of a chamber (decision 31 lists bare "Disziplinarsenat" as court; decision 6 would leave a generic word untagged; ambiguous) | 5 | 0158 "Der Disziplinarrat hat die Anzeige ..." -> `court` |
| missed location: bare municipality in running text | 2 | 0076 "Kaufvertrag Hochneukirchen" -> `location`; 0137 "Mietzins Wohnung Waidhofen" -> `location` |
| missed organization: company with legal form | 1 | 0089 "Die Oesterreicher Immobilien GmbH" untagged |
| wrong label and boundary: list of notary names in a letterhead tagged as one organization (decision 40: one `person` per name) | 1 | 0076 `[[organization\|S E I P E L , E R K I N G E R , E N D L , B I T T E R]]` -> 4 `person` spans |
| wrong label (country/location/organization, date vs date_of_birth, other_identifier kinds, land register keywords, phone extensions, postcode+place, St. places) | 0 | none found |

Decisions 31-41 were applied cleanly: countries, `date_of_birth`, `postcode + place` as `address`, extensions inside phone spans,
`Kd.-Nr.`/`Kl.-Nr.`/`Zeichen`/`FIN`/`Polizzen-Nr.` prefixes outside, one land register span per reference, lists, St. places as
`location`, `BG ...`/`LG für ZRS Wien` as `court`, split values across line breaks. All VINs have 17 characters, all weekdays in the
e-mail threads match the dates, all fee tables add up.

## Per document type

| type | spans | errors | error % | realism |
|---|---|---|---|---|
| anwaltsschreiben | 96 | 1 | 1.0 | Letterhead and closing are credible; body is a collage (Zeugen, SV-Nr., plate, loan, land register in one letter), see below |
| schriftsatz_erv | 130 | 0 | 0.0 | Clear Klage/Einspruch structure with Sachverhalt, Beweis, Anträge; content mildly stuffed |
| kaufvertrag_liegenschaft | 89 | 1 | 1.1 | Right sections (Gegenstand, Kaufpreis, Aufsandung, Treuhand); land register data and courts do not match geographically |
| mietvertrag | 67 | 1 | 1.5 | Too thin and too generic; § structure fine, content contradictory |
| honorarnote | 110 | 1 | 0.9 | Best-looking type: letterhead, Honorarnote number, table, 20 % USt add up; narrative is incoherent |
| email_verlauf | 142 | 4 | 2.8 | Header format and weekdays correct; threads are incoherent and sender domains do not fit the firm |
| firmenbuchauszug | 113 | 1 | 0.9 | Does not look like a Firmenbuch extract at all |
| meldebestaetigung | 88 | 0 | 0.0 | Does not look like a ZMR Meldebestätigung |
| polizeibericht | 108 | 0 | 0.0 | Structure plausible (Zl., Sachverhalt, Beteiligte); clutter of unrelated identifiers |
| verlassenschaft | 99 | 1 | 1.0 | Notary letterhead and GZ plausible; contents are not a Verlassenschaft document |
| obdk_disziplinar | 185 | 5 | 2.7 | Heading "Im Namen der Republik" fine; reasoning does not read like an OBDK decision |
| total | 1227 | 15 | 1.2 | |

Weakest (errors): email_verlauf, then obdk_disziplinar. Strongest: schriftsatz_erv, meldebestaetigung, polizeibericht (0 errors).
Weakest (realism): firmenbuchauszug, meldebestaetigung, verlassenschaft.

## Realism, most unrealistic features (cross-type)

- **Identifier stuffing.** Almost every document contains the same kit: Mitgliedsnummer, Kd.-Nr., Vertragsnummer, FIN, SV-Nr., IBAN,
  Treuhandbuch-Nr., a block of 2-3 land register references, a "Tel. ... DW", a bare "NNNN Ort" address. This is why police reports,
  Firmenbuch extracts, Meldebestätigungen and Honorarnoten all look alike (SV-Nr. and FIN in a Firmenbuch extract; land register in a
  Meldebestätigung and a police report).
- **Injected boilerplate.** "Die Republik Österreich als Beklagte (im Parallelverfahren) ..." appears in 14 of 22 documents,
  including Verlassenschaft, Firmenbuch, Meldebestätigung, Polizeibericht and a Kaufvertrag, where it makes no sense.
- **Recurring entities.** "Eleonore Dr. Schneider" (example of decision 41) in 4 documents (0010, 0071, 0069, 0123);
  `+43 664 1288 471` (spec example) in 0098; "Ihr/Unser Zeichen ... ./. ..." formula in four types.
- **Geography does not match.** Land register places, courts, addresses and phone area codes come from different federal states
  (e.g. 0043: KG Grein, Gnas, Großsteinbach, BG Kirchdorf; 0005: Klage at LG Innsbruck, BG Eisenstadt, Wohnsitz Raaba, Tel. 0662).
- **Personal data does not fit.** SV-Nr. birth date differs from the stated date of birth (0005, 0069); first name and surname
  gender mixed (0059 "Otakar Makarová"); SV-Nr. of a "Mandantin" that is a GmbH (0069).
- **Dates and amounts.** Mostly consistent. Exceptions: 0164 decision of 17.03.2026 says a Gewährleistungsfrist "bis 30.04.2025 läuft";
  0158 Vertragsnummer `LV-2025-...` for a 2023 contract; 0137 rent booked after the death with a date 11.04.2026.

## Per document

Format: file (spans): errors. "ok" = no error found.

- AT_v7_0010_anwaltsschreiben (49): `*[[date_of_birth|1977-10-25]]` should include `*` (decision 33). Rest ok.
- AT_v7_0005_anwaltsschreiben (47): ok. Realism: "KG: KG: 26650 ..." duplicated keyword, SV-Nr. 221185 vs born 1958, 9.800 EUR claim at a Landesgericht.
- AT_v7_0027_schriftsatz_erv (47): ok. Realism: "Einwendungen" instead of "Einspruch gegen den Zahlungsbefehl".
- AT_v7_0021_schriftsatz_erv (83): ok. Realism: BG Döbling for a defendant living in 1180/1090; Zeuge address and SV-free, otherwise good.
- AT_v7_0043_kaufvertrag_liegenschaft (51): `*[[date_of_birth|23.09.1938]]` should include `*`. Realism: seller e-mail at richter.at (buyer firm).
- AT_v7_0042_kaufvertrag_liegenschaft (38): ok. Realism: property in Droß (NÖ) at BG Liesing, Schaden/Fahrzeug paragraph in a land sale.
- AT_v7_0059_mietvertrag (38): `*[[date_of_birth|5. November 1962]]` should include `*`. Realism: "Otakar Makarová", MIETERLISTE/STAMP line.
- AT_v7_0057_mietvertrag (29): ok. Realism: Gerichtsstand "Oberlandesgericht Graz ... sofern die Berufung betroffen ist", SV-Nr. as Anlage.
- AT_v7_0071_honorarnote (57): `*[[date_of_birth|22. Oktober 1974]]` should include `*`. Realism: "Schreibgebühr EUR 35,00 je Seite", Gegenseite revokes the Vollmacht.
- AT_v7_0069_honorarnote (53): ok. Realism: GmbH client "Zu Handen" with an SV-Nr. of a Mandantin, Gutachterin in a fee note.
- AT_v7_0076_email_verlauf (50): letterhead `[[organization|S E I P E L , E R K I N G E R , E N D L , B I T T E R]]` -> four `person` spans
  (decision 40); "Kaufvertrag Hochneukirchen" (Betreff) missed `[[location|Hochneukirchen]]`.
- AT_v7_0089_email_verlauf (92): "Die Oesterreicher Immobilien GmbH" missed `organization`; `*[[date_of_birth|07.11.1972]]` should include `*`.
  Realism: six unrelated client threads in one mail chain.
- AT_v7_0098_firmenbuchauszug (61): ok. Realism: E-Mail-Signatur, SV-Nr., FIN, Treuhandbuch in an extract; no "Stand der Eintragung"-style layout.
- AT_v7_0103_firmenbuchauszug (52): `*[[date_of_birth|1954-04-13]]` should include `*`. Realism: "Ihr Zeichen", Klientennummer, Klage note in an extract.
- AT_v7_0109_meldebestaetigung (56): ok. Realism: six people on one "Meldebestätigung", land register block, "Mitgliedsnummer".
- AT_v7_0116_meldebestaetigung (32): ok. Realism: same; a Polizze number, "Republik Österreich als Beklagte".
- AT_v7_0121_polizeibericht (43): ok (`[[date_of_birth|*28.10.1959]]` is the form shown in decision 33). Realism: land register list and Vers.-Nr. in an Anzeige; plate "SZ-" is not Austrian.
- AT_v7_0123_polizeibericht (65): ok. Realism: Anzeige "zur Kenntnis" of a Landesgericht, contact person with Vertragsnummer; long and detailed, otherwise the best police text.
- AT_v7_0137_verlassenschaft (51): "Mietzins Wohnung Waidhofen" missed `[[location|Waidhofen]]`. Realism: heirs listed with StA, Girokonto in a table.
- AT_v7_0141_verlassenschaft (48): ok. Realism: two deceased, "Republik Österreich als Beklagte" in a Verlassenschaft, heirs without roles.
- AT_v7_0158_obdk_disziplinar (98): 4 x bare "Disziplinarrat/-rats" (Verfahrensverlauf, Berufungsrüge, Beweiswürdigung) missed `court`.
  Realism: parties listed as Klient/Mandantin/Zeugin, no RAO/DSt § cited, Spruch near the end.
- AT_v7_0164_obdk_disziplinar (87): "gegen den Spruch des Disziplinarrats" missed `court`. Realism: decision of 2026 speaks of a deadline "bis 30.04.2025 läuft".
