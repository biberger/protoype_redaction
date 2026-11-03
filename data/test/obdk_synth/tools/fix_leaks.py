"""Rename persons whose full name also occurs in the real corpus, and normalise TZ prefixes.

    python fix_leaks.py <raw_dir> <leak.json> <real_txt_dir>

For every person/judge/lawyer hit of leak_check.py, the surname is replaced in the hit
documents only (all mentions, genitives included) by a surname that occurs nowhere in the
real corpus and nowhere in the synthetic set. Prints the rename map.
"""

import json
import os
import pathlib
import re
import sys

raw_dir, leak_path, real_dir = sys.argv[1:4]
POOL = ["Wallnöfer", "Kogelnig", "Pirkhuber", "Stranzinger", "Moosleitner", "Hochleitner", "Eggenberger",
        "Schrattenecker", "Wiesinger", "Pühringer", "Kronawetter", "Grabmayr", "Aschauer", "Haslinger",
        "Rabensteiner", "Zehentner", "Thalhammer", "Feichtlbauer", "Kranewitter", "Lindorfer", "Hofstädter",
        "Spitzbart", "Tiefengraber", "Wurzinger", "Leopoldseder", "Grünberger", "Stockhammer", "Fuchsluger",
        "Reischenböck", "Wimmleitner", "Edlinger", "Sturmlechner", "Kaltseis", "Rauchenbichler", "Unterrainer",
        "Hirschbichler", "Ploberger", "Ganglbauer", "Brandauer", "Seebacher"]

real = "\n".join(open(os.path.join(real_dir, f), encoding="utf-8").read()
                 for f in os.listdir(real_dir) if f.endswith(".txt"))
files = {p.stem: p for p in pathlib.Path(raw_dir).rglob("*.md")}
synth = "\n".join(p.read_text(encoding="utf-8") for p in files.values())
PRE = ["Hinter", "Ober", "Unter", "Mitter", "Brunn", "Wald", "Moos", "Stein", "Holz", "Eben", "Grub", "Lind",
       "Reit", "Feld", "Kogl", "Rain", "Thal", "Wies", "Egg", "Asch", "Hasl", "Kron", "Sees", "Pirk"]
SUF = ["huber", "bauer", "leitner", "egger", "maier", "bichler", "lechner", "gruber", "hofer", "moser",
       "reiter", "wieser", "thaler", "steiner", "berger", "rainer", "stätter", "wallner"]
POOL += [p + s for s in SUF for p in PRE if not (p.lower().endswith(s[:2]))]
free = [s for s in dict.fromkeys(POOL) if s not in real and s not in synth]
print(f"{len(free)} free surnames")

plan = {}
for h in json.load(open(leak_path, encoding="utf-8"))["hits"]:
    if h["label"] not in ("person", "judge", "lawyer"):
        continue
    first, surname = h["text"].split()[0], h["text"].split()[-1]
    if first.endswith("."):  # "G. Wien": initial + common word, no real person behind it
        continue
    for doc in h["docs"]:
        plan.setdefault(doc, {}).setdefault(surname, None)
for doc, names in plan.items():
    for old in names:
        names[old] = free.pop(0)

tz = re.compile(r"\[\[case_number\|TZ\s+")
for doc, names in sorted(plan.items()):
    p = files[doc]
    t = p.read_text(encoding="utf-8")
    for old, new in names.items():
        t = re.sub(rf"(?<![\w-]){re.escape(old)}(?=s\b|'|\b)", new, t)
        print(f"{doc}: {old} -> {new}")
    p.write_text(t, encoding="utf-8")
n = 0
for p in files.values():
    t = p.read_text(encoding="utf-8")
    t2, k = tz.subn("TZ [[case_number|", t)
    if k:
        p.write_text(t2, encoding="utf-8")
        n += k
print(f"TZ prefixes moved outside: {n}")
