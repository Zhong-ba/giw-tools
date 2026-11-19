import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import type { FormEvent, KeyboardEvent, ReactNode } from 'react'
import {
  ArrowDownToLine, ArrowRight, BookOpen, Bot, Braces, ChartColumn, Check, ChevronRight, ChevronsUp, CircleAlert, Clock3, CookingPot, Copy, Crosshair, Database,
    FileText, Fish, FolderOpen, Image as ImageIcon, KeyRound, LayoutGrid, Link2, ListPlus, LoaderCircle, Maximize2, Minimize2, Pencil, Play,
    RotateCcw, Save, Scale, Search, Send, Square, Terminal, Trash2, X,
} from 'lucide-react'
  import { AbyssSpiral, Guoba, CloudRetainer, Hilichurl, StygianBloom, TheaterBook } from './icons'
import type { Artifact, BotSettings, BotState, Character, Dataset, Job, Parameters, Period, PickerItem, PreparedDatasets, Property, QueueEntry, QueueItem, Revision, ServerConfig, Tool, Versions } from './api'
import { api, datasetChoice, downloadArchive, hosted, message, saveBlob, serverConfig, setDatasetChoice, useAssetUrl } from './api'
import type { StorageInfo } from './local'
import { highlightWikitext } from './wikitext'
import { highlightLua } from './lua'
import { boostParty, startParty, stopParty } from './party'
import { findMatches, markMatches, useFindShortcut } from './search'
import { SearchBar } from './SearchBar'
import { OtherLanguages } from './OtherLanguages'
import { BinOutputViewer } from './BinOutputViewer'
import { AI_RESULT, EnemyAITable } from './EnemyAITable'

const icons: Record<string, typeof BookOpen> = { 'other-languages': CloudRetainer, 'binoutput-viewer': Braces, 'character-kit': Guoba, 'attribute-scaling': ChartColumn, 'character-data': ChevronsUp, 'particle-audit': ChartColumn, redirects: Link2, enemy: Hilichurl,
  bounties: Crosshair, 'fishing-point': Fish, 'fish-weights': Scale, 'manual-cooking': CookingPot, 'spiral-abyss': AbyssSpiral, 'imaginarium-theater': TheaterBook, 'stygian-onslaught': StygianBloom }
const picksCharacter = (tool: Tool | null) => !!tool && 'character_id' in tool.schema.properties
const advanced = new Set(['natlan', 'nodkrai', 'hexerei', 'stellar', 'traveler', 'skill_depot'])
const passiveTypes = ['natlan', 'nodkrai', 'hexerei', 'stellar']
const levelFields = ['normal_attack', 'elemental_skill', 'elemental_burst']
const active = (job: Job) => job.status === 'queued' || job.status === 'running'
const size = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
const time = (date: string) => new Date(date).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
// Apply carriage returns like a terminal so redrawn progress bars show only their latest state.
const terminal = (text: string) => text.replace(/\r\n/g, '\n').split('\n')
  .map(line => line.split('\r').filter(Boolean).pop() ?? '').join('\n')
const isWikitext = (path: string) => path.toLowerCase().endsWith('.wikitext')
const isLua = (path: string) => path.toLowerCase().endsWith('.lua')
const FULLSCREEN_KEY = 'wiki-tools.fullscreen'
const preferFullscreen = () => { try { return localStorage.getItem(FULLSCREEN_KEY) === '1' } catch { return false } }
const rememberFullscreen = (value: boolean) => { try { localStorage.setItem(FULLSCREEN_KEY, value ? '1' : '0') } catch { /* storage unavailable */ } }
const urlExcludedFields = new Set(['lines', 'text'])
const propertyType = (property: Property) => property.type ?? property.anyOf?.find(item => item.type !== 'null')?.type
const propertyDefault = (property: Property): Parameters[string] =>
  property.default ?? (propertyType(property) === 'array' ? [] : '')

function readToolUrl(tool: Tool, search: string) {
  const values = Object.fromEntries(Object.entries(tool.schema.properties)
    .map(([key, property]) => [key, propertyDefault(property)])) as Parameters
  const invalid: string[] = []
  const provided: string[] = []
  const params = new URLSearchParams(search)
  for (const [key, property] of Object.entries(tool.schema.properties)) {
    if (urlExcludedFields.has(key)) {
      if (params.has(key)) invalid.push(key)
      continue
    }
    const raw = params.getAll(key)
    if (!raw.length) continue
    const type = propertyType(property)
    let value: Parameters[string]
    if (type === 'array') {
      if (raw.length === 1 && raw[0] === '') value = []
      else if (property.items?.type === 'integer' || property.items?.type === 'number') {
        const numbers = raw.map(item => Number(item))
        if (raw.some(item => item.trim() === '') || numbers.some(item => !Number.isFinite(item) ||
            (property.items?.type === 'integer' && !Number.isInteger(item)))) {
          invalid.push(key)
          continue
        }
        value = numbers
      } else value = raw
    } else {
      if (raw.length !== 1) {
        invalid.push(key)
        continue
      }
      const item = raw[0]
      if (item === '') value = ''
      else if (type === 'boolean' && (item === 'true' || item === 'false')) value = item === 'true'
      else if (type === 'boolean') {
        invalid.push(key)
        continue
      } else if (type === 'integer' || type === 'number') {
        const number = Number(item)
        if (!Number.isFinite(number) || (type === 'integer' && !Number.isInteger(number))) {
          invalid.push(key)
          continue
        }
        value = number
      } else value = item
    }
    if ((typeof value === 'string' && (value.length > (property.maxLength ?? Infinity) ||
        (property.enum && !property.enum.includes(value)))) ||
        (typeof value === 'number' && ((property.minimum !== undefined && value < property.minimum) ||
          (property.maximum !== undefined && value > property.maximum)))) {
      invalid.push(key)
      continue
    }
    values[key] = value
    provided.push(key)
  }
  return { values, invalid, provided }
}

function writeToolUrl(tool: Tool, values: Parameters, touched: Set<string>) {
  const url = new URL(window.location.href)
  for (const [key, property] of Object.entries(tool.schema.properties)) {
    url.searchParams.delete(key)
    if (urlExcludedFields.has(key)) continue
    const value = values[key]
    if (JSON.stringify(value) === JSON.stringify(propertyDefault(property))) {
      if (!touched.has(key)) continue
    }
    if (Array.isArray(value)) {
      if (!value.length) url.searchParams.append(key, '')
      else value.forEach(item => url.searchParams.append(key, String(item)))
    } else if (value === '' || value === null) url.searchParams.set(key, '')
    else url.searchParams.set(key, String(value))
  }
  const next = `${url.pathname}${url.search}${url.hash}`
  if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== next) {
    window.history.replaceState(window.history.state, '', next)
  }
}

function Status({ status }: { status: Job['status'] }) {
  return <span className={`status ${status}`}>
    {status === 'running' ? <LoaderCircle size={12} className="spin" /> : <span className="status-dot" />}
    {status === 'succeeded' ? 'Completed' : status.charAt(0).toUpperCase() + status.slice(1)}
  </span>
}

function ToolText({ text, className }: { text: string; className: string }) {
  const fimsh = text.replace(/fish/gi, match =>
    match.slice(0, 2) + (match === match.toUpperCase() ? 'M' : 'm') + match.slice(2))
  if (fimsh === text) return <span className={className}>{text}</span>
  return <span className={`${className} tool-text-swap`}>
    <span className="tool-text-original">{text}</span>
    <span className="tool-text-fimsh" aria-hidden="true">{fimsh}</span>
  </span>
}

function Dialog({ title, subtitle, extra, children, onClose, wide = false, expandable = true }: {
  title: string; subtitle?: string; extra?: ReactNode; children: ReactNode; onClose: () => void; wide?: boolean; expandable?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [full, setFull] = useState(() => expandable && preferFullscreen())
  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])
  const toggleFull = () => {
    const dialog = ref.current
    if (!dialog) return
    const before = dialog.getBoundingClientRect()
    const radius = getComputedStyle(dialog).borderRadius
    const next = !full
    rememberFullscreen(next)
    flushSync(() => setFull(next))
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const after = dialog.getBoundingClientRect()
    // Animate between the measured sizes; the modal stays centred because its margins are auto.
    dialog.animate([
      { width: `${before.width}px`, height: `${before.height}px`, borderRadius: radius, maxWidth: 'none', maxHeight: 'none', overflow: 'hidden' },
      { width: `${after.width}px`, height: `${after.height}px`, borderRadius: getComputedStyle(dialog).borderRadius, maxWidth: 'none', maxHeight: 'none', overflow: 'hidden' },
    ], { duration: 240, easing: 'cubic-bezier(.2, .8, .2, 1)' })
  }
  return <dialog ref={ref} className={['dialog', wide && 'wide', full && 'fullscreen'].filter(Boolean).join(' ')}
    onCancel={event => { event.preventDefault(); onClose() }}
    onClick={event => {
      if (event.target !== event.currentTarget) return
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX >= bounds.right || event.clientY < bounds.top || event.clientY >= bounds.bottom) onClose()
    }}
    onDoubleClick={event => {
      if (!expandable || !(event.target instanceof Element) ||
          event.target.closest('button, a, input, select, textarea, label, summary, [role="button"], [contenteditable]')) return
      const selection = window.getSelection()
      // Double-clicking padding can select a nearby word even though the pointer is outside it.
      const selectingText = selection?.rangeCount && selection.toString().trim() &&
        Array.from(selection.getRangeAt(0).getClientRects()).some(bounds =>
          event.clientX >= bounds.left && event.clientX < bounds.right && event.clientY >= bounds.top && event.clientY < bounds.bottom)
      if (event.target.closest('.dialog-header') || !selectingText) {
        selection?.removeAllRanges()
        toggleFull()
      }
    }} aria-label={title}>
    <header className="dialog-header"
      onMouseDown={event => { if (expandable && event.detail > 1) event.preventDefault() }}>
      <div className="dialog-title"><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
      {extra && <div className="dialog-extra">{extra}</div>}
      <div className="dialog-actions">
        {expandable && <button className="icon-button" onClick={toggleFull} aria-label={full ? 'Exit full screen' : 'Full screen'} title={full ? 'Exit full screen (or double-click empty space)' : 'Full screen (or double-click empty space)'}>
          {full ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
        </button>}
        <button className="icon-button" onClick={onClose} aria-label="Close dialog" title="Close"><X size={20} /></button>
      </div>
    </header>
    {children}
  </dialog>
}

function WikitextEditor({ value, onChange, onSave }: { value: string; onChange: (value: string) => void; onSave: () => void }) {
  const layer = useRef<HTMLPreElement>(null)
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); onSave() }
  }
  return <div className="code-editor">
    {/* The trailing newline keeps the highlight layer as tall as the textarea when the text ends in one. */}
    <pre ref={layer} className="code-layer" aria-hidden="true">{highlightWikitext(value)}{'\n'}</pre>
    <textarea aria-label="Edit file" value={value} spellCheck={false} autoFocus onKeyDown={keyDown}
      onChange={event => onChange(event.target.value)}
      onScroll={event => { if (layer.current) { layer.current.scrollTop = event.currentTarget.scrollTop; layer.current.scrollLeft = event.currentTarget.scrollLeft } }} />
  </div>
}

interface PickerConfig {
  list: string; table: string; plural: string; label: string; search: string
  compare: boolean; selectAll?: boolean; newNames?: boolean
}
// Multi-select fields backed by a list endpoint that can be narrowed to the rows added between two versions.
const pickers: Record<string, PickerConfig> = {
  enemy_ids: { list: '/enemies', table: 'MonsterExcelConfigData', plural: 'enemies', label: 'Enemies',
    search: 'Search by name, ID or internal name...', compare: true, newNames: true },
  pool_ids: { list: '/fishing-point', table: 'FishPoolExcelConfigData', plural: 'fishing points', label: 'Fishing Points',
    search: 'Search by name, ID or region...', compare: true },
  bounty_ids: { list: '/bounties', table: 'HuntingV2MonsterBundleExcelConfigData', plural: 'bounties', label: 'Bounties',
    search: 'Search by enemy, ID or region...', compare: false, selectAll: true },
}
const pickerKey = (tool: Tool) => Object.keys(pickers).find(key => key in tool.schema.properties)
const enemyAIPicker = { ...pickers.enemy_ids, compare: false, newNames: false }

/** A checklist of the dataset's dated periods (newest first, which starts selected), like the enemy picker. */
function PeriodPicker({ label, kind, value, preserveSelection, onChange }: {
  label: string; kind: string; value: string[]; preserveSelection: boolean; onChange: (value: string[]) => void
}) {
  const [periods, setPeriods] = useState<Period[] | null>(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const initialSelection = useRef(preserveSelection || value.length > 0)
  const onChangeRef = useRef(onChange)
  useEffect(() => { onChangeRef.current = onChange })
  useEffect(() => {
    const controller = new AbortController()
    api<Period[]>(`/periods/${kind}`, { signal: controller.signal })
      .then(result => {
        setPeriods(result)
        if (initialSelection.current) initialSelection.current = false
        else onChangeRef.current(result.length ? [result[0].value] : [])
      })
      .catch(reason => { if (!controller.signal.aborted) { setError(message(reason)); setPeriods([]) } })
    return () => controller.abort()
  }, [kind])
  const plural = label.toLowerCase()
  const selected = new Set(value)
  const term = search.trim().toLowerCase()
  const shown = (periods ?? []).filter(period => !term || `${period.label} ${period.name ?? ''}`.toLowerCase().includes(term))
  const toggle = (id: string, on: boolean) => onChange(on ? [...value, id] : value.filter(item => item !== id))
  return <div className="item-picker">
    <input aria-label={`Filter ${plural}`} placeholder="Search by date or name..." value={search}
      onChange={event => setSearch(event.target.value)} />
    <div className="picker-toolbar">
      <span>{periods ? `${value.length} of ${periods.length} selected` : `Loading ${plural}...`}</span>
      <button type="button" className="button secondary" disabled={!shown.length}
        onClick={() => onChange([...new Set([...value, ...shown.map(period => period.value)])])}>Select Shown</button>
      <button type="button" className="button secondary" disabled={!value.length} onClick={() => onChange([])}>Clear</button>
    </div>
    <div className="picker-list" role="group" aria-label={label}>
      {periods && !shown.length && <div className="empty-note">{periods.length ? `No ${plural} match the search.` : `No ${plural} found.`}</div>}
      {shown.map(period => <label className="check-field" key={period.value}>
        <input type="checkbox" checked={selected.has(period.value)} onChange={event => toggle(period.value, event.target.checked)} />
        <span><strong>{period.name ?? period.label}</strong>
          <small>{[period.name && period.label, period.value === periods?.[0]?.value && 'Latest'].filter(Boolean).join(' · ')}</small></span>
      </label>)}
    </div>
    {!value.length && periods && periods.length > 0 && <small>None selected: the newest one is generated.</small>}
    {error && <small className="field-error" role="alert">{error}</small>}
  </div>
}

function ItemPicker({ config, value, preserveSelection, onChange, onVersion }: {
  config: PickerConfig; value: number[]; preserveSelection: boolean
  onChange: (value: number[]) => void; onVersion: (version: string) => void
}) {
  const [versions, setVersions] = useState<Versions | null>(null)
  const [compare, setCompare] = useState(config.compare && !preserveSelection && value.length === 0)
  const [older, setOlder] = useState('')
  const [newer, setNewer] = useState('current')
  const [newNamesOnly, setNewNamesOnly] = useState(true)
  const [items, setItems] = useState<PickerItem[] | null>(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const initialSelection = useRef(preserveSelection || value.length > 0)
  useEffect(() => {
    const controller = new AbortController()
    api<Versions>(`/versions?${new URLSearchParams({ table: config.table })}`, { signal: controller.signal })
      .then(result => { setVersions(result); setOlder(result.older ?? ''); setNewer(result.newer); if (!result.older) setCompare(false) })
      .catch(reason => { if (!controller.signal.aborted) { setError(message(reason)); setCompare(false); setVersions({ options: [], older: null, newer: 'current' }) } })
    return () => controller.abort()
  }, [config])
  const comparing = compare && !!older
  const onChangeRef = useRef(onChange)
  const onVersionRef = useRef(onVersion)
  useEffect(() => { onChangeRef.current = onChange; onVersionRef.current = onVersion })
  useEffect(() => {
    if (!versions) return
    const controller = new AbortController()
    const parameters: Record<string, string> = comparing ? { older, newer } : {}
    if (comparing && config.newNames) parameters.new_names_only = String(newNamesOnly)
    const query = comparing ? `?${new URLSearchParams(parameters)}` : ''
    const start = setTimeout(() => { setItems(null); setError('') }, 0)
    api<PickerItem[]>(`${config.list}${query}`, { signal: controller.signal })
      .then(result => {
        setItems(result)
        // A version comparison selects everything it finds; the full list starts empty unless the tool prefers all.
        if (initialSelection.current) initialSelection.current = false
        else onChangeRef.current(comparing || config.selectAll ? result.map(item => item.id) : [])
      })
      .catch(reason => { if (!controller.signal.aborted) { setError(message(reason)); setItems([]) } })
    return () => { clearTimeout(start); controller.abort() }
  }, [config, versions, comparing, older, newer, newNamesOnly])
  useEffect(() => {
    const version = comparing ? versions?.options.find(option => option.value === newer)?.version : null
    if (version) onVersionRef.current(version)
  }, [versions, comparing, newer])
  const selected = new Set(value)
  const term = search.trim().toLowerCase()
  const shown = (items ?? []).filter(item => !term || `${item.name} ${item.id} ${item.internal}`.toLowerCase().includes(term))
  const toggle = (id: number, on: boolean) => onChange(on ? [...value, id] : value.filter(item => item !== id))
  const versionSelect = (id: string, label: string, current: string, set: (value: string) => void) => <div className="field">
    <label htmlFor={id}>{label}</label>
    <select id={id} value={current} onChange={event => set(event.target.value)}>
      {versions?.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </div>
  return <div className="item-picker">
    <label className="check-field">
      <input type="checkbox" checked={comparing} disabled={!versions?.older && !older}
        onChange={event => setCompare(event.target.checked)} />
      <span><strong>Compare Versions</strong><small>{versions && !versions.older && !older
        ? 'No older version is available to compare with.' : `Only list ${config.plural} added between two versions.`}</small></span>
    </label>
    {comparing && <>
      <div className="field-row">
        {versionSelect('picker-older', 'Older Version', older, setOlder)}
        {versionSelect('picker-newer', 'Newer Version', newer, setNewer)}
      </div>
      {config.newNames && <label className="check-field">
        <input type="checkbox" checked={newNamesOnly} onChange={event => setNewNamesOnly(event.target.checked)} />
        <span><strong>Only New Enemy Names</strong><small>Hides new IDs of enemies that already existed (variants, event
          copies) and repeat IDs of the same new enemy, so existing wiki pages are not overwritten.</small></span>
      </label>}
    </>}
    <input aria-label={`Filter ${config.plural}`} placeholder={config.search} value={search}
      onChange={event => setSearch(event.target.value)} />
    <div className="picker-toolbar">
      <span>{items ? `${value.length} of ${items.length} selected` : comparing ? 'Comparing versions (the first time can take a few seconds)...' : `Loading ${config.plural}...`}</span>
      <button type="button" className="button secondary" disabled={!shown.length}
        onClick={() => onChange([...new Set([...value, ...shown.map(item => item.id)])])}>Select Shown</button>
      <button type="button" className="button secondary" disabled={!value.length} onClick={() => onChange([])}>Clear</button>
    </div>
    <div className="picker-list" role="group" aria-label={config.label}>
      {items && !shown.length && <div className="empty-note">{items.length ? `No ${config.plural} match the search.` : `No ${config.plural} found.`}</div>}
      {shown.map(item => <label className="check-field" key={item.id}>
        <input type="checkbox" checked={selected.has(item.id)} onChange={event => toggle(item.id, event.target.checked)} />
        <span><strong>{item.name}</strong><small>{item.id}{item.internal && ` · ${item.internal}`}</small></span>
      </label>)}
    </div>
    {error && <small className="field-error" role="alert">{error}</small>}
  </div>
}

function ToolForm({ tool, characters, characterError, submitting, error, onSubmit, onClose }: {
  tool: Tool; characters: Character[]; characterError: string; submitting: boolean; error: string
  onSubmit: (parameters: Parameters) => void; onClose: () => void
}) {
  const [urlState] = useState(() => readToolUrl(tool, window.location.search))
  const [values, setValues] = useState<Parameters>(() => urlState.values)
  const overrides = useRef(new Set(urlState.provided))
  const urlWarning = urlState.invalid.length
    ? `Ignored invalid or non-shareable URL value(s) for: ${urlState.invalid.join(', ')}.` : ''
  const [characterSearch, setCharacterSearch] = useState('')
  const [versionNote, setVersionNote] = useState('')
  const autoVersion = useRef('')
  const characterId = values.character_id
  const fillsVersion = 'version' in tool.schema.properties && 'character_id' in tool.schema.properties
  useEffect(() => { writeToolUrl(tool, values, overrides.current) }, [tool, values])
  useEffect(() => {
    if (!fillsVersion || typeof characterId !== 'number') return
    const controller = new AbortController()
    const name = characters.find(item => item.id === characterId)?.name ?? 'this character'
    const start = setTimeout(() => setVersionNote(`Looking up ${name} on the wiki...`), 0)
    api<{ character: string; version: string | null }>(`/characters/${characterId}/version`, { signal: controller.signal })
      .then(result => {
        if (!result.version) { setVersionNote(`No Change History found for ${result.character} on the wiki.`); return }
        setValues(previous => {
          if (overrides.current.has('version') || previous.version !== '' && previous.version !== autoVersion.current) return previous
          autoVersion.current = result.version ?? ''
          return { ...previous, version: result.version ?? '' }
        })
        setVersionNote(`Wiki Change History lists ${result.character} as ${result.version}.`)
      })
      .catch(reason => { if (!controller.signal.aborted) setVersionNote(`Could not check the wiki: ${message(reason)}`) })
    return () => { clearTimeout(start); controller.abort() }
  }, [fillsVersion, characterId, characters])
  const [advancedOpen, setAdvancedOpen] = useState(() => urlState.provided.some(key => advanced.has(key)))
  const [passiveNote, setPassiveNote] = useState('')
  const detectsPassives = passiveTypes.every(key => key in tool.schema.properties) && 'character_id' in tool.schema.properties
  useEffect(() => {
    if (!detectsPassives || typeof characterId !== 'number') return
    const controller = new AbortController()
    api<{ types: string[] }>(`/characters/${characterId}/passives`, { signal: controller.signal })
      .then(({ types }) => {
        if (controller.signal.aborted) return
        setValues(previous => ({ ...previous, ...Object.fromEntries(passiveTypes
          .filter(key => !overrides.current.has(key)).map(key => [key, types.includes(key)])) }))
        const titles = types.map(key => tool.schema.properties[key]?.title ?? key)
        setPassiveNote(titles.length ? `Detected ${titles.join(', ')} passive.` : '')
        if (types.length) setAdvancedOpen(true)
      })
      .catch(() => { if (!controller.signal.aborted) setPassiveNote('') })
    return () => controller.abort()
  }, [detectsPassives, characterId, tool])
  const update = (key: string, value: Parameters[string]) => {
    overrides.current.add(key)
    setValues(previous => ({ ...previous, [key]: value }))
  }
  // Fills the version unless the user typed their own.
  const autofillVersion = useCallback((version: string) => setValues(previous => {
    if (overrides.current.has('version') || previous.version !== '' && previous.version !== autoVersion.current) return previous
    autoVersion.current = version
    return { ...previous, version }
  }), [])
  // Tools that pick dated periods fill the version from the wiki's Date to Version for a single period; with several,
  // the field stays empty so each page gets its own.
  const periodKey = 'version' in tool.schema.properties
    ? Object.keys(tool.schema.properties).find(key => tool.schema.properties[key].periods) : undefined
  const periodDates = periodKey && Array.isArray(values[periodKey]) ? values[periodKey].map(String).join(',') : null
  useEffect(() => {
    if (periodDates === null) return
    const dates = periodDates ? periodDates.split(',') : []
    if (dates.length !== 1) {
      const start = setTimeout(() => {
        autofillVersion('')
        setVersionNote(dates.length > 1 ? 'Leave empty to give each page the version live at its start (wiki Date to Version).' : '')
      }, 0)
      return () => clearTimeout(start)
    }
    const controller = new AbortController()
    const start = setTimeout(() => setVersionNote('Looking up the version on the wiki...'), 0)
    api<Record<string, string>>(`/date-versions?${new URLSearchParams({ dates: dates[0] })}`, { signal: controller.signal })
      .then(result => {
        const version = result[dates[0]]
        if (version) autofillVersion(version)
        setVersionNote(version ? `Wiki Date to Version gives ${version} for ${dates[0]}.` : `The wiki has no version for ${dates[0]}.`)
      })
      .catch(reason => { if (!controller.signal.aborted) setVersionNote(`Could not check the wiki: ${message(reason)}`) })
    return () => { clearTimeout(start); controller.abort() }
  }, [periodDates, autofillVersion])
  const field = (key: string, property: Property) => {
    const type = propertyType(property)
    const required = tool.schema.required?.includes(key)
    if (type === 'boolean') return <label className="check-field" key={key}>
      <input type="checkbox" checked={values[key] === true} onChange={event => update(key, event.target.checked)} />
      <span><strong>{property.title}</strong>{property.description && <small>{property.description}</small>}</span>
    </label>
    return <div className="field" key={key}>
      <label htmlFor={key}>{property.title}{required && <span className="required"> *</span>}</label>
      {key === 'character_id' ? <>
        <input aria-label="Filter characters" placeholder="Search by name or ID..." value={characterSearch}
          onChange={event => setCharacterSearch(event.target.value)} />
        <select id={key} required value={String(values[key] ?? '')} onChange={event => update(key, Number(event.target.value) || '')}>
          <option value="">{characters.length ? 'Select a character' : 'Loading characters...'}</option>
          {characters.filter(item => item.id === values[key] || `${item.name} ${item.id}`.toLowerCase().includes(characterSearch.toLowerCase()))
            .map(item => <option key={item.id} value={item.id}>{item.name} ({item.id})</option>)}
        </select>
        {characterError && <small className="field-error" role="alert">{characterError}</small>}
      </>       : pickers[key] ? <ItemPicker config={tool.id === 'enemy-ai' && key === 'enemy_ids' ? enemyAIPicker : pickers[key]}
        value={Array.isArray(values[key]) ? values[key].map(Number) : []}
        preserveSelection={urlState.provided.includes(key)}
        onChange={value => update(key, value)} onVersion={autofillVersion} />
      : property.periods ? <PeriodPicker label={property.title} kind={property.periods}
        value={Array.isArray(values[key]) ? values[key].map(String) : []}
        preserveSelection={urlState.provided.includes(key)} onChange={value => update(key, value)} />
      : property.enum ? <select id={key} required={required} value={String(values[key] ?? '')}
        onChange={event => update(key, event.target.value)}>
        {property.enum.map(option => <option key={option} value={option}>{option}</option>)}
      </select> : (key === 'lines' || key === 'text') ? <textarea id={key} required={required} rows={key === 'lines' ? 7 : 3}
        maxLength={property.maxLength} value={String(values[key] ?? '')}
        placeholder={key === 'lines' ? 'Alternate name%%%Target page\nAnother name%%%Target page' : 'e.g. Amber'}
        onChange={event => update(key, event.target.value)} /> : <input
        id={key} type={type === 'integer' ? 'number' : 'text'} required={required} min={property.minimum} max={property.maximum}
        maxLength={property.maxLength} value={String(values[key] ?? '')} placeholder={key === 'version' ? 'e.g. 7.2' : 'Optional'}
        onChange={event => update(key, type === 'integer' && event.target.value !== '' ? Number(event.target.value) : event.target.value)} />}
      {property.description && <small>{property.description}</small>}
      {key === 'version' && versionNote && <small className="version-note">{versionNote}</small>}
    </div>
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit(Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== '' || tool.schema.required?.includes(key))))
  }
  const fields = Object.entries(tool.schema.properties)
  const picked = pickerKey(tool)
  const render = (list: [string, Property][]) => list.flatMap(([key, property]) => !levelFields.includes(key) ? [field(key, property)]
    : key !== levelFields[0] ? [] : [<fieldset className="field-row" key="levels"><legend>Max Talent Levels</legend>
      {list.filter(([name]) => levelFields.includes(name)).map(([name, item]) => field(name, item))}
    </fieldset>])
  // A tool without settings gets a compact prompt: no empty body and nothing to maximize.
  return <Dialog title={tool.name} subtitle={tool.description} onClose={onClose} expandable={fields.length > 0}>
    <form onSubmit={submit}>
      {(fields.length > 0 || error || urlWarning) && <div className="dialog-body form-fields">
        {render(fields.filter(([key]) => !advanced.has(key)))}
        {fields.some(([key]) => advanced.has(key)) && <details className="advanced" open={advancedOpen}
          onToggle={event => setAdvancedOpen(event.currentTarget.open)}>
          <summary>Advanced Options</summary>
          {passiveNote && <small className="version-note">{passiveNote}</small>}
          <div className="form-fields">{render(fields.filter(([key]) => advanced.has(key)))}</div>
        </details>}
        {urlWarning && <div className="error-box" role="alert"><CircleAlert size={18} />{urlWarning}</div>}
        {error && <div className="error-box" role="alert"><CircleAlert size={18} />{error}</div>}
      </div>}
      <footer className="dialog-footer"><button type="button" className="button secondary" onClick={onClose}>Cancel</button>
        <button className="button primary" disabled={submitting || (picksCharacter(tool) && characters.length === 0)
          || (!!picked && !(Array.isArray(values[picked]) && values[picked].length))}>
          {submitting ? <LoaderCircle size={16} className="spin" /> : <Play size={15} />} Run
        </button>
      </footer>
    </form>
  </Dialog>
}

function FilePreview({ jobId, file, editable, shortcut, onDirty }: {
  jobId: string; file: Artifact; editable: boolean; shortcut: boolean; onDirty: (dirty: boolean) => void
}) {
  const [text, setText] = useState('')
  const [draft, setDraft] = useState<string | null>(null)
  const [loading, setLoading] = useState(file.kind === 'text')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const { path, kind } = file
  const wikitext = isWikitext(path)
  const [saves, setSaves] = useState(0)
  const url = useAssetUrl('file', jobId, path, saves)
  useEffect(() => {
    if (kind !== 'text') return
    const controller = new AbortController()
    api<{ text: string }>(`/jobs/${jobId}/preview/${encodeURIComponent(path)}`, { signal: controller.signal })
      .then(result => setText(result.text))
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [jobId, path, kind])
  const edit = (value: string | null) => { setDraft(value); onDirty(value !== null && value !== text) }
  const copy = async () => {
    try { await navigator.clipboard.writeText(draft ?? text); setCopied(true) }
    catch (reason) { setError(`Could not copy: ${message(reason)}`) }
  }
  const save = async () => {
    if (draft === null || saving) return
    setSaving(true); setError('')
    try {
      await api<Job>(`/jobs/${jobId}/files/${path.split('/').map(encodeURIComponent).join('/')}`, { method: 'PUT', body: JSON.stringify({ text: draft }) })
      setText(draft); edit(null); setSaves(count => count + 1)
    } catch (reason) { setError(message(reason)) }
    finally { setSaving(false) }
  }
  const cancel = () => { if (draft === text || window.confirm('Discard unsaved changes?')) edit(null) }
  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState('')
  const [hitIndex, setHitIndex] = useState(0)
  const searchInput = useRef<HTMLInputElement>(null)
  const preview = useRef<HTMLPreElement>(null)
  const searchable = kind === 'text' && !loading && draft === null && !!text
  const needle = searching && searchable ? query.toLowerCase() : ''
  const hits = useMemo(() => findMatches(text, needle), [text, needle])
  const activeHit = hits.length ? hits[Math.min(hitIndex, hits.length - 1)] : undefined
  const step = (direction: number) => { if (hits.length) setHitIndex((Math.min(hitIndex, hits.length - 1) + direction + hits.length) % hits.length) }
  const openSearch = useCallback(() => { setSearching(true); requestAnimationFrame(() => searchInput.current?.select()) }, [])
  useFindShortcut(shortcut && searchable, openSearch)
  const highlighted = useMemo(() => wikitext ? highlightWikitext(text) : isLua(path) ? highlightLua(text) : [text], [text, wikitext, path])
  useEffect(() => {
    preview.current?.querySelector('mark.active')?.scrollIntoView({ block: 'center', inline: 'nearest' })
  }, [activeHit, needle])
  return <div className="preview-panel">
    <div className="preview-header"><span title={path}>{path.split('/').pop()}{draft !== null && draft !== text && <em> · Unsaved</em>}</span><div>
      {draft !== null ? <>
        <button className="button secondary small" onClick={cancel} disabled={saving}>Cancel</button>
        <button className="button primary small" onClick={() => { void save() }} disabled={saving || draft === text} title="Save (Ctrl+S)">
          {saving ? <LoaderCircle size={14} className="spin" /> : <Save size={14} />} Save
        </button>
      </> : <>
        {editable && wikitext && !loading && !error && <button className="icon-button" onClick={() => edit(text)} aria-label="Edit file" title="Edit"><Pencil size={16} /></button>}
        {searchable && <button className="icon-button" onClick={openSearch} aria-label="Search file" title="Search (Ctrl+F)"><Search size={16} /></button>}
        {kind === 'text' && text && <button className="icon-button" onClick={() => { void copy() }} aria-label="Copy output" title="Copy">{copied ? <Check size={16} /> : <Copy size={16} />}</button>}
        {url && <a className="icon-button" href={url} download={path.split('/').pop()} aria-label="Download file" title="Download"><ArrowDownToLine size={17} /></a>}
      </>}
    </div></div>
    {error && <div className="error-box" role="alert">{error}</div>}
    {searching && searchable && <SearchBar inputRef={searchInput} label="Search file" query={query} count={hits.length} index={hitIndex}
      onQuery={value => { setQuery(value); setHitIndex(0) }} onStep={step} onClose={() => setSearching(false)} />}
    {loading ? <div className="empty"><LoaderCircle className="spin" />Loading preview...</div> :
      draft !== null ? <WikitextEditor value={draft} onChange={edit} onSave={() => { void save() }} /> :
        kind === 'image' ? <div className="image-preview">{url && <img src={hosted() ? url : `${url}?inline=true`} alt={path} />}</div> :
          kind === 'text' ? <pre ref={preview} className="text-preview">{markMatches(highlighted, hits, needle.length, activeHit)}</pre> :
            <div className="empty"><ArrowDownToLine /><p>No preview available. Download to open.</p></div>}
  </div>
}

function JobProgress({ job }: { job: Job }) {
  const progress = job.progress
  const total = progress?.total, completed = progress?.completed
  const known = job.status === 'running' && total != null && total > 0 && completed != null
  const stage = job.status === 'queued' ? 'Queued' : job.status === 'failed' ? 'Failed' : progress?.stage ?? (active(job) ? 'Running' : 'Completed')
  const count = known ? `${completed} / ${total}` : ''
  const warnings = progress?.warnings ? `${progress.warnings} ${progress.warnings === 1 ? 'warning' : 'warnings'}` : ''
  const detail = job.status === 'running' ? progress?.message : ''
  return <div className="job-progress" title={[stage, detail].filter(Boolean).join(' · ')}>
    <strong>{stage}</strong>
    {(count || warnings) && <span>{[count, warnings].filter(Boolean).join(' · ')}</span>}
  </div>
}

function JobDialog({ job, onClose, onDelete, onQueued }: { job: Job; onClose: () => void; onDelete: () => void; onQueued: (open: boolean) => void }) {
  const [tab, setTab] = useState<'output' | 'logs'>(job.status === 'failed' || active(job) ? 'logs' : 'output')
  const [references, setReferences] = useState(false)
  const hasReferences = job.tool_id === 'character-kit' && job.status === 'succeeded'
  const hasAIResult = job.tool_id === 'enemy-ai' && job.status === 'succeeded' && job.files.some(file => file.path === AI_RESULT)
  const [status, setStatus] = useState(job.status)
  const [logs, setLogs] = useState('')
  const [logTruncated, setLogTruncated] = useState(false)
  const [logError, setLogError] = useState('')
  const [logBusy, setLogBusy] = useState(false)
  const [copiedLog, setCopiedLog] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Artifact | null>(null)
  const [picked, setPicked] = useState<Set<string>>(() => new Set())
  const [queueing, setQueueing] = useState(false)
  const [queueNote, setQueueNote] = useState('')
  const dirty = useRef(false)
  // Switch to the output when a job finishes successfully while this window is open.
  if (status !== job.status) {
    setStatus(job.status)
    if (job.status === 'succeeded') setTab('output')
  }
  const selectedFile = job.files.find(file => file.path === selected?.path) ?? job.files[0] ?? null
  const discard = () => {
    if (dirty.current && !window.confirm('Discard unsaved changes?')) return false
    dirty.current = false
    return true
  }
  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        const result = await api<{ text: string; truncated: boolean }>(`/jobs/${job.id}/logs`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setLogs(terminal(result.text))
        setLogTruncated(result.truncated)
        setLogError('')
      } catch (reason) { if (!controller.signal.aborted) setLogError(message(reason)) }
    }
    void load()
    const timer = job.status === 'running' || job.status === 'queued' ? setInterval(() => { void load() }, 2000) : undefined
    return () => { controller.abort(); clearInterval(timer) }
  }, [job.id, job.status])
  const exportLog = async (copy: boolean) => {
    setLogBusy(true); setError(''); setCopiedLog(false)
    try {
      const result = await api<{ text: string }>(`/jobs/${job.id}/logs?full=true`)
      if (copy) { await navigator.clipboard.writeText(result.text); setCopiedLog(true) }
      else saveBlob(new Blob([result.text], { type: 'text/plain;charset=utf-8' }), `${job.tool_id}-${job.id.slice(0, 8)}.log`)
    } catch (reason) { setError(message(reason)) }
    finally { setLogBusy(false) }
  }
  const pages = active(job) ? [] : job.files.filter(queueable)
  const pickedPages = pages.filter(file => picked.has(file.path))
  const enqueue = async (files: Artifact[]) => {
    if (!discard()) return
    setQueueing(true); setQueueNote(''); setError('')
    try {
      const result = await api<{ added: number; skipped: number }>('/bot/queue', { method: 'POST', body: JSON.stringify({ job_id: job.id, paths: files.map(file => file.path) }) })
      setQueueNote(`Added ${result.added} ${result.added === 1 ? 'item' : 'items'} to the bot queue${result.skipped ? ` (${result.skipped} already queued)` : ''}.`)
      setPicked(new Set()); onQueued(false)
    } catch (reason) { setError(message(reason)) }
    finally { setQueueing(false) }
  }
  return <Dialog wide title={job.name} subtitle={`${time(job.created_at)} · ${job.id.slice(0, 8)}`} onClose={() => { if (discard()) onClose() }}
    extra={<>
      <Status status={job.status} />
      <JobProgress job={job} />
      {!active(job) && !hasAIResult && <span className="file-count">{job.files.length} {job.files.length === 1 ? 'file' : 'files'}</span>}
      {hasReferences && <button className={`button game-data small${references ? ' toggled' : ''}`} aria-pressed={references}
        title="View the character's BinOutput and attenuation data beside the output"
        onClick={() => { setReferences(!references); setTab('output') }}><Braces size={14} /> Game Data</button>}
      {job.files.length > 0 && !active(job) && !hasAIResult && <button className="button secondary small" onClick={() => { void downloadArchive(job).catch(reason => setError(message(reason))) }}><ArrowDownToLine size={15} /> Download ZIP</button>}
      {!active(job) && <button className="button danger small" onClick={() => { if (discard()) onDelete() }}><Trash2 size={14} /> Delete</button>}
    </>}>
    {job.error && <div className="job-error error-box" role="alert"><CircleAlert size={18} />{job.error} {job.files.length > 0 && 'Files below may be incomplete.'}</div>}
    <div className="detail-tabs">
      <button className={tab === 'output' ? 'selected' : ''} onClick={() => setTab('output')}><FolderOpen size={16} /> Output {!hasAIResult && <span>{job.files.length}</span>}</button>
      <button className={tab === 'logs' ? 'selected' : ''} onClick={() => { if (discard()) setTab('logs') }}><Terminal size={16} /> Log</button>
    </div>
    {(error || logError) && <div className="job-error error-box" role="alert">{error || logError}</div>}
    {queueNote && <div className="job-error queue-note" role="status"><Check size={16} />{queueNote}
      <button className="text-button" onClick={() => { if (discard()) onQueued(true) }}>Open Bot <ArrowRight size={14} /></button></div>}
    {tab === 'logs' ? <>
      <div className="log-toolbar">
        <span className="muted">{logTruncated ? 'Showing the most recent 128 KB. Copy or download for the full log.' : 'Job Log'}</span>
        <button className="text-button" disabled={logBusy} onClick={() => { void exportLog(true) }}><Copy size={14} />{copiedLog ? 'Copied' : 'Copy Log'}</button>
        <button className="text-button" disabled={logBusy} onClick={() => { void exportLog(false) }}><ArrowDownToLine size={14} />Download Full Log</button>
      </div>
      <pre className="log-view">{logs ? logs.split('\n').map((line, index) =>
        <span key={index} className={/^\[\d+:\d+\] ERROR/.test(line) ? 'log-error' : /^\[\d+:\d+\] WARNING/.test(line) ? 'log-warning' : undefined}>{line}{'\n'}</span>)
        : job.status === 'queued' ? 'Queued.' : 'No log output.'}</pre>
    </> :
      hasAIResult
        ? <EnemyAITable key={job.id} jobId={job.id} onDirty={value => { dirty.current = value }} />
        : job.files.length === 0 ? <div className="empty"><FolderOpen size={32} /><p>{active(job) ? 'Files appear when the job finishes.' : 'No output files.'}</p></div> :
      <div className={`output-layout${references && hasReferences ? ' with-references' : ''}`}>
        <div className="file-list">
          {pages.length > 0 && <div className="queue-bar">
            <input type="checkbox" aria-label="Select all pages and files" checked={pickedPages.length === pages.length}
              ref={input => { if (input) input.indeterminate = pickedPages.length > 0 && pickedPages.length < pages.length }}
              onChange={() => setPicked(new Set(pickedPages.length === pages.length ? [] : pages.map(file => file.path)))} />
            <span>{pickedPages.length ? `${pickedPages.length} selected` : 'Bot queue'}</span>
            {queueing ? <LoaderCircle size={14} className="spin" /> : <>
              {pickedPages.length > 0 && <button className="text-button" title="Add the ticked pages and files to the bot queue" onClick={() => { void enqueue(pickedPages) }}><ListPlus size={14} /> Add</button>}
              <button className="text-button" title="Add every page and file from this job to the bot queue" onClick={() => { void enqueue(pages) }}>{pickedPages.length ? 'All' : <><ListPlus size={14} /> Add All</>}</button>
            </>}
          </div>}
          {job.files.map(file => <div key={file.path} className={`file-row${pages.includes(file) ? ' pickable' : ''}`}>
            {pages.includes(file) && <input type="checkbox" aria-label={`Select ${file.path} for the bot queue`} checked={picked.has(file.path)}
              onChange={event => setPicked(previous => { const next = new Set(previous); if (event.target.checked) next.add(file.path); else next.delete(file.path); return next })} />}
            <button className={file.path === selectedFile?.path ? 'selected' : ''} onClick={() => { if (file.path !== selectedFile?.path && discard()) setSelected(file) }}>
              <FileText size={16} /><span title={file.path}>{file.path}<small>{size(file.size)}</small></span>
            </button>
          </div>)}
        </div>
        {selectedFile && <FilePreview key={selectedFile.path} jobId={job.id} file={selectedFile} editable={!active(job)}
          shortcut={!(references && hasReferences)} onDirty={value => { dirty.current = value }} />}
        {references && hasReferences && <BinOutputViewer jobId={job.id} onClose={() => setReferences(false)} />}
      </div>}
  </Dialog>
}

function RevisionSelect({ source, value, disabled, label, onChange }: {
  source: string; value: string; disabled: boolean; label: string; onChange: (value: string) => void
}) {
  const [revisions, setRevisions] = useState<Revision[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    api<Revision[]>(`/dataset/revisions?source=${encodeURIComponent(source)}`, { signal: controller.signal })
      .then(setRevisions)
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
    return () => controller.abort()
  }, [source])
  const listed = revisions?.some(revision => revision.commit === value)
  return <>
    <select aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value)}>
      <option value="latest">Latest (main)</option>
      {value !== 'latest' && !listed && <option value={value}>Pinned {value.slice(0, 8)}</option>}
      {revisions?.map(revision => <option key={revision.commit} value={revision.commit}>
        {revision.title} · {revision.date.slice(0, 10)} · {revision.commit.slice(0, 8)}{revision.downloaded ? ' · downloaded' : ''}
      </option>)}
    </select>
    {error ? <small className="field-error" role="alert">{error}</small> : !revisions && <small>Loading revisions...</small>}
  </>
}

function SourcePicker({ dataset, disabled, onSaved }: { dataset: Dataset; disabled: boolean; onSaved: (dataset: Dataset) => void }) {
  const [excel, setExcel] = useState(dataset.excel_source ?? 'dimbreath')
  const [binoutput, setBinoutput] = useState(dataset.binoutput_source ?? 'gura')
  const [excelRevision, setExcelRevision] = useState(dataset.excel_revision)
  const [binoutputRevision, setBinoutputRevision] = useState(dataset.binoutput_revision)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const changed = excel !== dataset.excel_source || binoutput !== dataset.binoutput_source ||
    excelRevision !== dataset.excel_revision || binoutputRevision !== dataset.binoutput_revision
  const save = async () => {
    setSaving(true); setError('')
    try {
      onSaved(await api<Dataset>('/dataset/sources', { method: 'PUT', body: JSON.stringify({
        excel, binoutput, excel_revision: excelRevision, binoutput_revision: binoutputRevision,
      }) }))
    } catch (reason) { setError(message(reason)) }
    finally { setSaving(false) }
  }
  const options = Object.entries(dataset.sources)
  const busy = disabled || saving
  return <div className="source-picker">
    <div className="field"><label htmlFor="excel-source">Excel &amp; TextMap Source</label>
      <select id="excel-source" value={excel} disabled={busy} onChange={event => { setExcel(event.target.value); setExcelRevision('latest') }}>
        {options.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>
      <RevisionSelect source={excel} value={excelRevision} disabled={busy} label="Excel & TextMap revision" onChange={setExcelRevision} />
      <small>ExcelBinOutput tables and the TextMaps used to resolve their text.</small>
    </div>
    <div className="field"><label htmlFor="binoutput-source">BinOutput Source</label>
      <select id="binoutput-source" value={binoutput} disabled={busy} onChange={event => { setBinoutput(event.target.value); setBinoutputRevision('latest') }}>
        {options.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>
      <RevisionSelect source={binoutput} value={binoutputRevision} disabled={busy} label="BinOutput revision" onChange={setBinoutputRevision} />
      <small>Monster configs used for enemy weight and endure type.</small>
    </div>
    <div className="source-actions">
      {changed && <button className="button secondary" disabled={busy} onClick={() => { void save() }}>
        {saving ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />} Save Sources
      </button>}
      {changed && <span className="subtle">Run setup after saving to download and prepare the selection.</span>}
      {error && <span className="field-error" role="alert">{error}</span>}
    </div>
  </div>
}

const LOCAL_SETUP_URL = 'https://github.com/Zhong-ba/tools#web-interface'

/** On a hosted site: which of the server's prepared revisions this browser uses. */
function HostedDatasetPicker({ dataset, onChanged }: { dataset: Dataset | null; onChanged: () => void }) {
  const [available, setAvailable] = useState<PreparedDatasets | null>(null)
  const [error, setError] = useState('')
  const [choice, setChoice] = useState(() => datasetChoice()?.split('.') ?? [])
  useEffect(() => {
    const controller = new AbortController()
    api<PreparedDatasets>('/datasets', { signal: controller.signal }).then(setAvailable)
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
    return () => controller.abort()
  }, [])
  const [excel, binoutput] = [choice[0] ?? available?.excel.find(item => item.active)?.commit ?? '',
    choice[1] ?? available?.binoutput.find(item => item.active)?.commit ?? '']
  const pick = (next: string[]) => {
    setChoice(next)
    setDatasetChoice(next[0] && next[1] ? next.join('.') : null)
    onChanged()
  }
  const label = (item: PreparedDatasets['excel'][number]) => `${item.title ?? 'Revision'} · ${dataset?.sources[item.source] ?? item.source} · ${item.commit.slice(0, 8)}${item.active ? ' · default' : ''}`
  return <div className="source-picker">
    <div className="field"><label htmlFor="hosted-excel">Excel &amp; TextMap Revision</label>
      <select id="hosted-excel" value={excel} disabled={!available} onChange={event => pick([event.target.value, binoutput])}>
        {available?.excel.map(item => <option key={item.commit} value={item.commit}>{label(item)}</option>)}
      </select>
      <small>ExcelBinOutput tables and the TextMaps used to resolve their text.</small>
    </div>
    <div className="field"><label htmlFor="hosted-binoutput">BinOutput Revision</label>
      <select id="hosted-binoutput" value={binoutput} disabled={!available} onChange={event => pick([excel, event.target.value])}>
        {available?.binoutput.map(item => <option key={item.commit} value={item.commit}>{label(item)}</option>)}
      </select>
      <small>Monster configs used for enemy weight and endure type.</small>
    </div>
    <div className="source-actions">
      {choice.length > 0 && <button className="button secondary" onClick={() => pick([])}><RotateCcw size={15} /> Use Default</button>}
      {error ? <span className="field-error" role="alert">{error}</span> : <span className="subtle">Available revisions depend on server storage; older revisions may be removed. For other revisions, <a href={LOCAL_SETUP_URL} target="_blank" rel="noreferrer">run Painmelo on your own PC</a>.</span>}
    </div>
  </div>
}

function WorkingDirectory({ config, storage, busy, onChanged }: {
  config: ServerConfig; storage: StorageInfo | null; busy: boolean; onChanged: (config?: ServerConfig) => void
}) {
  const [path, setPath] = useState(config.working_directory ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const work = async (task: () => Promise<void>) => {
    setSaving(true); setError('')
    try { await task() } catch (reason) { if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(message(reason)) }
    finally { setSaving(false) }
  }
  const save = (value: string) => work(async () => {
    const next = await api<ServerConfig>('/config', { method: 'PUT', body: JSON.stringify({ working_directory: value }) })
    setPath(next.working_directory ?? ''); onChanged(next)
  })
  const local = (task: (store: typeof import('./local')) => Promise<void>) => work(async () => { await task(await import('./local')); onChanged() })
  const disabled = busy || saving
  return <section className="panel dataset-panel">
    <div className="dataset-title"><span className="stat-icon"><FolderOpen size={22} /></span><div><h2>Working Directory</h2>
      <p>{config.hosted ? 'Where this browser keeps your finished jobs, bot queue and bot settings' : 'Where jobs and the bot queue are kept'}</p></div></div>
    {config.hosted ? <>
      <div className="dataset-path"><span>{storage?.kind === 'folder' ? 'FOLDER' : 'STORAGE'}</span>
        <code>{storage ? storage.kind === 'folder' ? storage.folder : 'Browser storage (this browser profile only)' : 'Checking...'}</code></div>
      {storage?.needsPermission && <div className="notice"><FolderOpen size={18} /><p>The browser needs permission to use this folder again.</p></div>}
      {!storage?.supported && <p className="subtle">This browser cannot save to a folder, so jobs are kept in browser storage. Use Chrome or Edge to choose a folder.</p>}
      <footer><p>Switching does not move existing files. Your bot password stays in this browser.</p><div className="source-actions">
        {storage?.needsPermission && <button className="button primary" disabled={disabled} onClick={() => { void local(store => store.reconnectFolder()) }}><Check size={15} /> Reconnect Folder</button>}
        {storage?.kind === 'folder' && <button className="button secondary" disabled={disabled} onClick={() => { void local(store => store.useBrowserStorage()) }}>Use Browser Storage</button>}
        {storage?.supported && <button className="button secondary" disabled={disabled} onClick={() => { void local(store => store.chooseFolder()) }}><FolderOpen size={15} /> Choose Folder</button>}
      </div></footer>
    </> : <>
      <div className="field"><label htmlFor="working-directory">Folder</label>
        <input id="working-directory" value={path} disabled={disabled} placeholder={config.default_working_directory ?? ''} onChange={event => setPath(event.target.value)}
          onKeyDown={event => { if (event.key === 'Enter') void save(path) }} />
        <small>Jobs go in its <code>jobs</code> folder and the bot queue in <code>bot</code>. Existing files are not moved.</small>
      </div>
      <footer><p>{busy ? 'Wait for running jobs and posting to finish before switching.' : `Default: ${config.default_working_directory ?? ''}`}</p><div className="source-actions">
        {config.working_directory !== config.default_working_directory && <button className="button secondary" disabled={disabled} onClick={() => { void save('') }}><RotateCcw size={15} /> Use Default</button>}
        <button className="button primary" disabled={disabled || !path.trim() || path.trim() === config.working_directory} onClick={() => { void save(path) }}>
          {saving ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />} Save
        </button>
      </div></footer>
    </>}
    {error && <div className="error-box" role="alert"><CircleAlert size={18} />{error}</div>}
  </section>
}

type Selection = { checked: Set<string>; onChange: (ids: Set<string>) => void }

const isPage = (path: string) => /\.(wikitext|lua)$/i.test(path)
const isMedia = (path: string) => /\.(png|jpe?g|webp|gif)$/i.test(path)
const queueable = (file: Artifact) => isPage(file.path) || isMedia(file.path)
const queueStatus: Record<QueueEntry['status'], { label: string; tone: string }> = {
  pending: { label: 'Pending', tone: 'queued' }, posting: { label: 'Posting', tone: 'running' },
  posted: { label: 'Posted', tone: 'succeeded' }, skipped: { label: 'Skipped', tone: 'skipped' }, failed: { label: 'Failed', tone: 'failed' },
}
const postable = (item: QueueEntry) => !!item.title && (item.status === 'pending' || item.status === 'failed')
const botOptions: { key: keyof BotSettings; title: string; description: string }[] = [
  { key: 'skip_existing', title: 'Skip Existing Pages', description: 'Only create pages and upload files that do not exist yet.' },
  { key: 'skip_unchanged', title: 'Skip Unchanged Pages', description: 'Do not save null edits or re-upload files identical to the live version.' },
  { key: 'bot_edit', title: 'Mark as Bot Edits', description: 'Hides the edits from Recent Changes (needs the bot right).' },
  { key: 'watch', title: 'Watch Posted Pages', description: 'Adds each posted page to your watchlist.' },
  { key: 'protect', title: 'Protect Posted Pages', description: 'Restricts editing and moving to administrators (sysop only).' },
]

function QueueItemDialog({ id, onClose, onSaved }: { id: string; onClose: () => void; onSaved: () => void }) {
  const [item, setItem] = useState<QueueItem | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    api<QueueItem>(`/bot/queue/${id}`, { signal: controller.signal })
      .then(result => { setItem(result); setTitle(result.title ?? ''); setContent(result.content) })
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
    return () => controller.abort()
  }, [id])
  const dirty = !!item && (title.trim() !== (item.title ?? '') || content !== item.content)
  const close = () => { if (!dirty || window.confirm('Discard unsaved changes?')) onClose() }
  const save = async () => {
    if (!item || !dirty || saving) return
    setSaving(true); setError('')
    try {
      const saved = await api<QueueItem>(`/bot/queue/${id}`, { method: 'PATCH', body: JSON.stringify({ title: title.trim(), content }) })
      setItem(saved); setTitle(saved.title ?? ''); setContent(saved.content); onSaved()
    } catch (reason) { setError(message(reason)) }
    finally { setSaving(false) }
  }
  const file = item?.kind === 'file'
  const media = useAssetUrl('media', file ? id : '')
  return <Dialog wide title={item?.title || (file ? 'Untitled File' : 'Untitled Page')} subtitle={item ? `${item.source} · ${item.path ?? ''}` : undefined} onClose={close}
    extra={<>
      {item && <span className={`status ${queueStatus[item.status].tone}`}><span className="status-dot" />{queueStatus[item.status].label}</span>}
      <button className="button primary small" disabled={!dirty || saving || item?.status === 'posting'} onClick={() => { void save() }} title="Save (Ctrl+S)">
        {saving ? <LoaderCircle size={14} className="spin" /> : <Save size={14} />} Save
      </button>
    </>}>
    <div className="queue-editor">
      <div className="field"><label htmlFor="queue-title">{file ? 'Target File' : 'Target Page'}</label>
        <input id="queue-title" value={title} placeholder={file ? 'File:Name.png' : 'Page title on the wiki'} onChange={event => setTitle(event.target.value)}
          onKeyDown={event => { if (event.key === 'Enter') void save() }} />
        {item?.message && <small>{item.message}</small>}
      </div>
      {error && <div className="error-box" role="alert"><CircleAlert size={18} />{error}</div>}
      {file && <div className="queue-media">{media && <img src={media} alt={item.path ?? ''} />}
        <small>File page content, used when the file is new. Re-uploading an existing file leaves its page unchanged.</small></div>}
      {item ? <WikitextEditor value={content} onChange={setContent} onSave={() => { void save() }} />
        : !error && <div className="empty"><LoaderCircle className="spin" />Loading page...</div>}
    </div>
  </Dialog>
}

function BotPage({ state, onState }: { state: BotState; onState: (state: BotState) => void }) {
  const [draft, setDraft] = useState<BotSettings>(state.settings)
  const [password, setPassword] = useState('')
  const [checked, setChecked] = useState<Set<string>>(() => new Set())
  const [opened, setOpened] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [settingsNote, setSettingsNote] = useState('')
  const anchor = useRef<string | null>(null)
  const { items, running } = state
  const dirty = password !== '' || (Object.keys(draft) as (keyof BotSettings)[]).some(key => draft[key] !== state.settings[key])
  const selected = items.filter(item => checked.has(item.id))
  const ready = items.filter(postable)
  const untitled = items.filter(item => !item.title && item.status !== 'posted')
  const posted = items.filter(item => item.status === 'posted')
  const request = async <T,>(work: () => Promise<T>) => {
    setBusy(true); setError('')
    try { return await work() } catch (reason) { setError(message(reason)); return undefined } finally { setBusy(false) }
  }
  const saveSettings = async () => {
    const next = await api<BotState>('/bot/settings', { method: 'PUT', body: JSON.stringify({ ...draft, password: password || null }) })
    setPassword(''); setDraft(next.settings); onState(next)
    return next
  }
  const save = () => request(async () => { await saveSettings(); setSettingsNote('Settings saved.') })
  const testLogin = () => request(async () => {
    setSettingsNote('')
    if (dirty) await saveSettings()
    const result = await api<{ username: string }>('/bot/login', { method: 'POST' })
    setSettingsNote(`Logged in as ${result.username}.`)
  })
  const forget = () => request(async () => {
    const next = await api<BotState>('/bot/settings', { method: 'PUT', body: JSON.stringify({ ...state.settings, remember: false, password: '' }) })
    setPassword(''); setDraft(next.settings); onState(next); setSettingsNote('Password cleared.')
  })
  const post = (ids?: string[]) => request(async () => {
    if (dirty) await saveSettings()
    onState(await api<BotState>('/bot/post', { method: 'POST', body: JSON.stringify(ids ? { ids } : {}) }))
    setChecked(new Set())
  })
  const stop = () => request(async () => onState(await api<BotState>('/bot/stop', { method: 'POST' })))
  const remove = (ids: string[]) => request(async () => {
    onState(await api<BotState>('/bot/queue/remove', { method: 'POST', body: JSON.stringify({ ids }) }))
    setChecked(previous => new Set([...previous].filter(id => !ids.includes(id))))
  })
  const reset = (ids: string[]) => request(async () => onState(await api<BotState>('/bot/queue/reset', { method: 'POST', body: JSON.stringify({ ids }) })))
  const rename = (item: QueueEntry, value: string) => {
    if (value.trim() === (item.title ?? '')) return
    void request(async () => {
      await api<QueueItem>(`/bot/queue/${item.id}`, { method: 'PATCH', body: JSON.stringify({ title: value.trim() }) })
      onState(await api<BotState>('/bot'))
    })
  }
  const toggle = (item: QueueEntry, range: boolean) => {
    const next = new Set(checked)
    const on = !next.has(item.id)
    const from = range && anchor.current ? items.findIndex(entry => entry.id === anchor.current) : -1
    const to = items.indexOf(item)
    const span = from < 0 ? [item] : items.slice(Math.min(from, to), Math.max(from, to) + 1)
    span.forEach(entry => { if (on) next.add(entry.id); else next.delete(entry.id) })
    anchor.current = item.id
    setChecked(next)
  }
  const setting = <K extends keyof BotSettings>(key: K, value: BotSettings[K]) => { setDraft(previous => ({ ...previous, [key]: value })); setSettingsNote('') }
  const selectedReady = selected.filter(postable)
  return <>
    <div className="section-heading page-title"><h1>Bot</h1></div>
    {error && <div className="error-box page-error" role="alert"><CircleAlert size={18} />{error}<button className="text-button" onClick={() => setError('')}>Dismiss</button></div>}
    <div className="bot-layout">
      <div className="bot-main">
        <section className="panel">
          <div className="panel-heading"><h2>Queue <span className="count">{items.length}</span></h2>
            {selected.length > 0 ? <div className="bulk-actions"><span className="subtle">{selected.length} selected</span>
              <button className="text-button" onClick={() => setChecked(new Set())}>Clear</button>
              <button className="button secondary small" disabled={busy || running || !selectedReady.length} title={selectedReady.length ? undefined : 'Selected pages need a title and must be pending or failed'}
                onClick={() => { void post(selectedReady.map(item => item.id)) }}><Send size={14} /> Post Selected</button>
              <button className="button secondary small" disabled={busy} onClick={() => { void reset(selected.map(item => item.id)) }}><RotateCcw size={14} /> Reset</button>
              <button className="button danger small" disabled={busy} onClick={() => { void remove(selected.map(item => item.id)) }}><Trash2 size={14} /> Remove</button>
            </div> : <div className="bulk-actions">
              {posted.length > 0 && <button className="text-button" disabled={busy} onClick={() => { void remove(posted.map(item => item.id)) }}>Clear posted</button>}
              {running ? <button className="button danger small" disabled={state.stopping} onClick={() => { void stop() }}>
                {state.stopping ? <LoaderCircle size={14} className="spin" /> : <Square size={13} />} {state.stopping ? 'Stopping' : 'Stop'}
              </button> : <button className="button primary small" disabled={busy || !ready.length} title={ready.length ? `Post ${ready.length} ${ready.length === 1 ? 'page' : 'pages'} to ${state.settings.wiki}` : 'Nothing is ready to post'}
                onClick={() => { void post() }}><Send size={14} /> Post Queue {ready.length > 0 && <span className="button-count">{ready.length}</span>}</button>}
            </div>}
          </div>
          {untitled.length > 0 && <div className="queue-warning"><CircleAlert size={15} />{untitled.length} {untitled.length === 1 ? 'page needs' : 'pages need'} a target page before {untitled.length === 1 ? 'it' : 'they'} can be posted.</div>}
          {!items.length ? <div className="empty"><Bot size={28} /><p>The queue is empty. Open a finished job and add its outputs to the queue.</p></div> :
            <div className="table-scroll"><table className="jobs-table queue-table"><thead><tr>
              <th className="select-cell"><input type="checkbox" aria-label="Select all queued pages" checked={selected.length === items.length}
                ref={input => { if (input) input.indeterminate = selected.length > 0 && selected.length < items.length }}
                onChange={() => setChecked(new Set(selected.length === items.length ? [] : items.map(item => item.id)))} /></th>
              <th>Target Page</th><th>Source</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{items.map(item => <tr key={item.id} className={checked.has(item.id) ? 'selected' : ''} onClick={() => setOpened(item.id)}>
                <td className="select-cell" onClick={event => { event.stopPropagation(); toggle(item, event.shiftKey) }}>
                  <input type="checkbox" aria-label={`Select ${item.title ?? item.path ?? 'page'}`} checked={checked.has(item.id)}
                    onClick={event => { event.stopPropagation(); toggle(item, event.shiftKey) }} onChange={() => {}} />
                </td>
                <td className="title-cell" onClick={event => event.stopPropagation()}>
                  <input key={`${item.id}:${item.title ?? ''}`} className={`title-input${item.title ? '' : ' missing'}`} aria-label="Target page"
                    defaultValue={item.title ?? ''} placeholder="Set the target page..." disabled={item.status === 'posting'}
                    onBlur={event => rename(item, event.target.value)}
                    onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur(); if (event.key === 'Escape') { event.currentTarget.value = item.title ?? ''; event.currentTarget.blur() } }} />
                  {item.message && <small className={item.status === 'failed' ? 'field-error' : ''} title={item.message}>{item.message}</small>}
                </td>
                <td className="muted source-cell"><span title={item.path ?? ''}>{item.kind === 'file' && <ImageIcon size={13} className="kind-icon" />}{item.path}</span><small>{item.source} · {size(item.size)}</small></td>
                <td><span className={`status ${queueStatus[item.status].tone}`}>
                  {item.status === 'posting' ? <LoaderCircle size={12} className="spin" /> : <span className="status-dot" />}{queueStatus[item.status].label}</span></td>
                <td className="row-actions">
                  <button className="icon-button delete" disabled={item.status === 'posting'} aria-label={`Remove ${item.title ?? 'page'} from the queue`} title="Remove"
                    onClick={event => { event.stopPropagation(); void remove([item.id]) }}><Trash2 size={15} /></button>
                  <ChevronRight size={16} />
                </td>
              </tr>)}</tbody></table></div>}
        </section>
        {state.log.length > 0 && <section className="panel"><div className="panel-heading"><h2>Posting Log</h2>{running && <span className="subtle"><LoaderCircle size={13} className="spin" /> Posting...</span>}</div>
          <pre className="log-view bot-log">{state.log.join('\n')}</pre></section>}
      </div>
      <section className="panel bot-settings">
        <div className="panel-heading"><h2>Settings</h2></div>
        <form className="form-fields" onSubmit={event => { event.preventDefault(); void save() }}>
          <div className="field"><label htmlFor="bot-wiki">Wiki URL</label>
            <input id="bot-wiki" value={draft.wiki} disabled={running} placeholder="https://genshin-impact.fandom.com" onChange={event => setting('wiki', event.target.value)} />
            {draft.wiki !== 'https://genshin-impact.fandom.com' && <button type="button" className="text-button align-start" onClick={() => setting('wiki', 'https://genshin-impact.fandom.com')}>Use the Genshin Impact Wiki</button>}
          </div>
          <div className="field"><label htmlFor="bot-user">Bot Username</label>
            <input id="bot-user" value={draft.username} disabled={running} autoComplete="username" placeholder="Username@BotName" onChange={event => setting('username', event.target.value)} />
          </div>
          <div className="field"><label htmlFor="bot-password">Bot Password</label>
            <input id="bot-password" type="password" value={password} disabled={running} autoComplete="current-password"
              placeholder={state.has_password ? '•••••••• (unchanged)' : 'From Special:BotPasswords'} onChange={event => { setPassword(event.target.value); setSettingsNote('') }} />
            <small>Create one at Special:BotPasswords with the "Edit existing pages", "Create, edit, and move pages", "Upload new files" and "Upload, replace, and move files" (for images) and, for protecting, "Protect and unprotect pages" grants.</small>
          </div>
          <label className="check-field"><input type="checkbox" checked={draft.remember} disabled={running} onChange={event => setting('remember', event.target.checked)} />
            <span><strong>Remember Login</strong><small>{hosted() ? 'Saves the username and password in this browser. Otherwise they are kept until the page is closed or reloaded.' : 'Saves the username and password on this computer. Otherwise they are kept until the server restarts.'}</small></span></label>
          <div className="field"><label htmlFor="bot-summary">Edit Summary</label>
            <input id="bot-summary" value={draft.summary} disabled={running} maxLength={500} onChange={event => setting('summary', event.target.value)} />
          </div>
          {botOptions.map(option => <label className="check-field" key={option.key}>
            <input type="checkbox" checked={draft[option.key] === true} disabled={running} onChange={event => setting(option.key, event.target.checked)} />
            <span><strong>{option.title}</strong><small>{option.description}</small></span>
          </label>)}
          {settingsNote && <small className="version-note">{settingsNote}</small>}
          <div className="settings-actions">
            {state.has_password && <button type="button" className="text-button" disabled={busy || running} onClick={() => { void forget() }}>Forget password</button>}
            <button type="button" className="button secondary small" disabled={busy || running || !draft.username || !(password || state.has_password)} onClick={() => { void testLogin() }}><KeyRound size={14} /> Test Login</button>
            <button className="button primary small" disabled={busy || running || !dirty}><Save size={14} /> Save</button>
          </div>
        </form>
      </section>
    </div>
    {opened && <QueueItemDialog key={opened} id={opened} onClose={() => setOpened(null)} onSaved={() => { void api<BotState>('/bot').then(onState) }} />}
  </>
}

function JobTable({ jobs, onSelect, onDelete, selection }: { jobs: Job[]; onSelect: (id: string) => void; onDelete: (job: Job) => void; selection?: Selection }) {
  const anchor = useRef<string | null>(null)
  if (!jobs.length) return <div className="empty"><Clock3 size={28} /><p>No jobs yet.</p></div>
  const deletable = jobs.filter(job => !active(job))
  const checkedCount = deletable.filter(job => selection?.checked.has(job.id)).length
  const toggle = (job: Job, range: boolean) => {
    if (!selection) return
    const next = new Set(selection.checked)
    const on = !next.has(job.id)
    const from = range && anchor.current ? jobs.findIndex(item => item.id === anchor.current) : -1
    const to = jobs.indexOf(job)
    const span = from < 0 ? [job] : jobs.slice(Math.min(from, to), Math.max(from, to) + 1)
    span.filter(item => !active(item)).forEach(item => { if (on) next.add(item.id); else next.delete(item.id) })
    anchor.current = job.id
    selection.onChange(next)
  }
  return <div className="table-scroll"><table className="jobs-table"><thead><tr>
    {selection && <th className="select-cell"><input type="checkbox" aria-label="Select all jobs" disabled={!deletable.length}
      checked={deletable.length > 0 && checkedCount === deletable.length} ref={input => { if (input) input.indeterminate = checkedCount > 0 && checkedCount < deletable.length }}
      onChange={() => selection.onChange(new Set(checkedCount === deletable.length ? [] : deletable.map(job => job.id)))} /></th>}
    <th>Tool</th><th>Status</th><th>Created</th><th>Files</th><th><span className="sr-only">Actions</span></th></tr></thead>
    <tbody>{jobs.map(job => <tr key={job.id} className={selection?.checked.has(job.id) ? 'selected' : ''} onClick={() => onSelect(job.id)}>
      {selection && <td className="select-cell" onClick={event => { event.stopPropagation(); if (!active(job)) toggle(job, event.shiftKey) }}>
        <input type="checkbox" aria-label={`Select ${job.name} job ${job.id.slice(0, 8)}`} disabled={active(job)} title={active(job) ? 'Wait for the job to finish' : undefined}
          checked={selection.checked.has(job.id)} onClick={event => { event.stopPropagation(); toggle(job, event.shiftKey) }} onChange={() => {}} />
      </td>}
      <td><button className="job-name" onClick={event => { event.stopPropagation(); onSelect(job.id) }}><span className="job-glyph"><FileText size={17} /></span><span>{job.name}<small>{job.id.slice(0, 8)}</small></span></button></td>
      <td><Status status={job.status} /></td><td className="muted">{time(job.created_at)}</td><td className="muted">{job.files.length}</td>
      <td className="row-actions">
        <button className="icon-button delete" disabled={active(job)} aria-label={`Delete ${job.name} job ${job.id.slice(0, 8)}`} title={active(job) ? 'Wait for the job to finish' : 'Delete'}
          onClick={event => { event.stopPropagation(); onDelete(job) }}><Trash2 size={15} /></button>
        <ChevronRight size={16} />
      </td>
    </tr>)}</tbody></table></div>
}

function App() {
  const [page, setPage] = useState<'tools' | 'jobs' | 'bot' | 'dataset'>('tools')
  const [tools, setTools] = useState<Tool[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [bot, setBot] = useState<BotState | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [networkError, setNetworkError] = useState('')
  const [actionError, setActionError] = useState('')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null)
  const [selectedJob, setSelectedJob] = useState<string | null>(null)
  const [characters, setCharacters] = useState<Character[]>([])
  const [characterError, setCharacterError] = useState('')
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [confirmSetup, setConfirmSetup] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Job[] | null>(null)
  const [checkedJobs, setCheckedJobs] = useState<Set<string>>(() => new Set())
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [config, setConfig] = useState<ServerConfig | null>(null)
  const [storage, setStorage] = useState<StorageInfo | null>(null)
  const [datasetNotice, setDatasetNotice] = useState('')
  useEffect(() => {
    let cleanup = () => {}
    let cancelled = false
    serverConfig().then(async next => {
      if (cancelled) return
      setConfig(next)
      if (!next.hosted) return
      const choice = datasetChoice()
      if (choice) {
        // The server only keeps recent versions, so a revision picked earlier may have been removed since.
        const [excel, binoutput] = choice.split('.')
        const found = await api<PreparedDatasets>('/datasets')
        if (!found.excel.some(item => item.commit === excel) || !found.binoutput.some(item => item.commit === binoutput)) {
          setDatasetChoice(null)
          if (!cancelled) setDatasetNotice('The revision you picked is no longer on this server, so the default dataset is used again.')
        }
      }
      const store = await import('./local')
      const update = () => { void store.storage().then(setStorage) }
      cleanup = store.onStorageChange(update)
      update()
    }).catch(reason => setNetworkError(message(reason)))
    return () => { cancelled = true; cleanup() }
  }, [])
  // Hosted refreshes also copy finished jobs into browser storage, so they can overlap; only the newest one's result counts,
  // or a refresh started before a job was submitted could drop it from the list (and close its dialog).
  const refreshes = useRef(0)
  const refreshing = useRef(0)
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const current = ++refreshes.current
    refreshing.current++
    try {
      const [nextJobs, nextDataset, nextTools, nextBot] = await Promise.all([
        api<Job[]>('/jobs', { signal }), api<Dataset>('/dataset', { signal }), api<Tool[]>('/tools', { signal }), api<BotState>('/bot', { signal }),
      ])
      if (current !== refreshes.current) return
      setJobs(nextJobs); setDataset(nextDataset); setTools(nextTools); setBot(nextBot); setNetworkError('')
    } catch (reason) { if (!signal?.aborted && current === refreshes.current) setNetworkError(message(reason)) }
    finally { refreshing.current-- }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    const initial = setTimeout(() => { void refresh(controller.signal) }, 0)
    // Polling skips a tick while a slow refresh is still running instead of superseding it.
    const timer = setInterval(() => { if (!refreshing.current) void refresh(controller.signal) }, 2000)
    return () => { controller.abort(); clearTimeout(initial); clearInterval(timer) }
  }, [refresh])
  useEffect(() => {
    const syncToolFromPath = () => {
      const path = window.location.pathname.replace(/\/+$/, '')
      const tool = tools.find(item => path === `/${item.id}`) ?? null
      setSelectedTool(current => current?.id === tool?.id ? current : tool)
    }
    window.addEventListener('popstate', syncToolFromPath)
    syncToolFromPath()
    return () => window.removeEventListener('popstate', syncToolFromPath)
  }, [tools])
  useEffect(() => {
    if (!picksCharacter(selectedTool)) return
    const controller = new AbortController()
    api<Character[]>('/characters', { signal: controller.signal }).then(setCharacters)
      .catch(reason => { if (!controller.signal.aborted) setCharacterError(message(reason)) })
    return () => controller.abort()
  }, [selectedTool])
  const run = async (parameters: Parameters) => {
    if (!selectedTool) return
    setSubmitting(true); setFormError('')
    try {
      const job = await api<Job>('/jobs', { method: 'POST', body: JSON.stringify({ tool_id: selectedTool.id, parameters }) })
      closeTool(); setSelectedJob(job.id); setJobs(previous => [job, ...previous]); void refresh()
    } catch (reason) { setFormError(message(reason)) }
    finally { setSubmitting(false) }
  }
  const setup = async () => {
    setSubmitting(true); setActionError('')
    try {
      const job = await api<Job>('/dataset/setup', { method: 'POST', body: '{}' })
      setConfirmSetup(false); setSelectedJob(job.id); setJobs(previous => [job, ...previous]); void refresh()
    } catch (reason) { setActionError(message(reason)) }
    finally { setSubmitting(false) }
  }
  const deleteJob = (job: Job) => { setDeleteError(''); setPendingDelete([job]) }
  const confirmDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true); setDeleteError('')
    const removed = new Set<string>()
    let failure = ''
    for (const job of pendingDelete) {
      try { await api<void>(`/jobs/${job.id}`, { method: 'DELETE' }); removed.add(job.id) }
      catch (reason) { failure = `${job.name} ${job.id.slice(0, 8)}: ${message(reason)}` }
    }
    setJobs(previous => previous.filter(item => !removed.has(item.id)))
    refreshes.current++
    setCheckedJobs(previous => new Set([...previous].filter(id => !removed.has(id))))
    setSelectedJob(current => current && removed.has(current) ? null : current)
    if (failure) {
      setPendingDelete(pendingDelete.filter(job => !removed.has(job.id)))
      setDeleteError(removed.size ? `Deleted ${removed.size}; ${failure}` : failure)
    } else setPendingDelete(null)
    setDeleting(false)
  }
  const openTool = (tool: Tool) => {
    setFormError('')
    if (picksCharacter(tool)) { setCharacterError(''); setCharacters([]) }
    const path = `/${tool.id}`
    if (window.location.pathname !== path) window.history.pushState({ painmeloToolId: tool.id }, '', path)
    setSelectedTool(tool)
  }
  const closeTool = () => {
    const tool = selectedTool
    setSelectedTool(null)
    if (!tool || window.location.pathname.replace(/\/+$/, '') !== `/${tool.id}`) return
    if (window.history.state?.painmeloToolId === tool.id) window.history.back()
    else window.history.replaceState(null, '', '/')
  }
  const currentJob = jobs.find(job => job.id === selectedJob)
  const activeJobs = jobs.filter(active)
  const queuedPages = bot?.items.filter(item => item.status === 'pending' || item.status === 'failed').length ?? 0
  const selectedJobs = jobs.filter(job => checkedJobs.has(job.id) && !active(job))
  const setupRunning = activeJobs.some(job => job.tool_id === 'dataset-setup')
  const remote = dataset?.source === 'remote' || dataset?.source === 'github'
  const categories = ['All', ...new Set(tools.map(tool => tool.category))]
  const filtered = tools.filter(tool => (category === 'All' || tool.category === category) &&
    `${tool.name} ${tool.description}`.toLowerCase().includes(search.toLowerCase()))
  return <div className="workspace">
    <aside className="sidebar">
      <button className="brand" type="button" title="Click to boost the spin-up"
        onMouseEnter={event => startParty(event.currentTarget.querySelector('img'), page === 'tools')}
        onMouseLeave={stopParty} onBlur={stopParty}
        onClick={event => boostParty(event.currentTarget.querySelector('img'), page === 'tools', event.detail > 0 ? event : undefined)}>
        <img className="brand-mark" src="/painmelo.png" alt="" /><span>Painmelo</span>
      </button>
      <nav aria-label="Main navigation">
        <button className={page === 'tools' ? 'active' : ''} onClick={() => setPage('tools')}><LayoutGrid size={18} /> Tools <span>{tools.length}</span></button>
        <button className={page === 'jobs' ? 'active' : ''} onClick={() => setPage('jobs')}><Clock3 size={18} /> Jobs {activeJobs.length > 0 && <span>{activeJobs.length}</span>}</button>
        <button className={page === 'bot' ? 'active' : ''} onClick={() => setPage('bot')}><Bot size={18} /> Bot {bot?.running ? <LoaderCircle size={14} className="spin nav-spinner" /> : queuedPages > 0 && <span>{queuedPages}</span>}</button>
        <button className={page === 'dataset' ? 'active' : ''} onClick={() => setPage('dataset')}><Database size={18} /> Dataset <i className={dataset?.ready ? 'live-dot' : 'live-dot warning'} /></button>
      </nav>
      <button className="dataset-badge" onClick={() => setPage('dataset')}>
        <span className={dataset?.ready ? 'live-dot' : 'live-dot warning'} />
        {dataset ? dataset.ready ? `${dataset.commit?.slice(0, 8) ?? 'Local data'} · ${dataset.tables.toLocaleString()} tables` : 'Dataset not prepared' : 'Checking dataset...'}
      </button>
    </aside>
    <div className="main-shell">
      <main>
        {(networkError || actionError) && <div className="error-box page-error" role="alert"><CircleAlert size={18} />{networkError || actionError}<button className="text-button" onClick={() => { setActionError(''); void refresh() }}>Retry</button></div>}
        {datasetNotice && <div className="notice page-error"><Database size={18} /><p>{datasetNotice}</p>
          <button className="text-button" onClick={() => setDatasetNotice('')}>Dismiss</button></div>}
        {storage?.needsPermission && <div className="notice page-error"><FolderOpen size={18} /><p>Painmelo needs permission to use your working folder <strong>{storage.folder}</strong> again.</p>
          <button className="text-button" onClick={() => { void import('./local').then(store => store.reconnectFolder()).then(() => refresh()) }}>Reconnect</button></div>}
        {page === 'tools' && <>
          <section className="library-section">
            <div className="section-heading"><h1>Tools</h1><label className="search"><Search size={17} /><input aria-label="Search tools" placeholder="Search tools..." value={search} onChange={event => setSearch(event.target.value)} /></label></div>
            <div className="filters" aria-label="Tool categories">{categories.map(item => <button key={item} className={category === item ? 'selected' : ''} onClick={() => setCategory(item)}>{item}</button>)}</div>
            <div className="tool-grid">{filtered.map(tool => {
              const Icon = icons[tool.id] ?? BookOpen
              const disabled = tool.requires_dataset && !dataset?.ready
              return <button className={`tool-card ${tool.id}`} key={tool.id} onClick={() => disabled ? setPage('dataset') : openTool(tool)}
                title={disabled ? 'Prepare the dataset to use this tool' : `Open ${tool.name}`}>
                {tool.id === 'attribute-scaling' && <img className="tool-watermark" src="/leopeek.png" alt="" aria-hidden="true" />}
                <span className="tool-card-top"><span className="tool-icon"><Icon className="tool-glyph" size={25} strokeWidth={1.6} /><img className="tool-melo" src="/painmelo.png" alt="" /></span><span className="category-label">{tool.category}</span></span>
                <ToolText className="tool-name" text={tool.name} />
                <ToolText className="tool-description" text={tool.description} />
                {disabled && <span className="setup-required">Requires dataset setup <ChevronRight size={12} /></span>}
              </button>
            })}</div>
            {tools.length === 0 && !networkError && <div className="empty"><LoaderCircle className="spin" /><p>Loading tools...</p></div>}
            {tools.length > 0 && filtered.length === 0 && <div className="empty"><Search /><p>No matching tools.</p></div>}
          </section>
          <section className="panel"><div className="panel-heading"><h2>Recent Jobs</h2><button className="text-button" onClick={() => setPage('jobs')}>View all <ArrowRight size={15} /></button></div><JobTable jobs={jobs.slice(0, 5)} onSelect={setSelectedJob} onDelete={deleteJob} /></section>
        </>}
        {page === 'jobs' && <>
          <div className="section-heading page-title"><h1>Jobs</h1></div>
          <div className="panel"><div className="panel-heading"><h2>All Jobs <span className="count">{jobs.length}</span></h2>
            {selectedJobs.length > 0 ? <div className="bulk-actions"><span className="subtle">{selectedJobs.length} selected</span>
              <button className="text-button" onClick={() => setCheckedJobs(new Set())}>Clear</button>
              <button className="button danger small" onClick={() => { setDeleteError(''); setPendingDelete(selectedJobs) }}><Trash2 size={14} /> Delete selected</button></div>
              : <span className="subtle">{activeJobs.length} active · runs one at a time</span>}</div>
            <JobTable jobs={jobs} onSelect={setSelectedJob} onDelete={deleteJob} selection={{ checked: checkedJobs, onChange: setCheckedJobs }} /></div>
        </>}
        {page === 'bot' && (bot ? <BotPage state={bot} onState={setBot} /> : <div className="empty"><LoaderCircle className="spin" /><p>Loading bot...</p></div>)}
        {page === 'dataset' && <>
          <div className="section-heading page-title"><h1>Dataset</h1></div>
          <section className="panel dataset-panel">
            <div className="dataset-title"><span className="stat-icon"><Database size={22} /></span><div><h2>{remote ? 'Downloaded Game Data' : 'Local Game Data'}</h2><p>{remote ? 'Managed copies from the selected sources' : 'Configured RepoPath'}</p></div><span className={`status ${dataset?.ready ? 'succeeded' : 'queued'}`}><span className="status-dot" />{dataset?.ready ? 'Prepared' : 'Not prepared'}</span></div>
            {config?.hosted ? <HostedDatasetPicker dataset={dataset} onChanged={() => { void refresh() }} />
              : remote && dataset && <SourcePicker key={`${dataset.excel_source}-${dataset.binoutput_source}-${dataset.excel_revision}-${dataset.binoutput_revision}`} dataset={dataset} disabled={setupRunning} onSaved={setDataset} />}
            {dataset?.error && <div className="error-box"><CircleAlert size={18} />{dataset.error}</div>}
            <div className="dataset-metrics"><div><strong>{dataset?.tables.toLocaleString() ?? '0'}</strong><span>Mapped Tables</span></div><div><strong>{dataset?.languages ?? 0}</strong><span>TextMap Languages</span></div><div><strong>{dataset?.commit?.slice(0, 8) ?? '—'}</strong><span>{remote ? 'Excel Revision' : 'Revision'}</span>{dataset?.excel_title && <small className="revision-title" title={dataset.excel_title}>{dataset.excel_title}</small>}</div>{remote && <div><strong>{dataset?.binoutput_commit?.slice(0, 8) ?? '—'}</strong><span>BinOutput Revision</span>{dataset?.binoutput_title && <small className="revision-title" title={dataset.binoutput_title}>{dataset.binoutput_title}</small>}</div>}</div>
            {!config?.hosted && <div className="dataset-path"><span>{remote ? 'EXCEL & TEXTMAP PATH' : 'PATH'}</span><code>{dataset?.path ?? 'No prepared dataset.'}</code></div>}
            {!config?.hosted && dataset?.binoutput_path && <div className="dataset-path"><span>BINOUTPUT PATH</span><code>{dataset.binoutput_path}</code></div>}
            {!config?.hosted && <footer><p>{remote ? 'Failed updates keep the current revisions active.' : 'Setup rewrites the local dataset in place.'}</p><button className="button primary" disabled={setupRunning || !dataset?.source} onClick={() => { setActionError(''); setConfirmSetup(true) }}>{setupRunning ? <LoaderCircle className="spin" size={16} /> : <ArrowDownToLine size={16} />}{setupRunning ? 'Setup running' : dataset?.ready ? 'Check for updates' : 'Run setup'}</button></footer>}
          </section>
          {config && <WorkingDirectory key={config.working_directory ?? 'hosted'} config={config} storage={storage} busy={activeJobs.length > 0 || !!bot?.running}
            onChanged={next => { if (next) setConfig(next); setSelectedJob(null); setCheckedJobs(new Set()); void refresh() }} />}
        </>}
      </main>
    </div>
    {selectedTool && (selectedTool.id === 'other-languages'
      ? <Dialog title={selectedTool.name} subtitle={selectedTool.description} wide onClose={closeTool}><OtherLanguages /></Dialog>
      : selectedTool.id === 'binoutput-viewer'
        ? <Dialog title={selectedTool.name} subtitle={selectedTool.description} wide onClose={closeTool}><BinOutputViewer characters={characters} /></Dialog>
      : <ToolForm key={selectedTool.id} tool={selectedTool} characters={characters} characterError={characterError} submitting={submitting} error={formError} onSubmit={parameters => { void run(parameters) }} onClose={closeTool} />)}
    {currentJob && <JobDialog key={currentJob.id} job={currentJob} onClose={() => setSelectedJob(null)} onDelete={() => deleteJob(currentJob)}
      onQueued={open => { void refresh(); if (open) { setSelectedJob(null); setPage('bot') } }} />}
    {pendingDelete && <Dialog title={pendingDelete.length === 1 ? 'Delete Job?' : `Delete ${pendingDelete.length} Jobs?`} expandable={false} onClose={() => { if (!deleting) setPendingDelete(null) }}>
      <div className="dialog-body form-fields">
        {pendingDelete.length === 1
          ? <p className="confirm-text">Delete the <strong>{pendingDelete[0].name}</strong> job <code>{pendingDelete[0].id.slice(0, 8)}</code> from {time(pendingDelete[0].created_at)} and its {pendingDelete[0].files.length} output {pendingDelete[0].files.length === 1 ? 'file' : 'files'}? This cannot be undone.</p>
          : <p className="confirm-text">Delete <strong>{pendingDelete.length} jobs</strong> and their {pendingDelete.reduce((sum, job) => sum + job.files.length, 0)} output files? This cannot be undone.</p>}
        {deleteError && <div className="error-box" role="alert"><CircleAlert size={18} />{deleteError}</div>}
      </div>
      <footer className="dialog-footer">
        <button className="button secondary" autoFocus onClick={() => setPendingDelete(null)} disabled={deleting}>Cancel</button>
        <button className="button danger" onClick={() => { void confirmDelete() }} disabled={deleting}>
          {deleting ? <LoaderCircle size={15} className="spin" /> : <Trash2 size={15} />} Delete
        </button>
      </footer>
    </Dialog>}
    {confirmSetup && <Dialog title="Run Dataset Setup?" expandable={false} onClose={() => setConfirmSetup(false)}>
      <div className="dialog-body"><div className="notice"><Database size={18} /><p>{remote ? `Checks ${dataset?.sources[dataset.excel_source ?? ''] ?? 'the Excel source'} and ${dataset?.sources[dataset.binoutput_source ?? ''] ?? 'the BinOutput source'} for new revisions and prepares them. A new Excel revision downloads several GB and takes a few minutes; unchanged revisions are reused.` : 'Rewrites TextMaps and mapped tables in the configured dataset. Back up the input data first.'}</p></div>{actionError && <div className="error-box" role="alert">{actionError}</div>}</div>
      <footer className="dialog-footer"><button className="button secondary" onClick={() => setConfirmSetup(false)}>Cancel</button><button className="button primary" disabled={submitting} onClick={() => { void setup() }}>{submitting ? <LoaderCircle className="spin" size={16} /> : <Play size={15} />} Run setup</button></footer>
    </Dialog>}
  </div>
}

export default App
