# Isel v3 in the anonymisation service

Model: `sb-aiss/isel-v3` (private), folder `best/`. Post-processing files in the same repo under `postprocess/`:
`thresholds.json`, `postprocess.py`, `common_capitalized.txt` (also in this repository: `models/isel-v3/` and
`legalner/postprocess.py`).

## Pipeline per document

1. **One model call per page** with all labels, 96-word chunks, and the **lowest** threshold of `thresholds.json`
   (0.10), so that every candidate comes back with its confidence:

   ```python
   res = model.extract_entities_long(page_text, PROD_QUERY, threshold=0.10, chunk_size=96, chunk_overlap=24,
                                     include_spans=True, include_confidence=True)
   ```

   `PROD_QUERY` = person, organization, address, street, location, case number, bank account, social security
   number, tax id, company register number, license plate, land register id, id document number, other identifier,
   phone number, email, date of birth, court, date, legal norm, country.

2. **Per-label threshold**: keep a candidate if its confidence ≥ `thresholds[label]` (labels with spaces written with
   underscores). Spans labelled court, date, legal norm or country are **not masked** but kept as **protected
   regions** for step 4. Location/organization spans that are a country name are dropped (as before).
3. **Nesting**: of nested masked spans the longest wins (as before).
4. **Name propagation, once per document after all pages**: `postprocess.propagate(page_texts, page_masks,
   page_protected)` adds every further occurrence of found persons (full name, surname alone, capitals, genitive),
   organisations (full name, name without legal form, abbreviation defined in parentheses) and identifiers (exact
   repeats), never inside protected regions and never for common capitalised words.

In this repository steps 1-3 are `legalner.prodeval.predict_cands` (with the threshold), `select(cands,
thresholds)` and `protected(cands, thresholds)`; step 4 is `legalner.prodeval.propagate_docs` /
`legalner.postprocess.propagate`. The code is pure Python and can be vendored.

```python
import json
from legalner.prodeval import predict_cands, select, protected
from legalner.postprocess import propagate

thresholds = json.load(open("thresholds.json"))
query_t = min(thresholds.values())
cands = [predict_cands(model, t, 96, query_t) for t in page_texts]
masks = [select(c, thresholds) for c in cands]
prot = [protected(c, thresholds) for c in cands]
masks = propagate(page_texts, masks, prot)          # [(start, end, label)] per page
```

## Effect (production mode, 96-word chunks; gold_at, MAPA_v2, OBDK synthetic, regression cases)

| Variant | PII char recall | leaked mentions | precision | visible text masked |
|---|---:|---:|---:|---:|
| global 0.5 (current) | 0.954 | 5.7 % | 0.978 | 0.5 % |
| per-label thresholds | 0.964 | 4.7 % | 0.972 | 0.9 % |
| propagation | 0.960 | 5.0 % | 0.972 | 0.9 % |
| **thresholds + propagation** | **0.968** | **4.2 %** | 0.967 | 1.1 % |

Leaked mentions per set, current → thresholds + propagation: gold 2.2 % → 1.8 %, OBDK 5.6 % → 4.9 %, MAPA_v2 (EU)
20.9 % → 8.5 %, regression cases 2.2 % → 1.4 %. Speed is unchanged (one model call; propagation is a regex pass).
