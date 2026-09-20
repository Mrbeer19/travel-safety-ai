"""Strict module 04 input shapes for the Phase 2 storage boundary.

These describe the producer's actual wire payload. The shared route output
contract uses ``sources[]``; the module 04 input currently carries ``source``.
The input distinction is retained until the producer/consumer contract is locked.
"""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class GeoPoint(StrictRecord):
    type: Literal["Point"]
    coordinates: tuple[FiniteFloat, FiniteFloat]

    @model_validator(mode="after")
    def in_range(self) -> Self:
        lon, lat = self.coordinates
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("GeoJSON point outside lon/lat range")
        return self


class GeoLineString(StrictRecord):
    type: Literal["LineString"]
    coordinates: list[tuple[FiniteFloat, FiniteFloat]] = Field(min_length=2)

    @model_validator(mode="after")
    def in_range(self) -> Self:
        for lon, lat in self.coordinates:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("GeoJSON line outside lon/lat range")
        if len(set(self.coordinates)) < 2:
            raise ValueError("route line has no distinct points")
        return self


class SourceProvenance(StrictRecord):
    source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_record_id: str | None = None
    authority: Literal["OFFICIAL", "INTERGOVERNMENTAL", "LICENSED_PROVIDER", "COMMUNITY", "UNKNOWN"]
    source_url: str | None = None
    license: str | None = None
    attribution: str | None = None
    observed_at: AwareDatetime | None = None
    published_at: AwareDatetime | None = None
    fetched_at: AwareDatetime
    expires_at: AwareDatetime | None = None
    content_hash: str | None = None
    schema_version: str = Field(pattern=r"^1\.[0-9]+\.[0-9]+$")


class DataQuality(StrictRecord):
    status: Literal["FRESH", "STALE", "UNAVAILABLE", "CONFLICTING", "PARTIAL"]
    score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    score_version: str | None = None
    flags: list[
        Literal["MISSING", "STALE", "CONFLICTING", "INFERRED", "INCOMPLETE", "OUTSIDE_COVERAGE"]
    ] = Field(default_factory=list)
    coverage: FiniteFloat | None = Field(default=None, ge=0, le=1)
    completeness: FiniteFloat | None = Field(default=None, ge=0, le=1)
    freshness_seconds: int | None = Field(default=None, ge=0)
    conflicts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def score_needs_version(self) -> Self:
        if self.score is not None and not self.score_version:
            raise ValueError("score requires score_version")
        return self


Severity = Literal["INFO", "MINOR", "MODERATE", "SEVERE", "EXTREME", "UNKNOWN"]
TravelMode = Literal["FLIGHT", "TRAIN", "BUS", "CAR", "WALK", "BICYCLE", "MULTIMODAL"]


class WeatherForecastPoint(StrictRecord):
    id: str = Field(min_length=1)
    location: GeoPoint
    valid_at: AwareDatetime
    temperature_c: FiniteFloat | None = None
    apparent_temperature_c: FiniteFloat | None = None
    precipitation_mm: FiniteFloat | None = Field(default=None, ge=0)
    precipitation_probability: int | None = Field(default=None, ge=0, le=100)
    snowfall_cm: FiniteFloat | None = Field(default=None, ge=0)
    wind_speed_kmh: FiniteFloat | None = Field(default=None, ge=0)
    wind_gust_kmh: FiniteFloat | None = Field(default=None, ge=0)
    visibility_m: FiniteFloat | None = Field(default=None, ge=0)
    weather_code: int | None = None
    severity: Severity
    quality: DataQuality
    source: SourceProvenance
    eta_offset_seconds: int | None = None
    sample_id: str | None = None


class DisasterEvent(StrictRecord):
    event_id: str = Field(min_length=1)
    event_type: Literal[
        "EARTHQUAKE",
        "CYCLONE",
        "STORM",
        "FLOOD",
        "WILDFIRE",
        "VOLCANO",
        "LANDSLIDE",
        "EXTREME_TEMPERATURE",
        "HEALTH",
        "TRANSPORT_CLOSURE",
        "OTHER",
    ]
    title: str
    description: str | None = None
    severity: Severity
    geometry: GeoPoint
    effective_at: AwareDatetime
    ends_at: AwareDatetime | None = None
    instruction: str | None = None
    official: bool
    quality: DataQuality
    source: SourceProvenance
    magnitude: FiniteFloat | None = None
    magnitude_unit: str | None = None
    depth_km: FiniteFloat | None = None
    alert_level: str | None = None
    tsunami: bool | None = None
    cross_reference_ids: list[str] = Field(default_factory=list)
    reporting_networks: list[str] = Field(default_factory=list)
    episode_id: str | None = None

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.ends_at is not None and self.ends_at < self.effective_at:
            raise ValueError("event ends before it becomes effective")
        return self


class RouteStep(StrictRecord):
    distance_m: FiniteFloat = Field(ge=0)
    duration_seconds: FiniteFloat = Field(ge=0)
    instruction: str | None = None
    street_name: str | None = None
    way_points: tuple[int, int] | None = None


class RouteSegment(StrictRecord):
    segment_id: str = Field(min_length=1)
    mode: TravelMode
    from_name: str | None = None
    to_name: str | None = None
    geometry: GeoLineString | None = None
    distance_m: FiniteFloat = Field(ge=0)
    duration_seconds: FiniteFloat = Field(ge=0)
    departure_time: AwareDatetime | None = None
    arrival_time: AwareDatetime | None = None
    transport_status_id: str | None = None
    steps: list[RouteStep] = Field(default_factory=list)


class RouteCandidate(StrictRecord):
    route_id: str = Field(min_length=1)
    provider_route_id: str | None = None
    label: Literal["ORIGINAL", "RECOMMENDED", "FASTEST", "LOWEST_RISK", "ALTERNATIVE"]
    mode: TravelMode
    geometry: GeoLineString
    segments: list[RouteSegment] = Field(default_factory=list)
    distance_m: FiniteFloat = Field(ge=0)
    duration_seconds: FiniteFloat = Field(ge=0)
    transfers: int = Field(ge=0)
    exposure: None = None
    risk_level: Literal["UNKNOWN"]
    quality: DataQuality
    source: SourceProvenance
    bbox: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat] | None = None


class StopRef(StrictRecord):
    stop_id: str | None = None
    name: str
    coordinates: GeoPoint | None = None


class Cancellation(StrictRecord):
    cancelled: bool
    reason: str | None = None
    announced_at: AwareDatetime | None = None


class TransportStatus(StrictRecord):
    id: str = Field(min_length=1)
    mode: TravelMode
    operator: str | None = None
    service_number: str | None = None
    origin_stop: StopRef
    destination_stop: StopRef
    scheduled_departure: AwareDatetime | None = None
    estimated_departure: AwareDatetime | None = None
    scheduled_arrival: AwareDatetime | None = None
    estimated_arrival: AwareDatetime | None = None
    status: Literal["ON_TIME", "DELAYED", "CANCELLED", "DISRUPTED", "UNKNOWN"]
    delay_minutes: int | None = None
    cancellation: Cancellation | None = None
    quality: DataQuality
    source: SourceProvenance
    feed_id: str | None = None

    @model_validator(mode="after")
    def on_time_requires_measurement(self) -> Self:
        if self.status == "ON_TIME" and self.delay_minutes is None:
            raise ValueError("ON_TIME requires measured delay")
        return self


class EmergencyPlace(StrictRecord):
    place_id: str = Field(min_length=1)
    place_type: Literal[
        "HOSPITAL",
        "CLINIC",
        "DOCTOR",
        "PHARMACY",
        "POLICE",
        "FIRE_STATION",
        "EMBASSY",
        "TOWNHALL",
        "OTHER",
    ]
    name: str | None = None
    location: GeoPoint
    distance_m: FiniteFloat | None = Field(default=None, ge=0)
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    provider_category: str | None = None
    quality: DataQuality
    source: SourceProvenance


RecordModel = (
    WeatherForecastPoint | DisasterEvent | RouteCandidate | TransportStatus | EmergencyPlace
)
RECORD_MODELS: dict[str, type[StrictRecord]] = {
    "weather": WeatherForecastPoint,
    "disaster": DisasterEvent,
    "route": RouteCandidate,
    "transport": TransportStatus,
    "place": EmergencyPlace,
}
