import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Braces, Check, ChevronRight, Copy, FileText, FolderOpen, LoaderCircle, Search, X } from 'lucide-react'
import { api, datasetChoice, message } from './api'
import type { Character, PickerItem } from './api'
import { cleanFloat32, findJson, JSON_HIGHLIGHTS, sortKeys } from './json'
import { JsonView } from './JsonView'
import type { JsonHit } from './JsonView'
import { useFindShortcut } from './search'
import { SearchBar } from './SearchBar'
import { updateToolQuery } from './toolUrl'

interface ReferenceFile { key: string; relative: string; group: string; name: string; size: number; reasons: string[]; legacyKey?: string }
interface References { character: string; files: ReferenceFile[]; warnings: string[] }
interface TreeEntry { key: string; name: string; directory: boolean; size: number | null }
type Source = { kind: 'all' } | { kind: 'character' | 'enemy' | 'gadget'; id: number } | { kind: 'job'; id: string }
type Filter = 'all' | 'attackInfo' | 'elemBall'
const publicScopes = ['character', 'enemy', 'gadget'] as const
const defaultHighlights = JSON_HIGHLIGHTS.map(rule => rule.id)
const toolId = 'binoutput-viewer'
const filenameTerms = (name: string) => name.trim().toLowerCase().split(/\s+/).filter(Boolean)

function readViewerLink(jobId?: string) {
  const params = new URLSearchParams(jobId ? '' : location.search)
  const scope = publicScopes.flatMap(kind => {
    const raw = params.get(`${kind}_id`)
    const id = Number(raw)
    return raw && /^\d+$/.test(raw) && Number.isSafeInteger(id) && id > 0 ? [{ kind, id }] : []
  })[0]
  const rawFilter = params.get('filter')
  const filter: Filter = rawFilter === 'attackInfo' || rawFilter === 'elemBall' ? rawFilter : 'all'
  const path = params.get('path') ?? ''
  const highlights = params.get('highlights')
  return { scope, path: path.length <= 4096 ? path : '', name: (params.get('name') ?? '').slice(0, 120),
    filter,
    cleanDecimals: params.get('clean_decimals') !== 'false',
    highlights: highlights === null ? defaultHighlights : defaultHighlights.filter(id => highlights.split(',').includes(id)) }
}
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const filters: { id: Exclude<Filter, 'all'>; label: string; title: string; field: string
  pick: (key: string | null, value: unknown) => unknown }[] = [
  { id: 'attackInfo', label: 'Attack Info', title: 'Only the attackInfo blocks', field: 'attackInfo',
    pick: (key, value) => key === 'attackInfo' ? value : undefined },
  { id: 'elemBall', label: 'GenerateElemBall', title: 'Only the actions that generate elemental particles', field: 'action',
    pick: (_, value) => isRecord(value) && value.$type === 'GenerateElemBall' ? value : undefined },
]
const scopeQuery = (source: Source) => source.kind !== 'all' && source.kind !== 'job' ? `${source.kind}_id=${source.id}` : ''
const encodePath = (path: string) => path.split('/').map(encodeURIComponent).join('/')
const size = (bytes: number | null) => bytes === null ? '' : bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
const PICKER_ROW_HEIGHT = 32

function FilterPicker({ label, value, options, onChange }: {
  label: string; value: string; options: { value: string; label: string }[] | null; onChange: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [top, setTop] = useState(0)
  const [height, setHeight] = useState(PICKER_ROW_HEIGHT)
  const id = useId()
  const picker = useRef<HTMLDivElement>(null)
  const popup = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const matches = useMemo(() => {
    const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean)
    return (options ?? []).filter(option => terms.every(term => option.label.toLowerCase().includes(term)))
  }, [options, query])
  const first = Math.max(0, Math.floor(top / PICKER_ROW_HEIGHT) - 6)
  const last = Math.min(matches.length, Math.ceil((top + height) / PICKER_ROW_HEIGHT) + 6)
  useEffect(() => {
    if (!open) return
    input.current?.focus()
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !picker.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', dismiss, true)
    return () => document.removeEventListener('pointerdown', dismiss, true)
  }, [open])
  useLayoutEffect(() => {
    if (!open || !popup.current || !list.current) return
    const update = () => {
      const panel = popup.current, element = list.current
      if (!panel || !element) return
      const viewport = window.visualViewport
      let bottom = viewport ? viewport.offsetTop + viewport.height : window.innerHeight
      for (let ancestor = panel.parentElement; ancestor; ancestor = ancestor.parentElement) {
        if (getComputedStyle(ancestor).overflowY !== 'visible')
          bottom = Math.min(bottom, ancestor.getBoundingClientRect().bottom)
      }
      const bounds = element.getBoundingClientRect()
      const footer = panel.getBoundingClientRect().bottom - bounds.bottom
      setHeight(Math.max(PICKER_ROW_HEIGHT, Math.floor(bottom - bounds.top - footer - 8)))
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(popup.current)
    if (picker.current) observer.observe(picker.current)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    window.visualViewport?.addEventListener('resize', update)
    window.visualViewport?.addEventListener('scroll', update)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
      window.visualViewport?.removeEventListener('resize', update)
      window.visualViewport?.removeEventListener('scroll', update)
    }
  }, [open])
  const close = () => { setOpen(false); button.current?.focus() }
  const choose = (selected: string) => { onChange(selected); close() }
  return <div ref={picker} className="binoutput-picker" onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false)
  }}>
    <button ref={button} type="button" aria-label={`BinOutput ${label}`} aria-haspopup="listbox" aria-expanded={open}
      disabled={!options} onClick={() => { setQuery(''); setActive(0); setTop(0); setOpen(!open) }}>
      <span>{options ? options.find(option => option.value === value)?.label ?? `Select ${label === 'Enemy' ? 'an' : 'a'} ${label}` : `Loading ${label}...`}</span>
      <ChevronRight size={13} className={open ? 'expanded' : ''} />
    </button>
    {open && <div ref={popup} className="binoutput-picker-popup">
      <input ref={input} role="combobox" aria-label={`Search ${label}`} aria-autocomplete="list" aria-expanded="true"
        aria-controls={id} aria-activedescendant={active >= first && active < last ? `${id}-${active}` : undefined}
        placeholder="Search by Name, ID, or Type" value={query} onChange={event => {
          setQuery(event.target.value); setActive(0); setTop(0)
          if (list.current) list.current.scrollTop = 0
        }}
        onKeyDown={event => {
          if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close() }
          else if (event.key === 'Enter') { event.preventDefault(); if (matches[active]) choose(matches[active].value) }
          else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            const next = Math.max(0, Math.min(matches.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1)))
            setActive(next)
            const element = list.current, y = next * PICKER_ROW_HEIGHT
            if (element) {
              if (y < element.scrollTop) element.scrollTop = y
              else if (y + PICKER_ROW_HEIGHT > element.scrollTop + element.clientHeight)
                element.scrollTop = y + PICKER_ROW_HEIGHT - element.clientHeight
              setTop(element.scrollTop)
            }
          }
        }} />
      <div ref={list} id={id} role="listbox" aria-label={`${label} Options`}
        style={{ height: Math.min(height, matches.length * PICKER_ROW_HEIGHT) }}
        onScroll={event => setTop(event.currentTarget.scrollTop)}>
        <div role="presentation" style={{ position: 'relative', height: matches.length * PICKER_ROW_HEIGHT }}>
          {matches.slice(first, last).map((option, offset) => {
            const index = first + offset
            return <button key={option.value} id={`${id}-${index}`} type="button" role="option"
              aria-selected={value === option.value} aria-setsize={matches.length} aria-posinset={index + 1}
              tabIndex={-1} className={active === index ? 'active' : ''}
              style={{ position: 'absolute', top: index * PICKER_ROW_HEIGHT, height: PICKER_ROW_HEIGHT }}
              title={option.label} onMouseDown={event => { if (event.button === 0) event.preventDefault() }}
              onClick={event => { if (event.button === 0) choose(option.value) }}>
              {option.label}
            </button>
          })}
        </div>
      </div>
      <div className="muted" role="status">{!matches.length ? 'No matches.'
        : `${matches.length.toLocaleString()} ${matches.length === 1 ? 'match' : 'matches'}`}</div>
    </div>}
  </div>
}

function Directory({ path, name, selected, expanded, load, onSelect }: {
  path: string; name: string; selected: string; load: (path: string, signal: AbortSignal) => Promise<TreeEntry[]>
  expanded: boolean; onSelect: (key: string) => void
}) {
  const [open, setOpen] = useState(expanded || !path || selected.startsWith(`${path}/`))
  const [entries, setEntries] = useState<TreeEntry[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    load(path, controller.signal).then(result => {
      if (!controller.signal.aborted) { setEntries(result); setError('') }
    }).catch(reason => {
      if (!controller.signal.aborted) setError(message(reason))
    })
    return () => controller.abort()
  }, [open, path, load])
  return <div className="binoutput-directory">
    {path && <button className="binoutput-folder" aria-expanded={open} onClick={() => setOpen(!open)} title={path}>
      <ChevronRight size={13} className={open ? 'expanded' : ''} /><FolderOpen size={14} /><span>{name}</span>
    </button>}
    {open && <div className={path ? 'binoutput-children' : ''}>
      {error ? <div className="error-box" role="alert">{error}</div> : !entries ? <span className="binoutput-tree-loading"><LoaderCircle size={13} className="spin" /> Loading...</span> :
        entries.length === 0 ? <span className="muted">No JSON files.</span> : entries.map(entry => entry.directory
          ? <Directory key={entry.key} path={entry.key} name={entry.name} selected={selected} expanded={expanded} load={load} onSelect={onSelect} />
          : <button key={entry.key} className={`binoutput-file${selected === entry.key ? ' selected' : ''}`}
            aria-current={selected === entry.key ? 'true' : undefined} onClick={() => onSelect(entry.key)} title={`${entry.key}\n${size(entry.size)}`}>
            <FileText size={13} /><span>{entry.name}</span>
          </button>)}
    </div>}
  </div>
}

function Browser({ source, highlights, cleanDecimals, link, listings }: {
  source: Source; highlights: string[]; cleanDecimals: boolean
  link?: ReturnType<typeof readViewerLink>; listings: Map<string, TreeEntry[]>
}) {
  const [references, setReferences] = useState<References | null>(null)
  const [selected, setSelected] = useState(link?.path ?? '')
  const [text, setText] = useState('')
  const [filter, setFilter] = useState<Filter>(link?.filter ?? 'all')
  const [loading, setLoading] = useState(source.kind !== 'all' || !!link?.path)
  const [error, setError] = useState('')
  const [filename, setFilename] = useState(link?.name ?? '')
  const [foundNames, setFoundNames] = useState<{ term: string; entries: { key: string; name: string }[]; truncated: boolean; error?: string }>()
  const [copiedMode, setCopiedMode] = useState<boolean | null>(null)
  const [focus, setFocus] = useState<{ line: number } | null>(null)
  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState('')
  const [hitIndex, setHitIndex] = useState(0)
  const searchInput = useRef<HTMLInputElement>(null)
  const queryString = scopeQuery(source)
  const jobId = source.kind === 'job' ? source.id : null
  const legacyKey = references?.files.find(file => file.key === selected)?.legacyKey
  const related = source.kind !== 'all'
  const linkedPath = link?.path ?? ''
  const term = filename.trim()
  useEffect(() => {
    if (!link) return
    updateToolQuery(toolId, { path: selected || undefined, name: term || undefined, filter: filter === 'all' ? undefined : filter })
  }, [link, selected, filter, term])
  useEffect(() => {
    if (!term || related) return
    const controller = new AbortController()
    const start = setTimeout(() => {
      api<{ entries: { key: string; name: string }[]; truncated: boolean }>(
        `/binoutput/search?${new URLSearchParams({ name: term })}`, { signal: controller.signal },
      ).then(result => { if (!controller.signal.aborted) setFoundNames({ ...result, term }) })
        .catch(reason => {
          if (!controller.signal.aborted) setFoundNames({ term, entries: [], truncated: false, error: message(reason) })
        })
    }, 250)
    return () => { clearTimeout(start); controller.abort() }
  }, [term, related])
  const nameResults = useMemo(() => {
    if (!term) return undefined
    if (!related) return foundNames?.term === term ? foundNames : undefined
    if (!references) return undefined
    const terms = filenameTerms(term)
    const entries = references.files.flatMap(file => {
      const name = file.key.split('/').pop() ?? file.name
      return terms.every(part => name.toLowerCase().includes(part)) ? [{ key: file.key, name }] : []
    })
    return { entries: entries.slice(0, 100), truncated: entries.length > 100, error: undefined }
  }, [term, related, foundNames, references])
  useEffect(() => {
    if (!related) return
    const controller = new AbortController()
    const endpoint = jobId ? `/jobs/${jobId}/references` : `/binoutput/references?${queryString}`
    api<References>(endpoint, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return
      setReferences({ ...result, files: result.files.map(file => ({ ...file, key: file.relative, legacyKey: jobId ? file.key : undefined })) })
      if (linkedPath && !result.files.some(file => file.relative === linkedPath)) {
        setError('The linked file is not available in this scope.')
        setLoading(false)
      } else {
        setSelected(linkedPath || result.files[0]?.relative || '')
        if (!result.files.length) setLoading(false)
      }
    }).catch(reason => { if (!controller.signal.aborted) { setError(message(reason)); setLoading(false) } })
    return () => controller.abort()
  }, [jobId, queryString, related, linkedPath])
  const canLoadFile = !related || !!references?.files.some(file => file.key === selected)
  useEffect(() => {
    if (!selected || !canLoadFile) return
    const controller = new AbortController()
    const endpoint = jobId ? `/jobs/${jobId}/references/${encodePath(legacyKey ?? selected)}`
      : `/binoutput/file?path=${encodeURIComponent(selected)}${queryString ? `&${queryString}` : ''}`
    api<{ text: string }>(endpoint, { signal: controller.signal }).then(result => { if (!controller.signal.aborted) setText(result.text) })
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [jobId, selected, queryString, legacyKey, canLoadFile])
  const tree = useMemo(() => {
    const result = new Map<string, Map<string, TreeEntry>>()
    result.set('', new Map())
    for (const file of references?.files ?? []) {
      const parts = file.key.split('/')
      parts.forEach((name, index) => {
        const parent = parts.slice(0, index).join('/'), key = parts.slice(0, index + 1).join('/')
        if (!result.has(parent)) result.set(parent, new Map())
        result.get(parent)?.set(key, { key, name, directory: index < parts.length - 1, size: index === parts.length - 1 ? file.size : null })
      })
    }
    return result
  }, [references])
  const load = useCallback(async (path: string, signal: AbortSignal) => {
    if (!related) {
      const key = `${datasetChoice() ?? ''}:${path}`
      const cached = listings.get(key)
      if (cached) return cached
      const { entries } = await api<{ entries: TreeEntry[] }>(`/binoutput/tree?path=${encodeURIComponent(path)}`, { signal })
      if (!signal.aborted) {
        if (listings.size >= 64) listings.clear()
        listings.set(key, entries)
      }
      return entries
    }
    return [...(tree.get(path)?.values() ?? [])].map(entry => {
      let compact = entry
      while (compact.directory) {
        const children = [...(tree.get(compact.key)?.values() ?? [])]
        if (children.length !== 1 || !children[0].directory) break
        compact = { ...children[0], name: `${compact.name} / ${children[0].name}` }
      }
      return compact
    }).sort((a, b) => Number(b.directory) - Number(a.directory) || a.name.localeCompare(b.name))
  }, [related, tree, listings])
  const parsed = useMemo(() => {
    if (!text) return { value: undefined, error: '' }
    try { return { value: JSON.parse(text) as unknown, error: '' } }
    catch (reason) { return { value: undefined, error: `Could not parse JSON: ${message(reason)}` } }
  }, [text])
  const matches = useMemo(() => Object.fromEntries(filters.map(item =>
    [item.id, parsed.value === undefined ? [] : findJson(parsed.value, item.pick)])), [parsed])
  const current = parsed.value === undefined ? undefined : filters.find(item => item.id === filter)
  const view = useMemo(() => {
    const toc: { label: string; line: number; count: number }[] = []
    const replacer = (key: string, value: unknown) => cleanDecimals && typeof value === 'number' ? cleanFloat32(value)
      : key === 'attackInfo' ? sortKeys(value) : value
    if (!current) {
      const body = parsed.value === undefined ? text
        : JSON.stringify(parsed.value, replacer, 2)
      return { lines: body.split('\n'), toc }
    }
    const lines = ['['], all = matches[current.id]
    all.forEach((match, index) => {
      const entry = { ...(match.ability ? { ability: match.ability } : {}), path: match.path,
        [current.field]: match.value }
      const body = JSON.stringify(entry, replacer, 2).split('\n').map(line => `  ${line}`)
      if (index < all.length - 1) body[body.length - 1] += ','
      const label = match.ability ?? match.path.replace(/\.attackInfo$/, '').replace(/(^|\.)combat\.animEvents\./, '$1').replaceAll('.', ' › ')
      const previous = toc[toc.length - 1]
      if (previous?.label === label) previous.count++
      else toc.push({ label, line: lines.length, count: 1 })
      for (const line of body) lines.push(line)
    })
    lines.push(']')
    return { lines, toc }
  }, [current, matches, parsed, text, cleanDecimals])
  const gadgetFocus = useMemo(() => {
    if (source.kind !== 'gadget' || current || !references) return null
    const prefix = `  ${JSON.stringify(references.character)}:`
    const line = view.lines.findIndex(value => value.startsWith(prefix))
    return line === -1 ? null : { line }
  }, [source.kind, current, references, view])
  const needle = searching ? query.toLowerCase() : ''
  const hits = useMemo(() => {
    const found: JsonHit[] = []
    if (needle) view.lines.forEach((line, number) => {
      const lower = line.toLowerCase()
      for (let at = lower.indexOf(needle); at !== -1 && found.length < 100000; at = lower.indexOf(needle, at + needle.length)) found.push({ line: number, start: at })
    })
    return found
  }, [needle, view])
  const activeHit = hits.length ? hits[Math.min(hitIndex, hits.length - 1)] : undefined
  const step = (direction: number) => { if (hits.length) setHitIndex((Math.min(hitIndex, hits.length - 1) + direction + hits.length) % hits.length) }
  const openSearch = useCallback(() => { setSearching(true); requestAnimationFrame(() => searchInput.current?.select()) }, [])
  useFindShortcut(true, openSearch)
  const chooseFilter = (value: Filter) => { setCopiedMode(null); setFocus(null); setHitIndex(0); setFilter(value) }
  const chooseFile = (value: string) => {
    if (value === selected) return
    setCopiedMode(null); setFocus(null); setHitIndex(0); setText(''); setError(''); setLoading(true); setSelected(value)
  }
  const copy = async () => {
    setCopiedMode(null); setError('')
    try { await navigator.clipboard.writeText(view.lines.join('\n')); setCopiedMode(cleanDecimals) }
    catch (reason) { setError(`Could not copy: ${message(reason)}`) }
  }
  const selectedFile = references?.files.find(file => file.key === selected)
  return <div className="binoutput-layout">
    <aside className="binoutput-tree" aria-label="BinOutput File Tree">
      <div className="binoutput-tree-title">{related ? `${references?.character ?? 'Relevant Files'}${references ? ` (${references.files.length})` : ''}` : 'BinOutput'}</div>
      <label className="field"><span>Filter by Filename</span>
        <input type="search" value={filename} maxLength={120} onChange={event => setFilename(event.target.value)} />
      </label>
      {term ? nameResults?.error ? <div className="error-box" role="alert">{nameResults.error}</div>
        : !nameResults ? <span className="muted" role="status">{related && error ? 'Could not load filenames.' : 'Searching filenames...'}</span>
        : <>
          {!nameResults.entries.length && <span className="muted" role="status">No matching filenames.</span>}
          {nameResults.entries.map(entry => <button key={entry.key} className={`binoutput-file${selected === entry.key ? ' selected' : ''}`}
            aria-current={selected === entry.key ? 'true' : undefined} onClick={() => chooseFile(entry.key)} title={entry.key}>
            <FileText size={13} /><span>{entry.key}</span>
          </button>)}
          {nameResults.truncated && <span className="muted" role="status">Showing the first 100 matches. Refine the filename to narrow results.</span>}
        </> : (!related || references) && <Directory path="" name="BinOutput" selected={selected} expanded={related} load={load} onSelect={chooseFile} />}
      {references && references.warnings.length > 0 && <details className="binoutput-warnings"><summary>Discovery Notes ({references.warnings.length})</summary>
        <ul>{references.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      </details>}
    </aside>
    <div className="preview-panel binoutput-preview">
      <div className="preview-header"><span title={selectedFile?.reasons.join('\n') ?? selected}>{selected || 'Select a JSON File'}</span><div>
        {text && !loading && <button className="icon-button" onClick={openSearch} aria-label="Search game data" title="Search (Ctrl+F)"><Search size={16} /></button>}
        {text && !loading && <button className="icon-button" onClick={() => { void copy() }} aria-label="Copy game data" title={current ? 'Copy filtered data' : 'Copy'}>{copiedMode === cleanDecimals ? <Check size={16} /> : <Copy size={16} />}</button>}
      </div></div>
      {text && !loading && parsed.value !== undefined && <div className="reference-filters" role="group" aria-label="Filter game data">
        <button className={!current ? 'selected' : ''} aria-pressed={!current} onClick={() => chooseFilter('all')}>Full File</button>
        {filters.map(item => <button key={item.id} className={current?.id === item.id ? 'selected' : ''} aria-pressed={current?.id === item.id}
          title={item.title} onClick={() => chooseFilter(item.id)}>{item.label} <span>{matches[item.id].length}</span></button>)}
      </div>}
      {searching && <SearchBar inputRef={searchInput} label="Search game data" query={query} count={hits.length} index={hitIndex}
        onQuery={value => { setQuery(value); setHitIndex(0) }} onStep={step} onClose={() => setSearching(false)} />}
      {(error || parsed.error) && <div className="error-box" role="alert">{error || parsed.error}</div>}
      {current?.id === 'attackInfo' && view.toc.length > 0 && !loading && <details className="reference-toc" open>
        <summary>Contents <span>{view.toc.length}</span></summary>
        <ol>{view.toc.map(entry => <li key={entry.line}><button onClick={() => setFocus({ line: entry.line })} title={entry.label}>
          {entry.label}{entry.count > 1 && <span>{entry.count}</span>}
        </button></li>)}</ol>
      </details>}
      {loading ? <div className="empty"><LoaderCircle className="spin" />Loading BinOutput...</div> :
        !selected ? <div className="empty"><Braces size={28} /><p>{references?.files.length === 0 ? 'No relevant JSON files found.' : 'Select a JSON file from the tree.'}</p></div> :
          current && !matches[current.id].length ? <div className="empty"><Braces size={28} /><p>No {current.label} in this file.</p></div> :
            text && <JsonView key={`${selected}:${current?.id ?? 'all'}`} lines={view.lines} query={needle} active={activeHit} focus={focus ?? gadgetFocus} highlights={highlights} />}
    </div>
  </div>
}

export function BinOutputViewer({ jobId, onClose, characters: initialCharacters = [] }: {
  jobId?: string; onClose?: () => void; characters?: Character[]
}) {
  const [initial] = useState(() => readViewerLink(jobId))
  const [link, setLink] = useState(initial)
  const [listings] = useState(() => new Map<string, TreeEntry[]>())
  const [mode, setMode] = useState<'all' | 'character' | 'enemy' | 'gadget' | 'job'>(jobId ? 'job' : initial.scope?.kind ?? 'all')
  const linkedId = (kind: typeof publicScopes[number]) => initial.scope?.kind === kind ? String(initial.scope.id) : ''
  const [character, setCharacter] = useState(() => linkedId('character'))
  const [enemy, setEnemy] = useState(() => linkedId('enemy'))
  const [gadget, setGadget] = useState(() => linkedId('gadget'))
  const [characters, setCharacters] = useState(initialCharacters)
  const [enemies, setEnemies] = useState<PickerItem[] | null>(null)
  const [gadgets, setGadgets] = useState<PickerItem[] | null>(null)
  const [error, setError] = useState('')
  const [highlights, setHighlights] = useState(initial.highlights)
  const [cleanDecimals, setCleanDecimals] = useState(initial.cleanDecimals)
  const scopeId = useId()
  const characterMode = mode === 'character' || mode === 'job'
  const scopeValue = mode === 'character' ? character : mode === 'enemy' ? enemy : mode === 'gadget' ? gadget : ''
  const highlightParam = defaultHighlights.filter(id => highlights.includes(id)).join(',')
  useEffect(() => {
    if (jobId) return
    updateToolQuery(toolId, { character_id: mode === 'character' ? scopeValue || undefined : undefined,
      enemy_id: mode === 'enemy' ? scopeValue || undefined : undefined, gadget_id: mode === 'gadget' ? scopeValue || undefined : undefined,
      clean_decimals: cleanDecimals ? undefined : 'false',
      highlights: highlightParam === defaultHighlights.join(',') ? undefined : highlightParam })
  }, [jobId, mode, scopeValue, cleanDecimals, highlightParam])
  const resetFileLink = () => {
    setLink({ ...initial, path: '', name: '', filter: 'all' })
    if (!jobId) updateToolQuery(toolId, { path: undefined, name: undefined, filter: undefined })
  }
  useEffect(() => {
    if (mode === 'all' || characterMode && characters.length || mode === 'enemy' && enemies || mode === 'gadget' && gadgets) return
    const controller = new AbortController()
    if (characterMode) api<Character[]>('/characters', { signal: controller.signal }).then(setCharacters)
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
    else if (mode === 'enemy') api<PickerItem[]>('/enemies', { signal: controller.signal }).then(setEnemies)
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
    else if (mode === 'gadget') api<PickerItem[]>('/gadgets', { signal: controller.signal }).then(setGadgets)
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
    return () => controller.abort()
  }, [mode, characterMode, characters.length, enemies, gadgets])
  const characterOptions = useMemo(() => [
    ...(jobId ? [{ value: 'job', label: 'Job Character' }] : []),
    ...characters.map(item => ({ value: String(item.id),
      label: `${item.name}${item.id === 10000005 ? ' (Aether)' : item.id === 10000007 ? ' (Lumine)' : ''} · ${item.id}` })),
  ], [characters, jobId])
  const enemyOptions = useMemo(() => enemies?.map(item => ({ value: String(item.id),
    label: `${item.name} · ${item.id}${item.internal ? ` · ${item.internal}` : ''}` })) ?? null, [enemies])
  const gadgetOptions = useMemo(() => gadgets?.map(item => ({ value: String(item.id),
    label: `${item.name} · ${item.id}${item.internal ? ` · ${item.internal}` : ''}` })) ?? null, [gadgets])
  let source: Source | null = null
  if (mode === 'all') source = { kind: 'all' }
  if (mode === 'job' && jobId) source = { kind: 'job', id: jobId }
  if (mode === 'character' && character) source = { kind: 'character', id: Number(character) }
  if (mode === 'enemy' && enemy) source = { kind: 'enemy', id: Number(enemy) }
  if (mode === 'gadget' && gadget) source = { kind: 'gadget', id: Number(gadget) }
  return <section className={`binoutput-panel${jobId ? ' reference-panel' : ' binoutput-tool'}`} aria-label="BinOutput Viewer">
    <div className="binoutput-toolbar">
      <div className="binoutput-scope" role="radiogroup" aria-label="Filter By"><span>Filter By</span>
        {(['all', 'character', 'enemy', 'gadget'] as const).map(value => <label key={value}>
          <input type="radio" name={`${scopeId}-scope`} value={value}
            checked={value === 'character' ? characterMode : mode === value} onChange={() => {
              resetFileLink(); setError(''); setMode(value === 'character' && jobId && !character ? 'job' : value)
            }} />{value === 'all' ? 'None' : value === 'character' ? 'Character' : value === 'enemy' ? 'Enemy' : 'Gadget'}
        </label>)}
      </div>
      {characterMode && <FilterPicker label="Character" value={mode === 'job' ? 'job' : character}
        options={characterOptions} onChange={value => {
        if (value === 'job') setMode('job')
        else if (value !== character || mode !== 'character') { resetFileLink(); setCharacter(value); setMode('character') }
      }} />}
      {mode === 'enemy' && <FilterPicker label="Enemy" value={enemy} options={enemyOptions} onChange={value => {
        if (value !== enemy) { resetFileLink(); setEnemy(value) }
      }} />}
      {mode === 'gadget' && <FilterPicker label="Gadget" value={gadget} options={gadgetOptions} onChange={value => {
        if (value !== gadget) { resetFileLink(); setGadget(value) }
      }} />}
      <label title="Remove float32 extraction noise from displayed and copied numbers without changing the source files.">
        <input type="checkbox" checked={cleanDecimals} onChange={event => setCleanDecimals(event.target.checked)} />Clean Decimals
      </label>
      <details className="binoutput-highlights"><summary>Row Highlights ({highlights.length}/{JSON_HIGHLIGHTS.length})</summary>
        <div role="group" aria-label="Row Highlights">
          <div className="binoutput-highlight-actions"><button onClick={() => setHighlights(JSON_HIGHLIGHTS.map(rule => rule.id))}>All</button><button onClick={() => setHighlights([])}>None</button></div>
          {JSON_HIGHLIGHTS.map(rule => <label key={rule.id}><input type="checkbox" checked={highlights.includes(rule.id)}
            onChange={event => setHighlights(current => event.target.checked ? [...current, rule.id] : current.filter(id => id !== rule.id))} />{rule.label}</label>)}
        </div>
      </details>
      {onClose && <button className="icon-button" onClick={onClose} aria-label="Hide game data" title="Hide game data"><X size={16} /></button>}
    </div>
    {error && <div className="error-box" role="alert">{error}</div>}
    {source ? <Browser key={JSON.stringify(source)} source={source} highlights={highlights} cleanDecimals={cleanDecimals}
      link={jobId ? undefined : link} listings={listings} /> :
      <div className="empty"><Braces size={28} /><p>Select {mode === 'enemy' ? 'an' : 'a'} {mode} to find its BinOutput files.</p></div>}
  </section>
}
