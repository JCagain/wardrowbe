import type { Dispatch, SetStateAction } from 'react';

// PartTypeSelect fires both callbacks in the same change event (picking a part
// resets the type). Value-form setters would both close over the same stale
// form and the second call would overwrite the first — so these must be
// functional updaters, each seeing the previous update's result.
export function partTypeChangeHandlers<T extends { body_part: string; type: string }>(
  setForm: Dispatch<SetStateAction<T>>,
) {
  return {
    onBodyPartChange: (bodyPart: string) =>
      setForm((prev) => ({ ...prev, body_part: bodyPart })),
    onTypeChange: (type: string) => setForm((prev) => ({ ...prev, type })),
  };
}
