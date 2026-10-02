"""Evidence retrieval is descriptive and never alters risk-model inputs or outputs."""
import hashlib, json
from functools import lru_cache
from .settings import ROOT
from .graph_views import atlas_metrics, atlas_projection, case_projection, association_edges

@lru_cache(maxsize=1)
def graph():
    p=ROOT/'resources/evidence_graph.json'
    if not p.exists(): return None
    return json.loads(p.read_text(encoding='utf8'))

@lru_cache(maxsize=1)
def compatible():
    g=graph()
    return bool(g and hashlib.sha256((ROOT/'models/active_model.json').read_bytes()).hexdigest()==g['model_sha256'])

def public_graph():
    g=graph()
    if not compatible(): return {'ready':False,'reason':'Evidence/model version mismatch or evidence unavailable.'}
    return {'ready':True,**g}

def visual_data(stratum='ALL',policy='best',all_features=False):
    if not compatible():return {'ready':False,'reason':'Evidence/model version mismatch.'}
    g=graph()
    return {'ready':True,'metrics':atlas_metrics(g),'network':atlas_projection(g,stratum,policy,all_features)}

def evidence_paths(feature, stratum='ALL'):
    """Whitelist two-step evidence retrieval; no path multiplication or causal inference."""
    if not compatible(): return {'ready':False,'paths':[]}
    g=graph();nodes={n['id']:n for n in g['nodes']}
    if feature not in nodes or nodes[feature]['kind']!='feature':
        return {'ready':True,'paths':[],'total':0}
    contribution={e['source']:e for e in g['edges'] if e['relation']=='predictive_contribution'}
    chosen={}
    for e in association_edges(g,stratum,'best'):
        if feature not in (e['source'],e['target']):continue
        other=e['target'] if e['source']==feature else e['source']
        if other not in contribution:continue
        # Prefer adjusted evidence where available, without comparing unlike effect families.
        if other not in chosen or e['relation']=='adjusted_association':chosen[other]=e
    paths=[]
    for other,e in chosen.items():
        p=contribution[other]
        paths.append(dict(nodes=[feature,other,'outcome:recurrence'],edge_ids=[e['id'],p['id']],
                          association_population=e['stratum'],contribution_population=p['stratum'],
                          same_patient_sample_established=False,causal_inference=False,
                          positive_heldout_contribution=p.get('effect',0)>0))
    paths.sort(key=lambda p:p['nodes'][1])
    return dict(ready=True,paths=paths,total=len(paths),version=g['version'],
                meaning='Two linked evidence records, not a mediated effect. Populations and measures differ; no composite path score is computed.')

def case_evidence(features):
    if not compatible(): return {'ready':False,'reason':'Evidence/model version mismatch or evidence unavailable.'}
    g=graph(); nodes={n['id']:n for n in g['nodes']}
    observed={f['key']:f for f in features if f.get('value') is not None
              and f.get('status') not in ('missing','uncertain','conflict')
              and (f['key'].endswith('_hu') or f['value']>=0)}
    def permitted(f):
        # LUAD-only findings are not used to build an explanation for other histologies.
        h=observed.get('PATH.histology_code',{}).get('value')
        return h==1 or f['key'] not in g['adeno_only_keys']
    observed={k:f for k,f in observed.items() if permitted(f)}
    items=[]
    for k,f in observed.items():
        p=nodes.get(k,{}).get('priority')
        if p:
            items.append(dict(key=k,value=f['value'],status=f['status'],manual_override=f.get('manual_override',False),
                              report_ids=f.get('report_ids',[]),evidence=f.get('evidence',''),priority=p))
    items.sort(key=lambda x:(x['key'].split('.')[0],x['priority'].get('joint_rank') or 999,x['priority'].get('association_rank') or 999))
    hcode=observed.get('PATH.histology_code',{}).get('value')
    hist=next((n['label_en'] for n in g['nodes'] if n['kind']=='histology' and n.get('code')==hcode),'UNKNOWN')
    links=[e for e in g['edges'] if e['relation'] in ('associated_with','adjusted_association')
           and e['source'] in observed and e['target'] in observed and e.get('q') is not None and e['q']<.05
           and e.get('stratum') in ('ALL',hist)]
    links.sort(key=lambda e:(e['relation']!='adjusted_association',-abs(e.get('effect') or 0),e['id']))
    facts=[dict(id='finding:'+f['key'],concept=f['key'],value=f.get('value'),status=f.get('status'),
                report_ids=f.get('report_ids',[]),evidence=f.get('evidence',''),manual_override=f.get('manual_override',False),previous_value=f.get('previous_value'),
                interpretation='recorded assertion, unresolved status retained') for f in features]
    return dict(ready=True,version=g['version'],histology=hist,observed_features=len(observed),priorities=items,facts=facts,
                visual=case_projection(g,features,observed,hist),
                matched_edge_ids=[e['id'] for e in links],matched_edge_count=len(links),
                unresolved_keys=[f['key'] for f in features if f.get('status') in ('uncertain','conflict')],
                meaning='Feature presence retrieves cohort evidence. It does not establish patient-specific effect, concordance, causation or a risk explanation.')
