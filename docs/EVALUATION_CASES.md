# Curated engine evaluation cases

This directory defines versioned case records and split hygiene. It is a
reviewed test corpus, not an automatic learner. `macro-feedback` keeps the
append-only runtime feedback log; accepted feedback does not enter these files
unless a reviewer writes and privacy-clears a case explicitly.
The complete feedback→evaluation→promotion contract and priority order are in
[`PROJECT_PLAN.md`](../PROJECT_PLAN.md), §7 and §11.

## Current state

The three versioned manifests currently contain six synthetic contract cases,
two per split. They cover the fixed World Bank and BOJ paths, a BLS CPI
contrast between a qualified and ambiguous request, incompatible frequencies
in Excel, and unknown-frequency freshness. They are author-generated fixtures,
not user feedback or evidence that live providers returned the expected data.
The reviewer field records the synthetic author's self-review; it is not an
independent human review.

The validation and holdout file bytes and versions are pinned in
`evaluation/sets/frozen.json`. A change to either frozen set must include a
deliberate, reviewed lock update in the same PR. The hash detects unreviewed
drift; it does not make the public holdout secret or prevent an approved
baseline change. The validator reports structural `READY` separately from
`reviewed_feedback_split_coverage` (`none`, `partial`, or `complete`). Coverage
is based only on declared provenance labels; the validator does not
authenticate feedback IDs against the SQLite feedback log. Neither status
scores engine behavior. These six synthetic cases are scaffolding only and do
not satisfy the user-evidence or generalization gate.

Run the structural, split-leakage, provenance-count, and frozen-hash checks from
the repository root:

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
questions across splits, and contrast groups split across sets. It reports
provenance counts for each split. `reviewed_feedback_split_coverage` only
summarizes declared feedback-origin labels; synthetic and official-reference
cases do not count as reviewed-feedback cases, and the validator does not
verify feedback IDs against the feedback log.

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

The validator does not authenticate source evidence, run an engine, calculate
answer/ranking accuracy, compare baseline and candidate rules, calculate
false-confirmation rates, or approve a rule. The current synthetic cases only
exercise corpus structure. A representative evaluation still needs
independently reviewed cases and verified feedback/source references, plus a
shared, versioned outcome record from the product engines. Rule promotion and
rollback remain explicit human decisions with no automatic feedback-to-code
path.
