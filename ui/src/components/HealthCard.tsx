import { useTranslation } from 'react-i18next'
import type { Environment } from '../types/Environment'
import { Icon } from './Icon'

interface HealthCardProps {
  environment: Environment
  scanning: boolean
  scanStatus: 'idle' | 'scanning' | 'success' | 'error'
  scanMessage: string
  onRescan: () => void
  onMutualSync: () => void
}

export function HealthCard({ environment, scanning, scanStatus, scanMessage, onRescan, onMutualSync }: HealthCardProps) {
  const { t } = useTranslation()
  const healthy = environment.health >= 80 && environment.issueCount === 0
  const metrics = [
    { label: t('dashboard.connectedAgents'), value: environment.agentCount },
    { label: t('dashboard.activeSkills'), value: environment.skillCount },
    { label: t('dashboard.unsynced'), value: environment.unsyncedCount },
    { label: t('dashboard.attention'), value: environment.issueCount },
  ]

  return (
    <section className="workspace-overview" aria-labelledby="workspace-overview-title">
      <div className="overview-copy">
        <h1 id="workspace-overview-title" className="overview-title">
          {healthy ? t('dashboard.environmentReady') : t('dashboard.environmentNeedsAttention')}
        </h1>
        <p className="overview-description">{t('dashboard.environmentDescription')}</p>
        <div className="overview-actions">
          <button type="button" className="btn btn-primary" onClick={onRescan} disabled={scanning}>
            <Icon name="refresh" size={15} />
            {scanning ? t('dashboard.scanning') : t('dashboard.scanNow')}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onMutualSync} disabled={scanning}>
            <Icon name="refresh" size={15} />
            {t('dashboard.mutualSync')}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => { window.location.hash = '#/skills' }}>
            {t('dashboard.viewSkills')}
            <Icon name="arrow-right" size={15} />
          </button>
        </div>
        {scanStatus !== 'idle' ? (
          <div className={`scan-feedback scan-feedback--${scanStatus}`} role={scanStatus === 'error' ? 'alert' : 'status'}>
            <span className="scan-feedback-dot" />
            <span>{scanMessage}</span>
          </div>
        ) : null}
      </div>

      <div className="overview-health">
        <div className="health-status">
          <span className={`status-dot ${healthy ? 'status-dot--success' : 'status-dot--warning'}`} />
          {healthy ? t('common.ready') : t('dashboard.attention')}
        </div>
        <div className="health-value">
          <strong>{environment.health}</strong>
          <span>/ 100</span>
        </div>
        <div className="health-label">{t('dashboard.healthLabel')}</div>
        <div className="health-meter" aria-label={`${environment.health} / 100`}>
          <span style={{ width: `${Math.max(0, Math.min(100, environment.health))}%` }} />
        </div>
        <p className="health-note">{healthy ? t('dashboard.healthGood') : t('dashboard.healthNeedsAttention')}</p>
      </div>

      <div className="metric-grid">
        {metrics.map((metric) => (
          <div className="metric-cell" key={metric.label}>
            <div className="metric-label">{metric.label}</div>
            <div className="metric-value">{metric.value}</div>
          </div>
        ))}
      </div>
    </section>
  )
}
