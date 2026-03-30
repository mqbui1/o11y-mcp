# Incident Playbooks

## Playbook: Latency Spike

**Symptoms**: P99 alert firing, users reporting slowness

1. `list_incidents` → confirm which detector fired, note severity and start time
2. `get_service_topology` (last 1h, environment filter) → look for red/elevated edges
3. `execute_signalflow`: `data('service.request.duration.ns.p99').mean(by=['sf_service']).publish()` → which service is elevated?
4. Narrow by operation: `data('service.request.duration.ns.p99', filter=filter('sf_service', '<svc>')).mean(by=['sf_operation']).publish()`
5. `get_trace_outliers` (services=[<svc>], last 30 min) → get worst operations
6. `search_traces` (services=[<svc>], operations=[<op>], last 30 min) → get trace IDs
7. `get_trace_analysis` on 2–3 trace IDs → identify top latency contributors
8. `get_trace_full` on the worst trace → inspect span tags for root cause clues
9. Verify hypothesis with filtered SignalFlow query (with vs without suspected cause)
10. If dependency is the cause: repeat steps 5–9 for the dependency service

---

## Playbook: Error Surge

**Symptoms**: Error rate alert firing, 5xx responses increasing

1. `list_incidents` → confirm detector, note which service and environment
2. `execute_signalflow`: `data('spans.count', filter=filter('error','true')).sum(by=['sf_service']).publish()` → which service?
3. `execute_signalflow` with `by=['sf_operation']` for that service → which endpoint?
4. `search_traces` (services=[<svc>], tags={"error": "true"}, last 30 min) → get errored trace IDs
5. `get_trace_full` on 2–3 error traces → look at error span tags: `error.message`, `http.status_code`, `db.statement`
6. If DB error: check `db.statement` and `db.instance` tags; look for connection errors
7. If HTTP error: check `http.url`, `http.status_code` on the outbound span
8. `search_events` (last 1h) → any deployments before the errors started?
9. Verify: query error count WITH vs WITHOUT suspected filter

---

## Playbook: Deployment Regression

**Symptoms**: Metrics degraded shortly after a deploy; new version behaving differently

1. `search_events` (last 2h) → find deployment event with timestamp
2. `execute_signalflow`: P99 and error rate — look for step change at deploy time
3. If metrics have `deployment.version` dimension: query old vs new version side-by-side
4. `search_traces` (services=[<svc>], tags={"deployment.version": "<new>"}, last 1h)
5. `get_trace_analysis` on traces from new version → compare contributor profile to expected
6. `search_traces` (same service, old version) → `get_trace_analysis` → compare patterns
7. If new version is clearly worse: recommend rollback; provide metric evidence

---

## Playbook: Dependency Failure

**Symptoms**: Service is slow/erroring but its own code is fine; root cause is downstream

1. `get_service_topology` (last 30 min, environment filter) → look for elevated edge latency
2. `get_service_dependencies` (serviceName=<affected svc>) → list all dependencies
3. `execute_signalflow`: P99 for each dependency service → identify which one is slow
4. `search_traces` (services=[<dependency>], last 30 min) → confirm the dependency has slow traces
5. `get_trace_analysis` on a slow dependency trace → is the issue inside the dependency or its own dependency?
6. Repeat until reaching the root cause service
7. Check `list_incidents` — is there already an alert on the root cause service?

---

## Playbook: Traffic Drop / Silent Failure

**Symptoms**: No errors, no latency spike, but traffic/throughput dropped significantly

1. `execute_signalflow`: `data('spans.count').sum(by=['sf_service']).publish()` → which service dropped?
2. `list_trace_services` → is the service still reporting at all?
3. If service stopped reporting entirely: check infra/container health; look for OOMKill, CrashLoop
4. `list_incidents` → any infra detectors firing (disk, memory, pod restarts)?
5. `search_events` (last 2h) → deployments, config changes, maintenance windows?
6. Check upstream services: if they stopped calling, the downstream will show no spans
7. `get_service_dependencies` → trace the call path upstream from the silent service

---

## Playbook: On-Call Handoff / Health Check

**Goal**: Quickly assess overall system health at the start of an on-call shift

1. `list_incidents` → any active Critical or Major incidents?
2. `list_detectors` (limit=50) → review active detectors; any recently created/modified?
3. `execute_signalflow`: `data('service.request.duration.ns.p99').mean(by=['sf_service']).publish()` → any services elevated?
4. `execute_signalflow`: error count by service → any non-zero baselines?
5. `get_service_topology` (last 1h) → overall service map health
6. If everything is green: confirm and document; note any detectors in warning state to watch
