"""Canonical label schema shared by every data source.

Labels are lowercase English keys. GLiNER treats the label string as a
prompt, so each label also carries a description and German/French synonyms
that build.py can swap in during training (keeps the model robust to label
wording and preserves zero-shot behaviour).

Role labels (judge, lawyer) are *additional* labels on spans that are also
`person`; `person` is always the superset of every named natural person.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Label:
    description: str
    de: tuple = ()
    fr: tuple = ()
    group: str = "pii"  # pii | legal | other; only informs reporting


LABELS = {
    # --- natural persons -------------------------------------------------
    "person": Label(
        "Name of a natural person (parties, witnesses, judges, lawyers, officials), "
        "including academic degrees, pseudonyms like 'A*****' and initials; "
        "excluding forms of address (Herr, Frau) and job titles.",
        de=("Person", "Name einer Person", "natürliche Person"),
        fr=("personne", "nom de personne", "personne physique")),
    "judge": Label(
        "Name of a person acting as judge, court panel member or Rechtspfleger.",
        de=("Richter", "Richterin oder Richter"), fr=("juge", "magistrat")),
    "lawyer": Label(
        "Name of a person acting as attorney, defence counsel or notary.",
        de=("Rechtsanwalt", "Anwalt", "Notar"), fr=("avocat", "notaire")),
    # --- organisations ---------------------------------------------------
    "organization": Label(
        "Company, association, political party, authority, ministry, public body "
        "or law firm; not courts.",
        de=("Organisation", "Unternehmen oder Behörde", "Firma"),
        fr=("organisation", "entreprise ou administration")),
    "court": Label(
        "Court or tribunal, including abbreviations such as OGH, BGH, VwGH, LG Wien.",
        de=("Gericht",), fr=("tribunal", "juridiction", "cour"), group="legal"),
    # --- places ----------------------------------------------------------
    "address": Label(
        "Postal address or street with house number, including door, postcode and "
        "city when written together.",
        de=("Adresse", "Anschrift", "Wohnadresse"), fr=("adresse", "adresse postale")),
    "street": Label(
        "Name of a street or square without a house number.",
        de=("Straße", "Straßenname"), fr=("rue", "nom de rue")),
    "location": Label(
        "City, municipality, region, landscape or country that is not part of an address.",
        de=("Ort", "Ortsname", "Land oder Stadt"), fr=("lieu", "ville ou pays")),
    # --- time --------------------------------------------------------------
    "date": Label(
        "Day-precise calendar date in any spelling.",
        de=("Datum",), fr=("date",)),
    # --- identifiers -----------------------------------------------------
    "case_number": Label(
        "Case reference number of a court or authority (Geschäftszahl, Aktenzeichen).",
        de=("Geschäftszahl", "Aktenzeichen"), fr=("numéro de dossier", "numéro de rôle"),
        group="legal"),
    "bank_account": Label(
        "IBAN, BIC or bank account number.",
        de=("Bankverbindung", "IBAN", "Kontonummer"), fr=("compte bancaire", "IBAN")),
    "social_security_number": Label(
        "Social security or national insurance number.",
        de=("Sozialversicherungsnummer", "SV-Nummer"), fr=("numéro de sécurité sociale",)),
    "tax_id": Label(
        "Tax number or VAT identification number (Steuernummer, UID).",
        de=("Steuernummer", "UID-Nummer"), fr=("numéro fiscal", "numéro de TVA")),
    "company_register_number": Label(
        "Company register number such as FN 123456a, HRB 1234, CHE-123.456.789 or SIREN.",
        de=("Firmenbuchnummer", "Handelsregisternummer"), fr=("numéro RCS", "numéro SIREN")),
    "license_plate": Label(
        "Vehicle registration plate.",
        de=("Kennzeichen", "KFZ-Kennzeichen"), fr=("plaque d'immatriculation",)),
    "land_register_id": Label(
        "Land register identifier: Einlagezahl, Katastralgemeinde, plot number, Flurstück.",
        de=("Grundbuchsangabe", "Grundstücksnummer", "Einlagezahl"),
        fr=("référence cadastrale",)),
    "id_document_number": Label(
        "Number of a passport, identity card or driving licence.",
        de=("Ausweisnummer", "Reisepassnummer"), fr=("numéro de pièce d'identité",)),
    "other_identifier": Label(
        "Other personal identifier such as customer, policy, file or social-media account ID.",
        de=("Kennnummer", "Kundennummer"), fr=("identifiant",)),
    "phone_number": Label(
        "Telephone or fax number.",
        de=("Telefonnummer",), fr=("numéro de téléphone",)),
    "email": Label(
        "E-mail address.", de=("E-Mail-Adresse",), fr=("adresse e-mail", "courriel")),
    # --- legal references --------------------------------------------------
    "legal_norm": Label(
        "Citation of a statute, regulation or EU legal act with paragraph or article, "
        "e.g. '§ 879 Abs 3 ABGB', 'Art. 8 EMRK'.",
        de=("Gesetzesstelle", "Norm", "Gesetz"), fr=("disposition légale", "article de loi"),
        group="legal"),
    "case_citation": Label(
        "Full citation of a court decision (court, date and/or case number or reporter).",
        de=("Rechtsprechungszitat", "Entscheidungszitat"), fr=("référence jurisprudentielle",),
        group="legal"),
    "contract": Label(
        "Reference to a specific contract or treaty.",
        de=("Vertrag",), fr=("contrat",), group="legal"),
    "literature": Label(
        "Citation of legal literature (commentary, journal article, textbook).",
        de=("Literaturzitat", "Fundstelle"), fr=("doctrine",), group="legal"),
    "brand": Label(
        "Product or brand name.", de=("Marke", "Produktname"), fr=("marque",), group="other"),
}


@dataclass(frozen=True)
class Source:
    """A data source and the labels it annotates exhaustively.

    Only covered labels may be queried during training: querying an uncovered
    label would turn every unannotated mention into a false negative.
    `nested_conflicts` maps a label to labels that occur unannotated *inside*
    its spans; those are dropped from the query of any example containing it.
    """
    name: str
    coverage: frozenset
    nested_conflicts: dict = field(default_factory=dict)


_ALL = frozenset(LABELS)

SOURCES = {
    "synthetic_v1": Source(
        "synthetic_v1",
        _ALL - {"judge", "lawyer", "street", "case_citation", "contract",
                "literature", "brand", "id_document_number"}),
    "synthetic": Source("synthetic", _ALL - {"case_citation", "contract", "literature", "brand"}),
    "ler": Source(
        "ler",
        frozenset({"person", "judge", "lawyer", "organization", "court", "street",
                   "location", "legal_norm", "case_citation", "contract",
                   "literature", "brand"}),
        nested_conflicts={"case_citation": ("court",), "literature": ("person",)}),
}


def labels_for(source: str) -> list:
    return sorted(SOURCES[source].coverage)
