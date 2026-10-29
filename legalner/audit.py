"""Rule-based audit of canonical records against data/synthetic/GENERATION.md.

Complements the strict parser (which checks tag syntax and untagged repeats)
with checks on span content:

- forms of address or rank titles inside person spans (Herr, Mme, Me, Hofrat …)
- dates without a day ("März 2024"), gazette references (BGBl., JO) tagged legal_norm
- identifiers whose check digit is wrong (IBAN, AT SV-Nr, FN, ATU, DE USt-IdNr,
  RV-Nr, AHV, CHE-UID, NIR, SIREN/SIRET, BE enterprise number, DE driving licence)
- identifier-shaped surfaces under the wrong label (an IBAN tagged tax_id)

    python -m legalner.audit data/canonical/synthetic.jsonl [--json report.json]
"""
import argparse
import collections
import json
import re

from legalner import fake_ids as F

PERSON_LABELS = {"person", "judge", "lawyer"}
ADDRESS_FORMS = re.compile(
    r"^(Herr|Herrn|Frau|Fräulein|Fa\.|M\.|MM\.|Mme|Mmes|Mlle|Me|Maître|Monsieur|Madame|"
    r"Hofrat|Hofrätin|Senatspräsident(in)?|Präsident(in)?|Richter(in)?|Rechtsanwalt|"
    r"Rechtsanwältin|Notar(in)?|RA|RAin|GrInsp|RevInsp|BezInsp|AbtInsp|Insp|Kommissar)\s")
DAY_RE = re.compile(r"(?i)(?<!\d)\d{1,2}(?!\d)|\*|\b[a-zäöü]+s?ten\b|\b(1er|premier|erste[nr]?)\b|"
                    r"\b(un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|"
                    r"quatorze|quinze|seize|vingt|trente)\b")
GAZETTE_RE = re.compile(r"^(BGBl|LGBl|JO|J\.O\.|ABl|Amtsblatt|Journal officiel|Moniteur belge|AS \d|SR \d)")

IBAN_SHAPE = re.compile(r"\b([A-Z]{2}\d{2}(?: ?[\dA-Z]{4}){2,7}(?: ?[\dA-Z]{1,3})?)\b")


def identifier_problems(label, text, jurisdiction):
    """Return a list of (kind, detail) for one identifier span."""
    t = text.strip()
    compact = re.sub(r"[\s.\-/]", "", t)
    out = []

    def check(ok, what):
        if not ok:
            out.append(("bad_check_digit", f"{what}: {t!r}"))

    m = IBAN_SHAPE.search(t)
    if m and m.group(1)[:2] in F.IBAN_BBAN_LEN and \
            len(m.group(1).replace(" ", "")) == 4 + F.IBAN_BBAN_LEN[m.group(1)[:2]]:
        if label != "bank_account":
            out.append(("wrong_label", f"IBAN tagged {label}: {t!r}"))
        else:
            check(F.iban_is_valid(m.group(1)), "IBAN")
    if re.search(r"\bATU\s?\d{8}\b", t):
        if label != "tax_id":
            out.append(("wrong_label", f"ATU tagged {label}: {t!r}"))
        check(F.uid_at_is_valid(re.search(r"ATU\s?\d{8}", t).group()), "AT UID")
    if re.fullmatch(r"(DE|USt-?IdNr\.?:?)\s?\d{9}", t):
        check(F.ust_idnr_de_is_valid(t), "DE USt-IdNr")
    if re.search(r"\bCHE-?\d{3}\.\d{3}\.\d{3}", t):
        if label not in ("company_register_number", "tax_id"):
            out.append(("wrong_label", f"CHE-UID tagged {label}: {t!r}"))
        check(F.che_uid_is_valid(re.search(r"CHE-?\d{3}\.\d{3}\.\d{3}", t).group()), "CHE-UID")
    if label == "company_register_number" and jurisdiction == "AT" and re.fullmatch(r"(FN\s*)?\d{1,6}\s?[a-z]", t):
        check(F.fn_is_valid(t), "FN")
    if label == "social_security_number":
        if jurisdiction == "AT" and re.fullmatch(r"\d{4}\s?\d{6}", t):
            check(F.svnr_is_valid(t), "AT SV-Nr")
        elif t.startswith("756"):
            check(F.ahv_is_valid(t), "AHV")
        elif jurisdiction == "DE" and re.fullmatch(r"\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}", t):
            check(F.rvnr_is_valid(t), "RV-Nr")
        elif jurisdiction == "BE" and re.fullmatch(r"\d{2}\.?\d{2}\.?\d{2}-?\d{3}\.?\d{2}", t):
            check(F.be_nrn_is_valid(t), "BE national register no.")
        elif jurisdiction == "LU" and len(re.sub(r"\D", "", t)) == 13 and re.fullmatch(r"[\d ]+", t):
            check(F.lu_matricule_is_valid(t), "LU matricule")
        elif jurisdiction in ("FR", "BE", "LU") and re.fullmatch(r"[12](\s?\d|\s?2[AB]){12,13}\s?\d{2}", t):
            check(F.nir_is_valid(t), "NIR")
    if jurisdiction == "FR" and label in ("company_register_number", "tax_id"):
        digits = re.sub(r"\D", "", t)
        if re.fullmatch(r"(FR\s?\d{2}\s?)?[\d ]{9,17}", t.replace("RCS ", "")) and len(digits) in (9, 14):
            check(F.siren_is_valid(digits), "SIREN/SIRET")
        elif t.startswith("FR") and len(digits) == 11:
            check(F.siren_is_valid(digits[2:]) and int(digits[:2]) == (12 + 3 * (int(digits[2:]) % 97)) % 97,
                  "FR TVA")
    if jurisdiction == "BE" and label in ("company_register_number", "tax_id"):
        digits = re.sub(r"\D", "", t)
        if len(digits) == 10:
            check(F.be_enterprise_is_valid(digits), "BE enterprise no.")
    if label == "id_document_number" and jurisdiction == "DE" and re.fullmatch(r"[A-Z0-9]{9}[0-9X]\d", compact):
        check(F.id_document_is_valid(compact, "DE", "driving_licence"), "DE Führerscheinnummer")
    del compact
    return out


def span_problems(rec, span):
    label, text = span["label"], span["text"]
    out = []
    if label in PERSON_LABELS and ADDRESS_FORMS.match(text):
        out.append(("title_in_span", repr(text)))
    if label == "date" and not DAY_RE.search(text):
        out.append(("date_without_day", repr(text)))
    if label == "legal_norm" and GAZETTE_RE.match(text):
        out.append(("gazette_reference", repr(text)))
    if label in ("bank_account", "social_security_number", "tax_id", "company_register_number",
                 "id_document_number", "other_identifier", "license_plate", "phone_number"):
        out += identifier_problems(label, text, rec["jurisdiction"])
    return out


def audit(records):
    """Return (problems, per-label span counts); problems are dicts."""
    problems, counts = [], collections.Counter()
    for rec in records:
        for span in rec["spans"]:
            counts[span["label"]] += 1
            for kind, detail in span_problems(rec, span):
                problems.append({"doc": rec["doc_id"], "label": span["label"],
                                 "kind": kind, "detail": detail})
    return problems, counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", nargs="+", help="canonical JSONL files")
    ap.add_argument("--json", help="write the problem list here")
    args = ap.parse_args(argv)
    from legalner.build import read_records
    problems, counts = audit(list(read_records(args.data)))
    by_label = collections.Counter(p["label"] for p in problems)
    print(f"{'label':24s} {'spans':>6s} {'flagged':>7s} {'rate':>6s}")
    for label, n in counts.most_common():
        k = by_label.get(label, 0)
        print(f"{label:24s} {n:6d} {k:7d} {k / n:6.1%}")
    print("\nby kind:", dict(collections.Counter(p["kind"] for p in problems)))
    for p in problems:
        print(f"  {p['doc']}: [{p['label']}] {p['kind']} {p['detail']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(problems, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
