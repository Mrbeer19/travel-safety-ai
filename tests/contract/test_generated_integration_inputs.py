"""Generated integration scalars retain the canonical constraints."""

import sys

import pytest
from pydantic import ValidationError

from conftest import GENERATED_PYTHON

sys.path.insert(0, str(GENERATED_PYTHON))

from smart_travel_contracts.integration_inputs import enums_schema, primitives_schema  # noqa: E402


def test_generated_input_scalars() -> None:
    assert enums_schema.TravelMode("CAR").value == "CAR"
    assert primitives_schema.RecordId.model_validate("ors:route").root == "ors:route"
    with pytest.raises(ValidationError):
        primitives_schema.RecordId.model_validate("bad record id")
