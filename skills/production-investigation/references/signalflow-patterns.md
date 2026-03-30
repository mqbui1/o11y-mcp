# SignalFlow Patterns for Production Investigation

## APM Latency

### P99 by service (all services, last hour)
```
data('service.request.duration.ns.p99')
  .mean(by=['sf_service', 'sf_environment'])
  .publish()
```

### P99 for a specific service
```
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway') and filter('sf_environment', 'production'))
  .mean().publish(label='p99_ms')
```

### P99 broken down by operation
```
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway'))
  .mean(by=['sf_operation'])
  .publish()
```

### Compare two deployment versions
```
A = data('service.request.duration.ns.p99',
         filter=filter('sf_service', 'api-gateway') and filter('deployment.version', 'v2'))
      .mean().publish(label='new')
B = data('service.request.duration.ns.p99',
         filter=filter('sf_service', 'api-gateway') and filter('deployment.version', 'v1'))
      .mean().publish(label='old')
```

---

## APM Errors

### Error count by service
```
data('spans.count',
     filter=filter('sf_environment', 'production') and filter('error', 'true'))
  .sum(by=['sf_service'])
  .publish()
```

### Error rate (errors / total) for a service
```
errors = data('spans.count',
              filter=filter('sf_service', 'checkout') and filter('error', 'true'))
           .sum()
total  = data('spans.count',
              filter=filter('sf_service', 'checkout'))
           .sum()
(errors / total * 100).publish(label='error_rate_pct')
```

### Error count by HTTP status code
```
data('spans.count',
     filter=filter('sf_service', 'api-gateway') and filter('error', 'true'))
  .sum(by=['http.status_code'])
  .publish()
```

---

## Throughput

### Request rate (spans per minute) by service
```
data('spans.count')
  .sum(by=['sf_service'])
  .publish()
```

### Traffic drop detection — rolling mean comparison
```
current = data('spans.count', filter=filter('sf_service', 'api-gateway'))
            .sum().mean(over='5m')
baseline = data('spans.count', filter=filter('sf_service', 'api-gateway'))
             .sum().mean(over='1h')
(current / baseline * 100).publish(label='traffic_pct_of_baseline')
```

---

## Infrastructure (host metrics)

### CPU utilization by host
```
data('cpu.utilization')
  .mean(by=['host'])
  .publish()
```

### Memory utilization
```
data('memory.utilization')
  .mean(by=['host'])
  .publish()
```

### Disk I/O
```
data('disk.utilization')
  .mean(by=['host', 'device'])
  .publish()
```

---

## Events (custom / deployment)

### Query custom events via SignalFlow
```
events(eventType='deployment.started').publish()
```

```
events(eventType='behavioral_baseline.incident.opened',
       filter=filter('sf_environment', 'production')).publish()
```

Note: Events are returned as event messages in the SignalFlow response, not as data points.

---

## SignalFlow Rules (avoid these mistakes)

1. `detect()` requires a boolean — use `detect(when(A > threshold))` not `detect(A)`
2. `data()` takes one filter via `filter=` keyword — combine multiples with `and`:
   `filter=filter('sf_service','x') and filter('error','true')`
3. `lasting` belongs inside `when()`:
   `detect(when(A > B, lasting=duration('5m')))`
4. `filter()` with multiple values is OR across those values:
   `filter('sf_service', 'svc-a', 'svc-b')` matches either service
