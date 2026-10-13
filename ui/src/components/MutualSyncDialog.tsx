import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { useTranslation } from 'react-i18next'
import type { Agent } from '../types/Agent'
import { getCompatibilityWarmupStatus, planMutualSync, type CompatibilityWarmupStatus, type MutualSyncPlan } from '../services/api'
import { Icon } from './Icon'
import { HarnessIcon } from './HarnessIcon'
import { useMutualSyncJob } from '../hooks/useMutualSyncJob'

interface MutualSyncDialogProps {
  onClose: () => void
  availableAgents: Agent[]
}

type ResultFilter = 'all' | 'ready' | 'exceptions' | 'same'

interface SkillItemGroup<T extends { skillId: string; skillName: string }> {
  id: string
  skillName: string
  items: T[]
}

function groupBySkill<T extends { skillId: string; skillName: string }>(items: T[]): SkillItemGroup<T>[] {
  const groups = new Map<string, SkillItemGroup<T>>()
  for (const item of items) {
    const id = item.skillId.trim().toLocaleLowerCase() || item.skillName.trim().toLocaleLowerCase()
    const group = groups.get(id)
    if (group) group.items.push(item)
    else groups.set(id, { id, skillName: item.skillName, items: [item] })
  }
  return [...groups.values()]
}

function statusLabel(status: string, t: (key: string) => string) {
  const labels: Record<string, string> = {
    ready: t('mutualSync.ready'),
    review: t('mutualSync.review'),
    blocked: t('mutualSync.blocked'),
    conflict: t('mutualSync.conflict'),
    same: t('mutualSync.same'),
    started: t('status.running'),
    queued: t('mutualSync.queued'),
    pending: t('mutualSync.queued'),
    running: t('status.running'),
    success: t('status.success'),
    failed: t('status.failed'),
    warning_required: t('mutualSync.review'),
    stale: t('mutualSync.stale'),
    already_installed: t('mutualSync.same'),
    interrupted: t('mutualSync.interrupted'),
    unknown: t('mutualSync.unknownResult'),
    skipped: t('mutualSync.skipped'),
  }
  return labels[status] ?? status
}

function compatibilityLabel(status: string, t: (key: string) => string) {
  const labels: Record<string, string> = {
    compatible: t('mutualSync.technicalCompatibleTag'),
    review: t('mutualSync.technicalReviewTag'),
    incompatible: t('mutualSync.technicalIncompatibleTag'),
    unknown: t('mutualSync.technicalUnknownTag'),
  }
  return labels[status] ?? labels.unknown
}

function statusTone(status: string) {
  if (['review', 'warning_required', 'stale', 'unknown', 'interrupted', 'skipped'].includes(status)) return 'review'
  if (['blocked', 'conflict', 'failed'].includes(status)) return 'blocked'
  if (['same', 'already_installed'].includes(status)) return 'same'
  if (['queued', 'pending', 'started', 'running'].includes(status)) return 'running'
  return 'ready'
}

function checkDetailRows(
  details: Record<string, unknown> | undefined,
  t: (key: string) => string,
): Array<{ label: string; value: string }> {
  if (!details) return []
  const rows: Array<{ label: string; value: string }> = []
  const addString = (key: string, labelKey: string) => {
    const value = details[key]
    if (typeof value === 'string' && value.trim()) rows.push({ label: t(labelKey), value })
  }
  const addArray = (key: string, labelKey: string) => {
    const value = details[key]
    if (Array.isArray(value)) {
      const items = value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
      if (items.length) rows.push({ label: t(labelKey), value: items.slice(0, 8).join(', ') + (items.length > 8 ? ` (+${items.length - 8})` : '') })
    }
  }

  addString('evidence', 'mutualSync.sourceExcerpt')
  const locations = [details.targetPath, details.path, ...(Array.isArray(details.targetPaths) ? details.targetPaths : [])]
    .filter((value): value is string => typeof value === 'string' && Boolean(value.trim()) )
  if (locations.length) rows.push({ label: t('mutualSync.locations'), value: [...new Set(locations)].join(' · ') })
  addArray('missingReferences', 'mutualSync.missingSupportFiles')
  addArray('outsideSkillFolderReferences', 'mutualSync.outsideReferences')
  addArray('requiredHarnesses', 'mutualSync.harnessConstraint')
  addArray('limitedHarnesses', 'mutualSync.harnessConstraint')
  addString('installed', 'mutualSync.installedRequirement')
  addString('required', 'mutualSync.requiredRequirement')

  const hashes = ['sourceSha256', 'targetSha256', 'sha256']
    .flatMap((key) => typeof details[key] === 'string' ? [`${key}: ${String(details[key]).slice(0, 16)}`] : [])
  if (hashes.length) rows.push({ label: t('mutualSync.versionDetails'), value: hashes.join(' · ') })
  return rows
}

export function MutualSyncDialog({ onClose, availableAgents }: MutualSyncDialogProps) {
  const { t } = useTranslation()
  const agents = availableAgents
  const [selected, setSelected] = useState<string[]>(() => agents.map((agent) => agent.id))
  const [warmupStatus, setWarmupStatus] = useState<CompatibilityWarmupStatus>({ status: 'warming', checkedPairs: 0 })
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [plan, setPlan] = useState<MutualSyncPlan | null>(null)
  const { job, begin, clear, startError, pollError, restoring, active } = useMutualSyncJob()
  const tasks = job?.tasks ?? []
  const visiblePlan = job?.plan ?? plan
  const [elapsed, setElapsed] = useState(0)
  const [resultsExpanded, setResultsExpanded] = useState(false)
  const [resultsFilter, setResultsFilter] = useState<ResultFilter>('all')
  const [showAllSkills, setShowAllSkills] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const refreshWarmup = async () => {
      try {
        const status = await getCompatibilityWarmupStatus()
        if (cancelled) return
        setWarmupStatus(status)
        if (status.status === 'warming') timer = setTimeout(() => { void refreshWarmup() }, 300)
      } catch (err) {
        if (!cancelled) {
          setWarmupStatus({ status: 'failed', checkedPairs: 0, error: err instanceof Error ? err.message : t('mutualSync.warmupFailed') })
        }
      }
    }
    void refreshWarmup()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [t])

  useEffect(() => {
    if (warmupStatus.status !== 'ready' || selected.length < 2 || job || restoring) return
    let cancelled = false
    setChecking(true)
    setError(null)
    setPlan(null)
    void planMutualSync(selected)
      .then((nextPlan) => { if (!cancelled) setPlan(nextPlan) })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t('common.failed'))
      })
      .finally(() => { if (!cancelled) setChecking(false) })
    return () => { cancelled = true }
  }, [selected, t, warmupStatus.status, job?.id, restoring])

  useEffect(() => {
    setResultsExpanded(false)
    setResultsFilter('all')
    setShowAllSkills(false)
  }, [visiblePlan?.planId])

  useEffect(() => {
    if (!job) return
    const update = () => setElapsed(Math.max(0, Math.floor((job.endedAt ?? Date.now() / 1000) - job.startedAt)))
    update()
    if (job.status !== 'running') return
    const timer = setInterval(update, 1000)
    return () => clearInterval(timer)
  }, [job?.id, job?.status, job?.endedAt])

  useEffect(() => {
    if (job) setSelected(job.plan.agents)
  }, [job?.id])

  const toggleAgent = (id: string) => {
    setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
    setPlan(null)
    if (job && !active) clear()
  }

  const analyze = async () => {
    if (active) return
    setChecking(true)
    setError(null)
    setPlan(null)
    try {
      setPlan(await planMutualSync(selected))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.failed'))
    } finally {
      setChecking(false)
    }
  }

  const syncCompatible = () => {
    if (!plan || active) return
    setError(null)
    begin(selected, plan)
    setResultsExpanded(true)
    setResultsFilter('ready')
  }

  const allItems = visiblePlan?.items ?? []
  const exceptionItems = allItems.filter((item) => ['review', 'blocked', 'conflict'].includes(item.status))
  const readySkillGroups = groupBySkill(allItems.filter((item) => item.status === 'ready'))
  const exceptionSkillGroups = groupBySkill(exceptionItems)
  const sameSkillGroups = groupBySkill(allItems.filter((item) => item.status === 'same'))
  const filteredItems = resultsFilter === 'ready'
    ? allItems.filter((item) => item.status === 'ready')
    : resultsFilter === 'exceptions'
      ? exceptionItems
      : resultsFilter === 'same'
        ? allItems.filter((item) => item.status === 'same')
        : allItems
  const resultGroups = groupBySkill(filteredItems)
  const allSkillGroups = groupBySkill(allItems)
  const shownResultGroups = showAllSkills ? resultGroups : resultGroups.slice(0, 10)
  const taskByTarget = new Map(tasks.map((task) => [`${task.skillId.toLocaleLowerCase()}:${task.target.toLocaleLowerCase()}`, task]))

  const agentLabel = (id: string) => agents.find((agent) => agent.id.toLocaleLowerCase() === id.toLocaleLowerCase())?.name ?? id
  const agentListLabel = (ids: string) => ids.split(/[,，]/).map((id) => agentLabel(id.trim())).filter(Boolean).join(', ')
  const completedTasks = tasks.filter((task) => !['queued', 'started', 'pending', 'running'].includes(task.status))
  const failedTasks = completedTasks.filter((task) => !['success', 'already_installed'].includes(task.status))
  const progress = tasks.length ? Math.round(tasks.reduce((sum, task) => sum + (completedTasks.includes(task) ? 100 : task.progress || 0), 0) / tasks.length) : 0
  const currentTasks = tasks.filter((task) => ['started', 'pending', 'running'].includes(task.status))
  const phaseLabel = job?.status === 'success' ? t('mutualSync.completed') : job?.status === 'failed' ? t('mutualSync.finishedWithErrors') : t(`mutualSync.phases.${job?.phase ?? 'validating'}`)

  return (
    <div className="modal-backdrop" role="presentation">
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.18 }}
        className="sync-dialog mutual-sync-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mutual-sync-title"
      >
        <div className="sync-dialog-header">
          <div>
            <h2 id="mutual-sync-title" className="sync-dialog-title">{t('mutualSync.title')}</h2>
            <p className="sync-dialog-subtitle">{t('mutualSync.subtitle')}</p>
          </div>
          <button type="button" className="btn btn-quiet btn-icon" onClick={onClose} aria-label={t('common.close')}>
            <Icon name="x" size={17} />
          </button>
        </div>

        <div className="sync-dialog-body">
          {restoring ? <p className="mutual-sync-scan" role="status">{t('mutualSync.restoring')}</p> : null}
          {!job && pollError ? <p className="notice notice-error" role="alert">{t('mutualSync.pollRetry')}</p> : null}
          {startError ? <p className="notice notice-error" role="alert">{startError}</p> : null}
          {job ? (
            <section className={`mutual-sync-progress is-${job.status}`} aria-label={t('mutualSync.progress')}>
              <div className="mutual-sync-progress-heading" role="status" aria-live="polite">
                <span><Icon name={job.status === 'success' ? 'check' : job.status === 'failed' ? 'shield' : 'refresh'} size={17} />{phaseLabel}</span>
                <small>{t('mutualSync.elapsed', { seconds: elapsed })}</small>
              </div>
              <div className="mutual-sync-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label={t('mutualSync.progress')}>
                <span style={{ width: `${progress}%` }} />
              </div>
              <p>{t('mutualSync.completedCount', { completed: completedTasks.length, total: tasks.length })}{failedTasks.length ? ` · ${t('mutualSync.failedCount', { count: failedTasks.length })}` : ''}</p>
              {currentTasks.map((task) => <div className="mutual-sync-current-task" key={`${task.skillId}:${task.target}`}><span>{task.skillName} <small>→ {agentLabel(task.target)}</small></span><span>{task.progress || 0}%</span></div>)}
              {pollError ? <p className="mutual-sync-note" role="alert">{t('mutualSync.pollRetry')}</p> : null}
              {job.error ? <p className="notice notice-error" role="alert">{job.code ? t(`errors.${job.code}`, { defaultValue: job.error }) : job.error}</p> : null}
              {active ? <p className="mutual-sync-note">{t('mutualSync.backgroundHint')}</p> : null}
            </section>
          ) : null}
          <span className="form-label">{t('mutualSync.chooseAgents')}</span>
          {agents.length ? (
            <div className="mutual-sync-harness-grid">
              {agents.map((agent) => (
                <label key={agent.id} className={`mutual-sync-harness-card ${selected.includes(agent.id) ? 'is-selected' : ''}`}>
                  <span className={`mutual-sync-harness-icon harness-${agent.id}`}><HarnessIcon id={agent.id} /></span>
                  <span className="mutual-sync-harness-copy">{agent.name}{agent.version ? <small>{agent.version}</small> : null}</span>
                  <input type="checkbox" checked={selected.includes(agent.id)} onChange={() => toggleAgent(agent.id)} disabled={checking || active} />
                </label>
              ))}
            </div>
          ) : <p className="page-subtitle">{t('mutualSync.noAgents')}</p>}

          <p className="mutual-sync-note">{t('mutualSync.fastCheckNote')}</p>
          {warmupStatus.status === 'warming' ? (
            <div className="mutual-sync-scan" role="status"><Icon name="refresh" size={15} /> {t('mutualSync.warming')}</div>
          ) : warmupStatus.status === 'ready' ? (
            <p className="mutual-sync-note">{t('mutualSync.warmupReady', { count: warmupStatus.checkedPairs })}</p>
          ) : warmupStatus.status === 'failed' ? (
            <p className="mutual-sync-note" role="status">{t('mutualSync.warmupFailed')} {t('mutualSync.liveCheckFallback')}</p>
          ) : null}
          {error ? <div className="notice notice-error" style={{ marginTop: 13 }} role="alert">{error}</div> : null}

          {visiblePlan ? (
            <>
              <p className="mutual-sync-note mutual-sync-summary-label">{t('mutualSync.technicalSummary')}</p>
              <div className="mutual-sync-summary" aria-label={t('mutualSync.technicalSummary')}>
                <span>{t('mutualSync.technicalCompatible')}: {visiblePlan.summary.compatibility.compatible}</span>
                <span>{t('mutualSync.technicalReview')}: {visiblePlan.summary.compatibility.review}</span>
                <span>{t('mutualSync.technicalIncompatible')}: {visiblePlan.summary.compatibility.incompatible}</span>
                <span>{t('mutualSync.technicalUnknown')}: {visiblePlan.summary.compatibility.unknown}</span>
              </div>
              <p className="mutual-sync-note">{t('mutualSync.technicalDisclaimer')}</p>

              <p className="mutual-sync-note mutual-sync-summary-label">{t('mutualSync.syncSummary')}</p>
              <div className="mutual-sync-summary" aria-label={t('mutualSync.summary')}>
                <span>{t('mutualSync.ready')}: {visiblePlan.summary.ready}</span>
                <span>{t('mutualSync.review')}: {visiblePlan.summary.review}</span>
                <span>{t('mutualSync.blocked')}: {visiblePlan.summary.blocked}</span>
                <span>{t('mutualSync.conflict')}: {visiblePlan.summary.conflicts}</span>
                <span>{t('mutualSync.same')}: {visiblePlan.summary.alreadySynced}</span>
              </div>

              {allItems.length ? (
                <section className="mutual-sync-result-section">
                  <button
                    type="button"
                    className={`mutual-sync-section-toggle ${resultsExpanded ? 'is-expanded' : ''}`}
                    aria-expanded={resultsExpanded}
                    aria-controls="mutual-sync-results"
                    onClick={() => setResultsExpanded((value) => !value)}
                  >
                    <span className="mutual-sync-section-label">
                      <strong>{t('mutualSync.resultsTitle')}</strong>
                      <small>{t('mutualSync.groupSummary', { skills: allSkillGroups.length, targets: allItems.length })}</small>
                    </span>
                    <Icon name="chevron-right" size={15} />
                  </button>
                  <div id="mutual-sync-results" className="mutual-sync-section-content" hidden={!resultsExpanded}>
                    <div className="mutual-sync-filter-row" role="group" aria-label={t('mutualSync.filterResults')}>
                      {[
                        { key: 'all' as const, label: t('mutualSync.resultsAll'), count: allSkillGroups.length },
                        { key: 'ready' as const, label: t('mutualSync.ready'), count: readySkillGroups.length },
                        { key: 'exceptions' as const, label: t('mutualSync.resultsExceptions'), count: exceptionSkillGroups.length },
                        { key: 'same' as const, label: t('mutualSync.same'), count: sameSkillGroups.length },
                      ].map((filter) => (
                        <button
                          key={filter.key}
                          type="button"
                          className={`mutual-sync-filter ${resultsFilter === filter.key ? 'is-active' : ''}`}
                          aria-pressed={resultsFilter === filter.key}
                          onClick={() => { setResultsFilter(filter.key); setShowAllSkills(false) }}
                        >
                          {filter.label}<span>{filter.count}</span>
                        </button>
                      ))}
                    </div>
                    {resultsFilter === 'exceptions' ? <p className="mutual-sync-exception-hint">{t('mutualSync.exceptionHint')}</p> : null}
                    {resultGroups.length ? (
                      <div className="preflight-list">
                        {shownResultGroups.map((group) => {
                        const description = group.items.find((item) => item.skillDescription)?.skillDescription
                        return (
                          <article key={group.id} className="sync-state-row mutual-sync-skill-group">
                            <div className="sync-state-head"><span>{group.skillName}</span></div>
                            {description ? <p className="mutual-sync-description">{description}</p> : null}
                            <div className="mutual-sync-target-results">
                              {group.items.map((item, index) => {
                                const task = item.targetAgent
                                  ? taskByTarget.get(`${item.skillId.toLocaleLowerCase()}:${item.targetAgent.toLocaleLowerCase()}`)
                                  : undefined
                                const shownStatus = task?.status ?? item.status
                                const tone = statusTone(shownStatus)
                                const targetName = item.targetAgent ? agentLabel(item.targetAgent) : agentListLabel(item.sourceAgent) || t('mutualSync.multipleHarnesses')
                                const route = item.targetAgent
                                  ? `${agentListLabel(item.sourceAgent)} → ${targetName}`
                                  : agentListLabel(item.sourceAgent)
                                const message = task?.message || (item.status === 'ready' && !task ? '' : item.message)
                                return (
                                  <div key={`${item.targetAgent}:${item.status}:${index}`} className={`mutual-sync-target-result mutual-sync-target-result--${tone}`}>
                                    <div className="mutual-sync-outcome-head">
                                      <span className="mutual-sync-outcome-route">{route || targetName}</span>
                                      <span className="mutual-sync-badges">
                                        {item.targetAgent ? <span className={`mutual-sync-compat-chip mutual-sync-compat-chip--${item.compatibilityStatus}`}>{compatibilityLabel(item.compatibilityStatus, t)}</span> : null}
                                        <span className={`mutual-sync-target-chip mutual-sync-target-chip--${tone}`}>
                                          <span className="mutual-sync-target-dot" />{targetName}<small>{statusLabel(shownStatus, t)}</small>
                                        </span>
                                      </span>
                                    </div>
                                    {message ? <p className="sync-state-message">{message}</p> : null}
                                    {item.checks.some((check) => check.status !== 'pass') ? (
                                      <div className="mutual-sync-check-evidence">
                                        <p>{t('mutualSync.checkEvidence')}</p>
                                        <ul className="mutual-sync-checks">
                                          {item.checks.filter((check) => check.status !== 'pass').map((check, checkIndex) => (
                                            <li key={`${check.name}:${checkIndex}`} data-check-status={check.status}>
                                              {check.message}
                                              {checkDetailRows(check.details, t).map((row, rowIndex) => (
                                                <span className="mutual-sync-check-detail" key={`${row.label}:${rowIndex}`}>
                                                  <strong>{row.label}:</strong> {row.value}
                                                </span>
                                              ))}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}
                                  </div>
                                )
                              })}
                            </div>
                          </article>
                        )
                        })}
                      </div>
                    ) : <p className="mutual-sync-note">{t('mutualSync.noFilteredResults')}</p>}
                    {resultGroups.length > 10 ? (
                      <button type="button" className="panel-link mutual-sync-more" onClick={() => setShowAllSkills((value) => !value)}>
                        {showAllSkills ? t('mutualSync.showLess') : t('mutualSync.showMore', { count: resultGroups.length - 10 })}
                      </button>
                    ) : null}
                  </div>
                </section>
              ) : null}
            </>
          ) : null}

          <div className="sync-dialog-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>{active ? t('mutualSync.hidePanel') : t('common.close')}</button>
            {job ? (
              <button type="button" className="btn btn-primary" disabled={active} onClick={() => { clear(); setPlan(null) }}>{active ? phaseLabel : t('mutualSync.analyzeAgain')}</button>
            ) : !plan ? (
              <button type="button" className="btn btn-primary" disabled={active || warmupStatus.status === 'warming' || checking || selected.length < 2} onClick={() => { void analyze() }}>
                <Icon name="shield" size={15} />{warmupStatus.status === 'warming' ? t('mutualSync.warming') : checking ? t('mutualSync.checking') : t('mutualSync.analyze')}
              </button>
            ) : (
              <button type="button" className="btn btn-primary" disabled={active || checking || plan.summary.ready === 0 || tasks.length > 0} onClick={syncCompatible}>
                <Icon name="refresh" size={15} />{active ? t('mutualSync.syncing') : t('mutualSync.syncReady', { count: plan.summary.ready })}
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
