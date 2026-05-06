/**
 * Exhaustive-switch helper. Place in the `default` branch of a switch over a
 * finite union; the compiler will reject the call if any case is unhandled,
 * and the runtime throws if a future enum addition reaches this branch
 * before the switch is updated.
 */
export function assertNever(value: never): never {
  throw new Error(`Unhandled discriminant: ${JSON.stringify(value)}`);
}
