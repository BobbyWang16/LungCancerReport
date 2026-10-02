'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {select,fields}=require('../static/priority-selection.js');
const graph=JSON.parse(fs.readFileSync(path.join(__dirname,'../resources/evidence_graph.json'),'utf8'));
const before=JSON.stringify(graph);
for(const mode of Object.keys(fields)){
 for(const group of select(graph,mode)){
  const eligible=graph.nodes.filter(n=>n.kind==='feature'&&n.modality===group.modality&&Number.isFinite(n.priority?.[fields[mode]]));
  assert.deepEqual(new Set(group.items.map(x=>x.node.id)),new Set(eligible.map(n=>n.id)));
  group.items.forEach((x,i)=>{assert.equal(x.weight,x.node.priority[fields[mode]]);if(i)assert(group.items[i-1].weight>=x.weight);});
 }
}
const joint=new Set(select(graph,'joint').flatMap(g=>g.items.map(x=>x.node.id)));
const single=select(graph,'association').flatMap(g=>g.items).find(x=>!joint.has(x.node.id));
assert(single,'Single-dimension fields must remain discoverable');
assert.equal(JSON.stringify(graph),before,'Browsing must never modify fitted evidence');
const sparse={nodes:[{id:'PATH.none',kind:'feature',modality:'PATH',priority:{joint_weight:null}},{id:'PATH.zero',kind:'feature',modality:'PATH',priority:{joint_weight:0}}]};
assert.deepEqual(select(sparse)[0].items.map(x=>x.node.id),['PATH.zero']);
console.log(JSON.stringify({passed:true,checks:['all estimable fields accessible','frozen weights preserved','within-report rankings','single-domain fields retained','unestimated differs from zero','evidence unchanged']}));
