import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SearchBar } from '../components/SearchBar'
import { SkillCard } from '../components/SkillCard'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { useApi } from '../hooks/useApi'
import { getSkills } from '../services/api'
import type { Skill } from '../types/Skill'

interface SkillsProps {
  onOpenSkill: (skill: Skill) => void
}

const CATEGORY_KEYS = ['all', 'development', 'document', 'browser', 'automation', 'data', 'other']
type SortKey = 'name' | 'agents' | 'default'

export function Skills({ onOpenSkill }: SkillsProps) {
  const { t } = useTranslation()
  const skills = useApi(getSkills)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [sort, setSort] = useState<SortKey>('default')

  const filtered = useMemo(() => {
    const list = [...(skills.data ?? [])]
    const keyword = search.trim().toLowerCase()
    const next = list.filter((skill) => {
      const haystack = [skill.name, skill.displayName, skill.summary, skill.description, skill.category, ...(skill.tags ?? [])].join(' ').toLowerCase()
      if (keyword && !haystack.includes(keyword)) return false
      if (category !== 'all' && (skill.category || 'other') !== category) return false
      return true
    })

    if (sort === 'name') next.sort((a, b) => (a.displayName || a.name).localeCompare(b.displayName || b.name))
    if (sort === 'agents') next.sort((a, b) => (b.installedAgents?.length ?? 0) - (a.installedAgents?.length ?? 0))
    return next
  }, [skills.data, search, category, sort])

  if (skills.loading) return <LoadingSkeleton />

  if (skills.error) {
    return (
      <div className="error-state" role="alert">
        <h1 className="error-state-title">{t('common.error')}</h1>
        <p className="error-state-copy">{skills.error}</p>
        <button type="button" className="btn btn-secondary" style={{ marginTop: 18 }} onClick={skills.reload}>
          {t('common.retry')}
        </button>
      </div>
    )
  }

  return (
    <div className="page-stack skills-page">
      <div className="page-heading">
        <div>
          <h1 className="page-title">{t('skills.title')}</h1>
          <p className="page-subtitle">{t('skills.subtitle')} · {skills.data?.length ?? 0} {t('skills.installedAcross')}</p>
        </div>
        <div className="page-heading-actions">
          <span className="tag tag--success">{filtered.length} {t('skills.resultCount')}</span>
        </div>
      </div>

      <div className="filter-toolbar">
        <SearchBar value={search} onChange={setSearch} placeholder={t('skills.searchHint')} />
        <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)} className="select-field" aria-label={t('common.details')}>
          <option value="default">{t('skills.sortDefault')}</option>
          <option value="name">{t('skills.sortName')}</option>
          <option value="agents">{t('skills.sortAgents')}</option>
        </select>
        {search || category !== 'all' || sort !== 'default' ? (
          <button type="button" className="btn btn-quiet" onClick={() => { setSearch(''); setCategory('all'); setSort('default') }}>
            {t('skills.clearFilters')}
          </button>
        ) : null}
      </div>

      <div className="filter-tabs" role="tablist" aria-label={t('common.category', { defaultValue: 'Category' })}>
        {CATEGORY_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={category === key}
            onClick={() => setCategory(key)}
            className={`filter-tab ${category === key ? 'is-active' : ''}`}
          >
            {t(`categories.${key}`)}
          </button>
        ))}
      </div>

      <div className="result-meta">
        <span>{filtered.length} {t('skills.resultCount')}</span>
        <span>{t('dashboard.scanSource')}</span>
      </div>

      {filtered.length ? (
        <section className="panel skill-index-panel" aria-label={t('skills.title')}>
          <div className="skill-records">
            {filtered.map((skill) => <SkillCard key={skill.id} skill={skill} onOpen={onOpenSkill} />)}
          </div>
        </section>
      ) : (
        <div className="empty-state">
          <h2 className="empty-state-title">{t('skills.noMatching')}</h2>
          <p className="empty-state-copy">{t('skills.noMatchingHint')}</p>
        </div>
      )}
    </div>
  )
}
