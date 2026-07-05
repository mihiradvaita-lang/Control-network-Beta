# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""
Realistic simulated Kubernetes incident scenarios for FDE incident triage.
No external imports; pure Python data structures.
"""

SCENARIOS = [
    # OOMKill incidents (x2)
    {
        "id": "oom-payment-001",
        "alertname": "KubePodOOMKilled",
        "service": "payment-service",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "critical",
        "summary": "Payment service pod killed by OOMKiller after memory spike to 1Gi limit.",
        "raw": {
            "metrics": {
                "memory_before": "512Mi",
                "memory_at_kill": "1.2Gi",
                "limit": "1Gi",
                "growth": "+95% in 5m",
                "cpu": "45%",
                "request_rate": "120 req/s"
            },
            "pod_describe": {
                "phase": "Running",
                "restarts": 4,
                "last_state": "OOMKilled",
                "exit_code": 137,
                "image": "payment-service:v2.3.1"
            },
            "logs": [
                "2026-06-29T14:23:01Z INFO Processing batch payment request, transactions=450",
                "2026-06-29T14:23:15Z INFO Loading merchant profiles into cache, count=8923",
                "2026-06-29T14:23:28Z WARN Memory usage 750Mi, approaching limit",
                "2026-06-29T14:23:35Z WARN Memory usage 950Mi, cache still growing",
                "2026-06-29T14:23:42Z FATAL Kernel terminated process: OOMKilled"
            ],
            "deployment": {
                "last_deploy_sha": "v2.3.1",
                "minutes_before": 23,
                "author": "alice-team"
            }
        }
    },
    {
        "id": "oom-postgres-replica-001",
        "alertname": "KubePodOOMKilled",
        "service": "postgres",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "critical",
        "summary": "PostgreSQL replica pod killed by OOMKiller during large query execution.",
        "raw": {
            "metrics": {
                "memory_before": "2.8Gi",
                "memory_at_kill": "3.5Gi",
                "limit": "3Gi",
                "growth": "+85% in 8m",
                "cpu": "92%",
                "request_rate": "3400 q/s"
            },
            "pod_describe": {
                "phase": "Running",
                "restarts": 2,
                "last_state": "OOMKilled",
                "exit_code": 137,
                "image": "postgres:14.5-alpine"
            },
            "logs": [
                "2026-06-29T15:01:12Z LOG Starting full table scan on transactions table",
                "2026-06-29T15:01:45Z LOG Memory allocated 2.8Gi, sort operation in progress",
                "2026-06-29T15:02:10Z LOG Hash aggregate using 950Mi, buffer growth",
                "2026-06-29T15:02:28Z FATAL out of memory"
            ],
            "deployment": {
                "last_deploy_sha": "postgres:14.5-alpine",
                "minutes_before": 45,
                "author": "dba-ops"
            }
        }
    },

    # CrashLoopBackOff incidents (x2)
    {
        "id": "crashloop-checkout-api-001",
        "alertname": "KubePodCrashLooping",
        "service": "checkout-api",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "high",
        "summary": "Checkout API crashing on startup; missing environment variable or malformed config.",
        "raw": {
            "metrics": {
                "cpu": "5%",
                "memory": "120Mi",
                "restart_count": 12,
                "crash_interval": "~15s"
            },
            "pod_describe": {
                "phase": "CrashLoopBackOff",
                "restarts": 12,
                "last_state": "Terminated",
                "exit_code": 1,
                "image": "checkout-api:v1.8.2"
            },
            "logs": [
                "2026-06-29T16:34:22Z FATAL ConfigError: environment variable STRIPE_API_KEY not set",
                "2026-06-29T16:34:23Z FATAL Exiting due to missing required config"
            ],
            "deployment": {
                "last_deploy_sha": "v1.8.2",
                "minutes_before": 8,
                "author": "checkout-team"
            },
            "events": [
                "Back-off restarting failed container",
                "ConfigMap default-config was not found in namespace prod",
                "Pod failed to start due to init container error"
            ]
        }
    },
    {
        "id": "crashloop-notifications-worker-001",
        "alertname": "KubePodCrashLooping",
        "service": "notifications-worker",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "high",
        "summary": "Notifications worker repeatedly crashing due to malformed JSON in dependency injection config.",
        "raw": {
            "metrics": {
                "cpu": "8%",
                "memory": "95Mi",
                "restart_count": 18,
                "crash_interval": "~20s"
            },
            "pod_describe": {
                "phase": "CrashLoopBackOff",
                "restarts": 18,
                "last_state": "Terminated",
                "exit_code": 2,
                "image": "notifications-worker:v3.1.0"
            },
            "logs": [
                "2026-06-29T17:05:33Z INFO Starting notification worker service",
                "2026-06-29T17:05:34Z FATAL JSON decode error in /etc/config/services.json line 14: Expecting comma delimiter",
                "2026-06-29T17:05:34Z FATAL Exception: json.JSONDecodeError"
            ],
            "deployment": {
                "last_deploy_sha": "v3.1.0",
                "minutes_before": 5,
                "author": "platform-eng"
            },
            "events": [
                "ConfigMap notifications-config updated 2 minutes ago",
                "Container failed with exit code 2",
                "Back-off restarting failed container"
            ]
        }
    },

    # HighLatency incidents (x2)
    {
        "id": "latency-api-gateway-001",
        "alertname": "HighRequestLatency",
        "service": "api-gateway",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "high",
        "summary": "API gateway p99 latency spiked to 2.4s from baseline 180ms due to CPU saturation.",
        "raw": {
            "metrics": {
                "p50_latency": "180ms",
                "p99_latency": "2400ms",
                "baseline_p99": "180ms",
                "request_count": "8500 req/s",
                "error_rate": "2.3%"
            },
            "saturation": {
                "cpu": "88%",
                "memory": "72%",
                "network_in": "1.2Gbps",
                "db_pool": "92% (46/50 connections)"
            },
            "pod_describe": {
                "phase": "Running",
                "restarts": 0,
                "image": "api-gateway:v5.2.1",
                "cpu_request": "1000m",
                "cpu_limit": "1200m"
            },
            "logs": [
                "2026-06-29T18:12:45Z WARN Request latency p99=2100ms, p95=1200ms",
                "2026-06-29T18:12:52Z WARN Database connection pool saturation 92%",
                "2026-06-29T18:13:01Z ERROR Timeout connecting to upstream payment-service, retrying",
                "2026-06-29T18:13:10Z WARN CPU throttling detected, current utilization 88%"
            ],
            "deployment": {
                "last_deploy_sha": "v5.2.1",
                "minutes_before": 18,
                "author": "platform-team"
            }
        }
    },
    {
        "id": "latency-orders-service-001",
        "alertname": "HighRequestLatency",
        "service": "orders-service",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "high",
        "summary": "Orders service p99 latency reached 3.5s; database pool exhausted due to slow query.",
        "raw": {
            "metrics": {
                "p50_latency": "220ms",
                "p99_latency": "3500ms",
                "baseline_p99": "200ms",
                "request_count": "4200 req/s",
                "error_rate": "1.8%"
            },
            "saturation": {
                "cpu": "76%",
                "memory": "85%",
                "db_pool": "100% (30/30 connections)",
                "slow_query_count": 34
            },
            "pod_describe": {
                "phase": "Running",
                "restarts": 0,
                "image": "orders-service:v2.5.4",
                "cpu_request": "500m",
                "cpu_limit": "800m"
            },
            "logs": [
                "2026-06-29T19:22:10Z WARN Detected slow query: SELECT ... FROM orders WHERE status='processing' took 8500ms",
                "2026-06-29T19:22:25Z WARN Database pool at capacity 30/30, request queue building",
                "2026-06-29T19:22:40Z ERROR Connection timeout after 5000ms waiting for pool resource",
                "2026-06-29T19:22:55Z WARN Latency p99=3200ms, upstream response times degraded"
            ],
            "deployment": {
                "last_deploy_sha": "v2.5.4",
                "minutes_before": 12,
                "author": "order-team"
            }
        }
    },

    # DiskPressure incident (x1)
    {
        "id": "diskpressure-postgres-001",
        "alertname": "KubePersistentVolumeFillingUp",
        "service": "postgres",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "critical",
        "summary": "PostgreSQL persistent volume 94% full; writes will start failing within hours.",
        "raw": {
            "node_describe": {
                "node": "ip-10-0-1-23",
                "condition": "DiskPressure",
                "disk_used": "94%",
                "disk_free": "3.2Gi",
                "inodes_used": "91%"
            },
            "pvc": {
                "name": "data-postgres-0",
                "capacity": "50Gi",
                "used_pct": "94%",
                "used": "47Gi",
                "status": "Bound"
            },
            "disk": {
                "volume": "/var/lib/postgresql",
                "used": "47Gi",
                "capacity": "50Gi",
                "pct": "94%",
                "inodes_available": 1203
            },
            "pod_describe": {
                "phase": "Running",
                "restarts": 0,
                "image": "postgres:14.5-alpine"
            },
            "logs": [
                "2026-06-29T20:05:12Z LOG Autovacuum running on table pg_toast.pg_toast_16428",
                "2026-06-29T20:15:33Z WARNING Could not fsync file: No space left on device",
                "2026-06-29T20:25:44Z WARNING Temporary file could not be created",
                "2026-06-29T20:35:55Z CRITICAL Database disk usage critical: 94% full"
            ],
            "deployment": {
                "last_deploy_sha": "postgres:14.5-alpine",
                "minutes_before": 0,
                "author": "dba-ops"
            }
        }
    },

    # ConfigError incidents (x2)
    {
        "id": "configerror-api-gateway-001",
        "alertname": "CreateContainerConfigError",
        "service": "api-gateway",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "severity": "high",
        "summary": "API gateway unable to mount config; referenced ConfigMap does not exist.",
        "raw": {
            "pod_describe": {
                "phase": "Pending",
                "restarts": 0,
                "image": "api-gateway:v5.2.2",
                "init_container_status": "Error"
            },
            "events": [
                "ConfigMap api-gateway-config not found in namespace prod",
                "MountVolume.SetUp failed for volume config: configmap \"api-gateway-config\" not found",
                "Create pod failed: Unable to mount volumes"
            ],
            "logs": [
                "Failed to mount volume: configmap \"api-gateway-config\" not found"
            ],
            "deployment": {
                "last_deploy_sha": "v5.2.2",
                "minutes_before": 3,
                "author": "platform-eng"
            }
        }
    },
    {
        "id": "configerror-checkout-service-001",
        "alertname": "CreateContainerConfigError",
        "service": "checkout-api",
        "namespace": "payments",
        "cluster": "eks-prod-use1",
        "severity": "high",
        "summary": "Checkout service init container failed; secret stripe-api-secret does not exist.",
        "raw": {
            "pod_describe": {
                "phase": "Pending",
                "restarts": 0,
                "image": "checkout-api:v1.8.3",
                "init_container_status": "CreateContainerConfigError"
            },
            "events": [
                "Secret stripe-api-secret not found in namespace payments",
                "Back-off pulling image checkout-api:v1.8.3",
                "Error creating secret mount: referenced secret not found",
                "Pod initialization failed"
            ],
            "logs": [
                "Unable to locate secret stripe-api-secret in namespace payments"
            ],
            "deployment": {
                "last_deploy_sha": "v1.8.3",
                "minutes_before": 7,
                "author": "checkout-team"
            }
        }
    }
]


def list_scenarios():
    """
    Return a list of compact scenario dicts with keys:
    id, alertname, service, namespace, cluster, severity, summary
    """
    return [
        {
            "id": scenario["id"],
            "alertname": scenario["alertname"],
            "service": scenario["service"],
            "namespace": scenario["namespace"],
            "cluster": scenario["cluster"],
            "severity": scenario["severity"],
            "summary": scenario["summary"]
        }
        for scenario in SCENARIOS
    ]


def get_scenario(scenario_id):
    """
    Return the full scenario dict matching the given id, or None if not found.
    """
    for scenario in SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    return None


# --- Merge Qwen-contributed extra scenarios (reviewed by Claude) ---
try:
    from .scenarios_extra import EXTRA_SCENARIOS as _EXTRA
    _existing = {s["id"] for s in SCENARIOS}
    for _s in _EXTRA:
        if _s["id"] not in _existing:
            SCENARIOS.append(_s)
except Exception as _e:  # pragma: no cover
    pass
