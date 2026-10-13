export interface Agent {
  id: string
  name: string
  installed: boolean
  version: string | null
  skillCount: number
  skillPaths: string[]
}
