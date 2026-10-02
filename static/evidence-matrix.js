'use strict';
// Select only estimates actually present for the requested population/modality.
// Falling back across measures is labelled; populations are never substituted.
const LCEvidenceMatrix=(()=>{
 const measures=['partial_rank_rho','spearman_rho','bias_corrected_cramers_v','epsilon_squared'];
 function select(graph,{population='ALL',modality='CE',measure='partial_rank_rho'}={}){
  const available=graph.edges.filter(e=>e.stratum===population&&e.modality===modality&&['associated_with','adjusted_association'].includes(e.relation)&&Number.isFinite(e.effect));
  const counts=Object.fromEntries(measures.map(m=>[m,available.filter(e=>e.measure===m).length]));
  const chosen=counts[measure]?measure:measures.find(m=>counts[m])||measure;
  const edges=available.filter(e=>e.measure===chosen);
  const populationNode=graph.nodes.find(n=>n.kind==='histology'&&n.label_en===population);
  return {population,modality,requestedMeasure:measure,measure:chosen,changed:measure!==chosen,counts,edges,
   significant:edges.filter(e=>Number.isFinite(e.q)&&e.q<.05).length,
   pairMin:edges.length?Math.min(...edges.map(e=>e.n)):null,pairMax:edges.length?Math.max(...edges.map(e=>e.n)):null,
   populationN:population==='ALL'?graph.summary.report_cohort_n:populationNode?.population?.n,
   reportN:populationNode?.population?.[modality+'_reports'],
   modalities:Object.fromEntries(['CE','NCE','PET_CT'].map(m=>[m,graph.edges.filter(e=>e.stratum===population&&e.modality===m&&['associated_with','adjusted_association'].includes(e.relation)).length]))};
 }
 return {select,measures};
})();
if(typeof module!=='undefined')module.exports=LCEvidenceMatrix;
