"""Programmatic Austrian register documents: company register extracts (Firmenbuchauszug) and residence registration
confirmations (ZMR Meldebestätigung, Meldezettel). Fixed layouts that an LLM writer gets wrong (v7 pilot audit), so
they are generated like the land register extracts (legalner.sources.grundbuch), with scan-mode OCR noise.

    python -m legalner.sources.registers --docs 150 --ocr-frac 0.2 --seed 13 -o data/synthetic/raw_v7_registers
"""
import argparse
import pathlib
import random
import re

from legalner import fake_ids as F
from legalner.gazetteers import Gazetteer, transliterate
from legalner.practice import NATIONALITIES, REGISTER_COURTS, surname
from legalner.sources.grundbuch import DEGREES, Cast, Doc, maybe_split, ocr

BRANCHES = ["Baugewerbe", "Handel mit Waren aller Art", "Immobilienverwaltung", "Unternehmensberatung",
            "Gastronomie und Beherbergung", "Softwareentwicklung", "Transport und Logistik", "Elektrotechnik",
            "Installateur", "Vermögensverwaltung", "Holdinggesellschaft", "Tischlerei", "Kfz-Handel und Werkstätte",
            "Reinigungsdienstleistungen", "Physiotherapie", "Landwirtschaftlicher Handel", "Werbeagentur"]
FORMS = [("GmbH", "Gesellschaft mit beschränkter Haftung", 0.55), ("FlexCo", "Flexible Kapitalgesellschaft", 0.05),
         ("KG", "Kommanditgesellschaft", 0.12), ("OG", "Offene Gesellschaft", 0.08), ("AG", "Aktiengesellschaft", 0.05),
         ("e.U.", "Eingetragenes Unternehmen", 0.15)]
MELDEBEHOERDEN = ["Magistrat der Stadt Wien, Magistratsabteilung 62", "Marktgemeinde {t}", "Stadtgemeinde {t}",
                  "Gemeinde {t}", "Magistrat der Stadt {t}", "Bürgerservice {t}"]
COUNTRY_OF = {"DE": "Deutschland", "RS": "Serbien", "BA": "Bosnien und Herzegowina", "TR": "Türkei", "RO": "Rumänien",
              "HR": "Kroatien", "HU": "Ungarn", "PL": "Polen", "SY": "Syrien", "AF": "Afghanistan", "SK": "Slowakei",
              "CZ": "Tschechien", "IT": "Italien", "UA": "Ukraine", "AT": "Österreich"}
FOREIGN_TOWNS = {"DE": ["München", "Passau", "Rosenheim", "Berlin"], "RS": ["Beograd", "Niš", "Novi Sad"],
                 "BA": ["Sarajevo", "Tuzla", "Banja Luka"], "TR": ["Ankara", "Kayseri", "Konya"],
                 "RO": ["Timişoara", "Cluj-Napoca", "Arad"], "HR": ["Zagreb", "Split", "Osijek"],
                 "HU": ["Győr", "Sopron", "Budapest"], "PL": ["Kraków", "Wrocław", "Rzeszów"],
                 "SY": ["Aleppo", "Damaskus", "Homs"], "AF": ["Kabul", "Herat", "Mazar-e Sharif"],
                 "SK": ["Bratislava", "Trnava", "Nitra"], "CZ": ["Brno", "České Budějovice", "Znojmo"],
                 "IT": ["Udine", "Bozen", "Verona"], "UA": ["Lwiw", "Kyjiw", "Czernowitz"]}


def _d(rng, lo, hi):
    return f"{rng.randint(1, 28):02d}.{rng.randint(1, 12):02d}.{rng.randint(lo, hi)}"


def _person(gaz, rng, foreign_p=0.2):
    g = rng.choice("MF")
    c = "AT" if rng.random() >= foreign_p else rng.choice(list(FOREIGN_TOWNS))
    first = transliterate(gaz.first_name(c, g))
    last = transliterate(surname(gaz, c, g))
    deg = rng.choice(DEGREES) if rng.random() < 0.2 else None
    return {"first": first, "last": last, "g": g, "c": c, "degree": deg, "dob": _d(rng, 1940, 2004)}


def _full(p, rng, caps=False):
    last = p["last"].upper() if caps else p["last"]
    name = f"{p['first']} {last}"
    return f"{p['degree']} {name}" if p["degree"] else name


def _std(a):
    """'Street 1, Town 1234' / 'Wien 1100' -> 'Street 1, 1234 Town' (register order)."""
    return re.sub(r"(^|, )([^,\d]+?) (\d{4})$", r"\1\3 \2", a)


def _addr(cast, rng, two_lines=False, indent="", a=None):
    a = a or _std(cast.address(rural=rng.random() < 0.3))
    if two_lines and ", " in a:
        street, rest = a.split(", ", 1)
        return f"{street}\n{indent}{rest}"
    return a


# --- Firmenbuch ---------------------------------------------------------------------------------------------------------

def firmenbuch(gaz, rng, idx):
    cast = Cast(gaz, rng)
    short, form_long, _ = rng.choices(FORMS, [w for *_, w in FORMS])[0]
    owner = _person(gaz, rng)
    core = rng.choice([owner["last"], f"{owner['last']} & {transliterate(gaz.last_name('AT'))}",
                       f"{transliterate(gaz.last_name('AT'))} {rng.choice(['Bau', 'Immobilien', 'Handels', 'Holding', 'Consulting', 'Transporte', 'Technik'])}"])
    firm = f"{owner['first']} {owner['last']}" if short == "e.U." and rng.random() < 0.6 else core
    firm = f"{firm} {short}" if short != "FlexCo" else f"{firm} FlexCo"
    fn = F.fn(rng)
    court_full, court_abbr = rng.choice(REGISTER_COURTS)
    seat_addr = _std(cast.address(rural=rng.random() < 0.3))
    town = _town_of(seat_addr)
    historic = rng.random() < 0.35
    founded = rng.randint(1985, 2023)
    stichtag = _d(rng, 2025, 2026)
    caps = rng.random() < 0.3
    W = 18  # column width of the official layout
    d = Doc()

    def row(key, *parts, ind=" 1"):
        d.t(f"{ind:<4}" if key is None else f"{key}\n{ind:<4}")
        d.t(" " * (W - 4))
        for p in parts:
            d.e(*p) if isinstance(p, tuple) else d.t(p)
        d.nl()

    official = rng.random() < 0.75
    if official:
        d.t("FIRMENBUCH\n")
        d.e("country", "REPUBLIK ÖSTERREICH")
        d.t("\n\n")
        d.t(f"Auszug mit {'historischen' if historic else 'aktuellen'} Daten\n")
        d.e("company_register_number", fn)
        d.t(f"{' ' * 30}Stichtag ")
        d.e("date", stichtag)
        d.t(f"{' ' * 8}Seite 1\n{'-' * 72}\n")
        d.t(f"{' ' * 12}zuletzt eingetragen am ")
        d.e("date", _d(rng, max(founded, 2015), 2026))
        d.t(f" mit Eintragungsnummer {rng.randint(2, 40)}\n{'-' * 72}\n")
        d.t("FIRMENBUCHGERICHT  ")
        d.e("court", court_full if rng.random() < 0.7 else court_abbr)
        d.t("\n")
        if short in ("GmbH", "AG", "FlexCo"):
            d.t("ZULETZT EINGEBRACHTER JAHRESABSCHLUSS zum ")
            d.e("date", f"31.12.{rng.randint(2022, 2025)}")
            d.t(" eingereicht am ")
            d.e("date", _d(rng, 2023, 2026))
            d.t("\n")
        d.t(f"{'-' * 72}\n")
        if historic and rng.random() < 0.6:
            old = f"{transliterate(gaz.last_name('AT'))} {short}"
            row("FIRMA", ("organization", old.upper() if caps else old), ind=" 1")
            d.t(f"{' ' * W}gelöscht\n")
            row(None, ("organization", firm.upper() if caps else firm), ind=f" {rng.randint(3, 9)}")
        else:
            row("FIRMA", ("organization", firm.upper() if caps else firm))
        row("RECHTSFORM", form_long)
        d.t("SITZ in\n 1  " + " " * (W - 4) + "politischer Gemeinde ")
        d.e("location", town)
        d.nl()
        row("GESCHÄFTSANSCHRIFT", ("address", _addr(cast, rng, two_lines=rng.random() < 0.6, indent=" " * W, a=seat_addr)),
            ind=f" {rng.randint(1, 12)}")
        row("GESCHÄFTSZWEIG", rng.choice(BRANCHES))
        if short in ("GmbH", "FlexCo"):
            row("STAMMKAPITAL", f"EUR {rng.choice(['10.000', '35.000', '36.000', '50.000', '100.000'])}")
        elif short == "AG":
            row("GRUNDKAPITAL", f"EUR {rng.choice(['70.000', '100.000', '1.000.000', '2.500.000'])}")
        if short in ("GmbH", "FlexCo", "AG"):
            row("STICHTAG für JAHRESABSCHLUSS", "31. Dezember")
            row("GESELLSCHAFTSVERTRAG" if short != "AG" else "SATZUNG", f"{'Gesellschaftsvertrag' if short != 'AG' else 'Satzung'} vom ",
                ("date", _d(rng, founded, founded)))
        d.t(f"{'-' * 72}\n")
    else:  # portal "Kurzinfo" layout
        d.t(rng.choice(["Firmenbuch-Kurzinfo", "FIRMENBUCHAUSZUG (Kurzinformation)", "Firmeninformation"]) + "\n\n")
        for key, val in [("Firmenbuchnummer", ("company_register_number", fn)), ("Firmenwortlaut", ("organization", firm)),
                         ("Rechtsform", form_long), ("Sitz", ("location", town)),
                         ("Geschäftsanschrift", ("address", seat_addr)), ("Firmenbuchgericht", ("court", court_full)),
                         ("Stichtag", ("date", stichtag))]:
            d.t(f"{key + ':':<22}")
            d.e(*val) if isinstance(val, tuple) else d.t(val)
            d.nl()
        d.nl()

    # functions; persons get letters A, B, C … and reappear in PERSONEN with address and birth date
    people = []
    letters = iter("ABCDEFGHIJKLMNOP")
    if short == "e.U.":
        roles = [("INHABER/IN", [owner])]
    elif short in ("KG", "OG"):
        partners = [owner] + [_person(gaz, rng) for _ in range(rng.randint(1, 2))]
        roles = [("UNBESCHRÄNKT HAFTENDE GESELLSCHAFTER/IN", partners[:1 if short == "KG" else None])]
        if short == "KG":
            roles.append(("KOMMANDITIST/IN", partners[1:]))
    else:
        gfs = [owner] + [_person(gaz, rng) for _ in range(rng.randint(0, 2))]
        roles = [("VORSTAND" if short == "AG" else "GESCHÄFTSFÜHRER/IN (handelsrechtlich)", gfs)]
        if rng.random() < 0.45:
            roles.append(("PROKURIST/IN", [_person(gaz, rng) for _ in range(rng.randint(1, 2))]))
        if short != "AG":
            roles.append(("GESELLSCHAFTER/IN", gfs[:rng.randint(1, len(gfs))]))
    for title, members in roles:
        d.t(f"{title}\n")
        for p in members:
            if "letter" not in p:
                p["letter"] = next(letters)
                people.append(p)
            d.t(f" {p['letter']:<3}" + " " * (W - 4))
            d.e("person", _full(p, rng, caps))
            d.t(", geb. ")
            d.e("date_of_birth", p["dob"])
            d.nl()
            n = rng.randint(1, 12)
            if "GESCHÄFTSFÜHRER" in title or title in ("VORSTAND", "INHABER/IN", "UNBESCHRÄNKT HAFTENDE GESELLSCHAFTER/IN"):
                d.t(f" {n:<3}" + " " * (W - 4) + f"vertritt seit ")
                d.e("date", _d(rng, founded, 2026))
                d.t(rng.choice([" selbständig", " gemeinsam mit einem weiteren Geschäftsführer", " gemeinsam mit einem Prokuristen"]) + "\n")
            elif title == "PROKURIST/IN":
                d.t(f" {n:<3}" + " " * (W - 4) + rng.choice(["Einzelprokura", "Gesamtprokura gemeinsam mit einem Geschäftsführer"]) + "\n")
            elif title == "GESELLSCHAFTER/IN":
                amt = rng.choice(["17.500", "35.000", "5.000", "10.000", "50.000"])
                d.t(f" {n:<3}" + " " * (W - 4) + f"Einlage EUR {amt}  geleistet EUR {amt}\n")
            elif title == "KOMMANDITIST/IN":
                d.t(f" {n:<3}" + " " * (W - 4) + f"Haftsumme EUR {rng.choice(['1.000', '5.000', '10.000'])}\n")
            if historic and rng.random() < 0.15:
                d.t(" " * W + "gelöscht am ")
                d.e("date", _d(rng, founded, 2026))
                d.nl()
        if title == "GESELLSCHAFTER/IN" and rng.random() < 0.3:  # a corporate shareholder
            hold = f"{transliterate(gaz.last_name('AT'))} Holding GmbH"
            d.t(f" {next(letters):<3}" + " " * (W - 4))
            d.e("organization", hold)
            d.t(" (")
            d.e("company_register_number", F.fn(rng))
            d.t(")\n" + " " * W + "Einlage EUR 17.500  geleistet EUR 17.500\n")
        d.t(f"{'-' * 72}\n")
    if official:
        d.t("PERSONEN\n")
        for p in people:
            d.t(f" {p['letter']:<3}" + " " * (W - 4))
            d.e("person", maybe_split(rng, _full(p, rng, caps), 0.08))
            d.t(", geb. ")
            d.e("date_of_birth", p["dob"])
            d.nl()
            d.t(f" {rng.randint(1, 12):<3}" + " " * (W - 4))
            if p["c"] != "AT" and rng.random() < 0.3:
                d.e("address", f"{transliterate(gaz.last_name(p['c']))}str. {rng.randint(1, 90)}, {rng.choice(FOREIGN_TOWNS[p['c']])}")
                d.t(", ")
                d.e("country", COUNTRY_OF[p["c"]])
            else:
                d.e("address", _addr(cast, rng, two_lines=rng.random() < 0.4, indent=" " * W))
            d.nl()
        d.t(f"{'-' * 72}\nVOLLZUGSÜBERSICHT\n")
        k = rng.randint(2, 5)
        years = sorted(rng.randint(founded, 2026) for _ in range(k - 1))
        entries = [(1, founded, "Neueintragung")] + [
            (n, y, rng.choice(["Änderung Geschäftsführer", "Änderung Geschäftsanschrift", "Jahresabschluss",
                               "Änderung Gesellschafter", "Prokura"])) for n, y in zip(sorted(rng.sample(range(2, 16), k - 1)), years)]
        for n, y, what in entries:
            mo, day = rng.randint(1, 11), rng.randint(1, 20)
            d.t(f" {n:<3}" + " " * (W - 4) + "eingetragen am ")
            d.e("date", f"{day + rng.randint(3, 8):02d}.{mo + 1:02d}.{y}")
            d.t("\n" + " " * W)
            d.e("court", court_full)
            d.t("\n" + " " * W + "Antrag eingelangt am ")
            d.e("date", f"{day:02d}.{mo:02d}.{y}")
            d.t("\n" + " " * W)
            d.e("case_number", f"{rng.randint(1, 99)} Fr {rng.randint(100, 29999)}/{y % 100:02d} {rng.choice('abdfghikmpstvwxyz')}")
            d.t("\n" + " " * W + what + "\n")
        d.t(f"{'-' * 72}\nEnde des Auszuges\n")
    return d


# --- ZMR -----------------------------------------------------------------------------------------------------------------

def _town_of(address):
    """The municipality of an address as Cast.address writes it ("…, Town 1234", "Wien 1100", "Village 12 1234")."""
    import re as _re
    m = (_re.search(r"(?:^|, )\d{4} ([^,\d]+)$", address) or _re.search(r"(?:^|, )([^,\d]+?) \d{4}$", address)
         or _re.match(r"([^\d,]+?) \d", address))
    return m.group(1).strip() if m else "Wien"


def _behoerde(rng, town):
    if town == "Wien":
        return "Magistrat der Stadt Wien, Magistratsabteilung 62"
    return rng.choice(MELDEBEHOERDEN[1:]).format(t=town)


def _zmr_no(rng):
    n = f"{rng.randint(0, 9999):04d}{rng.randint(0, 99999999):08d}"
    return rng.choice([f"{n[:4]} {n[4:8]} {n[8:]}", n, f"{n[:4]}-{n[4:8]}-{n[8:]}"])


def meldebestaetigung(gaz, rng, idx):
    cast = Cast(gaz, rng)
    p = _person(gaz, rng, foreign_p=0.35)
    caps = rng.random() < 0.7
    birthplace = rng.choice(FOREIGN_TOWNS[p["c"]]) if p["c"] != "AT" else cast.town()[0]
    nat = COUNTRY_OF[p["c"]] if rng.random() < 0.85 else rng.choice(NATIONALITIES)
    d = Doc()

    def field(key, label, val, width=24):
        d.t(f"{key + ':':<{width}}")
        d.e(label, val) if label else d.t(val)
        d.nl()

    if rng.random() < 0.65:  # ZMR printout with Amtssignatur
        historic = rng.random() < 0.4
        d.e("country", "REPUBLIK ÖSTERREICH")
        d.t("\nZentrales Melderegister\n\n")
        d.t(f"MELDEBESTÄTIGUNG{' (historisch)' if historic else ''}\n\n")
        field("Familienname", "person", p["last"].upper() if caps else p["last"])
        field("Vorname", "person", p["first"])
        if p["degree"]:
            field("Akademischer Grad", None, p["degree"])
        field("Geschlecht", None, "männlich" if p["g"] == "M" else "weiblich")
        field("Geburtsdatum", "date_of_birth", p["dob"])
        field("Geburtsort", "location", birthplace)
        field("Staatsangehörigkeit", "country", nat)
        field("ZMR-Zahl", "other_identifier", _zmr_no(rng))
        d.nl()
        n_addr = rng.randint(2, 4) if historic else 1
        since = rng.randint(1995, 2024)
        for i in range(n_addr):
            d.t(f"Wohnsitzqualität:       {'Hauptwohnsitz' if i == 0 or rng.random() < 0.7 else 'Nebenwohnsitz'}\n")
            d.t("Adresse:                ")
            a = _std(cast.address())
            d.e("address", maybe_split(rng, a, 0.1))
            d.nl()
            if rng.random() < 0.4:
                if rng.random() < 0.6:
                    field("Unterkunftgeber", "person",
                          f"{transliterate(gaz.first_name('AT', rng.choice('MF')))} {transliterate(gaz.last_name('AT'))}")
                else:
                    field("Unterkunftgeber", "organization", f"{transliterate(gaz.last_name('AT'))} Immobilien GmbH")
            d.t("gemeldet seit:          " if i == 0 else "gemeldet von:           ")
            d.e("date", _d(rng, since, since))
            if i:
                d.t(" bis ")
                d.e("date", _d(rng, since + 1, since + 4))
            d.nl()
            d.t("Meldebehörde:           ")
            d.e("organization", _behoerde(rng, _town_of(a)))
            d.t("\n\n")
            since = max(1950, since - rng.randint(2, 8))
        d.t("Diese Meldebestätigung wurde elektronisch aus dem Zentralen Melderegister erstellt.\n")
        d.t("Datum/Zeit: ")
        d.e("date", _d(rng, 2025, 2026))
        d.t(f" {rng.randint(7, 18):02d}:{rng.randint(0, 59):02d}\n")
        d.t("Unterzeichner: Bundesministerium für Inneres\nPrüfinformation: Informationen zur Prüfung des elektronischen "
            "Siegels bzw. der elektronischen Signatur finden Sie unter: https://www.oesterreich.gv.at/amtssignatur\n")
        d.t("Signaturwert: " + "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
                                       for _ in range(rng.randint(60, 120))) + "\n")
    else:  # Meldezettel (Anlage A MeldeG) with registration stamp
        d.t("MELDEZETTEL\nfür Hauptwohnsitz und weitere Wohnsitze\n\n")
        field("FAMILIENNAME (in Blockschrift)", "person", p["last"].upper(), 34)
        field("Vorname lt. Geburtsurkunde", "person", p["first"], 34)
        if rng.random() < 0.4:
            field("Familienname vor der ersten Eheschließung", "person", transliterate(gaz.last_name(p["c"])).upper(), 34)
        field("Geburtsdatum", "date_of_birth", p["dob"], 34)
        field("Geschlecht", None, "männlich" if p["g"] == "M" else "weiblich", 34)
        field("Geburtsort lt. Reisedokument", "location", birthplace, 34)
        field("Familienstand", None, rng.choice(["ledig", "verheiratet", "geschieden", "verwitwet", "in eingetragener Partnerschaft"]), 34)
        field("Staatsangehörigkeit", "country", nat, 34)
        if p["c"] != "AT" or rng.random() < 0.3:
            d.t(f"{'Reisedokument (Art, Nummer)':<34}{rng.choice(['Reisepass', 'Personalausweis', 'Konventionsreisepass'])}, ")
            d.e("id_document_number", rng.choice([f"{rng.choice('PUCLK')}{rng.randint(1000000, 9999999)}",
                                                  f"{rng.choice('ABCDEFGHJKLMN')}{rng.randint(10000000, 99999999)}"]))
            d.t("\nAusstellungsdatum                 ")
            d.e("date", _d(rng, 2015, 2025))
            d.nl()
        d.t("\nANMELDUNG der Unterkunft in\n")
        d.t(f"{'Straße, Hausnummer, Stiege, Tür':<34}")
        a = _std(cast.address())
        d.e("address", a)
        d.t("\nIst diese Unterkunft Hauptwohnsitz?  ja\n")
        d.t("\nUNTERKUNFTGEBER (Name in Blockschrift, Datum und Unterschrift)\n")
        d.e("person", f"{transliterate(gaz.last_name('AT')).upper()} {transliterate(gaz.first_name('AT', rng.choice('MF')))}")
        d.t(", ")
        d.e("date", _d(rng, 2018, 2026))
        d.t("\n\n" + rng.choice(["Unterschrift des Meldepflichtigen", "Unterschrift der/des Meldepflichtigen"]) + "\n\n")
        d.t("Meldebehörde: ")
        d.e("organization", _behoerde(rng, _town_of(a)))
        d.t("\nAngemeldet am ")
        d.e("date", _d(rng, 2018, 2026))
        d.t("  ZMR-Zahl ")
        d.e("other_identifier", _zmr_no(rng))
        d.nl()
    return d


KINDS = {"firmenbuchauszug": firmenbuch, "meldebestaetigung": meldebestaetigung}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=150, help="per kind")
    ap.add_argument("--ocr-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    gaz = Gazetteer(rng=rng)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for kind, make in KINDS.items():
        for i in range(args.docs):
            doc = make(gaz, rng, i)
            scanned = rng.random() < args.ocr_frac
            if scanned:
                doc = ocr(doc, rng)
            body = re.sub(r"\n{3,}", "\n\n", doc.render())
            (out / f"AT_{kind[:2]}_{i + 1:04d}_{kind}.md").write_text(
                f"---\ndoc_type: {kind}{'_scan' if scanned else ''}\njurisdiction: AT\nlang: de\n---\n{body}",
                encoding="utf-8")
    print(f"{args.docs} x {len(KINDS)} documents -> {out}")


if __name__ == "__main__":
    main()
