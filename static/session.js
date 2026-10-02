'use strict';
const originalFetch=window.fetch.bind(window);
window.fetch=async(...args)=>{const response=await originalFetch(...args);if(response.status===401){window.location.replace('/login');throw new Error('Session expired');}return response;};
let sessionToken='';
async function initializeSession(){const r=await fetch('/api/status');if(!r.ok)return;const s=await r.json();sessionToken=s.token;const button=document.getElementById('logout-button');if(button)button.hidden=!s.invitation_test;}
function sessionLanguage(){try{return localStorage.getItem('lc-report-language')==='en'?'en':'zh';}catch{return 'zh';}}
function localizeSession(){const b=document.getElementById('logout-button');if(b)b.textContent=sessionLanguage()==='en'?'Sign out':'退出';}
document.getElementById('logout-button')?.addEventListener('click',async()=>{try{await fetch('/auth/logout',{method:'POST',headers:{'Content-Type':'application/json','X-MVP-Token':sessionToken},body:'{}',credentials:'same-origin'});}finally{window.location.replace('/login');}});
new MutationObserver(localizeSession).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
localizeSession();initializeSession().catch(()=>{});
