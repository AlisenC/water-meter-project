// 1 "unit of water" = 748 gallons — the billing unit printed on SFPUC statements.
// This is the canonical display unit for water consumption across the app.
export const GALLONS_PER_UNIT = 748;
export const CUBIC_FEET_TO_GALLONS = 7.48052;

// Reading.unit: 0 = gallons, 1 = cubic feet
export function toGallons(reading, unit) {
  const val = Number(reading) || 0;
  return unit === 1 ? val * CUBIC_FEET_TO_GALLONS : val;
}

export function toUnits(reading, unit) {
  return toGallons(reading, unit) / GALLONS_PER_UNIT;
}

// Inverse of toUnits for a cubic-feet-stored reading — used by manual-entry
// forms that let the user type a value in units of water.
export function unitsToCubicFeet(units) {
  return (Number(units) * GALLONS_PER_UNIT) / CUBIC_FEET_TO_GALLONS;
}
