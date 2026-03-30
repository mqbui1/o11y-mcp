# Muting Rule Examples

## Planned Maintenance Window

Suppress all alerts for an environment during a maintenance window:
```json
{
  "description": "Maintenance window 2026-04-01 02:00-04:00 UTC",
  "filters": [
    {"property": "sf_environment", "propertyValue": "production"}
  ],
  "startTime": 1743469200000,
  "stopTime":  1743476400000
}
```

## Mute a Specific Service

Suppress alerts only for a specific service during a deploy:
```json
{
  "description": "Deploying api-gateway v2.4.0 — expected brief latency spike",
  "filters": [
    {"property": "sf_service", "propertyValue": "api-gateway"}
  ],
  "startTime": 1743469200000,
  "stopTime":  1743470100000
}
```

## Mute a Specific Detector

Suppress a known-noisy detector while investigating a false positive:
```json
{
  "description": "Muting noisy latency detector while tuning thresholds",
  "filters": [
    {"property": "detector_name", "propertyValue": "api-gateway P99 Latency Warning"}
  ],
  "startTime": 1743469200000,
  "stopTime":  1743493200000
}
```

## Mute Only Critical Severity

Downgrade to Warning-only alerting during off-hours:
```json
{
  "description": "Off-hours: mute Critical, allow Warning to notify async",
  "filters": [
    {"property": "sf_environment", "propertyValue": "production"},
    {"property": "severity", "propertyValue": "Critical"}
  ],
  "startTime": 1743469200000,
  "stopTime":  1743504000000
}
```

## Muting Best Practices

1. **Always set `stopTime`** — open-ended muting silently suppresses real incidents indefinitely
2. **Use the narrowest filter** — mute one service, not the entire environment, if possible
3. **Review before creating** — `list_muting_rules` to see if a rule already covers the window
4. **Document the reason** — use the `description` field; it shows in the UI and audit logs
5. **Delete expired rules** — `list_muting_rules` with `includeExpired=false` to clean up
