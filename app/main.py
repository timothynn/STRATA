from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from .domain import NODES,EDGES,LOOKUP,FAULTS,assess,downstream,upstream
WEB=Path(__file__).resolve().parent.parent/'web'

def utc_now(): return datetime.now(timezone.utc).isoformat()

class InjectFault(BaseModel):
    node_id: str=Field(min_length=1,max_length=80)
    fault: str=Field(min_length=1,max_length=20)

class Recover(BaseModel):
    node_id:str=Field(min_length=1,max_length=80)

def create_app(db_path:str|None=None):
    app=FastAPI(title='STRATA — Data Reliability Control Plane',version='1.0.0',description='Simulated data quality and lineage incident response sandbox.')
    path=db_path or str(Path(os.getenv('DATA_DIR','.'))/'strata.db')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    def db():
        con=sqlite3.connect(path,timeout=10)
        con.row_factory=sqlite3.Row
        return con
    with db() as cx:
        cx.execute('CREATE TABLE IF NOT EXISTS node_state (node_id TEXT PRIMARY KEY, fault TEXT, updated_at TEXT NOT NULL)')
        cx.execute('CREATE TABLE IF NOT EXISTS incidents (id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL, fault TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT)')
        cx.execute('CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, node_id TEXT, at TEXT NOT NULL, details TEXT NOT NULL)')
        for node in NODES:
            cx.execute('INSERT OR IGNORE INTO node_state (node_id,fault,updated_at) VALUES (?,?,?)',(node['id'],None,utc_now()))
    def snapshot():
        with db() as cx: rows={r['node_id']:dict(r) for r in cx.execute('SELECT * FROM node_state')}
        nodes=[{**n,'fault':rows[n['id']]['fault'],'updated_at':rows[n['id']]['updated_at']} for n in NODES]
        enriched,counts=assess(nodes)
        failing=[n for n in enriched if n['status']=='FAILING']
        return {'nodes':enriched,'edges':[{'source':a,'target':b} for a,b in EDGES],
                'summary':{'datasets':len(enriched),'healthy':counts['HEALTHY'],'impacted':counts['IMPACTED'],'failing':counts['FAILING'], 'reliability_pct':round(100*counts['HEALTHY']/len(enriched),1), 'open_incidents':len(failing)},
                'mode':'SIMULATION','updated_at':utc_now()}
    @app.get('/health')
    def health():return {'ok':True,'service':'strata'}
    @app.get('/api/overview')
    def overview():return snapshot()
    @app.get('/api/lineage/{node_id}')
    def lineage(node_id:str):
        if node_id not in LOOKUP:raise HTTPException(404,'Unknown dataset')
        return {'node':LOOKUP[node_id],'upstream':upstream(node_id),'downstream':downstream(node_id)}
    @app.get('/api/checks')
    def checks():
        state=snapshot()
        checks=[]
        for node in state['nodes']:
            for kind,title in [('freshness','Freshness SLA'),('schema','Schema contract'),('volume','Volume threshold')]:
                issue=(node['fault']=='stale' and kind=='freshness') or (node['fault']==kind)
                checks.append({'dataset':node['id'],'check':title,'type':kind,'status':'FAIL' if issue else 'PASS','expected':f"≤ {node['freshness_sla_min']} min" if kind=='freshness' else 'Expected contract' if kind=='schema' else f"≈ {node['row_expectation']} rows"})
        return {'checks':checks,'mode':'SIMULATION'}
    @app.get('/api/incidents')
    def incidents():
        with db() as cx:
            incidents=[dict(row) for row in cx.execute('SELECT * FROM incidents ORDER BY id DESC LIMIT 75')]
            activity=[dict(row) for row in cx.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 80')]
        return {'incidents':incidents,'activity':activity}
    @app.post('/api/fault')
    def inject(req:InjectFault):
        if req.node_id not in LOOKUP:raise HTTPException(404,'Unknown dataset')
        if req.fault not in FAULTS: raise HTTPException(422,'Fault must be stale, schema or volume')
        with db() as cx:
            exists=cx.execute('SELECT fault FROM node_state WHERE node_id=?',(req.node_id,)).fetchone()
            if exists and exists['fault'] is not None:raise HTTPException(409,'Resolve existing incident first')
            now=utc_now()
            cx.execute('UPDATE node_state SET fault=?,updated_at=? WHERE node_id=?',(req.fault,now,req.node_id))
            cx.execute('INSERT INTO incidents(node_id,fault,status,created_at) VALUES(?,?,?,?)',(req.node_id,req.fault,'OPEN',now))
            cx.execute('INSERT INTO activity(action,node_id,at,details) VALUES(?,?,?,?)',('FAULT_INJECTED',req.node_id,now,f'Simulated {req.fault} anomaly'))
        return {'ok':True,'affected':downstream(req.node_id),'overview':snapshot()}
    @app.post('/api/recover')
    def recover(req:Recover):
        if req.node_id not in LOOKUP:raise HTTPException(404,'Unknown dataset')
        with db() as cx:
            state=cx.execute('SELECT fault FROM node_state WHERE node_id=?',(req.node_id,)).fetchone()
            if state['fault'] is None:raise HTTPException(409,'Dataset is already healthy')
            now=utc_now()
            cx.execute('UPDATE node_state SET fault=NULL,updated_at=? WHERE node_id=?',(now,req.node_id))
            cx.execute("UPDATE incidents SET status='RESOLVED',resolved_at=? WHERE node_id=? AND status='OPEN'",(now,req.node_id))
            cx.execute('INSERT INTO activity(action,node_id,at,details) VALUES(?,?,?,?)',('RECOVERED',req.node_id,now,'Simulated incident recovered'))
        return {'ok':True,'overview':snapshot()}
    @app.post('/api/reset')
    def reset():
        with db() as cx:
            now=utc_now()
            cx.execute('UPDATE node_state SET fault=NULL,updated_at=?',(now,))
            cx.execute("UPDATE incidents SET status='RESOLVED',resolved_at=? WHERE status='OPEN'",(now,))
            cx.execute('INSERT INTO activity(action,node_id,at,details) VALUES(?,?,?,?)',('RESET',None,now,'All simulated faults cleared'))
        return {'ok':True,'overview':snapshot()}
    @app.get('/')
    def index():return FileResponse(WEB/'index.html')
    app.mount('/static',StaticFiles(directory=WEB),name='static')
    return app
app=create_app()
