// Locale messages merge by DEPTH: a frozen locale's nested object (e.g. its
// empty{}) would otherwise shadow the English base entirely and leave keys
// like empty.goToWardrobe rendering as raw key paths.
export function mergeMessages(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const baseValue = base[key];
    const bothObjects =
      value !== null && typeof value === 'object' && !Array.isArray(value) &&
      baseValue !== null && typeof baseValue === 'object' && !Array.isArray(baseValue);
    merged[key] = bothObjects
      ? mergeMessages(baseValue as Record<string, unknown>, value as Record<string, unknown>)
      : value;
  }
  return merged;
}
