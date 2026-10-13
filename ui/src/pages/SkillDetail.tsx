import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { SourceBadge } from '../components/SourceBadge'
import { SyncCheckDialog } from '../components/SyncCheckDialog'
import { Tag } from '../components/Tag'
import { Icon } from '../components/Icon'
import { useApi } from '../hooks/useApi'
import {
  disableSkill,
  enableSkill,
  getAgents,
  getSkill,
  importSkillToLibrary,
  openSkillFile,
  openSkillFolder,
  uninstallSkill,
} from '../services/api'

interface SkillDetailProps {
  skillId: string
  onBack: () => void
}

export function SkillDetail({ skillId, onBack }: SkillDetailProps) {
  const { t, i18n } = useTranslation()
  const fetcher = useCallback(() => getSkill(skillId), [skillId])
  const skill = useApi(fetcher)
  const agentList = useApi(getAgents)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showSyncDialog, setShowSyncDialog] = useState(false)

  const runAction = async (action: () => Promise<unknown>, successMessage?: string) => {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      await action()
      if (successMessage) setMessage(successMessage)
      skill.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleUninstall = async () => {
    if (!window.confirm(t('common.uninstall'))) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await uninstallSkill(skillId)
      onBack()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.failed'))
      setBusy(false)
    }
  }

  if (skill.loading) return <LoadingSkeleton />

  if (skill.error || !skill.data) {
    return (
      <div className="error-state" role="alert">
        <h1 className="error-state-title">{t('skillDetail.notFound')}</h1>
        <p className="error-state-copy">{skill.error}</p>
        <button type="button" className="btn btn-secondary" style={{ marginTop: 18 }} onClick={onBack}>
          <Icon name="chevron-right" size={15} style={{ transform: 'rotate(180deg)' }} />
          {t('common.back')}
        </button>
      </div>
    )
  }

  const data = skill.data
  const agents = data.installedAgents?.length ? data.installedAgents : data.installed_agents ?? []
  const files = data.files ?? []
  const scripts = files.filter((file) => file.startsWith('scripts/'))
  const references = files.filter((file) => file.startsWith('references/'))
  const disabled = data.status === 'disabled' || data.enabled === false
  const statusLabel = data.status === 'error' ? t('status.error') : data.status === 'missing' ? t('status.missing') : disabled ? t('status.disabled') : t('status.enabled')
  const statusTone = data.status === 'error' ? 'status-dot--danger' : data.status === 'missing' ? 'status-dot--warning' : disabled ? '' : 'status-dot--success'
  const sourceAgent = agents[0] ?? ''
  const localizedFeatures = (data.features?.[i18n.language] ?? []).filter(Boolean)

  const handleAddToLibrary = async () => {
    if (!sourceAgent) {
      setError(t('skillDetail.noSourceAgent'))
      return
    }
    await runAction(() => importSkillToLibrary(skillId, sourceAgent), t('skillDetail.addedToLibrary'))
  }

  return (
    <div className="detail-page">
      <button type="button" className="back-link" onClick={onBack}>
        <Icon name="chevron-right" size={15} style={{ transform: 'rotate(180deg)' }} />
        {t('skillDetail.backToIndex')}
      </button>

      <div className="detail-layout">
        <main className="detail-main">
          <div className="detail-hero">
            <div className="detail-title-row">
              <div className="detail-monogram" aria-hidden>{(data.displayName || data.name || 'S').charAt(0).toUpperCase()}</div>
              <div>
                <h1 className="detail-title">{data.displayName || data.name}</h1>
                <p className="detail-id">{data.name}</p>
              </div>
              <div style={{ marginLeft: 'auto' }}><SourceBadge source={data.source} /></div>
            </div>
            <div className="detail-status"><span className={`status-dot ${statusTone}`} />{statusLabel}</div>
            <p className="detail-summary">{data.summaries?.[i18n.language] || t('common.unknown')}</p>
            <div className="detail-tags">
              {data.category ? <Tag tone="accent">{t(`categories.${data.category.toLowerCase()}`)}</Tag> : null}
              {(data.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
              {data.inLibrary ? <Tag tone="success">{t('common.managedByLibrary')}</Tag> : null}
            </div>
          </div>

          <section className="detail-section">
            <h2 className="detail-section-title">{t('skillDetail.features')}</h2>
            {localizedFeatures.length ? (
              <ul className="detail-feature-list">
                {localizedFeatures.map((feature, index) => <li key={`${data.id}:feature:${index}`}>{feature}</li>)}
              </ul>
            ) : <p className="detail-feature-unknown">{t('common.unknown')}</p>}
          </section>

          <section className="detail-section">
            <h2 className="detail-section-title">{t('skillDetail.runtime')}</h2>
            <div className="detail-list">
              {agents.length ? agents.map((agent) => (
                <div key={agent} className="detail-list-row">
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}><span className="status-dot status-dot--success" />{agent}</span>
                  <small>{t('status.installed')}</small>
                </div>
              )) : <p className="page-subtitle">{t('skillDetail.noInstalledAgents')}</p>}
            </div>
          </section>

          <section className="detail-section">
            <h2 className="detail-section-title">{t('skillDetail.files')}</h2>
            <div className="detail-list">
              <div className="detail-list-row"><span>SKILL.md</span><small className="detail-status" style={{ marginTop: 0 }}><span className="status-dot status-dot--success" />{t('common.ready')}</small></div>
              <div className="detail-list-row"><span>scripts/</span><small>{scripts.length} {t('common.details')}</small></div>
              <div className="detail-list-row"><span>references/</span><small>{references.length} {t('common.details')}</small></div>
            </div>
          </section>

          <section className="detail-section">
            <h2 className="detail-section-title">{t('skillDetail.location')}</h2>
            <div className="detail-path">{data.path}</div>
          </section>

          {message ? <div className="notice notice-success" style={{ margin: '0 28px 22px' }}>{message}</div> : null}
          {error ? <div className="notice notice-error" style={{ margin: '0 28px 22px' }}>{error}</div> : null}
        </main>

        <aside className="detail-side">
          <section className="detail-side-panel">
            <h2 className="detail-side-title">{t('skillDetail.actions')}</h2>
            <div className="detail-actions">
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => { void runAction(() => openSkillFile(skillId), t('common.openSkillMd')) }}>
                <Icon name="code" size={15} />{t('skillDetail.openFileAction')}
              </button>
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => { void runAction(() => openSkillFolder(skillId), t('common.openFolder')) }}>
                <Icon name="folder" size={15} />{t('skillDetail.openFolderAction')}
              </button>
              {disabled ? (
                <button type="button" className="btn btn-success" disabled={busy} onClick={() => { void runAction(() => enableSkill(skillId), t('skillDetail.enableAction')) }}>
                  <Icon name="check" size={15} />{t('skillDetail.enableAction')}
                </button>
              ) : (
                <button type="button" className="btn btn-warning" disabled={busy} onClick={() => { void runAction(() => disableSkill(skillId), t('skillDetail.disableAction')) }}>
                  <Icon name="shield" size={15} />{t('skillDetail.disableAction')}
                </button>
              )}
              <button type="button" className="btn btn-danger" disabled={busy} onClick={() => { void handleUninstall() }}>
                <Icon name="x" size={15} />{t('skillDetail.uninstallAction')}
              </button>
              {data.inLibrary ? (
                <span className="tag tag--success" style={{ minHeight: 38, justifyContent: 'center' }}>{t('common.managedByLibrary')}</span>
              ) : (
                <button type="button" className="btn btn-secondary" disabled={busy || !sourceAgent} onClick={() => { void handleAddToLibrary() }}>
                  <Icon name="library" size={15} />{t('skillDetail.addToLibraryAction')}
                </button>
              )}
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setShowSyncDialog(true)}>
                <Icon name="refresh" size={15} />{t('skillDetail.syncAction')}
              </button>
            </div>
          </section>
          <section className="detail-side-panel">
            <h2 className="detail-side-title">{t('common.source')}</h2>
            <div style={{ marginTop: 13 }}><SourceBadge source={data.source} /></div>
            <p className="detail-path" style={{ marginTop: 12 }}>{data.path}</p>
          </section>
        </aside>
      </div>

      {showSyncDialog ? (
        <SyncCheckDialog
          skillId={skillId}
          skillName={data.displayName || data.name}
          agents={agentList.data ?? []}
          onClose={() => setShowSyncDialog(false)}
        />
      ) : null}
    </div>
  )
}
