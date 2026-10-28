# Synthetische Rechtsdokumente (AT/DE) mit NER-Goldannotationen

Vollständig fiktive deutschsprachige Rechtsdokumente als Trainings-/Testdaten für ein
PII-/Legal-NER-Redaktionsmodell. 40 Dokumente (30 AT, 10 DE). Personen, Unternehmen,
Kennnummern und Sachverhalte sind erfunden; reale Gerichte, Behörden und Ortsnamen
werden verwendet.

```
raw/*.md            v1: 40 Dokumente mit Inline-Tags [[LABEL|Oberflächentext]] (alte 10 Labels, s. u.)
raw_v2/<batch>/*.md v2: Dokumente im kanonischen Schema, Spezifikation in GENERATION.md
```

## Neu erzeugen

Der Parser liegt im Paket `legalner` (Repo-Root) und bildet v1-Labels auf das kanonische Schema
(`legalner/schema.py`) ab; KENNNUMMER/KONTAKT werden per Muster und Kontext in feine Labels
(bank_account, tax_id, …) aufgeteilt.

```
python3 -m legalner.tagged data/synthetic/raw    -o data/canonical/synthetic_v1.jsonl --source synthetic_v1 --strict
python3 -m legalner.tagged data/synthetic/raw_v2 -o data/canonical/synthetic.jsonl    --source synthetic    --strict
```

Der Parser bricht bei fehlerhaften Tags (unbekanntes Label, `[[`/`]]`-Reste, Leerzeichen
am Span-Rand) ab und prüft `text[start:end] == surface` für jeden Span. Chunks entstehen durch
Aufteilen an Leerzeilen (≤ 1500 Zeichen); überlange Absätze werden an Zeilenumbrüchen außerhalb
von Entitäten geteilt. Der Lint warnt vor ungetaggten Vorkommen bereits getaggter Strings, von
Nachnamen getaggter Personen und häufiger Städtenamen.

## Labels (v1)

| Label | Definition |
|---|---|
| PERSON | Natürliche Person (Partei, Richter:in, Anwält:in, Zeug:in, Notar:in …) inkl. akademischer Grade (Dr., Mag., DI, Ing., Bmstr., LL.M., BSc); auch Nachname/Vorname allein und RIS-Platzhalter (`A*****`, `Mag. B***** C*****`, VwGH-Initialen `M K`). |
| ORGANISATION | Unternehmen, Vereine, Kanzleien, Banken, Behörden und Gebietskörperschaften als Rechtsträger (BH, Magistrat, BFA, Finanzamt, Polizeiinspektion, Staatsanwaltschaft, „Land Steiermark“) – keine Gerichte. |
| GERICHT | Konkret benannte Gerichte inkl. Abkürzungen (OGH, VwGH, BVwG, LG Mainz, BGH). |
| ADRESSE | Anschrift mit Hausnummer, ganzer Span inkl. PLZ/Ort wenn zusammenhängend (auch über Zeilenumbruch); auch RIS-Platzhalter `*****` an Adressstelle. |
| ORT | Eigenständiger Orts-, Gemeinde-, Bezirks-, Regions- oder Staatsname, der nicht Teil von ADRESSE/GERICHT/ORGANISATION ist (auch Staatsangehörigkeit „StA. Syrien“). |
| DATUM | Tagesgenaues Datum (Geburts-, Ereignis-, Entscheidungsdatum), in jeder Schreibweise (`12.03.2025`, `2024-09-19`, `5. Juli`, `dritten Juli zweitausendfünfundzwanzig`, RIS `***** 2011`). |
| GESCHAEFTSZAHL | Akten-/Geschäftszeichen von Gerichten, Behörden, Kanzleien, Polizei, Grundbuch-TZ, Firmenbuch-Geschäftsfälle, Notariats-GZ. |
| GESETZ | Normzitat mit Fundstelle (§, Art., TP/Tarifpost, Nr. VV RVG), z. B. `§ 1295 ABGB`, `Art. 8 EMRK`, `§ 823 Abs. 1 BGB`. |
| KENNNUMMER | IBAN, SV-/Rentenversicherungsnummer, FN/HRB/HRA, UID/USt-IdNr., Steuernummer, KFZ-Kennzeichen, FIN, EZ, KG-Nummer, Grundstücksnummer, Grundbuchblatt, Ausweis-/Führerschein-/Polizzennummern, Anwaltscode, Register-/Mitglieds-/Buchungsnummern. |
| KONTAKT | Telefon, Fax, E-Mail, Social-Media-Handle. |

## Doc-Types

AT: ogh_urteil, ogh_beschluss, olg_urteil, lg_strafurteil, bg_beschluss (Exekution, Verlassenschaft,
Pflegschaft), vwgh_erkenntnis, vfgh_erkenntnis, bvwg_erkenntnis, lvwg_erkenntnis, bescheid (BH,
DSB, Finanzamt), strafverfuegung, klage, klagebeantwortung, berufung, anwaltsschreiben,
email_korrespondenz, mietvertrag, kaufvertrag, arbeitsvertrag, grundbuchauszug, firmenbuchauszug,
protokoll_tagsatzung, testament, notariatsakt, polizeiliche_anzeige, sachverstaendigengutachten.
DE: bgh_urteil, olg_urteil, lg_urteil, ag_urteil, arbeitsgericht_urteil, strafbefehl, abmahnung,
mietvertrag, grundbuchauszug, anwaltsschreiben.

RIS-pseudonymisiert: `at_01`, `at_21`, `at_28` (teilweise `at_03`). OCR-Rauschen (Silbentrennung,
Zeilenumbrüche, O/0-, l/1-, S/§-Verwechslungen, Leerzeichen in Zahlen): `at_24`, `at_25`, `de_39`.

## Annotationsregeln (Entscheidungen)

- **Gesetze ohne Fundstelle werden nicht getaggt**: „das ABGB“, „MRG“, „Parkometergesetz“,
  „Kollektivvertrag“, „ÖNORM B 3521-1“, „BGBl. II 143/2012“, `RS0127773` (RIS-Rechtssatz).
  Mit §/Art. wird der ganze Zitatblock inkl. Gesetzesabkürzung getaggt.
- **Zitatketten**: jedes Zitat separat (`§ 879 Abs 3 ABGB` iVm `§ 6 Abs 1 Z 1 KSchG`); Aufzählungen
  innerhalb eines Gesetzes bleiben ein Span (`§§ 41, 50 ZPO`, `§§ 146, 147 Abs 1 Z 1 … StGB`).
  Unvollständige Glieder in Ketten (`Art. 5 Abs. 1 lit. a und c`, `Art. 6 Abs. 1`, … `der Verordnung (EU) 2016/679`) werden einzeln getaggt.
- **Anreden/Funktions- und Dienstgrade gehören nicht zum Span**: Herr/Frau, Fa., RAA, GrInsp,
  RevInsp, POK, ADir., Hofrat, Senatspräsident. Akademische Grade (inkl. „Dr. med.“, „DSA“, „Bmstr.“) gehören dazu.
- **Gattungsbezeichnungen von Gerichten** ohne Ortsangabe (Erstgericht, Berufungsgericht, „das
  Landgericht“, „das Verwaltungsgericht“) werden nicht getaggt; eindeutige Höchst-/Bundesgerichte
  (Oberster Gerichtshof, Verwaltungsgerichtshof, Bundesverwaltungsgericht, BGH) schon.
- **ORT vs. ADRESSE vs. GERICHT vs. ORGANISATION**: „Landesgericht Linz“ = GERICHT, „Linz“ allein =
  ORT, „Leonfeldner Straße 118, 4040 Linz“ = ADRESSE, „Landeshauptstadt Innsbruck“ als zahlungspflichtige
  Partei = ORGANISATION. Straßennamen ohne Hausnummer (Tatort-Beschreibungen) werden nicht getaggt.
  Adjektive („Wiener“, „syrische Armee“) werden nicht getaggt.
- **Kein Nesting**: Organisationsnamen mit Personen- oder Ortsnamen („Kanzlei Dr. Hutterer & Partner
  Rechtsanwälte GmbH“, „Linz Textil GmbH“, „Ordination Dr. Kollegger“) sind ein ORGANISATION-Span.
- **Katastralgemeinde mit Nummer** („KG 01009 Neubau“, „Grundbuch 56508 Ebenau“) = KENNNUMMER;
  bloßer Gemarkungsname (DE, „Schwabing“) = ORT.
- **DATUM nur tagesgenau**; Monat+Jahr („März 2022“) und bloße Jahre bleiben ungetaggt. Datumsangaben
  innerhalb von Kennnummern (SV-Nr.) werden nicht separat getaggt.
- URLs (www.…) werden nicht getaggt; Social-Media-Handles als KONTAKT.
- OCR-Spans enthalten das Rauschen exakt (z. B. `Hu-\nmer`, `46OO Wels`, `S 180 Abs 2 ABGB`).

## Bekannte Einschränkungen

- Klein (40 Dokumente, ~21.000 Wörter, ~1.900 Entitäten), von einem einzigen Autor (LLM) geschrieben –
  stilistisch homogener als echte Daten; DE unterrepräsentiert (25 %).
- Reale Institutionen (Gerichte, Behörden, einzelne Kliniken/Universitäten) kommen vor; Firmen-
  und Personennamen sind erfunden, können aber zufällig mit realen übereinstimmen. IBANs/SV-Nummern
  sind nur formatplausibel (keine gültigen Prüfziffern garantiert).
- Zitierte Geschäftszahlen sind erfunden; Übereinstimmungen mit realen Entscheidungen sind Zufall.
- Grenzfälle (Staatsnamen als ORT, Behörden als ORGANISATION, KG als KENNNUMMER) sind Konventionen
  dieses Datensatzes und ggf. an das Zielschema anzupassen.
- Die Lint-Prüfung findet nur Wiederholungen bereits getaggter Strings und häufige Städte; erstmalig
  übersehene Entitäten erkennt sie nicht.
