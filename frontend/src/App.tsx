import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronRight, CircleAlert, Clock3, Copy, Database,
  FileText, FolderOpen, Languages, LayoutGrid, Link2, LoaderCircle, Play, Search, Sparkles, Terminal,
  WandSparkles, X,
} from 'lucide-react'
import type { Artifact, Character, Dataset, Job, Parameters, Property, Tool } from './api'
import { api, fileUrl, message } from './api'

const icons: Record<string, typeof Languages> = { 'other-languages': Languages, 'character-kit': WandSparkles, redirects: Link2 }
const advanced = new Set(['natlan', 'nodkrai', 'hexerei', 'stellar', 'traveler', 'skill_depot'])
const active = (job: Job) => job.status === 'queued' || job.status === 'running'
const size = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
const time = (date: string) => new Date(date).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
// Apply carriage returns like a terminal so redrawn progress bars show only their latest state.
const terminal = (text: string) => text.replace(/\r\n/g, '\n').split('\n')
  .map(line => line.split('\r').filter(Boolean).pop() ?? '').join('\n')

function Status({ status }: { status: Job['status'] }) {
  return <span className={`status ${status}`}>
    {status === 'running' ? <LoaderCircle size={12} className="spin" /> : <span className="status-dot" />}
    {status === 'succeeded' ? 'Completed' : status.charAt(0).toUpperCase() + status.slice(1)}
  </span>
}

function Dialog({ title, subtitle, children, onClose, wide = false }: {
  title: string; subtitle?: string; children: ReactNode; onClose: () => void; wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])
  return <dialog ref={ref} className={wide ? 'dialog wide' : 'dialog'} onCancel={onClose}
    onClick={event => { if (event.target === event.currentTarget) onClose() }} aria-label={title}>
    <header className="dialog-header"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
      <button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={20} /></button>
    </header>
    {children}
  </dialog>
}

function ToolForm({ tool, characters, characterError, submitting, error, onSubmit, onClose }: {
  tool: Tool; characters: Character[]; characterError: string; submitting: boolean; error: string
  onSubmit: (parameters: Parameters) => void; onClose: () => void
}) {
  const [values, setValues] = useState<Parameters>(() => Object.fromEntries(
    Object.entries(tool.schema.properties).map(([key, property]) => [key, property.default ?? '']),
  ))
  const [characterSearch, setCharacterSearch] = useState('')
  const update = (key: string, value: Parameters[string]) => setValues(previous => ({ ...previous, [key]: value }))
  const field = (key: string, property: Property) => {
    const type = property.type ?? property.anyOf?.find(item => item.type !== 'null')?.type
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
      </> : property.enum ? <select id={key} required={required} value={String(values[key] ?? '')}
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
    </div>
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit(Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== '' || tool.schema.required?.includes(key))))
  }
  const fields = Object.entries(tool.schema.properties)
  return <Dialog title={tool.name} subtitle={tool.description} onClose={onClose}>
    <form onSubmit={submit}>
      <div className="dialog-body form-fields">
        {fields.filter(([key]) => !advanced.has(key)).map(([key, property]) => field(key, property))}
        {fields.some(([key]) => advanced.has(key)) && <details className="advanced">
          <summary>Advanced options</summary>
          <div className="form-fields">{fields.filter(([key]) => advanced.has(key)).map(([key, property]) => field(key, property))}</div>
        </details>}
        {error && <div className="error-box" role="alert"><CircleAlert size={18} />{error}</div>}
      </div>
      <footer className="dialog-footer"><button type="button" className="button secondary" onClick={onClose}>Cancel</button>
        <button className="button primary" disabled={submitting || (tool.id === 'character-kit' && characters.length === 0)}>
          {submitting ? <LoaderCircle size={16} className="spin" /> : <Play size={15} />} Run
        </button>
      </footer>
    </form>
  </Dialog>
}

function FilePreview({ jobId, file }: { jobId: string; file: Artifact }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(file.kind === 'text')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const { path, kind } = file
  useEffect(() => {
    if (kind !== 'text') return
    const controller = new AbortController()
    api<{ text: string }>(`/jobs/${jobId}/preview/${encodeURIComponent(path)}`, { signal: controller.signal })
      .then(result => setText(result.text))
      .catch(reason => { if (!controller.signal.aborted) setError(message(reason)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [jobId, path, kind])
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true) }
    catch (reason) { setError(`Could not copy: ${message(reason)}`) }
  }
  return <div className="preview-panel">
    <div className="preview-header"><span title={path}>{path.split('/').pop()}</span><div>
      {kind === 'text' && text && <button className="icon-button" onClick={() => { void copy() }} aria-label="Copy output">{copied ? <Check size={16} /> : <Copy size={16} />}</button>}
      <a className="icon-button" href={fileUrl(jobId, path)} aria-label="Download file"><ArrowDownToLine size={17} /></a>
    </div></div>
    {error && <div className="error-box" role="alert">{error}</div>}
    {loading ? <div className="empty"><LoaderCircle className="spin" />Loading preview...</div> :
      kind === 'image' ? <div className="image-preview"><img src={`${fileUrl(jobId, path)}?inline=true`} alt={path} /></div> :
        kind === 'text' ? <pre className="text-preview">{text}</pre> :
          <div className="empty"><ArrowDownToLine /><p>No preview available. Download to open.</p></div>}
  </div>
}

function JobDialog({ job, onClose }: { job: Job; onClose: () => void }) {
  const [tab, setTab] = useState<'output' | 'logs'>(job.status === 'failed' || active(job) ? 'logs' : 'output')
  const [logs, setLogs] = useState('')
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Artifact | null>(null)
  const selectedFile = job.files.find(file => file.path === selected?.path) ?? job.files[0] ?? null
  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        const result = await api<{ text: string; truncated: boolean }>(`/jobs/${job.id}/logs`, { signal: controller.signal })
        setLogs((result.truncated ? '[Showing the most recent log output]\n' : '') + terminal(result.text))
        setError('')
      } catch (reason) { if (!controller.signal.aborted) setError(message(reason)) }
    }
    void load()
    const timer = setInterval(() => { void load() }, 2000)
    return () => { controller.abort(); clearInterval(timer) }
  }, [job.id])
  return <Dialog wide title={job.name} subtitle={`${time(job.created_at)} · ${job.id.slice(0, 8)}`} onClose={onClose}>
    <div className="job-dialog-summary"><Status status={job.status} />
      {!active(job) && <span>{job.files.length} {job.files.length === 1 ? 'file' : 'files'}</span>}
      {job.files.length > 0 && !active(job) && <a className="button secondary small" href={`/api/jobs/${job.id}/archive`}><ArrowDownToLine size={15} /> Download ZIP</a>}
    </div>
    {job.error && <div className="job-error error-box" role="alert"><CircleAlert size={18} />{job.error} {job.files.length > 0 && 'Files below may be incomplete.'}</div>}
    <div className="detail-tabs">
      <button className={tab === 'output' ? 'selected' : ''} onClick={() => setTab('output')}><FolderOpen size={16} /> Output <span>{job.files.length}</span></button>
      <button className={tab === 'logs' ? 'selected' : ''} onClick={() => setTab('logs')}><Terminal size={16} /> Log</button>
    </div>
    {error && <div className="job-error error-box" role="alert">{error}</div>}
    {tab === 'logs' ? <pre className="log-view">{logs || (job.status === 'queued' ? 'Queued.' : 'No log output.')}</pre> :
      job.files.length === 0 ? <div className="empty"><FolderOpen size={32} /><p>{active(job) ? 'Files appear when the job finishes.' : 'No output files.'}</p></div> :
      <div className="output-layout">
        <div className="file-list">{job.files.map(file => <button key={file.path}
          className={file.path === selectedFile?.path ? 'selected' : ''} onClick={() => setSelected(file)}>
          <FileText size={16} /><span title={file.path}>{file.path}<small>{size(file.size)}</small></span>
        </button>)}</div>
        {selectedFile && <FilePreview key={selectedFile.path} jobId={job.id} file={selectedFile} />}
      </div>}
  </Dialog>
}

function JobTable({ jobs, onSelect }: { jobs: Job[]; onSelect: (id: string) => void }) {
  if (!jobs.length) return <div className="empty"><Clock3 size={28} /><p>No jobs yet.</p></div>
  return <div className="table-scroll"><table className="jobs-table"><thead><tr><th>Tool</th><th>Status</th><th>Created</th><th>Files</th><th><span className="sr-only">Open</span></th></tr></thead>
    <tbody>{jobs.map(job => <tr key={job.id} onClick={() => onSelect(job.id)}>
      <td><button className="job-name" onClick={event => { event.stopPropagation(); onSelect(job.id) }}><span className="job-glyph"><FileText size={17} /></span><span>{job.name}<small>{job.id.slice(0, 8)}</small></span></button></td>
      <td><Status status={job.status} /></td><td className="muted">{time(job.created_at)}</td><td className="muted">{job.files.length}</td><td><ChevronRight size={16} /></td>
    </tr>)}</tbody></table></div>
}

function App() {
  const [page, setPage] = useState<'tools' | 'jobs' | 'dataset'>('tools')
  const [tools, setTools] = useState<Tool[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
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
  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const [nextJobs, nextDataset, nextTools] = await Promise.all([
        api<Job[]>('/jobs', { signal }), api<Dataset>('/dataset', { signal }), api<Tool[]>('/tools', { signal }),
      ])
      setJobs(nextJobs); setDataset(nextDataset); setTools(nextTools); setNetworkError('')
    } catch (reason) { if (!signal?.aborted) setNetworkError(message(reason)) }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    const initial = setTimeout(() => { void refresh(controller.signal) }, 0)
    const timer = setInterval(() => { void refresh(controller.signal) }, 2000)
    return () => { controller.abort(); clearTimeout(initial); clearInterval(timer) }
  }, [refresh])
  useEffect(() => {
    if (selectedTool?.id !== 'character-kit') return
    const controller = new AbortController()
    api<Character[]>('/characters', { signal: controller.signal }).then(setCharacters)
      .catch(reason => { if (!controller.signal.aborted) setCharacterError(message(reason)) })
    return () => controller.abort()
  }, [selectedTool?.id])
  const run = async (parameters: Parameters) => {
    if (!selectedTool) return
    setSubmitting(true); setFormError('')
    try {
      const job = await api<Job>('/jobs', { method: 'POST', body: JSON.stringify({ tool_id: selectedTool.id, parameters }) })
      setSelectedTool(null); setSelectedJob(job.id); setJobs(previous => [job, ...previous]); void refresh()
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
  const openTool = (tool: Tool) => {
    setFormError('')
    if (tool.id === 'character-kit') { setCharacterError(''); setCharacters([]) }
    setSelectedTool(tool)
  }
  const currentJob = jobs.find(job => job.id === selectedJob)
  const activeJobs = jobs.filter(active)
  const setupRunning = activeJobs.some(job => job.tool_id === 'dataset-setup')
  const categories = ['All', ...new Set(tools.map(tool => tool.category))]
  const filtered = tools.filter(tool => (category === 'All' || tool.category === category) &&
    `${tool.name} ${tool.description}`.toLowerCase().includes(search.toLowerCase()))
  return <div className="workspace">
    <aside className="sidebar">
      <a className="brand" href="/"><span className="brand-mark"><Sparkles size={22} /></span><span>Wiki Tools<small>GENSHIN IMPACT</small></span></a>
      <nav aria-label="Main navigation">
        <button className={page === 'tools' ? 'active' : ''} onClick={() => setPage('tools')}><LayoutGrid size={18} /> Tools <span>{tools.length}</span></button>
        <button className={page === 'jobs' ? 'active' : ''} onClick={() => setPage('jobs')}><Clock3 size={18} /> Jobs {activeJobs.length > 0 && <span>{activeJobs.length}</span>}</button>
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
        {page === 'tools' && <>
          <section className="library-section">
            <div className="section-heading"><h1>Tools</h1><label className="search"><Search size={17} /><input aria-label="Search tools" placeholder="Search tools..." value={search} onChange={event => setSearch(event.target.value)} /></label></div>
            <div className="filters" aria-label="Tool categories">{categories.map(item => <button key={item} className={category === item ? 'selected' : ''} onClick={() => setCategory(item)}>{item}</button>)}</div>
            <div className="tool-grid">{filtered.map(tool => {
              const Icon = icons[tool.id] ?? BookOpen
              const disabled = tool.requires_dataset && !dataset?.ready
              return <article className={`tool-card ${tool.id}`} key={tool.id}>
                <div className="tool-card-top"><span className="tool-icon"><Icon size={25} strokeWidth={1.6} /></span><span className="category-label">{tool.category}</span></div>
                <h3>{tool.name}</h3><p>{tool.description}</p>
                <div className="tool-card-footer">
                  {disabled ? <button className="setup-required" onClick={() => setPage('dataset')}>Requires dataset setup <ChevronRight size={12} /></button> : <span />}
                  <button className="open-button" aria-label={`Open ${tool.name}`} disabled={disabled} onClick={() => openTool(tool)}><ArrowRight size={18} /></button>
                </div>
              </article>
            })}</div>
            {tools.length === 0 && !networkError && <div className="empty"><LoaderCircle className="spin" /><p>Loading tools...</p></div>}
            {tools.length > 0 && filtered.length === 0 && <div className="empty"><Search /><p>No matching tools.</p></div>}
          </section>
          <section className="panel"><div className="panel-heading"><h2>Recent jobs</h2><button className="text-button" onClick={() => setPage('jobs')}>View all <ArrowRight size={15} /></button></div><JobTable jobs={jobs.slice(0, 5)} onSelect={setSelectedJob} /></section>
        </>}
        {page === 'jobs' && <>
          <div className="section-heading page-title"><h1>Jobs</h1></div>
          <div className="panel"><div className="panel-heading"><h2>All jobs <span className="count">{jobs.length}</span></h2><span className="subtle">{activeJobs.length} active · runs one at a time</span></div><JobTable jobs={jobs} onSelect={setSelectedJob} /></div>
        </>}
        {page === 'dataset' && <>
          <div className="section-heading page-title"><h1>Dataset</h1></div>
          <section className="panel dataset-panel">
            <div className="dataset-title"><span className="stat-icon"><Database size={22} /></span><div><h2>{dataset?.source === 'github' ? 'AnimeGameData' : 'Local game data'}</h2><p>{dataset?.source === 'github' ? 'github.com/DimbreathBot/AnimeGameData · main' : 'Configured RepoPath'}</p></div><span className={`status ${dataset?.ready ? 'succeeded' : 'queued'}`}><span className="status-dot" />{dataset?.ready ? 'Prepared' : 'Not prepared'}</span></div>
            {dataset?.error && <div className="error-box"><CircleAlert size={18} />{dataset.error}</div>}
            <div className="dataset-metrics"><div><strong>{dataset?.tables.toLocaleString() ?? '0'}</strong><span>Mapped tables</span></div><div><strong>{dataset?.languages ?? 0}</strong><span>TextMap languages</span></div><div><strong>{dataset?.commit?.slice(0, 8) ?? '—'}</strong><span>Revision</span></div></div>
            <div className="dataset-path"><span>PATH</span><code>{dataset?.path ?? 'No prepared dataset.'}</code></div>
            <footer><p>{dataset?.source === 'github' ? 'Failed updates keep the current revision active.' : 'Setup rewrites the local dataset in place.'}</p><button className="button primary" disabled={setupRunning || !dataset?.source} onClick={() => { setActionError(''); setConfirmSetup(true) }}>{setupRunning ? <LoaderCircle className="spin" size={16} /> : <ArrowDownToLine size={16} />}{setupRunning ? 'Setup running' : dataset?.ready ? 'Check for updates' : 'Run setup'}</button></footer>
          </section>
        </>}
      </main>
    </div>
    {selectedTool && <ToolForm key={selectedTool.id} tool={selectedTool} characters={characters} characterError={characterError} submitting={submitting} error={formError} onSubmit={parameters => { void run(parameters) }} onClose={() => setSelectedTool(null)} />}
    {currentJob && <JobDialog key={currentJob.id} job={currentJob} onClose={() => setSelectedJob(null)} />}
    {confirmSetup && <Dialog title="Run dataset setup?" onClose={() => setConfirmSetup(false)}>
      <div className="dialog-body"><div className="notice"><Database size={18} /><p>{dataset?.source === 'github' ? 'Checks GitHub main for a new revision and prepares it. A new revision downloads several GB and takes a few minutes; unchanged revisions are reused.' : 'Rewrites TextMaps and mapped tables in the configured dataset. Back up the input data first.'}</p></div>{actionError && <div className="error-box" role="alert">{actionError}</div>}</div>
      <footer className="dialog-footer"><button className="button secondary" onClick={() => setConfirmSetup(false)}>Cancel</button><button className="button primary" disabled={submitting} onClick={() => { void setup() }}>{submitting ? <LoaderCircle className="spin" size={16} /> : <Play size={15} />} Run setup</button></footer>
    </Dialog>}
  </div>
}

export default App
