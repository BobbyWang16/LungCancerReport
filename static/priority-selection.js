'use strict';
(function(root){
 const fields={joint:'joint_weight',association:'association_weight',recurrence:'recurrence_weight'};
 function select(graph,mode='joint'){
  const field=fields[mode]||fields.joint;
  return ['PATH','CE','NCE','PET_CT'].map(modality=>({modality,items:(graph.nodes||[])
   .filter(n=>n.kind==='feature'&&n.modality===modality&&Number.isFinite(n.priority?.[field]))
   .map(node=>({node,weight:node.priority[field]}))
   .sort((a,b)=>b.weight-a.weight||a.node.id.localeCompare(b.node.id))}));
 }
 const api={select,fields};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LCPriorities=api;
})(typeof window!=='undefined'?window:globalThis);
