"""Plan a synthetic generation wave: one brief per document, grouped into agent batches.

Each brief fixes the document type, jurisdiction, language, target length,
hard-case flags and a *cast*: persons (names drawn from WGND/Wikidata
gazetteers, so agents do not fall back on a few favourite surnames), judges,
lawyers, companies and identifiers with valid check digits (legalner.fake_ids).
Agents (Haiku, see data/synthetic/GENERATION.md) write the document around the
cast and may add further entities of their own.

    python -m legalner.genplan --docs 1000 --per-batch 6 --wave v3 -o data/synthetic/plans/v3.jsonl
"""
import argparse
import collections
import json
import pathlib
import random
import re

from legalner import fake_ids as F
from legalner.gazetteers import Gazetteer

# (jurisdiction, lang) -> (share of the wave, doc types)
MATRIX = {
    ("AT", "de"): (0.45, [
        "ogh_urteil", "ogh_beschluss", "olg_urteil", "olg_beschluss", "lg_urteil", "lg_strafurteil",
        "bg_urteil", "bg_beschluss_exekution", "bg_beschluss_verlassenschaft", "bg_beschluss_pflegschaft",
        "asg_urteil", "handelsgericht_beschluss", "firmenbuch_beschluss", "vwgh_erkenntnis", "vfgh_erkenntnis",
        "bvwg_erkenntnis", "lvwg_erkenntnis", "bfg_erkenntnis", "bescheid_bh", "bescheid_magistrat",
        "bescheid_finanzamt", "bescheid_dsb", "bescheid_bfa", "strafverfuegung", "anklageschrift", "klage",
        "klagebeantwortung", "berufung", "revision", "exekutionsantrag", "anwaltsschreiben", "email_kanzlei",
        "mietvertrag", "kaufvertrag_liegenschaft", "kaufvertrag_kfz", "arbeitsvertrag", "dienstzeugnis",
        "gesellschaftsvertrag", "notariatsakt", "testament", "grundbuchsauszug", "firmenbuchauszug",
        "protokoll_tagsatzung", "polizeiliche_anzeige", "sachverstaendigengutachten", "arztbrief",
        "versicherungsschreiben", "datenschutzauskunft", "vollmacht", "aufenthaltstitel"]),
    ("DE", "de"): (0.20, [
        "bgh_urteil", "olg_urteil", "lg_urteil", "ag_urteil", "arbeitsgericht_urteil", "lag_urteil",
        "sozialgericht_urteil", "vg_urteil", "finanzgericht_urteil", "strafbefehl", "anklageschrift",
        "bescheid_finanzamt", "bescheid_jobcenter", "abmahnung", "klageschrift", "mietvertrag",
        "kaufvertrag_notariell", "arbeitsvertrag", "handelsregisterauszug", "grundbuchauszug",
        "anwaltsschreiben", "mahnbescheid", "bussgeldbescheid", "kaufvertrag_kfz", "versicherungsschreiben",
        "polizeiliche_anzeige", "aufenthaltserlaubnis"]),
    ("CH", "de"): (0.10, [
        "bger_urteil", "obergericht_urteil", "kantonsgericht_entscheid", "handelsgericht_urteil", "strafbefehl",
        "zahlungsbefehl", "verfuegung_migrationsamt", "mietvertrag", "arbeitsvertrag", "arbeitszeugnis",
        "handelsregisterauszug", "anwaltsschreiben", "polizeirapport", "kaufvertrag_fahrzeug",
        "versicherungsschreiben", "auslaenderausweis_verfuegung"]),
    ("CH", "fr"): (0.05, [
        "bger_arret", "arret_cour_de_justice", "jugement_tribunal_des_baux", "ordonnance_penale",
        "contrat_de_bail", "lettre_avocat"]),
    ("FR", "fr"): (0.12, [
        "arret_cour_de_cassation", "arret_cour_d_appel", "jugement_tribunal_judiciaire", "jugement_prud_hommes",
        "jugement_correctionnel", "arret_conseil_d_etat", "jugement_tribunal_administratif", "ordonnance_refere",
        "acte_notarie", "contrat_de_bail", "contrat_de_travail", "mise_en_demeure", "proces_verbal_audition",
        "assignation", "extrait_kbis", "avis_de_contravention", "proces_verbal_police", "lettre_assurance",
        "certificat_de_cession_vehicule", "titre_de_sejour_decision"]),
    ("BE", "fr"): (0.04, [
        "arret_cour_d_appel", "jugement_tribunal_entreprise", "jugement_tribunal_premiere_instance",
        "arret_conseil_d_etat", "contrat_de_bail", "mise_en_demeure"]),
    ("LU", "fr"): (0.02, ["jugement_tribunal_arrondissement", "arret_cour_d_appel", "contrat_de_bail"]),
    ("LI", "de"): (0.02, ["fl_ogh_urteil", "landgericht_urteil", "mietvertrag", "handelsregisterauszug"]),
}

LEGAL_FORMS = {
    "AT": ["GmbH", "GmbH", "AG", "KG", "OG", "e.U.", "GmbH & Co KG"],
    "DE": ["GmbH", "GmbH", "AG", "UG (haftungsbeschränkt)", "GmbH & Co. KG", "e.K.", "KG"],
    "CH": ["AG", "AG", "GmbH", "Sàrl", "SA", "Genossenschaft"],
    "LI": ["AG", "Anstalt", "Stiftung", "GmbH"],
    "FR": ["SAS", "SARL", "SA", "SCI", "SASU", "EURL"],
    "BE": ["SRL", "SA", "SC", "ASBL"],
    "LU": ["S.à r.l.", "S.A.", "SCS", "SARL-S"],
}
SECTORS = {
    "de": ["Bau", "Immobilien", "Handels", "Transport", "Logistik", "Gastro", "Holz", "Elektro", "Consulting",
           "Software", "Metallbau", "Reinigungs", "Installations", "Hausverwaltung", "Autohaus", "Textil", "Druck",
           "Pflege", "Event", "Agrar", "Energie", "Möbel", "Fliesen", "Dachdecker"],
    "fr": ["Bâtiment", "Immobilier", "Transports", "Logistique", "Restauration", "Conseil", "Informatique",
           "Nettoyage", "Plomberie", "Distribution", "Services", "Textile", "Imprimerie", "Énergie", "Habitat"],
}
FR_CITIES = ["Paris", "Lyon", "Marseille", "Toulouse", "Nantes", "Strasbourg", "Bordeaux", "Lille", "Rennes",
             "Montpellier", "Grenoble", "Dijon", "Angers", "Nîmes", "Reims", "Le Havre", "Metz", "Tours"]
BE_CITIES = ["Bruxelles", "Liège", "Namur", "Charleroi", "Mons", "Louvain-la-Neuve", "Wavre", "Arlon"]
LU_CITIES = ["Luxembourg", "Esch-sur-Alzette", "Differdange", "Dudelange", "Ettelbruck", "Diekirch"]
# document types where licence plates, ID documents, phones and e-mails occur naturally: drawn
# OVERSAMPLE times as often within their jurisdiction (synthetic v4 targets the rare labels)
OVERSAMPLE = 4
RARE_LABEL_TYPES = {
    "polizeiliche_anzeige", "strafverfuegung", "kaufvertrag_kfz", "bescheid_bfa", "aufenthaltstitel",
    "versicherungsschreiben", "bussgeldbescheid", "aufenthaltserlaubnis", "polizeirapport", "kaufvertrag_fahrzeug",
    "auslaenderausweis_verfuegung", "avis_de_contravention", "proces_verbal_police", "lettre_assurance",
    "certificat_de_cession_vehicule", "titre_de_sejour_decision", "proces_verbal_audition", "strafbefehl"}
# rare-label entities, 1-3 per brief in v4
RARE_KINDS = ("license_plate", "id_document_number", "street", "phone_number", "email")
# degrees by country: Mag./DI/MMag. are Austrian; Germany writes Dipl.-Ing., Switzerland lic. iur./MLaw
DEGREES = {"AT": ["Dr.", "Mag.", "DI", "Ing.", "MMag.", "Dr. med.", "BSc", "MBA"],
           "DE": ["Dr.", "Dipl.-Ing.", "Dr. med.", "Dipl.-Kfm.", "Prof. Dr.", "B.Sc.", "M.A."],
           "CH": ["Dr.", "lic. iur.", "Dr. med.", "MLaw", "Prof. Dr.", "dipl. Ing. ETH"]}
DEGREES["LI"] = DEGREES["AT"]
PRE_DEGREES = {"AT": ["Dr.", "Mag.", "DI", "MMag.", "Dr. med.", "Prof. Dr.", "Univ.-Prof. Dr.", "Dr. Dr.",
                      "Prof. Dr. Dr.", "Mag. Dr.", "Dipl.-Ing. Dr.", "DDr.", "Priv.-Doz. Dr."],
               "DE": ["Dr.", "Prof. Dr.", "Dr. Dr.", "Prof. Dr. Dr.", "Dipl.-Ing.", "Dr. med.", "Dr.-Ing.",
                      "Priv.-Doz. Dr."],
               "CH": ["Dr.", "Prof. Dr.", "Dr. iur.", "lic. iur.", "Dr. med.", "Dr. Dr."]}
PRE_DEGREES["LI"] = PRE_DEGREES["AT"]
POST_DEGREES = ["MBA", "BSc", "MSc", "LL.M.", "PhD", "MBA PhD (New York)", "LL.M. (Harvard)", "MSc (London)",
                "BA", "MAS", "MBA MSc"]
PHONE_FORMATS = {
    "AT": ["+43 {a} {b}", "0{a} {b}", "+43 (0){a} {b}"], "DE": ["+49 {a} {b}", "0{a} {b}", "0{a}/{b}"],
    "CH": ["+41 {c} {d} {e} {f}", "0{c} {d} {e} {f}"], "LI": ["+423 {d} {e} {f}"],
    "FR": ["+33 {g}", "0{g}"], "BE": ["+32 {c} {d} {e} {f}", "0{c} {d} {e} {f}"], "LU": ["+352 {d} {e} {f}"],
}
MAIL_DOMAINS = {"AT": ["gmx.at", "aon.at", "chello.at", "a1.net", "outlook.at"], "DE": ["web.de", "gmx.de", "t-online.de"],
                "CH": ["bluewin.ch", "gmx.ch", "sunrise.ch"], "LI": ["adon.li", "powersurf.li"],
                "FR": ["orange.fr", "free.fr", "laposte.net", "sfr.fr"], "BE": ["skynet.be", "telenet.be"],
                "LU": ["pt.lu", "internet.lu"]}
COURT_DOC_PREFIXES = ("ogh", "olg", "lg", "bg", "asg", "vwgh", "vfgh", "bvwg", "lvwg", "bfg", "bgh", "ag_",
                      "lag", "sozial", "vg_", "finanz", "bger", "ober", "kantons", "handelsgericht", "arret",
                      "jugement", "fl_ogh", "landgericht", "firmenbuch")


CASE_HARD_CASES = [
    "a letterhead or party block in ALL CAPS (tag the entities inside it as usual)",
    "a passage in all lower case, e.g. a quoted e-mail or chat message (tag as usual)",
    "an ALL-CAPS name or company in an OCR'd stamp or heading (tag as usual)"]


def _weighted_types(rng, n, oversample=1):
    keys = list(MATRIX)
    counts = collections.Counter(rng.choices(keys, [MATRIX[k][0] for k in keys], k=n))
    out = []
    for key, k in counts.items():
        types = MATRIX[key][1]
        if oversample > 1:  # repeat the rare-label types in the round-robin list
            types = [t for t in types for _ in range(oversample if t in RARE_LABEL_TYPES else 1)]
        for i in range(k):  # round-robin over types keeps every type represented
            out.append((key[0], key[1], types[(i + rng.randrange(len(types))) % len(types)]))
    rng.shuffle(out)
    return out


def _company(gaz, rng, jur, lang):
    name = gaz.surname(jur if jur in ("AT", "DE", "CH", "FR", "BE", "LU") else "CH")
    style = rng.random()
    sector = rng.choice(SECTORS[lang])
    if style < 0.4:
        base = f"{name} {sector}"
    elif style < 0.7:
        base = f"{sector} {name}" if lang == "fr" else f"{name} & {gaz.surname(jur if jur != 'LI' else 'AT')}"
    else:
        base = name
    company = {"name": f"{base} {rng.choice(LEGAL_FORMS[jur])}"}
    if jur == "AT":
        company.update(register=F.fn(rng), vat=F.uid_at(rng))
    elif jur == "DE":
        kind = "HRA" if re.search(r"e\.K\.|KG$", company["name"]) else "HRB"  # partnerships, sole traders: HRA
        company.update(register=F.hrb(rng, kind), register_court=rng.choice(F.DE_REGISTER_COURTS),
                       vat=F.ust_idnr_de(rng), tax_number=F.steuernummer_de(rng))
    elif jur in ("CH", "LI"):
        company.update(register=F.che_uid(rng))
    elif jur == "FR":
        siren = F.siren(rng)
        company.update(siren=siren, siret=F.siret(rng, siren), vat=F.tva_fr(rng, siren),
                       rcs=f"RCS {rng.choice(FR_CITIES)}")
    elif jur == "BE":
        company.update(enterprise_number=F.be_enterprise(rng))
    elif jur == "LU":
        company.update(register=f"RCS Luxembourg B{rng.randint(10000, 290000)}")
    return company


def _address(gaz, rng, jur):
    if jur in ("AT", "DE", "CH") and gaz.streets.get(jur) and gaz.towns.get(jur):
        return gaz.address(jur)
    if jur == "LI":
        return f"{gaz.rng.choice(gaz.streets['CH'] or ['Landstrasse'])} {rng.randint(1, 90)}, " \
               f"{rng.choice(['9490 Vaduz', '9494 Schaan', '9495 Triesen', '9487 Gamprin-Bendern'])}"
    city = rng.choice({"FR": FR_CITIES, "BE": BE_CITIES, "LU": LU_CITIES}[jur])
    return f"(invent a realistic street address in {city})"


def _person(gaz, rng, jur, role=None, chains=False):
    home = jur if jur != "LI" else "AT"
    gender = rng.choice("MF")
    p = {"name": gaz.person(home, gender), "gender": gender}
    if rng.random() < 0.25 and jur in ("AT", "DE", "LI"):
        p["degree"] = rng.choice(DEGREES[jur])
    if chains and rng.random() < 0.07 and jur in ("AT", "DE", "LI", "CH"):  # "Prof. Dr. Dr. X, MBA PhD (New York)"
        p["degree"] = rng.choice(PRE_DEGREES[jur])
        p["degree_after"] = rng.choice(POST_DEGREES)
    if role:
        p["role"] = role
    return p


def _identifiers(rng, jur):
    country = {"LI": "LI", "CH": "CH"}.get(jur, jur)
    ids = {"iban": F.iban(country, rng)}
    if jur == "AT":
        ids["social_security_number"] = F.svnr(rng)
    elif jur == "DE":
        ids["social_security_number"] = F.rvnr(rng)
    elif jur in ("CH", "LI"):
        ids["social_security_number"] = F.ahv(rng)
    elif jur == "FR":
        ids["social_security_number"] = F.nir(rng)
    elif jur == "BE":
        ids["social_security_number"] = F.be_nrn(rng)
    elif jur == "LU":
        ids["social_security_number"] = F.lu_matricule(rng)
    return ids


def _phone(rng, jur):
    d = lambda n: "".join(rng.choice("0123456789") for _ in range(n))  # noqa: E731
    fmt = rng.choice(PHONE_FORMATS[jur])
    area = {"AT": ["664", "650", "676", "699", "1", "316", "732", "512", "662", "463"],
            "DE": ["30", "89", "40", "221", "151", "160", "170", "176", "711"]}.get(jur, ["1"])
    return fmt.format(a=rng.choice(area),
                      b=f"{d(3)} {d(4)}" if rng.random() < 0.5 else d(7), c=rng.choice(["44", "79", "76", "22", "21"]),
                      d=d(3), e=d(2), f=d(2), g=" ".join(d(2) for _ in range(4)) if "+" in fmt else
                      rng.choice("1234567") + " " + " ".join(d(2) for _ in range(4)))


def _email(rng, jur, person=None, company=None):
    import unicodedata
    def ascii_(x):
        return unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    if company and rng.random() < 0.5:
        base = re.sub(r"[^a-z]+", "-", ascii_(company.split()[0])).strip("-") or "office"
        prefixes = ["contact", "info", "accueil", "secretariat", "compta"] if jur in ("FR", "BE", "LU") else \
            ["office", "info", "kanzlei", "kontakt", "buchhaltung", "verwaltung"]
        return f"{rng.choice(prefixes)}@{base}." \
               f"{jur.lower() if jur != 'DE' else 'de'}"
    first, *rest = (person or "Max Muster").split()
    last = rest[-1] if rest else "muster"
    first, last = re.sub(r"[^a-z]", "", ascii_(first)) or "post", re.sub(r"[^a-z]", "", ascii_(last)) or "mail"
    sep = rng.choice([".", "_", "", "."])
    local = rng.choice([f"{first}{sep}{last}", f"{first[0]}{sep}{last}", f"{last}{rng.randint(1, 99)}"])
    return f"{re.sub(r'[^a-z0-9._]', '', local)}@{rng.choice(MAIL_DOMAINS[jur])}"


def _rare_entities(gaz, rng, jur, doc_type, persons, companies, is_court=False):
    """1-3 mentions of the rare labels; the vehicle and residence doc types always get theirs.
    Judgments get no phone numbers or e-mails (implausible there)."""
    kinds = list(RARE_KINDS)
    if jur in ("BE", "LU"):  # no plate/ID document generators for these countries
        kinds = ["street", "phone_number", "email"]
    if is_court:
        kinds = [k for k in kinds if k not in ("phone_number", "email")]
    k = rng.randint(1, 3)
    chosen = rng.sample(kinds, min(k, len(kinds)))
    if re.search(r"kfz|fahrzeug|vehicule|contravention|bussgeld|strafverfuegung|anzeige|rapport|police", doc_type) \
            and "license_plate" in kinds and "license_plate" not in chosen:
        chosen[0] = "license_plate"
    if re.search(r"aufenthalt|bfa|sejour|auslaender|migrations", doc_type) \
            and "id_document_number" in kinds and "id_document_number" not in chosen:
        chosen[-1] = "id_document_number"
    country = {"LI": "CH"}.get(jur, jur)
    out = {}
    for kind in chosen:
        if kind == "license_plate":
            out[kind] = F.license_plate("LI" if jur == "LI" else country, rng)
        elif kind == "id_document_number":
            doc = rng.choice(["passport", "id_card", "driving_licence"])
            out[kind] = {"document": doc, "number": F.id_document(country, doc, rng)}
        elif kind == "street":
            street = rng.choice(gaz.streets.get(country) or gaz.streets["AT"]) if country in ("AT", "DE", "CH") \
                else "(invent a street name)"
            out[kind] = f"{street} (mention the street without house number, e.g. a place of an incident)"
        elif kind == "phone_number":
            out[kind] = _phone(rng, jur)
        else:
            out[kind] = _email(rng, jur, rng.choice(persons)["name"] if persons else None,
                               rng.choice(companies)["name"] if companies else None)
    return out


def brief(gaz, rng, jur, lang, doc_type, idx, wave, rare=False, pseudo_frac=0.2):
    is_court = doc_type.startswith(COURT_DOC_PREFIXES)
    n_persons = rng.randint(2, 7)
    b = {
        "file": f"{jur}_{wave}_{idx:04d}_{doc_type}.md", "doc_type": doc_type, "jurisdiction": jur, "lang": lang,
        "target_words": int(min(2500, max(300, rng.lognormvariate(6.7, 0.5)))),
        "persons": [_person(gaz, rng, jur, chains=rare) for _ in range(n_persons)],
        "lawyers": [_person(gaz, rng, jur, "lawyer") for _ in range(rng.randint(0, 3 if is_court else 1))],
        "judges": [_person(gaz, rng, jur, "judge") for _ in range(rng.randint(1, 5) if is_court else 0)],
        "companies": [_company(gaz, rng, jur, lang) for _ in range(rng.randint(0, 3))],
        "addresses": [_address(gaz, rng, jur) for _ in range(rng.randint(1, 3))],
        # judgments rarely contain IBANs or social security numbers; forcing them in made texts implausible
        "identifiers": {} if is_court else _identifiers(rng, jur),
        "pseudonymised": jur == "AT" and is_court and rng.random() < pseudo_frac,
        "ocr_noise": rng.random() < 0.1,
        "hard_cases": rng.sample([
            "a person whose surname is also a place or common word", "surname-only coreference",
            "a person in the genitive (\"Hubers Antrag\")", "a long chain of norm citations",
            "a table written as text", "a list of several parties", "a person with a particle (von, de, van der)",
            "a double-barrelled or hyphenated name", "an abbreviation of an authority after its full name",
            "dates in two different spellings", "an address split over two lines"]
            + (CASE_HARD_CASES if rare else []), 2),
    }
    if rare:
        b["rare_entities"] = _rare_entities(gaz, rng, jur, doc_type, b["persons"], b["companies"], is_court)
    if not is_court:
        b["judges"] = []
    return b


# --- EU wave (v6): CJEU, General Court, AG opinions, Commission and EUIPO decisions, ECtHR ----------------
EU_TYPES = {
    "de": ["eugh_urteil", "eugh_urteil", "eugh_urteil", "eugh_beschluss", "schlussantraege_generalanwalt",
           "schlussantraege_generalanwalt", "vorabentscheidungsersuchen", "vorabentscheidungsersuchen", "eug_urteil",
           "kommission_beschluss_beihilfe", "kommission_beschluss_kartell", "euipo_beschwerdekammer", "egmr_urteil"],
    "fr": ["arret_cjue", "arret_cjue", "arret_cjue", "ordonnance_cjue", "conclusions_avocat_general",
           "conclusions_avocat_general", "demande_decision_prejudicielle", "demande_decision_prejudicielle",
           "arret_tribunal_ue", "decision_commission_aide_etat", "decision_commission_concurrence",
           "decision_chambre_recours_euipo", "arret_cedh"],
}
# member states with name gazetteers; legal forms for those without an entry in LEGAL_FORMS
EU_STATES = ["AT", "DE", "FR", "BE", "LU", "IT", "PL", "CZ", "SK", "HU", "RO", "PT", "ES", "HR"]
EU_LEGAL_FORMS = {"IT": ["SpA", "Srl"], "PL": ["sp. z o.o.", "S.A."], "CZ": ["s.r.o.", "a.s."], "SK": ["s.r.o."],
                  "HU": ["Kft.", "Zrt."], "RO": ["SRL", "SA"], "PT": ["Lda", "SA"], "ES": ["SL", "SA"],
                  "HR": ["d.o.o."]}
STATE_NAMES = {
    "de": {"AT": "Österreich", "DE": "Deutschland", "FR": "Frankreich", "BE": "Belgien", "LU": "Luxemburg",
           "IT": "Italien", "PL": "Polen", "CZ": "Tschechische Republik", "SK": "Slowakei", "HU": "Ungarn",
           "RO": "Rumänien", "PT": "Portugal", "ES": "Spanien", "HR": "Kroatien", "IE": "Irland",
           "NL": "Niederlande", "EL": "Griechenland", "FI": "Finnland"},
    "fr": {"AT": "Autriche", "DE": "Allemagne", "FR": "France", "BE": "Belgique", "LU": "Luxembourg",
           "IT": "Italie", "PL": "Pologne", "CZ": "République tchèque", "SK": "Slovaquie", "HU": "Hongrie",
           "RO": "Roumanie", "PT": "Portugal", "ES": "Espagne", "HR": "Croatie", "IE": "Irlande", "NL": "Pays-Bas",
           "EL": "Grèce", "FI": "Finlande"},
}
EU_BODIES = {
    "de": ["Kommission", "Rat", "Europäisches Parlament", "EUIPO", "Europäische Zentralbank (EZB)",
           "Europäische Behörde für Lebensmittelsicherheit (EFSA)", "Frontex", "Europäischer Datenschutzbeauftragter",
           "Einheitlicher Abwicklungsausschuss (SRB)", "Europäische Investitionsbank"],
    "fr": ["Commission", "Conseil", "Parlement européen", "EUIPO", "Banque centrale européenne (BCE)",
           "Autorité européenne de sécurité des aliments (EFSA)", "Frontex", "Contrôleur européen de la protection des données",
           "Conseil de résolution unique (CRU)", "Banque européenne d'investissement"],
}
EU_HARD_CASES = [
    "an organisation referred to by its acronym alone after it was defined once (tag every acronym mention)",
    "a company named without its legal form in most mentions",
    "a member state acting as a party or submitting observations (organization), and the same country as territory (location)",
    "parties pseudonymised with initials (IR, JQ, XY) as the CJEU does",
    "a cited earlier case referred to by its short name (\"Urteil Simmenthal\", \"arrêt Factortame\")",
    "an EU institution referred to bare (\"die Kommission\", \"le Conseil\")",
    "a national authority with an acronym from the referring member state",
    "an anaphoric generic noun (\"die Stiftung\", \"la société\") that stays untagged",
    "a national court whose name contains its seat (\"Tribunale di Teramo\", one court span)",
    "a list of governments that submitted observations",
]


def _eu_company(gaz, rng, state, lang):
    name = gaz.surname(state)
    sector = rng.choice(SECTORS[lang])
    base = rng.choice([name, f"{name} {sector}", f"{name}-{gaz.surname(state)}", f"{sector} {name}"])
    forms = LEGAL_FORMS.get(state) or EU_LEGAL_FORMS[state]
    c = {"name": base if rng.random() < 0.35 else f"{base} {rng.choice(forms)}", "state": state}
    if rng.random() < 0.3:
        c["acronym"] = "".join(w[0] for w in re.findall(r"[A-ZÄÖÜ][\w-]*", base))[:4].upper() or None
        if not c["acronym"] or len(c["acronym"]) < 2:
            c.pop("acronym")
    return c


def eu_brief(gaz, rng, lang, doc_type, idx, wave):
    state = rng.choice(EU_STATES)
    ecthr = doc_type in ("egmr_urteil", "arret_cedh")
    parties = []
    for _ in range(rng.randint(1, 3)):
        if rng.random() < 0.5:
            p = _person(gaz, rng, state if state in ("AT", "DE") else "CH" if state == "LU" else state)
            p.pop("degree", None)
            if not ecthr and rng.random() < 0.7:
                p["cited_as_initials"] = "".join(rng.choice("ABCDEFGHIJKLMNOPRSTUVWXYZ") for _ in range(2))
            parties.append({"person": p})
        else:
            parties.append({"company": _eu_company(gaz, rng, rng.choice(EU_STATES), lang)})
    names = STATE_NAMES[lang]
    governments = rng.sample(sorted(names), rng.randint(0, 4))
    cited = []
    for _ in range(rng.randint(1, 4)):
        year = rng.randint(1964, 2024)
        party = gaz.surname(rng.choice(EU_STATES))
        cited.append({"short_name": party, "party_is": rng.choice(["company", "company", "person"]),
                      "case_number": f"{rng.choice('CT') if year > 1989 else 'C'}-{rng.randint(1, 820)}/{year % 100:02d}"
                      if year > 1988 else f"{rng.randint(1, 300)}/{year % 100:02d}",
                      "year": year})
    b = {
        "file": f"EU_{wave}_{idx:04d}_{doc_type}.md", "doc_type": doc_type, "jurisdiction": "EU", "lang": lang,
        "target_words": int(min(2500, max(500, rng.lognormvariate(6.9, 0.45)))),
        "member_state_of_origin": names.get(state, state),
        "referring_court": f"(a real court of {names.get(state, state)}; if its name contains a place, one court span)",
        "national_authority": f"(invent a public authority of {names.get(state, state)} with an acronym, "
                              "define the acronym once and then use it alone)",
        "parties": parties,
        "governments_observations": [names[g] for g in governments],
        "eu_bodies": rng.sample(EU_BODIES[lang], rng.randint(1, 3)),
        "judges": [_person(gaz, rng, rng.choice(EU_STATES), "judge") for _ in range(rng.randint(3, 5))],
        "advocate_general": None if ecthr else _person(gaz, rng, rng.choice(EU_STATES), "judge"),
        "representatives": [_person(gaz, rng, rng.choice(EU_STATES), "lawyer") for _ in range(rng.randint(1, 3))],
        "agents": [_person(gaz, rng, rng.choice(EU_STATES)) for _ in range(rng.randint(0, 3))],
        "cited_cases": cited,
        "hard_cases": rng.sample(EU_HARD_CASES, 3),
        "ocr_noise": rng.random() < 0.05,
    }
    # keep the cast consistent with the document type and the hard cases
    no_bench = re.search(r"kommission|commission|euipo", doc_type)
    if no_bench:  # Commission and EUIPO decisions: no judges, no Advocate General
        b["judges"], b["advocate_general"] = [], None
    if re.search(r"^eug_|tribunal_ue", doc_type):  # the General Court has no Advocates General
        b["advocate_general"] = None
    if any(h.startswith("a list of governments") for h in b["hard_cases"]) and len(b["governments_observations"]) < 2:
        b["governments_observations"] = [names[g] for g in rng.sample(sorted(names), 3)]
    if any(h.startswith("parties pseudonymised") for h in b["hard_cases"]) \
            and not any("cited_as_initials" in p.get("person", {}) for p in b["parties"]):
        p = _person(gaz, rng, "AT")
        p.pop("degree", None)
        p["cited_as_initials"] = "".join(rng.choice("ABCDEFGHIJKLMNOPRSTUVWXYZ") for _ in range(2))
        b["parties"].append({"person": p})
    for p in b["judges"] + b["representatives"] + b["agents"] + ([b["advocate_general"]] if b["advocate_general"] else []):
        p.pop("degree", None)
    return b


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=1000)
    ap.add_argument("--per-batch", type=int, default=6)
    ap.add_argument("--wave", default="v3")
    ap.add_argument("--seed", type=int, default=29)
    ap.add_argument("--pseudo-frac", type=float, default=0.2,
                    help="share of AT court documents written RIS-pseudonymised")
    ap.add_argument("--rare", action=argparse.BooleanOptionalAction, default=None,
                    help="v4 briefs: rare-label entities, oversampled types, degree chains, case hard cases "
                         "(default: on for waves from v4)")
    ap.add_argument("--eu", action="store_true", help="EU wave: CJEU/GC/AG/Commission/EUIPO/ECtHR documents")
    ap.add_argument("--fr-share", type=float, default=0.4, help="EU wave: share of French documents")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    gaz = Gazetteer(rng=rng)
    if args.eu:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for i in range(args.docs):
                lang = "fr" if rng.random() < args.fr_share else "de"
                b = eu_brief(gaz, rng, lang, EU_TYPES[lang][i % len(EU_TYPES[lang])], i + 1, args.wave)
                b["batch"] = f"{args.wave}_b{i // args.per_batch:03d}"
                fh.write(json.dumps(b, ensure_ascii=False) + "\n")
        print(f"{args.docs} EU briefs in {-(-args.docs // args.per_batch)} batches -> {out}")
        return
    rare = args.rare if args.rare is not None else args.wave not in ("v1", "v2", "v3")
    plan = _weighted_types(rng, args.docs, OVERSAMPLE if rare else 1)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for i, (jur, lang, doc_type) in enumerate(plan):
            b = brief(gaz, rng, jur, lang, doc_type, i + 1, args.wave, rare, args.pseudo_frac)
            b["batch"] = f"{args.wave}_b{i // args.per_batch:03d}"
            fh.write(json.dumps(b, ensure_ascii=False) + "\n")
    print(f"{len(plan)} briefs in {-(-len(plan) // args.per_batch)} batches -> {out}")
    print(dict(collections.Counter(f"{j}-{l}" for j, l, _ in plan)))


if __name__ == "__main__":
    main()
