from backend.units import GALLONS_PER_UNIT, to_units


def test_to_units_passes_through_ccf_unchanged():
    assert to_units(12.5, unit=1) == 12.5


def test_to_units_converts_gallons_unit_to_ccf():
    assert to_units(GALLONS_PER_UNIT, unit=0) == 1.0


def test_to_units_zero_reading():
    assert to_units(0.0, unit=0) == 0.0
    assert to_units(0.0, unit=1) == 0.0
