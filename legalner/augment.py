"""Span-safe training augmentations for production-like text (docs/PLAN.md, step 4 of the 2026-11 plan).

Production input is one page of a PDF text layer or OCR: letter-spaced letterheads ("R e c h t s a n w ä l t e"),
page headers, hard line wraps with hyphenation, broken spacing ("Eint ragung (en )"), OCR character swaps, and
windows of about 100 words. The model was trained on clean prose chunks, so build.py applies these to a share of
the training records:

- `layout_noise(rec, rng)`: one to three of letter-spacing, page break, line wrap, broken spacing, OCR swaps.
- `name_swap(rec, gaz, rng)`: replaces person names with names from the gazetteer decks (degrees, case, gender
  and genitive -s kept), so the training set covers the European name lists instead of a few favourites.
- `rewindow(records, rng)`: re-cuts the chunks of a document into windows of 50-700 words.

All of them rebuild the text from per-character (prefix, glyph, suffix) pieces: a span starts at the glyph of its
first character and ends after the glyph of its last one, so labels stay exact whatever is inserted or replaced.
"""
import collections
import re

from legalner.gazetteers import EUROPE, transliterate


def rebuild(rec, pre=None, core=None, post=None):
    """New record from per-character replacements: pre[i] + core[i] + post[i] stands for text[i]."""
    text = rec["text"]
    pre, core, post = pre or {}, core or {}, post or {}
    out, start_at, end_at = [], [], []
    pos = 0
    for i, ch in enumerate(text):
        p, c, q = pre.get(i, ""), core.get(i, ch), post.get(i, "")
        start_at.append(pos + len(p))
        end_at.append(pos + len(p) + len(c))
        out.append(p + c + q)
        pos += len(p) + len(c) + len(q)
    new_text = "".join(out)
    spans = []
    for s in rec["spans"]:
        a, b = start_at[s["start"]], end_at[s["end"] - 1]
        if b > a:
            spans.append(dict(s, start=a, end=b, text=new_text[a:b]))
    return dict(rec, text=new_text, spans=spans)


def _span_chars(rec):
    covered = [False] * len(rec["text"])
    for s in rec["spans"]:
        for i in range(s["start"], s["end"]):
            covered[i] = True
    return covered


# --- layout noise -------------------------------------------------------------------------------------------------

def letter_spacing(rec, rng):
    """Spread the letters of one or two short lines ("G E R N G R O S S  K Ö C K"), preferring the first lines."""
    text = rec["text"]
    lines, pos = [], 0
    for ln in text.split("\n"):
        if 3 <= len(ln.strip()) <= 45:
            lines.append((pos, pos + len(ln)))
        pos += len(ln) + 1
    if not lines:
        return rec
    head = [ln for ln in lines if ln[0] < 300] or lines
    post = {}
    for a, b in rng.sample(head, min(len(head), rng.choice((1, 1, 2)))):
        for i in range(a, b - 1):
            if text[i] != " ":
                post[i] = " "  # a space after every letter; the space between words becomes a double space
    return rebuild(rec, post=post)


def page_break(rec, rng):
    """Insert a page footer/header at a line boundary ("- 2 -", "Seite 2 von 4", "2/4")."""
    text = rec["text"]
    cuts = [m.end() for m in re.finditer(r"\n", text) if 0.2 * len(text) < m.end() < 0.9 * len(text)]
    if not cuts:
        return rec
    at = rng.choice(cuts)
    if at >= len(text):
        return rec
    k = rng.randint(2, 9)
    n = k + rng.randint(0, 6)
    header = rng.choice([f"- {k} -", f"Seite {k} von {n}", f"{k}/{n}", f"Seite {k}", f"– {k} –", f"Page {k}"])
    sep = rng.choice(["\n", "\n\n", "\n\f"])
    return rebuild(rec, pre={at: f"{header}{sep}"})


def line_wrap(rec, rng):
    """Hard-wrap long lines at 55-85 characters; long words crossing the margin are hyphenated ("Über-\ntragung")."""
    text = rec["text"]
    width = rng.randint(55, 85)
    core, post = {}, {}
    col, last_end = 0, 0
    for w in re.finditer(r"\S+", text):
        if "\n" in text[last_end:w.start()]:
            col = w.start() - (text.rfind("\n", 0, w.start()) + 1)
        elif col + len(w.group()) > width and text[w.start() - 1] == " ":
            word = w.group()
            if len(word) >= 8 and word.isalpha() and rng.random() < 0.4:
                cut = w.start() + rng.randint(3, len(word) - 4)
                post[cut - 1] = "-\n"
                col = w.end() - cut
                last_end = w.end()
                col += 1
                continue
            core[w.start() - 1] = "\n"
            col = 0
        col += len(w.group()) + 1
        last_end = w.end()
    return rebuild(rec, core=core, post=post)


def broken_spacing(rec, rng, p=0.04):
    """Stray spaces inside words and before closing brackets ("Eint ragung (en )")."""
    text = rec["text"]
    post = {}
    for w in re.finditer(r"[^\W\d_]{6,}", text):
        if rng.random() < p:
            post[w.start() + rng.randint(2, len(w.group()) - 3)] = " "
    pre = {m.start(): " " for m in re.finditer(r"\)", text) if rng.random() < p * 3}
    return rebuild(rec, pre=pre, post=post)


OCR_SWAPS = [("rn", "m"), ("m", "rn"), ("ü", "u"), ("ä", "a"), ("ö", "o"), ("ß", "B"), ("l", "1"), ("e", "c"),
             ("i", "l"), ("O", "0"), ("ii", "ü"), ("cl", "d")]


def ocr_swaps(rec, rng, p=0.006):
    """Typical OCR confusions (rn<->m, umlauts dropped, ß->B, l->1) at a low per-character rate."""
    text = rec["text"]
    core = {}
    i = 0
    while i < len(text):
        if text[i].isalpha() and rng.random() < p:
            for a, b in rng.sample(OCR_SWAPS, len(OCR_SWAPS)):
                if text.startswith(a, i):
                    core[i] = b
                    for j in range(i + 1, i + len(a)):
                        core[j] = ""
                    i += len(a) - 1
                    break
        i += 1
    return rebuild(rec, core=core)


TRANSFORMS = (letter_spacing, page_break, line_wrap, broken_spacing, ocr_swaps)


def layout_noise(rec, rng):
    for fn in rng.sample(TRANSFORMS, rng.choice((1, 1, 2, 3))):
        rec = fn(rec, rng)
    return dict(rec, meta=dict(rec.get("meta", {}), layout_noise=True))


# --- name swap ----------------------------------------------------------------------------------------------------

DEGREE_PRE = re.compile(r"^(?:(?:Univ\.-Prof\.|Prof\.|Priv\.-Doz\.|Dr\.(?:\s(?:med|iur|phil|techn|rer\.\s?nat)\.)?|"
                        r"DDr\.|Mag\.(?:\s\(FH\))?|MMag\.|Dipl\.-Ing\.|Dipl\.-Kfm\.|DI|Ing\.|lic\.\s?iur\.|"
                        r"Me|Mag\.a)\s+)+")
DEGREE_POST = re.compile(r"(?:,?\s+(?:MBA|BSc|MSc|B\.Sc\.|M\.Sc\.|LL\.M\.|PhD|BA|MA|MAS|MLaw|M\.A\.)"
                         r"(?:\s\([^)]{1,20}\))?)+$")
PARTICLE = {"von", "van", "der", "de", "da", "di", "del", "zu", "le", "la", "du", "ten", "ter", "den"}
NAME_TOKEN = re.compile(r"[A-ZÄÖÜÀ-ÝŁŚŻŹĆŃŠČŘŽĐ][a-zäöüßà-ÿłśżźćńšěčřžđ'’]+(?:-[A-ZÄÖÜÀ-Ý][a-zäöüßà-ÿ'’]+)?")
FEMALE_CUE = re.compile(r"(?:\bFrau|\bMme|\bMadame|\bdie\s(?:Klägerin|Beklagte|Zeugin|Antragstellerin|Beschuldigte)|"
                        r"\bin)\s*$")
MALE_CUE = re.compile(r"(?:\bHerrn?|\bM\.|\bMonsieur)\s*$")


def _parse(name):
    """(prefix, given tokens, surname, suffix) or None for initials, pseudonyms and other non-names."""
    pre = DEGREE_PRE.match(name)
    prefix = pre.group() if pre else ""
    rest = name[len(prefix):]
    post = DEGREE_POST.search(rest)
    suffix = post.group() if post else ""
    core = rest[:len(rest) - len(suffix)] if suffix else rest
    toks = core.split()
    if not toks or any("*" in t or re.fullmatch(r"\w\.?", t) for t in toks):
        return None
    if not all(NAME_TOKEN.fullmatch(t) or t.lower() in PARTICLE for t in toks):
        return None
    i = len(toks) - 1
    while i > 0 and toks[i - 1].lower() in PARTICLE:
        i -= 1
    return prefix, toks[:i], " ".join(toks[i:]), suffix


class NameSwapper:
    """Replaces person names consistently within a record, cycling through European name decks."""

    def __init__(self, gaz, rng, countries=None):
        self.gaz, self.rng = gaz, rng
        self.countries = [c for c in sorted(countries or EUROPE) if gaz.last.get(c)]
        self.gender = {}
        for (country, g), names in gaz.first.items():
            for n in names:
                self.gender.setdefault(n, g)

    def _country(self):
        # weighted by list size, so every name of every country is drawn about equally often
        if not hasattr(self, "_weights"):
            self._weights = [len(self.gaz.last[c]) + sum(len(self.gaz.first[(c, g)]) for g in "MF")
                             for c in self.countries]
        return self.rng.choices(self.countries, weights=self._weights)[0]

    def swap(self, rec):
        text = rec["text"]
        people = sorted((s for s in rec["spans"] if s["label"] == "person"), key=lambda s: s["start"])
        surnames, givens, core, seen = {}, {}, {}, set()
        for s in people:
            if (s["start"], s["end"]) in seen:
                continue
            seen.add((s["start"], s["end"]))
            parsed = _parse(s["text"])
            if not parsed:
                continue
            prefix, given, surname, suffix = parsed
            genitive = surname.endswith("s") and surname[:-1] in surnames and len(given) == 0
            key = surname[:-1] if genitive else surname
            if key not in surnames:
                country = self._country()
                surnames[key] = transliterate(self.gaz.last_name(country)), country
            new_last, country = surnames[key]
            new = prefix
            if given:
                gkey = " ".join(given)
                if gkey not in givens:
                    ctx = text[max(0, s["start"] - 25):s["start"]]
                    g = "F" if FEMALE_CUE.search(ctx) else "M" if MALE_CUE.search(ctx) else \
                        self.gender.get(given[0], self.rng.choice("MF"))
                    givens[gkey] = " ".join(transliterate(self.gaz.first_name(country, g)) for _ in given[:2])
                new += givens[gkey] + " "
            new += new_last + ("s" if genitive else "") + suffix
            body = s["text"]
            if body.isupper():
                new = new.upper()
            elif body.islower():
                new = new.lower()
            core[s["start"]] = new
            for j in range(s["start"] + 1, s["end"]):
                core[j] = ""
        if not core:
            return rec
        # the replacement sits on the first character; other spans on the same name follow it
        out = rebuild(rec, core=core)
        return dict(out, meta=dict(rec.get("meta", {}), name_swap=len(surnames)))


# --- windows ------------------------------------------------------------------------------------------------------

WINDOW_WORDS = ((50, 150, 0.4), (150, 350, 0.4), (350, 700, 0.2))


def _join(chunks):
    """One record from the consecutive chunks of a document (blank line between chunks)."""
    text, spans, uncovered = "", [], set()
    for c in chunks:
        if text:
            text += "\n\n"
        off = len(text)
        text += c["text"]
        spans += [dict(s, start=s["start"] + off, end=s["end"] + off) for s in c["spans"]]
        uncovered |= set(c.get("meta", {}).get("uncovered", ()))
    meta = dict(chunks[0].get("meta", {}))
    if uncovered:
        meta["uncovered"] = sorted(uncovered)
    return dict(chunks[0], text=text, spans=spans, meta=meta)


def _chunk_no(rec):
    m = re.search(r"#(\d+)$", rec["id"])
    return int(m.group(1)) if m else 0


def rewindow(records, rng, sizes=WINDOW_WORDS):
    """Re-cut each document's chunks into windows of a random word count (weights in `sizes`), cutting only at
    whitespace outside spans. Records of one document must share doc_id; order follows the chunk number."""
    by_doc = collections.defaultdict(list)
    for r in records:
        by_doc[r["doc_id"]].append(r)
    out = []
    for doc_id, chunks in by_doc.items():
        doc = _join(sorted(chunks, key=_chunk_no))
        text = doc["text"]
        inside = _span_chars(doc) + [False]
        starts = [m.start() for m in re.finditer(r"\S+", text)]
        pos, k = 0, 0
        while pos < len(text):
            lo, hi, _ = rng.choices(sizes, weights=[w for _, _, w in sizes])[0]
            want = rng.randint(lo, hi)
            first = next((i for i, s in enumerate(starts) if s >= pos), None)
            if first is None:
                break
            cut = starts[first + want] if first + want < len(starts) else len(text)
            while cut < len(text) and inside[cut - 1] and inside[cut]:  # never split a span
                cut = next((s for s in starts if s > cut), len(text))
            a = len(text[pos:cut]) - len(text[pos:cut].lstrip())
            seg_start, seg_end = pos + a, len(text[:cut].rstrip())
            if seg_end > seg_start:
                spans = [dict(s, start=s["start"] - seg_start, end=s["end"] - seg_start)
                         for s in doc["spans"] if seg_start <= s["start"] and s["end"] <= seg_end]
                out.append(dict(doc, id=f"{doc['id'].split('#')[0]}#w{k}", text=text[seg_start:seg_end], spans=spans,
                                meta=dict(doc.get("meta", {}), window_words=want)))
                k += 1
            pos = cut
    return out
