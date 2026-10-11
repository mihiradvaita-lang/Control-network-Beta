// Focus mode coaching content. Pure data + tiny pure functions. No imports.

export type ModeId = 'study' | 'research' | 'work' | 'brainstorm' | 'write'

export type Mode = {
  id: ModeId
  label: string
  icon: string
  defaultMinutes: number
  breakMinutes: number
  coach: string
  tips: string[]
  keywords: string[]
}

const lines = (...xs: string[]): string => xs.map(x => '- ' + x).join('\n')

export const MODES: Record<ModeId, Mode> = {
  study: {
    id: 'study',
    label: 'Study',
    icon: '◆',
    defaultMinutes: 25,
    breakMinutes: 5,
    coach: lines(
      'Favor retrieval over re-reading: ask the user to recall key ideas from memory before showing answers.',
      'Quiz often with short questions (1-3 at a time); give feedback, then re-ask missed items later in the session.',
      'Use the Feynman technique: have the user explain a concept in plain words, then point out gaps precisely.',
      'Interleave related topics and problem types instead of drilling one type in a block.',
      'Prefer worked examples followed by a similar problem for the user to solve unaided.',
      'Keep a short list of weak spots; suggest spaced review of them (later today, tomorrow, in 3 days).',
      'Do not hand over full answers to practice problems unless asked; give hints first.',
    ),
    tips: [
      'Close the book and write what you remember.',
      'Explain it out loud as if to a 12-year-old.',
      'Test yourself before you feel ready.',
      'Mix problem types; do not repeat one kind.',
      'Mark weak spots and review them tomorrow.',
      'Ask Claude to quiz you with 3 questions.',
      'Re-reading feels productive; recall actually is.',
      'Sketch a diagram from memory, then check it.',
    ],
    keywords: [
      'study', 'studying', 'exam', 'exams', 'midterm', 'finals', 'quiz', 'learn', 'learning',
      'chapter', 'lecture', 'course', 'classes', 'homework', 'revise', 'revision', 'flashcards',
      'memorize', 'textbook', 'notes', 'understand', 'practice', 'syllabus', 'biology',
      'chemistry', 'physics', 'math', 'calculus', 'vocab', 'language',
    ],
  },
  research: {
    id: 'research',
    label: 'Research',
    icon: '?',
    defaultMinutes: 45,
    breakMinutes: 10,
    coach: lines(
      'Keep a running list of open questions; restate the current one when the user asks something new.',
      'Track sources explicitly: for each claim note where it came from and how strong the evidence is.',
      'Separate notes (what sources say) from conclusions (what the user believes); label which is which.',
      'Flag weak evidence, conflicting findings, and claims that need a primary source.',
      'Suggest the single next search, paper, or query that best narrows the current question.',
      'Periodically summarize: what we know, what we do not know, what to check next.',
    ),
    tips: [
      'Write the question before you open a tab.',
      'Note the source next to every claim.',
      'Keep notes and conclusions in separate lists.',
      'Skim abstracts first; read fully only the best 2.',
      'Ask: what evidence would change my mind?',
      'Close tabs you have already extracted from.',
      'End with: what is the next search?',
    ],
    keywords: [
      'research', 'paper', 'papers', 'literature', 'review', 'sources', 'source', 'survey',
      'investigate', 'evidence', 'citations', 'cite', 'references', 'compare',
      'analysis', 'analyze', 'benchmark', 'eval', 'evals', 'arxiv', 'thesis', 'findings',
      'data', 'dataset', 'hypothesis', 'explore', 'background',
    ],
  },
  work: {
    id: 'work',
    label: 'Work',
    icon: '▶',
    defaultMinutes: 50,
    breakMinutes: 10,
    coach: lines(
      'Help define "done" for this block in one sentence before starting.',
      'Always reduce the task to the single next physical action the user can do in under 10 minutes.',
      'Timebox: if something is taking longer than planned, say so and propose cutting scope.',
      'Bias to shipping small: suggest the smallest version that works, then iterate.',
      'When blocked, offer one concrete unblocking step rather than a list of options.',
      'Keep a short checklist of remaining steps and tick them off as the user reports progress.',
    ),
    tips: [
      'Define done in one sentence.',
      'What is the very next physical action?',
      'Ship the small version first.',
      'One tab, one task, one window.',
      'If stuck 10 minutes, ask or cut scope.',
      'Notifications off until the block ends.',
      'Write down distractions; do not act on them.',
    ],
    keywords: [
      'ship', 'fix', 'build', 'email', 'emails', 'deploy', 'bug', 'bugs', 'implement',
      'refactor', 'code', 'feature', 'deliver', 'report',
      'invoice', 'inbox', 'meeting', 'spreadsheet', 'review', 'release', 'test', 'tests',
      'migrate', 'setup', 'configure', 'debug', 'admin', 'todo',
    ],
  },
  brainstorm: {
    id: 'brainstorm',
    label: 'Brainstorm',
    icon: '*',
    defaultMinutes: 20,
    breakMinutes: 5,
    coach: lines(
      'Diverge first: aim for quantity, no judgment; push for 15+ ideas before evaluating any.',
      'Frame prompts as "How might we...?" and offer wild or opposite angles to break fixation.',
      'Use SCAMPER (substitute, combine, adapt, modify, put to other use, eliminate, reverse) when ideas stall.',
      'Build on the user\'s ideas ("yes, and") instead of critiquing during the divergent phase.',
      'Then converge: cluster ideas into themes and score each on impact vs effort.',
      'Finish by naming the top 3 ideas and one cheap test or next step for each.',
    ),
    tips: [
      'Quantity first; judge later.',
      'Start with "How might we...?"',
      'Write the worst idea on purpose.',
      'Flip it: what would the opposite look like?',
      'Steal from another industry.',
      'Cluster, then score impact vs effort.',
      'Pick a top 3 before you stop.',
    ],
    keywords: [
      'brainstorm', 'brainstorming', 'ideas', 'idea', 'ideate', 'pitch', 'strategy',
      'market', 'marketing', 'pricing', 'business', 'startup', 'product', 'names', 'naming',
      'concept', 'concepts', 'plan', 'roadmap', 'growth', 'campaign', 'positioning',
      'options', 'creative', 'vision', 'features', 'monetize', 'launch',
    ],
  },
  write: {
    id: 'write',
    label: 'Write',
    icon: '✎',
    defaultMinutes: 30,
    breakMinutes: 5,
    coach: lines(
      'Outline first: agree on the main point and 3-6 section headings before drafting.',
      'Work on one section at a time; keep the user on the current section.',
      'During drafting, discourage editing: momentum over polish, fix it in the revision pass.',
      'Do not ghost-write the whole piece unless asked; prompt, suggest, and give short examples.',
      'When the user is stuck, ask what they want the reader to know or feel, then suggest a first sentence.',
      'In revision, give at most 3 high-impact edits at a time (clarity, structure, cut).',
    ),
    tips: [
      'Outline before you draft.',
      'Write ugly first; edit later.',
      'One section at a time.',
      'What should the reader know after this?',
      'Leave [TK] for facts; do not stop to look up.',
      'Read it aloud during revision.',
      'Cut the first paragraph; see if it improves.',
    ],
    keywords: [
      'write', 'writing', 'essay', 'draft', 'drafting', 'blog', 'post', 'article', 'chapter',
      'intro', 'introduction', 'story', 'novel', 'copy', 'outline', 'newsletter', 'letter',
      'proposal', 'script', 'docs', 'documentation', 'edit', 'rewrite', 'manuscript', 'memo',
      'speech', 'readme', 'abstract',
    ],
  },
}

const MODE_ORDER: ModeId[] = ['study', 'research', 'write', 'brainstorm', 'work']

const tokenMatches = (tok: string, kw: string): boolean =>
  tok === kw || (kw.length >= 4 && tok.startsWith(kw) && /^(s|es|ed|ing)$/.test(tok.slice(kw.length)))

export function detectMode(goal: string): ModeId {
  const toks = (goal || '').toLowerCase().match(/[a-z0-9]+/g) || []
  if (toks.length === 0) return 'work'
  let best: ModeId = 'work'
  let bestScore = 0
  for (const id of MODE_ORDER) {
    let score = 0
    toks.forEach((tok, i) => {
      if (MODES[id].keywords.some(kw => tokenMatches(tok, kw))) score += i === 0 ? 2 : 1
    })
    if (score > bestScore) {
      best = id
      bestScore = score
    }
  }
  return best
}

export const FOCUS_RULES: string = lines(
  'Keep replies tight and tied to the stated goal; no padding, no preamble.',
  'If the user drifts off-goal, say so in ONE short line and offer to park it with `/park <thought>`; answer briefly only if they insist.',
  'Do not introduce tangents, side quests, or "you might also..." suggestions.',
  'End every substantive reply with exactly one concrete next step.',
  'Celebrate progress briefly (a few words), then move on.',
  'Never lecture or moralize about focus or productivity.',
  'Ask at most one clarifying question at a time.',
)

export const BREAK_IDEAS: string[] = [
  'Stand up and stretch your back and shoulders.',
  'Drink a glass of water.',
  'Look at something 20 ft (6 m) away for 20 seconds.',
  'Walk around for a couple of minutes, ideally outside.',
  'Breathe 4-7-8: in 4s, hold 7s, out 8s; repeat 4 times.',
  'Close your eyes and rest them; no screens.',
  'Do 10 squats or a short wall push-up set.',
  'Tidy one small thing on your desk.',
]

const clampMin = (n: number): number => Math.min(240, Math.max(1, Math.round(n)))

const UNIT = '(m|min|mins|minute|minutes|h|hr|hrs|hour|hours)'

function toMinutes(num: string, unit?: string): number {
  const n = parseFloat(num)
  return unit && /^h/i.test(unit) ? n * 60 : n
}

const MODE_PREFIX = /^(study|research|work|brainstorm|write)\s*:/i

export function parseFocusArgs(args: string): { goal: string; minutes?: number; mode?: ModeId } {
  let s = (args || '').trim()
  let mode: ModeId | undefined
  let minutes: number | undefined

  const pm = s.match(/^(study|research|work|brainstorm|write)\s*:\s*/i)
  if (pm) {
    mode = (pm[1] ?? '').toLowerCase() as ModeId
    s = s.slice(pm[0].length).trim()
  }

  // Leading duration: "45 ...", "45m ...", "1h ...", "1h30m ..."
  const lead = s.match(new RegExp('^(\\d+(?:\\.\\d+)?)\\s*' + UNIT + '?(?:\\s*(\\d+)\\s*(?:m|min|mins)?)?(?=\\s|$)\\s*', 'i'))
  const afterLead = lead ? s.slice(lead[0].length) : ''
  const isBareOk = afterLead.trim() === '' || MODE_PREFIX.test(afterLead)
  if (lead && (lead[2] ? true : !lead[3] && (lead[1] ?? '').length <= 3 && isBareOk)) {
    minutes = toMinutes(lead[1] ?? '', lead[2]) + (lead[2] && /^h/i.test(lead[2]) && lead[3] ? parseInt(lead[3], 10) : 0)
    s = s.slice(lead[0].length).trim()
  } else {
    // Trailing duration (unit required): "... 45m", "... 45 min", "... for 1h", "... 1h30m"
    const tail = s.match(new RegExp('(?:^|\\s)(?:(?:for|in)\\s+)?(\\d+(?:\\.\\d+)?)\\s*' + UNIT + '(?:\\s*(\\d+)\\s*(?:m|min|mins)?)?\\.?$', 'i'))
    if (tail) {
      minutes = toMinutes(tail[1] ?? '', tail[2]) + (/^h/i.test(tail[2] ?? '') && tail[3] ? parseInt(tail[3], 10) : 0)
      s = s.slice(0, tail.index).trim()
    }
  }

  // Mode prefix may also follow a leading number: "60 research: llm evals"
  if (!mode) {
    const pm2 = s.match(/^(study|research|work|brainstorm|write)\s*:\s*/i)
    if (pm2) {
      mode = (pm2[1] ?? '').toLowerCase() as ModeId
      s = s.slice(pm2[0].length).trim()
    }
  }

  const out: { goal: string; minutes?: number; mode?: ModeId } = { goal: s.replace(/\s+/g, ' ').trim() }
  if (minutes !== undefined && isFinite(minutes) && minutes > 0) out.minutes = clampMin(minutes)
  if (mode) out.mode = mode
  return out
}
