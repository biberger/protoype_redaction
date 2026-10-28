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
  OpenAI terms apply; **decision: not used**), `urchade/pile-mistral-v0.1` (Apache-2.0) and the multilingual
  `urchade/synthetic-pii-ner-mistral-v1` (en/fr/it/de/es, Apache-2.0).
- **GLiNER2 / GLiNER2.5:** no. The paper describes the corpus but Fastino has not released it
  (their only Hub dataset is `fastino/fast-decisions`, for classification).

We use open GLiNER v1 data as **replay** to keep zero-shot ability. **Decision:** replay data is
`urchade/pile-mistral-v0.1` and `urchade/synthetic-pii-ner-mistral-v1` only; `Universal-NER/Pile-NER-type`
is not used (OpenAI-generated labels).

**Decision:** Universal-NER/Pile-NER-type is not used. Replay data is `urchade/pile-mistral-v0.1`
and `urchade/synthetic-pii-ner-mistral-v1` only. The name gazetteer is WGND 2.0 (WIPO World Gender
Name Dictionary, Harvard Dataverse).

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

### legal_norm convention (settled)

LER tags bare act names (2,920 of 20,446 norm spans: `Grundgesetz`, `FGO`, `SGB II`) and keeps a chain
inside one act as one span (`§ 6c i. V. m. § 6b Abs. 2 EStG`) while splitting chains across acts
(`§ 82 FGO` i. V. m. `§§ 404, 412 ZPO`). We adopt that convention: bare act names are `legal_norm`
(`das [[legal_norm|ABGB]]`, `le [[legal_norm|Code civil]]`). Reasons: LER supplies ≈97% of the norm
supervision; for redaction, recognising `DSGVO` or `ABGB` as a norm keeps them from being masked as
organisations. Synthetic data was retagged (`legalner/acts.py`), and `--strict` now flags untagged act names
and norm citations. Gazette references (BGBl., JO) stay untagged in synthetic data. LER sometimes includes them
inside a span; that's accepted noise.

## Data

| Source | Status | Lang / jurisdiction | Labels | License |
|---|---|---|---|---|
| Synthetic v1 (`data/synthetic/raw`) | done, 40 docs | de / AT, DE | 10 coarse → canonical (no roles) | ours |
| Synthetic v2 (`data/synthetic/raw_v2`) | pilot running: 72 docs (6 Haiku batches) | de / AT, DE, CH; fr / FR, CH, BE, LU | full canonical schema | ours |
| LER `elenanereiss/german-ler` | converter ready (`legalner/sources/ler.py`) | de / DE federal courts | 19 classes → canonical | CC-BY-4.0 |
| RIS OGD API (`data.bka.gv.at/ris/api/v2.6`) | done, 440 decisions (OGH/OLG/LG, VwGH, VfGH, BVwG, LVwG, 2022+) → 6,105 chunks in `data/canonical/ris.jsonl` (`legalner/sources/ris.py`, index in `data/ris/index.jsonl`) | de / AT | placeholders filled from gazetteers + rules: person, judge, lawyer, address, date, case_number, court (audit: `docs/audits/ris_rules.md`, ≈2–8 % misses per label) | open government data |
| EUR-Lex / CELLAR | planned, for unlabelled legal text and teacher pseudo-labels | de, fr / EU | — | reuse permitted with attribution |
| MAPA `joelniklaus/mapa` | planned, evaluation only (12 docs per language) | de, fr + 19 more / EU | PERSON/ADDRESS/DATE/ORG/AMOUNT, fine sub-tags | CC-BY-4.0 |
| GLiNER v1 replay (`urchade/pile-mistral-v0.1`, `urchade/synthetic-pii-ner-mistral-v1`; **not** Pile-NER) | planned | en + de/fr/it/es | open label set | Apache-2.0 |

Avoided for a commercial product: Babelscape MultiNERD and WikiNEuRal (CC-BY-NC-SA) and the
ai4privacy datasets (custom licence restricting commercial use). Pile-NER is not used (decision).

### Gazetteers (names, streets, companies)

Used to (1) fill RIS placeholders with realistic values, (2) swap entity surfaces in any labelled
source for diversity, and (3) seed the synthetic generators so names do not collapse onto a few
LLM favourites. Planned sources, all with open licences:

- names: **decision: WGND 2.0** (WIPO World Gender Name Dictionary, Harvard Dataverse; first names by
  country incl. Europe) is the name gazetteer. Wikidata family names (CC0) only as a supplement for surnames,
  which WGND does not cover
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

PyPI and GitHub already work by default. Hosts marked (verify) are the expected download hosts;
confirm on first use, since the agent proxy logs every refused host.

| Purpose | Hosts |
|---|---|
| Hugging Face models and datasets | `huggingface.co`, `*.hf.co` (covers `us.aws.cdn.hf.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs-us-1.hf.co`), `cdn-lfs.huggingface.co`, `datasets-server.huggingface.co` |
| PyTorch CPU wheels (small install for CPU smoke tests) | `download.pytorch.org` |
| RIS (Austrian law and case law) | `data.bka.gv.at` (OGD API), `ogd.ris.bka.gv.at` (document HTML/XML, the URLs the API returns), `rismcp.mburgler.com` (the RIS MCP plugin) |
| EUR-Lex / EU publications | `eur-lex.europa.eu`, `publications.europa.eu` (CELLAR, SPARQL), `data.europa.eu` |
| Wikidata (names, courts, authorities) | `query.wikidata.org`, `www.wikidata.org` |
| Addresses | `data.bev.gv.at` (AT, verify), `data.geo.admin.ch` (CH), `adresse.data.gouv.fr` and `files.data.gouv.fr` (FR), `download.geofabrik.de` (OSM, DE) |
| Companies | `goldencopy.gleif.org` and `api.gleif.org` (GLEIF), `www.zefix.admin.ch` (CH), `object.files.data.gouv.fr` (SIRENE, verify) |
| Names statistics | `www.statistik.at` (verify) |
| Name lists | `dataverse.harvard.edu` (WGND) |
| Misc | `raw.githubusercontent.com` (original LER repo, GLiNER docs), `api.wandb.ai` (only if W&B logging is used) |

## Status and next steps

Done on branch `ccr-40b02117-uffvk3`:
- pipeline in `legalner/` with tests (`python -m pytest`)
- synthetic v1: 40 documents in `data/synthetic/raw` (old 10 labels, mapped by the parser)
- synthetic v2 pilot: 72 documents in `data/synthetic/raw_v2/<batch>` written by 6 Haiku agents
  (at_civil, at_public, at_private, de, ch, fr); all pass `--strict`, **not yet audited**.
  Known gaps: OCR noise only in a few docs; no generators yet for DE Steuernummer/RV-Nr/HRB,
  CHE-UID, SIREN/SIRET, BE enterprise numbers (agents hand-formatted these)

Next session, in order:
1. ~~Validate and audit v2~~ done: `docs/audits/synthetic_v2_pilot.md` (4.8% span error rate in the
   LLM-audited sample before fixes, mostly missed CH-fr norms; fixed, new lint rules, `legalner.audit`).
2. ~~Convert LER, settle legal_norm~~ done: 53,384 / 6,666 / 6,673 sentences; bare act names are
   `legal_norm` (see "legal_norm convention").
3. ~~Validate a build, tiny CPU run~~ done: all 67k examples of a full build pass
   `TrainingDataset.validate()`; a 6-step fp32 CPU run (`--precision fp32 --num-workers 0`) trains, evaluates
   and saves checkpoints (~27 s/step at batch 2 on 4 cores). Findings: the boundary trainer defaults to bf16
   (use `--precision fp32` on CPU); reported losses are large (~100/step, summed); GLiNER2's default flat
   decoding resolves overlaps **across** labels, so a judge never also comes out as `person`. Inference
   therefore queries role labels (`judge`, `lawyer`) in a separate pass (`evaluate.predict`); production
   inference must do the same.
4. ~~Baselines~~ done: `docs/baselines.md`. Both ≈F1 0.53–0.54 zero-shot; PII character recall 0.81 (base)
   vs 0.93 (PII model); roles, identifiers and LER-style citations are weak.
5. ~~RIS fetcher~~ done: `search`/`fetch`/`convert` run on 440 live decisions (raw HTML cached in the
   gitignored `data/ris/raw`). Text extraction drops metadata blocks and the screen-reader duplicate of every
   paragraph. Each court pseudonymises its own way (Justiz `A*`/`* K*`/`*`, BVwG `XXXX`, LVwG `***`/`xxx`/`AA`/
   `Adresse 1`, VwGH initials `des M K in W`, VwG Wien `A. B.`/`...`); placeholders are classified from context and
   filled per document. The rules were checked on 30 decisions; real fixtures for Justiz, BVwG and VwGH are in `tests/`.
   Placeholders no rule can classify (5.4 % of chunks) set `meta.uncovered`, and `build.query_labels` then drops
   the PII labels for that chunk. Audit on 24 decisions (`docs/audits/ris_rules.md`): misses before the last fixes were
   person 4.8 %, address 8.3 %, date 2.1 %, case_number 6.9 %, court 4.8 %. Coverage unchanged. `convert` keeps 40 chunks
   per decision because BVwG country reports would otherwise dominate. `python -m legalner.build data/canonical/ris.jsonl`
   validates under `TrainingDataset.validate()` (4,983/723/399). Open: LVwG letter-coded towns and VwG Wien `C.-platz`
   cut address spans; fetch more LVwG/LG.
6. Add replay converters (GLiNER v1 format) and the MAPA evaluation converter.
7. Scale synthetic generation to 1,000–3,000 documents; build the hand-checked Austrian gold set.
8. First GPU run.

## Open questions

- Which labels does the redaction policy actually mask? (Probably all `pii` group labels plus
  `person` except `judge`.)
- Swiss Italian and Romansh: out of scope for now.
