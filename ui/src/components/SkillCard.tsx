import { useTranslation } from 'react-i18next'
import type { Skill } from '../types/Skill'
import { Icon } from './Icon'
import { SourceBadge } from './SourceBadge'
import { Tag } from './Tag'

interface SkillCardProps {
  skill: Skill
  index?: number
  onOpen: (skill: Skill) => void
}

function statusMeta(skill: Skill, t: (key: string) => string) {
  if (skill.status === 'disabled' || skill.enabled === false) {
    return { label: t('status.disabled'), className: '' }
  }
  if (skill.status === 'error') {
    return { label: t('status.error'), className: 'status-dot--danger' }
  }
  if (skill.status === 'missing') {
    return { label: t('status.missing'), className: 'status-dot--warning' }
  }
  return { label: t('status.enabled'), className: 'status-dot--success' }
}

export function SkillCard({ skill, onOpen }: SkillCardProps) {
  const { t, i18n } = useTranslation()
  const agents = skill.installedAgents?.length ? skill.installedAgents : skill.installed_agents ?? []
  const icon = skill.displayName?.charAt(0).toUpperCase() || skill.name?.charAt(0).toUpperCase() || 'S'
  const status = statusMeta(skill, t)
  const summary = skill.summaries?.[i18n.language] || t('common.unknown')

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(skill)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen(skill)
        }
      }}
      className="skill-record"
      aria-label={`${t('common.open')} ${skill.displayName || skill.name}`}
    >
      <div className="skill-record-head">
        <div className="skill-leading">
          <div className="skill-monogram" aria-hidden>{icon}</div>
          <div className="skill-title-wrap">
            <div className="skill-name">{skill.displayName || skill.name}</div>
            <div className="skill-id">{skill.name}</div>
          </div>
        </div>
        <SourceBadge source={skill.source} interactive={false} />
      </div>

      <p className="skill-summary">{summary}</p>

      <div className="skill-record-footer">
        <div className="skill-agents">
          <span className={`skill-agent-chip ${skill.inLibrary ? 'tag--accent' : ''}`}>
            <span className={`status-dot ${skill.inLibrary ? 'status-dot--success' : ''}`} />
            {skill.inLibrary ? t('common.inLibrary') : t('common.notInLibrary')}
          </span>
          <span className="skill-agent-chip">
            <span className={`status-dot ${status.className}`} />
            {status.label}
          </span>
          {agents.slice(0, 3).map((agent) => (
            <span className="skill-agent-chip" key={agent}>
              <span className="status-dot status-dot--success" />
              {agent}
            </span>
          ))}
          {skill.category ? <Tag tone="accent">{t(`categories.${skill.category.toLowerCase()}`)}</Tag> : null}
          {(skill.tags ?? []).slice(0, 2).map((tag) => <Tag key={tag} tone="muted">{tag}</Tag>)}
        </div>
        <span className="skill-arrow" aria-hidden><Icon name="arrow-right" size={16} /></span>
      </div>
    </article>
  )
}
