"""Versioned evaluation scaffolds and evidence-backed offline corpora."""

from macro_data_platform.evaluation.case_contracts import EvaluationCase
from macro_data_platform.evaluation.case_sets import validate_case_sets
from macro_data_platform.evaluation.cases import EvaluationCorpus, load_corpus, read_cases
from macro_data_platform.evaluation.split_audit import SplitLeakageIssue, audit_split_leakage

__all__ = [
    "EvaluationCase", "EvaluationCorpus", "SplitLeakageIssue", "audit_split_leakage",
    "load_corpus", "read_cases", "validate_case_sets",
]
