# DBeaver Setup For Autoscaler Postgres Sidecar

This guide connects DBeaver to the PostgreSQL sidecar running inside the autoscaler pod.

## 1. Start Port-Forward

Run this in a terminal and keep it open:

```bash
kubectl port-forward -n thesis-autoscaling deploy/agent-autoscaler 15432:5432
```

If port `15432` is in use, choose another local port.

## 2. Create Connection In DBeaver

- Database type: PostgreSQL
- Host: `localhost`
- Port: `15432`
- Database: `autoscaler`
- Username: `autoscaler`
- Password: `autoscaler`

Click `Test Connection` and then `Finish`.

## 3. Useful Queries

```sql
select count(*) as audit_events_count from audit_events;
```

```sql
select id, created_at, action, desired_replicas, rps, openai_action, openai_confidence
from audit_events
order by id desc
limit 20;
```

```sql
select action, count(*)
from audit_events
group by action
order by count(*) desc;
```

## 4. Notes

- The sidecar database is pod-local and uses `emptyDir`, so data is reset when the pod is recreated.
- For durable storage, move PostgreSQL to a dedicated Deployment + PVC.
