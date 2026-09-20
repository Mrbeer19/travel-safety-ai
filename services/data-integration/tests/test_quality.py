"""Quality gates retain explicit unknown, stale, and conflicting evidence."""

from app.domain.canonical import DataQuality
from app.pipeline.quality import QualityPolicy, summarize_quality

POLICY = QualityPolicy("review-1", 0.8, 0.7, 3600)


def quality(
    *,
    status: str = "FRESH",
    score: float | None = 0.9,
    coverage: float | None = 0.9,
    freshness_seconds: int | None = 60,
    conflicts: list[str] | None = None,
) -> DataQuality:
    return DataQuality(
        status=status,
        score=score,
        score_version="1.0.0" if score is not None else None,
        coverage=coverage,
        freshness_seconds=freshness_seconds,
        conflicts=conflicts or [],
    )


def summarize(
    sources: dict[str, DataQuality], *, identity_valid: bool = True, geometry_valid: bool = True
):
    return summarize_quality(
        sources,
        required=frozenset({"weather", "route"}),
        policy=POLICY,
        identity_valid=identity_valid,
        geometry_valid=geometry_valid,
    )


def test_required_evidence_and_invalid_identity_block() -> None:
    missing = summarize({"weather": quality()})
    assert missing.gate == "BLOCK"
    assert missing.missing_critical == ("route",)
    assert "MISSING" in missing.flags
    invalid = summarize({"weather": quality(), "route": quality()}, identity_valid=False)
    assert invalid.gate == "BLOCK"


def test_unknown_score_or_stale_source_degrades() -> None:
    unknown = summarize({"weather": quality(score=None), "route": quality(score=None)})
    assert unknown.gate == "DEGRADED"
    assert unknown.score is None
    stale = summarize({"weather": quality(freshness_seconds=3601), "route": quality()})
    assert stale.gate == "DEGRADED"
    assert "STALE" in stale.flags


def test_conflict_preserved_and_clean_sources_pass() -> None:
    sources = {"weather": quality(), "route": quality()}
    assert summarize(sources).gate == "PASS"
    sources["weather"] = quality(status="CONFLICTING", conflicts=["severity"])
    result = summarize(sources)
    assert result.gate == "DEGRADED"
    assert result.conflict_count == 1
    assert "CONFLICTING" in result.flags
