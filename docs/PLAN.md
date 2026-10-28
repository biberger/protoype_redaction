# Legal NER / redaction model: plan

Goal: one multilingual model that is especially strong on German legal text (Austria first,
then DACH, then France) and extracts persons, organisations, courts, addresses, identifiers
and legal references. Focus now: the large teacher model and its training data. Distilling
into a small CPU/browser student and adding a rules layer come later.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Architecture | GLiNER2.5 boundary model, base checkpoint `fastino/gliner2.5-multi-v1` | Multilingual (mDeBERTa-v3-base, 287M), open label set (zero-shot), no span-width cap, Apache-2.0 |
| Pretrain or fine-tune | Fine-tune on top, with replay data to keep zero-shot | GLiNER2's own training data is not public; redoing pretraining means rebuilding that corpus first |
| Label schema | One canonical schema (`legalner/schema.py`), every source mapped onto it | Different datasets tag differently; alignment happens at conversion time |
| Mixing sources with partial annotation | Per-source label coverage; only covered labels are queried | Prevents unannotated mentions from being trained as negatives |
| Synthetic data | Many parallel Haiku agents writing inline-tagged documents, validated by a strict parser and lint | Cheap, controllable, covers AT/CH/FR document types that no public dataset has |
| Compute | Rent a single 24–80 GB GPU per run | The model is small; full fine-tuning fits on one card |

### gliner2.5-multi-v1 vs gliner2-privacy-filter-PII-multi

| | `gliner2.5-multi-v1` | `gliner2-privacy-filter-PII-multi` |
|---|---|---|
| Architecture | boundary (start/end pairing), any span length up to `max_len` 4096 tokens | span grid, `max_width` 8 words |
| Encoder / size | mDeBERTa-v3-base, 287M | mDeBERTa-v3-base, 205M |
| Trained for | general IE: entities, classification, relations, records | 42 PII types only |
| Training data | not published | 4,910 synthetic texts in 7 languages, not published |
| Reported quality | general | SPY benchmark legal F1 0.477, precision 0.35–0.37 (over-predicts names) |
| Role here | **base for fine-tuning** | baseline to beat in evaluation |

The span model's 8-word cap is too short for court names ("Landesgericht für Zivilrechtssachen Wien"
is 4 words, but full addresses and organisation names with legal form often exceed 8), and its
small synthetic training set gives it weak precision.

### Is the original training data open?

- **GLiNER (v1):** yes. Pile-NER (`Universal-NER/Pile-NER-type`, English, labelled with ChatGPT, so
  OpenAI terms apply), `urchade/pile-mistral-v0.1` (Apache-2.0) and the multilingual
  `urchade/synthetic-pii-ner-mistral-v1` (en/fr/it/de/es, Apache-2.0).
- **GLiNER2 / GLiNER2.5:** no. The paper describes the corpus but Fastino has not released it
  (their only Hub dataset is `fastino/fast-decisions`, for classification).

We use the open GLiNER v1 data as **replay** to keep zero-shot ability.

## Label schema

Canonical labels (lowercase English keys, with German/French synonyms used as alternative prompts
during training), defined in `legalner/schema.py`:

- persons: `person` (superset of every named natural person), role labels `judge`, `lawyer` (same span also labelled `person`)
- organisations: `organization` (companies, authorities, law firms; not courts), `court`
- places: `address` (with house number), `street` (name only), `location`
- time: `date` (day-precise)
- identifiers: `case_number`, `bank_account`, `social_security_number`, `tax_id`,
  `company_register_number`, `license_plate`, `land_register_id`, `id_document_number`,
  `other_identifier`, `phone_number`, `email`
- legal references: `legal_norm`, `case_citation`, `contract`, `literature`; other: `brand`

### How sources with different tag sets are combined

Each source declares the labels it annotates exhaustively (`SOURCES` in `schema.py`). At build time
an example is only asked about covered labels: LER is never queried for `date`, because LER does not
tag dates. `nested_conflicts` handles labels that occur unannotated inside another span: LER's
`case_citation` ("BGH, Urteil vom 12.3.2002 – VI ZR 12/01") contains unannotated courts, so `court`
is not queried on LER sentences that contain a citation.

Judges' names are published in Austrian RIS decisions, while parties' names are pseudonymised.
Keeping `judge` and `lawyer` as role labels is what lets a redaction policy treat them differently.

## Data

| Source | Status | Lang / jurisdiction | Labels | License |
|---|---|---|---|---|
| Synthetic v1 (`data/synthetic/raw`) | done, 40 docs | de / AT, DE | 10 coarse → canonical (no roles) | ours |
| Synthetic v2 (`data/synthetic/raw_v2`) | pilot running: 72 docs (6 Haiku batches) | de / AT, DE, CH; fr / FR, CH, BE, LU | full canonical schema | ours |
| LER `elenanereiss/german-ler` | converter ready (`legalner/sources/ler.py`) | de / DE federal courts | 19 classes → canonical | CC-BY-4.0 |
| RIS OGD API (`data.bka.gv.at/ris/api/v2.6`) | planned | de / AT | pseudonymised placeholders mark PII | open government data |
| EUR-Lex / CELLAR | planned, for unlabelled legal text and teacher pseudo-labels | de, fr / EU | — | reuse permitted with attribution |
| MAPA `joelniklaus/mapa` | planned, evaluation only (12 docs per language) | de, fr + 19 more / EU | PERSON/ADDRESS/DATE/ORG/AMOUNT, fine sub-tags | CC-BY-4.0 |
| GLiNER v1 replay (`urchade/pile-mistral-v0.1`, `urchade/synthetic-pii-ner-mistral-v1`) | planned | en + de/fr/it/es | open label set | Apache-2.0 |

Avoided for a commercial product: Babelscape MultiNERD and WikiNEuRal (CC-BY-NC-SA) and the
ai4privacy datasets (custom licence restricting commercial use). Pile-NER only if the OpenAI terms
are acceptable.

### Gazetteers (names, streets, companies)

Used to (1) fill RIS placeholders with realistic values, (2) swap entity surfaces in any labelled
source for diversity, and (3) seed the synthetic generators so names do not collapse onto a few
LLM favourites. Planned sources, all with open licences:

- names: Wikidata given and family names with country (CC0), Statistik Austria first-name statistics
- addresses: BEV Adressregister (AT, CC-BY-4.0), Swiss official building address register,
  French Base Adresse Nationale, OpenStreetMap for DE (ODbL, attribution)
- companies: GLEIF LEI records (CC0, covers AT/DE/CH/FR legal entities), Zefix (CH), SIRENE (FR)
- courts and authorities: curated lists from justiz.gv.at, Wikidata

Avoid name lists built from leaked personal data (e.g. the Facebook-leak-based `name-dataset`).

### Synthetic generation

- Spec: `data/synthetic/GENERATION.md` (labels, rules, realism, hard cases).
- Agents (Haiku) write `[[label|surface]]` documents; `python -m legalner.tagged --strict` rejects
  malformed tags and flags untagged repeats of tagged strings, bare surnames and common place names.
- Identifiers come from `legalner.fake_ids` (valid IBAN, AT SV-Nr, FN check letter, AT UID, CH AHV, FR NIR).
- Quality loop: a second agent audits a sample of each batch against the spec; the error rate per
  label decides whether a batch is kept.
- Scale-up after the pilot: about 1,000–3,000 documents across the doc-type × jurisdiction matrix.

## Training

1. `python -m legalner.tagged …` and `python -m legalner.sources.ler` produce canonical JSONL in `data/canonical/`.
2. `python -m legalner.build data/canonical/*.jsonl … -o data/build/<name>` merges sources, splits by
   document, applies coverage and label augmentation (label subsets, synonyms, descriptions) and
   writes GLiNER2 `train.jsonl`/`dev.jsonl`/`test.jsonl`.
3. `python -m legalner.train data/build/<name> -o out/<run>` fine-tunes `gliner2.5-multi-v1`
   (full weights; `--lora` for adapters).
4. `python -m legalner.evaluate out/<run>/best data/build/<name>/test.canonical.jsonl` reports
   per-label and per-slice P/R/F1 plus PII character recall.

Starting mix: LER ≈ 40%, synthetic ≈ 30%, RIS pseudo-labelled ≈ 15%, replay ≈ 15%. Encoder LR
1e-5, task-head LR 5e-4, 3 epochs, early stopping on dev loss. Check the baselines (base model and
PII model) on the same test sets before the first run.

## Evaluation

- Slices: per source, per jurisdiction (AT/DE/CH/FR), per label.
- The decisive set is a **hand-checked Austrian gold set** (≈300–500 RIS and synthetic paragraphs,
  never used for training). LER test F1 alone would overstate Austrian quality.
- Metrics: exact-match F1 per label; PII character recall (share of gold PII characters covered by
  any prediction), since every missed character is leaked data.
- Zero-shot check: a held-out label set (e.g. medication, vehicle model) the model was never fine-tuned
  on, compared with the base model, to catch forgetting.

## Hosts to allow in the sandbox

Already allowed: `huggingface.co` (API and small files). Still needed:

- `*.hf.co` (at least `us.aws.cdn.hf.co`, `cas-bridge.xethub.hf.co`): model weights and parquet files
- `datasets-server.huggingface.co`: Dataset Viewer API
- `data.bka.gv.at`: RIS OGD API
- `eur-lex.europa.eu`, `publications.europa.eu`: EUR-Lex / CELLAR
- `query.wikidata.org`, `www.wikidata.org`: gazetteers
- optional: `download.geofabrik.de`, `data.bev.gv.at`, `adresse.data.gouv.fr`, `leidata-preview.gleif.org`

## Open questions

- Should `legal_norm` include bare act names ("das ABGB")? Our synthetic data says no; LER's
  convention must be checked once its data can be downloaded, and the mapping adjusted.
- Which labels does the redaction policy actually mask? (Probably all `pii` group labels plus
  `person` except `judge`.)
- Swiss Italian and Romansh: out of scope for now.
