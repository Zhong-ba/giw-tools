import type { ReactElement, ReactNode } from 'react'
import { isValidElement, useEffect } from 'react'

/** Start offsets of every case-insensitive match of `needle` (lowercase) in `text`. */
export function findMatches(text: string, needle: string, limit = 100000): number[] {
  const found: number[] = []
  if (!needle) return found
  const lower = text.toLowerCase()
  for (let at = lower.indexOf(needle); at !== -1 && found.length < limit; at = lower.indexOf(needle, at + needle.length)) found.push(at)
  return found
}

/**
 * Wraps the matches in <mark>s inside highlighter output: plain strings and spans holding a string.
 * `starts` are match offsets in the joined text, and the match starting at `active` gets the active style.
 */
export function markMatches(nodes: ReactNode[], starts: number[], length: number, active?: number): ReactNode[] {
  if (!starts.length) return nodes
  let offset = 0, next = 0
  const split = (text: string) => {
    const end = offset + text.length
    const parts: ReactNode[] = []
    let cursor = offset
    while (next < starts.length && starts[next] + length <= offset) next++
    for (let index = next; index < starts.length && starts[index] < end; index++) {
      const start = starts[index]
      const from = Math.max(start, cursor), to = Math.min(start + length, end)
      if (from >= to) continue
      if (from > cursor) parts.push(text.slice(cursor - offset, from - offset))
      parts.push(<mark key={from} className={start === active ? 'active' : undefined}>{text.slice(from - offset, to - offset)}</mark>)
      cursor = to
    }
    if (cursor < end) parts.push(text.slice(cursor - offset))
    offset = end
    return parts
  }
  return nodes.map((node, index) => {
    if (typeof node === 'string') return <span key={`m${index}`}>{split(node)}</span>
    if (isValidElement(node)) {
      const element = node as ReactElement<{ className?: string; children?: ReactNode }>
      if (typeof element.props.children === 'string') return <span key={element.key ?? index} className={element.props.className}>{split(element.props.children)}</span>
    }
    return node
  })
}

/** Ctrl+F opens this search instead of the browser's while `enabled`. */
export function useFindShortcut(enabled: boolean, open: () => void) {
  useEffect(() => {
    if (!enabled) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'f') {
        event.preventDefault()
        open()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [enabled, open])
}
