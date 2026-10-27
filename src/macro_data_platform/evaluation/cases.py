"""Deterministic JSONL case and fixed-catalog snapshot readers."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from macro_data_platform.evaluation.case_contracts import EvaluationCase
from macro_data_platform.workflow_contracts import Candidate

_MAX_CORPUS_BYTES = 8 * 1024 * 1024
_MAX_CASE_BYTES = 256 * 1024
_MANIFEST_FIELDS = {
    "manifest_version", "corpus_version", "gate_status", "intended_case_count",
    "intended_cases_per_split", "intended_cases_per_type_per_split", "case_count",
    "counts_by_split", "counts_by_type", "missing_case_types", "gate_blockers", "files",
}
_REQUIRED_FILES = {"cases.jsonl", "schema.json", "catalog_snapshot.json"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Nonstandard JSON numeric constant: {value}")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_bounded(path: Path, maximum: int) -> bytes:
    if path.stat().st_size > maximum:
        raise ValueError("Evaluation corpus file exceeds its size limit")
    with path.open("rb") as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("Evaluation corpus file exceeds its size limit")
    return content


def read_cases(path: str | Path) -> tuple[EvaluationCase, ...]:
    """Read validated UTF-8 JSONL cases without executing or mutating product state."""
    source = Path(path)
    content = _read_bounded(source, _MAX_CORPUS_BYTES)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Evaluation case file must be UTF-8") from None
    if not text or not text.endswith("\n"):
        raise ValueError("Evaluation case JSONL must end with a newline")
    cases = []
    seen = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line or len(line.encode("utf-8")) > _MAX_CASE_BYTES:
            raise ValueError(f"Invalid evaluation case line {line_number}")
        try:
            value = json.loads(line, object_pairs_hook=_unique_object,
                               parse_constant=_reject_json_constant)
            case = EvaluationCase.from_dict(value)
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ValueError(f"Invalid evaluation case line {line_number}") from None
        if case.case_id in seen:
            raise ValueError("Duplicate evaluation case identifier")
        seen.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError("Evaluation case file must not be empty")
    return tuple(cases)


@dataclass(frozen=True, repr=False)
class EvaluationCorpus:
    manifest: Mapping[str, Any]
    cases: tuple[EvaluationCase, ...]
    candidates: tuple[Candidate, ...]
    case_sha256: str
    catalog_sha256: str

    def __repr__(self) -> str:
        return "EvaluationCorpus(<values omitted>)"


def _safe_corpus_file(root: Path, filename: Any) -> Path:
    if not isinstance(filename, str) or filename not in _REQUIRED_FILES:
        raise ValueError("Manifest references an unsupported corpus file")
    path = (root / filename).resolve()
    if path.parent != root.resolve():
        raise ValueError("Corpus file escapes its version directory")
    return path


def _load_candidates(path: Path) -> tuple[Candidate, ...]:
    try:
        value = json.loads(_read_bounded(path, _MAX_CORPUS_BYTES).decode("utf-8"),
                           object_pairs_hook=_unique_object,
                           parse_constant=_reject_json_constant)
        if not isinstance(value, dict) or set(value) != {"snapshot_version", "candidates"}:
            raise ValueError
        if value["snapshot_version"] != "catalog-v1":
            raise ValueError
        raw_candidates = value["candidates"]
        if not isinstance(raw_candidates, list) or not raw_candidates or len(raw_candidates) > 500:
            raise ValueError
        candidates = tuple(Candidate.from_dict(item) for item in raw_candidates)
    except (UnicodeDecodeError, ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("Invalid candidate catalog snapshot") from None
    ids = [candidate.candidate_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate candidate identifier in catalog snapshot")
    return candidates


def _verify_evidence_files(cases: tuple[EvaluationCase, ...], repo_root: Path) -> None:
    root = repo_root.resolve()
    for case in cases:
        for evidence in case.required_evidence:
            candidate_path = (root / evidence["local_ref"]).resolve()
            if root not in candidate_path.parents or not candidate_path.is_file():
                raise ValueError("Evaluation evidence reference is missing or outside the repository")
            if sha256_bytes(_read_bounded(candidate_path, _MAX_CORPUS_BYTES)) != evidence["sha256"]:
                raise ValueError("Evaluation evidence SHA-256 mismatch")


def load_corpus(corpus_dir: str | Path, *, repo_root: str | Path | None = None
                ) -> EvaluationCorpus:
    """Verify the immutable initial manifest, evidence files, and candidate references."""
    root = Path(corpus_dir).resolve()
    try:
        manifest_bytes = _read_bounded(root / "manifest.json", 64 * 1024)
        manifest = json.loads(manifest_bytes.decode("utf-8"),
                              object_pairs_hook=_unique_object,
                              parse_constant=_reject_json_constant)
    except (OSError, UnicodeDecodeError, ValueError):
        raise ValueError("Invalid evaluation corpus manifest") from None
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
        raise ValueError("Invalid evaluation corpus manifest fields")
    if (type(manifest["manifest_version"]) is not int or manifest["manifest_version"] != 1
            or not isinstance(manifest["corpus_version"], str)
            or not manifest["corpus_version"]
            or not isinstance(manifest["gate_status"], str)
            or manifest["gate_status"] not in {"complete", "blocked"}
            or type(manifest["intended_case_count"]) is not int
            or manifest["intended_case_count"] <= 0
            or type(manifest["intended_cases_per_split"]) is not int
            or manifest["intended_cases_per_split"] <= 0
            or type(manifest["intended_cases_per_type_per_split"]) is not int
            or manifest["intended_cases_per_type_per_split"] <= 0
            or type(manifest["case_count"]) is not int
            or manifest["case_count"] <= 0
            or not isinstance(manifest["missing_case_types"], list)
            or not isinstance(manifest["gate_blockers"], list)
            or not all(isinstance(item, str) and item for item in manifest["gate_blockers"])
            or not isinstance(manifest["counts_by_split"], dict)
            or not isinstance(manifest["counts_by_type"], dict)
            or not isinstance(manifest["files"], dict)
            or set(manifest["files"]) != _REQUIRED_FILES):
        raise ValueError("Invalid evaluation corpus manifest values")

    paths = {name: _safe_corpus_file(root, name) for name in _REQUIRED_FILES}
    file_bytes = {name: _read_bounded(path, _MAX_CORPUS_BYTES)
                  for name, path in paths.items()}
    for name, content in file_bytes.items():
        expected = manifest["files"][name]
        if not isinstance(expected, str) or sha256_bytes(content) != expected:
            raise ValueError("Evaluation corpus manifest hash mismatch")

    try:
        schema = json.loads(file_bytes["schema.json"].decode("utf-8"),
                            object_pairs_hook=_unique_object,
                            parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("Invalid EvaluationCase v1 schema JSON") from None
    if (not isinstance(schema, dict)
            or schema.get("title") != "MacroAtlas EvaluationCase v1"
            or schema.get("additionalProperties") is not False
            or not isinstance(schema.get("required"), list)
            or not all(isinstance(item, str) for item in schema["required"])
            or not isinstance(schema.get("properties"), dict)
            or set(schema["required"]) != EvaluationCase._FIELDS
            or set(schema["properties"]) != EvaluationCase._FIELDS):
        raise ValueError("EvaluationCase v1 schema does not match its contract")

    cases = read_cases(paths["cases.jsonl"])
    if len(cases) != manifest["case_count"]:
        raise ValueError("Evaluation corpus case count mismatch")
    actual_split_counts = {split: sum(case.split == split for case in cases)
                           for split in ("development", "validation", "holdout")}
    actual_type_counts = {case_type: sum(case.case_type == case_type for case in cases)
                          for case_type in ("rankable", "near_match", "insufficient_evidence",
                                            "unrelated")}
    if (manifest["counts_by_split"] != actual_split_counts
            or manifest["counts_by_type"] != actual_type_counts):
        raise ValueError("Evaluation corpus distribution count mismatch")
    expected_missing = [case_type for case_type in
                        ("rankable", "near_match", "insufficient_evidence", "unrelated")
                        if any(sum(case.split == split and case.case_type == case_type
                                   for case in cases)
                               != manifest["intended_cases_per_type_per_split"]
                               for split in ("development", "validation", "holdout"))]
    if manifest["missing_case_types"] != expected_missing:
        raise ValueError("Evaluation corpus missing-type declaration mismatch")
    if (manifest["intended_case_count"] != 3 * manifest["intended_cases_per_split"]
            or manifest["intended_cases_per_split"]
            != 4 * manifest["intended_cases_per_type_per_split"]):
        raise ValueError("Invalid initial case distribution target")
    complete = len(cases) == manifest["intended_case_count"] and not expected_missing
    if (manifest["gate_status"] == "complete") != complete:
        raise ValueError("Evaluation corpus gate status does not match its case counts")
    if not complete and not manifest["gate_blockers"]:
        raise ValueError("Blocked evaluation corpus needs an explicit blocker")
    if complete and manifest["gate_blockers"]:
        raise ValueError("Complete evaluation corpus cannot retain unresolved gate blockers")
    candidates = _load_candidates(paths["catalog_snapshot.json"])
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    for case in cases:
        references = (set(case.relevant_candidate_ids) | set(case.forbidden_candidate_ids)
                      | set(case.expected_match_status) | set(case.expected_fields))
        if not references.issubset(candidate_ids):
            raise ValueError("Evaluation case references a candidate outside the fixed snapshot")

    if repo_root is None:
        repo_roots = [parent for parent in (root, *root.parents)
                      if (parent / "AGENTS.md").is_file()]
        if not repo_roots:
            raise ValueError("Repository root is required to verify evidence references")
        repo_root = repo_roots[0]
    _verify_evidence_files(cases, Path(repo_root))
    return EvaluationCorpus(MappingProxyType(manifest), cases, candidates,
                            manifest["files"]["cases.jsonl"],
                            manifest["files"]["catalog_snapshot.json"])
