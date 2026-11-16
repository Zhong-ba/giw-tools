import type { RefObject } from 'react'
import { ChevronDown, ChevronUp, Search, X } from 'lucide-react'

/** The find bar of the Game Data and output file previews. */
export function SearchBar({ inputRef, label, query, count, index, onQuery, onStep, onClose }: {
  inputRef: RefObject<HTMLInputElement | null>; label: string; query: string; count: number; index: number
  onQuery: (query: string) => void; onStep: (direction: number) => void; onClose: () => void
}) {
  return <div className="reference-search" role="search">
    <Search size={14} />
    <input ref={inputRef} autoFocus aria-label={label} placeholder={label} value={query}
      onChange={event => onQuery(event.target.value)}
      onKeyDown={event => {
        if (event.key === 'Enter') { event.preventDefault(); onStep(event.shiftKey ? -1 : 1) }
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose() }
      }} />
    <span className="reference-search-count">{query ? count ? `${Math.min(index, count - 1) + 1} / ${count.toLocaleString()}` : 'No results' : ''}</span>
    <button className="icon-button" onClick={() => onStep(-1)} disabled={!count} aria-label="Previous match" title="Previous (Shift+Enter)"><ChevronUp size={15} /></button>
    <button className="icon-button" onClick={() => onStep(1)} disabled={!count} aria-label="Next match" title="Next (Enter)"><ChevronDown size={15} /></button>
    <button className="icon-button" onClick={onClose} aria-label="Close search" title="Close (Esc)"><X size={15} /></button>
  </div>
}
