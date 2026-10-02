'use strict';
// Pure rendering contract tests; no browser, server, patient or external API.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',style:{},className:'',hidden:false,classList:{toggle(k,v){if(k==='hidden')element(id).hidden=v;}},querySelectorAll(){return [];}});return elements.get(id);}
const context=vm.createContext({console,localStorage:{getItem(){return 'zh';}},$:element,state:{current:null,model:{format:'report_recurrence_multihorizon_v3',ready:true,sites_enabled:true}},specFor(){return null;},escapeHTML:s=>String(s??''),percent:v=>typeof v==='number'?(100*v).toFixed(1)+'%':'—',valueLabel:f=>String(f.value)});
vm.runInContext(fs.readFileSync(path.join(root,'static/i18n.js'),'utf8'),context);
const source=fs.readFileSync(path.join(root,'static/app.js'),'utf8');
vm.runInContext(source.slice(source.indexOf('function placeholderSites()'),source.indexOf('function renderResult()')),context);
const run=()=>vm.runInContext('renderRisk()',context);
context.state.current={risk:{status:'available',risks_by_year:{1:{status:'available',probability:.12},3:{status:'available',probability:.24},5:{status:'validation_insufficient',probability:.88}},site_status:'exploratory_ranking',top_sites:[{site:'brain'},{site:'bone'},{site:'lung'}]}};
run();assert(element('single-risk').hidden);assert(!element('multihorizon-risk').hidden);
assert(element('multihorizon-risk').innerHTML.includes('12.0%'));assert(element('multihorizon-risk').innerHTML.includes('24.0%'));assert(!element('multihorizon-risk').innerHTML.includes('88.0%'));
assert.equal((element('site-cards').innerHTML.match(/class="site-card"/g)||[]).length,3);assert(!element('site-cards').innerHTML.includes('%'));
context.state.current.risk.site_status='cohort_reference';run();assert(element('sites-heading-title').textContent.includes('队列'));assert(element('site-rank-note').textContent.includes('不是该患者'));
vm.runInContext("lang='en'",context);run();assert(element('sites-heading-title').textContent.includes('cohort'));assert(element('multihorizon-risk').innerHTML.includes('Year 5'));assert(!/[\u4e00-\u9fff]/.test(element('multihorizon-risk').innerHTML));
context.state.current.risk={status:'unavailable',site_status:'not_validated',top_sites:[],reason:'test'};run();assert(!element('site-cards').innerHTML.includes('class="site-card"'));assert(!element('multihorizon-risk').innerHTML.includes('24.0%'));
context.state.current.risk={status:'demo',is_demo:true,horizon_months:36,recurrence_probability:.24,top_sites:[{site:'brain',absolute_probability:.08}]};run();assert(element('single-risk').hidden);assert(!element('multihorizon-risk').innerHTML.includes('%'));assert(!element('site-cards').innerHTML.includes('%'));
vm.runInContext("lang='zh'",context);
context.state.current.report_review={histology:'LUSC',missing_common_fields:['PATH.margin_positive','PATH.nodes_examined'],uncertain_fields:['PATH.nodes_positive'],prompts:[{zh:'一般分组提示',en:'General guidance'},{zh:'阳性数超过检查总数',en:'Positive nodes exceed examined nodes'}],highlights:[],risk_scope:{zh:'范围',en:'Scope'},note:{zh:'来源',en:'Source'}};
vm.runInContext('renderReportReview()',context);let html=element('report-review').innerHTML;
assert(html.includes('3/5'));assert(html.includes('width:60%'));assert(html.indexOf('阳性数超过检查总数')<html.indexOf('<details'));assert(html.indexOf('一般分组提示')>html.indexOf('<details'));
vm.runInContext("lang='en';renderReportReview()",context);html=element('report-review').innerHTML;assert(html.includes('Positive nodes exceed examined nodes'));assert(!/[\u4e00-\u9fff]/.test(html));
console.log(JSON.stringify({passed:true,checks:['1/3/5-year layout','unsupported probability withheld','rank-only sites','cohort reference labelled','unvalidated sites withheld','demo has no legacy probabilities','visible conflict prompts','core coverage meter','bilingual rendering']}));
