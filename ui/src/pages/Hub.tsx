import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'motion/react'
import { useTranslation } from 'react-i18next'
import { MutualSyncDialog } from '../components/MutualSyncDialog'
import { Icon } from '../components/Icon'
import { HarnessIcon } from '../components/HarnessIcon'
import { useMutualSyncJob } from '../hooks/useMutualSyncJob'
import { useApi } from '../hooks/useApi'
import { getAgents, getSkills } from '../services/api'
import type { Skill } from '../types/Skill'
import './Hub.css'

interface HubProps {
  onOpenDashboard: () => void
}

type IntroStage = 'capsule' | 'scanning' | 'harnesses' | 'skills' | 'ready'

const INTRO_KEY = 'skillbridge.hub.intro.v1'

function readFirstVisit() {
  try {
    return localStorage.getItem(INTRO_KEY) !== '1'
  } catch {
    return false
  }
}

function markIntroSeen() {
  try {
    localStorage.setItem(INTRO_KEY, '1')
  } catch {
    // The Hub remains usable when browser storage is unavailable.
  }
}

function skillAgents(skill: Skill) {
  return skill.installedAgents?.length ? skill.installedAgents : skill.installed_agents ?? []
}

function cardDescription(skill: Skill, language: string, fallback: string) {
  return skill.summaries?.[language] || fallback
}

function githubReadmeUrl(skill: Skill) {
  const hasReadme = (skill.files ?? []).some((file) => file.toLowerCase() === 'readme.md')
  const sourceUrl = skill.source?.type === 'github' ? skill.source.url?.replace(/\.git\/?$/, '').replace(/\/$/, '') : ''
  return hasReadme && sourceUrl ? `${sourceUrl}/blob/HEAD/README.md` : null
}

function ScanWave({ label }: { label: string }) {
  return (
    <div className="hub-scan-state" role="status" aria-label={label}>
      <div className="hub-scan-orbit" aria-hidden>
        <span className="hub-scan-ring hub-scan-ring--one" />
        <span className="hub-scan-ring hub-scan-ring--two" />
        <span className="hub-scan-ring hub-scan-ring--three" />
        <span className="hub-scan-triangle">△</span>
      </div>
      <span className="hub-visually-hidden">{label}</span>
    </div>
  )
}

export function Hub({ onOpenDashboard }: HubProps) {
  const { t, i18n } = useTranslation()
  const agents = useApi(getAgents)
  const skills = useApi(getSkills)
  const reduceMotion = useReducedMotion()
  const [firstVisit] = useState(readFirstVisit)
  const [expanded, setExpanded] = useState(false)
  const [introStage, setIntroStage] = useState<IntroStage>(firstVisit ? 'capsule' : 'ready')
  const [selectedHarness, setSelectedHarness] = useState('')
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null)
  const [showSyncDialog, setShowSyncDialog] = useState(false)
  const { job, active: syncActive } = useMutualSyncJob()
  const [syncDone, setSyncDone] = useState(false)

  const installedAgents = useMemo(() => (agents.data ?? []).filter((agent) => agent.installed), [agents.data])

  useEffect(() => {
    if (!firstVisit) return
    markIntroSeen()
    if (reduceMotion) {
      setExpanded(true)
      setIntroStage('ready')
      return
    }
    const timers = [
      window.setTimeout(() => { setExpanded(true); setIntroStage('scanning') }, 120),
      window.setTimeout(() => setIntroStage('harnesses'), 630),
      window.setTimeout(() => setIntroStage('skills'), 1030),
      window.setTimeout(() => setIntroStage('ready'), 1880),
    ]
    return () => timers.forEach(window.clearTimeout)
  }, [firstVisit, reduceMotion])

  useEffect(() => {
    if (!job || job.status === 'running') { setSyncDone(false); return }
    agents.reload()
    skills.reload()
    setSyncDone(job.status === 'success')
    const timer = window.setTimeout(() => setSyncDone(false), 1100)
    return () => window.clearTimeout(timer)
  }, [job?.id, job?.status])

  useEffect(() => {
    if (installedAgents.some((agent) => agent.id === selectedHarness)) return
    const preferred = installedAgents.find((agent) => agent.id === 'codex') ?? installedAgents[0]
    setSelectedHarness(preferred?.id ?? '')
  }, [installedAgents, selectedHarness])

  const visibleSkills = useMemo(() => {
    if (!selectedHarness) return []
    const grouped = new Map<string, Skill>()
    for (const skill of skills.data ?? []) {
      const id = skill.id.trim().toLocaleLowerCase()
      if (!id) continue
      const existing = grouped.get(id)
      if (!existing) {
        grouped.set(id, { ...skill, installedAgents: [...skillAgents(skill)] })
        continue
      }
      grouped.set(id, {
        ...existing,
        installedAgents: [...new Set([...skillAgents(existing), ...skillAgents(skill)])],
      })
    }
    return [...grouped.values()]
      .filter((skill) => skillAgents(skill).some((agentId) => agentId.toLocaleLowerCase() === selectedHarness.toLocaleLowerCase()))
      .sort((left, right) => (left.displayName || left.name).localeCompare(right.displayName || right.name))
  }, [selectedHarness, skills.data])

  const activeSkill = visibleSkills.find((skill) => skill.id === activeSkillId) ?? null
  const activeFeatures = activeSkill?.features?.[i18n.language]?.filter(Boolean) ?? []
  const showCards = introStage === 'skills' || introStage === 'ready' || !firstVisit
  const isLoading = agents.loading || skills.loading
  const error = agents.error || skills.error

  const toggleExpanded = () => {
    markIntroSeen()
    setIntroStage('ready')
    setActiveSkillId(null)
    setExpanded((value) => !value)
  }

  const openSync = () => {
    setShowSyncDialog(true)
  }

  const syncControl = (
    <motion.button
      layoutId="skillbridge-hub-sync"
      type="button"
      className="hub-icon-button hub-sync-control"
      aria-label={t('hub.sync')}
      title={t('hub.sync')}
      aria-busy={syncActive}
      onClick={openSync}
      whileTap={{ scale: 0.9 }}
    >
      <motion.span
        className="hub-sync-glyph"
        animate={syncActive && !reduceMotion ? { rotate: [0, 360] } : { rotate: 0 }}
        transition={syncActive ? { duration: 1.2, repeat: Infinity, ease: 'linear' } : { duration: 0.18 }}
      >
        {syncDone ? <Icon name="check" size={19} /> : <Icon name="refresh" size={19} />}
      </motion.span>
    </motion.button>
  )

  return (
    <div className="skillbridge-hub-stage">
      <div className="hub-ambient hub-ambient--dawn" aria-hidden />
      <div className="hub-ambient hub-ambient--blue" aria-hidden />
      <LayoutGroup id="skillbridge-hub-layout">
        <motion.section
          layout
          className={`skillbridge-hub-surface ${expanded ? 'is-expanded' : 'is-capsule'}`}
          animate={{ borderRadius: expanded ? 34 : 999 }}
          transition={{ layout: reduceMotion ? { duration: 0 } : { type: 'spring', stiffness: 245, damping: 30 }, borderRadius: { duration: reduceMotion ? 0 : 0.34 } }}
          aria-label={t('hub.title')}
        >
          <motion.header layout className={`hub-toolbar ${expanded ? 'is-expanded' : 'is-capsule'}`}>
            {syncControl}
            <AnimatePresence initial={false}>
              {expanded ? (
                <motion.nav
                  key="harness-selector"
                  className="hub-harness-selector"
                  aria-label={t('hub.harnesses')}
                  initial={{ opacity: 0, filter: 'blur(7px)', scale: 0.96 }}
                  animate={{ opacity: 1, filter: 'blur(0px)', scale: 1 }}
                  exit={{ opacity: 0, filter: 'blur(7px)', scale: 0.96 }}
                  transition={{ duration: reduceMotion ? 0 : 0.28, ease: 'easeOut' }}
                >
                  {installedAgents.map((agent, index) => (
                    <motion.button
                      key={agent.id}
                      type="button"
                      className={`hub-harness-button harness-${agent.id} ${selectedHarness === agent.id ? 'is-selected' : ''}`}
                      aria-label={agent.name}
                      aria-pressed={selectedHarness === agent.id}
                      title={agent.name}
                      onClick={() => { setSelectedHarness(agent.id); setActiveSkillId(null) }}
                      initial={firstVisit ? { opacity: 0, scale: 0.72, filter: 'blur(7px)' } : false}
                      animate={introStage === 'capsule' || introStage === 'scanning' ? { opacity: 0, scale: 0.72, filter: 'blur(7px)' } : { opacity: 1, scale: 1, filter: 'blur(0px)' }}
                      transition={{ duration: reduceMotion ? 0 : 0.36, delay: !reduceMotion && firstVisit && introStage === 'harnesses' ? index * 0.095 : 0 }}
                      whileTap={{ scale: 0.92 }}
                    >
                      <HarnessIcon id={agent.id} size={24} />
                    </motion.button>
                  ))}
                </motion.nav>
              ) : null}
            </AnimatePresence>
            <motion.div layout className="hub-toolbar-end">
              {expanded ? (
                <motion.button
                  type="button"
                  className="hub-icon-button hub-dashboard-control"
                  aria-label={t('hub.openDashboard')}
                  title={t('hub.openDashboard')}
                  onClick={onOpenDashboard}
                  initial={{ opacity: 0, scale: 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.22 }}
                >
                  <Icon name="grid" size={16} />
                </motion.button>
              ) : null}
              <motion.button
                layoutId="skillbridge-hub-toggle"
                type="button"
                className={`hub-icon-button ${expanded ? 'hub-collapse-control' : 'hub-expand-control'}`}
                aria-label={expanded ? t('hub.collapse') : t('hub.expand')}
                title={expanded ? t('hub.collapse') : t('hub.expand')}
                onClick={toggleExpanded}
                whileTap={{ scale: 0.9 }}
              >
                <motion.span animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.24 }} aria-hidden>
                  △
                </motion.span>
              </motion.button>
            </motion.div>
          </motion.header>

          {expanded ? (
            <motion.div
              className="hub-expanded-content"
              initial={{ opacity: 0.92, filter: 'blur(8px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              transition={{ duration: reduceMotion ? 0 : firstVisit ? 0.42 : 0.32, ease: 'easeOut' }}
            >
                <div className="hub-main-region">
                  {error ? (
                    <div className="hub-inline-state" role="alert">
                      <p>{error}</p>
                      <button type="button" className="hub-retry-button" onClick={() => { agents.reload(); skills.reload() }}>
                        <Icon name="refresh" size={15} />{t('common.retry')}
                      </button>
                    </div>
                  ) : null}

                  {!error && (isLoading || !showCards) ? <ScanWave label={t('hub.scanning')} /> : null}

                  {!error && !isLoading && showCards && visibleSkills.length === 0 ? (
                    <div className="hub-inline-state">
                      <p>{t('hub.noSkills')}</p>
                    </div>
                  ) : null}

                  {!error && !isLoading && showCards && visibleSkills.length > 0 ? (
                    <div className="hub-cards-scroll" key={`skills-${selectedHarness}`} aria-label={t('hub.skills')}>
                      <div className="hub-skill-grid">
                        {visibleSkills.map((skill, index) => {
                          const supportedHarnessIds = skillAgents(skill)
                          const supportedHarnesses = supportedHarnessIds.map((agentId) =>
                            installedAgents.find((agent) => agent.id.toLocaleLowerCase() === agentId.toLocaleLowerCase()),
                          )
                          const harnessNames = supportedHarnessIds.map((agentId, agentIndex) => supportedHarnesses[agentIndex]?.name ?? agentId)
                          return (
                            <motion.button
                              key={skill.id}
                              layoutId={`hub-skill-${skill.id}`}
                              type="button"
                              className="hub-skill-card"
                              aria-label={`${t('hub.openSkill')}: ${skill.displayName || skill.name}${harnessNames.length ? ` · ${harnessNames.join(', ')}` : ''}`}
                              onClick={() => setActiveSkillId(skill.id)}
                              initial={firstVisit && introStage === 'skills' ? { opacity: 0, scale: 0.78, rotate: index % 2 === 0 ? -2 : 2, filter: 'blur(8px)' } : { opacity: 0, scale: 0.92, filter: 'blur(5px)' }}
                              animate={{
                                opacity: activeSkill ? 0.18 : 1,
                                scale: activeSkill ? 0.96 : 1,
                                rotate: activeSkill ? (index % 2 === 0 ? -1 : 1) : 0,
                                filter: activeSkill ? 'blur(7px)' : 'blur(0px)',
                              }}
                              transition={{ duration: reduceMotion ? 0 : firstVisit && introStage === 'skills' ? 0.48 : 0.3, delay: reduceMotion ? 0 : firstVisit && introStage === 'skills' ? Math.min(index, 5) * 0.075 : Math.min(index, 5) * 0.025, type: 'spring', stiffness: 260, damping: 24 }}
                              whileHover={!activeSkill ? { y: -4, scale: 1.015 } : undefined}
                              whileTap={{ scale: 0.98 }}
                            >
                              <span className="hub-skill-name">{skill.displayName || skill.name}</span>
                              <span className="hub-skill-description">{cardDescription(skill, i18n.language, t('common.unknown'))}</span>
                              <span className="hub-card-harnesses" aria-hidden>
                                {supportedHarnesses.map((agent, agentIndex) => (
                                  <span key={`${skill.id}:${supportedHarnessIds[agentIndex]}`} className={`hub-card-harness-mark${supportedHarnessIds[agentIndex]?.toLocaleLowerCase() === selectedHarness.toLocaleLowerCase() ? ' is-current' : ''}`} title={harnessNames[agentIndex]}>
                                    <HarnessIcon id={agent?.id ?? supportedHarnessIds[agentIndex]} size={14} />
                                  </span>
                                ))}
                              </span>
                              <span className="hub-card-art" aria-hidden>
                                <i />
                                <i />
                                <i />
                              </span>
                            </motion.button>
                          )
                        })}
                      </div>
                    </div>
                  ) : null}

                  <AnimatePresence>
                    {activeSkill ? (
                      <motion.article
                        key={activeSkill.id}
                        layoutId={`hub-skill-${activeSkill.id}`}
                        className="hub-skill-detail"
                        initial={{ opacity: 0.86 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0, transition: { duration: 0.17 } }}
                        transition={{ layout: { type: 'spring', stiffness: 250, damping: 28 }, opacity: { duration: 0.2 } }}
                        aria-label={activeSkill.displayName || activeSkill.name}
                      >
                        <button type="button" className="hub-detail-back" onClick={() => setActiveSkillId(null)} aria-label={t('hub.backToHub')}>
                          <Icon name="chevron-right" size={17} />
                        </button>
                        <div className="hub-detail-art hub-card-art" aria-hidden><i /><i /><i /></div>
                        <div className="hub-detail-copy">
                          <p className="hub-detail-eyebrow">{t('hub.detail')}</p>
                          <h1>{activeSkill.displayName || activeSkill.name}</h1>
                          <p className="hub-detail-description">{cardDescription(activeSkill, i18n.language, t('common.unknown'))}</p>
                        </div>
                        <section className="hub-detail-section hub-detail-features">
                          <h2>{t('hub.features')}</h2>
                          {activeFeatures.length ? (
                            <ul className="hub-feature-list">
                              {activeFeatures.map((feature, index) => (
                                <li className="hub-feature-item" key={`${activeSkill.id}:feature:${index}`}>{feature}</li>
                              ))}
                            </ul>
                          ) : <p className="hub-feature-unknown">{t('common.unknown')}</p>}
                        </section>
                        <section className="hub-detail-section">
                          <h2>{t('hub.supportedHarnesses')}</h2>
                          <div className="hub-detail-harnesses">
                            {skillAgents(activeSkill).map((agentId) => {
                              const agent = installedAgents.find((item) => item.id === agentId)
                              return <span key={agentId} className={`hub-detail-harness harness-${agentId}`} title={agent?.name ?? agentId} aria-label={agent?.name ?? agentId}><HarnessIcon id={agentId} size={22} /></span>
                            })}
                            {!skillAgents(activeSkill).length ? <span className="hub-detail-local">{t('hub.noHarness')}</span> : null}
                          </div>
                        </section>
                        <section className="hub-detail-section hub-detail-source">
                          <h2>{t('hub.source')}</h2>
                          <div className="hub-source-links">
                            {activeSkill.source?.type === 'github' && activeSkill.source.url ? (
                              <a href={activeSkill.source.url} target="_blank" rel="noreferrer">GitHub <span aria-hidden>↗</span></a>
                            ) : <span>{t('hub.local')}</span>}
                            {githubReadmeUrl(activeSkill) ? <a href={githubReadmeUrl(activeSkill) ?? undefined} target="_blank" rel="noreferrer">README <span aria-hidden>↗</span></a> : null}
                          </div>
                        </section>
                      </motion.article>
                    ) : null}
                  </AnimatePresence>
                </div>
            </motion.div>
          ) : null}
        </motion.section>
      </LayoutGroup>

      {showSyncDialog ? (
        <MutualSyncDialog
          availableAgents={installedAgents}
          onClose={() => {
            setShowSyncDialog(false)
            agents.reload()
            skills.reload()
          }}
        />
      ) : null}
    </div>
  )
}
