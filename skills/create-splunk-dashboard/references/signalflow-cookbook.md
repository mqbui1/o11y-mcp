# SignalFlow Cookbook for Dashboards

## Golden Signals

### 1. Latency — P99 heatmap by service
```
data('service.request.duration.ns.p99')
  .mean(by=['sf_service', 'sf_environment'])
  .publish(label='P99 Latency (ns)')
```

### 2. Latency — P50 vs P99 comparison
```
data('service.request.duration.ns.p50',
     filter=filter('sf_service', 'api-gateway'))
  .mean().publish(label='P50')

data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway'))
  .mean().publish(label='P99')
```

### 3. Errors — absolute count
```
data('spans.count',
     filter=filter('sf_environment', 'production') and filter('error', 'true'))
  .sum(by=['sf_service']).publish(label='Errors')
```

### 4. Errors — rate percentage
```
errors = data('spans.count',
              filter=filter('sf_service', 'api-gateway') and filter('error', 'true'))
           .sum()
total  = data('spans.count',
              filter=filter('sf_service', 'api-gateway'))
           .sum()
(errors / total * 100).publish(label='Error Rate %')
```

### 5. Traffic — spans per interval
```
data('spans.count',
     filter=filter('sf_service', 'api-gateway'))
  .sum().publish(label='Request Rate')
```

### 6. Saturation — CPU utilization
```
data('cpu.utilization')
  .mean(by=['host']).publish(label='CPU %')
```

### 7. Saturation — memory utilization
```
data('memory.utilization')
  .mean(by=['host']).publish(label='Memory %')
```

---

## Service Breakdown Charts

### Top N operations by P99 (List chart)
```
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway'))
  .mean(by=['sf_operation'])
  .publish(label='P99 by Operation')
```

### Error count by operation
```
data('spans.count',
     filter=filter('sf_service', 'api-gateway') and filter('error', 'true'))
  .sum(by=['sf_operation'])
  .publish(label='Errors by Operation')
```

### P99 for multiple services (comparison)
```
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway', 'vets-service', 'customers-service'))
  .mean(by=['sf_service'])
  .publish(label='P99 Latency')
```

---

## Event Overlay Charts

### Deployment events
```
events(eventType='deployment.started').publish(label='Deployments')
```

### Alert/incident events
```
events(eventType='anomaly.detected').publish(label='Anomalies')
```

### Custom events filtered by environment
```
events(eventType='deployment.started',
       filter=filter('sf_environment', 'production'))
  .publish(label='Production Deployments')
```

---

## Infrastructure Charts

### Host CPU by host
```
data('cpu.utilization')
  .mean(by=['host'])
  .publish(label='CPU %')
```

### Disk usage by device
```
data('disk.utilization')
  .mean(by=['host', 'device'])
  .publish(label='Disk %')
```

### Network throughput
```
data('network.total')
  .sum(by=['host'])
  .publish(label='Network bytes/s')
```

### Container CPU (Kubernetes)
```
data('container_cpu_utilization')
  .mean(by=['kubernetes_pod_name', 'kubernetes_namespace'])
  .publish(label='Container CPU %')
```

---

## Anomaly / Baseline Comparison

### Current vs rolling average (anomaly signal)
```
current  = data('service.request.duration.ns.p99',
                filter=filter('sf_service', 'api-gateway'))
             .mean().mean(over='5m')
baseline = data('service.request.duration.ns.p99',
                filter=filter('sf_service', 'api-gateway'))
             .mean().mean(over='1h')
current.publish(label='Current P99 (5m avg)')
baseline.publish(label='Baseline P99 (1h avg)')
(current / baseline).publish(label='Ratio vs Baseline')
```

### Error rate vs 24h baseline
```
current_errors = data('spans.count',
                      filter=filter('sf_service','api-gateway') and filter('error','true'))
                   .sum().mean(over='5m')
baseline_errors = data('spans.count',
                       filter=filter('sf_service','api-gateway') and filter('error','true'))
                    .sum().mean(over='24h')
current_errors.publish(label='Current Error Rate')
baseline_errors.publish(label='24h Avg Error Rate')
```
