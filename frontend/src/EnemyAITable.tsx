import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { ArrowUpRight, Check, Copy, Pencil, Save, Trash2, Undo2, X } from 'lucide-react'
import { api, message } from './api'
import { SkillReferenceViewer } from './BinOutputViewer'
import type { SkillReference } from './BinOutputViewer'

export const AI_RESULT = 'Enemy AI Logic.json'
const EDITS = 'Enemy AI Edits.json'
type Confidence = 'direct' | 'traced' | 'candidate'
type AttackReference = SkillReference & { confidence?: Confidence; evidence?: string[];
  attacks?: { element: string | null; percent: string | null; condition?: string }[] }
const confidenceOf = (ref: AttackReference): Confidence => ref.confidence ??
  (ref.kind === 'Monster animation event' ? 'direct' : 'candidate')
const attackLabels = { direct: 'Direct Attacks', traced: 'Traced Attacks', candidate: 'Candidate Attacks' }
type Row = { id: string; name: string; internal: string; states: string[]; cells: (string | null)[]; references: AttackReference[] }
type Preview = { row: Row; anchor: HTMLElement }
type Result = { columns: string[]; monsters: { id: number; source: string | null; rows: Row[]; warnings: string[] }[];
  revision: { commit?: string } | null }
type Edits = { names: Record<string, string>; removed: string[] }
const keyFor = (id: number, row: Row) => `${id}:${row.id}`
const escapeWiki = (value: string) => value.replace(/[&<>'|[\]{}~\r\n]/g,
  character => /[\r\n]/.test(character) ? ' ' : `&#${character.charCodeAt(0)};`)

function copyFormat(columns: string[], rows: { name: string; cells: (string | null)[] }[], minimal: boolean) {
  const kept = columns.map((_, index) => index).filter(index => !minimal || rows.some(row => row.cells[index] !== null))
  const lines = ['===AI Logic===', '{| class="wikitable"', `! ${['Ability', ...kept.map(index => columns[index])].map(escapeWiki).join(' !! ')}`]
  for (const row of rows)
    lines.push('|-', `| ${[escapeWiki(row.name), ...kept.map(index => {
      const cell = row.cells[index]
      return cell === null ? '&mdash;' : escapeWiki(cell)
    })].join(' || ')}`)
  return [...lines, '|}', ''].join('\n')
}

function AttackPreview({ preview, id, onEnter, onLeave }: {
  preview?: Preview; id: string; onEnter: () => void; onLeave: () => void
}) {
  const popup = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const node = popup.current
    if (!node || !preview) return
    const position = () => {
      const bounds = preview.anchor.getBoundingClientRect()
      const viewport = document.documentElement
      const above = Math.max(0, bounds.top - 8)
      const below = Math.max(0, viewport.clientHeight - bounds.bottom - 8)
      const flip = below < node.scrollHeight && above > below
      const scroller = preview.anchor.closest('.enemy-ai-scroll')?.getBoundingClientRect()
      const start = Math.max(bounds.left, scroller?.left ?? 0)
      node.style.visibility = scroller && (bounds.bottom <= scroller.top || bounds.top >= scroller.bottom) ? 'hidden' : ''
      node.style.left = `${Math.max(8, Math.min(start + 144, viewport.clientWidth - node.offsetWidth - 8))}px`
      node.style.maxHeight = `${flip ? above : below}px`
      node.style.top = flip ? 'auto' : `${bounds.bottom}px`
      node.style.bottom = flip ? `${viewport.clientHeight - bounds.top}px` : 'auto'
    }
    node.showPopover()
    position()
    window.addEventListener('resize', position)
    window.addEventListener('scroll', position, true)
    return () => {
      node.hidePopover()
      window.removeEventListener('resize', position)
      window.removeEventListener('scroll', position, true)
    }
  }, [preview])
  const groups = preview?.row.references.filter(ref => ref.attacks?.length) ?? []
  return <div ref={popup} popover="manual" id={id} role="tooltip" className="enemy-ai-attack-preview"
    onPointerEnter={onEnter} onPointerLeave={onLeave}>
    {!groups.length && <span>No attack preview available.</span>}
    {(['direct', 'traced', 'candidate'] as const).map(confidence => {
      const refs = groups.filter(ref => confidenceOf(ref) === confidence)
      return refs.length > 0 && <div className="enemy-ai-attack-group" key={confidence}>
        <strong>{attackLabels[confidence]}</strong>
        {refs.map(ref => {
          const attacks = ref.attacks ?? []
          return <div className="enemy-ai-attack-source" key={`${ref.path}:${ref.focus}:${ref.section?.join('.') ?? ''}`}>
            <strong>{attacks.some(hit => hit.condition) ? 'Conditional Attack Records'
              : `${attacks.length} ${attacks.length === 1 ? 'Attack Record' : 'Attack Records'}`}</strong>
            {(refs.length > 1 || confidence === 'candidate') && <small>{ref.focus}</small>}
            {attacks.map((hit, hitIndex) => <div key={hitIndex}>
              <span data-element={hit.element || 'Physical'}>{hit.element || 'Physical'}</span>
              {' · '}{hit.percent ?? '?'}
              {hit.condition && <small>{hit.condition}</small>}
            </div>)}
          </div>
        })}
        </div>
    })}
    {!!groups.length && <small>Configured attack records, not runtime hit counts.</small>}
  </div>
}

export function EnemyAITable({ jobId, onDirty }: { jobId: string; onDirty: (dirty: boolean) => void }) {
  const [result, setResult] = useState<Result>()
  const [edits, setEdits] = useState<Edits>({ names: {}, removed: [] })
  const [saved, setSaved] = useState<Edits>(edits)
  const [monsterId, setMonsterId] = useState<number>()
  const [selected, setSelected] = useState<Row>()
  const [renaming, setRenaming] = useState<{ key: string; name: string; original: string }>()
  const [reference, setReference] = useState<AttackReference>()
  const [preview, setPreview] = useState<Preview>()
  const previewId = useId()
  const closeTimer = useRef<number | undefined>(undefined)
  const renameTrigger = useRef<HTMLButtonElement | null>(null)
  const keepPreview = () => window.clearTimeout(closeTimer.current)
  const hidePreview = () => { keepPreview(); setPreview(undefined) }
  const deferHidePreview = () => {
    keepPreview()
    closeTimer.current = window.setTimeout(() => setPreview(undefined), 150)
  }
  const showPreview = (row: Row, anchor: HTMLElement) => {
    keepPreview()
    if (!renaming) setPreview(current => current?.row === row ? current : { row, anchor })
  }
  useEffect(() => () => window.clearTimeout(closeTimer.current), [])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [minimal, setMinimal] = useState(false)
  const [showAllColumns, setShowAllColumns] = useState(false)
  const [copied, setCopied] = useState(false)
  const dirty = saved !== edits
  const hasUnsavedChanges = dirty || Boolean(renaming && renaming.name !== renaming.original)
  const path = `/jobs/${jobId}`

  useEffect(() => {
    const controller = new AbortController()
    const load = (name: string) => api<{ text: string }>(`${path}/preview/${encodeURIComponent(name)}`, { signal: controller.signal })
    Promise.all([load(AI_RESULT), load(EDITS)]).then(([data, editsFile]) => {
      if (controller.signal.aborted) return
      const parsed: Edits = JSON.parse(editsFile.text)
      setEdits(parsed)
      setSaved(parsed)
      setResult(JSON.parse(data.text))
    }).catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
    return () => controller.abort()
  }, [path])
  useEffect(() => { onDirty(hasUnsavedChanges) }, [hasUnsavedChanges, onDirty])
  useEffect(() => {
    if (!hasUnsavedChanges) return
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [hasUnsavedChanges])

  const monster = result?.monsters.find(item => item.id === monsterId) ?? result?.monsters[0]
  const rows = monster?.rows.filter(row => !edits.removed.includes(keyFor(monster.id, row))) ?? []
  const removed = monster?.rows.filter(row => edits.removed.includes(keyFor(monster.id, row))) ?? []
  const columns = result?.columns.flatMap((label, index) => showAllColumns || rows.some(row => row.cells[index] !== null)
    ? [{ label, index }] : []) ?? []
  const rowName = (row: Row) => monster ? edits.names[keyFor(monster.id, row)] ?? row.name : row.name
  const change = (next: Edits) => { setEdits(next); setCopied(false) }
  const finishRename = (apply: boolean) => {
    if (apply && renaming && renaming.name !== renaming.original)
      change({ ...edits, names: { ...edits.names, [renaming.key]: renaming.name } })
    setRenaming(undefined)
    requestAnimationFrame(() => renameTrigger.current?.focus())
  }
  const inspect = (row: Row) => { hidePreview(); setSelected(row); setReference(row.references[0]) }
  const closeDetails = () => { setSelected(undefined); setReference(undefined) }
  const save = async () => {
    setSaving(true); setError('')
    try {
      await api(`${path}/files/${encodeURIComponent(EDITS)}`, {
        method: 'PUT', body: JSON.stringify({ text: JSON.stringify(edits) }),
      })
      setSaved(edits)
    } catch (reason) { setError(`Could not save edits: ${message(reason)}`) }
    finally { setSaving(false) }
  }
  const copy = async () => {
    if (!result) return
    setError(''); setCopied(false)
    try {
      await navigator.clipboard.writeText(copyFormat(result.columns, rows.map(row => ({ ...row, name: rowName(row) })), minimal))
      setCopied(true)
    } catch (reason) { setError(`Could not copy wikitext: ${message(reason)}`) }
  }
  return <section className="enemy-ai-result" aria-label="Enemy AI Logic Table" onKeyDown={event => {
    if (event.key === 'Escape' && preview) {
      event.preventDefault()
      event.stopPropagation()
      hidePreview()
    }
  }}>
    {error && <div className="error-box" role="alert">{error}</div>}
    {!result || !monster ? !error && <p role="status">Loading AI Logic…</p> : <>
      <div className={`enemy-ai-workspace${selected ? ' with-skill' : ''}`}>
        <div className="enemy-ai-editor">
      <header className="enemy-ai-actions">
        <div className="enemy-ai-controls">
          <label>Monster <select value={monster.id} disabled={!!renaming} onChange={event => {
            setMonsterId(Number(event.target.value)); closeDetails(); hidePreview(); setCopied(false)
          }}>{result.monsters.map(item => <option key={item.id} value={item.id}>{item.source
            ? `${item.source.split('/').pop()?.replace(new RegExp(`_${item.id}\\.json$`), '').replace(/\.json$/, '')} · ${item.id}` : item.id}</option>)}</select></label>
        </div>
        <div className="enemy-ai-controls">
          <span className={hasUnsavedChanges ? 'enemy-ai-unsaved' : 'muted'} role="status">{saving ? 'Saving…' : hasUnsavedChanges ? 'Unsaved edits' : 'Edits saved'}</span>
          <button className="button secondary small" disabled={!dirty || saving || !!renaming} onClick={() => { void save() }}><Save size={14} /> Save Edits</button>
          <label className="enemy-ai-minimal"><input type="checkbox" checked={minimal} onChange={event => { setMinimal(event.target.checked); setCopied(false) }} /> Minimal Wikitext</label>
          <button className="button primary small" disabled={!rows.length || !!renaming} onClick={() => { void copy() }}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy Wikitext'}</button>
        </div>
      </header>
      {renaming && <form className="enemy-ai-rename-form" onSubmit={event => { event.preventDefault(); finishRename(true) }}
        onKeyDown={event => {
          if (event.key !== 'Escape' || event.nativeEvent.isComposing) return
          event.preventDefault()
          event.stopPropagation()
          finishRename(false)
        }}>
        <label>Ability Name<input autoFocus maxLength={200} value={renaming.name}
          onFocus={event => event.currentTarget.select()}
          onKeyDown={event => {
            if (event.key !== 'Enter' || event.nativeEvent.isComposing) return
            event.preventDefault()
            finishRename(true)
          }}
          onChange={event => setRenaming({ ...renaming, name: event.target.value })} /></label>
        <div>
          <button type="button" className="button secondary small" onClick={() => finishRename(false)}>Cancel</button>
          <button type="submit" className="button primary small"><Check size={14} /> Apply Name</button>
        </div>
      </form>}
        <section className="enemy-ai-sheet" aria-label="Abilities">
          <div className="enemy-ai-sheet-bar">
            <span>{rows.length} {rows.length === 1 ? 'ability' : 'abilities'}</span>
            <label><input type="checkbox" checked={showAllColumns} onChange={event => setShowAllColumns(event.target.checked)} /> Show Empty Columns</label>
          </div>
          {rows.length ? <div className="enemy-ai-scroll" tabIndex={0} role="region" aria-label="Ability Table">
            <table className="enemy-ai-table">
              <thead><tr><th scope="col">Ability</th>{columns.map(({ label }) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
              <tbody>{rows.map(row => {
                const key = keyFor(monster.id, row)
                return <tr key={key} className={selected === row ? 'selected' : undefined}
                  onPointerEnter={event => { if (event.pointerType === 'mouse') showPreview(row, event.currentTarget) }}
                  onPointerLeave={deferHidePreview}>
                  <th scope="row"><div className="enemy-ai-row-name">
                    <button className="enemy-ai-ability" aria-label={`Inspect ${rowName(row) || row.name}`} aria-pressed={selected === row}
                      aria-describedby={preview?.row === row ? previewId : undefined} disabled={!!renaming}
                      onFocus={event => {
                        const anchor = event.currentTarget.closest('tr')
                        if (anchor && event.currentTarget.matches(':focus-visible')) showPreview(row, anchor)
                      }}
                      onBlur={hidePreview}
                      onClick={() => inspect(row)}>{rowName(row) || '(Unnamed ability)'} <ArrowUpRight size={13} aria-hidden="true" /></button>
                    <button className="icon-button enemy-ai-rename" title="Rename Ability" aria-label={`Rename ${rowName(row) || row.name}`}
                      disabled={!!renaming} onClick={event => {
                        renameTrigger.current = event.currentTarget
                        hidePreview()
                        setRenaming({ key, name: rowName(row), original: rowName(row) })
                      }}><Pencil size={13} /></button>
                  </div></th>
                  {columns.map(({ index }) => <td key={index} className={row.cells[index] === null ? 'empty-cell' : row.cells[index] === '?' ? 'unknown-cell' : undefined}>{row.cells[index] ?? '—'}</td>)}
                </tr>
              })}</tbody>
            </table>
          </div> : <p className="enemy-ai-empty">{monster.rows.length ? 'All rows have been removed.' : 'No supported AI Logic rows for this monster.'}</p>}
          {removed.length > 0 && <details className="enemy-ai-removed">
            <summary>Removed Rows ({removed.length})</summary>
            {removed.map(row => <div key={row.id}><button className="text-button" onClick={() => change({
              ...edits, removed: edits.removed.filter(id => id !== keyFor(monster.id, row)),
            })}><Undo2 size={13} /> Restore {rowName(row) || row.name}</button></div>)}
          </details>}
        </section>
        <details className="enemy-ai-diagnostics">
          <summary>Source and Diagnostics</summary>
          <p>{monster.source ?? 'No exact source file'}{result.revision?.commit && ` · ${result.revision.commit.slice(0, 8)}`}</p>
          {monster.warnings.length > 0 && <ul>{monster.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
          <p>“?” means unresolved; “—” means not applicable. Initial cooldowns, phase conditions, and action interval flags are not inferred.</p>
        </details>
        </div>
        {selected && <aside className="enemy-ai-details reference-panel" aria-label="Skill Details">
          <div className="enemy-ai-inspector-controls">
          <div className="enemy-ai-inspector-heading">
            <div><span className="muted">Skill Details</span><h3>{rowName(selected) || selected.name}</h3></div>
            <button className="icon-button" title="Close Skill Details" aria-label="Close Skill Details" onClick={closeDetails}><X size={17} /></button>
          </div>
          <div className="enemy-ai-inspector-meta">
            <span>Skill ID <code>{selected.id}</code></span>
            {selected.internal && <span>Internal Name <code>{selected.internal}</code></span>}
            <button className="text-button enemy-ai-remove" disabled={!!renaming} onClick={() => {
              change({ ...edits, removed: [...edits.removed, keyFor(monster.id, selected)] }); closeDetails(); hidePreview()
            }}><Trash2 size={13} /> Remove Row</button>
          </div>
          {selected.states.length > 0 && <details className="enemy-ai-states"><summary>Execution States</summary><p>{selected.states.join(', ')}</p></details>}
          {selected.references.length > 0 && <label className="enemy-ai-reference-picker">BinOutput Reference
            <select value={reference ? selected.references.indexOf(reference) : ''}
              onChange={event => setReference(selected.references[Number(event.target.value)])}>
              {selected.references.map((target, index) => <option key={`${target.path}:${target.focus}:${index}`} value={index}>
                {target.focus} · {target.kind}{target.attackInfo ? ` · ${attackLabels[confidenceOf(target)]}` : ''}
              </option>)}
            </select>
          </label>}
          {!!reference?.evidence?.length && <details className="enemy-ai-states">
            <summary>Reference Evidence</summary>
            <ol>{reference.evidence.map(step => <li key={step}>{step}</li>)}</ol>
          </details>}
          </div>
          {reference ? <SkillReferenceViewer reference={reference} /> : <p className="enemy-ai-empty">No BinOutput reference for this ability.</p>}
        </aside>}
      </div>
      <AttackPreview preview={preview} id={previewId} onEnter={keepPreview} onLeave={deferHidePreview} />
    </>}
  </section>
}
