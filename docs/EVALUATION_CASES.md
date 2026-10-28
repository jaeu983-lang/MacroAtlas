# Evaluation scaffolds and evidence-backed cases

This documentation covers two separate inputs: the original JSON-per-split
scaffold in `evaluation/sets/` and the evidence-backed JSONL v1 corpus in
`tests/fixtures/evaluation/v1/`. Neither is an automatic learner.
`macro-feedback` keeps the append-only runtime feedback log; accepted feedback
does not enter an evaluation corpus unless a reviewer creates, verifies, and
privacy-clears a case explicitly.
Product requirements are in [PROJECT_PLAN.md](../PROJECT_PLAN.md); the current implementation order is in [PRODUCT_EVALUATION_ENGINE_PLAN.md](PRODUCT_EVALUATION_ENGINE_PLAN.md).

## Current state

The original split-set scaffold and evidence-backed JSONL v1 corpus are separate
contracts. The legacy scaffold has six synthetic cases. The v1 fixed corpus
has 9 of 36 intended cases and remains BLOCKED.

The repository contains 27 assistant-simulated draft files. The user has
confirmed that independent review is complete, but no per-case decision,
reviewer record, correction, or evidence ledger has been committed. The draft
files and their manifest preserve their generation-time
independent_review_pending state; that historical metadata does not record the
later review. Keep these cases unpromoted until a review ledger links each
decision to the exact draft hash and the accepted case version. Review
completion alone does not establish that every draft passed.

The fixed-corpus validator verifies structure, hashes, evidence references, and
split leakage. It does not authenticate the human review, run an engine,
calculate ranking accuracy, or promote cases. The current ranking evaluator
and rule-promotion workflow are not implemented.
## Legacy scaffold record

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

## Evidence-backed `EvaluationCase` v1 record

The JSONL corpus uses the richer immutable contract in
`src/macro_data_platform/evaluation/case_contracts.py`. Each record fixes its
case family and split, type, `DataRequest` snapshot, query variants, expected
state, relevant/forbidden candidate IDs, candidate match statuses, expected
field states, evidence references, prohibited actions, and Excel policy.
Evidence paths are repository-relative and hash checked; official references
must be clean HTTPS URIs without credential-bearing query data. Unknown or
conflicting expected fields require supporting evidence and a review-required
candidate status. Assistant authorship remains simulated provenance and cannot be marked human-observed. Human review decisions belong in the separate review ledger; they do not rewrite authorship.

## Not implemented by this step

The validator does not authenticate source evidence, run an engine, calculate
answer/ranking accuracy, compare baseline and candidate rules, calculate
false-confirmation rates, or approve a rule. The legacy synthetic cases exercise structure only; the fixed evidence-backed v1 cases have not been scored by an engine. A representative evaluation needs recorded per-case human review decisions, verified feedback/source references, and a shared, versioned outcome record from the product engines. Rule promotion and
rollback remain explicit human decisions with no automatic feedback-to-code
path.
