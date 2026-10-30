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
| Synthetic v2 (`data/synthetic/raw_v2`) | done, 72 docs, audited | de / AT, DE, CH; fr / FR, CH, BE, LU | full canonical schema | ours |
| Synthetic v3 (`data/synthetic/raw_v3`) | done, 1,000 docs, audited | de / AT, DE, CH, LI; fr / FR, CH, BE, LU | full canonical schema | ours |
| Synthetic v4 (`data/synthetic/raw_v4`) | done, 2,000 docs (8,290 records), audited 1.5 % span errors (`docs/audits/synthetic_v4.md`) | de / AT, DE, CH, LI; fr / FR, CH, BE, LU | full canonical schema, rare labels oversampled | ours |
| Synthetic v5 (`data/synthetic/raw_v5`) | done, 2,000 docs (8,362 records), audited 1.5 % span errors; 35 % of AT court documents RIS-pseudonymised | as v4 | as v4 | ours |
| LER `elenanereiss/german-ler` | converted | de / DE federal courts | 19 classes → canonical | CC-BY-4.0 |
| RIS OGD API (`data.bka.gv.at/ris/api/v2.6`) | done, 1,353 decisions (OGH/OLG/LG, VwGH, VfGH, BVwG, LVwG all states, 2020+) → 31,144 chunks in `data/canonical/ris.jsonl` (`legalner/sources/ris.py`, index in `data/ris/index.jsonl`) | de / AT | placeholders filled from gazetteers + rules: person, judge, lawyer, address, date, case_number, court (audit: `docs/audits/ris_rules.md`, ≈2–8 % misses per label) | open government data |
| EUR-Lex / CELLAR | planned, for unlabelled legal text and teacher pseudo-labels | de, fr / EU | — | reuse permitted with attribution |
| MAPA `joelniklaus/mapa` | converted, evaluation only (12 docs per language) | de, fr + 19 more / EU | PERSON/ADDRESS/DATE/ORG/AMOUNT, fine sub-tags | CC-BY-4.0 |
| GLiNER v1 replay (`urchade/pile-mistral-v0.1`, `urchade/synthetic-pii-ner-mistral-v1`; **not** Pile-NER) | converted (`sources/replay.py`) | en + de/fr/it/es | open label set | Apache-2.0 |

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

Done on branch `ccr-e3b45fa1-pbfzdy` (continues `ccr-45f5c65f-g4rgnu`; earlier history in the git log):
1. **Gold set** (`docs/audits/gold_at_review.md`): 550 paragraphs, 400 synthetic (convention pass with the gold-set
   decisions, artefacts fixed) + 150 RIS (first chunks of 51 decisions, fully annotated, filler artefacts fixed).
   Conventions settled with the project lead: `GENERATION.md` decisions 1-24. Agent-reviewed, not yet human-reviewed.
2. **RIS**: 1,353 decisions (913 new: LVwG all nine states, LG, OLG, 2020+), all chunks kept; BVwG balanced in the
   build (`--max-per-doc ris=20 --cap ris:Bundesverwaltungsgericht=800`). New rules: VwGH `Mag. [B]`, LVwG Tirol town
   codes, VwG Wien `C.-platz`, Burgenland `[Vertreter 1]`, Kopf degrees without dots, court seats/case numbers/durations
   no longer filled with names, date ranges as one span. Uncovered chunks 7.9 % (Kärnten 30 %). Audit of 10 new
   decisions in `docs/audits/ris_rules.md`.
3. **Case robustness**: `legalner.build --case-frac 0.1` upper/lower-cases whole records or single spans (offsets kept,
   ß stays ß); ALL-CAPS and lower-case passages are generation hard cases.
4. **Synthetic v4**: 2,000 documents (`docs/audits/synthetic_v4.md`): every brief has 1-3 of licence plate, ID document,
   street, phone, e-mail (new `fake_ids` generators for AT/DE/CH/FR plates and ID documents); vehicle/residence/
   insurance/police types oversampled; degree chains; correct BE/LU social security numbers. All pass `--strict` and
   `legalner.audit`; LLM audit 1.5 % span errors after new lint rules (towns, datelines, caps passages, phones, e-mails,
   IBANs). Generated by Haiku agents; audits by Sonnet agents.
   **Synthetic v5**: another 2,000 documents with the same design (seed 53, `--pseudo-frac 0.35`), audited 1.5 % span
   errors; lint additions dd/mm/yyyy dates, degrees and register prefixes outside spans (fixed across v4/v5).
5. **Mix and build** (`scripts/gpu_run.sh build`): LER 40 / synthetic 30 / RIS 15 / replay 15 % of training records
   via `--mix` (anchored on all synthetic training records), gold documents excluded, validated with
   `TrainingDataset.validate()` (0 invalid):

   ```
   python -m legalner.build \
     data/canonical/synthetic_v1.jsonl data/canonical/synthetic.jsonl data/canonical/synthetic_v3.jsonl \
     data/canonical/synthetic_v4.jsonl data/canonical/synthetic_v5.jsonl \
     data/canonical/ris.jsonl data/canonical/replay.jsonl \
     data/canonical/ler/*.jsonl data/canonical/mapa/*.jsonl data/canonical/gold_at.jsonl \
     --exclude-docs data/gold/at/doc_ids.txt \
     --max-per-doc ris=20 --cap ris:Bundesverwaltungsgericht=800 \
     --mix ler=0.4,synthetic=0.3,ris=0.15,replay=0.15 --validate -o data/build/v1
   ```

   Result: 55,473 training records (ler 22,189, replay 8,321, ris 8,321, synthetic 16,546, synthetic_v1 96; shares {'ler': 0.4, 'replay': 0.15, 'ris': 0.15, 'synthetic': 0.3}), dev 12,833, test 16,866 (incl. gold 550, MAPA, LER test); validate(): 0 invalid. 10 % of training records case-augmented.

6. **First GPU run (v1)**, 2026-10-30: RunPod, 1× A100-SXM4 80 GB (secure cloud, runpod/pytorch CUDA 12.4 image, torch 2.6,
   gliner2 2.1.0, transformers 5.22.0), driven by `scripts/pod_run.sh` (data and code from the private HF dataset
   `sb-aiss/legalner-build-v1`; checkpoint, eval JSONs and logs in the private HF model repo `sb-aiss/legalner-v1`).
   Total cost $3.17, including a first attempt that failed at import time (the image's torchvision did not match torch 2.6).
   - Smoke (20 steps): 48 GB peak, ≈2 s/step at batch 8 × accum 4. Training: 3 epochs, 5,195 steps, 88 min,
     31.4 samples/s, 80 GB peak (bf16). Eval of all three models on both sets: 11 min.
   - The large loss values are not divergence: the checkpoint's boundary head uses `loss_reduction="sum"`, so the loss
     is summed over all query × position and candidate elements (the logged train loss also over the 4 accumulation
     micro-batches). Dev loss (8-record batches): 274.0 after 10 smoke steps (≈ base model) → 162.3 (step 1,000) →
     139.3 (3,000) → 126.7 (5,000, best). It fell at every evaluation, so early stopping never triggered and more
     epochs may help.
   - Results (exact-match F1, threshold 0.5; FT = `out/v1/best`, base = `fastino/gliner2.5-multi-v1`,
     PII = `fastino/gliner2-privacy-filter-PII-multi`; gold = `gold_at`, 550 paragraphs; test = `test.canonical.jsonl`
     with at most 2,000 records per source, 9,566 records; each record is queried with its covered labels only):

     | Label | n gold | FT gold | base gold | PII gold | n test | FT test | base test | PII test |
     |---|---:|---:|---:|---:|---:|---:|---:|---:|
     | **all (micro)** | 6955 | 0.966 | 0.604 | 0.615 | 52569 | 0.901 | 0.502 | 0.546 |
     | person | 1834 | 0.972 | 0.643 | 0.642 | 11906 | 0.934 | 0.537 | 0.518 |
     | judge | 192 | 0.957 | 0.259 | 0.459 | 1046 | 0.947 | 0.167 | 0.315 |
     | lawyer | 130 | 0.828 | 0.147 | 0.177 | 811 | 0.904 | 0.135 | 0.160 |
     | organization | 663 | 0.943 | 0.598 | 0.632 | 4385 | 0.844 | 0.253 | 0.504 |
     | court | 324 | 0.986 | 0.689 | 0.665 | 2639 | 0.959 | 0.546 | 0.526 |
     | address | 259 | 0.986 | 0.894 | 0.701 | 1809 | 0.961 | 0.172 | 0.694 |
     | street | 6 | 0.857 | 0.091 | 0.043 | 268 | 0.884 | 0.232 | 0.238 |
     | location | 347 | 0.973 | 0.385 | 0.504 | 2891 | 0.883 | 0.565 | 0.540 |
     | date | 1284 | 0.993 | 0.892 | 0.892 | 9352 | 0.981 | 0.823 | 0.838 |
     | case_number | 201 | 0.931 | 0.370 | 0.444 | 1403 | 0.920 | 0.314 | 0.366 |
     | bank_account | 77 | 1.000 | 0.662 | 0.896 | 425 | 0.982 | 0.515 | 0.837 |
     | social_security_number | 78 | 0.987 | 0.485 | 0.677 | 412 | 0.987 | 0.460 | 0.623 |
     | tax_id | 178 | 1.000 | 0.041 | 0.024 | 825 | 0.985 | 0.002 | 0.345 |
     | company_register_number | 186 | 1.000 | 0.000 | 0.153 | 1012 | 0.915 | 0.310 | 0.258 |
     | license_plate | 13 | 0.800 | 0.522 | 0.643 | 259 | 0.953 | 0.423 | 0.684 |
     | land_register_id | 71 | 0.748 | 0.156 | 0.187 | 139 | 0.749 | 0.148 | 0.223 |
     | id_document_number | 2 | 0.800 | 0.000 | 0.030 | 184 | 0.975 | 0.031 | 0.224 |
     | other_identifier | 18 | 0.824 | 0.105 | 0.069 | 118 | 0.773 | 0.044 | 0.044 |
     | phone_number | 12 | 0.960 | 1.000 | 0.960 | 141 | 0.983 | 0.647 | 0.847 |
     | email | 14 | 0.933 | 0.824 | 0.778 | 331 | 0.988 | 0.876 | 0.923 |
     | legal_norm | 1066 | 0.953 | 0.767 | 0.769 | 4379 | 0.962 | 0.654 | 0.637 |
     | case_citation | 0 | – | – | – | 366 | 0.936 | 0.031 | 0.054 |
     | contract | 0 | – | – | – | 108 | 0.796 | 0.056 | 0.055 |
     | literature | 0 | – | – | – | 103 | 0.867 | 0.017 | 0.013 |
     | brand | 0 | – | – | – | 8 | 0.400 | 0.128 | 0.070 |
     | PII character recall | | 0.978 | 0.817 | 0.910 | | 0.966 | 0.773 | 0.907 |

     | Test slice (micro F1) | n | FT | base | PII |
     |---|---:|---:|---:|---:|
     | jur=AT | 24812 | 0.961 | 0.489 | 0.538 |
     | jur=BE | 866 | 0.965 | 0.545 | 0.660 |
     | jur=CH | 3876 | 0.960 | 0.579 | 0.674 |
     | jur=DE | 6617 | 0.956 | 0.405 | 0.442 |
     | jur=EU | 1370 | 0.658 | 0.386 | 0.337 |
     | jur=FR | 3539 | 0.941 | 0.445 | 0.587 |
     | jur=LI | 306 | 0.979 | 0.626 | 0.669 |
     | jur=LU | 614 | 0.966 | 0.494 | 0.614 |
     | jur=XX | 10569 | 0.703 | 0.628 | 0.631 |
     | source=gold_at | 6955 | 0.964 | 0.558 | 0.614 |
     | source=ler | 1577 | 0.882 | 0.174 | 0.147 |
     | source=mapa | 1370 | 0.658 | 0.386 | 0.337 |
     | source=replay | 10569 | 0.703 | 0.628 | 0.631 |
     | source=ris | 6441 | 0.936 | 0.380 | 0.397 |
     | source=synthetic | 25504 | 0.968 | 0.544 | 0.633 |
     | source=synthetic_v1 | 153 | 0.967 | 0.676 | 0.736 |

   - Reading: the fine-tuned model is far ahead on every canonical label (gold micro F1 0.966 vs 0.604/0.615; PII
     character recall 0.978 vs 0.817/0.910). The largest gains are on labels the baselines lack or confuse: role labels
     (judge 0.957, lawyer 0.828 on gold), tax ID, company register number, case number, case citation. Weakest:
     land register ID (0.75), lawyer precision (0.75 on gold), contract, literature, other_identifier, brand (n=8).
     MAPA (EU, never trained on) went 0.386 → 0.658 and replay (open label set, zero-shot proxy) 0.628 → 0.703, so no
     sign of forgetting on the replay distribution.
   - Caveats: 400 of the 550 gold paragraphs are synthetic from the same generators as the training data, and the gold
     set is only agent-reviewed, so 0.966 is optimistic. RIS test labels are rule-based pseudo-labels (audited 2–8 %
     misses). The held-out signal is MAPA (0.658). The report does not yet split gold into its RIS and synthetic parts.
   - **MAPA organisation (F1 0.383) analysed** (2,000 sampled MAPA records, 360 gold org spans; FT model on CPU;
     MAPA's ORGANISATION is scored against our organization ∪ court):
     - Precision is mostly an annotation artefact: 276 of 342 false positives hit no MAPA span at all, and they are
       courts and EU bodies MAPA leaves unannotated ("Gerichtshof" ×82, "High Court" ×35, "Supreme Court",
       "Verwaltungsgerichtshof", "Europäisches Parlament", "gouvernement autrichien"). Another 28 are court names
       whose seat MAPA tags as a location ("Tribunale di Teramo"). Counting only predictions that overlap some
       MAPA span, precision is 0.81, not 0.33. MAPA's organisation annotation is partial, so its precision is not a
       usable metric; recall is.
     - Recall 0.46 is a real gap. Misses by type: single-token company or case names ("Simmenthal", "Alpenrind",
       "Unibet", "Martin-Meat") recall 0.18, often predicted as person; EU institutions and governments
       ("die Kommission", "Rat", "österreichischen Regierung") 0.39; acronyms and CJEU party initials ("IR", "WRC",
       "CRP", "CIF") 0.62; multi-token names 0.50; a state as party ("Österreich") 0.00, predicted as location.
       Some of this is convention (MAPA tags anaphoric "die Stiftung"/"la Fondation", which decision 6 leaves untagged;
       case short names like "Urteil Simmenthal" have no settled convention), but most contradicts our own rules
       (decision 5: bare abbreviations are organizations; decision 6: unique bodies are tagged; decision 16: public
       bodies acting as a party are organizations).
     - Lowering the threshold does not help (recall 0.456 at 0.5, 0.486 at 0.2): the misses are confident, so the fix
       is data, not calibration. Training data has almost no EU-court text: no CJEU judgments or AG opinions, few
       EU institutions, few organisations referred to only by acronym or by a name without legal form.
     - Fixes, in order of expected effect: (1) synthetic EU documents in de/fr (CJEU judgments, AG opinions,
       preliminary references) with EU institutions, governments and member states as parties, CJEU-style party initials
       and acronyms, companies named without legal form; (2) a build-time augmentation that replaces later mentions of
       an organisation with its parenthesised abbreviation; (3) EUR-Lex text pseudo-labelled by this model (already
       planned); (4) settle conventions for a state as party ("Österreich" → organization, by analogy to decision 16),
       bare EU institutions (→ organization) and case short names; (5) score MAPA organisation as recall only, plus a
       hand-checked precision sample.

Next: human review of the gold set and a gold slice by origin (RIS vs synthetic); a per-label threshold sweep
(0.3–0.7); a longer run (dev loss was still falling after 3 epochs); teacher pseudo-labels for RIS organisations and
places; EUR-Lex; the held-out zero-shot label check (medication, vehicle model). `scripts/pod_run.sh` now waits after
smoke for `control/go` in the output repo (`control/abort` or a 60 min timeout stops the pod).

## Open questions

- Which labels does the redaction policy actually mask? Likely all `pii` group labels plus every `person` that is
  not also `judge` or `lawyer` (lawyers and judges acting professionally are published in RIS). The role labels
  exist so the policy can make that choice; unclear roles are labelled `person` (fail safe).
- Swiss Italian and Romansh: out of scope for now.
