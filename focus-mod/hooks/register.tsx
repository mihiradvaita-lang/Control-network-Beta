import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { FocusRecord, FocusSession } from '../types'
import { BREAK_IDEAS, FOCUS_RULES, MODES, detectMode, parseFocusArgs } from './modes'
import type { ModeId } from './modes'

const PANE = 'focus'
const MINUTE = 60_000
const session = atom({ plugin: 'focus', key: 'session' } as const, null)

const modeOf = (s: FocusSession) => MODES[(s.mode in MODES ? s.mode : 'work') as ModeId]

const remainingMs = (s: FocusSession, now: number) =>
  Math.max(0, s.phaseEndsAt - (s.pausedAt ?? now))

const clockText = (ms: number) => {
  const total = Math.ceil(ms / 1000)
  const m = Math.floor(total / 60)
  const sec = String(total % 60).padStart(2, '0')

  return `${m}:${sec}`
}

const bar = (done: number, width: number) => {
  const filled = Math.round(Math.min(1, Math.max(0, done)) * width)

  return '#'.repeat(filled) + '-'.repeat(width - filled)
}

const pick = <T,>(list: readonly T[], seed: number) => list[Math.abs(seed) % list.length]

const dayKey = (at: number) => {
  const d = new Date(at)

  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
}

const DAY = 24 * 60 * MINUTE
const STALE_PAUSE = 4 * 60 * MINUTE

const partialMinutes = (s: FocusSession, now: number) =>
  s.phase === 'focus' ? Math.round((s.minutes * MINUTE - remainingMs(s, now)) / MINUTE) : 0

const focusedMinutes = (s: FocusSession, now: number) => Math.round(s.focusedMs / MINUTE) + partialMinutes(s, now)

async function history($: EngineInterface) {
  return ((await $.store.get('history')) as FocusRecord[] | undefined) ?? []
}

async function record($: EngineInterface, s: FocusSession, minutes: number, at?: number) {
  if (minutes < 1) return
  const key = `${s.startedAt}:${s.round}`
  const list = await history($)
  if (list.some(r => r.key === key)) return
  const entry: FocusRecord = { goal: s.goal, mode: s.mode, minutes, at: at ?? (await $.clock.now()), key }
  await $.store.set('history', [...list, entry].slice(-300))
}

async function todayMinutes($: EngineInterface) {
  const today = dayKey(await $.clock.now())

  return (await history($)).filter(r => dayKey(r.at) === today).reduce((sum, r) => sum + r.minutes, 0)
}

async function streakDays($: EngineInterface) {
  const now = await $.clock.now()
  const days = new Set((await history($)).map(r => dayKey(r.at)))
  let at = days.has(dayKey(now)) ? now : now - DAY
  let streak = 0
  for (; days.has(dayKey(at)); at -= DAY) streak += 1

  return streak
}

let changing = 0
let isTicking = false

async function change($: EngineInterface, fn: (cur: FocusSession | null) => FocusSession | null) {
  changing += 1
  try {
    const next = await update($, session, cur => fn(cur ?? null))
    await $.store.set('active', next)
    $.ui.invalidate('ui.render')

    return next
  } finally {
    changing -= 1
  }
}

async function tick($: EngineInterface) {
  if (isTicking || changing > 0) return
  isTicking = true
  try {
    const s = await read($, session)
    if (s === null) return
    const kept = (await $.store.get('active')) as FocusSession | null | undefined
    if (changing === 0 && (kept == null || kept.startedAt !== s.startedAt)) {
      await update($, session, () => null)
      $.ui.invalidate('ui.render')

      return
    }
    if (s.pausedAt !== null) return
    const now = await $.clock.now()
    if (now >= s.phaseEndsAt) await advance($, now)
    $.ui.invalidate('ui.render')
  } finally {
    isTicking = false
  }
}

async function advance($: EngineInterface, now: number) {
  const seen: { ended?: FocusSession; resumed?: FocusSession } = {}
  await change($, cur => {
    seen.ended = undefined
    seen.resumed = undefined
    if (cur === null || cur.pausedAt !== null || now < cur.phaseEndsAt) return cur
    if (cur.phase === 'focus') {
      seen.ended = cur

      return { ...cur, phase: 'break', phaseEndsAt: now + cur.breakMinutes * MINUTE, focusedMs: cur.focusedMs + cur.minutes * MINUTE }
    }
    seen.resumed = cur

    const minutes = cur.nextMinutes ?? cur.minutes

    return { ...cur, phase: 'focus', round: cur.round + 1, minutes, nextMinutes: undefined, phaseEndsAt: now + minutes * MINUTE }
  })

  const s = seen.ended ?? seen.resumed
  if (s === undefined) return
  const title = `Focus: ${modeOf(s).label}`
  const text = seen.ended
    ? `Round ${s.round} done: ${s.minutes} min on "${s.goal}". Break ${s.breakMinutes} min: ${pick(BREAK_IDEAS, s.round)}`
    : `Break over. Round ${s.round + 1}: back to "${s.goal}".`
  if (seen.ended) await record($, s, s.minutes)
  $.ui.toast(text, { timeoutMs: 15_000 })
  void $.ui.notify(text, { title }).catch(() => undefined)
}

async function start($: EngineInterface, goal: string, modeId: ModeId, minutes: number | undefined) {
  const mode = MODES[modeId]
  const now = await $.clock.now()
  const previous = await read($, session)
  if (previous !== null) await record($, previous, partialMinutes(previous, now))
  const s: FocusSession = {
    goal,
    mode: modeId,
    minutes: minutes ?? mode.defaultMinutes,
    breakMinutes: mode.breakMinutes,
    phase: 'focus',
    phaseEndsAt: now + (minutes ?? mode.defaultMinutes) * MINUTE,
    pausedAt: null,
    round: 1,
    focusedMs: 0,
    parked: previous?.parked ?? [],
    startedAt: now,
  }
  await change($, () => s)

  return s
}

async function restore($: EngineInterface) {
  if ((await read($, session)) !== null) return
  const kept = (await $.store.get('active')) as FocusSession | null | undefined
  if (kept == null) return
  const now = await $.clock.now()
  const isFresh = kept.pausedAt !== null ? now - kept.pausedAt < STALE_PAUSE : kept.phaseEndsAt > now
  if (isFresh) {
    await update($, session, () => kept)

    return
  }
  const minutes = kept.phase !== 'focus' ? 0 : kept.pausedAt !== null ? partialMinutes(kept, now) : kept.minutes
  await record($, kept, minutes, Math.min(now, kept.pausedAt ?? kept.phaseEndsAt))
  await $.store.set('active', null)
  const parked = kept.parked.length > 0 ? ` Parked: ${kept.parked.join('; ')}` : ''
  $.ui.toast(`Your focus session on "${kept.goal}" ended while you were away.${parked}`, { timeoutMs: 15_000 })
}

const HELP = [
  'Focus mode: pick one goal, Claude keeps you on it.',
  '',
  '  /focus-on <goal>              start (mode auto-detected)',
  '  /focus-on study: ch 3 45m     pick the mode and minutes',
  '  /park <thought>               park a distraction for later',
  '  /focus-pause                  pause or resume the timer',
  '  /focus-check                  Claude checks your progress, gives the next step',
  '  /focus-board                  open the focus dashboard',
  '  /focus-done                   finish and see your summary',
  '',
  'Modes: study, research, work, brainstorm, write',
].join('\n')


async function togglePause($: EngineInterface) {
  const now = await $.clock.now()
  const next = await change($, cur => {
    if (cur === null) return cur
    if (cur.pausedAt === null) return { ...cur, pausedAt: now }

    return { ...cur, pausedAt: null, phaseEndsAt: cur.phaseEndsAt + (now - cur.pausedAt) }
  })
  if (next === null) return 'No focus session running. Start one with /focus-on <goal>.'

  return next.pausedAt !== null
    ? `Paused with ${clockText(remainingMs(next, now))} left. /focus-pause again to resume.`
    : `Resumed: "${next.goal}".`
}

async function finish($: EngineInterface) {
  const s = await read($, session)
  if (s === null) return { text: 'No focus session running. Start one with /focus-on <goal>.' }
  const now = await $.clock.now()
  await record($, s, partialMinutes(s, now))
  const total = focusedMinutes(s, now)
  await change($, () => null)
  const today = await todayMinutes($)
  const streak = await streakDays($)
  const parked = s.parked.length > 0 ? ['', 'Parked for later:', ...s.parked.map(p => `  - ${p}`)] : []
  const text = [
    `Focus session done: "${s.goal}"`,
    `${modeOf(s).label} mode | ${total} min focused | ${s.round} round${s.round === 1 ? '' : 's'}`,
    `Today: ${today} min | streak: ${streak} day${streak === 1 ? '' : 's'}`,
    ...parked,
  ].join('\n')

  return { text, context: ['The focus session has ended; stop applying the focus-mode rules.'] }
}

async function checkIn($: EngineInterface) {
  const s = await read($, session)
  if (s === null) return
  const text = CHECK_IN(s, focusedMinutes(s, await $.clock.now()))
  // A prompt submitted inside a command.run hook would wait on that hook, so send it once the hook returns.
  $.clock.after(0, () => void $.prompt.submit({ text }).catch(() => undefined))
}

async function pressDone($: EngineInterface) {
  const { text } = await finish($)
  $.ui.toast(text, { timeoutMs: 15_000 })
}

const CHECK_IN = (s: FocusSession, minutes: number) =>
  [
    `Focus check-in. My goal: "${s.goal}" (${modeOf(s).label} mode, ${minutes} min in).`,
    'In at most 6 short lines: what I have done toward it in this conversation, what is left,',
    'and the ONE next step I should take right now. If there is nothing yet, ask me one sharp question to get going.',
  ].join(' ')

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'focus-on', description: 'Start a focus session on one goal', argumentHint: '[mode:] <goal> [45m]' })
    await $.command.register({ name: 'park', description: 'Park a distracting thought for later', argumentHint: '<thought>', immediate: true })
    await $.command.register({ name: 'focus-pause', description: 'Pause or resume the focus timer', immediate: true })
    await $.command.register({ name: 'focus-check', description: 'Claude checks your progress and names the next step' })
    await $.command.register({ name: 'focus-board', description: 'Open the focus dashboard', immediate: true })
    await $.command.register({ name: 'focus-done', description: 'Finish the focus session and see the summary' })

    await restore($)

    $.clock.every(1000, () => void tick($).catch(() => undefined))

    return next(e)
  })

  on('command.run', { command: 'focus-on' }, async ($, e) => {
    const s = await read($, session)
    if (e.args.trim() === '') {
      if (s === null) return { text: HELP }
      const now = await $.clock.now()
      const state = s.pausedAt !== null ? 'paused' : s.phase === 'break' ? 'on a break' : 'focusing'

      return { text: `${state}: "${s.goal}" | ${clockText(remainingMs(s, now))} left | round ${s.round}` }
    }
    const parsed = parseFocusArgs(e.args)
    if (parsed.goal === '') {
      if (s !== null && parsed.minutes !== undefined) {
        const minutes = parsed.minutes
        await change($, cur => (cur === null ? cur : { ...cur, nextMinutes: minutes }))

        return { text: `Rounds after this one will be ${minutes} min.` }
      }

      return { text: `What's the goal? Try: /focus-on finish chapter 3 notes\n\n${HELP}` }
    }
    const started = await start($, parsed.goal, parsed.mode ?? detectMode(parsed.goal), parsed.minutes)
    const mode = modeOf(started)

    return {
      text: [
        `${mode.icon} ${mode.label} mode: "${started.goal}"`,
        `${started.minutes} min focus, then ${started.breakMinutes} min break. Rounds repeat until /focus-done.`,
        `Tip: ${pick(mode.tips, started.startedAt)}`,
        'Distracted? /park <thought>.  Stuck? /focus-check.',
      ].join('\n'),
    }
  })

  on('command.run', { command: 'park' }, async ($, e) => {
    const thought = e.args.trim()
    const s = await read($, session)
    if (s === null) return { text: 'No focus session running. Start one with /focus-on <goal>.' }
    if (thought === '') {
      return { text: s.parked.length === 0 ? 'Parking lot is empty.' : `Parked:\n${s.parked.map(p => `  - ${p}`).join('\n')}` }
    }
    await change($, cur => (cur === null ? cur : { ...cur, parked: [...cur.parked, thought].slice(-30) }))

    return { text: `Parked: "${thought}". Back to "${s.goal}".` }
  })

  on('command.run', { command: 'focus-pause' }, async $ => ({ text: await togglePause($) }))

  on('command.run', { command: 'focus-done' }, async $ => finish($))

  on('command.run', { command: 'focus-board' }, async $ => {
    const opened = await $.ui.open({ id: PANE, title: 'Focus' })

    return { text: opened.isPlaced ? 'Focus board opened.' : 'Focus board opens when there is room for a pane.' }
  })

  on('command.run', { command: 'focus-check' }, async $ => {
    const s = await read($, session)
    if (s === null) return { text: 'No focus session running. Start one with /focus-on <goal>.' }
    await checkIn($)

    return { text: 'Asking Claude for a check-in...' }
  })

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    const s = await read($, session)
    if (s === null) return composed
    const mode = modeOf(s)
    const text = [
      '# Focus mode',
      `The user turned on focus mode with the focus plugin. Their one goal: "${s.goal}". Mode: ${mode.label}. Timers, breaks and parked thoughts are handled by the plugin; you do not need to track them.`,
      '',
      'Rules for every reply:',
      FOCUS_RULES,
      '',
      `How to help in ${mode.label} mode:`,
      mode.coach,
    ].join('\n')

    return { sections: [...composed.sections, { id: 'focus:coach', text, scope: 'session' as const }] }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, session)
    if (s === null || e.props.hasSurvey) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    const now = await $.clock.now()
    const mode = modeOf(s)
    const left = remainingMs(s, now)
    const length = (s.phase === 'focus' ? s.minutes : s.breakMinutes) * MINUTE
    const label = s.pausedAt !== null ? 'paused' : s.phase === 'break' ? 'break' : 'left'
    const isWide = e.props.bodyColumns >= 90

    return (
      <Box flexDirection="row" gap={1}>
        <Text color={s.phase === 'break' ? 'success' : 'claude'} bold>
          {mode.icon} {mode.label.toUpperCase()}
        </Text>
        <Box flexShrink={1}>
          <Text wrap="truncate-end">{s.phase === 'break' ? 'Rest. You earned it.' : s.goal}</Text>
        </Box>
        <Text bold={s.pausedAt === null} dimColor={s.pausedAt !== null}>
          {clockText(left)} {label}
        </Text>
        {isWide && <Text dimColor>[{bar(1 - left / length, 10)}]</Text>}
        {isWide && <Text dimColor>r{s.round}{s.parked.length > 0 ? ` | ${s.parked.length} parked` : ''}</Text>}
        <Button key="pause" label={s.pausedAt === null ? 'Pause' : 'Resume'} onPress={() => void togglePause($)} />
        <Button key="board" label="Board" onPress={() => void $.ui.open({ id: PANE, title: 'Focus' })} />
        <Button key="done" label="Done" onPress={() => void pressDone($)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const s = await read($, session)
    const today = await todayMinutes($)
    const streak = await streakDays($)
    const stats = `Today ${today} min | streak ${streak} day${streak === 1 ? '' : 's'}`

    if (s === null) {
      const seenGoals = new Set<string>()
      const recent = [...(await history($))].reverse().filter(r => !seenGoals.has(r.goal) && seenGoals.add(r.goal)).slice(0, 5)

      return (
        <Box flexDirection="column" gap={1}>
          <Text bold>No focus session running.</Text>
          <Text dimColor>{stats}</Text>
          {recent.length > 0 && (
            <Box flexDirection="column">
              <Text>Pick up where you left off:</Text>
              {recent.map((r, i) => (
                <Button key={`again-${i}`} plain onPress={() => void start($, r.goal, (r.mode in MODES ? r.mode : 'work') as ModeId, undefined)}>
                  {r.goal} <Text dimColor>{r.mode}</Text>
                </Button>
              ))}
            </Box>
          )}
          <Text dimColor>{HELP}</Text>
        </Box>
      )
    }

    const now = await $.clock.now()
    const mode = modeOf(s)
    const left = remainingMs(s, now)
    const length = (s.phase === 'focus' ? s.minutes : s.breakMinutes) * MINUTE
    const width = Math.max(10, Math.min(40, e.props.bodyColumns - 2))
    const state = s.pausedAt !== null ? 'PAUSED' : s.phase === 'break' ? 'BREAK' : 'FOCUS'
    const tip = s.phase === 'break' ? pick(BREAK_IDEAS, s.round) : pick(mode.tips, Math.floor(now / (3 * MINUTE)))

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text color="claude" bold>
            {mode.icon} {mode.label} mode
          </Text>
          <Text bold>{s.goal}</Text>
        </Box>
        <Box flexDirection="column">
          <Text bold color={s.phase === 'break' ? 'success' : undefined}>
            {state} {clockText(left)} <Text dimColor>of {clockText(length)} | round {s.round}</Text>
          </Text>
          <Text dimColor>[{bar(1 - left / length, width)}]</Text>
          <Text dimColor>
            {focusedMinutes(s, now)} min focused this session | {stats}
          </Text>
        </Box>
        <Text italic>Tip: {tip}</Text>
        <Box flexDirection="column">
          <Text bold>Parking lot ({s.parked.length})</Text>
          {s.parked.length === 0 && <Text dimColor>Empty. /park any stray thought to keep it out of your head.</Text>}
          {s.parked.map(p => (
            <Text>- {p}</Text>
          ))}
        </Box>
        <Box flexDirection="row" gap={1}>
          <Button key="pane-pause" label={s.pausedAt === null ? 'Pause' : 'Resume'} hotkey="p" onPress={() => void togglePause($)} />
          <Button key="pane-check" label="Check-in" hotkey="c" onPress={() => void checkIn($)} />
          {s.parked.length > 0 && <Button key="pane-clear" label="Clear parked" onPress={() => void change($, cur => (cur === null ? cur : { ...cur, parked: [] }))} />}
          <Button key="pane-done" label="Done" variant="primary" hotkey="d" onPress={() => void pressDone($)} />
        </Box>
      </Box>
    )
  })
}
