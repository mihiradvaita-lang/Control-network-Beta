# Focus: a Claude Code focus mod

Focus mode for any kind of work: studying, research, deep work, business brainstorming or writing.
You pick **one goal**. The mod runs a Pomodoro-style timer, gives you a place to park stray thoughts,
and adds rules to Claude's system prompt so it stays on your goal.

## Install

In a Claude Code terminal session:

```
/plugin install focus --marketplace mihiradvaita-lang/Control-network-Beta
```

Answer `y` to add the marketplace, then pick the **user** scope so it is available in every session.

## Use it

| Command | What it does |
| --- | --- |
| `/focus-on <goal>` | Start a session. The mode is detected from your words. |
| `/focus-on study: chapter 3 45m` | Choose the mode (`study`, `research`, `work`, `brainstorm`, `write`) and the length. |
| `/focus-on brainstorm: pricing for Control Network` | A 20-minute brainstorm: ideas first, then Claude helps you converge. |
| `/park <thought>` | Park a distraction without breaking flow. It works even while Claude is replying. |
| `/focus-pause` | Pause or resume the timer. |
| `/focus-check` | Claude says what you have done toward the goal and the one next step. |
| `/focus-board` | Open the dashboard: timer, progress bar, tips, parking lot, today's minutes and your streak. |
| `/focus-done` | Finish. Shows minutes focused, rounds, today's total, your streak and what you parked. |
| `/focus-on 30m` | While a session runs, makes later rounds 30 minutes long. |

A band above the prompt shows the mode, the goal, the countdown and **Pause / Board / Done** buttons.
When a block ends you get a toast and a desktop notification with a break idea. Rounds repeat until you run `/focus-done`.

## What Claude does differently in focus mode

- Replies are short and tied to your goal. Each substantive reply ends with **one** concrete next step.
- If you drift off-goal, Claude says so in one line and offers `/park`.
- Each mode has its own coaching:
  - **Study**: active recall, quizzes you, has you explain concepts back to it (the Feynman technique).
  - **Research**: keeps a list of open questions, separates claims from evidence, names the next search.
  - **Work**: names the next physical action, defines "done", ships small.
  - **Brainstorm**: generates many ideas without judging them, then clusters them, scores impact against effort, and names the top 3.
  - **Write**: outline first, then a draft without editing, one section at a time.

## Files

- `hooks/register.tsx`: hooks, commands, timer, band and pane
- `hooks/modes.ts`: mode coaching, tips, break ideas, argument parsing
- `types/index.d.ts`: state contract
- `tests/`: `claude plugin test focus-mod`
