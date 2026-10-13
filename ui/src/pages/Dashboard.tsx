import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useApi } from '../hooks/useApi'
import { getAgents, getEnvironment, getLibrary, getSkills, rescanEnvironment } from '../services/api'
import type { Skill } from '../types/Skill'
import { AgentCard } from '../components/AgentCard'
import { HealthCard } from '../components/HealthCard'
import { Icon } from '../components/Icon'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { SkillCard } from '../components/SkillCard'
import { MutualSyncDialog } from '../components/MutualSyncDialog'

interface DashboardProps {
  onOpenSkill: (skill: Skill) => void
}

export function Dashboard({ onOpenSkill }: DashboardProps) {
  const { t } = useTranslation()
  const environment = useApi(getEnvironment)
  const agents = useApi(getAgents)
  const skills = useApi(getSkills)
  const library = useApi(getLibrary)
  const [scanning, setScanning] = useState(false)
  const [scanStatus, setScanStatus] = useState<'idle' | 'scanning' | 'success' | 'error'>('idle')
  const [scanMessage, setScanMessage] = useState('')
  const [showMutualSync, setShowMutualSync] = useState(false)

  const handleRescan = async () => {
    if (scanning) return
    setScanning(true)
    setScanStatus('scanning')
    setScanMessage(t('dashboard.scanProgress'))
    try {
      const result = await rescanEnvironment()
      environment.reload()
      agents.reload()
      skills.reload()
      library.reload()
      setScanStatus('success')
      setScanMessage(t('dashboard.scanCompleteDetail', { agents: result.agents, skills: result.skills }))
    } catch (error: unknown) {
      setScanStatus('error')
      setScanMessage(error instanceof Error ? error.message : t('dashboard.scanFailed'))
    } finally {
      setScanning(false)
    }
  }

  if (environment.loading || agents.loading || skills.loading || library.loading) {
    return <LoadingSkeleton />
  }

  if (environment.error || agents.error || skills.error || library.error) {
    return (
      <div className="error-state" role="alert">
        <h1 className="error-state-title">{t('common.error')}</h1>
        <p className="error-state-copy">{environment.error ?? agents.error ?? skills.error ?? library.error}</p>
        <button type="button" className="btn btn-secondary" style={{ marginTop: 18 }} onClick={handleRescan} disabled={scanning}>
          <Icon name="refresh" size={15} />
          {t('common.retry')}
        </button>
      </div>
    )
  }

  const env = environment.data ?? { health: 0, agentCount: 0, skillCount: 0, unsyncedCount: 0, issueCount: 0 }
  const agentItems = agents.data ?? []
  const skillItems = skills.data ?? []
  const libraryItems = library.data ?? []
  const sameCount = libraryItems.filter((skill) => Object.values(skill.deployments ?? {}).some((deployment) => deployment.status === 'same')).length
  const notDeployedCount = libraryItems.filter((skill) => Object.values(skill.deployments ?? {}).some((deployment) => deployment.status === 'not_deployed')).length
  const divergedCount = libraryItems.filter((skill) => Object.values(skill.deployments ?? {}).some((deployment) => deployment.status === 'diverged')).length

  return (
    <div className="page-stack">
      <HealthCard
        environment={env}
        scanning={scanning}
        scanStatus={scanStatus}
        scanMessage={scanMessage}
        onRescan={() => { void handleRescan() }}
        onMutualSync={() => setShowMutualSync(true)}
      />

      <div className="dashboard-grid">
        <section className="panel" aria-labelledby="agent-matrix-title">
          <div className="panel-header">
            <div>
              <h2 id="agent-matrix-title" className="panel-title">{t('dashboard.agentMatrix')}</h2>
              <p className="panel-subtitle">{t('dashboard.agentMatrixHint')}</p>
            </div>
            <span className="tag tag--success">{env.agentCount} {t('dashboard.connectedAgents')}</span>
          </div>
          <div className="agent-list">
            {agentItems.length ? agentItems.map((agent) => <AgentCard key={agent.id} agent={agent} />) : (
              <div className="empty-state" style={{ border: 0, borderRadius: 0 }}>
                <p className="empty-state-title">{t('dashboard.noAgents')}</p>
              </div>
            )}
          </div>
        </section>

        <section className="panel" aria-labelledby="library-status-title">
          <div className="panel-header">
            <div>
              <h2 id="library-status-title" className="panel-title">{t('dashboard.libraryStatus')}</h2>
              <p className="panel-subtitle">{t('dashboard.libraryStatusHint')}</p>
            </div>
            <button type="button" className="panel-link" onClick={() => { window.location.hash = '#/library' }}>
              {t('common.open')} <Icon name="arrow-right" size={14} />
            </button>
          </div>
          <div className="library-summary">
            <h3 className="library-summary-title">{libraryItems.length ? `${libraryItems.length} ${t('dashboard.managedLibrary')}` : t('dashboard.libraryEmpty')}</h3>
            <p className="library-summary-copy">{libraryItems.length ? t('dashboard.libraryStatusHint') : t('dashboard.libraryEmptyHint')}</p>
            {libraryItems.length === 0 ? (
              <div className="library-empty">
                <span className="library-empty-icon"><Icon name="library" size={16} /></span>
                <p className="library-empty-title">{t('dashboard.libraryEmpty')}</p>
                <p className="library-empty-copy">{t('dashboard.libraryEmptyHint')}</p>
                <button type="button" className="btn btn-secondary" style={{ marginTop: 14 }} onClick={() => { window.location.hash = '#/skills' }}>
                  {t('dashboard.openSkills')} <Icon name="arrow-right" size={14} />
                </button>
              </div>
            ) : null}
          </div>
          <div className="library-stats">
            <div className="library-stat"><div className="library-stat-value">{sameCount}</div><div className="library-stat-label">{t('dashboard.fullyDeployed')}</div></div>
            <div className="library-stat"><div className="library-stat-value">{notDeployedCount}</div><div className="library-stat-label">{t('dashboard.notDeployed')}</div></div>
            <div className="library-stat"><div className="library-stat-value">{divergedCount}</div><div className="library-stat-label">{t('dashboard.diverged')}</div></div>
          </div>
        </section>
      </div>

      <section className="panel skill-index-panel" aria-labelledby="skill-index-title">
        <div className="panel-header">
          <div>
            <h2 id="skill-index-title" className="panel-title">{t('dashboard.skillIndex')}</h2>
            <p className="panel-subtitle">{t('dashboard.skillIndexHint')} · {t('dashboard.scanSource')}</p>
          </div>
          {skillItems.length ? (
            <button type="button" className="panel-link" onClick={() => { window.location.hash = '#/skills' }}>
              {t('dashboard.viewSkills')} <Icon name="arrow-right" size={14} />
            </button>
          ) : null}
        </div>
        {skillItems.length ? (
          <div className="skill-records">
            {skillItems.slice(0, 8).map((skill) => <SkillCard key={skill.id} skill={skill} onOpen={onOpenSkill} />)}
          </div>
        ) : (
          <div className="empty-state" style={{ border: 0, borderRadius: 0 }}>
            <p className="empty-state-title">{t('dashboard.noSkillsFound')}</p>
            <p className="empty-state-copy">{t('dashboard.scanHint')}</p>
          </div>
        )}
      </section>
      {showMutualSync ? (
        <MutualSyncDialog
          availableAgents={agentItems.filter((agent) => agent.installed)}
          onClose={() => {
            setShowMutualSync(false)
            environment.reload()
            agents.reload()
            skills.reload()
            library.reload()
          }}
        />
      ) : null}
    </div>
  )
}
