# SignalFlow detect() Pattern Library

## Threshold Patterns

### Greater than (sustained)
```
A = data('metric.name', filter=filter('sf_service', 'my-svc')).mean()
detect(when(A > 100, lasting=duration('5m'))).publish(label='threshold_breach')
```

### Less than (sustained)
```
A = data('spans.count', filter=filter('sf_service', 'my-svc')).sum()
detect(when(A < 10, lasting=duration('5m'))).publish(label='low_traffic')
```

### Between two values (out-of-band)
```
A = data('my.metric').mean()
detect(when(A < 50) or when(A > 200)).publish(label='out_of_range')
```

---

## Dynamic / Anomaly Patterns

### Spike vs short rolling mean
```
f = filter('sf_service', 'api-gateway')
A = data('service.request.duration.ns.p99', filter=f).mean().mean(over='5m')
B = data('service.request.duration.ns.p99', filter=f).mean().mean(over='1h')
detect(when(A > B * 3, lasting=duration('5m'))).publish(label='spike')
```

### Drop vs rolling mean (traffic loss)
```
f = filter('sf_service', 'api-gateway')
current  = data('spans.count', filter=f).sum().mean(over='5m')
baseline = data('spans.count', filter=f).sum().mean(over='1h')
detect(when(current < baseline * 0.5, lasting=duration('5m'))).publish(label='drop')
```

### Standard deviation band (using mean ± N*stddev)
```
f = filter('sf_service', 'my-svc')
A        = data('my.metric', filter=f).mean().mean(over='5m')
mean_1h  = data('my.metric', filter=f).mean().mean(over='1h')
stddev_1h = data('my.metric', filter=f).stddev(over='1h')
upper = mean_1h + stddev_1h * 3
detect(when(A > upper, lasting=duration('5m'))).publish(label='anomaly')
```

---

## Error Patterns

### Error rate (percentage)
```
f_env = filter('sf_environment', 'production') and filter('sf_service', 'api-gateway')
errors = data('spans.count', filter=f_env and filter('error', 'true')).sum()
total  = data('spans.count', filter=f_env).sum()
rate   = (errors / total * 100).mean(over='5m')
detect(when(rate > 5, lasting=duration('3m'))).publish(label='high_error_rate')
```

### Absolute error count spike
```
f = filter('sf_service', 'api-gateway') and filter('error', 'true')
errors = data('spans.count', filter=f).sum().mean(over='5m')
baseline = data('spans.count', filter=f).sum().mean(over='1h')
detect(when(errors > baseline * 5, lasting=duration('3m'))).publish(label='error_spike')
```

---

## APM Latency Patterns

### P99 absolute threshold (nanoseconds)
```
# 1 second = 1,000,000,000 ns; 500ms = 500,000,000 ns
A = data('service.request.duration.ns.p99',
         filter=filter('sf_service', 'api-gateway') and filter('sf_environment', 'production'))
      .mean().mean(over='5m')
detect(when(A > 1000000000, lasting=duration('5m'))).publish(label='latency_critical')
```

### P99 vs P50 tail ratio (latency distribution widening)
```
f = filter('sf_service', 'api-gateway')
p99 = data('service.request.duration.ns.p99', filter=f).mean()
p50 = data('service.request.duration.ns.p50', filter=f).mean()
ratio = (p99 / p50).mean(over='5m')
detect(when(ratio > 10, lasting=duration('5m'))).publish(label='tail_widening')
```

---

## Infrastructure Patterns

### CPU saturation
```
A = data('cpu.utilization').mean(by=['host']).mean(over='5m')
detect(when(A > 90, lasting=duration('10m'))).publish(label='high_cpu')
```

### Memory saturation
```
A = data('memory.utilization').mean(by=['host']).mean(over='5m')
detect(when(A > 85, lasting=duration('10m'))).publish(label='high_memory')
```

### Disk filling up
```
A = data('disk.utilization').mean(by=['host', 'device']).mean(over='15m')
detect(when(A > 85, lasting=duration('15m'))).publish(label='disk_warning')
```

---

## Multi-rule (tiered severity)

```
f = filter('sf_service', 'api-gateway') and filter('sf_environment', 'production')
A = data('service.request.duration.ns.p99', filter=f).mean().mean(over='5m')
B = data('service.request.duration.ns.p99', filter=f).mean().mean(over='1h')

detect(when(A > B * 2, lasting=duration('5m'))).publish(label='warn')
detect(when(A > B * 5, lasting=duration('5m'))).publish(label='crit')
```

Rules JSON:
```json
[
  {"severity": "Warning",  "detectLabel": "warn", "name": "Latency Warning  (2x baseline)"},
  {"severity": "Critical", "detectLabel": "crit", "name": "Latency Critical (5x baseline)"}
]
```

---

## Lasting Duration Guidelines

| Use case | Recommended lasting |
|---|---|
| Fast-moving metric (p99, error rate) | `duration('3m')` – `duration('5m')` |
| Infrastructure (CPU, memory) | `duration('10m')` – `duration('15m')` |
| Traffic drop | `duration('5m')` |
| Business KPI | `duration('15m')` – `duration('30m')` |

Shorter lasting = more sensitive, more false positives.
Longer lasting = fewer alerts, but delayed notification.
