/* On a hosted site the server only runs tools. This browser keeps everything else: finished jobs
   (copied from the server, which then deletes them), the bot queue and the bot login, in a folder the
   user picks (File System Access API) or else in IndexedDB. Responses mirror the local server's API. */
import { ApiError, request, server } from './api'
import type { Artifact, BotSettings, BotState, Job, QueueEntry, QueueItem } from './api'

interface Disk {
  read(path: string): Promise<Blob | null>
  write(path: string, data: Blob | string): Promise<void>
  remove(path: string): Promise<void>
  list(directory: string): Promise<string[]>
}

// The parts of the File System Access API that TypeScript's DOM types do not include yet.
type Permission = 'granted' | 'denied' | 'prompt'
interface FolderHandle extends FileSystemDirectoryHandle {
  queryPermission(options: { mode: 'readwrite' }): Promise<Permission>
  requestPermission(options: { mode: 'readwrite' }): Promise<Permission>
  keys(): AsyncIterableIterator<string>
}
type FolderPicker = (options: { id?: string; mode: 'readwrite' }) => Promise<FolderHandle>
const picker = () => (window as unknown as { showDirectoryPicker?: FolderPicker }).showDirectoryPicker

function idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open('painmelo', 1)
    open.onupgradeneeded = () => { open.result.createObjectStore('files'); open.result.createObjectStore('handles') }
    open.onsuccess = () => resolve(open.result)
    open.onerror = () => reject(open.error ?? new Error('Could not open browser storage.'))
  })
}
let database: Promise<IDBDatabase> | null = null
async function transact<T>(store: string, mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  database ??= idb()
  const transaction = (await database).transaction(store, mode)
  const result = work(transaction.objectStore(store))
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve(result.result)
    transaction.onerror = transaction.onabort = () => reject(transaction.error ?? new Error('Browser storage failed.'))
  })
}

class BrowserDisk implements Disk {
  async read(path: string) { return (await transact<Blob | undefined>('files', 'readonly', store => store.get(path) as IDBRequest<Blob | undefined>)) ?? null }
  async write(path: string, data: Blob | string) {
    const blob = typeof data === 'string' ? new Blob([data], { type: 'text/plain' }) : data
    await transact('files', 'readwrite', store => store.put(blob, path))
  }
  async remove(path: string) {
    await transact('files', 'readwrite', store => store.delete(IDBKeyRange.bound(`${path}/`, `${path}/\uffff`)))
    await transact('files', 'readwrite', store => store.delete(path))
  }
  async list(directory: string) {
    const keys = await transact('files', 'readonly', store => store.getAllKeys(IDBKeyRange.bound(`${directory}/`, `${directory}/\uffff`)))
    return [...new Set(keys.map(key => String(key).slice(directory.length + 1).split('/')[0]))]
  }
}

class FolderDisk implements Disk {
  root: FolderHandle
  constructor(root: FolderHandle) { this.root = root }
  private async folder(parts: string[], create: boolean): Promise<FolderHandle | null> {
    let folder = this.root
    for (const part of parts) {
      try { folder = await folder.getDirectoryHandle(part, { create }) as FolderHandle }
      catch (reason) { if (!create && reason instanceof DOMException && reason.name === 'NotFoundError') return null; throw reason }
    }
    return folder
  }
  async read(path: string) {
    const parts = path.split('/')
    const folder = await this.folder(parts.slice(0, -1), false)
    try { return folder ? await (await folder.getFileHandle(parts[parts.length - 1])).getFile() : null }
    catch (reason) { if (reason instanceof DOMException && reason.name === 'NotFoundError') return null; throw reason }
  }
  async write(path: string, data: Blob | string) {
    const parts = path.split('/')
    const folder = await this.folder(parts.slice(0, -1), true)
    const writable = await (await folder!.getFileHandle(parts[parts.length - 1], { create: true })).createWritable()
    await writable.write(data)
    await writable.close()
  }
  async remove(path: string) {
    const parts = path.split('/')
    const folder = await this.folder(parts.slice(0, -1), false)
    try { await folder?.removeEntry(parts[parts.length - 1], { recursive: true }) }
    catch (reason) { if (!(reason instanceof DOMException && reason.name === 'NotFoundError')) throw reason }
  }
  async list(directory: string) {
    const folder = await this.folder(directory.split('/'), false)
    const names: string[] = []
    if (folder) for await (const name of folder.keys()) names.push(name)
    return names
  }
}

export interface StorageInfo {
  kind: 'browser' | 'folder'
  folder: string | null
  // The folder needs permission again after a reload; only a click can grant it.
  needsPermission: boolean
  supported: boolean
}

let disk: Disk | null = null
let info: StorageInfo = { kind: 'browser', folder: null, needsPermission: false, supported: false }
let opening: Promise<void> | null = null
const listeners = new Set<() => void>()
const changed = () => { for (const listener of listeners) listener() }

export function onStorageChange(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

async function open() {
  const handle = await transact<FolderHandle | undefined>('handles', 'readonly', store => store.get('workdir') as IDBRequest<FolderHandle | undefined>)
  info = { kind: handle ? 'folder' : 'browser', folder: handle?.name ?? null, needsPermission: false, supported: !!picker() }
  if (handle && await handle.queryPermission({ mode: 'readwrite' }) !== 'granted') {
    info.needsPermission = true
    disk = null
  } else disk = handle ? new FolderDisk(handle) : new BrowserDisk()
  jobs = null; bot = null
  changed()
}

async function ready(): Promise<Disk | null> {
  opening ??= open()
  await opening
  return disk
}
async function need(): Promise<Disk> {
  const found = await ready()
  if (!found) throw new Error(`Reconnect the working folder "${info.folder}" first.`)
  return found
}

export async function storage(): Promise<StorageInfo> {
  await ready()
  return { ...info }
}

function idle() {
  if (bot?.running) throw new Error('Wait for posting to finish before changing the working directory.')
}

/** Asks for a folder to keep jobs and the bot queue in. Existing files in the old location stay there. */
export async function chooseFolder() {
  const show = picker()
  if (!show) throw new Error('This browser cannot use folders. Jobs are kept in browser storage instead.')
  idle()
  const handle = await show({ id: 'painmelo', mode: 'readwrite' })
  await transact('handles', 'readwrite', store => store.put(handle, 'workdir'))
  opening = open()
  await opening
}

export async function reconnectFolder() {
  const handle = await transact<FolderHandle | undefined>('handles', 'readonly', store => store.get('workdir') as IDBRequest<FolderHandle | undefined>)
  if (handle && await handle.requestPermission({ mode: 'readwrite' }) === 'granted') {
    opening = open()
    await opening
  }
}

export async function useBrowserStorage() {
  idle()
  await transact('handles', 'readwrite', store => store.delete('workdir'))
  opening = open()
  await opening
}

const readText = async (store: Disk, path: string) => (await store.read(path))?.text() ?? null
const readJson = async <T>(store: Disk, path: string): Promise<T | null> => {
  const text = await readText(store, path)
  return text === null ? null : JSON.parse(text) as T
}
const save = (store: Disk, path: string, data: unknown) => store.write(path, JSON.stringify(data, null, 2))
const encodePath = (path: string) => path.split('/').map(encodeURIComponent).join('/')
const suffix = (path: string) => /\.[^./]*$/.exec(path)?.[0].toLowerCase() ?? ''
const active = (job: Job) => job.status === 'queued' || job.status === 'running'

/* Jobs */

let jobs: Map<string, Job> | null = null
const syncing = new Set<string>()

async function savedJobs(store: Disk) {
  if (!jobs) {
    const found = new Map<string, Job>()
    for (const id of await store.list('jobs')) {
      const job = await readJson<Job>(store, `jobs/${id}/job.json`).catch(() => null)
      if (job?.id === id) found.set(id, job)
    }
    jobs ??= found
  }
  return jobs
}

/** Copies a finished job from the server, then deletes it there. */
async function collect(store: Disk, job: Job) {
  if (syncing.has(job.id)) return
  syncing.add(job.id)
  try {
    for (const file of job.files) {
      const response = await request(`/jobs/${job.id}/files/${encodePath(file.path)}`)
      await store.write(`jobs/${job.id}/output/${file.path}`, await response.blob())
    }
    const log = await server<{ text: string }>(`/jobs/${job.id}/logs?full=true`)
    await store.write(`jobs/${job.id}/log.txt`, log.text)
    // Written last, so a job only appears once all of its files are saved.
    await save(store, `jobs/${job.id}/job.json`, job)
    ;(await savedJobs(store)).set(job.id, job)
    await server(`/jobs/${job.id}`, { method: 'DELETE' }).catch(() => undefined)
  } finally { syncing.delete(job.id) }
}

async function listJobs(): Promise<Job[]> {
  const remote = await server<Job[]>('/jobs')
  const store = await ready()
  const local = store ? await savedJobs(store) : new Map<string, Job>()
  if (store) for (const job of remote) if (!active(job) && !local.has(job.id)) await collect(store, job).catch(() => undefined)
  const merged = new Map(remote.map(job => [job.id, job]))
  for (const [id, job] of local) merged.set(id, job)
  return [...merged.values()].sort((a, b) => b.created_at.localeCompare(a.created_at))
}

async function getJob(id: string): Promise<{ job: Job; local: boolean }> {
  const store = await ready()
  const saved = async () => store ? (await savedJobs(store)).get(id) : undefined
  const job = await saved()
  if (job) return { job, local: true }
  try { return { job: await server<Job>(`/jobs/${id}`), local: false } }
  catch (reason) {
    // The job may have been copied here and deleted on the server while the request was in flight.
    const copied = reason instanceof ApiError && reason.status === 404 ? await saved() : undefined
    if (!copied) throw reason
    return { job: copied, local: true }
  }
}

/** A job's output file, from this browser's copy or else the server. */
export async function jobFile(id: string, path: string): Promise<Blob> {
  const store = await ready()
  const blob = store && (await savedJobs(store)).has(id) ? await store.read(`jobs/${id}/output/${path}`) : null
  return blob ?? (await request(`/jobs/${id}/files/${encodePath(path)}`)).blob()
}

/* Bot */

const PAGE_INFO = /^\ufeff?(?:--\[=\[)?<%--\s*\[PAGE_INFO\]([\s\S]*?)\[END_PAGE_INFO\]\s*--%>(?:--\]=\])?[ \t]*(?:\n\n?|$)/
const INVALID_TITLE = /[#<>[\]|{}]/
const POSTABLE = ['.wikitext', '.lua']
const MEDIA = ['.png', '.jpg', '.jpeg', '.webp', '.gif']
const PASSWORD_KEY = 'painmelo.botPassword'
const defaults: BotSettings = {
  wiki: 'https://genshin-impact.fandom.com', username: '', remember: false, summary: '//Batch Posted',
  skip_existing: false, skip_unchanged: true, bot_edit: true, watch: true, protect: false,
}

function parsePage(text: string): [Record<string, string>, string] {
  text = text.replace(/\r\n/g, '\n')
  const match = PAGE_INFO.exec(text)
  if (!match) return [{}, text]
  const fields: Record<string, string> = {}
  for (const line of match[1].split('\n')) {
    const split = line.indexOf('=')
    if (split >= 0) fields[line.slice(0, split).trim()] = line.slice(split + 1).trim().replace(/^#+|#+$/g, '')
  }
  return [fields, text.slice(match[0].length)]
}

function checkTitle(title: string | null | undefined): string | null {
  title = (title ?? '').trim()
  if (!title) return null
  if (INVALID_TITLE.test(title)) throw new Error(`"${title}" contains characters MediaWiki does not allow in titles (# < > [ ] | { }).`)
  return title
}

function fileTitle(name: string | null | undefined): string | null {
  let title = checkTitle(name)
  if (title === null) return null
  if (!/^(file|image):/i.test(title)) title = `File:${title}`
  if (!title.split(':').slice(1).join(':').trim()) throw new Error('Enter the file name to upload as.')
  return title
}

const attempt = <T>(work: () => T): T | null => { try { return work() } catch { return null } }

interface Bot {
  settings: BotSettings
  password: string
  items: QueueItem[]
  log: string[]
  running: boolean
  stopping: boolean
}
let bot: Bot | null = null

async function loadBot(store: Disk): Promise<Bot> {
  if (!bot) {
    const settings = { ...defaults, ...await readJson<Partial<BotSettings>>(store, 'bot/settings.json') }
    const items = await readJson<QueueItem[]>(store, 'bot/queue.json') ?? []
    for (const item of items) if (item.status === 'posting') { item.status = 'failed'; item.message = 'The page was closed while this was being posted.' }
    bot ??= { settings, password: settings.remember ? localStorage.getItem(PASSWORD_KEY) ?? '' : '', items, log: [], running: false, stopping: false }
  }
  return bot
}

const saveQueue = (store: Disk, state: Bot) => save(store, 'bot/queue.json', state.items)

function note(state: Bot, line: string) {
  const clock = new Date().toLocaleTimeString('en-GB', { hour12: false })
  state.log.push(`${clock}  ${line}`)
  state.log.splice(0, state.log.length - 300)
}

const entry = (item: QueueItem): QueueEntry => {
  const copy: Partial<QueueItem> = { ...item }
  delete copy.content
  return copy as QueueEntry
}
const botState = (state: Bot | null): BotState => state
  ? { settings: { ...state.settings }, has_password: !!state.password, running: state.running, stopping: state.stopping, log: [...state.log], items: state.items.map(entry) }
  : { settings: { ...defaults }, has_password: false, running: false, stopping: false, log: [], items: [] }

const mediaPath = (item: QueueEntry) => `bot/media/${item.id}${suffix(item.path ?? '')}`

export async function mediaFile(id: string): Promise<Blob> {
  const store = await need()
  const item = (await loadBot(store)).items.find(item => item.id === id)
  const blob = item?.kind === 'file' ? await store.read(mediaPath(item)) : null
  if (!blob) throw new ApiError('Queued file not found.', 404)
  return blob
}

function item(state: Bot, id: string): QueueItem {
  const found = state.items.find(item => item.id === id)
  if (!found) throw new ApiError('Queued page not found.', 404)
  return found
}

async function enqueue(store: Disk, state: Bot, jobId: string, paths: string[]) {
  const { job } = await getJob(jobId)
  if (active(job)) throw new ApiError('Wait for the job to finish before queueing its files.', 409)
  const files = [...new Set(paths)].map(path => {
    const file = job.files.find(file => file.path === path)
    if (!file) throw new ApiError('Output file not found.', 404)
    return file
  })
  for (const file of files) if (![...POSTABLE, ...MEDIA].includes(suffix(file.path)))
    throw new ApiError(`${file.path} is not a page (.wikitext or .lua) or media file (${MEDIA.join(', ')}).`, 409)
  const existing = new Set(state.items.map(item => `${item.job_id}\n${item.path}`))
  const source = `${job.name} ${job.id.slice(0, 8)}`
  let added = 0, skipped = 0
  for (const file of files as Artifact[]) {
    if (existing.has(`${job.id}\n${file.path}`)) { skipped++; continue }
    const id = crypto.randomUUID().replace(/-/g, '')
    const blob = await jobFile(job.id, file.path)
    const base = { id, source, job_id: job.id, path: file.path, status: 'pending' as const, message: null, added_at: new Date().toISOString(), posted_at: null }
    let queued: QueueItem
    if (MEDIA.includes(suffix(file.path))) {
      // Keep a copy so the upload survives deleting the job.
      queued = { ...base, kind: 'file', title: attempt(() => fileTitle(file.path.split('/').pop())), content: file.file_page ?? '', size: blob.size }
      await store.write(mediaPath(queued), blob)
    } else {
      const [fields, content] = parsePage(await blob.text())
      queued = { ...base, kind: 'page', title: attempt(() => checkTitle(fields.pageTitle)), content, size: new TextEncoder().encode(content).length }
      if (fields.skip) { queued.status = 'skipped'; queued.message = 'Marked skip in the page info.' }
    }
    state.items.push(queued)
    existing.add(`${job.id}\n${file.path}`)
    added++
  }
  await saveQueue(store, state)
  return { added, skipped }
}

function base64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] ?? '')
    reader.onerror = () => reject(reader.error ?? new Error('Could not read the file.'))
    reader.readAsDataURL(blob)
  })
}

async function login(settings: BotSettings, password: string) {
  return server<{ session: string; username: string; api: string }>('/wiki/login', {
    method: 'POST', body: JSON.stringify({ wiki: settings.wiki, username: settings.username, password }),
  })
}

async function post(store: Disk, state: Bot, ids: string[]) {
  const settings = { ...state.settings }
  let session: string | null = null
  let posted = 0
  const finish = async (queued: QueueItem, status: QueueItem['status'], text: string | null) => {
    queued.status = status; queued.message = text
    if (status === 'posted') queued.posted_at = new Date().toISOString()
    await saveQueue(store, state)
    note(state, `${status[0].toUpperCase()}${status.slice(1)}: ${queued.title}${text ? ` — ${text}` : ''}`)
  }
  try {
    note(state, `Connecting to ${settings.wiki}...`)
    const account = await login(settings, state.password)
    session = account.session
    note(state, `Logged in as ${account.username} via ${account.api}.`)
    for (const id of ids) {
      if (state.stopping) { note(state, 'Stopped.'); break }
      const queued = state.items.find(item => item.id === id)
      if (!queued || (queued.status !== 'pending' && queued.status !== 'failed') || !queued.title) continue
      queued.status = 'posting'; queued.message = null
      let data: string | null = null
      if (queued.kind === 'file') {
        const blob = await store.read(mediaPath(queued))
        if (!blob) { await finish(queued, 'failed', 'The queued file is missing; add it to the queue again.'); continue }
        data = await base64(blob)
      }
      const result = await server<{ status: QueueItem['status']; message: string | null }>('/wiki/post', {
        method: 'POST', body: JSON.stringify({ session, kind: queued.kind, title: queued.title, content: queued.content, data, settings }),
      })
      posted += Number(result.status === 'posted')
      await finish(queued, result.status, result.message)
    }
  } catch (reason) {
    const text = reason instanceof Error ? reason.message : String(reason)
    note(state, `Stopped: ${text}`)
    for (const queued of state.items) if (queued.status === 'posting') { queued.status = 'failed'; queued.message = text }
    await saveQueue(store, state).catch(() => undefined)
  } finally {
    if (session) void server('/wiki/logout', { method: 'POST', body: JSON.stringify({ session }) }).catch(() => undefined)
    note(state, `Done. Posted ${posted} ${posted === 1 ? 'page' : 'pages'}.`)
    state.running = false; state.stopping = false
  }
}

async function handleBot(path: string, method: string, body: Record<string, unknown>): Promise<unknown> {
  if (path === '/bot' && method === 'GET') {
    const store = await ready()
    return botState(store ? await loadBot(store) : null)
  }
  const store = await need()
  const state = await loadBot(store)
  const queueItem = /^\/bot\/queue\/([0-9a-f]{32})$/.exec(path)
  if (path === '/bot/settings' && method === 'PUT') {
    if (state.running) throw new ApiError('Wait for posting to finish before changing settings.', 409)
    const wiki = String(body.wiki ?? '').trim()
    if (!/^(?:https?:\/\/)?[\w.-]+\.[a-z]{2,}(?::\d+)?(?:\/\S*)?$/i.test(wiki))
      throw new ApiError('Enter the wiki address, for example https://genshin-impact.fandom.com.', 409)
    if (typeof body.password === 'string') state.password = body.password
    const next = { ...defaults }
    for (const key of Object.keys(defaults) as (keyof BotSettings)[]) if (typeof body[key] === typeof defaults[key]) (next as Record<string, unknown>)[key] = body[key]
    state.settings = { ...next, wiki: wiki.replace(/\/+$/, ''), username: next.username.trim() }
    if (state.settings.remember) localStorage.setItem(PASSWORD_KEY, state.password)
    else localStorage.removeItem(PASSWORD_KEY)
    await save(store, 'bot/settings.json', state.settings.remember ? state.settings : { ...state.settings, username: '' })
    return botState(state)
  }
  if (path === '/bot/login' && method === 'POST') {
    if (!state.settings.username || !state.password) throw new ApiError('Enter the bot username and password first.', 409)
    const account = await login(state.settings, state.password)
    void server('/wiki/logout', { method: 'POST', body: JSON.stringify({ session: account.session }) }).catch(() => undefined)
    return { username: account.username }
  }
  if (path === '/bot/queue' && method === 'POST') return enqueue(store, state, String(body.job_id), (body.paths as string[] | undefined) ?? [])
  if (queueItem && method === 'GET') return { ...item(state, queueItem[1]) }
  if (queueItem && method === 'PATCH') {
    const queued = item(state, queueItem[1])
    if (queued.status === 'posting') throw new ApiError('This page is being posted right now.', 409)
    try {
      if (typeof body.title === 'string') queued.title = queued.kind === 'file' ? fileTitle(body.title) : checkTitle(body.title)
    } catch (reason) { throw new ApiError(reason instanceof Error ? reason.message : String(reason), 409) }
    if (typeof body.content === 'string') {
      queued.content = body.content.replace(/\r\n/g, '\n')
      if (queued.kind === 'page') queued.size = new TextEncoder().encode(queued.content).length
    }
    if ((typeof body.title === 'string' || typeof body.content === 'string') && queued.status !== 'pending') {
      queued.status = 'pending'; queued.message = null; queued.posted_at = null
    }
    await saveQueue(store, state)
    return { ...queued }
  }
  const ids = new Set((body.ids as string[] | undefined) ?? [])
  if (path === '/bot/queue/remove' && method === 'POST') {
    if (state.items.some(queued => ids.has(queued.id) && queued.status === 'posting')) throw new ApiError('A selected page is being posted right now.', 409)
    for (const queued of state.items) if (ids.has(queued.id) && queued.kind === 'file') await store.remove(mediaPath(queued))
    state.items = state.items.filter(queued => !ids.has(queued.id))
    await saveQueue(store, state)
    return botState(state)
  }
  if (path === '/bot/queue/reset' && method === 'POST') {
    for (const queued of state.items) if (ids.has(queued.id) && queued.status !== 'posting') { queued.status = 'pending'; queued.message = null; queued.posted_at = null }
    await saveQueue(store, state)
    return botState(state)
  }
  if (path === '/bot/post' && method === 'POST') {
    if (state.running) throw new ApiError('The queue is already being posted.', 409)
    if (!state.settings.username || !state.password) throw new ApiError('Enter the bot username and password in the settings first.', 409)
    const chosen = state.items.filter(queued => (queued.status === 'pending' || queued.status === 'failed') && queued.title && (!body.ids || ids.has(queued.id))).map(queued => queued.id)
    if (!chosen.length) throw new ApiError('Nothing to post. Pending pages need a target title before they can be posted.', 409)
    state.running = true; state.stopping = false; state.log = []
    void post(store, state, chosen)
    return botState(state)
  }
  if (path === '/bot/stop' && method === 'POST') {
    if (state.running) state.stopping = true
    return botState(state)
  }
  throw new ApiError('Not found.', 404)
}

/* Routing */

async function handleJobs(path: string, method: string, body: Record<string, unknown>, options: RequestInit): Promise<unknown> {
  const [route, query] = path.split('?', 2)
  if (route === '/jobs') return method === 'GET' ? listJobs() : server(path, options)
  const match = /^\/jobs\/([0-9a-f]{32})(?:\/(files|preview|logs|references)(?:\/(.*))?)?$/.exec(route)
  if (!match) throw new ApiError('Not found.', 404)
  const [, id, section, rest] = match
  const { job, local } = await getJob(id)
  if (!local) {
    try { return await server(path, options) }
    catch (reason) {
      // Same race as in getJob: retry against this browser's copy once it exists.
      if (reason instanceof ApiError && reason.status === 404 && (await getJob(id)).local) return handleJobs(path, method, body, options)
      throw reason
    }
  }
  const store = await need()
  const name = rest ? rest.split('/').map(decodeURIComponent).join('/') : ''
  if (!section) {
    if (method === 'GET') return job
    if (method === 'DELETE') {
      await store.remove(`jobs/${id}`)
      ;(await savedJobs(store)).delete(id)
      return undefined
    }
  }
  if (section === 'logs') {
    const blob = await store.read(`jobs/${id}/log.txt`) ?? new Blob()
    const full = new URLSearchParams(query).get('full') === 'true'
    return { text: await (full ? blob : blob.slice(-131072)).text(), truncated: !full && blob.size > 131072 }
  }
  if (section === 'references') {
    if (job.tool_id !== 'character-kit') throw new ApiError('This job has no game data references.', 404)
    return server(`/characters/${Number(job.parameters?.character_id)}/references${rest ? `/${rest}` : ''}`, options)
  }
  const file = job.files.find(file => file.path === name)
  const blob = file ? await store.read(`jobs/${id}/output/${name}`) : null
  if (!file || !blob) throw new ApiError('Output file not found.', 404)
  if (section === 'preview') {
    if (!['.wikitext', '.txt', '.lua', '.json'].includes(suffix(name))) throw new ApiError('This file does not have a text preview.', 415)
    if (blob.size > 1048576) throw new ApiError('This file is too large to preview. Download it instead.', 413)
    return { text: await blob.text() }
  }
  if (section === 'files' && method === 'PUT') {
    const text = String(body.text ?? '')
    await store.write(`jobs/${id}/output/${name}`, text)
    const updated = { ...job, files: job.files.map(item => item.path === name ? { ...item, size: new TextEncoder().encode(text).length } : item) }
    await save(store, `jobs/${id}/job.json`, updated)
    ;(await savedJobs(store)).set(id, updated)
    return updated
  }
  throw new ApiError('Not found.', 404)
}

export async function handle<T>(path: string, options: RequestInit): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const body = typeof options.body === 'string' && options.body ? JSON.parse(options.body) as Record<string, unknown> : {}
  const result = path.startsWith('/bot') ? await handleBot(path, method, body) : await handleJobs(path, method, body, options)
  return result as T
}
