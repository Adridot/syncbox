/* B4 — a preview must make INVISIBLE changes visible. The backend never
   emits a no-op row, so a before/after pair that LOOKS identical always
   hides a real change: leading/trailing spaces, doubled spaces, or
   non-ASCII whitespace (NBSP & friends). Mark them git-diff style. */

export interface Segment {
  text: string
  mark: boolean
}

// Invisible-but-not-a-plain-space characters (NBSP, ogham, en/em spaces,
// zero-width, narrow NBSP, math space, ideographic space, BOM).
const INVISIBLE = '\\u00A0\\u1680\\u2000-\\u200B\\u202F\\u205F\\u3000\\uFEFF'
const SUSPECT = () =>
  new RegExp(`(^\\s+)|(\\s+$)|([ \\t]{2,})|([${INVISIBLE}\\t])`, 'g')

/** Split a value into plain/marked segments; marked segments carry suspect
    whitespace (rendered as visible dots by the caller). Normal single
    inter-word spaces stay unmarked. */
export function markInvisible(value: string): Segment[] {
  const segments: Segment[] = []
  let cursor = 0
  for (const match of value.matchAll(SUSPECT())) {
    const start = match.index ?? 0
    if (start > cursor) segments.push({ text: value.slice(cursor, start), mark: false })
    segments.push({ text: match[0], mark: true })
    cursor = start + match[0].length
  }
  if (cursor < value.length) segments.push({ text: value.slice(cursor), mark: false })
  return segments
}

/** Visible stand-in for a marked run: one dot per character. */
export function dots(text: string): string {
  return '·'.repeat(text.length)
}

/** True when before → after differ only by suspect whitespace — the case
    that MUST be explained to the eye (B4 legend). */
export function invisibleOnlyChange(before: string, after: string): boolean {
  const canon = (value: string) =>
    value.replace(new RegExp(`[\\s${INVISIBLE}]+`, 'g'), ' ').trim()
  return before !== after && canon(before) === canon(after)
}
