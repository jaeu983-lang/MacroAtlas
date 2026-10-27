"""Deterministic checks for evaluation-set leakage across splits."""

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from macro_data_platform.evaluation.case_contracts import EvaluationCase

_YEAR_RANGE = re.compile(
    r"(?<!\d)(?:18|19|20|21)\d{2}\s*(?:-|–|—|~|to|through)\s*"
    r"(?:18|19|20|21)\d{2}(?!\d)",
    re.IGNORECASE,
)
_MONTH_PERIOD = re.compile(r"(?<!\d)(?:18|19|20|21)\d{2}[-/]\d{1,2}(?!\d)")
_YEAR = re.compile(r"(?<!\d)(?:18|19|20|21)\d{2}(?!\d)")


@dataclass(frozen=True)
class SplitLeakageIssue:
    """A case family or date-normalized query template appears across splits."""

    kind: str
    fingerprint: str
    case_ids: tuple[str, ...]
    splits: tuple[str, ...]


def _template_fingerprint(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = _YEAR_RANGE.sub(" period ", normalized)
    normalized = _MONTH_PERIOD.sub(" period ", normalized)
    normalized = _YEAR.sub(" year ", normalized)
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    normalized = " ".join(normalized.replace("_", " ").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def audit_split_leakage(cases: Iterable[EvaluationCase]) -> tuple[SplitLeakageIssue, ...]:
    """Find repeated case families or query templates in different dataset splits.

    Years and year/month ranges are normalized so changing only the requested period
    cannot make an otherwise identical query appear independent across splits.
    This conservative text audit does not establish semantic independence.
    """
    family_cases: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    template_cases: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for case in cases:
        if not isinstance(case, EvaluationCase):
            raise TypeError("Split audit requires EvaluationCase values")
        family_cases[case.case_family_id][case.split].add(case.case_id)
        texts = {case.request["text"], *case.query_variants}
        for text in texts:
            template_cases[_template_fingerprint(text)][case.split].add(case.case_id)

    issues = []
    for family_id, by_split in family_cases.items():
        if len(by_split) > 1:
            fingerprint = hashlib.sha256(family_id.encode("utf-8")).hexdigest()
            issues.append(SplitLeakageIssue(
                "case_family_crosses_splits", fingerprint,
                tuple(sorted({case_id for ids in by_split.values() for case_id in ids})),
                tuple(sorted(by_split)),
            ))
    for fingerprint, by_split in template_cases.items():
        if len(by_split) > 1:
            issues.append(SplitLeakageIssue(
                "query_template_crosses_splits", fingerprint,
                tuple(sorted({case_id for ids in by_split.values() for case_id in ids})),
                tuple(sorted(by_split)),
            ))
    return tuple(sorted(issues, key=lambda item: (item.kind, item.fingerprint)))
