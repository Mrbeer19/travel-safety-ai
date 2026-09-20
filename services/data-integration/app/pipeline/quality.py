"""Versioned, deterministic quality aggregation for integrated evidence."""

from dataclasses import dataclass
from typing import Literal

from app.domain.canonical import DataQuality

Gate = Literal["PASS", "DEGRADED", "BLOCK"]


@dataclass(frozen=True)
class QualityPolicy:
    version: str
    minimum_coverage: float
    minimum_score: float
    maximum_freshness_seconds: int

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("quality policy version required")
        if not (0 <= self.minimum_coverage <= 1 and 0 <= self.minimum_score <= 1):
            raise ValueError("quality thresholds must be within [0, 1]")
        if self.maximum_freshness_seconds < 0:
            raise ValueError("freshness threshold must be nonnegative")


@dataclass(frozen=True)
class QualitySummary:
    policy_version: str
    gate: Gate
    score: float | None
    coverage: float | None
    flags: tuple[str, ...]
    missing_critical: tuple[str, ...]
    conflict_count: int
    source_count: int


def summarize_quality(
    sources: dict[str, DataQuality],
    *,
    required: frozenset[str],
    policy: QualityPolicy,
    identity_valid: bool,
    geometry_valid: bool,
) -> QualitySummary:
    """Keep missing evidence visible and never promote unknown scores to zero."""
    missing = tuple(
        sorted(
            name
            for name in required
            if name not in sources or sources[name].status == "UNAVAILABLE"
        )
    )
    score_values = [q.score for q in sources.values() if q.score is not None]
    coverage_values = [q.coverage for q in sources.values() if q.coverage is not None]
    flags = {flag for quality in sources.values() for flag in quality.flags}
    if missing:
        flags.add("MISSING")
    conflict_count = sum(len(quality.conflicts) for quality in sources.values())
    if conflict_count or any(q.status == "CONFLICTING" for q in sources.values()):
        flags.add("CONFLICTING")
    if any(
        q.status == "STALE"
        or (
            q.freshness_seconds is not None
            and q.freshness_seconds > policy.maximum_freshness_seconds
        )
        for q in sources.values()
    ):
        flags.add("STALE")
    score = min(score_values) if score_values else None
    coverage = min(coverage_values) if coverage_values else None
    if not identity_valid or not geometry_valid or missing:
        gate: Gate = "BLOCK"
    elif (
        score is None
        or coverage is None
        or score < policy.minimum_score
        or coverage < policy.minimum_coverage
        or flags
        or any(q.status != "FRESH" for q in sources.values())
    ):
        gate = "DEGRADED"
    else:
        gate = "PASS"
    return QualitySummary(
        policy.version,
        gate,
        score,
        coverage,
        tuple(sorted(flags)),
        missing,
        conflict_count,
        len(sources),
    )
