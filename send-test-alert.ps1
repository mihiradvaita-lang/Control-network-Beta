# Fires a realistic Prometheus Alertmanager v4 webhook at the running Control Network
# server, exactly like a real cluster would. Make sure start.bat is running first.
$body = @'
{
  "version": "4",
  "status": "firing",
  "receiver": "control-network",
  "groupLabels": { "alertname": "KubePodOOMKilled" },
  "commonLabels": { "alertname": "KubePodOOMKilled", "namespace": "prod", "severity": "critical" },
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "KubePodOOMKilled",
        "service": "payment-service",
        "namespace": "prod",
        "cluster": "eks-prod-use1",
        "pod": "payment-service-7d9f8b6c5-x2j9l",
        "severity": "critical"
      },
      "annotations": { "summary": "payment-service OOMKilled 12 min after deploy v2.3.1" }
    }
  ]
}
'@
Write-Host "Firing a test OOMKill alert into http://localhost:8000/v1/triage ...`n"
try {
  $r = Invoke-RestMethod -Uri "http://localhost:8000/v1/triage" -Method Post -ContentType "application/json" -Body $body
  Write-Host "Pattern matched:" $r.pattern "  (llm:" $r.llm ")`n"
  Write-Host "----- INCIDENT REPORT -----`n"
  Write-Host $r.report_markdown
} catch {
  Write-Host "Could not reach the server. Is start.bat running on port 8000?`n$_"
}
Write-Host "`nPress Enter to close..."
[void][System.Console]::ReadLine()
