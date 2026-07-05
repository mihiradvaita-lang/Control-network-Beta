# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Interactive onboarding CLI: `python -m app.onboard`.

Runs a ~30-minute interview (13 questions) and writes a filled skills/specialized.md from the
research-doc template (skills/specialized.template.md). This is a one-time, human-driven setup
step — it writes a static config file, not runtime incident telemetry, so it does not violate
the zero-retention posture (incidents themselves are never written to disk).

Kept intentionally simple: best-effort mapping of free-text answers into template sections,
no NLP. Handles empty answers (fills a "[not provided]" placeholder) and Ctrl-C (aborts
cleanly without leaving a half-written file).
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

from .config import SKILLS_DIR

QUESTIONS = [
    "Walk me through your cluster setup — managed or self-hosted, cloud provider, roughly how many nodes/namespaces?",
    "What's your deploy process and how often do you ship — and is there a tool (ArgoCD, Flux, Jenkins) we should know is the usual 'first suspect' after a bad deploy?",
    "Which model/provider do you want us to call — Anthropic, an OpenAI-compatible endpoint, Azure, Bedrock, or a local Ollama model? Any data-residency or latency constraints we should hard-code?",
    "If the model is unreachable mid-incident, what should happen — silent fallback to rule-based only, or should it page someone?",
    "Think of your last 3 real incidents. For each: what pattern was it (OOM/CrashLoop/Latency/DiskPressure/Config), and what was the actual root cause once you found it?",
    "Are there any services or jobs that look like an incident but are actually known-benign — things you've learned to ignore?",
    "Is there a recurring root cause we should bias toward suggesting first for your environment (e.g., 'it's almost always the shared Postgres connection pool')?",
    "For each critical service, who owns it, and where does it get paged/posted today (PagerDuty service name, Slack channel)?",
    "Any severity thresholds that differ from defaults — e.g., what counts as page-worthy vs. Slack-only?",
    "When this posts a summary to Slack, what does 'useful' look like versus 'too much noise' — bullet points, one-liner, or full narrative?",
    "Anything the tool should never suggest doing automatically (e.g., scaling actions, deleting resources, restarting stateful sets)?",
    "Any data we must never send to the model — internal hostnames, customer names, secrets — that we should redact first?",
    "I'll turn this into your specialized.md and send it back for review before we turn it on — anything else that's unique about how your team triages that we haven't covered?",
]


def _ask(prompt: str, n: int, total: int) -> str:
    try:
        ans = input(f"\n[{n}/{total}] {prompt}\n> ").strip()
    except EOFError:
        ans = ""
    return ans or "[not provided]"


def _fmt(answers: list[str], customer: str) -> str:
    today = dt.date.today().isoformat()
    a = answers  # 0-indexed, matches QUESTIONS order
    return f"""# specialized.md — {customer} K8s Incident Triage Profile
_Last updated: {today} by onboarding interview (app/onboard.py)_

## 1. Environment Fingerprint
- Cluster topology / setup notes: {a[0]}
- CI/CD deploy cadence & first-suspect tooling: {a[1]}
- Namespaces of concern (prod-critical vs. low-priority): [not captured in interview — edit manually]
- Service mesh / ingress: [not captured in interview — edit manually]
- Node pools & sizing quirks: [not captured in interview — edit manually]

## 2. Model & Runtime Config
- Model provider / constraints: {a[2]}
- Fallback behavior if model unreachable: {a[3]}
- Latency budget: [not captured in interview — edit manually]

## 3. Known Failure Patterns (customer-specific priors)
- Recent real incidents (pattern + root cause): {a[4]}
- Known-benign look-alikes (things to ignore): {a[5]}
- Recurring root cause to bias toward: {a[6]}
- Custom pattern additions: [not captured in interview — edit manually]

## 4. Escalation & Ownership Map
- Service -> team/owner + paging destination: {a[7]}
- Severity thresholds (page-worthy vs. Slack-only): {a[8]}
- Business-hours vs. off-hours escalation differences: [not captured in interview — edit manually]

## 5. Noise Suppression Rules
- Alerts to always downgrade/ignore: {a[5]}
- Alert grouping preferences: [not captured in interview — edit manually]

## 6. Narrative Tone & Output Preferences
- Preferred Slack summary style (bullets/one-liner/full): {a[9]}
- Jargon level: [not captured in interview — edit manually]
- Required output fields for Slack copy: [not captured in interview — edit manually]
- Redaction rules (data never sent to the model): {a[11]}

## 7. Historical Incident Corpus (optional, improves few-shot grounding)
- [not captured in interview — add links/paths to past postmortems manually]

## 8. Do-Not-Do List
- Actions the tool must never suggest automatically: {a[10]}

## 9. Additional Notes
- {a[12]}
"""


def main() -> int:
    print("=" * 72)
    print("Control Network — specialized.md onboarding interview")
    print("About 30 minutes. Press Ctrl-C at any time to abort without saving.")
    print("=" * 72)
    try:
        customer = input("\nCustomer/team name for this profile [DemoCorp]: ").strip() or "DemoCorp"
        answers = []
        total = len(QUESTIONS)
        for i, q in enumerate(QUESTIONS, start=1):
            answers.append(_ask(q, i, total))
    except KeyboardInterrupt:
        print("\n\n[onboard] Aborted — no file written.")
        return 130

    content = _fmt(answers, customer)
    out_path = Path(SKILLS_DIR) / "specialized.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"\n[onboard] Wrote {out_path}")
    print("[onboard] Review it, edit any '[not captured in interview]' sections, then restart the server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
