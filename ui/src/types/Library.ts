export interface DeploymentState {
  installed: boolean
  sameHash: boolean
  path: string
  status: 'same' | 'diverged' | 'not_deployed' | 'disabled' | 'unknown'
}

export interface LibrarySkill {
  id: string
  name: string
  displayName: string
  summary: string
  category: string
  tags: string[]
  libraryPath: string
  hash: string
  source: { type: string; url?: string }
  importedFrom: { agent?: string; path?: string }
  importedAt: string
  deployments: Record<string, DeploymentState>
}
