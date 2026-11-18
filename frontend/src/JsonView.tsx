import type { ReactNode } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { JSON_HIGHLIGHTS, jsonTokens } from './json'

const LINE_HEIGHT = 21
const PADDING = 16
const OVERSCAN = 40
const ALL_HIGHLIGHTS = JSON_HIGHLIGHTS.map(rule => rule.id)

export interface JsonHit { line: number; start: number }

function renderLine(line: string, query: string, active: number | undefined): ReactNode[] {
  const ranges: number[] = []
  if (query) {
    const lower = line.toLowerCase()
    for (let at = lower.indexOf(query); at !== -1; at = lower.indexOf(query, at + query.length)) ranges.push(at)
  }
  const nodes: ReactNode[] = []
  let offset = 0
  for (const token of jsonTokens(line)) {
    const end = offset + token.text.length
    const parts: ReactNode[] = []
    let cursor = offset
    for (const start of ranges) {
      const from = Math.max(start, cursor), to = Math.min(start + query.length, end)
      if (from >= to) continue
      if (from > cursor) parts.push(line.slice(cursor, from))
      parts.push(<mark key={from} className={start === active ? 'active' : undefined}>{line.slice(from, to)}</mark>)
      cursor = to
    }
    if (cursor < end) parts.push(line.slice(cursor, end))
    nodes.push(token.kind ? <span key={offset} className={`js-${token.kind}`}>{parts}</span> : <span key={offset}>{parts}</span>)
    offset = end
  }
  return nodes
}

/**
 * Highlighted JSON that renders only the visible lines, so multi-megabyte files stay responsive.
 * `query` (lowercase) marks search matches, `active` is scrolled into view, and a new `focus` object
 * scrolls its line to the top.
 */
export function JsonView({ lines, query = '', active, focus, highlights = ALL_HIGHLIGHTS }: {
  lines: string[]; query?: string; active?: JsonHit; focus?: { line: number } | null; highlights?: readonly string[]
}) {
  const width = useMemo(() => lines.reduce((longest, line) => Math.max(longest, line.length), 0), [lines])
  const ref = useRef<HTMLDivElement>(null)
  const [top, setTop] = useState(0)
  const [height, setHeight] = useState(600)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(() => setHeight(element.clientHeight))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    if (focus && ref.current) ref.current.scrollTop = focus.line * LINE_HEIGHT
  }, [focus])
  useEffect(() => {
    const element = ref.current
    if (!active || !element) return
    const y = PADDING + active.line * LINE_HEIGHT
    if (y < element.scrollTop || y + LINE_HEIGHT > element.scrollTop + element.clientHeight) element.scrollTop = y - element.clientHeight / 2
  }, [active])
  const first = Math.max(0, Math.floor(top / LINE_HEIGHT) - OVERSCAN)
  const last = Math.min(lines.length, Math.ceil((top + height) / LINE_HEIGHT) + OVERSCAN)
  // The active match only exists in the DOM once its line is rendered, so scroll horizontally afterwards.
  useEffect(() => {
    const element = ref.current
    const mark = element?.querySelector<HTMLElement>('mark.active')
    if (!element || !mark) return
    const x = mark.offsetLeft
    if (x < element.scrollLeft || x + mark.offsetWidth > element.scrollLeft + element.clientWidth) element.scrollLeft = Math.max(0, x - element.clientWidth / 3)
  }, [active, first])
  return <div ref={ref} className="json-view" onScroll={event => setTop(event.currentTarget.scrollTop)}>
    <pre style={{ height: lines.length * LINE_HEIGHT, minWidth: `${width}ch` }}>
      <code style={{ transform: `translateY(${first * LINE_HEIGHT}px)` }}>
        {lines.slice(first, last).map((line, index) => {
          const number = first + index
          return <div key={number} className={JSON_HIGHLIGHTS.some(rule => highlights.includes(rule.id) && rule.test.test(line)) ? 'json-line marked' : 'json-line'}>
            {renderLine(line, query, active?.line === number ? active.start : undefined)}
          </div>
        })}
      </code>
    </pre>
  </div>
}
