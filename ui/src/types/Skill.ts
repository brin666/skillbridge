import type { DeploymentState } from './Library'

export interface SkillSource {
  type: string
  url?: string
}

export interface InstalledLocation {
  path: string
  enabled: boolean
}


export interface Skill {
  id: string
  name: string
  displayName: string
  description: string
  summary: string
  summaries?: Record<string, string>
  features?: Record<string, string[]>
  category: string
  tags: string[]
  version: string | null
  source: SkillSource
  path: string
  installedAgents: string[]
  installed_agents?: string[]
  locations: Record<string, boolean>
  installedLocations: Record<string, InstalledLocation>
  installed_locations?: Record<string, InstalledLocation>
  files: string[]
  hash: string
  status: string
  enabled: boolean
  lastModified: string
  duplicateGroup: string
  duplicate_group?: string
  inLibrary?: boolean
  libraryHash?: string | null
  libraryPath?: string | null
  libraryDeployments?: Record<string, DeploymentState>
}
