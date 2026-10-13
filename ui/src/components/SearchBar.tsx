import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'

interface SearchBarProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

export function SearchBar({ value, onChange, placeholder }: SearchBarProps) {
  const { t } = useTranslation()

  return (
    <label className="search-field">
      <span className="search-icon"><Icon name="search" size={16} /></span>
      <span className="sr-only">{t('common.search')}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder ?? t('skills.searchPlaceholder')}
        className="search-input"
      />
    </label>
  )
}
