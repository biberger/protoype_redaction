import random

import pytest

from legalner import fake_ids
from legalner.bio import bio_spans, bio_to_record
from legalner.build import augment, query_labels, to_example
from legalner.evaluate import score
from legalner.schema import LABELS, SOURCES
from legalner.sources.ler import LABEL_MAP, convert_row
from legalner.tagged import TagError, parse_file, strip_tags, v1_identifier_label


def write_doc(tmp_path, body, header="doc_type: test\njurisdiction: AT\nlang: de"):
    path = tmp_path / "doc.md"
    path.write_text(f"---\n{header}\n---\n{body}", encoding="utf-8")
    return path


def test_role_tags_also_emit_person(tmp_path):
    recs, warnings = parse_file(write_doc(
        tmp_path, "Der [[court|OGH]] durch [[judge|Dr. Anna Taufner]]; [[judge|Taufner]] entschied."), "synthetic")
    labels = sorted((s["label"], s["text"]) for s in recs[0]["spans"])
    assert labels == [("court", "OGH"), ("judge", "Dr. Anna Taufner"), ("judge", "Taufner"),
                      ("person", "Dr. Anna Taufner"), ("person", "Taufner")]
    assert not warnings
    for s in recs[0]["spans"]:
        assert recs[0]["text"][s["start"]:s["end"]] == s["text"]


def test_lint_flags_untagged_surname(tmp_path):
    _, warnings = parse_file(write_doc(tmp_path, "[[person|Mag. Eva Brunnbauer]] klagt. Brunnbauer zahlt."), "synthetic")
    assert any("Brunnbauer" in w for w in warnings)


@pytest.mark.parametrize("body", ["[[nope|x]]", "[[person| x]]", "[[person|x]"])
def test_malformed_tags_raise(body):
    with pytest.raises(TagError):
        strip_tags(body, "t.md")


def test_v1_labels_map_to_canonical(tmp_path):
    recs, _ = parse_file(write_doc(tmp_path, "[[PERSON|Max Huber]], IBAN [[KENNNUMMER|AT61 1904 3002 3457 3201]], "
                                             "[[KONTAKT|max@huber.at]]"), "synthetic_v1")
    assert {s["label"] for s in recs[0]["spans"]} == {"person", "bank_account", "email"}


@pytest.mark.parametrize("surface,context,label", [
    ("FN 33209m", "", "company_register_number"),
    ("ATU63389210", "", "tax_id"),
    ("EZ 403", "", "land_register_id"),
    ("1204/7", "", "land_register_id"),
    ("L01X00T47", "Ausweisnummer ", "id_document_number"),
    ("2219 120784", "Ihre Gattin (VNR ", "social_security_number"),
    ("W-49172L", "", "license_plate"),
    ("KH-7731-0045-22", "Polizzennummer ", "other_identifier"),
])
def test_v1_identifier_split(surface, context, label):
    assert v1_identifier_label("KENNNUMMER", surface, context) == label


def test_bio_conversion_offsets():
    tokens = ["Nach", "§", "3", "Abs.", "1", "BGB", ",", "so", "der", "BGH", "."]
    tags = ["O", "B-GS", "I-GS", "I-GS", "I-GS", "I-GS", "O", "O", "O", "B-GRT", "O"]
    text, spans = bio_to_record(tokens, tags)
    assert text == "Nach § 3 Abs. 1 BGB, so der BGH."
    assert [(t, text[s:e]) for t, s, e in spans] == [("GS", "§ 3 Abs. 1 BGB"), ("GRT", "BGH")]
    assert bio_spans(["I-PER", "I-PER", "O", "I-ORG"]) == [("PER", 0, 1), ("ORG", 3, 3)]


def test_ler_mapping_covers_all_classes_and_schema():
    assert len(LABEL_MAP) == 19
    assert {lab for labs in LABEL_MAP.values() for lab in labs} <= SOURCES["ler"].coverage
    rec = convert_row(["Richter", "Dr.", "Meier", "am", "BGH"], ["O", "B-RR", "I-RR", "O", "B-GRT"], "train", 0)
    assert {(s["label"], s["text"]) for s in rec["spans"]} == {
        ("judge", "Dr. Meier"), ("person", "Dr. Meier"), ("court", "BGH")}


def test_query_labels_respect_coverage_and_nesting():
    rec = {"source": "ler", "spans": [{"label": "case_citation", "start": 0, "end": 5, "text": "x"}]}
    labels = query_labels(rec)
    assert "court" not in labels and "date" not in labels and "case_citation" in labels
    assert "judge" not in query_labels({"source": "synthetic_v1", "spans": []})
    assert all(src.coverage <= set(LABELS) for src in SOURCES.values())


def test_examples_have_span_mentions_and_negatives():
    rec = {"text": "Max Huber in Wien", "lang": "de", "source": "synthetic",
           "spans": [{"label": "person", "start": 0, "end": 9, "text": "Max Huber"}]}
    ex = to_example(rec, {"person", "location", "email"})
    assert ex["output"]["entities"]["person"] == [{"text": "Max Huber", "start": 0, "end": 9}]
    assert ex["output"]["entities"]["email"] == []
    rng = random.Random(0)
    for _ in range(50):
        aug = augment(rec, query_labels(rec), rng)
        assert aug["output"]["entities"]
        for mentions in aug["output"]["entities"].values():
            for m in mentions:
                assert rec["text"][m["start"]:m["end"]] == m["text"]


def test_score_counts_and_pii_recall():
    rec = {"source": "synthetic", "jurisdiction": "AT", "text": "Max Huber, 1.1.2020",
           "spans": [{"label": "person", "start": 0, "end": 9, "text": "Max Huber"},
                     {"label": "date", "start": 11, "end": 19, "text": "1.1.2020"}]}
    report = score([rec], [{"person": {(0, 3)}, "date": {(11, 19)}}])
    assert report["scores"]["all|date"]["f1"] == 1.0
    assert report["scores"]["all|person"]["f1"] == 0.0
    assert report["pii_char_recall"] == pytest.approx((3 + 8) / (9 + 8))


def test_fake_ids_are_valid():
    rng = random.Random(1)
    for country in fake_ids.IBAN_BBAN_LEN:
        assert fake_ids.iban_is_valid(fake_ids.iban(country, rng))
    assert fake_ids.svnr_is_valid(fake_ids.svnr(rng))
    assert fake_ids.iban_is_valid("AT61 1904 3002 3457 3201")  # published example IBAN


@pytest.mark.parametrize("gen,valid", [
    ("fn", "fn_is_valid"), ("uid_at", "uid_at_is_valid"), ("svnr", "svnr_is_valid"),
    ("ahv", "ahv_is_valid"), ("nir", "nir_is_valid"), ("che_uid", "che_uid_is_valid"),
    ("ust_idnr_de", "ust_idnr_de_is_valid"), ("rvnr", "rvnr_is_valid"),
    ("siren", "siren_is_valid"), ("siret", "siren_is_valid"), ("be_enterprise", "be_enterprise_is_valid"),
])
def test_fake_ids_validate(gen, valid):
    rng = random.Random(0)
    assert all(getattr(fake_ids, valid)(getattr(fake_ids, gen)(rng)) for _ in range(200))


def test_fake_id_validators_on_published_examples():
    assert fake_ids.uid_at_is_valid("ATU13585627")         # BMF example
    assert fake_ids.ust_idnr_de_is_valid("DE136695976")
    assert fake_ids.rvnr_is_valid("65 170839 J 003")
    assert fake_ids.siren_is_valid("780 129 987")
    assert not fake_ids.siren_is_valid("780 129 988")
    assert not fake_ids.che_uid_is_valid("CHE-116.281.711")


def test_audit_flags_titles_dates_and_check_digits():
    from legalner.audit import audit
    rec = {"doc_id": "d", "jurisdiction": "AT", "spans": [
        {"label": "lawyer", "text": "Me Anne Roux"}, {"label": "date", "text": "März 2024"},
        {"label": "date", "text": "1er mars 2024"}, {"label": "tax_id", "text": "ATU13585628"},
        {"label": "tax_id", "text": "AT61 1904 3002 3457 3201"}, {"label": "legal_norm", "text": "ABGB"}]}
    kinds = sorted(p["kind"] for p in audit([rec])[0])
    assert kinds == ["bad_check_digit", "date_without_day", "title_in_span", "wrong_label"]


def test_untagged_act_names_are_linted(tmp_path):
    _, warnings = parse_file(write_doc(
        tmp_path, "Nach [[legal_norm|§ 1 MRG]] gilt das MRG; vgl. Art. 15 DSGVO."), "synthetic")
    assert [w.split("untagged legal act ")[1] for w in warnings] == ["'MRG' (tag as legal_norm)",
                                                                      "'Art. 15 DSGVO' (tag as legal_norm)"]


def test_untagged_citations_and_court_names_are_linted(tmp_path):
    _, warnings = parse_file(write_doc(
        tmp_path, "Le [[court|TF]] (Tribunal fédéral) applique l'art. 257d al. 1 CO.",
        header="doc_type: test\njurisdiction: CH\nlang: fr"), "synthetic")
    assert any("'Tribunal fédéral'" in w for w in warnings)
    assert any("untagged norm citation 'art. 257d al. 1 CO'" in w for w in warnings)


class _FakeGaz:
    def person(self, home="AT"):
        return "Elif Brandstätter"

    def surname(self, home="AT"):
        return "Kovačević"

    def address(self, country="AT"):
        return "Lederergasse 7/3, 4020 Linz"

    def town(self, country="AT"):
        return ("Wels", "4600")


def test_ris_fixture_annotation():
    import pathlib
    from legalner.sources import ris
    text = ris.markup_to_text((pathlib.Path(__file__).parent / "fixtures" / "ris_ogh.html").read_text())
    assert "Kopf" in text and "\xa0" not in text and "OGH 7Ob161" not in text
    ref = {"id": "JJT_TEST", "case_numbers": ["7Ob161/26s"], "court": "OGH", "app": "Justiz"}
    out, spans = ris.annotate(text, ref, _FakeGaz(), random.Random(0))
    got = {(lab, t) for lab, s, e, t in spans}
    assert all(out[s:e] == t for _, s, e, t in spans)
    for expected in [("court", "Oberste Gerichtshof"), ("judge", "Dr. Solé"), ("judge", "Mag. Malesich"),
                     ("judge", "MMag. Matzka"), ("judge", "Dr. Weber"), ("judge", "Mag. Fitz"),
                     ("person", "Dr. Solé"), ("person", "Mag. Elif Brandstätter"), ("lawyer", "Dr. Paul Huber"),
                     ("court", "Oberlandesgerichts Linz"), ("date", "12. März 2026"),
                     ("case_number", "2 R 14/26k-31"), ("court", "Landesgerichts Wels"), ("date", "4. 11. 2025"),
                     ("case_number", "26 Cg 77/24m-24"), ("date", "3. Mai 2021"), ("case_number", "7 Ob 59/22w"),
                     ("address", "Lederergasse 7/3, 4020 Linz"), ("person", "Kovačević"),
                     ("organization", "Kovačević GmbH")]:
        assert expected in got, expected
    assert "*****" not in out
    recs = ris.to_records(out, spans, ref)
    assert recs and all(r["text"][s["start"]:s["end"]] == s["text"] for r in recs for s in r["spans"])
