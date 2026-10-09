# STRATA — Architecture and modeling notes

## Data model

A **nine-node directed acyclic graph** represents three source systems, two staging tables, two marts and two analytics consumers. The graph uses eight explicitly defined dependencies. All nodes have an owner, a freshness SLA, and an expected row-volume value.

```text
Orders API ------> stg_orders ------> fact_sales ----> Revenue dashboard
Payment events --> stg_payments ----/            \--> Operations dashboard
Inventory feed ---------------------> fact_stock ----/
```

`downstream(node)` performs a breadth-first graph traversal. On fault injection, the selected node becomes `FAILING` and every downstream dependency becomes `IMPACTED` unless it has its own direct fault, in which case it remains `FAILING`. Resolving a fault recomputes all statuses from the current active fault set: multiple simultaneous failures are supported.

## Persistent records

- `node_state`: each node's active simulated fault and update time.
- `incidents`: open/resolved incident records and timestamps.
- `activity`: a chronological audit-like event log for demo user actions.

SQLite writes are transactional. This is single-instance local persistence; not a distributed incident event store.

## Quality checks

Three rule families are exposed for each dataset: freshness, schema contract, and row volume. The current implementation simulates rule failures by injecting a named anomaly; it does **not** query Airflow, dbt, Spark or external data sources. The checks are reference behavior and correctly report simulated status.

## Production roadmap

- Connect to OpenLineage/Marquez events and Airflow/Dagster asset metadata.
- Run real schema, freshness and volume checks against authorized source systems.
- Add suppression/deduplication, incident acknowledgements, service ownership and severity policies.
- Add auth, RBAC, alert destinations, encrypted credentials, tenancy and audit retention.
- Use PostgreSQL + queue workers for concurrent checks; add OpenTelemetry and metrics.
