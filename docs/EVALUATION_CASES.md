# Curated engine evaluation cases

This directory defines versioned case records and split hygiene. It is a
reviewed test corpus, not an automatic learner. `macro-feedback` keeps the
append-only runtime feedback log; accepted feedback does not enter these files
unless a reviewer writes and privacy-clears a case explicitly.

## Current state

`evaluation/sets/development.json`, `validation.json`, and `holdout.json` are
versioned manifests and are deliberately empty. The validation and holdout
file bytes and versions are pinned in `evaluation/sets/frozen.json`. A change
to either frozen set must include a deliberate, reviewed lock update in the same
PR. This detects accidental edits; it does not prevent a reviewer from
approving a new baseline. No representative cases have
been curated yet, so the command reports `VALID_BUT_EMPTY`; that is not an
evaluation pass. Do not fill the sets with invented user or provider evidence.

Run the structural, split-leakage, and frozen-hash checks from the repository root:

```text
python -m macro_data_platform.evaluation.cli validate
```

After installing the project, the equivalent command is:

```text
macro-eval validate
```

## Case record

Each case has a stable `case_id`, integer `case_version`, assigned split,
canonical question and paraphrase variants, expected response state and source
entity/field, required evidence, forbidden actions, and an explicit Excel
expectation. It also records reviewed provenance, feedback reference when
applicable, reviewer/time, and privacy clearance. The validator rejects
unreviewed or uncleared cases, unknown fields, duplicate IDs, repeated exact
questions across splits, and contrast groups split across sets.

Illustrative record shape (documentation example only; it is not counted as an
evaluation case):

```json
{
  "schema_version": 1,
  "case_id": "example-do-not-run",
  "case_version": 1,
  "split": "development",
  "review": {
    "status": "reviewed",
    "reviewer": "reviewer-id",
    "reviewed_at": "2026-10-27T00:00:00+00:00",
    "privacy_cleared": true
  },
  "provenance": {
    "origin": "synthetic",
    "feedback_id": null,
    "evidence": []
  },
  "contrast_group": null,
  "question": {
    "canonical": "Example query",
    "variants": ["Example paraphrase"]
  },
  "expected": {"state": "NEEDS_REVIEW", "entities": []},
  "required_evidence": ["source_url", "definition"],
  "forbidden_actions": ["guess_identifier", "interpolate_missing_values"],
  "excel_expectation": {
    "policy": "not_applicable",
    "missing_value": "not_applicable",
    "overlap_conflict": "not_applicable",
    "interpolate": false,
    "forward_fill": false
  }
}
```

Assign semantically similar questions with different expected answers to the
same `contrast_group`; the validator cannot infer semantic similarity by itself.
All members of a contrast group stay in one split. Cases derived from feedback
must use sanitized question text and retain only a feedback identifier in the
case provenance, not the private feedback body.

Excel expectation fields are required even before an Excel exporter exists.
`interpolate` and `forward_fill` must remain false. Use `blank` for missing
values when an Excel output is applicable; overlapping incompatible series
must be kept separate or sent for review.

## Not implemented by this step

The validator does not run an engine, calculate answer/ranking accuracy,
compare baseline and candidate rules, calculate false-confirmation rates, or
approve a rule. The sets must first contain reviewed cases, and the product
engines need a shared, versioned outcome record before a meaningful candidate
comparison can be run. Rule promotion and rollback remain explicit human
decisions with no automatic feedback-to-code path.
