# Audit synthetic v6 (EU documents), sample of 10

Audited by: Sonnet agent. Standard: data/synthetic/GENERATION.md (labels, annotation rules, decisions 1-30, "EU documents (synthetic v6)").
Scope: 10 documents of data/synthetic/raw_v6 (0050, 0007, 0017, 0045, 0133, 0049, 0039, 0043, 0046, 0056), checked span by span. No file edited except this report.

**32 span errors in 635 spans = 5.0 %** (all 32 are errors of omission or boundary except 2 wrong labels and 1 spurious tag; existing tags are otherwise correct).

## Error kinds

| kind | n | example |
|---|---|---|
| missed legal_norm (EU act or article citation untagged) | 17 | 0133: "Richtlinie 2016/680" in title, para 6, para 15 |
| missed organization (state / "le Gouvernement" as actor) | 4 | 0133 para 12: "Der belgische Staat hat keine Erklärung abgegeben" |
| wrong boundary | 3 | 0045 para 23: "article 26 de la [[legal_norm|directive 2014/65/UE]]" must be one span |
| missed court (Court self-reference, decision 26) | 3 | 0017: "Der Gerichtshof (Achte Kammer)" untagged |
| wrong label (prosecutor labelled judge, decision 1) | 2 | 0049: "avocat général [[judge|Lelian Periețeanu]]" (ministère public) |
| missed case_number | 2 | 0045: "Affaire C-739/25" |
| tag that should not exist (nesting) | 1 | 0039: "règlement de la [[court|Cour]]" inside a norm |

Decisions 25 (states), 27 (case short names), 28 (acronyms, companies without legal form) and 30 (AG = judge, agents = person) were applied correctly in all 10 documents except the cases listed below. Party initials, acronyms (OSMP, KRNDE, SRB, ACS ...) and agents are clean.

## Per document

### 0050 decision_commission_concurrence (70 spans, 1 error)
- Missed legal_norm: "traité sur le fonctionnement de l'Union européenne" (long act name, decision 11).

### 0007 vorabentscheidungsersuchen (50 spans, 2 errors)
- Boundary: "Kanzlei [[organization|Mollin & Partner]]" must be [[organization|Kanzlei Mollin & Partner]] (no-nesting rule, firm span includes "Kanzlei").
- Missed case_number: "2025-3381" (report number of the authority RVK, para 5).

### 0017 eugh_beschluss (65 spans, 5 errors)
- Missed court: "beim Gerichtshof eingegangen" (header), "Der Gerichtshof (Achte Kammer)", "hat der Gerichtshof (Achte Kammer) für Recht erkannt".
- Missed legal_norm: "Art. 99 der Verfahrensordnung" (headnote) and "Art. 99 der Verfahrensordnung des Gerichtshofs" (para 9, one span incl. "des Gerichtshofs").

### 0045 conclusions_avocat_general (69 spans, 4 errors)
- Missed case_number: "C-739/25" (Affaire line).
- Missed legal_norm: "l'article 26 de la directive" (para 3 and para 9) -> [[legal_norm|article 26 de la directive]].
- Boundary: para 23 tags only "directive 2014/65/UE"; correct span is "article 26 de la directive 2014/65/UE".

### 0133 eugh_urteil (54 spans, 4 errors)
- Missed legal_norm: "Richtlinie 2016/680" in the headnote, para 6 ("Die Richtlinie 2016/680 verlangt") and para 15.
- Missed organization (decision 25): "belgische Staat" (para 12, state as procedural actor; adjective inside, article outside).

### 0049 decision_commission_aide_etat (67 spans, 3 errors)
- Wrong label: "avocat général [[judge|Lelian Periețeanu]]" is the prosecutor ("Le ministère public était représenté par") -> person.
- Missed legal_norm: "traité sur le fonctionnement de l'Union européenne".
- Missed organization: "l'État belge" (para 8, state as the aid-granting body, decisions 16/25).

### 0039 arret_cedh (74 spans, 9 errors)
- Spurious tag: "règlement de la [[court|Cour]]" (final line): the whole "article 77 §§ 2 et 3 du règlement de la Cour" is one legal_norm, no court inside.
- Missed legal_norm: "article 6 de la Convention" (heading I), "article 6, paragraphe 1, de la Convention" (para 18 and operative part 2), "article 41 de la Convention" (heading II), "article 77 §§ 2 et 3 du règlement de la Cour".
- Boundary: "article 34 de la [[legal_norm|Convention de sauvegarde ...]]" must be one span including "article 34 de la".
- Missed organization: "le Gouvernement" (para 14, para 17; defined term for the belgian government, procedural actor, decision 25).

### 0043 ordonnance_cjue (63 spans, 3 errors)
- Missed legal_norm: "Article 99 du règlement de procédure" (headnote); "l'article 4 du règlement n° 1/2003" (para 7 question 2 and para 14).

### 0046 demande_decision_prejudicielle (80 spans, 1 error)
- Wrong label: "avocat général [[judge|Baltek Motýl]]" is the ministère public -> person.

### 0056 eugh_beschluss (43 spans, 0 errors)
- Clean. The Bevollmächtigten are called Rechtsanwälte in the text, so lawyer is correct (decision 30).

## Realism notes (max 3 per document)

- 0050: Commission decision narrates a Court judgment of 8 Feb 2024 on an appeal in the same case, before the procedure started (12 March 2024). T-461/92 dated 16 Sept 1992 (same-year number) and "Tribunal de l'Union européenne" in 1992 (then Tribunal de première instance). Art. 101 decision addressed to natural persons, not undertakings.
- 0007: CJEU has no jurisdiction to interpret the CMR (Art. 23 CMR is not Union law); SRB (resolution of banks) submits an opinion in a freight case; a Croatian-named agent for the Dutch government.
- 0017: Headnote "Offensichtlich unbegründet" and "Kreditinstitute" do not match the energy-law content; an Art. 99 order cites an AG opinion that was already delivered; C-424/20 for a 14 May 2020 judgment and T-493/90 for a 27 March 1990 judgment are implausible.
- 0045: Reference received 3 Dec 2025, AG opinion 11 March 2026 (too fast); competition authority ACS regulates MiFID reporting; AG opinion announces the chamber composition including five judges.
- 0133: C-455/26 but reference received 24 July 2025 (should be /25); Directive 2016/680 applies to authorities, not to a private Kft.; C-662/94 for a 12 May 1994 judgment.
- 0049: Aid is "mise à exécution" but "notifiée" by the authorities in para 1; one-person brewery receives EUR 1.2 million; national court judgment and avocat général at Cour d'appel in a state aid decision are unusual detail.
- 0039: Chamber of five judges (ECtHR section chambers have seven); EU-law section and "La Cour a relevé" in the domestic-law section; C-336/15 (2015) and C-178/20 (2020) with same-year judgment dates.
- 0043: Headnote "Manifeste irrecevabilité" is Art. 53(2), not Art. 99 as cited; four governments with "les mêmes agents"; decided 3 months after receipt despite four sets of observations.
- 0046: Government and Commission "observations" appear in the national court's own reference, which cannot exist before the CJEU procedure; T-406/97 (1997), T-38/14 (2014) and 78/83 (1983) with same-year dates; "avocat général" and "ministère public" at the Tribunal administratif.
- 0056: C-281/25 but national decision dated 19 Sept 2025 (number too low); Art. 5 of Reg. 2017/1001 (eligibility of owners) does not concern similarity or reputation; T-560/92 for a 14 April 1992 judgment.

## Action

Missed EU norm citations are more than half of the errors. Rather than re-editing 240 documents, `legal_norm` is
removed from the coverage of the `synthetic_eu` source (`legalner/schema.py`), so these documents are never queried
for norms and their untagged citations cannot train as negatives. Organisations, courts, persons and the EU-specific
decisions 25-30 (the purpose of this wave) were applied correctly in the sample; the remaining 15 errors (12 of 600
non-norm spans, 2.4 %) are left as they are.
