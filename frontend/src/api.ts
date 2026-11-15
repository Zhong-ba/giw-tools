export type Parameters = Record<string, string | number | boolean | null>
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
}
export interface Tool {
  id: string
  name: string
  category: string
  description: string
  requires_dataset: boolean
  schema: { properties: Record<string, Property>; required?: string[] }
}
export interface Artifact { path: string; size: number; kind: 'text' | 'image' | 'file' }
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
}
export interface Dataset {
  source: string | null
  ready: boolean
  path: string | null
  commit: string | null
  tables: number
  languages: number
  error: string | null
}
export interface Character { id: number; name: string; skill_depot: number | null }

export function message(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
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

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  })
  if (!response.ok) {
    const type = response.headers.get('content-type') ?? ''
    throw new Error(type.includes('application/json') ? errorDetail(await response.json()) : `Server returned ${response.status}.`)
  }
  return response.json()
}

export const fileUrl = (job: string, path: string) => `/api/jobs/${job}/files/${path.split('/').map(encodeURIComponent).join('/')}`
