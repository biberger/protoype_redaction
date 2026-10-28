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
