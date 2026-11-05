# Lessons learned and the plan for the next NER run

Written after Isel v3 (2026-11-04). Part 1 is the follow-up for the two known weaknesses of Isel v3; part 2 is what
went wrong or nearly wrong in v1-v3 and how to avoid it; part 3 is a checklist for the next run.

## 1. Follow-up plan (not scheduled)

### 1a. EU regression (MAPA_v2 0.836 vs v2 0.860; EU case numbers 0.725 vs 0.929)

Cause: build v3 dropped the source mix ("more data is better"). With every record once, EUR-Lex fell from 2 % to
0.2 % of training and replay from 14.5 % to 7 %; the EU-specific patterns (case numbers like "C-255/22 P", "T-12/23",
"Rs. C-…", ECLI, EU dates and institutions) were seen ten times less often.

Plan:
1. **Shares as floors, not ratios.** Keep every record at least once (nothing is thrown away, unlike the v1/v2 mix)
   and repeat small groups up to a minimum share: EUR-Lex ≥ 2 %, synthetic EU (v6) ≥ 3 %, replay ≥ 10 %. Implement as
   `build.py --min-share group=share` next to `--mix`; print the final shares in the manifest and check them.
2. **More EU data**, since repetition only goes so far: another 100-200 EUR-Lex chunks (pre-tag + agent correction as
   in 2026-10, excluding MAPA documents) and 100 synthetic EU documents whose briefs force case-number variants
   (C-/T-/F-, "P", "Rs.", "verb. Rs.", ECLI, "affaire C-…").
3. **Fine-tune, not retrain**: start from `isel-v3/best`, 1 epoch over the new build with a low encoder LR (5e-6),
   about 4-5 h on an A100. Accept only if MAPA_v2 ≥ 0.86 and gold/OBDK do not drop by more than 0.003.

### 1b. Bare "Kommission" tagged as organization in Austrian disciplinary decisions (129 false spans on OBDK)

Cause: the same phrase means two things. In EU texts "die Kommission" is the European Commission, a specific
organisation, tagged `organization` 272× in synthetic v6, 30× in EUR-Lex and 43× in MAPA_v2. In Austrian
disciplinary decisions it is a generic back-reference to the OBDK and should stay untagged (decision 6), but our
Austrian data has only 3 untagged examples (v5, v7). The model transferred the EU habit. It masks a visible word; it
does not leak data, so it costs readability only.

Plan:
1. **Decision in GENERATION.md**: a bare back-reference to a body already named in the document ("die Kommission",
   "der Senat", "der Ausschuss", "die Kammer", "der Disziplinarrat", "die Behörde") stays untagged; "die (Europäische)
   Kommission" in EU texts stays `organization`. Write both cases with examples.
2. **Hard negatives**: 60-100 OBDK-style briefs with a `hard_case` "the body referred to again as 'die Kommission' /
   'der Senat' (untagged)", plus a lint check that counts tagged vs untagged bare forms per source, so the
   inconsistency is visible before training.
3. Optional stop-gap in the service: do not mask a lone "Kommission"/"Senat"/"Ausschuss" span in documents whose
   court is an Austrian disciplinary body.

### 1c. Align the OBDK benchmark's conventions with ours

The OBDK test set (built by another agent) differs from GENERATION.md on: "Generalprokuratur" (organization there,
untagged authority for us), "Ausschuss der Rechtsanwaltskammer …" (whole span there, chamber only for us) and
"Kanzlei Dr. X & Partner" ("Kanzlei" inside there, outside for us). These account for most of the 0.66 organization
F1 on OBDK, without a single leaked name. Decide each convention once, then correct either the benchmark or the
training data, so the metric measures model errors and not convention differences. Open question for the decision:
should public authorities (Generalprokuratur, Finanzprokuratur, Bezirkshauptmannschaft) be masked at all?

## 2. Lessons learned

### Data and the build
- **Check per-source shares after every build change.** "More data" changed the mix and caused the EU regression.
  The manifest shows `train_share`; compare it with the previous build before training.
- **Dev splits must be document-level.** LER's own split is by sentence, so its dev sentences come from training
  decisions; dev loss kept falling to 43 partly through memorisation. Never select a checkpoint by dev loss alone:
  gold_at, MAPA_v2 and OBDK are the real judges.
- **Benchmarks must share our annotation conventions** (see 1c); otherwise a low score is a convention mismatch.
- **Small labels are noise**: licence plates on gold have n=13 (0.67 on the pod, 0.92 locally). Report n with every
  per-label number and do not act on n < 30.
- **Context-dependent words** ("Kommission") need explicit examples of both readings in the training data.

### Synthetic data generation with LLM writers
- Writers copy anything literal from the instructions: example names ("Eleonore Dr. Schneider"), notes inside
  verbatim strings, the ⏎ symbol from the docs. Never put example values in briefs; keep notes in a separate field;
  lint for literal markup symbols.
- Briefs must be internally consistent, or writers improvise: deceased without a birth date, dates of death after
  "today", a 2003-born Kammeranwältin, hard cases that need a company the brief does not give, roles not assigned.
  Validate briefs in the generator (age vs role, dates ≤ today, hard case → required fields present).
- Gazetteer data needs cleaning: Wikidata surnames contained "kitten", "fence", "unbekannter Wert"; Cyrillic soft
  signs and Greek script survived transliteration; famous surnames (Schwarzenegger, Lauda) slipped in. Filter lists
  (lowercase entries, non-Latin script, blocklist of famous names) before drawing.
- Verbatim strings break grammar (court names cannot be declined); allow declension of named entities.
- Writers used bulk regex tagging and corrupted spans; ask for manual edits, and re-run the strict check yourself.
- Writers tried to call messaging/session tools; state the allowed tools explicitly in the prompt.
- Rate limits stop parallel writers mid-batch; resumed writers rushed and produced short documents (b069 at ~60 % of
  target). Keep batches resumable and re-check length after a resume.
- Audit samples with an independent model (Sonnet audits: 1.2 % pilot, 0.9 % full run); they found convention
  questions (the "*" birth cue, bare "Disziplinarrat") that the strict check cannot see.

### GPU runs
- **Estimate run time from the measured step time on the real build**, including evaluation overhead, never from the
  progress bar's ETA or from an earlier build. v3 ran at 2.15 s/step, not the 1.1 s of v2; the first attempt would
  have hit the 11 h watchdog at epoch 3.8 and was aborted ($2.49 lost).
- **Never let a timeout lose the model**: upload the best checkpoint whenever it improves and before any watchdog
  stop (done in `pod_run.sh`).
- **Set MAX_HOURS from the budget and the GPU price**, with ≥ 15 % headroom over the estimate, and check the balance
  first. Community GPUs are often unavailable; use a retry loop over several GPU types with per-type limits.
- **Make evaluation robust**: one failing model (here the base model, a prediction offset past the text end) aborted
  the whole eval step and the PII baseline was never evaluated. Run each model's evaluation independently, upload
  results after each, and smoke-test the eval scripts locally on two records of every set before launching.
- Production mode matters: 96-word chunks are much better than 384 (recall 0.955 vs 0.871).

### Operations
- Keep the HF progress log as the source of truth; local watchers die with container restarts.
- `pkill -f <pattern>` matched the agent's own shell twice; kill by PID.
- Tokens: use environment secrets, not chat messages; revoke after each run.

## 3. Checklist for the next run

1. Annotation conventions decided and written down (GENERATION.md), benchmarks aligned (1c).
2. Generator validations pass; strict check, audit and an independent sample audit < 1.5 % errors.
3. Build: per-source shares printed and compared with the previous build; floors for small groups; doc-level splits.
4. Smoke on the pod: measured s/step × planned steps + evaluation ≤ 85 % of MAX_HOURS; MAX_HOURS × price ≤ balance.
5. Eval scripts smoke-tested locally on every set and every model; per-model failure isolation.
6. Interim checkpoint uploads verified within the first hour (`best/` appears on HF).
7. Acceptance: gold, MAPA_v2, OBDK and production mode against the previous model; no regression > 0.003 on any
   set without an explicit decision.
