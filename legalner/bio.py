"""Turn pre-tokenised BIO sequences into text with character-offset spans."""
NO_SPACE_BEFORE = {",", ".", ";", ":", "!", "?", ")", "]", "}", "%", "“", "'", "»"}
NO_SPACE_AFTER = {"(", "[", "{", "„", "«", "/"}


def detokenize(tokens):
    """Join tokens with light punctuation rules; return (text, [(start, end)])."""
    parts, offsets, pos = [], [], 0
    for i, tok in enumerate(tokens):
        if i and not (tok in NO_SPACE_BEFORE or tokens[i - 1] in NO_SPACE_AFTER or tok == "/"):
            parts.append(" ")
            pos += 1
        parts.append(tok)
        offsets.append((pos, pos + len(tok)))
        pos += len(tok)
    return "".join(parts), offsets


def bio_spans(tags):
    """Return [(type, first_token, last_token_inclusive)] from BIO tags.

    An I- tag without a matching open entity starts a new one (lenient, as in
    seqeval's default mode)."""
    spans, cur = [], None
    for i, tag in enumerate(tags):
        if tag.startswith("B-") or (tag.startswith("I-") and (cur is None or cur[0] != tag[2:])):
            cur = [tag[2:], i, i]
            spans.append(cur)
        elif tag.startswith("I-"):
            cur[2] = i
        else:
            cur = None
    return [tuple(s) for s in spans]


def bio_to_record(tokens, tags):
    """Return (text, [(type, start, end)]) with character offsets (end exclusive)."""
    text, offsets = detokenize(tokens)
    return text, [(t, offsets[a][0], offsets[b][1]) for t, a, b in bio_spans(tags)]
