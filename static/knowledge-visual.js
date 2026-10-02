'use strict';
const requestedView=new URLSearchParams(location.search).get('view');
let kgView=new URLSearchParams(location.search).has('feature')?'detail':(['weights','overview','matrix','detail'].includes(requestedView)?requestedView:'weights'),globalController=null,visualRequest=0,priorityMode='joint';
function setKGView(view){
 kgView=view;document.querySelectorAll('.kg-view').forEach(el=>el.classList.toggle('hidden',el.id!=='kg-'+view+'-view'));
 document.querySelectorAll('[data-view]').forEach(b=>{const active=b.dataset.view===view||(b.dataset.view==='overview'&&view==='matrix');b.classList.toggle('selected',active);b.setAttribute('aria-current',active?'page':'false');});
 const association=['overview','matrix'].includes(view);K('kg-association-tools').classList.toggle('hidden',!association);
 document.querySelectorAll('[data-association-view]').forEach(b=>{b.classList.toggle('selected',b.dataset.associationView===view);b.setAttribute('aria-pressed',String(b.dataset.associationView===view));});
 K('kg-export').classList.toggle('hidden',view!=='detail');history.replaceState(null,'',view==='detail'?'?feature='+encodeURIComponent(selected):'?view='+view);
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setKGView(b.dataset.view));
document.querySelectorAll('[data-association-view]').forEach(b=>b.onclick=()=>{const pop=K(kgView==='matrix'?'kg-matrix-pop':'kg-global-pop').value;K('kg-global-pop').value=pop;K('kg-matrix-pop').value=pop;setKGView(b.dataset.associationView);renderGlobal();renderMatrix();});
function visualLocalize(){
 const texts={'kg-overview-title':['影像与病理如何关联','How imaging and pathology connect'],'kg-reset':['复位','Reset'],'kg-svg':['导出SVG','Export SVG'],'kg-all-nodes-label':['全部特征','All features'],'kg-weight-title':['哪些特征值得关注','Which features deserve attention'],'kg-alpha-label':['关联 / 复发','Association / recurrence'],'kg-matrix-title':['关联强度','Association strength'],'kg-pooled-label':['全队列','Pooled cohort'],'kg-display-options-label':['显示选项','Display options'],'kg-compare-title':['双维度对照','Compare both dimensions'],'kg-neighborhood-title':['关系图','Connections']};
 for(const[id,v]of Object.entries(texts))K(id).textContent=v[lang==='en'?1:0];
 for(const b of document.querySelectorAll('[data-view]'))b.querySelector('[data-view-label]').textContent=({overview:['跨模态关联','Cross-modal links'],weights:['报告重点','Report priorities'],detail:['统计证据','Statistical evidence']})[b.dataset.view][lang==='en'?1:0];
 for(const b of document.querySelectorAll('[data-association-view]'))b.textContent=({overview:['关系图','Network'],matrix:['关联热图','Heatmap']})[b.dataset.associationView][lang==='en'?1:0];
 for(const b of document.querySelectorAll('[data-priority-mode]'))b.textContent=({joint:['综合重点','Combined'],association:['跨模态关联','Association'],recurrence:['复发预测','Recurrence prediction']})[b.dataset.priorityMode][lang==='en'?1:0];
 for(const op of K('kg-global-policy').options)op.textContent=({best:['优先调整证据','Adjusted preferred'],adjusted:['仅调整秩关联','Adjusted rank only'],raw:['原始关联','Raw associations']})[op.value][lang==='en'?1:0];
 K('kg-weight-method').textContent=choose('权重说明','About the weights');
 K('kg-graph-method').textContent=choose('节点大小为全队列报告内权重；连线为所选人群的显著关联。可拖动、缩放，点击查看统计证据。','Node size reflects pooled within-report priority; links show significant associations in the selected population. Drag, zoom or select to inspect.');
 K('kg-global-network').setAttribute('aria-label',choose('影像与病理关联图','Imaging–pathology association network'));
 for(const [id,zh,en]of [['kg-global-pop','病理分组','Histology group'],['kg-global-policy','关联估计','Association policy'],['kg-matrix-pop','病理分组','Histology group'],['kg-matrix-mod','报告类型','Report type'],['kg-matrix-measure','效应量','Association measure']])K(id).setAttribute('aria-label',choose(zh,en));
 for(const[id,zh,en]of [['kg-zoom-in','放大','Zoom in'],['kg-zoom-out','缩小','Zoom out']])K(id).setAttribute('aria-label',choose(zh,en));
 if(kg){for(const id of ['kg-global-pop','kg-matrix-pop']){const keep=K(id).value;K(id).innerHTML='<option value="ALL">'+choose('全部病理','All histologies')+'</option>'+kg.nodes.filter(n=>n.kind==='histology').map(n=>'<option value="'+esc(n.label_en)+'">'+esc(n.label_en)+'</option>').join('');K(id).value=keep||'ALL';}}
 setKGView(kgView);if(kg){renderPriorityRanking();renderGlobal();renderWeightMap();renderMatrix();}
}
function reportTitle(mod){return ({PATH:['术后病理','Pathology'],CE:['增强 CT','Contrast CT'],NCE:['平扫 CT','Non-contrast CT'],PET_CT:['PET-CT','PET-CT']})[mod][lang==='en'?1:0];}
function renderPriorityRanking(){
 if(!kg)return;
 document.querySelectorAll('[data-priority-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.priorityMode===priorityMode);b.setAttribute('aria-pressed',String(b.dataset.priorityMode===priorityMode));});
 const groups=LCPriorities.select(kg,priorityMode);
 K('kg-priority-ranking').innerHTML=groups.map(({modality:m,items})=>{
  const max=items[0]?.weight||1;
  const row=(x,i)=>`<button class="kg-priority-row" data-rank-node="${esc(x.node.id)}" aria-label="${esc(label(x.node))} ${pct(x.weight)}"><span class="kg-rank-number">${String(i+1).padStart(2,'0')}</span><span class="kg-rank-label">${esc(label(x.node))}<i class="kg-rank-track"><i style="width:${Math.max(0,x.weight/max*100)}%;background:${COLORS[m]}"></i></i></span><strong>${pct(x.weight)}</strong></button>`;
  return `<article class="kg-ranking-card" style="--report-color:${COLORS[m]}"><h3><i></i>${reportTitle(m)}</h3>${items.length?items.slice(0,5).map(row).join(''):`<p class="kg-no-weight">${choose('暂无可估计权重','No estimable weights')}</p>`}${items.length>5?`<details class="kg-rank-more"><summary>${choose('更多特征','More features')}</summary>${items.slice(5).map((x,i)=>row(x,i+5)).join('')}</details>`:''}</article>`;
 }).join('');
 K('kg-priority-ranking').querySelectorAll('[data-rank-node]').forEach(b=>b.onclick=()=>selectNode(b.dataset.rankNode));
 K('kg-weight-note').textContent=choose('排名与权重来自冻结的全队列分析，分别在每类报告内比较。综合重点为关联与三年折外预测贡献的50:50组合，仅包括两个维度都可估计的特征；切换维度可查看单维度特征。没有可估计权重不表示不重要。这些权重不是个体风险贡献。对照图的滑块仅改变阅读偏好，不改变已拟合的预测模型。','Ranks and weights come from the frozen pooled-cohort analysis and are compared within each report type. Combined priority uses a 50:50 mixture of association and held-out three-year predictive contribution, restricted to jointly estimable fields. Other dimensions include fields with only one estimable weight. Unestimated does not mean unimportant. These are not patient-specific risk contributions. The comparison slider changes reading preferences, not fitted predictions.');
}
function inspectNode(n){
 const p=n.priority;K('kg-visual-detail').innerHTML=`<div><h3>${esc(label(n))}</h3><div class="weight-metrics"><span>${choose('关联权重','Association')}<b>${pct(p?.association_weight)}</b></span><span>${choose('复发权重','Recurrence')}<b>${pct(p?.recurrence_weight)}</b></span></div></div><button class="button primary" data-open-concept="${esc(n.id)}">${choose('统计证据','View evidence')}</button>`;
 K('kg-visual-detail').querySelector('[data-open-concept]').onclick=()=>selectNode(n.id);
}
function openKGEdge(id){
 const e=kg.edges.find(x=>x.id===id);if(!e)return;selectNode(e.target);K('kg-relation').value=e.relation;K('kg-stratum').value=e.stratum||'ANY';K('kg-significant').checked=e.q!=null&&e.q<.05;renderEdges();showEdge(id,true);
}
async function renderGlobal(){
 const req=++visualRequest;if(!kg)return;
 try{
  const hasAdjusted=kg.edges.some(e=>e.relation==='adjusted_association'&&e.stratum===K('kg-global-pop').value);K('kg-global-policy').querySelector('[value=adjusted]').disabled=!hasAdjusted;if(!hasAdjusted&&K('kg-global-policy').value==='adjusted')K('kg-global-policy').value='best';
  const query=new URLSearchParams({stratum:K('kg-global-pop').value,policy:K('kg-global-policy').value,all_features:String(K('kg-all-nodes').checked)});
  const r=await fetch('/api/knowledge/visual?'+query);if(!r.ok)throw Error('Evidence unavailable');const data=await r.json();if(req!==visualRequest)return;if(!data.ready)throw Error(data.reason);const net=data.network;
  globalController=LCGraph.render(K('kg-global-network'),net.nodes,net.edges,{label,onNode:n=>inspectNode(n),onEdge:e=>openKGEdge(e.id)});
  K('kg-global-note').textContent='';K('kg-global-note').classList.add('hidden');K('kg-visual-detail').innerHTML='';
 }catch(e){if(req===visualRequest){K('kg-global-note').classList.remove('hidden');K('kg-global-note').textContent=choose('关联图暂不可用，请重试。','Network unavailable. Please retry.');}}
}
function interactivePriorities(alpha){
 const nodes=kg.nodes.filter(n=>n.kind==='feature'&&n.priority?.association_weight!=null&&n.priority?.recurrence_weight!=null),totals={};
 for(const n of nodes)totals[n.modality]=(totals[n.modality]||0)+alpha*n.priority.association_weight+(1-alpha)*n.priority.recurrence_weight;
 return nodes.map(n=>({node:n,weight:totals[n.modality]?(alpha*n.priority.association_weight+(1-alpha)*n.priority.recurrence_weight)/totals[n.modality]:0}));
}
function renderWeightMap(){
 if(!kg)return;const alpha=Number(K('kg-alpha').value)/100,items=interactivePriorities(alpha),svg=K('kg-weight-map');
 K('kg-alpha-value').textContent=`${Math.round(alpha*100)}% / ${Math.round((1-alpha)*100)}%`;
 svg.setAttribute('role','img');svg.setAttribute('aria-label',choose('关联与复发双维度权重','Association and recurrence priority comparison'));
 const xmax=Math.max(.3,...items.map(x=>x.node.priority.association_weight))*1.18,ymax=Math.max(.3,...items.map(x=>x.node.priority.recurrence_weight))*1.15,xx=v=>110+780*v/xmax,yy=v=>455-365*v/ymax;let s='<rect width="1000" height="550" fill="#fcfdfd"/>';
 for(let i=0;i<=4;i++){const x=xx(xmax*i/4),y=yy(ymax*i/4);s+=`<path d="M${x} 90V455 M110 ${y}H890" stroke="#e5ecef" fill="none"/><text x="${x}" y="480" text-anchor="middle" font-size="15" fill="#70818c">${pct(xmax*i/4)}</text><text x="92" y="${y+4}" text-anchor="end" font-size="15" fill="#70818c">${pct(ymax*i/4)}</text>`;}
 s+=`<text x="500" y="520" text-anchor="middle" font-size="17" fill="#365a6d">${choose('关联权重','Association weight')}</text><text x="30" y="275" transform="rotate(-90 30 275)" text-anchor="middle" font-size="17" fill="#365a6d">${choose('复发权重','Recurrence weight')}</text>`;
 for(const {node:n,weight:w}of items){const p=n.priority;s+=`<g data-priority-node="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(label(n))}" cursor="pointer"><circle cx="${xx(p.association_weight)}" cy="${yy(p.recurrence_weight)}" r="${5+15*Math.sqrt(Math.max(0,w))}" fill="${COLORS[n.modality]}" fill-opacity=".8" stroke="#fff"/><title>${esc(label(n))} · ${pct(w)}</title></g>`;}
 Object.entries(COLORS).forEach(([m,c],i)=>{s+=`<circle cx="${200+i*180}" cy="35" r="5" fill="${c}"/><text x="${212+i*180}" y="40" font-size="15" fill="#3e5666">${m.replace('_','-')}</text>`;});svg.innerHTML=s;
 svg.querySelectorAll('[data-priority-node]').forEach(el=>{const n=nmap().get(el.dataset.priorityNode);el.onpointerenter=el.onfocus=()=>{K('kg-weight-info').textContent=label(n)+' · '+choose('关联','Association')+' '+pct(n.priority.association_weight)+' / '+choose('复发','Recurrence')+' '+pct(n.priority.recurrence_weight);};el.onclick=()=>selectNode(n.id);el.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();selectNode(n.id);}};});
}


function renderMatrix(){
 if(!kg)return;
 const mod=K('kg-matrix-mod').value,pop=K('kg-matrix-pop').value,selector=K('kg-matrix-measure');
 const data=LCEvidenceMatrix.select(kg,{population:pop,modality:mod,measure:selector.value});
 const names={partial_rank_rho:choose('调整 ρ','Adjusted ρ'),spearman_rho:choose('原始 ρ','Raw ρ'),bias_corrected_cramers_v:'Cramér V',epsilon_squared:'ε²'};
 for(const option of selector.options){option.disabled=!data.counts[option.value];option.textContent=names[option.value];}
 selector.value=data.measure;selector.disabled=!data.edges.length;
 const edges=data.edges,measure=data.measure,signed=measure.includes('rho'),map=nmap(),svg=K('kg-evidence-matrix');
 const paths=[...new Set(edges.map(e=>e.target))].sort(),images=[...new Set(edges.map(e=>e.source))].sort();
 const cw=72,ch=42,left=lang==='zh'?220:250,top=lang==='zh'?125:175,width=edges.length?Math.max(520,left+images.length*cw+80):760,height=Math.max(270,top+paths.length*ch+30);
 svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.style.width=width+'px';svg.style.height=height+'px';
 svg.setAttribute('role','img');svg.setAttribute('aria-label',`${pop} · ${mod} · ${names[measure]}`);
 let html=`<defs><pattern id="no-estimate" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#f1f4f5"/><path d="M0 6L6 0" stroke="#e0e6e9" stroke-width=".7"/></pattern></defs><rect width="${width}" height="${height}" fill="#fff"/>`;
 const matrix=new Map(edges.map(e=>[e.source+'|'+e.target,e]));
 images.forEach((id,j)=>html+=`<text x="${left+j*cw+cw/2}" y="${top-12}" transform="rotate(-45 ${left+j*cw+cw/2} ${top-12})" font-family="Arial,Microsoft YaHei" font-size="15" fill="#425d6f"><title>${esc(label(map.get(id)))}</title>${esc(short(label(map.get(id)),lang==='zh'?18:28))}</text>`);
 paths.forEach((id,i)=>{html+=`<text x="${left-12}" y="${top+i*ch+25}" text-anchor="end" font-family="Arial,Microsoft YaHei" font-size="15" fill="#425d6f"><title>${esc(label(map.get(id)))}</title>${esc(short(label(map.get(id)),lang==='zh'?18:28))}</text>`;images.forEach((im,j)=>{
  const e=matrix.get(im+'|'+id),x=left+j*cw,y=top+i*ch,value=e?Math.min(1,Math.abs(e.effect)):0,color=e?(signed&&e.effect<0?'#b87860':'#397f97'):'url(#no-estimate)';
  const title=e?`${label(map.get(im))} ↔ ${label(map.get(id))}: ${e.effect.toFixed(3)}; n=${e.n}; q=${qval(e.q)}`:choose('未估计','Not estimated');
  html+=`<g ${e?'data-matrix-edge="'+esc(e.id)+'" role="button" tabindex="0" aria-label="'+esc(title)+'" cursor="pointer"':''}><title>${esc(title)}</title><rect x="${x+1}" y="${y+1}" width="${cw-2}" height="${ch-2}" rx="4" fill="${color}" fill-opacity="${e?.q<.05?.15+.85*value:e?.18:1}"/><text x="${x+cw/2}" y="${y+25}" text-anchor="middle" font-family="Arial" font-size="14" fill="${e?.q<.05&&value>.65?'#fff':'#425d6f'}">${e?e.effect.toFixed(2):'—'}</text></g>`;
 });});
 if(!edges.length){
  const counts=Object.entries(data.modalities).filter(([,n])=>n>0);
  html+=`<circle cx="70" cy="96" r="24" fill="#edf3f5"/><text x="70" y="103" text-anchor="middle" font-size="24" fill="#678290">—</text><text x="114" y="96" font-family="Arial,Microsoft YaHei" font-size="18" fill="#315469">${choose('当前组合尚无关联估计','No association estimates for this selection')}</text><text x="114" y="128" font-family="Arial,Microsoft YaHei" font-size="14" fill="#617a88">${esc(pop)} · ${choose('患者','Patients')} ${num(data.populationN,0)}${data.reportN!=null?' · '+mod.replace('_','-')+' '+num(data.reportN,0):''}</text><text x="114" y="164" font-family="Arial,Microsoft YaHei" font-size="14" fill="#617a88">${(['ALL','LUAD','LUSC','SCLC'].includes(pop)?choose('未达到配对数或类别数量要求。','Pair or category support requirements were not met.'):choose('当前分层关联未覆盖此组；可在详情中查阅队列信息。','This group is outside the current stratified association analysis. Cohort details remain available.'))}</text>`;
  if(counts.length)html+=`<text x="114" y="204" font-family="Arial,Microsoft YaHei" font-size="14" fill="#397f97">${choose('可切换模态：','Available modalities: ')}${counts.map(([m,n])=>m.replace('_','-')+' ('+n+')').join(' · ')}</text>`;
 }
 svg.innerHTML=html;
 K('kg-matrix-count').textContent=names[measure];
 K('kg-matrix-summary').innerHTML=[[''+edges.length,choose('可估计关联','Estimates')],[''+data.significant,'q < 0.05'],[data.pairMin===null?'—':num(data.pairMin,0)+'–'+num(data.pairMax,0),choose('成对人数','Paired n')]].map(([v,l])=>`<div><strong>${v}</strong><span>${l}</span></div>`).join('');
 K('kg-matrix-note').innerHTML=edges.length?`<span>${signed?'−1':'0'}</span><i class="effect-gradient ${signed?'signed':''}"></i><span>1</span><span class="legend-divider"></span><span class="legend-square faint"></span><span>q ≥ 0.05</span><span class="legend-square missing"></span><span>${choose('未估计','Unestimated')}</span>`:'';
 K('kg-matrix-info').textContent=data.changed?choose('该亚组采用'+names[measure],names[measure]+' for this subgroup') : '';
 svg.querySelectorAll('[data-matrix-edge]').forEach(el=>{el.onclick=()=>{openKGEdge(el.dataset.matrixEdge);};const inspect=()=>{const e=kg.edges.find(e=>e.id===el.dataset.matrixEdge);K('kg-matrix-info').textContent=label(map.get(e.source))+' ↔ '+label(map.get(e.target))+' · '+e.effect.toFixed(3)+' · n='+num(e.n,0)+' · q='+qval(e.q);};el.onpointerenter=el.onfocus=inspect;el.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();el.onclick();}};});
}

for(const id of ['kg-global-pop','kg-global-policy','kg-all-nodes'])K(id).onchange=renderGlobal;
for(const id of ['kg-matrix-mod','kg-matrix-pop','kg-matrix-measure'])K(id).onchange=renderMatrix;
document.querySelectorAll('[data-priority-mode]').forEach(b=>b.onclick=()=>{priorityMode=b.dataset.priorityMode;renderPriorityRanking();});
K('kg-alpha').oninput=renderWeightMap;K('kg-zoom-in').onclick=()=>globalController?.zoomIn();K('kg-zoom-out').onclick=()=>globalController?.zoomOut();K('kg-reset').onclick=()=>globalController?.reset();K('kg-svg').onclick=()=>LCGraph.downloadSVG(K('kg-global-network'),'report_evidence_graph');
window.addEventListener('knowledge-ready',visualLocalize);window.addEventListener('knowledge-language',visualLocalize);if(kg)visualLocalize();else setKGView(kgView);
