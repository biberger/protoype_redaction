# RIS rule annotation: audit

## Update: 1,353 decisions (2026-10-29)

913 more decisions were fetched (`search --bundesland` for LVwG, 2020-2026 spread over years): LVwG all nine states
(648 decisions in total), LG and OLG (Justiz now 545), and converted with all chunks (31,139 chunks; BVwG country
reports are balanced in `legalner.build` with `--cap`/`--max-per-doc`). Rule changes for the new data:
VwGH bracket placeholders (`Herrn Mag. [B]`), LVwG Tirol letter-coded towns (`Adresse 2, ***** Y`, `KG ***** Z Stadt`),
VwG Wien initial streets (`C.-platz in Wien`, `Wien, G.-Park, Tür ...`), Burgenland descriptor placeholders
(`[Vertreter 1]`, `[KG]`, `[Klinik]`), `p.A.` addresses, the Kärnten judge's redacted post-nominal degree, redacted amounts
(`€ ***`, not an entity), quoted omissions (`…`) no longer taken for placeholders, an offset bug with three or more bare
address placeholders in a row (decisions with drifting spans are now skipped, none at present), and an attorney who is
a party (`Disziplinarsache gegen xxx, Rechtsanwalt`) is `person`.

Unclassified placeholders: 7.9 % of chunks flagged `uncovered` (before the new rules 10.5 %). By court: Justiz 5.7 %,
BVwG 6.3 %, VfGH 1.8 %, VwGH 0 %, LVwG OÖ 0.4 %, Wien 0.1 %, Stmk 3.8 %, Vbg 5.5 %, Tirol 6.3 %, Sbg 6.5 %, NÖ 12.2 %,
Burgenland 15.4 %, **Kärnten 30.4 %** (redacts nearly everything, including project and company names in quotes; those
chunks still teach court and case_number).

### Audit of 10 new decisions

Sample (seed 2026): 6 LVwG (NÖ, Kärnten, Steiermark, Salzburg, Wien, Vorarlberg), 2 LG Eisenstadt, 2 OLG. First
≈2,500 characters of each, inline-tagged, read by Sonnet agents (`scripts/ris_audit.workflow.js`, labels person, address,
date, case_number, court; roles per the gold-set decisions).

| Label | Mentions | Misses before the fixes | Fixed |
|---|---|---|---|
| person | 38 | 13 (34 %): 8 judges written with degrees without dot or space (`Mag Rak`, `Dr.Bott`, `Maga.Fabsits`, `Mag Jarec LLM`), list continuation after "als Vorsitzenden sowie", "Fürst als Einzelrichterin", 1 role (LVwG "sein Mitglied Mag. Pathy" -> judge), 2 pseudonyms in odd styles (`A, geboren am`, `p*Fauland`), 1 surname in clear | 11 of 13 |
| address | 8 | 0 | — |
| date | 71 | 0 missed; 18 ranges split in two spans | ranges merged (decision 8), also in synthetic parsing |
| case_number | 15 | 0 | — |
| court | 21 | 0 | — |

The person miss rate in this sample is dominated by two LG Eisenstadt and OLG Graz Kopf styles (degrees without dots);
after the fixes, the remaining misses are 2 of 38 (5 %). Regression tests: `test_ris_kopf_degrees_without_dots`,
`test_ris_vwgh_bracket_placeholders`, `test_ris_lvwg_tirol_letter_coded_towns`, `test_ris_vwg_wien_initial_streets`,
`test_ris_placeholder_lists_keep_offsets`.

## First audit (440 decisions)

Source: `legalner/sources/ris.py` on 440 live decisions (`data/ris/index.jsonl`, 2022 onwards):
OGH 120, OLG 60, LG 50 (Justiz), VwGH 60, VfGH 40, BVwG 60, LVwG 50 (all nine Länder, mostly Tirol/NÖ).

## Method

1. **Sample A** (seed 99, 4 decisions per application = 20 decisions): read the first 2,500
   characters of each converted decision (Kopf + start of the reasons, where most PII is) with
   the rule labels inlined, and listed every person, address, date, case-number and court mention
   the rules missed or cut wrongly. Counted *before* the last round of fixes, so these are the
   honest numbers for unseen text.
2. **Sample B** (seed 2024, 2 Justiz + 2 LVwG, another 4 decisions), read the same way after the
   first round of fixes, to check the fixes did not just fit sample A.
3. **Detectors over all 440 decisions** (after all fixes): untagged strings that look like a
   label: degree + name (`Dr. X`), named courts, `d.m.yyyy` / `d. Monat yyyy`, Gattungszeichen
   case numbers. These find only misses of a shape the rules could know; they cannot see names
   written in clear without a degree.

"Missed" includes boundary errors (span cut or over-extended). Mentions are counted per
occurrence; role labels (`judge`, `lawyer`) are counted inside `person`, and role errors are
listed separately.

## Miss rates

| Label | Sample A (pre-fix) | Sample B | Detector, all 440 (post-fix) |
|---|---|---|---|
| person | 4 / 84 = **4.8 %** | 2 / 22 = 9 % | 11 / 1,724 degree+name untagged = 0.6 % (10 in BVwG) |
| ├ judge role | 2 judges missed (of ≈ 30) | 1 missed (of 8) | — |
| └ lawyer role | 1 missed, 1 false (law firm) (of ≈ 16) | 1 missed (of 2) | — |
| address | 2 / 24 = **8.3 %** (+1 false) | 2 / 6 boundary errors | — |
| date | 2 / 96 = **2.1 %** | 0 / 14 | ≈ 0 (139 untagged hits are BVwG "Position 02.05.07" and similar, correctly untagged) |
| case_number | 2 / 29 = **6.9 %** | 0 / 6 | 0 / 2,809 |
| court | 3 / 62 = **4.8 %** | 0 / 11 | ≈ 0 (76 hits are statute names such as "Verwaltungsgerichtshofgesetz", correctly untagged) |

Per application (sample A): BVwG and VfGH had no misses in the audited windows; most misses
were in Justiz Kopf lists and in the Verwaltungsgericht Wien decision, which uses a placeholder
style ("Frau A. B.", "C.-platz", "Zl. ...") seen in no other court.

## Misses found (sample A and B) and what was done

| Decision | Miss | Fix |
|---|---|---|
| OLG Wien 13 R 175/25p | judges "als Vorsitzenden sowie Mag. Wieser und Mag. Wessely" (no role word) | `JUDGE_INTRO` accepts "als Vorsitzende(n) sowie/und" + degree |
| OLG Wien 13 R 175/25p | court "Landesgerichtes für ZRS Wien" | `COURT_RE` |
| OGH 3 Ob 141/26w | court "Landesgerichts St. Pölten" cut at "St" | `COURT_RE` allows "St." |
| OGH 1 Nc 37/24t | date "v 1.10.24" (two-digit year) | two-digit years after "v/vom/am" |
| OLG Wien 13 R 175/25p | case number "… 336/20t-35": redacted GZ filled, "-35" outside the span | not fixed (boundary) |
| VwGH 2026/15/0151 | person "Herr Mag. [B]" (bracket style) | not fixed (rare) |
| VwGH 2023/06/0216 | false lawyer "SHMP Schwartz Huber-Medek Pallitsch" (firm before "Rechtsanwälte GmbH") | names followed by "Rechtsanwälte/Partner + legal form" are skipped |
| VwGH 2023/16/0103 | court over-extended "Landesgerichtes Klagenfurt im Grundverfahren" | "im/am … verfahren" excluded |
| VwG Wien VGW-101/070/875/2026 | person "Frau A. B.", date "geboren am ...", case "Zl. ...", addresses "C.-platz in Wien", "Wien, G.-Park" | "..." is a placeholder (LVwG), dotted initials are persons; the two addresses are not fixed |
| LVwG NÖ AV-127/002-2022 | attorney written as placeholder ("***, Rechtsanwalt in ***") labelled person only | placeholder followed/preceded by "Rechtsanwalt/Verteidiger" is `lawyer` |
| LVwG Kärnten 2638/2023 | "Richterin xxx, xxx": second placeholder labelled address | address-after-party rule no longer applies after a judge |
| OLG Wien 17 Bs 277/23v (B) | judge "den Richter Ing.Mag. Kaml" (degrees without space) | degree list |
| OLG Wien 17 Bs 277/23v (B) | "Die über * verhängte Untersuchungshaft" filled as a place | "über" removed from location cues |
| LVwG Tirol 2026/33/0980 (B) | "Frau Rechtsanwältin AA" person only | role cue before a placeholder |
| LVwG Tirol 2026/33/0980 (B) | address spans leave the town code ("…, Hohenbrugg Y") | not fixed (boundary) |

Issues found during the 30-decision inspection (step 2, before this audit) are in the commit
message of `RIS: rules checked on real decisions`: metadata blocks and screen-reader duplicates in
the text, every court's placeholder style, BVwG judges in capitals, lawyer lists, authority file
numbers, addresses in clear, RIS-Justiz `RS…` numbers (now untagged, as in the synthetic data).

## Unclassified placeholders

A placeholder that no rule can classify ("(auch XXXX)", "Nutzer „*“", "für die Prüfung des
Antrags XXXX zuständig") is filled with a neutral surname and its chunk gets
`meta.uncovered = [person, judge, lawyer, address, date, …]`; `build.query_labels` drops those
labels for that record. Over the 440 decisions: 755 such placeholders, 329 of 6,105 chunks
(5.4 %) flagged (BVwG 156, LVwG 98, Justiz 70, VfGH 5, VwGH 0). Those chunks still teach
`court` and `case_number`.

## Coverage decision

Person (≈ 5 % misses before the fixes, mostly the role-word gaps now fixed) and court (≈ 5 %,
boundary cases) are good enough to stay covered. `schema.SOURCES["ris"].coverage` is unchanged:
`person, judge, lawyer, address, date, case_number, court`. Known weak spots, all in LVwG:
Verwaltungsgericht Wien's "C.-platz" style and Tirol's letter-coded towns, which cut address
spans. Revisit if a larger LVwG share is fetched. Not covered and not measured: organization,
location, street, land_register_id, company_register_number, license_plate. The rules fill and
label them, but no rule finds the ones written in clear.

What the audit cannot see: names written in clear without a degree, e.g. a witness or official
the court did not pseudonymise. None turned up in the 24 decisions read; RIS pseudonymises
parties and witnesses, and officials almost always carry a degree or title.

## Reproduce

```
python -m legalner.sources.ris convert data/ris/index.jsonl --cache data/ris/raw -o data/canonical/ris.jsonl
```

The inspection scripts (inline-tagged views, residue/unknown contexts, detectors) were ad hoc and
are not in the repository. The detector patterns are listed in the Method section above.
