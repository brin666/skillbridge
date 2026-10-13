import { useTranslation } from 'react-i18next'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { SourceBadge } from '../components/SourceBadge'
import { Tag } from '../components/Tag'
import { Icon } from '../components/Icon'
import { useApi } from '../hooks/useApi'
import { getLibrary } from '../services/api'
import type { LibrarySkill } from '../types/Library'

interface LibraryProps {
  onOpen: (skill: LibrarySkill) => void
}

export function Library({ onOpen }: LibraryProps) {
  const { t } = useTranslation()
  const library = useApi(getLibrary)

  if (library.loading) return <LoadingSkeleton />

  if (library.error) {
    return (
      <div className="error-state" role="alert">
        <h1 className="error-state-title">{t('common.error')}</h1>
        <p className="error-state-copy">{library.error}</p>
        <button type="button" className="btn btn-secondary" style={{ marginTop: 18 }} onClick={library.reload}>{t('common.retry')}</button>
      </div>
    )
  }

  const items = library.data ?? []

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <h1 className="page-title">{t('library.title')}</h1>
          <p className="page-subtitle">{items.length} {t('library.subtitle')}</p>
        </div>
        <div className="page-heading-actions">
          <button type="button" className="btn btn-secondary" onClick={() => { window.location.hash = '#/skills' }}>
            <Icon name="layers" size={15} />
            {t('dashboard.openSkills')}
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          <span className="library-empty-icon"><Icon name="library" size={18} /></span>
          <h2 className="empty-state-title" style={{ marginTop: 15 }}>{t('library.empty')}</h2>
          <p className="empty-state-copy">{t('library.emptyHint')}</p>
          <button type="button" className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => { window.location.hash = '#/skills' }}>
            {t('library.emptyAction')} <Icon name="arrow-right" size={15} />
          </button>
        </div>
      ) : (
        <section className="panel library-records" aria-label={t('library.title')}>
          {items.map((skill) => {
            const states = Object.values(skill.deployments ?? {})
            const same = states.filter((state) => state.status === 'same').length
            const notDeployed = states.filter((state) => state.status === 'not_deployed').length
            const diverged = states.filter((state) => state.status === 'diverged').length
            return (
              <button key={skill.id} type="button" className="library-record" onClick={() => onOpen(skill)}>
                <div>
                  <div className="library-record-title">{skill.displayName || skill.name}</div>
                  <p className="library-record-summary">{skill.summary || t('common.noData')}</p>
                  <div className="library-record-meta">
                    <SourceBadge source={skill.source} interactive={false} />
                    {skill.category ? <Tag tone="accent">{skill.category}</Tag> : null}
                    {(skill.tags ?? []).slice(0, 3).map((tag) => <Tag key={tag} tone="muted">{tag}</Tag>)}
                  </div>
                </div>
                <div className="deployment-counts" aria-label={t('library.deployments')}>
                  <span><strong>{same}</strong>{t('library.sameCount')}</span>
                  <span><strong>{notDeployed}</strong>{t('library.notDeployedCount')}</span>
                  <span><strong>{diverged}</strong>{t('library.divergedCount')}</span>
                  <Icon name="chevron-right" size={16} />
                </div>
              </button>
            )
          })}
        </section>
      )}
    </div>
  )
}
