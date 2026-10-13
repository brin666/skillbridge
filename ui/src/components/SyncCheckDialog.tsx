import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { useTranslation } from 'react-i18next'
import type { Agent } from '../types/Agent'
import type { PreflightCheck, PreflightResult } from '../types/Preflight'
import { Icon } from './Icon'
import { batchSyncSkill, getSyncTransaction, preflightSkill, syncSkill, type SyncResult } from '../services/api'

interface SyncCheckDialogProps {
  skillId: string
  skillName: string
  agents: Agent[]
  onClose: () => void
}

interface RunningTask {
  target: string
  transactionId: string
}

function CheckIcon({ status }: { status: PreflightCheck['status'] }) {
  if (status === 'pass') return <Icon name="check" size={14} style={{ color: 'var(--success)' }} />
  if (status === 'warn') return <Icon name="activity" size={14} style={{ color: 'var(--warning)' }} />
  return <Icon name="x" size={14} style={{ color: 'var(--danger)' }} />
}

export function SyncCheckDialog({ skillId, skillName, agents, onClose }: SyncCheckDialogProps) {
  const { t } = useTranslation()
  const installed = agents.filter((agent) => agent.installed)
  const [selected, setSelected] = useState<string[]>(installed.length ? [installed[0].id] : [])
  const [preflights, setPreflights] = useState<Record<string, PreflightResult>>({})
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runningTasks, setRunningTasks] = useState<RunningTask[]>([])
  const [taskStates, setTaskStates] = useState<Record<string, SyncResult>>({})
  const [confirmedWarning, setConfirmedWarning] = useState(false)

  const toggleTarget = (id: string) => {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
    setPreflights({})
    setConfirmedWarning(false)
  }

  const runCheck = async () => {
    if (selected.length === 0) return
    setChecking(true)
    setError(null)
    setPreflights({})
    setConfirmedWarning(false)
    try {
      const entries = await Promise.all(selected.map(async (target) => [target, await preflightSkill(skillId, target)] as const))
      setPreflights(Object.fromEntries(entries))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.failed'))
    } finally {
      setChecking(false)
    }
  }

  const startSync = async () => {
    if (selected.length === 0) return
    setError(null)
    setRunningTasks([])
    setTaskStates({})
    const anyWarn = selected.some((target) => preflights[target]?.status === 'warn')
    const confirm = confirmedWarning || !anyWarn

    try {
      if (selected.length === 1) {
        const target = selected[0]
        const result = await syncSkill(skillId, target, confirm)
        if (result.status === 'warning_required') {
          setError(t('syncDialog.warningRequired'))
          return
        }
        if (result.status === 'started' && result.transaction_id) {
          setRunningTasks([{ target, transactionId: result.transaction_id }])
        } else {
          setTaskStates({ [target]: result })
        }
      } else {
        const result = await batchSyncSkill(skillId, selected, confirm)
        const tasks: RunningTask[] = []
        const states: Record<string, SyncResult> = {}
        for (const task of result.tasks ?? []) {
          if (task.transaction_id && task.status === 'started') {
            tasks.push({ target: task.target, transactionId: task.transaction_id })
          } else {
            states[task.target] = { status: task.status ?? 'failed', message: task.error ?? task.status ?? 'failed' }
          }
        }
        setRunningTasks(tasks)
        setTaskStates(states)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.failed'))
    }
  }

  useEffect(() => {
    if (runningTasks.length === 0) return
    let cancelled = false
    const timer = setInterval(async () => {
      const next: Record<string, SyncResult> = {}
      let allDone = true
      for (const task of runningTasks) {
        try {
          const tx = await getSyncTransaction(task.transactionId)
          next[task.target] = tx
          if (!tx || !(tx.status === 'success' || tx.status === 'failed')) allDone = false
        } catch {
          next[task.target] = { status: 'failed', message: t('common.failed') }
        }
      }
      if (!cancelled) {
        setTaskStates((current) => ({ ...current, ...next }))
        if (allDone) setRunningTasks([])
      }
    }, 300)
    return () => { cancelled = true; clearInterval(timer) }
  }, [runningTasks, t])

  const allFinished = selected.length > 0 && selected.every((target) => {
    const state = taskStates[target]
    return state && (state.status === 'success' || state.status === 'failed')
  })
  const allSuccess = allFinished && selected.every((target) => taskStates[target]?.status === 'success')

  useEffect(() => {
    if (!allSuccess) return
    const timer = setTimeout(onClose, 1600)
    return () => clearTimeout(timer)
  }, [allSuccess, onClose])

  const anyBlock = selected.some((target) => preflights[target]?.status === 'block')
  const anyWarn = selected.some((target) => preflights[target]?.status === 'warn')
  const continueLabel = anyWarn && !confirmedWarning ? t('syncDialog.confirmContinue') : t('syncDialog.startSync')

  return (
    <div className="modal-backdrop" role="presentation">
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.18 }}
        className="sync-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sync-dialog-title"
      >
        <div className="sync-dialog-header">
          <div>
            <h2 id="sync-dialog-title" className="sync-dialog-title">{t('syncDialog.syncCheck')}</h2>
            <p className="sync-dialog-subtitle">{skillName}</p>
          </div>
          <button type="button" className="btn btn-quiet btn-icon" onClick={onClose} aria-label={t('common.close')}>
            <Icon name="x" size={17} />
          </button>
        </div>

        <div className="sync-dialog-body">
          <span className="form-label">{t('syncDialog.targets')}</span>
          <div className="target-list">
            {installed.length ? installed.map((agent) => (
              <label key={agent.id} className="target-row">
                <span>{agent.name}</span>
                <input type="checkbox" checked={selected.includes(agent.id)} onChange={() => toggleTarget(agent.id)} />
              </label>
            )) : <p className="page-subtitle">{t('syncDialog.noInstalledAgents')}</p>}
          </div>

          <button type="button" className="btn btn-primary" style={{ width: '100%', marginTop: 15 }} disabled={selected.length === 0 || checking || runningTasks.length > 0} onClick={() => { void runCheck() }}>
            <Icon name="shield" size={15} />
            {checking ? t('syncDialog.checking') : t('syncDialog.runPreflight')}
          </button>

          {error ? <div className="notice notice-error" style={{ marginTop: 13 }}>{error}</div> : null}

          {Object.keys(preflights).length > 0 ? (
            <div className="preflight-list">
              {Object.entries(preflights).map(([target, result]) => (
                <div key={target} className="preflight-card">
                  <div className="preflight-head">
                    <span>{target}</span>
                    <span style={{ color: result.status === 'pass' ? 'var(--success)' : result.status === 'warn' ? 'var(--warning)' : 'var(--danger)' }}>{result.status.toUpperCase()}</span>
                  </div>
                  <p className="mutual-sync-note">
                    {t('syncDialog.technicalCompatibility')}: {t(`syncDialog.technicalStatus.${result.technicalCompatibility.status}`)}
                    {result.technicalCompatibility.notes.length ? ` · ${result.technicalCompatibility.notes.join(' · ')}` : ''}
                  </p>
                  <div className="preflight-checks">
                    {result.checks.map((check) => (
                      <div key={check.name} className="preflight-check">
                        <CheckIcon status={check.status} />
                        <span>{check.name}: {check.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {anyWarn && !confirmedWarning ? (
                <div className="sync-warning">
                  <p>{t('syncDialog.risksFound')}</p>
                  <ul>{Object.values(preflights).flatMap((result) => result.warnings).map((warning) => <li key={warning}>{warning}</li>)}</ul>
                </div>
              ) : null}

              {runningTasks.length > 0 || allFinished ? (
                <div className="sync-state-list">
                  {selected.map((target) => {
                    const state = taskStates[target]
                    const stateTone = state?.status === 'success' ? 'var(--success)' : state?.status === 'failed' ? 'var(--danger)' : 'var(--accent-deep)'
                    return (
                      <div key={target} className="sync-state-row">
                        <div className="sync-state-head">
                          <span>{target}</span>
                          <span style={{ color: stateTone }}>{state?.status === 'success' ? t('status.success') : state?.status === 'failed' ? t('status.failed') : t('status.running')}</span>
                        </div>
                        {state?.message ? <p className="sync-state-message">{state.message}</p> : null}
                        {state?.steps ? <div className="sync-step-list">{state.steps.map((step) => <span key={step.name}><Icon name={step.status === 'success' ? 'check' : 'activity'} size={11} /> {step.name}</span>)}</div> : null}
                      </div>
                    )
                  })}
                </div>
              ) : null}

              <div className="sync-dialog-actions">
                {anyBlock ? (
                  <button type="button" className="btn btn-secondary" disabled>{t('syncDialog.blocked')}</button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={checking || runningTasks.length > 0 || allFinished}
                    onClick={() => { if (anyWarn && !confirmedWarning) setConfirmedWarning(true); else void startSync() }}
                  >
                    {allFinished ? t('syncDialog.completed') : continueLabel}
                  </button>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </motion.div>
    </div>
  )
}
