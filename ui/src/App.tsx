import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dashboard } from './pages/Dashboard'
import { Hub } from './pages/Hub'
import { Library } from './pages/Library'
import { LibrarySkillDetail } from './pages/LibrarySkillDetail'
import { Skills } from './pages/Skills'
import { SkillDetail } from './pages/SkillDetail'
import { SyncHistory } from './pages/SyncHistory'
import { currentLanguage, setLanguage } from './i18n'
import { Icon, type IconName } from './components/Icon'
import type { LibrarySkill } from './types/Library'
import type { Skill } from './types/Skill'

type Route =
  | { page: 'hub' }
  | { page: 'dashboard' }
  | { page: 'skills' }
  | { page: 'skill'; skillId: string }
  | { page: 'library' }
  | { page: 'librarySkill'; skillId: string }
  | { page: 'history' }

function parseHash(): Route {
  const hash = window.location.hash.replace(/^#/, '')
  const parts = hash.split('/').filter(Boolean)
  if (parts[0] === 'skills' && parts[1]) {
    return { page: 'skill', skillId: decodeURIComponent(parts[1]) }
  }
  if (parts[0] === 'skills') {
    return { page: 'skills' }
  }
  if (parts[0] === 'library' && parts[1]) {
    return { page: 'librarySkill', skillId: decodeURIComponent(parts[1]) }
  }
  if (parts[0] === 'library') {
    return { page: 'library' }
  }
  if (parts[0] === 'sync' || parts[0] === 'history') {
    return { page: 'history' }
  }
  if (parts[0] === 'dashboard') {
    return { page: 'dashboard' }
  }
  return { page: 'hub' }
}

interface NavItem {
  key: 'dashboard' | 'skills' | 'library' | 'history'
  icon: IconName
  label: string
  hash: string
}

export default function App() {
  const { t } = useTranslation()
  const [route, setRoute] = useState<Route>(() => parseHash())
  const [lang, setLang] = useState(currentLanguage())

  useEffect(() => {
    const onHashChange = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const toggleLanguage = () => {
    const next = lang === 'zh-CN' ? 'en-US' : 'zh-CN'
    setLanguage(next)
    setLang(next)
  }

  const openSkill = (skill: Skill) => {
    window.location.hash = `#/skills/${encodeURIComponent(skill.id)}`
  }

  const openLibrarySkill = (skill: LibrarySkill) => {
    window.location.hash = `#/library/${encodeURIComponent(skill.id)}`
  }

  const goBack = () => {
    window.location.hash = '#/skills'
  }

  const goLibraryBack = () => {
    window.location.hash = '#/library'
  }

  const navItems = useMemo<NavItem[]>(() => [
    { key: 'dashboard', icon: 'grid', label: t('nav.dashboard'), hash: '#/dashboard' },
    { key: 'skills', icon: 'layers', label: t('nav.skills'), hash: '#/skills' },
    { key: 'library', icon: 'library', label: t('nav.library'), hash: '#/library' },
    { key: 'history', icon: 'activity', label: t('nav.history'), hash: '#/sync' },
  ], [t])

  const pageTitle = route.page === 'dashboard'
    ? t('nav.dashboard')
    : route.page === 'skills' || route.page === 'skill'
      ? t('nav.skills')
      : route.page === 'library' || route.page === 'librarySkill'
        ? t('nav.library')
        : t('nav.history')

  const isActive = (key: NavItem['key']) => {
    if (key === 'dashboard') return route.page === 'dashboard'
    if (key === 'skills') return route.page === 'skills' || route.page === 'skill'
    if (key === 'library') return route.page === 'library' || route.page === 'librarySkill'
    return route.page === 'history'
  }

  if (route.page === 'hub') {
    return <Hub onOpenDashboard={() => { window.location.hash = '#/dashboard' }} />
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <button type="button" className="sidebar-brand" onClick={() => { window.location.hash = '#/' }}>
          <span className="brand-mark">SB</span>
          <span>
            <span className="brand-name">SkillBridge</span>
            <span className="brand-subtitle">{t('appShell.workspaceSubtitle')}</span>
          </span>
        </button>

        <p className="sidebar-section-title">{t('appShell.navigation')}</p>
        <nav className="sidebar-nav" aria-label={t('appShell.navigation')}>
          {navItems.slice(0, 1).map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => { window.location.hash = item.hash }}
              className={`sidebar-nav-item ${isActive(item.key) ? 'is-active' : ''}`}
            >
              <span className="sidebar-nav-icon"><Icon name={item.icon} size={17} /></span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <p className="sidebar-section-title" style={{ marginTop: 26 }}>{t('appShell.manage')}</p>
        <nav className="sidebar-nav" aria-label={t('appShell.manage')}>
          {navItems.slice(1, 3).map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => { window.location.hash = item.hash }}
              className={`sidebar-nav-item ${isActive(item.key) ? 'is-active' : ''}`}
            >
              <span className="sidebar-nav-icon"><Icon name={item.icon} size={17} /></span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <p className="sidebar-section-title" style={{ marginTop: 26 }}>{t('appShell.insights')}</p>
        <nav className="sidebar-nav" aria-label={t('appShell.insights')}>
          {navItems.slice(3).map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => { window.location.hash = item.hash }}
              className={`sidebar-nav-item ${isActive(item.key) ? 'is-active' : ''}`}
            >
              <span className="sidebar-nav-icon"><Icon name={item.icon} size={17} /></span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className="status-dot status-dot--success" />
            <p>
              {t('appShell.systemOnline')}
              <small>{t('common.localOnly')}</small>
            </p>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div className="topbar-breadcrumb">
            <span>{t('appShell.pageContext')}</span>
            <span aria-hidden>/</span>
            <span className="topbar-context">{pageTitle}</span>
          </div>
          <div className="topbar-actions">
            <span className="topbar-pill">
              <span className="status-dot status-dot--success" />
              {t('appShell.systemOnline')}
            </span>
            <button type="button" className="language-button" onClick={toggleLanguage}>
              <Icon name="globe" size={14} />
              <span>{t('nav.language')}</span>
            </button>
          </div>
        </header>

        <main className="content">
          <div className="content-inner">
            {route.page === 'dashboard' ? <Dashboard onOpenSkill={openSkill} /> : null}
            {route.page === 'skills' ? <Skills onOpenSkill={openSkill} /> : null}
            {route.page === 'skill' ? <SkillDetail skillId={route.skillId} onBack={goBack} /> : null}
            {route.page === 'library' ? <Library onOpen={openLibrarySkill} /> : null}
            {route.page === 'librarySkill' ? <LibrarySkillDetail skillId={route.skillId} onBack={goLibraryBack} /> : null}
            {route.page === 'history' ? <SyncHistory /> : null}
          </div>
        </main>
      </div>
    </div>
  )
}
