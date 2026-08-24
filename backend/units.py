# 1 CCF = 748 gallons -- the billing unit printed on SFPUC statements. Readings
# flagged unit=0 ("gallons") are stored in *thousands* of gallons, so this is 748
# in kgal (0.748), not 748 itself. Single source of truth: previously duplicated
# across main.py and oracle_ai.py, which is how it went wrong once before (see
# commit ba2eeb8, "gallons per unit is actually off by a factor of 100").
GALLONS_PER_UNIT = 0.748


def to_units(reading: float, unit: int) -> float:
    """unit: 0 = gallons (needs conversion), 1 = already units of water (CCF)."""
    return reading if unit == 1 else reading / GALLONS_PER_UNIT
