// 1 "unit of water" = 748 gallons — the billing unit printed on SFPUC statements.
// This is the canonical display unit for water consumption across the app.
export const GALLONS_PER_UNIT = 748;

// Reading.unit: 0 = gallons, 1 = units of water (already in billing units)
export function toUnits(reading, unit) {
  const val = Number(reading) || 0;
  return unit === 1 ? val : val / GALLONS_PER_UNIT;
}
