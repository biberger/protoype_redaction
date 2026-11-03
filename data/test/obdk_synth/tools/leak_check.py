"""Check that no synthetic entity was copied from the real OBDK decisions.

    python leak_check.py <docs.jsonl> <real_txt_dir> <out.json>

For person (incl. judge/lawyer), address, street, organization and identifier spans,
look for the span text (degrees stripped, whitespace normalised) verbatim in the real
corpus. Single-token names and generic organisations are skipped (common surnames and
real institutions occur legitimately). Hits are listed for review, not auto-removed.
"""

import json
import os
import re
import sys

docs_path, real_dir, out_path = sys.argv[1:4]
CHECK = {"person", "judge", "lawyer", "address", "street", "organization", "bank_account",
         "social_security_number", "tax_id", "company_register_number", "license_plate",
         "land_register_id", "id_document_number", "other_identifier", "phone_number", "email"}
DEGREES = re.compile(r"\b(?:Dr|Mag|MMag|DDr|Prof|Univ\.-Prof|Ing|DI|Dipl\.-Ing|Mag\.a|LL\.M|MBA|MSc|BSc|BA|PhD)\.?\s*")
INSTITUTIONS = re.compile(r"(?i)rechtsanwaltskammer|generalprokuratur|rechtsanwaltskammertag|finanzamt|"
                          r"staatsanwaltschaft|bezirkshauptmannschaft|ausschu|magistrat|ministerium|republik|"
                          r"versorgungseinrichtung|gebietskrankenkasse|sozialversicherung|landesregierung|kommission")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("-\n", "").replace("\n", " ")).strip()


corpus = "\n".join(
    norm(open(os.path.join(real_dir, f), encoding="utf-8").read())
    for f in os.listdir(real_dir) if f.endswith(".txt")
)
needles = {}
for line in open(docs_path, encoding="utf-8"):
    rec = json.loads(line)
    for s in rec["spans"]:
        if s["label"] not in CHECK:
            continue
        t = norm(s["text"])
        if s["label"] in ("person", "judge", "lawyer"):
            t = norm(DEGREES.sub("", t)).rstrip("s'")
            if len(t.split()) < 2 or "*" in t:
                continue
        elif s["label"] == "organization":
            if INSTITUTIONS.search(t) or len(t) < 8:
                continue
        elif len(re.sub(r"\D", "", t)) < 5 and s["label"] not in ("address", "street", "email"):
            continue
        if s["label"] == "street" and len(t) < 10:
            continue
        needles.setdefault((s["label"], t), set()).add(rec["doc_id"])

hits = [{"label": lab, "text": t, "docs": sorted(d)} for (lab, t), d in sorted(needles.items()) if t in corpus]
json.dump({"checked": len(needles), "hits": hits}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"checked {len(needles)} distinct entity strings, {len(hits)} found in the real corpus")
for h in hits:
    print(f"  {h['label']:22s} {h['text']!r}  in {', '.join(h['docs'][:3])}")
