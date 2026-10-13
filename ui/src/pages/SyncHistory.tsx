import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { Icon } from '../components/Icon'
import { useApi } from '../hooks/useApi'
import { getSyncHistory } from '../services/api'

function statusTone(status: string) {
  if (status === 'success') return 'history-status--success'
  if (status === 'failed' || status === 'rollback') return 'history-status--danger'
  if (status === 'warning_required') return 'history-status--warning'
  return ''
}

function stepTone(status: string) {
  if (status === 'success') return 'history-step--success'
  if (status === 'running') return 'history-step--running'
  if (status === 'failed') return 'history-step--failed'
  return ''
}

export function SyncHistory() {
  const { t } = useTranslation()
  const history = useApi(getSyncHistory)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (history.loading) return <LoadingSkeleton />

  if (history.error) {
    return (
      <div className="error-state" role="alert">
        <h1 className="error-state-title">{t('common.error')}</h1>
        <p className="error-state-copy">{history.error}</p>
        <button type="button" className="btn btn-secondary" style={{ marginTop: 18 }} onClick={history.reload}>{t('common.retry')}</button>
      </div>
    )
  }

  const items = history.data ?? []

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <h1 className="page-title">{t('syncHistory.title')}</h1>
          <p className="page-subtitle">{t('syncHistory.subtitle')}</p>
        </div>
        <span className="tag tag--muted">{items.length} {t('syncHistory.count')}</span>
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          <span className="library-empty-icon"><Icon name="clock" size={18} /></span>
          <h2 className="empty-state-title" style={{ marginTop: 15 }}>{t('syncHistory.noHistory')}</h2>
          <p className="empty-state-copy">{t('syncHistory.noHistoryHint')}</p>
        </div>
      ) : (
        <div className="history-list">
          {items.map((item, index) => {
            const itemId = item.id ?? `history-${index}`
            const open = selectedId === itemId
            const statusLabel = t(`status.${item.status}`) === `status.${item.status}` ? item.status : t(`status.${item.status}`)
            return (
              <div key={itemId} className="history-item">
                <button
                  type="button"
                  className="history-trigger"
                  aria-expanded={open}
                  onClick={() => setSelectedId(open ? null : itemId)}
                >
                  <span className="history-time">{item.startTime || t('appShell.waitingForScan')}</span>
                  <span>
                    <span className="history-skill">{item.skill || t('common.unknown')}</span>
                    <span className="history-route">
                      {item.sourceAgent ? <>{item.sourceAgent} <Icon name="arrow-right" size={12} /> </> : null}
                      {item.targetAgent || t('common.unknown')}
                    </span>
                  </span>
                  <span className={`history-status ${statusTone(item.status)}`}>
                    <span className={`status-dot ${statusTone(item.status).includes('success') ? 'status-dot--success' : statusTone(item.status).includes('danger') ? 'status-dot--danger' : statusTone(item.status).includes('warning') ? 'status-dot--warning' : ''}`} />
                    {statusLabel}
                    <Icon name={open ? 'chevron-down' : 'chevron-right'} size={13} />
                  </span>
                </button>
                {open ? (
                  <div className="history-details">
                    <p>{item.message || item.error || t('syncHistory.noDetails')}</p>
                    <div className="history-step-list">
                      {(item.steps ?? []).map((step) => (
                        <span key={step.name} className={`history-step ${stepTone(step.status)}`}>
                          {step.name}: {step.status}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
