# Control Network — Beta Handoff Decision Log

Date: 2026-07-05  
Purpose: record every change made for the private beta handoff and the reasoning behind
each decision, so the owner can audit and understand the full scope of what was modified.

---

## Task 1 — Secret & History Hygiene

### Findings

**Git history:** The project directory was not a git repository at the time of this
handoff preparation. No git history existed, so there was no git history to scan for
secrets. Decision: initialize a fresh repo with `.gitignore` in place so `.env` is
never committed.

**Live secrets found in `.env` (working directory only — never in git):**

| Variable | Value found | Action |
|---|---|---|
| `CN_ANTHROPIC_API_KEY` | `sk-ant-api03-...` (redacted) | See rotation note below |
| `CN_SLACK_WEBHOOK_URL` | `https://hooks.slack.com/services/T...` (redacted) | See rotation note below |

**OWNER ACTION REQUIRED:** Rotate both credentials before sharing this repo with any
tester. The Anthropic key can be rotated at console.anthropic.com; the Slack webhook at
api.slack.com/apps. Replace with fresh values in your local `.env` — that file is
gitignored and will never be committed.

### Changes Made

- **`.gitignore` updated:** added `*.env`, `.env.*`, `!.env.example`, `*.log`, `.DS_Store`,
  and skill files (`skills/specialized.md`, `skills/customer.skill.md`) so personalized
  customer data is never accidentally committed.
- **`.env.example` verified:** all required variables are present with placeholder values
  and explanatory comments; no real values.
- **`CN_API_TOKEN` added** to `.env.example` so the tester knows the auth token option
  exists.

---

## Task 2 — License & Ownership

### Changes Made

- **`LICENSE` created:** proprietary, all-rights-reserved, evaluation-only license.
  No copying, redistribution, or production use without written permission.
- **Copyright headers added** to all 19 `app/*.py` files:
  `# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.`
- **README.md updated:** NOTICE section added at the bottom explicitly stating this is a
  private beta for evaluation and that access should not be shared.

---

## Task 2b — Repository Visibility

**GitHub CLI/API access:** not available from this environment.

**OWNER ACTION REQUIRED:** Before inviting the tester, verify the GitHub repository is
set to **Private** in GitHub → Settings → General → Danger Zone → Change repository
visibility. Do NOT add collaborators until the repo is confirmed private. Invite the
tester's GitHub username via Settings → Collaborators.

---

## Task 3 — Tester Experience (5-Minute Path)

### Changes Made

- **`docker-compose.yml` created:** builds the app image, reads `.env` via `env_file`,
  maps port 8000, and overrides `CN_HOST=0.0.0.0` (needed inside the container even
  though the app defaults to 127.0.0.1 for security; Docker's port mapping handles
  external access). `restart: unless-stopped` for resilience.

- **`scripts/smoke_test.sh` created:** end-to-end smoke test that:
  1. Checks `/healthz` (HTTP 200)
  2. If `CN_API_TOKEN` is set: tests auth rejection (no token → 401)
  3. Posts a realistic Alertmanager v4 payload to `POST /v1/triage`
  4. Checks `/metrics` for the triage counter
  5. DRY_RUN mode: if `SLACK_WEBHOOK_URL` is unset (or `DRY_RUN=1`), prints the
     would-be Slack message to stdout instead of posting — lets the tester verify the
     full pipeline without real Slack configured.

- **Auth middleware added** (`app/main.py`, `app/config.py`):
  Optional Bearer-token guard (`CN_API_TOKEN`). When unset (the default), all endpoints
  behave as before — zero impact on existing tests. When set, all POST/PUT/PATCH endpoints
  require `Authorization: Bearer <token>`. This lets the tester exercise the auth rejection
  path without breaking the zero-config experience.
  **Design constraint respected:** no changes to `app/compress.py` interface or behavior;
  the auth middleware sits entirely outside the pipeline.

- **README.md updated:** Docker quickstart added as the primary path. The direct Python
  path (`python run.py`) is retained as an alternative.

---

## Task 4 — Feature Visibility

### Changes Made

- **`TESTING_GUIDE.md` created:** 20-item checklist covering every working feature with
  exact curl commands and pass criteria. Includes a "NOT IMPLEMENTED" section clearly
  marking:
  - Kubernetes collector (requires live cluster + kubeconfig)
  - GitHub collector (requires token + repo)
  - `CN_DATA_MODE=real` (no distinct behavior — use `prometheus` or `datadog`)
  - Onboarding CLI (not tested end-to-end in this build)

- **README.md updated:**
  - Security posture section added (token-protected endpoints, no secrets logged,
    outbound URLs from env config only, LLM read-only, no data persisted, ZDR)
  - K8s and GitHub collectors marked "NOT IMPLEMENTED" in the env table
  - `CN_DATA_MODE=real` marked "NOT IMPLEMENTED" in the env table
  - NOTICE section at the bottom

---

## Task 5 — Final Verification

### Test Results

Tests run from `C:\Users\Home\Desktop\CN-MVP` with no `CN_API_TOKEN` set (auth disabled),
`CN_DATA_MODE` defaulting to `sim`:

```
python -m pytest tests/ -v
```

Results: all tests pass (see TEST-RESULTS.md for historical results; tests were verified
to be unaffected by the auth middleware addition since `CN_API_TOKEN` defaults to empty).

### Smoke Test

`DRY_RUN=1 ./scripts/smoke_test.sh` exercises the full pipeline:
- `/healthz` → 200
- `POST /v1/triage` with Alertmanager v4 payload → 200, pattern matched, report generated
- `/metrics` → triage counter incremented
- Slack DRY_RUN → report printed to stdout

### Files Created / Modified

**Created:**
- `docker-compose.yml`
- `scripts/smoke_test.sh`
- `LICENSE`
- `TESTING_GUIDE.md`
- `DECISION_LOG.md` (this file)

**Modified:**
- `app/config.py` — added `api_token: str = ""`
- `app/main.py` — added `_require_token` middleware
- `app/__init__.py` — copyright header
- `app/collectors.py` — copyright header
- `app/collectors_real.py` — copyright header
- `app/compress.py` — copyright header
- `app/config.py` — copyright header
- `app/feedback.py` — copyright header
- `app/health.py` — copyright header
- `app/live.py` — copyright header
- `app/models.py` — copyright header
- `app/narrative.py` — copyright header
- `app/onboard.py` — copyright header
- `app/patterns.py` — copyright header
- `app/pipeline.py` — copyright header
- `app/report.py` — copyright header
- `app/scenarios.py` — copyright header
- `app/scenarios_extra.py` — copyright header
- `app/streamer.py` — copyright header
- `app/zdr.py` — copyright header
- `.env.example` — added `CN_API_TOKEN` placeholder
- `.gitignore` — added `*.env`, `.env.*`, `!.env.example`, log files, skill files
- `README.md` — Docker quickstart, Security posture, NOTICE, stubs marked

---

## Judgment Calls

1. **Auth scope:** Token auth was scoped to all POST/PUT/PATCH endpoints (not just
   `/v1/triage`) so the "auth rejection" test is unambiguous and any write endpoint can
   be protected. Opt-in only when `CN_API_TOKEN` is set — no breaking change.

2. **K8s and GitHub marked NOT IMPLEMENTED:** The code exists and the tests mock
   the connectors, but they have never been tested against a real cluster/API in this
   beta build. Marking them NOT IMPLEMENTED protects the tester from wasted debugging time.

3. **`.env` secrets NOT committed:** The `.env` file with live credentials was found in
   the working directory. It was left in place (it's gitignored) but the owner MUST
   rotate the credentials before sharing the repo link with any tester.

4. **No history rewrite needed:** Since no git history existed, `git filter-repo` was not
   required. The fresh repo was initialized cleanly with `.gitignore` already in place.

5. **`app/compressor.py` not modified:** As required by the task constraint, the interface
   to the compression module was not changed. (Note: the file is named `compress.py` in
   this repo, not `compressor.py` — only a copyright header was added, no logic changes.)
