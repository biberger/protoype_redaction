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
        "versicherungsschreiben", "datenschutzauskunft", "vollmacht"]),
    ("DE", "de"): (0.20, [
        "bgh_urteil", "olg_urteil", "lg_urteil", "ag_urteil", "arbeitsgericht_urteil", "lag_urteil",
        "sozialgericht_urteil", "vg_urteil", "finanzgericht_urteil", "strafbefehl", "anklageschrift",
        "bescheid_finanzamt", "bescheid_jobcenter", "abmahnung", "klageschrift", "mietvertrag",
        "kaufvertrag_notariell", "arbeitsvertrag", "handelsregisterauszug", "grundbuchauszug",
        "anwaltsschreiben", "mahnbescheid"]),
    ("CH", "de"): (0.10, [
        "bger_urteil", "obergericht_urteil", "kantonsgericht_entscheid", "handelsgericht_urteil", "strafbefehl",
        "zahlungsbefehl", "verfuegung_migrationsamt", "mietvertrag", "arbeitsvertrag", "arbeitszeugnis",
        "handelsregisterauszug", "anwaltsschreiben"]),
    ("CH", "fr"): (0.05, [
        "bger_arret", "arret_cour_de_justice", "jugement_tribunal_des_baux", "ordonnance_penale",
        "contrat_de_bail", "lettre_avocat"]),
    ("FR", "fr"): (0.12, [
        "arret_cour_de_cassation", "arret_cour_d_appel", "jugement_tribunal_judiciaire", "jugement_prud_hommes",
        "jugement_correctionnel", "arret_conseil_d_etat", "jugement_tribunal_administratif", "ordonnance_refere",
        "acte_notarie", "contrat_de_bail", "contrat_de_travail", "mise_en_demeure", "proces_verbal_audition",
        "assignation", "extrait_kbis"]),
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
COURT_DOC_PREFIXES = ("ogh", "olg", "lg", "bg", "asg", "vwgh", "vfgh", "bvwg", "lvwg", "bfg", "bgh", "ag_",
                      "lag", "sozial", "vg_", "finanz", "bger", "ober", "kantons", "handelsgericht", "arret",
                      "jugement", "fl_ogh", "landgericht", "firmenbuch")


def _weighted_types(rng, n):
    keys = list(MATRIX)
    counts = collections.Counter(rng.choices(keys, [MATRIX[k][0] for k in keys], k=n))
    out = []
    for key, k in counts.items():
        types = MATRIX[key][1]
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
        company.update(register=F.hrb(rng), register_court=rng.choice(F.DE_REGISTER_COURTS),
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


def _person(gaz, rng, jur, role=None):
    home = jur if jur != "LI" else "AT"
    gender = rng.choice("MF")
    p = {"name": gaz.person(home, gender), "gender": gender}
    if rng.random() < 0.25 and jur in ("AT", "DE", "LI"):
        p["degree"] = rng.choice(["Dr.", "Mag.", "DI", "Ing.", "MMag.", "Dr. med.", "BSc", "MBA"])
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


def brief(gaz, rng, jur, lang, doc_type, idx, wave):
    is_court = doc_type.startswith(COURT_DOC_PREFIXES)
    n_persons = rng.randint(2, 7)
    b = {
        "file": f"{jur}_{wave}_{idx:04d}_{doc_type}.md", "doc_type": doc_type, "jurisdiction": jur, "lang": lang,
        "target_words": int(min(2500, max(300, rng.lognormvariate(6.7, 0.5)))),
        "persons": [_person(gaz, rng, jur) for _ in range(n_persons)],
        "lawyers": [_person(gaz, rng, jur, "lawyer") for _ in range(rng.randint(0, 3 if is_court else 1))],
        "judges": [_person(gaz, rng, jur, "judge") for _ in range(rng.randint(1, 5) if is_court else 0)],
        "companies": [_company(gaz, rng, jur, lang) for _ in range(rng.randint(0, 3))],
        "addresses": [_address(gaz, rng, jur) for _ in range(rng.randint(1, 3))],
        # judgments rarely contain IBANs or social security numbers; forcing them in made texts implausible
        "identifiers": {} if is_court else _identifiers(rng, jur),
        "pseudonymised": jur == "AT" and is_court and rng.random() < 0.2,
        "ocr_noise": rng.random() < 0.1,
        "hard_cases": rng.sample([
            "a person whose surname is also a place or common word", "surname-only coreference",
            "a person in the genitive (\"Hubers Antrag\")", "a long chain of norm citations",
            "a table written as text", "a list of several parties", "a person with a particle (von, de, van der)",
            "a double-barrelled or hyphenated name", "an abbreviation of an authority after its full name",
            "dates in two different spellings", "an address split over two lines"], 2),
    }
    if not is_court:
        b["judges"] = []
    return b


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=1000)
    ap.add_argument("--per-batch", type=int, default=6)
    ap.add_argument("--wave", default="v3")
    ap.add_argument("--seed", type=int, default=29)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    gaz = Gazetteer(rng=rng)
    plan = _weighted_types(rng, args.docs)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for i, (jur, lang, doc_type) in enumerate(plan):
            b = brief(gaz, rng, jur, lang, doc_type, i + 1, args.wave)
            b["batch"] = f"{args.wave}_b{i // args.per_batch:03d}"
            fh.write(json.dumps(b, ensure_ascii=False) + "\n")
    print(f"{len(plan)} briefs in {-(-len(plan) // args.per_batch)} batches -> {out}")
    print(dict(collections.Counter(f"{j}-{l}" for j, l, _ in plan)))


if __name__ == "__main__":
    main()
