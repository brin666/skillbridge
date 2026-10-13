import { useTranslation } from 'react-i18next'
import type { Agent } from '../types/Agent'

interface AgentCardProps {
  agent: Agent
  index?: number
}

export function AgentCard({ agent }: AgentCardProps) {
  const { t } = useTranslation()
  const initial = agent.name.charAt(0).toUpperCase()

  return (
    <div className="agent-row">
      <div className="agent-avatar" aria-hidden>{initial}</div>
      <div className="agent-main">
        <div className="agent-name-line">
          <span className="agent-name">{agent.name}</span>
          <span className={`status-dot ${agent.installed ? 'status-dot--success' : ''}`} />
        </div>
        <div className="agent-meta">
          {agent.installed ? t('status.installed') : t('status.notInstalled')}
          {agent.version ? ` · ${agent.version}` : ''}
        </div>
      </div>
      <div className="agent-count">
        {agent.skillCount}
        <small>{t('dashboard.skills')}</small>
      </div>
    </div>
  )
}
