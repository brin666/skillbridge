import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { SourceBadge } from '../components/SourceBadge'
import { Tag } from '../components/Tag'
import { Icon } from '../components/Icon'
import { useApi } from '../hooks/useApi'
import { deployLibrarySkill, getAgents, getLibrarySkill, removeLibrarySkill } from '../services/api'

interface LibrarySkillDetailProps {
  skillId: string
  onBack: () => void
}

export function LibrarySkillDetail({ skillId, onBack }: LibrarySkillDetailProps) {
  const { t } = useTranslation()
  const fetcher = useCallback(() => getLibrarySkill(skillId), [skillId])
  const skill = useApi(fetcher)
  const agents = useApi(getAgents)
  const [selected, setSelected] = useState<string[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (skill.loading) return <LoadingSkeleton />

  if (skill.error || !skill.data) {
    return (
      <div className="error-state" role="alert">
        <h1 className="error-state-title">{t('errors.LIBRARY_SKILL_NOT_FOUND')}</h1>
        <p className="error-state-copy">{skill.error}</p>
        <button type="button" className="btn btn-secondary" style={{ marginTop: 18 }} onClick={onBack}>
          <Icon name="chevron-right" size={15} style={{ transform: 'rotate(180deg)' }} />
          {t('common.back')}
        </button>
      </div>
    )
  }

  const data = skill.data
  const installedAgents = (agents.data ?? []).filter((agent) => agent.installed)
  const deployments = data.deployments ?? {}
  const statusLabel = (status: string) => {
    const key = status === 'not_deployed' ? 'notDeployed' : status
    const translated = t(`status.${key}`)
    return translated === `status.${key}` ? status : translated
  }

  const toggle = (agentId: string) => {
    setSelected((current) => current.includes(agentId) ? current.filter((id) => id !== agentId) : [...current, agentId])
  }

  const handleDeploy = async () => {
    if (selected.length === 0) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await deployLibrarySkill(skillId, selected, false, false)
      const warnings = (result.tasks ?? []).filter((task) => task.status === 'warning_required')
      setMessage(warnings.length ? t('library.warningRequired') : t('library.deployStarted'))
      skill.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async () => {
    if (!window.confirm(t('library.removeConfirm'))) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await removeLibrarySkill(skillId)
      setMessage(result.message)
      setTimeout(onBack, 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="detail-page">
      <button type="button" className="back-link" onClick={onBack}>
        <Icon name="chevron-right" size={15} style={{ transform: 'rotate(180deg)' }} />
        {t('common.back')}
      </button>

      <div className="detail-layout">
        <main className="detail-main">
          <div className="detail-hero">
            <div className="detail-title-row">
              <div className="detail-monogram" aria-hidden>{(data.displayName || data.name || 'S').charAt(0).toUpperCase()}</div>
              <div>
                <h1 className="detail-title">{data.displayName || data.name}</h1>
                <p className="detail-id">{data.name} · {t('nav.library')}</p>
              </div>
              <div style={{ marginLeft: 'auto' }}><SourceBadge source={data.source} /></div>
            </div>
            <p className="detail-summary">{data.summary || t('common.noData')}</p>
            <div className="detail-tags">
              {data.category ? <Tag tone="accent">{data.category}</Tag> : null}
              {(data.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
            </div>
          </div>

          <section className="detail-section">
            <h2 className="detail-section-title">{t('library.deployments')}</h2>
            <div className="detail-list">
              {installedAgents.length ? installedAgents.map((agent) => {
                const state = deployments[agent.id]
                const tone = state?.status === 'same' ? 'status-dot--success' : state?.status === 'diverged' ? 'status-dot--warning' : ''
                return (
                  <label key={agent.id} className="detail-list-row">
                    <span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                      <input type="checkbox" checked={selected.includes(agent.id)} onChange={() => toggle(agent.id)} style={{ accentColor: 'var(--accent)' }} />
                      <span>{agent.name}</span>
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: 'var(--muted)' }}>
                      <span className={`status-dot ${tone}`} />
                      {statusLabel(state?.status ?? 'not_deployed')}
                    </span>
                  </label>
                )
              }) : <p className="page-subtitle">{t('library.noInstalledAgents')}</p>}
            </div>
          </section>

          <section className="detail-section">
            <h2 className="detail-section-title">{t('library.libraryPath')}</h2>
            <div className="detail-path">{data.libraryPath}</div>
          </section>

          {message ? <div className="notice notice-success" style={{ margin: '0 28px 22px' }}>{message}</div> : null}
          {error ? <div className="notice notice-error" style={{ margin: '0 28px 22px' }}>{error}</div> : null}
        </main>

        <aside className="detail-side">
          <section className="detail-side-panel">
            <h2 className="detail-side-title">{t('skillDetail.actions')}</h2>
            <div className="detail-actions">
              <button type="button" className="btn btn-primary" disabled={selected.length === 0 || busy} onClick={() => { void handleDeploy() }}>
                <Icon name="layers" size={15} />
                {t('library.deployToSelected')}
              </button>
              <button type="button" className="btn btn-danger" disabled={busy} onClick={() => { void handleRemove() }}>
                <Icon name="x" size={15} />
                {t('library.removeFromLibrary')}
              </button>
            </div>
          </section>
          <section className="detail-side-panel">
            <h2 className="detail-side-title">{t('common.status')}</h2>
            <div className="detail-status"><span className="status-dot status-dot--success" />{t('library.managedBy')}</div>
            <p className="panel-subtitle">{t('library.libraryPath')}</p>
          </section>
        </aside>
      </div>
    </div>
  )
}
