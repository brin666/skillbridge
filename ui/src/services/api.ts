import type { Agent } from '../types/Agent'
import type { Environment } from '../types/Environment'
import type { LibrarySkill } from '../types/Library'
import type { PreflightResult } from '../types/Preflight'
import type { Skill } from '../types/Skill'
import i18n from '../i18n'

export interface SyncResult {
  id?: string
  transaction_id?: string
  status: string
  message?: string
  reason?: string
  warnings?: string[]
  target?: string
  errors?: string[]
  checks?: Array<{ name: string; status: string; message: string }>
  progress?: number
  steps?: Array<{ name: string; status: string; message: string }>
  startTime?: string
  endTime?: string
  skill?: string
  sourceAgent?: string
  targetAgent?: string
  error?: string
}

export interface MutualSyncItem {
  skillId: string
  skillName: string
  skillDescription: string
  sourceAgent: string
  targetAgent: string
  status: 'ready' | 'review' | 'blocked' | 'conflict' | 'same'
  message: string
  compatibilityStatus: 'compatible' | 'review' | 'incompatible' | 'unknown'
  compatibilityNotes: string[]
  checks: Array<{ name: string; status: 'pass' | 'warn' | 'block'; message: string; details?: Record<string, unknown> }>
}

export interface MutualSyncPlan {
  planId: string
  agents: string[]
  summary: {
    ready: number
    review: number
    blocked: number
    conflicts: number
    alreadySynced: number
    compatibility: {
      compatible: number
      review: number
      incompatible: number
      unknown: number
    }
  }
  items: MutualSyncItem[]
}

export interface CompatibilityWarmupStatus {
  status: 'idle' | 'warming' | 'ready' | 'failed'
  checkedPairs: number
  error?: string | null
}

export interface MutualSyncTask {
  skillId: string
  skillName: string
  sourceAgent: string
  target: string
  transaction_id?: string
  status: string
  progress: number
  message?: string
  steps?: Array<{ name: string; status: string; message: string }>
}

export interface MutualSyncJob {
  id: string
  status: 'running' | 'success' | 'failed'
  phase: 'validating' | 'syncing' | 'refreshing' | 'finished'
  startedAt: number
  endedAt?: number
  plan: MutualSyncPlan
  tasks: MutualSyncTask[]
  code?: string
  error?: string | null
}

export const getMutualSyncJob = (id: string) =>
  request<MutualSyncJob>(`/api/sync/mutual/jobs/${encodeURIComponent(id)}`, { signal: AbortSignal.timeout(10000) })

export class ApiError extends Error {
  constructor(message: string, public code?: string) { super(message) }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `API request failed: ${response.status} ${path}`
    let code: string | undefined
    try {
      const data = (await response.json()) as { error?: string; code?: string; message?: string }
      if (data.code) {
        code = data.code
        message = i18n.t(`errors.${data.code}`, { defaultValue: data.message || message })
      } else if (data.error) {
        message = data.error
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new ApiError(message, code)
  }
  return response.json() as Promise<T>
}

export const getEnvironment = () => request<Environment>('/api/environment')
export const getAgents = () => request<Agent[]>('/api/agents')
export const getSkills = () => request<Skill[]>('/api/skills')
export const rescanEnvironment = () => request<{ agents: number; skills: number }>('/api/rescan')
export const getCompatibilityWarmupStatus = () => request<CompatibilityWarmupStatus>('/api/sync/mutual/warmup')
export const getSkill = (id: string) => request<Skill>(`/api/skills/${encodeURIComponent(id)}`)

export const preflightSkill = (id: string, targetAgent: string) =>
  request<PreflightResult>(`/api/skills/${encodeURIComponent(id)}/preflight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_agent: targetAgent }),
  })

export const syncSkill = (id: string, targetAgent: string, confirmWarning: boolean) =>
  request<SyncResult>(`/api/skills/${encodeURIComponent(id)}/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_agent: targetAgent, confirm_warning: confirmWarning }),
  })

export const getSyncTransaction = (id: string) => request<SyncResult>(`/api/sync/${encodeURIComponent(id)}`)
export const getSyncHistory = () => request<SyncResult[]>('/api/sync/history')

export const planMutualSync = (agents: string[]) =>
  request<MutualSyncPlan>('/api/sync/mutual/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agents }),
  })

export const startMutualSync = (agents: string[], planId: string, requestId: string) =>
  request<MutualSyncJob>('/api/sync/mutual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agents, plan_id: planId, request_id: requestId, background: true }),
    signal: AbortSignal.timeout(10000),
  })

export const batchSyncSkill = (
  id: string,
  targets: string[],
  confirmWarning: boolean,
  forceReplace = false,
) =>
  request<{ tasks: Array<{ target: string; transaction_id?: string; status?: string; warnings?: string[]; error?: string }> }>(
    `/api/skills/${encodeURIComponent(id)}/batch-sync`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        targets,
        confirm_warning: confirmWarning,
        force_replace: forceReplace,
      }),
    },
  )

export const getLibrary = () => request<LibrarySkill[]>('/api/library')
export const getLibrarySkill = (id: string) => request<LibrarySkill>(`/api/library/skills/${encodeURIComponent(id)}`)
export const importSkillToLibrary = (skillId: string, sourceAgent: string) =>
  request<{ status: string; message: string }>(`/api/library/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill_id: skillId, source_agent: sourceAgent }),
  })
export const removeLibrarySkill = (id: string) =>
  request<{ status: string; message: string }>(`/api/library/skills/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
export const deployLibrarySkill = (
  id: string,
  targets: string[],
  confirmWarning: boolean,
  forceReplace = false,
) =>
  request<{ tasks: Array<{ target: string; transaction_id?: string; status?: string; warnings?: string[]; error?: string }> }>(
    `/api/library/skills/${encodeURIComponent(id)}/deploy`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        targets,
        confirm_warning: confirmWarning,
        force_replace: forceReplace,
      }),
    },
  )

export const openSkillFolder = (id: string) =>
  request<{ success: boolean; message: string }>(`/api/skills/${encodeURIComponent(id)}/open-folder`, {
    method: 'POST',
  })

export const openSkillFile = (id: string) =>
  request<{ success: boolean; message: string }>(`/api/skills/${encodeURIComponent(id)}/open-file`, {
    method: 'POST',
  })

export const disableSkill = (id: string) =>
  request<{ success: boolean; message: string; enabled: boolean }>(`/api/skills/${encodeURIComponent(id)}/disable`, {
    method: 'POST',
  })

export const enableSkill = (id: string) =>
  request<{ success: boolean; message: string; enabled: boolean }>(`/api/skills/${encodeURIComponent(id)}/enable`, {
    method: 'POST',
  })

export const uninstallSkill = (id: string) =>
  request<{ success: boolean; message: string }>(`/api/skills/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
