"""Data lineage and quality models for a deliberately simulated reliability lab."""
from datetime import datetime,timezone
NODES = [
 {"id":"src_orders","label":"Orders API","kind":"source","owner":"Commerce","freshness_sla_min":30,"row_expectation":1200},
 {"id":"src_payments","label":"Payment events","kind":"source","owner":"Payments","freshness_sla_min":20,"row_expectation":950},
 {"id":"src_inventory","label":"Inventory feed","kind":"source","owner":"Supply","freshness_sla_min":40,"row_expectation":800},
 {"id":"stg_orders","label":"stg_orders","kind":"transform","owner":"Data Platform","freshness_sla_min":40,"row_expectation":1200},
 {"id":"stg_payments","label":"stg_payments","kind":"transform","owner":"Data Platform","freshness_sla_min":30,"row_expectation":950},
 {"id":"fact_sales","label":"fact_sales","kind":"model","owner":"Analytics","freshness_sla_min":60,"row_expectation":1100},
 {"id":"fact_stock","label":"fact_stock","kind":"model","owner":"Analytics","freshness_sla_min":60,"row_expectation":800},
 {"id":"dash_revenue","label":"Revenue dashboard","kind":"consumer","owner":"Finance","freshness_sla_min":90,"row_expectation":1100},
 {"id":"dash_ops","label":"Operations dashboard","kind":"consumer","owner":"Operations","freshness_sla_min":90,"row_expectation":800},
]
EDGES=[('src_orders','stg_orders'),('src_payments','stg_payments'),('stg_orders','fact_sales'),('stg_payments','fact_sales'),('src_inventory','fact_stock'),('fact_sales','dash_revenue'),('fact_sales','dash_ops'),('fact_stock','dash_ops')]
LOOKUP={n['id']:n for n in NODES}
FAULTS={'stale','schema','volume'}

def downstream(node_id:str):
    if node_id not in LOOKUP: raise ValueError('Unknown dataset')
    affected=[]; seen={node_id}; queue=[node_id]
    while queue:
        current=queue.pop(0)
        for u,v in EDGES:
            if u==current and v not in seen:
                seen.add(v);queue.append(v);affected.append(v)
    return affected

def upstream(node_id:str):
    if node_id not in LOOKUP: raise ValueError('Unknown dataset')
    seen={node_id}; result=[];queue=[node_id]
    while queue:
        current=queue.pop(0)
        for u,v in EDGES:
            if v==current and u not in seen:
                seen.add(u);queue.append(u);result.append(u)
    return result

def assess(nodes_state:list[dict]):
    issues={}; impacted=set()
    for row in nodes_state:
        fault=row.get('fault')
        if fault:
            issues[row['id']]=fault
            impacted.update(downstream(row['id']))
    enriched=[]
    for row in nodes_state:
        result={**row,'status':'FAILING' if row['id'] in issues else 'IMPACTED' if row['id'] in impacted else 'HEALTHY'}
        enriched.append(result)
    statuses={n['status']:sum(x['status']==n['status'] for x in enriched) for n in [{'status':'HEALTHY'},{'status':'IMPACTED'},{'status':'FAILING'}]}
    return enriched,statuses
