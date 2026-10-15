// Type → studio role, filled from the live vocabulary (GET /vocabulary) so types
// added at runtime are recognised. Pure studio helpers (reducers, ordering) can't
// call hooks, hence a module-level map. Empty until the vocabulary first loads.
let roles: Record<string, string> = {};

export function setTypeRoles(types: ReadonlyArray<{ value: string; role?: string }>): void {
  roles = Object.fromEntries(
    types.filter((t) => t.role).map((t) => [t.value, t.role as string]),
  );
}

export function roleForType(type: string): string | undefined {
  return roles[type];
}
