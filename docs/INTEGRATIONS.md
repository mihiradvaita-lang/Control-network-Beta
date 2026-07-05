# Integrations

## Prometheus Alertmanager → Control Network

Point an Alertmanager receiver at `POST /v1/triage`. It accepts the standard Alertmanager v4
webhook payload (`alerts[].labels`, `alerts[].annotations`, `commonLabels`, `fingerprint`, etc.)
and maps it to an incident automatically — `alertname`, `service` (from `service`/`pod`/
`deployment`/`app` labels), `namespace`, `cluster`, `severity`, and a summary from
`annotations.summary`/`description`.

`alertmanager.yml` receiver snippet:

```yaml
receivers:
  - name: control-network
    webhook_configs:
      - url: http://<host>:<port>/v1/triage
        send_resolved: false
```

Reference: [Prometheus Alerting configuration docs](https://prometheus.io/docs/alerting/latest/configuration/#webhook_config).

Alertnames that don't match one of the 5 built-in patterns (`config/patterns.yaml`) still
produce a valid report — with an empty evidence section and a generic narrative — instead of
erroring.

## Slack Incoming Webhook

1. Create a Slack app (or reuse one) and enable **Incoming Webhooks** for your workspace:
   see the [Slack Incoming Webhooks guide](https://api.slack.com/messaging/webhooks).
2. Choose the channel and copy the generated webhook URL
   (`https://hooks.slack.com/services/…`).
3. Set it as an environment variable before starting Control Network:

   ```
   CN_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
   ```

4. Use the **Post to Slack** button (or press `s`) in the UI, or call the API directly:

   ```
   POST /api/slack
   {"scenario_id": "oom-payment-001"}
   ```

If `CN_SLACK_WEBHOOK_URL` is not set, `/api/slack` returns `{"configured": false}` and the UI
falls back to copying the report to your clipboard instead.
