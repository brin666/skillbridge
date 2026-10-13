import { useTranslation } from 'react-i18next'
import type { SkillSource } from '../types/Skill'
import { Icon } from './Icon'

interface SourceBadgeProps {
  source: SkillSource
  interactive?: boolean
}

export function SourceBadge({ source, interactive = true }: SourceBadgeProps) {
  const { t } = useTranslation()
  const label = source.type === 'github' ? 'GitHub' : source.type === 'git' ? 'Git' : `${t('common.unknown')} ${t('common.source')}`

  if (interactive && source.url) {
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noreferrer"
        className="source-badge source-badge--link"
        onClick={(event) => event.stopPropagation()}
      >
        {label}
        <Icon name="external" size={11} />
      </a>
    )
  }

  return <span className="source-badge">{label}</span>
}
