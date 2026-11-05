"""Write plan.jsonl: one brief per synthetic OBDK document (20 batches x 10).

    python make_plan.py <synthetic_dir>

Each brief fixes era, decision type, topic, length, the identifier labels that
must occur, two hard cases and a pool of identifiers with valid check digits
(IBAN, SV-Nummer, FN, UID). The writers never see real decisions.
"""

import json
import pathlib
import random
import sys

rng = random.Random(20261102)

# ---------------------------------------------------------------- identifiers
SVNR_WEIGHTS = (3, 7, 9, 0, 5, 8, 4, 2, 1, 6)
FN_LETTERS = "abdfghikmpstvwxyz"
FN_WEIGHTS = (6, 4, 14, 15, 10, 1)
AT_DISTRICTS = ("W", "L", "G", "S", "I", "K", "B", "E", "P", "BN", "MD", "WU", "KO", "GU", "LL", "WL", "SL", "KU",
                "VB", "BR", "SZ", "LA", "FK", "BZ", "DO", "VI", "KL", "SP", "WO", "FR", "LE", "HB", "WN", "NK",
                "TU", "AM", "ME", "GD", "HO", "ZT", "MI", "GF", "HL", "BL", "OW", "JE", "EU", "MU", "LB", "WY")
UPPER = "ABCDEFGHIJKLMNOPRSTUVWXYZ"


def iban_at():
    bban = "".join(rng.choice("0123456789") for _ in range(16))
    check = 98 - int("".join(str(int(c, 36)) for c in bban + "AT00")) % 97
    raw = f"AT{check:02d}{bban}"
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def svnr(year_max):
    while True:
        serial = f"{rng.randint(100, 999)}"
        yy = rng.randint(15, min(99, year_max - 1900 - 20)) if year_max < 2000 else rng.randint(30, 99)
        dob = f"{rng.randint(1, 28):02d}{rng.randint(1, 12):02d}{yy:02d}"
        digits = [int(c) for c in serial + "0" + dob]
        check = sum(w * d for w, d in zip(SVNR_WEIGHTS, digits)) % 11
        if check < 10:
            return f"{serial}{check} {dob}"


def fn():
    number = rng.randint(1000, 650000)
    digits = [int(c) for c in f"{number:06d}"]
    return f"FN {number}{FN_LETTERS[sum(w * d for w, d in zip(FN_WEIGHTS, digits)) % 17]}"


def uid_at():
    d = [rng.randint(0, 9) for _ in range(7)]
    s = 0
    for i, x in enumerate(d):
        if i % 2:
            x = x * 2
            x = x // 10 + x % 10
        s += x
    return "ATU" + "".join(map(str, d)) + str((96 - s) % 10)


def plate(year):
    district = rng.choice(AT_DISTRICTS)
    if year < 1990:  # black plates: district + digits with a thousands dot
        n = rng.randint(1000, 199999)
        return f"{district} {n:,}".replace(",", ".")
    letters = "".join(rng.choice(UPPER) for _ in range(rng.randint(1, 2)))
    digits = str(rng.randint(10, 9999))
    return rng.choice([f"{district}-{digits}{letters}", f"{district} {digits} {letters}"])


def id_docs():
    d = lambda n: "".join(rng.choice("0123456789") for _ in range(n))  # noqa: E731
    return {"passport": f"{rng.choice('PUXS')}{d(7)}", "id_card": f"{rng.choice('ACE')}{d(7)}",
            "driving_licence": d(8)}


def old_account():
    return f"{rng.randint(100, 999)}-{rng.randint(100, 999)}.{rng.randint(100, 999)}"


def steuernummer():
    return f"{rng.randint(10, 99)}-{rng.randint(100, 999)}/{rng.randint(1000, 9999)}"


def anwaltscode():
    return f"{rng.choice('RP')}{rng.randint(100000, 999999)}"


# ---------------------------------------------------------------- plan axes
BATCH_ERAS = (
    [(1973, 1979)] * 3 + [(1980, 1989)] * 4 + [(1990, 1999)] * 5 + [(2000, 2009)] * 4 + [(2010, 2013)] * 2
    + [(2014, 2024)] * 2  # from 2014 the OGH decides lawyers' disciplinary appeals ("20 Ds 7/19x")
)

DECISION_TYPES = [
    ("erkenntnis_berufung_schuld_strafe", 30, "Erkenntnis über die Berufung des Beschuldigten und/oder des Kammeranwalts wegen Schuld und Strafe gegen ein Erkenntnis des Disziplinarrats (nach mündlicher Berufungsverhandlung)"),
    ("erkenntnis_berufung_strafe", 12, "Erkenntnis über eine Berufung nur wegen der Strafe (Geldbuße, Verweis, Untersagung, Streichung)"),
    ("beschluss_beschwerde_einstellung", 16, "Beschluss über die Beschwerde eines Anzeigers gegen die Einstellung/Zurücklegung durch den Disziplinarrat (nichtöffentliche Sitzung)"),
    ("beschluss_einstweilige_massnahme", 7, "Beschluss über eine Beschwerde gegen eine einstweilige Maßnahme (vorläufige Untersagung der Berufsausübung)"),
    ("beschluss_ablehnung_befangenheit", 5, "Beschluss über einen Ablehnungsantrag gegen Mitglieder des Disziplinarrats"),
    ("erkenntnis_wiederaufnahme", 5, "Erkenntnis/Beschluss über einen Antrag auf Wiederaufnahme des Disziplinarverfahrens"),
    ("bescheid_beschwerde_ausschuss", 12, "Entscheidung über eine Beschwerde gegen einen Bescheid des Ausschusses der Rechtsanwaltskammer (Eintragung in die Liste, Kammerbeitrag, Versorgungseinrichtung, Kanzleisitz, Substitution)"),
    ("beschluss_kosten_verfahrenshilfe", 6, "Beschluss über Verfahrenskosten oder Pauschalkosten des Disziplinarverfahrens"),
    ("erkenntnis_freispruch", 7, "Erkenntnis, mit dem der Berufung Folge gegeben und der Beschuldigte freigesprochen wird"),
]

TOPICS = [
    # (topic, identifier labels that fit naturally)
    ("Veruntreuung von Treuhandgeldern bei einem Liegenschaftskauf", ["bank_account", "land_register_id"]),
    ("Treuhandabwicklung einer Wohnungseigentumsübertragung mit verspäteter Lastenfreistellung", ["land_register_id", "bank_account"]),
    ("verspätete Weiterleitung von Fremdgeld aus einem Exekutionsverfahren", ["bank_account", "other_identifier"]),
    ("Doppelvertretung zweier Gesellschafter einer GmbH mit widerstreitenden Interessen", ["company_register_number", "tax_id"]),
    ("Vertretung gegen einen früheren Mandanten in einer Gesellschaftsauflösung", ["company_register_number"]),
    ("Fristversäumnis bei einer Berufung, Verschweigen gegenüber dem Mandanten", ["other_identifier"]),
    ("Verletzung der Verschwiegenheitspflicht in einem Scheidungsverfahren", ["social_security_number"]),
    ("herabsetzende Äußerungen über einen Richter in einem Schriftsatz", []),
    ("unsachliche Angriffe auf den Gegenvertreter in Briefen", ["phone_number"]),
    ("Honorarüberforderung und Zurückbehaltung von Handakten", ["bank_account", "other_identifier"]),
    ("Nichtbezahlung der Kammerumlage und der Beiträge zur Versorgungseinrichtung", ["bank_account", "other_identifier"]),
    ("direkte Kontaktaufnahme mit der anwaltlich vertretenen Gegenpartei", ["phone_number"]),
    ("unzulässige Werbung mit Erfolgsversprechen", ["phone_number"]),
    ("Alkoholisierte Fahrt und Verkehrsunfall des Beschuldigten, Ansehen des Standes", ["license_plate", "id_document_number"]),
    ("Vertretung eines Unfallgegners trotz Vorbefassung im Schadenersatzprozess", ["license_plate", "other_identifier"]),
    ("Missachtung der Sorgfaltspflichten zur Geldwäscheprävention bei einem Treuhandauftrag", ["id_document_number", "bank_account"]),
    ("mangelhafte Aufsicht über einen Rechtsanwaltsanwärter, der Unterschriften fälschte", ["other_identifier"]),
    ("Verfahrenshilfe: Untätigkeit als bestellter Verfahrenshelfer", ["social_security_number", "other_identifier"]),
    ("Abgabenhinterziehung durch den Beschuldigten (Strafurteil als Vorfrage)", ["tax_id"]),
    ("Mitwirkung an einer Scheinfirma und falschen Bilanzen eines Mandanten", ["company_register_number", "tax_id"]),
    ("Vertretung in einer Verlassenschaft und Unterschlagung von Nachlassvermögen", ["social_security_number", "land_register_id"]),
    ("unrichtige Angaben im Grundbuchsgesuch", ["land_register_id"]),
    ("Kanzleiführung ohne Haftpflichtversicherung", ["other_identifier", "company_register_number"]),
    ("Missbrauch der Vollmacht bei einer Exekution gegen den eigenen Mandanten", ["bank_account"]),
    ("E-Mail-Korrespondenz mit beleidigendem Inhalt an eine Behörde", ["email", "phone_number"]),
    ("Weitergabe von Mandantendaten per E-Mail an Dritte", ["email", "social_security_number"]),
    ("verspätete Antwort auf Anfragen der Rechtsanwaltskammer", ["other_identifier", "email"]),
    ("Eintragung eines Rechtsanwaltsanwärters trotz fehlender Gerichtspraxis", ["other_identifier"]),
    ("Verlegung des Kanzleisitzes ohne Anzeige, Zustellmängel", ["street", "phone_number"]),
    ("Vertretung bei einem Kfz-Kaufvertrag und Verschweigen von Vorschäden", ["license_plate", "id_document_number"]),
    ("Pflichtverletzung als Masseverwalter in einem Konkursverfahren", ["company_register_number", "bank_account"]),
    ("Mandatsführung für eine Bank gegen einen langjährigen Privatmandanten", ["bank_account", "other_identifier"]),
]

# earliest plausible year per topic (matched by topic prefix)
TOPIC_MIN_YEAR = {
    "E-Mail-Korrespondenz": 2000,
    "Weitergabe von Mandantendaten per E-Mail": 2002,
    "Missachtung der Sorgfaltspflichten zur Geldwäsche": 1994,
    "Kanzleiführung ohne Haftpflichtversicherung": 1999,
}


def min_year(topic):
    return next((y for prefix, y in TOPIC_MIN_YEAR.items() if topic.startswith(prefix)), 0)

HARD_CASES = [
    "Bare surname coreference: a person is introduced with full name and degree, later only by surname (tag every mention).",
    "Genitive of a name ('Dr. Hubers Schriftsatz' -> tag 'Dr. Hubers').",
    "A surname that is also a place or a common word (Herr Steyr, Frau Wien, Herr Baden, Frau Sommer) - person, not location.",
    "Line break with hyphenation inside an entity ('Rechtsan-\\nwaltskammer', 'Kre-\\nmser'); the tag spans the hyphen and the line break exactly as written.",
    "OCR noise typical of typewritten scans: letter o instead of 0 in numbers and dates ('199o', '2o. November'), 'l' for '1'; tags keep the noisy text as written.",
    "A header block in ALL CAPS (court name, address, case number) tagged like normal text.",
    "A list of several parties or witnesses with places of residence.",
    "A long chain of norm citations ('§§ 1 und 2 DSt', '§ 9 Abs 1 RAO iVm § 2 DSt', 'Art 6 EMRK').",
    "Literature citation with authors ('Feil/Wennig, Anwaltsrecht § 9 RAO Rz 5' -> authors are person, the rest untagged).",
    "Citation of earlier disciplinary decisions with body, date and case number tagged as parts ('[[court|OBDK]] [[date|12. März 1990]], [[case_number|Bkd 5/89]]').",
    "Page-number lines ('- 3 -' or a bare '2') and hard line breaks every 60-70 characters, as in a scanned typescript.",
    "Pseudonymised RIS style for parties and witnesses ('Dr. N***** M*****', 'A*****'): tag placeholders with the label of what they replace.",
    "A name with particle or double-barrelled surname (Maria von der Heyden-Lutz, Ahmet Yılmaz-Gruber).",
    "A Kanzlei name containing the partners' surnames ('Kanzlei Dr. Brandl & Partner Rechtsanwälte GmbH' is one organization span).",
    "Dates in several spellings in the same document (14.3.1987, 14. März 1987, 14. 3. 87), incl. a date range 'vom 1. bis 15. Juni'.",
    "Places both as residence ('Rechtsanwalt in Wels') and inside an address with postcode.",
]

NAME_MIXES = [
    "Austrian (Vienna, Lower Austria)", "Austrian (Tyrol, Vorarlberg)", "Austrian (Styria, Carinthia)",
    "Czech and Slovak origin", "Hungarian origin", "Croatian, Serbian, Bosnian origin", "Slovenian origin",
    "Turkish origin", "Polish origin", "Italian (South Tyrol)", "German", "Romanian origin",
    "Persian and Arabic origin", "Ukrainian origin", "Greek origin", "Bulgarian origin",
]

CHAMBERS = ["Wien", "Niederösterreich", "Oberösterreich", "Steiermark", "Kärnten", "Salzburg", "Tirol",
            "Vorarlberg", "Burgenland"]

RARE_SPREAD = ["street", "phone_number", "email", "license_plate", "id_document_number", "tax_id",
               "social_security_number", "company_register_number", "land_register_id", "bank_account",
               "other_identifier"]


def weighted_choice(items):
    total = sum(w for _, w, _ in items)
    x = rng.uniform(0, total)
    for name, w, desc in items:
        x -= w
        if x <= 0:
            return name, desc
    return items[-1][0], items[-1][2]


def main():
    out_dir = pathlib.Path(sys.argv[1])
    briefs = []
    for b, (y0, y1) in enumerate(BATCH_ERAS, start=1):
        for d in range(1, 11):
            year = rng.randint(y0, y1)
            dtype, ddesc = weighted_choice(DECISION_TYPES)
            topic, rare = rng.choice([t for t in TOPICS if year >= min_year(t[0])])
            rare = list(rare)
            # spread rare labels: one extra random identifier per document
            extra = rng.choice(RARE_SPREAD)
            if extra not in rare:
                rare.append(extra)
            if year < 2000:
                rare = [r for r in rare if r != "email"] or ["phone_number"]
            ids = {}
            if "bank_account" in rare:
                ids["bank_account"] = [iban_at(), iban_at()] if year >= 2002 else [
                    f"Konto Nr. {old_account()}", f"Kto.-Nr. {old_account()}"]
            if "social_security_number" in rare:
                ids["social_security_number"] = [svnr(year), svnr(year)]
            if "company_register_number" in rare:
                ids["company_register_number"] = [fn(), fn()] if year >= 1991 else [
                    f"HRB {rng.randint(1000, 60000)}", f"HRA {rng.randint(1000, 30000)}"]
            if "tax_id" in rare:
                ids["tax_id"] = [uid_at(), uid_at()] if year >= 1995 else [
                    f"St.Nr. {steuernummer()}", f"Steuernummer {steuernummer()}"]
            if "license_plate" in rare:
                ids["license_plate"] = [plate(year), plate(year)]
            if "id_document_number" in rare:
                ids["id_document_number"] = id_docs()
            if "other_identifier" in rare:
                ids["other_identifier_examples"] = [
                    f"Treuhandbuch-Nr. {rng.randint(10, 999)}/{str(year)[2:]}",
                    f"Klientennummer {rng.randint(10000, 99999)}",
                    f"Polizzennummer {rng.randint(10, 99)}-{rng.randint(100000, 999999)}",
                ] + ([f"Anwaltscode {anwaltscode()}"] if year >= 1995 else [])
            brief = {
                "batch": f"b{b:02d}",
                "file": f"obdk_b{b:02d}_d{d:02d}_{dtype}.md",
                "year": year,
                "decision_type": dtype,
                "decision_type_desc": ddesc,
                "topic": topic,
                "chamber": rng.choice(CHAMBERS),
                "accused_role": rng.choices(["Rechtsanwalt", "Rechtsanwältin", "Rechtsanwaltsanwärter",
                                             "Rechtsanwaltsanwärterin", "Rechtsanwalts-GmbH and its managing partner"],
                                            (45, 25, 12, 8, 10 if year >= 2000 else 0))[0],
                "target_words": rng.choice([500, 700, 900, 1100, 1300, 1600, 2000]),
                "required_labels": sorted(set(rare)),
                "identifiers": ids,
                "hard_cases": rng.sample(HARD_CASES, 2),
                "names_from": rng.sample(NAME_MIXES, 2),
                "ris_pseudonymised": rng.random() < 0.1,
                "ocr_typescript": year < 1995 and rng.random() < 0.6,
            }
            briefs.append(brief)
    with (out_dir / "plan.jsonl").open("w", encoding="utf-8") as fh:
        for br in briefs:
            fh.write(json.dumps(br, ensure_ascii=False) + "\n")
    print(len(briefs), "briefs")


if __name__ == "__main__":
    main()
