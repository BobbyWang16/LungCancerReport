"""Deterministic visual projections of recorded evidence; no predictive learning."""
from collections import defaultdict, Counter

MODALITIES=('PATH','CE','NCE','PET_CT')

def association_edges(g, stratum='ALL', policy='best', significant=True):
    if policy not in ('best','adjusted','raw'): return []
    raw=[e for e in g['edges'] if e['relation']=='associated_with' and e.get('stratum')==stratum]
    adj=[e for e in g['edges'] if e['relation']=='adjusted_association' and e.get('stratum')==stratum]
    if policy=='raw':edges=raw
    elif policy=='adjusted':edges=adj
    else:
        chosen={(e['source'],e['target']):e for e in raw}
        chosen.update({(e['source'],e['target']):e for e in adj})
        edges=list(chosen.values())
    # Choose the estimate before filtering significance; never rescue a failed adjusted
    # result by reverting to a significant raw estimate for the same pair.
    if significant:edges=[e for e in edges if e.get('q') is not None and e['q']<.05]
    return sorted(edges,key=lambda e:e['id'])

def atlas_projection(g,stratum='ALL',policy='best',all_features=False):
    features=[n for n in g['nodes'] if n['kind']=='feature']
    nodes=features if all_features else [n for n in features if n.get('priority')]
    ids={n['id'] for n in nodes}
    eligible=association_edges(g,stratum,policy)
    edges=[e for e in eligible if e['source'] in ids and e['target'] in ids]
    neighbors=defaultdict(set);modalities=defaultdict(set)
    for e in eligible:
        neighbors[e['source']].add(e['target']);neighbors[e['target']].add(e['source'])
        modalities[e['target']].add(e['modality']);modalities[e['source']].add('PATH')
    result=[]
    for n in nodes:
        result.append({**n,'linked_concepts':len(neighbors[n['id']]),'linked_modalities':sorted(modalities[n['id']])})
    return dict(nodes=result,edges=edges,stratum=stratum,policy=policy,all_features=all_features,
                eligible_edges=len(eligible),displayed_edges=len(edges),displayed_nodes=len(nodes),total_features=len(features),
                selection='All dictionary fields' if all_features else 'All fields with at least one estimable review-priority dimension',
                meaning='Node size represents within-report review weight where estimable. Connectivity is descriptive coverage, not importance. Geometry has no clinical-distance interpretation.')

def atlas_metrics(g):
    features=[n for n in g['nodes'] if n['kind']=='feature'];best=association_edges(g)
    endpoints={x for e in best for x in (e['source'],e['target'])}
    by_path=defaultdict(set)
    for e in best:by_path[e['target']].add(e['modality'])
    contrib={e['source'] for e in g['edges'] if e['relation']=='predictive_contribution'}
    path_starts={e['source'] for e in best if e['target'] in contrib}|{e['target'] for e in best if e['source'] in contrib}
    by_report=[]
    for mod in MODALITIES:
        ns=[n for n in features if n['modality']==mod];ps=[n for n in ns if n.get('priority')]
        by_report.append(dict(modality=mod,candidate_fields=len(ns),priority_fields=len(ps),joint_fields=sum(n['priority'].get('joint_weight') is not None for n in ps),
                              association_fields=sum(n['priority'].get('association_weight') is not None for n in ps),
                              contribution_fields=sum(n['id'] in contrib for n in ns),connected_fields=sum(n['id'] in endpoints for n in ns)))
    return dict(version='2026-09-30.KG.VIS.2',graph_version=g['version'],
                candidate_fields=len(features),priority_fields=sum(bool(n.get('priority')) for n in features),
                joint_fields=sum(bool(n.get('priority')) and n['priority'].get('joint_weight') is not None for n in features),
                primary_significant_pairs=len(best),primary_connected_fields=len(endpoints),
                pathology_bridges_two_or_more_modalities=sum(len(ms)>=2 for ms in by_path.values()),
                fields_with_two_step_evidence=len(path_starts),signed_contribution_fields=len(contrib),
                source_traceability_edges=sum(bool(e.get('provenance')) for e in g['edges']),total_edges=len(g['edges']),
                by_report=by_report,
                definition='Primary display: pooled associations, adjusted estimate preferred where available, then q<0.05. Counts describe existing evidence coverage, not clinical improvement.')

def case_projection(g,features,observed,histology):
    fm={f['key']:f for f in features};node_map={n['id']:n for n in g['nodes']}
    present_mods={f['key'].split('.')[0] for f in features}
    permitted=lambda k:histology=='LUAD' or k not in g['adeno_only_keys']
    selected=set();agenda=[]
    for mod in MODALITIES:
        candidates=[n for n in g['nodes'] if n['kind']=='feature' and n.get('modality')==mod and n.get('priority') and mod in present_mods and permitted(n['id'])]
        candidates.sort(key=lambda n:(n['priority'].get('joint_rank') or 999,n['priority'].get('association_rank') or 999,n['id']))
        actual=[n for n in candidates if n['id'] in observed]
        gaps=[n for n in candidates if n['id'] not in observed and fm.get(n['id'],{}).get('value')!=-7]
        selected.update(n['id'] for n in actual[:5]);selected.update(n['id'] for n in gaps[:2])
        for n in gaps[:3]:
            f=fm.get(n['id'],{})
            agenda.append(dict(key=n['id'],status=f.get('status','missing'),priority=n['priority'],
                               reason='Review applicability and source text; absence of coding is not a negative finding.'))
    edges=[e for e in association_edges(g) if e['source'] in selected and e['target'] in selected]
    nodes=[]
    for key in sorted(selected):
        f=fm.get(key,{})
        nodes.append(dict(**node_map[key],value=f.get('value'),status=f.get('status','missing'),observed=key in observed,
                          evidence=f.get('evidence',''),report_ids=f.get('report_ids',[]),manual_override=f.get('manual_override',False)))
    return dict(nodes=nodes,edges=edges,review_agenda=agenda,displayed_nodes=len(nodes),total_input_fields=len(features),
                meaning='Selected reading priorities from submitted modalities, at most five observed and two unresolved fields per report; links are pooled cohort evidence and include unresolved endpoints only as review prompts.')
