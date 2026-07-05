# specialized.md — [Customer Name] K8s Incident Triage Profile
_Last updated: YYYY-MM-DD by [name]_

## 1. Environment Fingerprint
- Cluster topology: [managed EKS/GKE/AKS | self-hosted | bare-metal | hybrid]
- Node pools & sizing quirks: [e.g., spot-instance pool prone to preemption]
- Namespaces of concern (prod-critical vs. low-priority): [list]
- Service mesh / ingress: [Istio | Linkerd | nginx-ingress | none]
- CI/CD deploy cadence: [e.g., 20 deploys/day via ArgoCD — recent deploy = prime suspect]

## 2. Model & Runtime Config
- Model provider: [Anthropic | OpenAI-compatible | Azure OpenAI | Bedrock | Ollama local]
- Model name/version: [e.g., claude-sonnet, llama3.1:70b]
- Latency budget: [target time-to-first-token, max total report time]
- Fallback behavior if model unreachable: [deterministic-only | queue & retry | alert on-call]

## 3. Known Failure Patterns (customer-specific priors)
For each of the 5 base patterns, note customer-specific overrides:
- **OOMKill**: [typical culprits — e.g., "batch job X regularly OOMs during nightly ETL, non-critical"]
- **CrashLoopBackOff**: [common root causes seen historically — bad configmap rollout, missing secret]
- **HighLatency**: [known bottleneck services, downstream dependency SLAs]
- **DiskPressure**: [nodes/volumes known to fill up, log-rotation gaps]
- **ConfigError**: [common misconfig sources — Helm values drift, secret rotation timing]
- Custom pattern additions: [any incident type outside the base 5 that recurs for this customer]

## 4. Escalation & Ownership Map
- Service -> team/owner mapping: [table]
- Severity thresholds -> who gets paged (link to PagerDuty/Opsgenie service + Slack channel)
- Business-hours vs. off-hours escalation differences

## 5. Noise Suppression Rules
- Alerts to always downgrade/ignore: [e.g., known-flaky liveness probe on service Y]
- Alert grouping preferences: [group by namespace | by deploy | by root pod]

## 6. Narrative Tone & Output Preferences
- Preferred report length: [terse bullet | full narrative]
- Jargon level: [assume senior SRE | assume generalist on-call rotation incl. non-K8s-experts]
- Required output fields for Slack copy: [title, confidence, blast radius, suggested next command]
- Redaction rules: [customer names, PII, internal hostnames to scrub before any external model call]

## 7. Historical Incident Corpus (optional, improves few-shot grounding)
- Links/paths to last 5-10 real postmortems for this cluster (used to calibrate tone & root-cause style)

## 8. Do-Not-Do List
- Actions the tool must never suggest (e.g., "never suggest scaling down prod replicas," "never suggest deleting PVCs")
