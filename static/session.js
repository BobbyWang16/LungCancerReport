'use strict';
const originalFetch=window.fetch.bind(window);
window.fetch=async(...args)=>{const response=await originalFetch(...args);if(response.status===401){window.location.replace('/login');throw new Error('Session expired');}return response;};
let sessionToken='';
async function initializeSession(){const r=await fetch('/api/status');if(!r.ok)return;const s=await r.json();sessionToken=s.token;const button=document.getElementById('logout-button');if(button)button.hidden=!s.invitation_test;}
function sessionLanguage(){try{return localStorage.getItem('lc-report-language')==='en'?'en':'zh';}catch{return 'zh';}}
function localizeSession(){const b=document.getElementById('logout-button');if(b)b.textContent=sessionLanguage()==='en'?'Sign out':'退出';}
document.getElementById('logout-button')?.addEventListener('click',async()=>{const b=document.getElementById('logout-button');b.disabled=true;try{await initializeSession();const r=await fetch('/auth/logout',{method:'POST',headers:{'Content-Type':'application/json','X-MVP-Token':sessionToken},body:'{}',credentials:'same-origin'});if(!r.ok){const d=await r.json();throw new Error(d.error||'Sign-out failed');}window.location.replace('/login');}catch(e){if(typeof toast==='function')toast(e.message,true);else b.textContent=sessionLanguage()==='en'?'Retry sign out':'重试退出';}finally{b.disabled=false;}});
new MutationObserver(localizeSession).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
localizeSession();initializeSession().catch(()=>{});
