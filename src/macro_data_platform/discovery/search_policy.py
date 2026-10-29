"""Versioned candidate ranking policies shared by evaluation and runtime search."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SearchPolicy:
    """Rank candidates only; this policy cannot confirm or collect a candidate."""

    version: str = "lexical-v1"
    limit: int = 50
    minimum_score: float = 0
    semantic_disambiguation: bool = False

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("policy version must be non-empty")
        if type(self.limit) is not int or not 1 <= self.limit <= 50:
            raise ValueError("policy limit must be between 1 and 50")
        if (isinstance(self.minimum_score, bool)
                or not isinstance(self.minimum_score, (int, float))
                or not 0 <= self.minimum_score <= 100):
            raise ValueError("minimum score must be between 0 and 100")
        if type(self.semantic_disambiguation) is not bool:
            raise ValueError("semantic_disambiguation must be a boolean")

    @property
    def sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def rank(self, request, candidates, *, limit=None, ranker=None):
        # Import at call time: the runtime search module owns the lexical scorer.
        if ranker is None:
            from macro_data_platform.discovery.series_search import rank_candidates

            ranker = rank_candidates

        result_limit = self.limit if limit is None else limit
        if type(result_limit) is not int or not 1 <= result_limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        ranked = ranker(request, candidates, limit=50)
        if self.semantic_disambiguation:
            for row in ranked:
                row["ranking_score"] = row["score"] + _semantic_adjustment(
                    request, row["candidate"],
                )
            ranked.sort(
                key=lambda row: (
                    -row["ranking_score"], -row["score"], row["candidate"].candidate_id,
                )
            )
        return [row for row in ranked if row["score"] >= self.minimum_score][:result_limit]


def _semantic_adjustment(request, candidate) -> float:
    """Apply explicit measure/basis contrasts reviewed in Gate C."""
    query = " ".join(re.findall(
        r"[a-z0-9%$]+", f"{request.text} {request.concept or ''}".casefold(),
    ))
    label = " ".join(re.findall(r"[a-z0-9%$]+", candidate.label.casefold()))
    adjustment = 0.0

    asks_gdp = "gdp" in query
    asks_per_capita = any(phrase in query for phrase in ("per capita", "per person", "per head"))
    candidate_per_capita = any(
        phrase in label for phrase in ("per capita", "per person", "per head")
    )
    if asks_gdp and asks_per_capita:
        adjustment += 35 if candidate_per_capita else -35
    elif asks_gdp:
        adjustment += -35 if candidate_per_capita else 12

    asks_ppp = "ppp" in query or "purchasing power parity" in query or "international dollars" in query
    asks_constant = "constant" in query or "real gdp" in query
    asks_current = (
        "nominal" in query or "current price" in query
        or ("current" in query.split() and ("dollar" in query or "$" in query))
    )
    candidate_ppp = "ppp" in label or "purchasing power parity" in label or "international $" in label
    candidate_constant = "constant" in label or "real gdp" in label
    candidate_current = "current" in label and ("$" in label or "dollar" in label)
    if asks_ppp:
        adjustment += 30 if candidate_ppp else -35
    elif asks_constant:
        adjustment += 30 if candidate_constant else -35
    elif asks_current:
        adjustment += 30 if candidate_current and not candidate_ppp else -35

    asks_price_rate = (
        ("inflation" in query or any(word in query.split() for word in (
            "rise", "rose", "rising", "increase", "increased", "increasing", "fast",
        ))) and any(phrase in query for phrase in ("consumer price", "consumer prices", "cpi"))
    )
    asks_price_index = ("cpi" in query or "consumer price index" in query) and not asks_price_rate
    candidate_price_rate = "inflation" in label and "consumer" in label
    candidate_price_index = "consumer price index" in label
    candidate_gdp_deflator = "gdp deflator" in label
    excludes_consumer_inflation = any(phrase in query for phrase in (
        "not the consumer", "not consumer", "not cpi", "rather than cpi",
        "rather than the consumer", "distinct from cpi", "distinct from consumer",
        "exclude cpi", "exclude the consumer", "not the consumer price basket",
    ))
    asks_gdp_deflator = "gdp deflator" in query
    if asks_gdp_deflator and excludes_consumer_inflation:
        adjustment += 45 if candidate_gdp_deflator else -45 if candidate_price_rate else 0
    elif asks_price_rate:
        if candidate_price_rate:
            adjustment += 35
        elif candidate_price_index or candidate_gdp_deflator:
            adjustment -= 40
    elif asks_price_index:
        if candidate_price_index:
            adjustment += 35
        elif candidate_price_rate:
            adjustment -= 40
    return adjustment


PROMOTED_SEARCH_POLICY = SearchPolicy(
    version="semantic-disambiguation-v1",
    limit=50,
    minimum_score=37.5,
    semantic_disambiguation=True,
)
