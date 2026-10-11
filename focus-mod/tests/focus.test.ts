import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { FocusRecord, FocusSession } from '../types'
import { detectMode, parseFocusArgs } from '../hooks/modes'

const MIN = 60_000
const T0 = Date.UTC(2026, 9, 11, 9, 0, 0)
const SURFACES = ['terminal', 'desktop'] as const
const SLOW = { timeoutMs: 60_000 }

const COMPOSE = {
  model: 'claude-opus-5-5',
  promptModel: 'claude-opus-5-5',
  surfaces: ['terminal'],
  tools: [],
  outputStyle: null,
  traits: [],
} as const

const BAND = (bodyColumns = 100) => ({
  hasSurvey: false,
  isWorking: false,
  maxRows: 10,
  bodyColumns,
  scroll: { offset: 0, bodyRows: 10 },
  view: {},
})

const PANE = {
  title: 'Focus',
  isFocused: true,
  bodyColumns: 60,
  placement: 'dock',
  scroll: { offset: 0, bodyRows: 30 },
  view: {},
} as const

// The world beneath the plugin. `$` in a test has no `state` or `store` noun,
// so the test watches the plugin's writes from beneath: every `state.set` of
// the session passes through `seen.session`, and the store is a Map the
// test's own `store.*` hooks answer (in place of mock.store, which would hide
// the writes from the test).
function world(on: On, stored: Record<string, unknown> = {}) {
  const clock = mock.clock(on, { now: T0 })
  const store = new Map<string, unknown>(Object.entries(stored))
  const seen = { session: null as FocusSession | null, writes: 0 }
  const toasts: string[] = []
  const notes: string[] = []
  const opened: string[] = []

  on('store.get', async (_$, e) => ({ value: store.get(e.key) }))
  on('store.set', async (_$, e) => {
    store.set(e.key, e.value)

    return { value: undefined }
  })
  on('store.delete', async (_$, e) => {
    store.delete(e.key)

    return { value: undefined }
  })
  on('store.keys', async () => ({ value: [...store.keys()] }))
  on('state.set', async (_$, e, next) => {
    if (e.plugin === 'focus' && e.key === 'session') {
      seen.session = e.value as FocusSession | null
      seen.writes += 1
    }

    return next(e)
  })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('command.register', async (_$, e) => ({ value: { command: e.name } }))
  on('ui.toast', async (_$, e) => {
    toasts.push(e.text)

    return { value: undefined }
  })
  on('ui.notify', async (_$, e) => {
    notes.push(e.text)

    return { value: { isSent: false, reason: 'no-surface' } }
  })
  on('ui.open', async (_$, e) => {
    opened.push(e.id)

    return { value: { isPlaced: true } }
  })
  const submitted: string[] = []
  on('prompt.submit', async (_$, e) => {
    submitted.push(e.text)

    return { text: e.text }
  })
  on('prompt.compose', async () => ({ sections: [{ id: 'intro', text: 'You are Claude.', scope: 'shared' }] }))
  // What the engine draws when the plugin yields the band.
  on('ui.render', async ($, e) => {
    const { Box } = $.ui.resolve(e)

    return h(Box, {})
  })

  return { clock, store, seen, toasts, notes, opened, submitted }
}

async function boot($: any) {
  await $.session.start({ cwd: '/tmp/focus-test', surface: 'terminal', isInteractive: true })
}

async function run($: any, command: string, args = ''): Promise<{ text?: string; context?: readonly string[] }> {
  return $.command.run({ command, args })
}

const history = (store: Map<string, unknown>) => (store.get('history') as FocusRecord[] | undefined) ?? []

describe('modes (pure)', () => {
  test('parseFocusArgs reads mode prefix, goal and duration', async () => {
    expect(parseFocusArgs('study: chapter 3 notes 30m')).toEqual({ goal: 'chapter 3 notes', mode: 'study', minutes: 30 })
    expect(parseFocusArgs('Research: llm evals 1h')).toEqual({ goal: 'llm evals', mode: 'research', minutes: 60 })
    expect(parseFocusArgs('45m write the intro')).toEqual({ goal: 'write the intro', minutes: 45 })
    expect(parseFocusArgs('write the intro 45m')).toEqual({ goal: 'write the intro', minutes: 45 })
    // A bare leading number is part of the goal unless nothing (or a mode prefix) follows.
    expect(parseFocusArgs('45 write the intro')).toEqual({ goal: '45 write the intro' })
    expect(parseFocusArgs('3 body problem essay')).toEqual({ goal: '3 body problem essay' })
    expect(parseFocusArgs('90')).toEqual({ goal: '', minutes: 90 })
    expect(parseFocusArgs('draft the essay in 20 min')).toEqual({ goal: 'draft the essay', minutes: 20 })
    expect(parseFocusArgs('1h30m fix login bug')).toEqual({ goal: 'fix login bug', minutes: 90 })
    expect(parseFocusArgs('60 research: llm evals')).toEqual({ goal: 'llm evals', mode: 'research', minutes: 60 })
    expect(parseFocusArgs('draft the essay for 1.5 hours')).toEqual({ goal: 'draft the essay', minutes: 90 })
    expect(parseFocusArgs('fix   the   bug')).toEqual({ goal: 'fix the bug' })
    expect(parseFocusArgs('finish 2024 report')).toEqual({ goal: 'finish 2024 report' })
    expect(parseFocusArgs('study:')).toEqual({ goal: '', mode: 'study' })
    expect(parseFocusArgs('')).toEqual({ goal: '' })
  })

  test('parseFocusArgs clamps minutes to 1..240', async () => {
    expect(parseFocusArgs('marathon 500m').minutes).toBe(240)
    expect(parseFocusArgs('quick 0.2m').minutes).toBe(1)
    expect(parseFocusArgs('nothing 0m').minutes).toBeUndefined()
  })

  test('detectMode picks the mode from keywords', async () => {
    expect(detectMode('chapter 3 notes')).toBe('study')
    expect(detectMode('studying for the biology midterm')).toBe('study')
    expect(detectMode('review literature on sleep')).toBe('research')
    expect(detectMode('fix login bug')).toBe('work')
    expect(detectMode('brainstorm startup names')).toBe('brainstorm')
    expect(detectMode('write essay on history')).toBe('write')
    expect(detectMode('zzz qqq')).toBe('work')
    expect(detectMode('')).toBe('work')
  })
})

describe('commands', () => {
  test('/focus-on study: chapter 3 notes 30m starts a Study session', async ($, on) => {
    const { seen, store } = world(on)
    await boot($)
    const out = await run($, 'focus-on', 'study: chapter 3 notes 30m')
    expect(out.text).toContain('Study mode: "chapter 3 notes"')
    expect(out.text).toContain('30 min focus, then 5 min break')
    expect(seen.session).toMatchObject({
      goal: 'chapter 3 notes',
      mode: 'study',
      minutes: 30,
      breakMinutes: 5,
      phase: 'focus',
      round: 1,
      pausedAt: null,
      phaseEndsAt: T0 + 30 * MIN,
      parked: [],
    })
    // The session is kept in the store too, to survive a restart.
    expect(store.get('active')).toEqual(seen.session)
  })

  test('/focus-on detects the mode and uses its default minutes', async ($, on) => {
    const { seen } = world(on)
    await boot($)
    const out = await run($, 'focus-on', 'fix login bug')
    expect(out.text).toContain('Work mode')
    expect(seen.session).toMatchObject({ goal: 'fix login bug', mode: 'work', minutes: 50, breakMinutes: 10 })
  })

  test('/focus-on with no args and no session prints help', async ($, on) => {
    const { seen } = world(on)
    await boot($)
    const out = await run($, 'focus-on', '')
    expect(out.text).toContain('Focus mode: pick one goal, Claude keeps you on it.')
    expect(out.text).toContain('/park <thought>')
    expect(seen.writes).toBe(0)
  })

  test('/focus-on with no args during a session reports status', async ($, on) => {
    const { clock } = world(on)
    await boot($)
    await run($, 'focus-on', 'write: blog post 20m')
    await clock.advance(90_000)
    const out = await run($, 'focus-on', '   ')
    expect(out.text).toBe('focusing: "blog post" | 18:30 left | round 1')
  })

  test('/focus-on with a duration but no goal and no session asks for a goal', async ($, on) => {
    const { seen } = world(on)
    await boot($)
    const out = await run($, 'focus-on', '45m')
    expect(out.text).toContain("What's the goal?")
    expect(out.text).toContain('Focus mode: pick one goal')
    expect(seen.writes).toBe(0)
  })

  test('/focus-on with a duration but no goal keeps the running session', async ($, on) => {
    const { seen, store } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    const out = await run($, 'focus-on', '45m')
    expect(out.text).toBe('Rounds after this one will be 45 min.')
    expect(seen.session).toMatchObject({ goal: 'chapter 3 notes', mode: 'study', round: 1, startedAt: T0, phaseEndsAt: T0 + 30 * MIN })
    expect(store.get('active')).toMatchObject({ goal: 'chapter 3 notes', startedAt: T0 })
  })

  test('/focus-on 45m mid-round: done counts the minutes actually focused', SLOW, async ($, on) => {
    const { clock } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await clock.advance(10 * MIN)
    await run($, 'focus-on', '45m')
    // 10 minutes into a 30-minute round, still 20 left on the clock.
    expect((await run($, 'focus-on')).text).toBe('focusing: "chapter 3 notes" | 20:00 left | round 1')
    const out = await run($, 'focus-done')
    expect(out.text).toContain('Study mode | 10 min focused | 1 round')
  })

  test('/focus-on 45m mid-round: the current round still ends and counts as 30, the next is 45', SLOW, async ($, on) => {
    const { clock, seen, store } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await clock.advance(10 * MIN)
    await run($, 'focus-on', '45m')
    await clock.advance(20 * MIN)
    expect(seen.session).toMatchObject({ phase: 'break', focusedMs: 30 * MIN })
    expect(history(store).map(r => r.minutes)).toEqual([30])
    await clock.advance(5 * MIN)
    expect(seen.session).toMatchObject({ phase: 'focus', round: 2, phaseEndsAt: T0 + 80 * MIN })
  })

  test('/park adds a thought to the parked list', async ($, on) => {
    const { seen } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    const out = await run($, 'park', 'call mom')
    expect(out.text).toBe('Parked: "call mom". Back to "chapter 3 notes".')
    expect(seen.session?.parked).toEqual(['call mom'])
    await run($, 'park', 'buy milk')
    expect(seen.session?.parked).toEqual(['call mom', 'buy milk'])
    const list = await run($, 'park', '')
    expect(list.text).toBe('Parked:\n  - call mom\n  - buy milk')
  })

  test('/park with no session says so and writes nothing', async ($, on) => {
    const { seen } = world(on)
    await boot($)
    const out = await run($, 'park', 'call mom')
    expect(out.text).toBe('No focus session running. Start one with /focus-on <goal>.')
    expect(seen.writes).toBe(0)
  })

  test('/focus-pause pauses, and again resumes with the paused time added back', SLOW, async ($, on) => {
    const { clock, seen } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 5m')
    await clock.advance(2 * MIN)

    const paused = await run($, 'focus-pause')
    expect(paused.text).toBe('Paused with 3:00 left. /focus-pause again to resume.')
    expect(seen.session?.pausedAt).toBe(T0 + 2 * MIN)

    // The block does not end while paused, however long the pause.
    await clock.advance(10 * MIN)
    expect(seen.session?.phase).toBe('focus')
    expect((await run($, 'focus-on')).text).toBe('paused: "chapter 3 notes" | 3:00 left | round 1')

    const resumed = await run($, 'focus-pause')
    expect(resumed.text).toBe('Resumed: "chapter 3 notes".')
    expect(seen.session?.pausedAt).toBeNull()
    expect(seen.session?.phaseEndsAt).toBe(T0 + 15 * MIN)
  })

  test('/focus-pause with no session says so', async ($, on) => {
    world(on)
    await boot($)
    expect((await run($, 'focus-pause')).text).toBe('No focus session running. Start one with /focus-on <goal>.')
  })

  test('/focus-done prints a summary, records the minutes and clears the session', SLOW, async ($, on) => {
    const { clock, seen, store } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await run($, 'park', 'call mom')
    await clock.advance(4 * MIN)
    const out = await run($, 'focus-done')
    expect(out.text).toBe(
      [
        'Focus session done: "chapter 3 notes"',
        'Study mode | 4 min focused | 1 round',
        'Today: 4 min | streak: 1 day',
        '',
        'Parked for later:',
        '  - call mom',
      ].join('\n'),
    )
    expect(out.context).toEqual(['The focus session has ended; stop applying the focus-mode rules.'])
    expect(seen.session).toBeNull()
    expect(store.get('active')).toBeNull()
    expect(history(store)).toEqual([{ goal: 'chapter 3 notes', mode: 'study', minutes: 4, at: T0 + 4 * MIN, key: `${T0}:1` }])
  })

  test('/focus-done with no session says so', async ($, on) => {
    world(on)
    await boot($)
    expect((await run($, 'focus-done')).text).toBe('No focus session running. Start one with /focus-on <goal>.')
  })

  test('/focus-board opens the pane', async ($, on) => {
    const { opened } = world(on)
    await boot($)
    expect((await run($, 'focus-board')).text).toBe('Focus board opened.')
    expect(opened).toEqual(['focus'])
  })
})

describe('session.start', () => {
  test('restores a session kept in the store that is still running', async ($, on) => {
    const kept: FocusSession = {
      goal: 'chapter 3 notes',
      mode: 'study',
      minutes: 30,
      breakMinutes: 5,
      phase: 'focus',
      phaseEndsAt: T0 + 10 * MIN,
      pausedAt: null,
      round: 1,
      focusedMs: 0,
      parked: ['call mom'],
      startedAt: T0 - 20 * MIN,
    }
    const { seen } = world(on, { active: kept })
    await boot($)
    expect(seen.session).toEqual(kept)
    expect((await run($, 'park', '')).text).toBe('Parked:\n  - call mom')
  })

  test('drops a kept session whose block ended while away', async ($, on) => {
    const stale = {
      goal: 'old',
      mode: 'work',
      minutes: 50,
      breakMinutes: 10,
      phase: 'focus',
      phaseEndsAt: T0 - MIN,
      pausedAt: null,
      round: 1,
      focusedMs: 0,
      parked: [],
      startedAt: T0 - 51 * MIN,
    }
    const { seen, store, toasts } = world(on, { active: stale })
    await boot($)
    expect(seen.writes).toBe(0)
    expect(store.get('active')).toBeNull()
    // The block that ended while away is credited once, on the day it ended, and the person told.
    expect(history(store)).toEqual([{ goal: 'old', mode: 'work', minutes: 50, at: T0 - MIN, key: `${T0 - 51 * MIN}:1` }])
    expect(toasts).toEqual(['Your focus session on "old" ended while you were away.'])
    expect((await run($, 'focus-on')).text).toContain('Focus mode: pick one goal')
  })

  test('the timer clears the session when the store no longer holds it', SLOW, async ($, on) => {
    const { clock, seen, store } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    // Another session of the same person ended it (store 'active' cleared).
    store.set('active', null)
    await clock.advance(1000)
    expect(seen.session).toBeNull()
  })
})

describe('prompt.compose', () => {
  test('adds the focus:coach section with the goal only while a session runs', async ($, on) => {
    world(on)
    await boot($)
    const before = await $.prompt.compose(COMPOSE)
    expect(before.sections.map(s => s.id)).toEqual(['intro'])

    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await run($, 'park', 'call mom')
    const during = await $.prompt.compose(COMPOSE)
    expect(during.sections.map(s => s.id)).toEqual(['intro', 'focus:coach'])
    const coach = during.sections[1]
    expect(coach?.scope).toBe('session')
    expect(coach?.text).toContain('Their one goal: "chapter 3 notes". Mode: Study.')
    expect(coach?.text).toContain('How to help in Study mode:')
    // Goal, mode and rules only: parked thoughts stay out of the prompt.
    expect(coach?.text).not.toContain('call mom')

    // Pausing does not change the section (it carries no phase), so the prompt cache holds.
    await run($, 'focus-pause')
    expect((await $.prompt.compose(COMPOSE)).sections[1]?.text).toBe(coach?.text)

    await run($, 'focus-done')
    const after = await $.prompt.compose(COMPOSE)
    expect(after.sections.map(s => s.id)).toEqual(['intro'])
  })
})

describe('timer', () => {
  test('a focus block ends in a break, records history, and the break ends in round 2', SLOW, async ($, on) => {
    const { clock, seen, store, toasts, notes } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 5m')

    await clock.advance(5 * MIN - 1000)
    expect(seen.session?.phase).toBe('focus')
    expect(history(store)).toEqual([])

    await clock.advance(1000)
    expect(seen.session).toMatchObject({ phase: 'break', round: 1, phaseEndsAt: T0 + 10 * MIN, focusedMs: 5 * MIN })
    expect(history(store)).toEqual([{ goal: 'chapter 3 notes', mode: 'study', minutes: 5, at: T0 + 5 * MIN, key: `${T0}:1` }])
    expect(toasts.at(-1)).toContain('Round 1 done: 5 min on "chapter 3 notes". Break 5 min:')
    expect(notes.at(-1)).toBe(toasts.at(-1))

    await clock.advance(5 * MIN)
    expect(seen.session).toMatchObject({ phase: 'focus', round: 2, phaseEndsAt: T0 + 15 * MIN })
    expect(toasts.at(-1)).toBe('Break over. Round 2: back to "chapter 3 notes".')
    // A break adds nothing to history.
    expect(history(store)).toHaveLength(1)

    // Done mid-round-2: 5 min from round 1 plus 2 running.
    await clock.advance(2 * MIN)
    const out = await run($, 'focus-done')
    expect(out.text).toContain('Study mode | 7 min focused | 2 rounds')
    expect(out.text).toContain('Today: 7 min')
    expect(history(store).map(r => [r.minutes, r.key])).toEqual([[5, `${T0}:1`], [2, `${T0}:2`]])
  })
})

describe('AbovePrompt band', () => {
  test('shows the goal, timer and buttons on every surface', SLOW, async ($, on) => {
    const { seen } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await run($, 'park', 'call mom')

    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'AbovePrompt', props: BAND() })
      expect(await ui.find({ type: 'Text', text: 'chapter 3 notes' }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /STUDY/ }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '30:00 left' }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '1 parked' }), surface).toBeDefined()
      expect((await ui.find({ key: 'pause' }))?.props.label, surface).toBe('Pause')

      await ui.press({ key: 'pause' })
      expect(seen.session?.pausedAt, surface).toBe(T0)
      expect((await ui.find({ key: 'pause' }))?.props.label, surface).toBe('Resume')
      expect(await ui.find({ type: 'Text', text: '30:00 paused' }), surface).toBeDefined()

      await ui.press({ key: 'pause' })
      expect(seen.session?.pausedAt, surface).toBeNull()
      await ui.unmount()
    }
  })

  test('drops the progress bar on a narrow band', async ($, on) => {
    world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'AbovePrompt', props: BAND(60) })
      expect(await ui.find({ type: 'Text', text: 'chapter 3 notes' }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /\[-+\]/ }), surface).toBeUndefined()
      await ui.unmount()
    }
  })

  test('the Done button ends the session', async ($, on) => {
    const { seen } = world(on)
    await boot($)
    for (const surface of SURFACES) {
      await run($, 'focus-on', 'study: chapter 3 notes 30m')
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'AbovePrompt', props: BAND() })
      await ui.press({ key: 'done' })
      expect(seen.session, surface).toBeNull()
      expect(await ui.find({ type: 'Text', text: 'chapter 3 notes' }), surface).toBeUndefined()
      await ui.unmount()
    }
  })

  test('yields the band when there is no session', async ($, on) => {
    world(on)
    await boot($)
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'AbovePrompt', props: BAND() })
      expect(await ui.find({ key: 'pause' }), surface).toBeUndefined()
      await ui.unmount()
    }
  })
})

describe('Pane', () => {
  test('shows the session and the parking lot on every surface', async ($, on) => {
    world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await run($, 'park', 'call mom')
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'Pane', requestId: 'focus', props: PANE })
      expect(await ui.find({ type: 'Text', text: 'chapter 3 notes' }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /FOCUS 30:00/ }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: 'Parking lot (1)' }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: '- call mom' }), surface).toBeDefined()
      await ui.unmount()
    }
  })

  test('with no session offers recent goals', async ($, on) => {
    const { clock } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await clock.advance(3 * MIN)
    await run($, 'focus-done')
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'Pane', requestId: 'focus', props: PANE })
      expect(await ui.find({ type: 'Text', text: 'No focus session running.' }), surface).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /Today 3 min/ }), surface).toBeDefined()
      expect(await ui.find({ key: 'again-0' }), surface).toBeDefined()
      await ui.unmount()
    }
  })

  test('a recent goal starts again when pressed', async ($, on) => {
    const { clock, seen } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await clock.advance(3 * MIN)
    await run($, 'focus-done')
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'Pane', requestId: 'focus', props: PANE })
      await ui.press({ key: 'again-0' })
      expect(seen.session, surface).toMatchObject({ goal: 'chapter 3 notes', mode: 'study', minutes: 25, round: 1 })
      expect(await ui.find({ type: 'Text', text: /FOCUS 25:00/ }), surface).toBeDefined()
      await run($, 'focus-done')
      await ui.unmount()
    }
  })

  test('the Done button ends the session', async ($, on) => {
    const { seen } = world(on)
    await boot($)
    for (const surface of SURFACES) {
      await run($, 'focus-on', 'study: chapter 3 notes 30m')
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'Pane', requestId: 'focus', props: PANE })
      await ui.press({ key: 'pane-done' })
      expect(seen.session, surface).toBeNull()
      await ui.unmount()
    }
  })

  test('the Check-in button asks Claude for a check-in', async ($, on) => {
    const { clock, submitted } = world(on)
    await boot($)
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    for (const surface of SURFACES) {
      const ui = await $.ui.mount({ plugin: 'focus', surface, component: 'Pane', requestId: 'focus', props: PANE })
      await ui.press({ key: 'pane-check' })
      await clock.settle()
      expect(submitted.at(-1), surface).toContain('Focus check-in. My goal: "chapter 3 notes"')
      await ui.unmount()
    }
  })
})

describe('/focus-check', () => {
  test('submits a check-in prompt for the goal', async ($, on) => {
    const { clock, submitted } = world(on)
    await boot($)
    expect((await run($, 'focus-check')).text).toBe('No focus session running. Start one with /focus-on <goal>.')
    await run($, 'focus-on', 'study: chapter 3 notes 30m')
    await clock.advance(0)
    const out = await run($, 'focus-check')
    await clock.settle()
    expect(out.text).toBe('Asking Claude for a check-in...')
    expect(submitted).toHaveLength(1)
    expect(submitted[0]).toContain('Focus check-in. My goal: "chapter 3 notes" (Study mode, 0 min in).')
  })
})
