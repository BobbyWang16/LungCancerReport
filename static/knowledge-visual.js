'use strict';
let kgView=new URLSearchParams(location.search).has('feature')?'detail':'overview',globalController=null,visualMetrics=null,visualRequest=0;
function setKGView(view){kgView=view;document.querySelectorAll('.kg-view').forEach(el=>el.classList.toggle('hidden',el.id!=='kg-'+view+'-view'));document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('selected',b.dataset.view===view);b.setAttribute('aria-selected',String(b.dataset.view===view));});K('kg-export').classList.toggle('hidden',view!=='detail');}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setKGView(b.dataset.view));
function visualLocalize(){
 const texts={'kg-overview-title':['跨模态关联','Cross-modal associations'],'kg-overview-sub':['查看跨报告联系，点击节点进入统计证据。','Inspect cross-report connections; select a node to inspect its evidence.'],'kg-reset':['复位','Reset'],'kg-svg':['导出SVG','Export SVG'],'kg-all-nodes-label':['显示全部210个字段','Show all 210 fields'],'kg-weight-title':['特征优先级','Feature priorities'],'kg-alpha-label':['阅读偏好：跨模态 / 复发预测','Reading preference: association / prognosis'],'kg-matrix-title':['影像—病理关联矩阵','Imaging–pathology associations']};
 for(const[id,v]of Object.entries(texts))K(id).textContent=v[lang==='en'?1:0];
 for(const b of document.querySelectorAll('[data-view]'))b.textContent=({overview:['全局图谱','Global graph'],weights:['权重地图','Priority map'],matrix:['证据矩阵','Evidence matrix'],detail:['特征详情','Feature detail']})[b.dataset.view][lang==='en'?1:0];
 for(const op of K('kg-global-policy').options)op.textContent=({best:['优先调整证据','Adjusted evidence preferred'],adjusted:['仅调整秩关联','Adjusted rank associations'],raw:['原始关联','Raw associations']})[op.value][lang==='en'?1:0];
 K('kg-matrix-measure').options[0].textContent=choose('调整ρ（有方向）','Adjusted ρ (signed)');K('kg-matrix-measure').options[1].textContent=choose('原始ρ（有方向）','Raw ρ (signed)');
 K('kg-coverage-toggle').textContent=choose('报告覆盖','Report coverage');K('kg-weight-method').textContent=choose('权重说明','About the weights');
 if(kg){for(const id of ['kg-global-pop','kg-matrix-pop']){const keep=K(id).value;K(id).innerHTML='<option value="ALL">'+choose('全部病理','All histologies')+'</option>'+kg.nodes.filter(n=>n.kind==='histology').map(n=>'<option value="'+n.label_en+'">'+n.label_en+'</option>').join('');K(id).value=keep||'ALL';}}
 setKGView(kgView);if(kg){renderGlobal();renderWeightMap();renderMatrix();}
}
function inspectNode(n,container='kg-visual-detail'){
 const p=n.priority;
 K(container).innerHTML=`<div><span class="kg-eyebrow">${esc(n.modality)}</span><h3>${esc(label(n))}</h3><p>${choose('跨模态权重','Association weight')} ${pct(p?.association_weight)} · ${choose('预后权重','Prognostic weight')} ${pct(p?.recurrence_weight)} · ${choose('综合权重','Joint weight')} ${pct(p?.joint_weight)}</p><p class="kg-quiet">${choose('跨报告连接范围','Cross-report connection coverage')}: ${esc(n.linked_modalities?.join(' / ')||'—')} ${choose('（连接数量表示证据覆盖）','(connectivity describes evidence coverage)')}</p></div><button class="button primary" data-open-concept="${esc(n.id)}">${choose('查看原始证据','Inspect evidence')}</button>`;
 K(container).querySelector('[data-open-concept]').onclick=()=>selectNode(n.id);
}
async function renderGlobal(){
 const req=++visualRequest;
 try{
  const hasAdjusted=kg.edges.some(e=>e.relation==='adjusted_association'&&e.stratum===K('kg-global-pop').value);K('kg-global-policy').querySelector('[value=adjusted]').disabled=!hasAdjusted;if(!hasAdjusted&&K('kg-global-policy').value==='adjusted')K('kg-global-policy').value='best';
  const query=new URLSearchParams({stratum:K('kg-global-pop').value,policy:K('kg-global-policy').value,all_features:String(K('kg-all-nodes').checked)});
  const r=await fetch('/api/knowledge/visual?'+query);if(!r.ok)throw Error('Evidence unavailable');const data=await r.json();if(req!==visualRequest)return;
  if(!data.ready)throw Error(data.reason);visualMetrics=data.metrics;const net=data.network;
  globalController=LCGraph.render(K('kg-global-network'),net.nodes,net.edges,{label,onNode:n=>inspectNode(n),onEdge:e=>{setKGView('detail');showEdge(e.id,true);}});
  K('kg-global-note').innerHTML=`<span>${net.displayed_nodes} ${choose('字段','fields')}</span><span>${net.displayed_edges} ${choose('显著关联','significant links')}</span><span>${choose('大小：全队列权重','Size: pooled priority')}</span><span>${choose('点选查看 · 拖动调整','Select to inspect · Drag to move')}</span>`;
  K('kg-visual-detail').innerHTML='';
  K('kg-report-coverage').innerHTML=data.metrics.by_report.map(x=>`<div class="kg-coverage-card" style="border-top-color:${COLORS[x.modality]}"><b>${x.modality.replace('_','-')}</b><strong>${x.priority_fields}<span> / ${x.candidate_fields}</span></strong><p>${choose('具有至少一个重要性维度','At least one estimable priority dimension')}</p><small>${x.joint_fields} ${choose('个双维度字段','jointly estimable fields')}</small></div>`).join('');
 }catch(e){if(req===visualRequest)K('kg-global-note').textContent=choose('全局图谱暂不可用：','Global graph unavailable: ')+e.message;}
}
function interactivePriorities(alpha){
 const nodes=kg.nodes.filter(n=>n.kind==='feature'&&n.priority?.association_weight!=null&&n.priority?.recurrence_weight!=null);
 const totals={};for(const n of nodes)totals[n.modality]=(totals[n.modality]||0)+alpha*n.priority.association_weight+(1-alpha)*n.priority.recurrence_weight;
 return nodes.map(n=>({node:n,weight:totals[n.modality]?(alpha*n.priority.association_weight+(1-alpha)*n.priority.recurrence_weight)/totals[n.modality]:0}));
}
function renderWeightMap(){
 if(!kg)return;const alpha=Number(K('kg-alpha').value)/100,items=interactivePriorities(alpha),svg=K('kg-weight-map');
 K('kg-alpha-value').textContent=`${Math.round(alpha*100)}% / ${Math.round((1-alpha)*100)}%`;K('kg-weight-count').textContent=items.length+' / 210';
 const xmax=Math.max(.3,...items.map(x=>x.node.priority.association_weight))*1.18,ymax=Math.max(.3,...items.map(x=>x.node.priority.recurrence_weight))*1.15;
 const xx=v=>110+780*v/xmax,yy=v=>455-365*v/ymax;let s='<rect width="1000" height="550" fill="#fcfdfd"/>';
 for(let i=0;i<=4;i++){const x=xx(xmax*i/4),y=yy(ymax*i/4);s+=`<path d="M${x} 90V455 M110 ${y}H890" stroke="#e5ecef" stroke-width="1" fill="none"/><text x="${x}" y="480" text-anchor="middle" font-family="Arial" font-size="13" fill="#70818c">${pct(xmax*i/4)}</text><text x="92" y="${y+4}" text-anchor="end" font-family="Arial" font-size="13" fill="#70818c">${pct(ymax*i/4)}</text>`;}
 s+=`<text x="500" y="520" text-anchor="middle" font-size="16" font-family="Arial,Microsoft YaHei" fill="#365a6d">${choose('跨模态关联权重（报告内）','Association weight (within report)')}</text><text x="30" y="275" transform="rotate(-90 30 275)" text-anchor="middle" font-size="16" font-family="Arial,Microsoft YaHei" fill="#365a6d">${choose('复发预测贡献权重（报告内）','Prognostic weight (within report)')}</text>`;
 for(const {node:n,weight:w}of items){const p=n.priority;s+=`<g data-priority-node="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(label(n))}" cursor="pointer"><circle cx="${xx(p.association_weight)}" cy="${yy(p.recurrence_weight)}" r="${5+15*Math.sqrt(w)}" fill="${COLORS[n.modality]}" fill-opacity=".8" stroke="#fff" stroke-width="1.2"/><title>${esc(n.modality+' · '+label(n))} · ${choose('交互阅读权重','Interactive review weight')} ${pct(w)}</title></g>`;}
 Object.entries(COLORS).forEach(([m,c],i)=>{s+=`<circle cx="${200+i*180}" cy="35" r="5" fill="${c}"/><text x="${212+i*180}" y="40" font-family="Arial" font-size="14" fill="#3e5666">${m.replace('_','-')}</text>`;});svg.innerHTML=s;
 svg.querySelectorAll('[data-priority-node]').forEach(el=>{const n=nmap().get(el.dataset.priorityNode);el.onpointerenter=()=>{K('kg-weight-info').textContent=n.modality+' · '+label(n)+' · '+choose('关联','Association')+' '+pct(n.priority.association_weight)+' / '+choose('预后','Prognosis')+' '+pct(n.priority.recurrence_weight);};el.onclick=()=>selectNode(n.id);el.onkeydown=e=>{if(e.key==='Enter')selectNode(n.id);};});
 K('kg-weight-note').textContent=choose('仅绘制30个双维度可估计字段；单维度字段仍在全局图谱和详情中。滑块演示阅读偏好，在每份报告的可估计字段中重新归一化；不会改变风险概率或模型参数。','Only 30 jointly estimable fields are plotted. Single-domain fields remain in the graph and details. The slider illustrates reading preferences, renormalized within each report; it does not change risk estimates or fitted parameters.');
 K('kg-weight-ranking').innerHTML=['PATH','CE','NCE','PET_CT'].map(m=>`<div class="kg-rank-card"><b style="color:${COLORS[m]}">${m.replace('_','-')}</b>${items.filter(x=>x.node.modality===m).sort((a,b)=>b.weight-a.weight).slice(0,4).map((x,i)=>`<button data-rank-node="${esc(x.node.id)}"><span>${i+1} · ${esc(label(x.node))}</span><b>${pct(x.weight)}</b></button>`).join('')}</div>`).join('');K('kg-weight-ranking').querySelectorAll('[data-rank-node]').forEach(b=>b.onclick=()=>selectNode(b.dataset.rankNode));
}
function renderMatrix(){
 if(!kg)return;
 const mod=K('kg-matrix-mod').value,pop=K('kg-matrix-pop').value,selector=K('kg-matrix-measure');
 const data=LCEvidenceMatrix.select(kg,{population:pop,modality:mod,measure:selector.value});
 const names={partial_rank_rho:choose('调整 ρ','Adjusted ρ'),spearman_rho:choose('原始 ρ','Raw ρ'),bias_corrected_cramers_v:'Cramér V',epsilon_squared:'ε²'};
 for(const option of selector.options){option.disabled=!data.counts[option.value];option.textContent=names[option.value]+' · '+data.counts[option.value];}
 selector.value=data.measure;selector.disabled=!data.edges.length;
 const edges=data.edges,measure=data.measure,signed=measure.includes('rho'),map=nmap(),svg=K('kg-evidence-matrix');
 const paths=[...new Set(edges.map(e=>e.target))].sort(),images=[...new Set(edges.map(e=>e.source))].sort();
 const cw=72,ch=42,left=lang==='zh'?220:250,top=lang==='zh'?125:175,width=edges.length?Math.max(520,left+images.length*cw+80):760,height=Math.max(270,top+paths.length*ch+30);
 svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.style.width=width+'px';svg.style.height=height+'px';
 svg.setAttribute('role','img');svg.setAttribute('aria-label',`${pop} · ${mod} · ${names[measure]}`);
 let html=`<defs><pattern id="no-estimate" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#f1f4f5"/><path d="M0 6L6 0" stroke="#e0e6e9" stroke-width=".7"/></pattern></defs><rect width="${width}" height="${height}" fill="#fff"/>`;
 const matrix=new Map(edges.map(e=>[e.source+'|'+e.target,e]));
 images.forEach((id,j)=>html+=`<text x="${left+j*cw+cw/2}" y="${top-12}" transform="rotate(-45 ${left+j*cw+cw/2} ${top-12})" font-family="Arial,Microsoft YaHei" font-size="13" fill="#425d6f"><title>${esc(label(map.get(id)))}</title>${esc(short(label(map.get(id)),lang==='zh'?18:28))}</text>`);
 paths.forEach((id,i)=>{html+=`<text x="${left-12}" y="${top+i*ch+25}" text-anchor="end" font-family="Arial,Microsoft YaHei" font-size="13" fill="#425d6f"><title>${esc(label(map.get(id)))}</title>${esc(short(label(map.get(id)),lang==='zh'?18:28))}</text>`;images.forEach((im,j)=>{
  const e=matrix.get(im+'|'+id),x=left+j*cw,y=top+i*ch,value=e?Math.min(1,Math.abs(e.effect)):0,color=e?(signed&&e.effect<0?'#b87860':'#397f97'):'url(#no-estimate)';
  const title=e?`${label(map.get(im))} ↔ ${label(map.get(id))}: ${e.effect.toFixed(3)}; n=${e.n}; q=${qval(e.q)}`:choose('未估计','Not estimated');
  html+=`<g ${e?'data-matrix-edge="'+esc(e.id)+'" role="button" tabindex="0" aria-label="'+esc(title)+'" cursor="pointer"':''}><title>${esc(title)}</title><rect x="${x+1}" y="${y+1}" width="${cw-2}" height="${ch-2}" rx="4" fill="${color}" fill-opacity="${e?.q<.05?.15+.85*value:e?.18:1}"/><text x="${x+cw/2}" y="${y+25}" text-anchor="middle" font-family="Arial" font-size="12" fill="${e?.q<.05&&value>.65?'#fff':'#425d6f'}">${e?e.effect.toFixed(2):'—'}</text></g>`;
 });});
 if(!edges.length){
  const counts=Object.entries(data.modalities).filter(([,n])=>n>0);
  html+=`<circle cx="70" cy="96" r="24" fill="#edf3f5"/><text x="70" y="103" text-anchor="middle" font-size="24" fill="#678290">—</text><text x="114" y="96" font-family="Arial,Microsoft YaHei" font-size="18" fill="#315469">${choose('当前组合尚无关联估计','No association estimates for this selection')}</text><text x="114" y="128" font-family="Arial,Microsoft YaHei" font-size="14" fill="#617a88">${esc(pop)} · ${choose('患者','Patients')} ${num(data.populationN,0)}${data.reportN!=null?' · '+mod.replace('_','-')+' '+num(data.reportN,0):''}</text><text x="114" y="164" font-family="Arial,Microsoft YaHei" font-size="14" fill="#617a88">${(['ALL','LUAD','LUSC','SCLC'].includes(pop)?choose('未达到配对数或类别数量要求。','Pair or category support requirements were not met.'):choose('当前分层关联未覆盖此组；可在详情中查阅队列信息。','This group is outside the current stratified association analysis. Cohort details remain available.'))}</text>`;
  if(counts.length)html+=`<text x="114" y="204" font-family="Arial,Microsoft YaHei" font-size="14" fill="#397f97">${choose('可切换模态：','Available modalities: ')}${counts.map(([m,n])=>m.replace('_','-')+' ('+n+')').join(' · ')}</text>`;
 }
 svg.innerHTML=html;
 K('kg-matrix-count').textContent=pop+' · '+names[measure];
 K('kg-matrix-summary').innerHTML=[[''+edges.length,choose('可估计关联','Estimates')],[''+data.significant,'q < 0.05'],[data.pairMin===null?'—':num(data.pairMin,0)+'–'+num(data.pairMax,0),choose('成对人数','Paired n')]].map(([v,l])=>`<div><strong>${v}</strong><span>${l}</span></div>`).join('');
 K('kg-matrix-note').innerHTML=edges.length?`<span>${signed?'−1':'0'}</span><i class="effect-gradient ${signed?'signed':''}"></i><span>1</span><span class="legend-divider"></span><span class="legend-square faint"></span><span>q ≥ 0.05</span><span class="legend-square missing"></span><span>${choose('未估计','Unestimated')}</span><span class="matrix-action-hint">${choose('点选查看证据','Select to inspect')}</span>`:'';
 K('kg-matrix-info').textContent=data.changed?choose('已切换至该亚组可用的'+names[measure]+'；未替换人群。','Showing available '+names[measure]+' for the selected subgroup.') : '';
 svg.querySelectorAll('[data-matrix-edge]').forEach(el=>{el.onclick=()=>{setKGView('detail');showEdge(el.dataset.matrixEdge,true);};const inspect=()=>{const e=kg.edges.find(e=>e.id===el.dataset.matrixEdge);K('kg-matrix-info').textContent=label(map.get(e.source))+' ↔ '+label(map.get(e.target))+' · '+e.effect.toFixed(3)+' · n='+num(e.n,0)+' · q='+qval(e.q);};el.onpointerenter=el.onfocus=inspect;el.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();el.onclick();}};});
}
for(const id of ['kg-global-pop','kg-global-policy','kg-all-nodes'])K(id).onchange=renderGlobal;
for(const id of ['kg-matrix-mod','kg-matrix-pop','kg-matrix-measure'])K(id).onchange=renderMatrix;
K('kg-alpha').oninput=renderWeightMap;K('kg-zoom-in').onclick=()=>globalController?.zoomIn();K('kg-zoom-out').onclick=()=>globalController?.zoomOut();K('kg-reset').onclick=()=>globalController?.reset();K('kg-svg').onclick=()=>LCGraph.downloadSVG(K('kg-global-network'),'report_evidence_graph');
for(const id of ['weights','matrix']){const div=document.createElement('div');div.id=id==='weights'?'kg-weight-info':'kg-matrix-info';div.className='kg-inspect kg-quiet';K('kg-'+id+'-view').appendChild(div);}
window.addEventListener('knowledge-ready',visualLocalize);window.addEventListener('knowledge-language',visualLocalize);if(kg)visualLocalize();else setKGView(kgView);
