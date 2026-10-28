"""Source-guide snapshots and explicit institution-strategy selection."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol
from urllib.parse import urlsplit

from macro_data_platform.contracts import EvidenceKind, utc

MAX_GUIDE_BYTES = 1_048_576
MAX_EXTRACTION_STEPS = 30
_TAG = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")


class GuideCategory(str, Enum):
    API_GUIDE = "api_guide"
    USAGE_POLICY = "usage_policy"
    CODEBOOK = "codebook"
    STATISTICAL_EXPLANATION = "statistical_explanation"


class GuideChangeStatus(str, Enum):
    FIRST_SEEN = "first_seen"
    UNCHANGED = "unchanged"
    CHANGED = "changed"


class StrategySelectionStatus(str, Enum):
    SELECTED = "selected"
    NO_MATCH = "no_match"
    NEEDS_REVIEW = "needs_review"
    GUIDE_EXPIRED = "guide_expired"
    GUIDE_CHANGED = "guide_changed"


def _fingerprint(document: dict) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SourceGuide:
    institution_id: str
    category: GuideCategory
    title: str
    source_url: str
    media_type: str
    original_body: bytes
    extraction_path: tuple[str, ...]
    retrieved_at: datetime
    evidence_kind: EvidenceKind
    evidence_ref: str
    extracted_text: str | None = None
    expires_at: datetime | None = None
    source_version: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("institution_id", "title", "media_type", "evidence_ref"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be nonempty")
        if len(self.title) > 256 or len(self.media_type) > 128 or len(self.evidence_ref) > 2_048:
            raise ValueError("guide text metadata exceeds the configured limit")
        if not isinstance(self.category, GuideCategory):
            raise TypeError("category must be a GuideCategory")
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise TypeError("evidence_kind must be an EvidenceKind")
        if self.evidence_kind not in {EvidenceKind.FIXTURE, EvidenceKind.OFFICIAL_DOCS}:
            raise ValueError("guide snapshots accept fixture or official documentation evidence only")
        if not isinstance(self.original_body, bytes):
            raise TypeError("original_body must be bytes")
        if not self.original_body or len(self.original_body) > MAX_GUIDE_BYTES:
            raise ValueError("guide body must be nonempty and within the size limit")
        if self.extracted_text is not None:
            if not isinstance(self.extracted_text, str):
                raise TypeError("extracted_text must be text or None")
            if len(self.extracted_text.encode("utf-8")) > MAX_GUIDE_BYTES:
                raise ValueError("extracted_text exceeds the configured size limit")
        if not isinstance(self.extraction_path, tuple) or not self.extraction_path:
            raise ValueError("extraction_path must be a nonempty tuple")
        if len(self.extraction_path) > MAX_EXTRACTION_STEPS or any(
            not isinstance(step, str) or not step.strip() or len(step) > 256
            for step in self.extraction_path
        ):
            raise ValueError("extraction_path contains invalid or excessive steps")
        if not isinstance(self.source_url, str) or len(self.source_url) > 2_048:
            raise ValueError("source_url is empty or too long")
        parsed = urlsplit(self.source_url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
        ):
            raise ValueError("source_url must be HTTPS, credential-free and query-free")
        utc(self.retrieved_at)
        if self.expires_at is not None:
            utc(self.expires_at)
        if self.source_version is not None and (
            not isinstance(self.source_version, str) or len(self.source_version) > 128
        ):
            raise ValueError("source_version exceeds the configured limit")

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.original_body).hexdigest()

    @property
    def revision_sha256(self) -> str:
        """Fingerprint guide meaning and policy metadata, excluding fetch time."""
        document = self.metadata()
        document.pop("retrieved_at")
        return _fingerprint(document)

    def metadata(self) -> dict:
        return {
            "institution_id": self.institution_id,
            "category": self.category.value,
            "title": self.title,
            "source_url": self.source_url,
            "media_type": self.media_type,
            "content_sha256": self.content_sha256,
            "extraction_path": list(self.extraction_path),
            "retrieved_at": self.retrieved_at.isoformat(),
            "evidence_kind": self.evidence_kind.value,
            "evidence_ref": self.evidence_ref,
            "extracted_text": self.extracted_text,
            "expires_at": None if self.expires_at is None else self.expires_at.isoformat(),
            "source_version": self.source_version,
        }

    @property
    def guide_id(self) -> str:
        return _fingerprint(self.metadata())


@dataclass(frozen=True)
class GuideSaveResult:
    guide_id: str
    content_sha256: str
    change_status: GuideChangeStatus


@dataclass(frozen=True)
class GuideStrategyRule:
    institution_id: str
    strategy_id: str
    trigger_tags: tuple[str, ...]
    guide_ids: tuple[str, ...]
    created_at: datetime
    priority: int = 0

    def __post_init__(self) -> None:
        for field_name in ("institution_id", "strategy_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be nonempty")
        if len(self.institution_id) > 128 or len(self.strategy_id) > 128:
            raise ValueError("strategy identity exceeds the configured limit")
        if not isinstance(self.trigger_tags, tuple) or not self.trigger_tags:
            raise ValueError("trigger_tags must be a nonempty tuple")
        normalized = tuple(sorted({tag.strip().lower() for tag in self.trigger_tags
                                   if isinstance(tag, str) and tag.strip()}))
        if len(normalized) != len(self.trigger_tags) or any(
            not _TAG.fullmatch(tag) for tag in normalized
        ):
            raise ValueError("trigger_tags must be unique normalized tags")
        object.__setattr__(self, "trigger_tags", normalized)
        if not isinstance(self.guide_ids, tuple) or not self.guide_ids:
            raise ValueError("guide_ids must be a nonempty tuple")
        if len(self.guide_ids) > 20 or any(
            not isinstance(guide_id, str) or not guide_id.strip() or len(guide_id) > 128
            for guide_id in self.guide_ids
        ):
            raise ValueError("guide_ids must be bounded nonempty identifiers")
        if len(set(self.guide_ids)) != len(self.guide_ids):
            raise ValueError("guide_ids must be unique nonempty identifiers")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise TypeError("priority must be an integer")
        utc(self.created_at)

    def metadata(self) -> dict:
        return {
            "institution_id": self.institution_id,
            "strategy_id": self.strategy_id,
            "trigger_tags": list(self.trigger_tags),
            "guide_ids": list(self.guide_ids),
            "created_at": self.created_at.isoformat(),
            "priority": self.priority,
        }

    @property
    def rule_id(self) -> str:
        return _fingerprint(self.metadata())


@dataclass(frozen=True)
class StrategySelection:
    status: StrategySelectionStatus
    strategy_id: str | None = None
    rule_id: str | None = None
    guide_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    candidate_strategy_ids: tuple[str, ...] = ()


class GuideRepository(Protocol):
    def latest_strategy_rules(self, institution_id: str) -> tuple[GuideStrategyRule, ...]: ...

    def get_guide(self, guide_id: str) -> SourceGuide: ...

    def latest_for_source(self, guide: SourceGuide) -> SourceGuide: ...


class GuideStrategySelector:
    """Select only explicit institution rules backed by their exact guide snapshots."""

    def select(
        self,
        repository: GuideRepository,
        institution_id: str,
        requested_tags: tuple[str, ...],
        as_of: datetime,
    ) -> StrategySelection:
        utc(as_of)
        request_tags = {
            tag.strip().lower()
            for tag in requested_tags
            if isinstance(tag, str) and tag.strip() and _TAG.fullmatch(tag.strip().lower())
        }
        matches = [
            rule for rule in repository.latest_strategy_rules(institution_id)
            if set(rule.trigger_tags).issubset(request_tags)
        ]
        if not matches:
            return StrategySelection(StrategySelectionStatus.NO_MATCH)
        best_rank = max((len(rule.trigger_tags), rule.priority) for rule in matches)
        best = [rule for rule in matches if (len(rule.trigger_tags), rule.priority) == best_rank]
        if len(best) != 1:
            ids = tuple(sorted(rule.strategy_id for rule in best))
            return StrategySelection(
                StrategySelectionStatus.NEEDS_REVIEW,
                candidate_strategy_ids=ids,
                warnings=("strategy_match_is_ambiguous",),
            )
        rule = best[0]
        guides = tuple(repository.get_guide(guide_id) for guide_id in rule.guide_ids)
        if any(guide.institution_id != institution_id for guide in guides):
            return StrategySelection(
                StrategySelectionStatus.NEEDS_REVIEW,
                strategy_id=rule.strategy_id,
                rule_id=rule.rule_id,
                guide_ids=rule.guide_ids,
                warnings=("guide_institution_mismatch",),
            )
        for guide in guides:
            if guide.expires_at is not None and as_of >= guide.expires_at:
                return StrategySelection(
                    StrategySelectionStatus.GUIDE_EXPIRED,
                    strategy_id=rule.strategy_id,
                    rule_id=rule.rule_id,
                    guide_ids=rule.guide_ids,
                    warnings=(f"guide_expired:{guide.guide_id}",),
                )
        for guide in guides:
            latest = repository.latest_for_source(guide)
            if latest.revision_sha256 != guide.revision_sha256:
                return StrategySelection(
                    StrategySelectionStatus.GUIDE_CHANGED,
                    strategy_id=rule.strategy_id,
                    rule_id=rule.rule_id,
                    guide_ids=rule.guide_ids,
                    warnings=(f"guide_changed_requires_review:{guide.guide_id}",),
                )
        warnings = tuple(
            f"guide_expiry_unknown:{guide.guide_id}"
            for guide in guides
            if guide.expires_at is None
        )
        return StrategySelection(
            StrategySelectionStatus.SELECTED,
            strategy_id=rule.strategy_id,
            rule_id=rule.rule_id,
            guide_ids=rule.guide_ids,
            warnings=warnings,
        )
