"""Generated integration scalars retain the canonical constraints."""

import sys
import json

import pytest
from pydantic import ValidationError

from conftest import GENERATED_PYTHON, REPO_ROOT

sys.path.insert(0, str(GENERATED_PYTHON))

from smart_travel_contracts.integration_inputs import enums_schema, primitives_schema  # noqa: E402


def test_generated_input_scalars() -> None:
    assert enums_schema.TravelMode("CAR").value == "CAR"
    assert primitives_schema.RecordId.model_validate("ors:route").root == "ors:route"
    with pytest.raises(ValidationError):
        primitives_schema.RecordId.model_validate("bad record id")


def test_generated_provenance_and_quality_accept_m04_route() -> None:
    from smart_travel_contracts.integration_inputs import data_quality_schema, geojson_schema, source_provenance_schema

    path = REPO_ROOT / "docs/handoffs/m04-records/route-candidates.json"
    route = json.loads(path.read_text(encoding="utf-8"))["records"][0]
    assert source_provenance_schema.SourceProvenance.model_validate(route["sources"][0])
    assert data_quality_schema.DataQuality.model_validate(route["quality"])
    assert geojson_schema.LineString.model_validate(route["geometry"])
