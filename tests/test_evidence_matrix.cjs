'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {select,measures}=require('../static/evidence-matrix.js');
const graph=JSON.parse(fs.readFileSync(path.join(__dirname,'../resources/evidence_graph.json'),'utf8'));
const strata=['ALL',...graph.nodes.filter(n=>n.kind==='histology').map(n=>n.label_en)];
let cases=0;
for(const population of strata)for(const modality of ['CE','NCE','PET_CT'])for(const measure of measures){
 const result=select(graph,{population,modality,measure});
 const actual=graph.edges.filter(e=>e.stratum===population&&e.modality===modality&&['associated_with','adjusted_association'].includes(e.relation)&&e.measure===result.measure);
 assert.deepEqual(result.edges.map(e=>e.id),actual.map(e=>e.id));
 assert(result.edges.every(e=>e.stratum===population));
 assert.equal(result.significant,result.edges.filter(e=>e.q!=null&&e.q<.05).length);
 if(result.counts[measure])assert.equal(result.measure,measure);
 else if(Object.values(result.counts).some(Boolean))assert(result.edges.length>0);
 cases++;
}
for(const population of ['LUAD','LUSC','SCLC']){
 const r=select(graph,{population,modality:'CE',measure:'partial_rank_rho'});
 assert.equal(r.measure,'spearman_rho');assert(r.changed&&r.edges.length>0);
 assert.equal(r.counts.partial_rank_rho,0);
}
const sparse=select(graph,{population:'HEME',modality:'CE'});
assert.equal(sparse.populationN,11);assert.equal(sparse.edges.length,0);
assert.equal(select(graph,{population:'ALL'}).changed,false);
console.log(JSON.stringify({passed:true,combinations:cases,checks:['preserve stratum','use existing measures','retain numeric results','disable unavailable measures','sparse groups remain unestimated']}));
