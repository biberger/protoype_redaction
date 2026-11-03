# Synthetic v7 full-sample audit

What: span-by-span audit of 30 documents (9 types, 2-6 per type) from `data/synthetic/raw_v7/` against
`data/synthetic/GENERATION.md` (labels, annotation rules, decisions 1-41; role labels judge/lawyer/person not counted;
bare "Disziplinarrat" untagged, "*" outside `date_of_birth`, generic role words untagged, geography and document length not counted).
By: Sonnet agent. Date: 2026-11-03. Method: every `[[label|surface]]` read in context with the untagged text around it, plus scripts
that searched for untagged repeats of tagged names and for untagged legal-form words; errors = wrong label, wrong boundary,
spurious tag, missed entity.

**15 span errors in 1648 spans = 0.9 %** (5 missed entities, 5 boundary errors, 2 wrong label+boundary, 3 spurious tags).
The pilot settled conventions (asterisk, bare Disziplinarrat) produced no errors this time; no wrong labels in the narrow sense
(date vs date_of_birth, identifier kinds, land register keywords, phone extensions, postcode+place, St. places) were found.

## Error kinds

| kind | n | example |
|---|---|---|
| missed entity (organization, legal_norm, location, country) | 5 | 0451 "Donaulandische Versicherungs AG" (addressee) untagged; 0251 "nach dem Gerichtsgebührengesetz" untagged `legal_norm`; 0586 „Kaufpreis Weitensfeld“ untagged `location`; 0728 "vertreten durch die Finanzprokuratur" untagged `organization` (decision 6, unique federal body); 0728 "Schreiben der Republik" untagged although "Die [[country\|Republik]]" is tagged two lines above |
| wrong boundary | 5 | 0251 and 0250 `[[tax_id\|UID ATU73567357]]` -> prefix "UID" outside (every other document writes `UID: [[tax_id\|ATU...]]`); 0077 "Die [[organization\|Griesser]] Handels GmbH" -> whole name; 0574 `vom [[date\|12. Februar 2025]] bis zum [[date\|30. Juni 2025]]` and 0728 `von [[date\|9. Juli 2025]] bis [[date\|14. August 2025]]` -> one date span each (decisions 8, 23; 0550 does it correctly) |
| wrong label and boundary | 2 | letterhead list of surnames tagged as one organization: 0775 `[[organization\|Z E H E T G R U B E R , K E R B E R , R E I T H O F E R , V O N S T A R H E M B E R G]]`, 0327 `[[organization\|S C H I N A G L , F R I S C H M U T H , P L A S C H G]]` -> one `person` per name (decision 40; same as the pilot's 0076) |
| spurious tag | 3 | 0250 yearless recurring dates `bis zum [[date\|30. April]] des Folgejahres` and `jährlich zum [[date\|1. Jänner]]` (decision 8: untagged); 0103 `Sachverständigen der [[organization\|Landespolizeidirektion]]` (generic, no place; decision 6) |

Everything else held: all `*`/`geb.`/`GEB:`/`Geburtsdatum` cues give `date_of_birth` with the asterisk outside, `StA.` countries as `country`,
postcode+place as `address`, extensions inside phone spans, `Kd.-Nr.`/`Klienten-Nr.`/`Polizzen-Nr.`/`Treuhandschaft Nr.` prefixes outside,
VINs 17 characters, fee tables and Treuhand tables add up (0845: 1.800 + 20 % + 186 = 2.346; 0147: 3.015,40 + 603,08 = 3.618,48), weekdays in the
e-mail threads match the dates, one land register span per reference, `Disziplinarrat der Rechtsanwaltskammer ...` as `court`.

## Per document type

| type | docs | spans | errors | error % | realism |
|---|---|---|---|---|---|
| obdk_disziplinar | 6 | 326 | 1 | 0.3 | Heading, Senat list, Spruch, Begründung, Strafbemessung look like a Disziplinarerkenntnis; Treuhand tables are plausible, but several mix up the stages (Disziplinarrat decision citing "OBDK" reasoning, §§ of RAO/RL-BA cited generically, "Im Namen der Republik" on an Disziplinarrat decision, Beschuldigte/Beschuldigter switching in 0776) |
| anwaltsschreiben | 4 | 174 | 1 | 0.6 | Letterhead block and closing credible; insurance/claims letters read like real Schadensersatz letters but carry extra Zeugen with citizenship and birth dates |
| email_verlauf | 4 | 296 | 2 | 0.7 | Header format, weekdays and quoting credible; threads partly incoherent (0077 mixes three parties; letterhead after the last mail) |
| kaufvertrag_liegenschaft | 3 | 161 | 3 | 1.9 | Sections right (Kaufgegenstand, Kaufpreis, Treuhand, Aufsandung); 0251 pads with §§ 9-15 and a "Beteiligte Personen" register extract that no contract has; land register data do not match court/place |
| schriftsatz_erv | 3 | 156 | 4 | 2.6 | Clear Klage/Klagebeantwortung structure; Nebenintervenient "Land Niederösterreich" and "Republik Österreich" as Nebenbeteiligte are legally odd; 0327 claims 8.420 EUR at a Bezirksgericht with sums that do not add up (6.420 shown as "Gesamt") |
| honorarnote | 2 | 107 | 0 | 0.0 | Best-looking type: letterhead, running Honorarnote number, Leistungstabelle that adds up, USt; 0845 has a duplicated sentence |
| polizeibericht | 2 | 129 | 1 | 0.8 | Plausible Anzeige structure with Beteiligte table and Feststellungen; too long and detailed, odd items (Bundesstraße, German-looking plate F-BH 43, Schadennummer in a police report) |
| verlassenschaft | 3 | 193 | 0 | 0.0 | Notary letterhead and GZ plausible, but the text reads as a mix of Abhandlungsprotokoll and Mitteilung; dates inconsistent (0997: 2019 case with 2026 entries) |
| mietvertrag | 3 | 106 | 3 | 2.8 | § structure fine and compact (0310, 1005 good); 0250 has a chain of "IV. a-i" sub-paragraphs and a Bürge as "Mitmieter", mixing Wohnung/Geschäftsraum |
| total | 30 | 1648 | 15 | 0.9 | |

Weakest (errors): mietvertrag (2.8 %), schriftsatz_erv (2.6 %), kaufvertrag_liegenschaft (1.9 %). Strongest: honorarnote and
verlassenschaft (0 errors), obdk_disziplinar (0.3 %). Weakest (realism): verlassenschaft and polizeibericht (very long, incoherent
filler); strongest: honorarnote.

## Systematic issues

1. **Letterhead firm names with the legal form on the line above.** `Rechtsanwälte OG` / `[[organization|Mach, Röck, Czeike]]` (0824, 1070, 0451, 0923,
   0251, 0250, 0147, 0586) tags only the surname list, not the legal form, and 1020/1084 tag the same kind of list as `person` one by one. Only the
   two spaced-out letterheads were counted as errors here (0327, 0775); if the project lead decides that the unspaced lists must be `person` per
   name (decision 40) or that the legal form belongs in the organization span, about 20 more spans in this sample change. Letterhead convention
   should be fixed in the generator (one rule for all).
2. **`UID` prefix inside `tax_id`** in two documents (0251, 0250) while the normal form is `UID: [[tax_id|...]]`; a generator variant without a colon.
3. **Date ranges with `von ... bis` / `vom ... bis zum`** are tagged as two dates in 0574 and 0728 but merged in 0550; no rule applied consistently.
4. **Yearless recurring dates** tagged in 0250 but not in 1005, which has the same wording.
5. **Realism**: identifier stuffing (Kd.-Nr., Vertragsnummer, Treuhand number in every type), the "Republik Österreich / Land Niederösterreich als Nebenintervenient"
   formula in schriftsatz_erv, anwaltsschreiben and kaufvertrag, and appended filler paragraphs after the closing (0147, 0845, 0550, 0586) repeat across the sample.

## Per document

Format: file (spans): errors. "ok" = none found.

- 0970_obdk (56): ok. 0776_obdk (45): ok. 0574_obdk (68): `vom [[date]] bis zum [[date]]` should be one span. 0682_obdk (44): ok. 0550_obdk (62): ok. 0350_obdk (51): ok.
- 0876_anwalt (48): ok. 1070_anwalt (41): ok. 0451_anwalt (41): "Donaulandische Versicherungs AG" missed. 0159_anwalt (44): ok.
- 0077_email (75): "Griesser Handels GmbH" split. 0508_email (75): ok. 0775_email (70): spaced letterhead list tagged as organization. 0824_email (76): ok.
- 0251_kauf (71): `UID` prefix inside tax_id; "Gerichtsgebührengesetz" missed. 1020_kauf (50): ok. 0586_kauf (40): "Kaufpreis Weitensfeld" missed location.
- 0923_schriftsatz (52): ok. 0327_schriftsatz (48): spaced letterhead list tagged as organization. 0728_schriftsatz (56): date range split; "Schreiben der Republik" untagged; "Finanzprokuratur" missed.
- 0845_honorarnote (50): ok. 0147_honorarnote (57): ok.
- 0103_polizei (67): bare "Landespolizeidirektion" tagged. 0262_polizei (62): ok.
- 1014_verlass (60): ok. 0997_verlass (61): ok. 1084_verlass (72): ok.
- 0310_miet (39): ok. 0250_miet (44): `UID` prefix inside tax_id; two yearless dates tagged. 1005_miet (23): ok.
