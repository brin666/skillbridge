import { useEffect, useState } from 'react'
import { ApiError, getMutualSyncJob, startMutualSync, type MutualSyncJob, type MutualSyncPlan } from '../services/api'

const JOB_KEY = 'skillbridge.sync.activeJob'
const JOB_EVENT = 'skillbridge:sync-job'
const PENDING_KEY = 'skillbridge.sync.pendingRequest'
let memoryId: string | null = null
let memoryPending: { id: string; agents: string[]; planId: string } | null = null
let storageAvailable = true

function savedJobId() {
  if (!storageAvailable) return memoryId
  try { return localStorage.getItem(JOB_KEY) } catch { return memoryId }
}

function pendingRequest() {
  if (!storageAvailable) return memoryPending
  try { return JSON.parse(localStorage.getItem(PENDING_KEY) || 'null') as typeof memoryPending } catch { return memoryPending }
}

function forgetPending() {
  memoryPending = null
  try { localStorage.removeItem(PENDING_KEY) } catch { /* storage is optional */ }
}

export function useMutualSyncJob() {
  const [jobId, setJobId] = useState(savedJobId)
  const [job, setJob] = useState<MutualSyncJob | null>(null)
  const [pollError, setPollError] = useState(false)
  const [restoring, setRestoring] = useState(Boolean(jobId))
  const [startError, setStartError] = useState<string | null>(null)

  useEffect(() => {
    const update = (event: Event) => {
      if (event instanceof StorageEvent && event.key !== JOB_KEY && event.key !== null) return
      const id = savedJobId()
      if (id === jobId) return
      setJobId(id)
      setJob((current) => current?.id === id ? current : null)
      setRestoring(Boolean(id))
    }
    window.addEventListener(JOB_EVENT, update)
    window.addEventListener('storage', update)
    return () => {
      window.removeEventListener(JOB_EVENT, update)
      window.removeEventListener('storage', update)
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) { setJob(null); setRestoring(false); setPollError(false); return }
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        let next: MutualSyncJob
        try {
          next = await getMutualSyncJob(jobId)
        } catch (err) {
          const pending = pendingRequest()
          if (!(err instanceof ApiError) || err.code !== 'SYNC_JOB_NOT_FOUND' || pending?.id !== jobId) throw err
          // The ID and payload were saved BEFORE POST. If its response was
          // lost, GET recovers it; if POST never arrived, retry that same ID.
          next = await startMutualSync(pending.agents, pending.planId, pending.id)
        }
        if (cancelled) return
        if (pendingRequest()?.id === jobId) forgetPending()
        setJob(next)
        setRestoring(false)
        setPollError(false)
        if (next.status === 'running') timer = setTimeout(() => { void poll() }, 600)
      } catch (err) {
        if (cancelled) return
        setPollError(true)
        if (err instanceof ApiError && ['SYNC_JOB_NOT_FOUND', 'PLAN_REQUIRED', 'PLAN_STALE', 'AGENTS_REQUIRED', 'SYNC_REQUEST_INVALID', 'SYNC_REQUEST_MISMATCH'].includes(err.code || '')) {
          memoryId = null
          try { localStorage.removeItem(JOB_KEY) } catch { /* storage is optional */ }
          forgetPending()
          setStartError(err.message)
          setJobId(null)
          setRestoring(false)
          window.dispatchEvent(new Event(JOB_EVENT))
          return
        }
        // Keep the unresolved ID active: a lost response is NOT permission
        // to start another batch while the old one may still be writing.
        timer = setTimeout(() => { void poll() }, 1800)
      }
    }
    void poll()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [jobId])

  const begin = (agents: string[], plan: MutualSyncPlan) => {
    if (jobId) return
    const id = crypto.randomUUID().replace(/-/g, '')
    memoryId = id
    memoryPending = { id, agents, planId: plan.planId }
    try {
      localStorage.setItem(PENDING_KEY, JSON.stringify(memoryPending))
      localStorage.setItem(JOB_KEY, id)
    } catch { storageAvailable = false /* keep tracking if storage is unavailable */ }
    setStartError(null)
    setJob(null)
    setJobId(id)
    setRestoring(true)
    window.dispatchEvent(new Event(JOB_EVENT))
  }

  const clear = () => {
    memoryId = null
    forgetPending()
    try { localStorage.removeItem(JOB_KEY) } catch { /* storage is optional */ }
    setJob(null)
    setJobId(null)
    setStartError(null)
    window.dispatchEvent(new Event(JOB_EVENT))
  }

  return { job, begin, clear, startError, pollError, restoring, active: Boolean(jobId) && (job?.id !== jobId || job.status === 'running') }
}
