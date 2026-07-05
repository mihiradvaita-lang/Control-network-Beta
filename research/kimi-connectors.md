# Connector design (Kimi K2.6, captured by Claude)

Behind the existing collector interface: each source returns a Signal
{kind, collector, data(flat key->value), provenance high|medium|low}. Real mode with
automatic fallback to sim when the source is unconfigured.

## Connector 1 — Prometheus (+ Alertmanager already wired at /v1/triage)
Env: CN_PROMETHEUS_URL (required to enable), CN_PROMETHEUS_TOKEN (optional bearer),
CN_PROMETHEUS_TIMEOUT (default 3s).
Instant query: GET {CN_PROMETHEUS_URL}/api/v1/query?query=<promql>  (provenance=high)
Per-pattern PromQL (scope by pod=~"<pod>.*",namespace="<ns>" from the alert labels):
- OOMKill:        container_memory_working_set_bytes{...}  and
                  kube_pod_container_resource_limits{resource="memory",...}  -> usage, limit, pct
- CrashLoopBackOff: kube_pod_container_status_restarts_total{...}            -> restarts
                  (exit reason/code from K8s state: lastState.terminated.reason/exitCode)
- HighLatency:    histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{...}[5m])) by (le,service))  -> p99
                  saturation: sum(rate(container_cpu_usage_seconds_total{...}[5m])) by (pod)
                              / kube_pod_container_resource_limits{resource="cpu",...}
- DiskPressure:   kubelet_volume_stats_used_bytes{...} / kubelet_volume_stats_capacity_bytes{...} -> used_pct
- ConfigError:    from K8s events (kube-state / events) — reason CreateContainerConfigError etc.
Parse: resultType vector/scalar -> take first result .value[1] as float -> flat fact.
Thinnest real-time proof: one GET /api/v1/query returning a live value at alert time.

## Connector 2 — Datadog
Env: CN_DATADOG_API_KEY, CN_DATADOG_APP_KEY, CN_DATADOG_SITE (default datadoghq.com).
Headers: DD-API-KEY, DD-APPLICATION-KEY. Base https://api.{CN_DATADOG_SITE}.
- Metrics timeseries: GET /api/v1/query?from=&to=&query=<datadog metric query>
  (e.g. avg:kubernetes.memory.usage{pod_name:<pod>}, ...cpu, restarts). provenance=high.
- Logs (recent, scoped): POST /api/v2/logs/events/search  body {filter:{query:"pod_name:<pod>",from:"now-15m",to:"now"},page:{limit:20}}. provenance=low.
- (optional) Monitor state: GET /api/v1/monitor. 
Rate limits: metrics ~a few hundred/hr; logs search has its own quota — cache per-incident,
short timeouts, best-effort (never block the report on Datadog).
Thinnest real-time proof: one GET /api/v1/query returning a live metric point.

## Config switch
CN_DATA_MODE = sim (default) | prometheus | datadog  — OR per-collector source resolution:
a source is used only if its env is set, else fall back to sim for that collector.
No hardcoded secrets — env only. All calls: short timeout, catch+fallback to sim,
never block the deterministic facts/first token.
