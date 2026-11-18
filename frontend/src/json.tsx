// Groups: 1 key (string followed by a colon), 2 string, 3 number, 4 literal.
const pattern = /("(?:[^"\\\n]|\\.)*")(?=\s*:)|("(?:[^"\\\n]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g

export const JSON_HIGHLIGHTS = [
  { id: 'attackTag', label: 'Attack Tag', test: /^\s*"attackTag"\s*:/ },
  { id: 'hitImpulseType', label: 'Hit Impulse Type', test: /^\s*"hitImpulseType"\s*:/ },
  { id: 'elementDurability', label: 'Element Durability', test: /^\s*"elementDurability"\s*:/ },
  { id: 'enBreak', label: 'Poise (enBreak)', test: /^\s*"enBreak"\s*:/ },
  { id: 'attenuationTag', label: 'Attenuation Tag', test: /^\s*"attenuationTag"\s*:/ },
  { id: 'attenuationGroup', label: 'Attenuation Group', test: /^\s*"attenuationGroup"\s*:/ },
  { id: 'blunt', label: 'Strike Type: Blunt', test: /^\s*"strikeType"\s*:\s*"Blunt"/i },
]

export interface JsonToken { text: string; kind?: 'key' | 'string' | 'number' | 'literal' }

/** Shortest decimal (up to seven places) that preserves an extracted float32 value. */
export function cleanFloat32(value: number): number {
  if (!Number.isFinite(value) || Number.isInteger(value) || Math.fround(value) !== value) return value
  for (let digits = 0; digits < 8; digits++) {
    const rounded = Number(value.toFixed(digits))
    if (Math.fround(rounded) === value) return rounded
  }
  return value
}

export function jsonTokens(text: string): JsonToken[] {
  const tokens: JsonToken[] = []
  let last = 0
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) tokens.push({ text: text.slice(last, match.index) })
    tokens.push({ text: match[0], kind: match[1] ? 'key' : match[2] ? 'string' : match[3] ? 'number' : 'literal' })
    last = match.index + match[0].length
  }
  if (last < text.length) tokens.push({ text: text.slice(last) })
  return tokens
}

/** A copy of `value` with every object's keys in case-insensitive alphabetical order. */
export function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys)
  if (typeof value !== 'object' || value === null) return value
  return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b, 'en', { sensitivity: 'base' }) || (a < b ? -1 : 1))
    .map(([key, child]) => [key, sortKeys(child)]))
}

export interface JsonMatch { ability?: string; path: string; value: unknown }

/**
 * Values selected by `pick` with their path and enclosing ability name. `pick(key, value)` returns
 * the value to keep, or undefined to keep searching inside it; `key` is null for array items and the root.
 */
export function findJson(root: unknown, pick: (key: string | null, value: unknown) => unknown): JsonMatch[] {
  const matches: JsonMatch[] = []
  const walk = (key: string | null, value: unknown, path: string, ability: string | undefined) => {
    const picked = pick(key, value)
    if (picked !== undefined) { matches.push({ ability, path: path || '(root)', value: picked }); return }
    if (Array.isArray(value)) { value.forEach((child, index) => walk(null, child, `${path}[${index}]`, ability)); return }
    if (typeof value !== 'object' || value === null) return
    const record = value as Record<string, unknown>
    if (typeof record.abilityName === 'string') ability = record.abilityName
    for (const [name, child] of Object.entries(record)) walk(name, child, path ? `${path}.${name}` : name, ability)
  }
  walk(null, root, '', undefined)
  return matches
}
