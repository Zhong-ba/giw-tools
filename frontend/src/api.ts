import { useEffect, useState } from 'react'

export type Parameters = Record<string, string | number | boolean | null | number[] | string[]>
export interface Property {
  type?: string
  title: string
  description?: string
  default?: Parameters[string]
  enum?: string[]
  anyOf?: { type: string }[]
  minimum?: number
  maximum?: number
  maxLength?: number
  // A list of dated periods (Spiral Abyss rotations, Stygian Onslaught events) to pick from, served at /api/periods/<name>.
  periods?: string
}
export interface Period { value: string; label: string; name?: string }
export interface Tool {
  id: string
  name: string
  category: string
  description: string
  requires_dataset: boolean
  schema: { properties: Record<string, Property>; required?: string[] }
}
export interface Artifact { path: string; size: number; kind: 'text' | 'image' | 'file'; file_page?: string | null }
export interface Job {
  id: string
  tool_id: string
  name: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null
  files: Artifact[]
  parameters?: Parameters
}
export interface Dataset {
  source: string | null
  ready: boolean
  path: string | null
  commit: string | null
  tables: number
  languages: number
  error: string | null
  excel_source: string | null
  binoutput_source: string | null
  binoutput_path: string | null
  binoutput_commit: string | null
  excel_revision: string
  binoutput_revision: string
  excel_title: string | null
  binoutput_title: string | null
  sources: Record<string, string>
}
export interface Revision { commit: string; title: string; date: string; downloaded: boolean }
export interface Character { id: number; name: string; skill_depot: number | null }
export interface PickerItem { id: number; name: string; internal: string }
export interface LanguageResult { textmap_hash: string; text: string }
export interface Versions { options: { value: string; label: string; version: string | null }[]; older: string | null; newer: string }
export interface BotSettings {
  wiki: string
  username: string
  remember: boolean
  summary: string
  skip_existing: boolean
  skip_unchanged: boolean
  bot_edit: boolean
  watch: boolean
  protect: boolean
}
export interface QueueEntry {
  id: string
  kind: 'page' | 'file'
  title: string | null
  source: string
  job_id: string | null
  path: string | null
  status: 'pending' | 'posting' | 'posted' | 'skipped' | 'failed'
  message: string | null
  added_at: string
  posted_at: string | null
  size: number
}
export interface QueueItem extends QueueEntry { content: string }
export interface BotState {
  settings: BotSettings
  has_password: boolean
  running: boolean
  stopping: boolean
  log: string[]
  items: QueueEntry[]
}

export interface ServerConfig { hosted: boolean; working_directory: string | null; default_working_directory: string | null }
export interface PreparedRevision { source: string; commit: string; title: string | null; active: boolean }
export interface PreparedDatasets { excel: PreparedRevision[]; binoutput: PreparedRevision[] }

export function message(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

export class ApiError extends Error {
  status: number
  constructor(text: string, status: number) { super(text); this.status = status }
}

function errorDetail(body: unknown): string {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return 'The request could not be completed.'
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item: unknown) =>
    typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : 'Invalid input.',
  ).join(' ')
  return 'The request could not be completed.'
}

// The backend that runs the tools; empty when it also serves this page.
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')
const CLIENT_KEY = 'painmelo.client'
const DATASET_KEY = 'painmelo.dataset'
let config: ServerConfig | null = null
let loading: Promise<ServerConfig> | null = null

/** On a hosted site this browser keeps its own jobs and bot queue; the server only runs tools. */
export const hosted = () => config?.hosted ?? false

export function serverConfig(refresh = false): Promise<ServerConfig> {
  if (!loading || refresh) loading = fetch(`${BASE}/api/config`).then(async response => {
    if (!response.ok) throw new Error(`Could not reach the Painmelo server (${response.status}).`)
    config = await response.json() as ServerConfig
    return config
  }).catch((reason: unknown) => { loading = null; throw reason })
  return loading
}

function clientId(): string {
  let id = localStorage.getItem(CLIENT_KEY)
  if (!id) { id = crypto.randomUUID(); localStorage.setItem(CLIENT_KEY, id) }
  return id
}

/** The server's prepared dataset this browser uses, as "<Excel commit>.<BinOutput commit>". */
export const datasetChoice = () => localStorage.getItem(DATASET_KEY)
export function setDatasetChoice(value: string | null) {
  if (value) localStorage.setItem(DATASET_KEY, value)
  else localStorage.removeItem(DATASET_KEY)
}

/** A request to the Painmelo server itself. */
export async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const settings = await serverConfig()
  const headers: Record<string, string> = options.body && typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}
  if (settings.hosted) {
    headers['X-Client-Id'] = clientId()
    const choice = datasetChoice()
    if (choice) headers['X-Dataset'] = choice
  }
  const response = await fetch(`${BASE}/api${path}`, { ...options, headers: { ...headers, ...options.headers as Record<string, string> } })
  if (!response.ok) {
    const type = response.headers.get('content-type') ?? ''
    throw new ApiError(type.includes('application/json') ? errorDetail(await response.json()) : `Server returned ${response.status}.`, response.status)
  }
  return response
}

export async function server<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await request(path, options)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  if ((await serverConfig()).hosted && /^\/(jobs|bot)(?=[/?]|$)/.test(path)) {
    const local = await import('./local')
    return local.handle<T>(path, options)
  }
  return server<T>(path, options)
}

const encodePath = (path: string) => path.split('/').map(encodeURIComponent).join('/')
export const fileUrl = (job: string, path: string) => `${BASE}/api/jobs/${job}/files/${encodePath(path)}`

/** A URL for a job file or queued media: the server's, or on a hosted site an object URL of the browser's copy. */
export function useAssetUrl(kind: 'file' | 'media', id: string, path = '', version = 0): string | null {
  const key = `${kind}:${id}/${path}#${version}`
  const [loaded, setLoaded] = useState<{ key: string; url: string } | null>(null)
  const local = hosted()
  useEffect(() => {
    if (!local) return
    let created: string | null = null
    let cancelled = false
    void import('./local').then(store => kind === 'file' ? store.jobFile(id, path) : store.mediaFile(id)).then(blob => {
      if (cancelled) return
      created = URL.createObjectURL(blob)
      setLoaded({ key, url: created })
    }).catch(() => undefined)
    return () => { cancelled = true; if (created) URL.revokeObjectURL(created) }
  }, [local, key, kind, id, path])
  if (!local) return kind === 'file' ? fileUrl(id, path) : `${BASE}/api/bot/queue/${id}/media`
  return loaded?.key === key ? loaded.url : null
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}

export async function downloadArchive(job: Job) {
  if (!hosted()) {
    window.location.href = `${BASE}/api/jobs/${job.id}/archive`
    return
  }
  const [{ zip }, store] = await Promise.all([import('fflate'), import('./local')])
  const entries: Record<string, Uint8Array> = {}
  for (const file of job.files) entries[file.path] = new Uint8Array(await (await store.jobFile(job.id, file.path)).arrayBuffer())
  const data = await new Promise<Uint8Array>((resolve, reject) => zip(entries, (error, result) => error ? reject(error) : resolve(result)))
  saveBlob(new Blob([data as BlobPart], { type: 'application/zip' }), `${job.tool_id}-${job.id.slice(0, 8)}.zip`)
}
