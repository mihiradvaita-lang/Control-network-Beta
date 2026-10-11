export type FocusPhase = 'focus' | 'break'

export type FocusSession = {
  goal: string
  mode: string
  minutes: number
  breakMinutes: number
  phase: FocusPhase
  phaseEndsAt: number
  pausedAt: number | null
  round: number
  focusedMs: number
  parked: string[]
  startedAt: number
}

export type FocusRecord = { goal: string; mode: string; minutes: number; at: number; key?: string }

declare module 'claude-code' {
  interface PluginState {
    focus: { session: FocusSession | null }
  }
}
