# search_traces Query Patterns

## Basic Patterns

### All traces for a service (last hour)
```
search_traces(
  environment="production",
  services=["api-gateway"]
)
```

### Traces for a specific endpoint
```
search_traces(
  environment="production",
  services=["customers-service"],
  operations=["GET /owners/{ownerId}"]
)
```

### Error traces only
```
search_traces(
  environment="production",
  services=["api-gateway"],
  tags={"error": "true"}
)
```

### 5xx errors specifically
```
search_traces(
  environment="production",
  services=["api-gateway"],
  tags={"http.status_code": "500"}
)
```

---

## Latency Investigation Patterns

### Find slow traces (filter post-search by duration)
```
# Get traces, then filter client-side for duration > threshold
search_traces(
  environment="production",
  services=["api-gateway"],
  startTimeMs=<now - 3600000>,
  limit=50
)
# Then filter results where trace.duration > 1000000 (1 second in microseconds)
```

### Find traces for a specific operation with errors
```
search_traces(
  environment="production",
  services=["vets-service"],
  operations=["GET /vets"],
  tags={"error": "true"},
  limit=20
)
```

---

## Deployment Investigation Patterns

### Traces from a specific deployment version
```
search_traces(
  environment="production",
  services=["api-gateway"],
  tags={"deployment.version": "v2.3.1"},
  limit=20
)
```

### Compare two versions — search each separately
```
# New version
search_traces(environment="production", services=["api-gateway"],
              tags={"deployment.version": "v2.3.1"}, limit=10)

# Old version
search_traces(environment="production", services=["api-gateway"],
              tags={"deployment.version": "v2.2.9"}, limit=10)
```

---

## Multi-Service Investigation Patterns

### Traces touching multiple services
```
# Search by root service; traces will include downstream spans
search_traces(
  environment="production",
  services=["api-gateway"],
  limit=20
)
# Then use get_service_map_for_trace to see all services in each trace
```

### Find traces that hit a specific downstream
```
search_traces(
  environment="production",
  services=["customers-service"],
  tags={"peer.service": "mysql"}
)
```

---

## Time Range Patterns

### Incident window (specific 30-min window)
```
search_traces(
  environment="production",
  services=["api-gateway"],
  startTimeMs=1743000000000,
  endTimeMs=1743001800000,
  limit=50
)
```

### Before and after a deployment
```
# Before deploy (30 min before)
search_traces(
  environment="production",
  services=["api-gateway"],
  startTimeMs=<deploy_time - 1800000>,
  endTimeMs=<deploy_time>,
  limit=20
)

# After deploy (30 min after)
search_traces(
  environment="production",
  services=["api-gateway"],
  startTimeMs=<deploy_time>,
  endTimeMs=<deploy_time + 1800000>,
  limit=20
)
```

---

## Tips

1. **Always include `environment`** — required for reliable results
2. **Start with `limit=20`** — enough to find representative traces; avoid overwhelming results
3. **Results cap at 200** — if you get exactly 200, narrow your filters or time range
4. **Use `operations` to narrow scope** — especially for high-traffic services
5. **Combine with `get_trace_outliers`** — use outliers to find the right operation to search for
6. **`startTimeMs` defaults to now-1h** — always specify for incident investigations outside that window
