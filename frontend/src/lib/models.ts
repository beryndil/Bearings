// Kept in sync with the Claude model IDs the backend accepts. Bump
// this list when a new model ships; leaving it frontend-side avoids
// a round-trip for what is essentially a static enum.
export const KNOWN_MODELS = [
  'claude-opus-4-7',
  'claude-sonnet-4-6',
  'claude-haiku-4-5-20251001',
] as const;

export type KnownModel = (typeof KNOWN_MODELS)[number];

export function isKnownModel(v: string): v is KnownModel {
  return (KNOWN_MODELS as readonly string[]).includes(v);
}
