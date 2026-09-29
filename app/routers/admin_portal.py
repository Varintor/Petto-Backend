"""Minimal same-origin administration portal for staging operations.

The portal never embeds the administrator credential. Operators provide the
existing ADMIN_API_KEY for the current browser tab and every mutation still
passes through the validated administration API.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["Administration Portal"])


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_portal() -> HTMLResponse:
    return HTMLResponse(
        content=_ADMIN_PORTAL_HTML,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'self'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; connect-src 'self'; "
                "img-src 'self' data:; frame-ancestors 'none'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        },
    )


_ADMIN_PORTAL_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Petto Admin Portal</title>
  <style>
    :root{--ink:#4c2326;--muted:#8c7470;--wine:#8e3137;--cream:#fffaf6;--line:#eaded7;--ok:#2d7a4b;--warn:#a86a12;--bad:#b13b42;--card:#fff}
    *{box-sizing:border-box} body{margin:0;background:linear-gradient(145deg,#fffaf6,#f8efea);color:var(--ink);font:15px/1.45 Inter,system-ui,sans-serif;min-height:100vh}
    button,input,select,textarea{font:inherit} button{cursor:pointer}.hidden{display:none!important}
    .gate{max-width:440px;margin:11vh auto;padding:32px;background:#fff;border:1px solid var(--line);border-radius:24px;box-shadow:0 20px 60px #5b262315}
    .brand{display:flex;gap:12px;align-items:center}.logo{width:42px;height:42px;border-radius:14px;background:var(--wine);display:grid;place-items:center;color:#fff;font-size:22px}.brand h1{font-size:23px;margin:0}.brand p{margin:2px 0;color:var(--muted)}
    label{display:block;font-size:12px;font-weight:700;margin:14px 0 6px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
    input,select,textarea{width:100%;border:1px solid var(--line);border-radius:11px;padding:11px 12px;background:#fff;color:var(--ink)} input:focus,select:focus,textarea:focus{outline:2px solid #d99aa0;border-color:var(--wine)}
    .primary{border:0;border-radius:11px;padding:11px 16px;background:var(--wine);color:#fff;font-weight:750}.secondary{border:1px solid var(--line);border-radius:10px;padding:8px 12px;background:#fff;color:var(--ink);font-weight:650}.danger{color:var(--bad)}
    .gate .primary{width:100%;margin-top:18px}.hint{font-size:12px;color:var(--muted);margin-top:12px}
    header{position:sticky;top:0;z-index:4;background:#fffdfacc;border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}.top{max-width:1240px;margin:auto;padding:14px 22px;display:flex;align-items:center;justify-content:space-between}.top-actions{display:flex;gap:8px}
    main{max-width:1240px;margin:24px auto;padding:0 22px 48px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.metric,.panel{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 30px #5b26230b}.metric{padding:17px}.metric strong{display:block;font-size:28px}.metric span{color:var(--muted);font-size:13px}
    .tabs{display:flex;gap:8px;margin:22px 0}.tab{border:1px solid var(--line);background:#fff;padding:10px 16px;border-radius:999px;color:var(--muted);font-weight:750}.tab.active{background:var(--ink);color:#fff;border-color:var(--ink)}
    .layout{display:grid;grid-template-columns:360px 1fr;gap:18px}.panel{padding:19px}.panel h2{margin:0 0 4px;font-size:18px}.panel-sub{margin:0 0 15px;color:var(--muted);font-size:13px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}.check{display:flex;gap:9px;align-items:center;margin-top:14px;color:var(--ink)}.check input{width:auto}.form-actions{display:flex;gap:8px;margin-top:18px}.form-actions .primary{flex:1}
    .toolbar{display:flex;gap:10px;justify-content:space-between;align-items:center;margin-bottom:13px}.toolbar input{max-width:300px}.list{display:grid;gap:10px}.item{border:1px solid var(--line);border-radius:14px;padding:14px}.item-head{display:flex;justify-content:space-between;gap:12px}.item h3{margin:0;font-size:16px}.meta{color:var(--muted);font-size:13px;margin-top:4px}.badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.badge{font-size:11px;padding:4px 8px;border-radius:999px;background:#f1e8e3;color:var(--ink);font-weight:750}.badge.ok{background:#e5f5ea;color:var(--ok)}.badge.warn{background:#fff0d8;color:var(--warn)}.badge.bad{background:#fde7e8;color:var(--bad)}.actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.actions button{font-size:12px}.assign{display:grid;grid-template-columns:1fr auto auto;gap:8px;margin-top:10px;align-items:center}.assign .check{margin:0;text-transform:none;letter-spacing:0}.empty{padding:35px;text-align:center;color:var(--muted)}
    #toast{position:fixed;right:18px;bottom:18px;max-width:380px;padding:13px 16px;border-radius:12px;background:var(--ink);color:#fff;box-shadow:0 10px 35px #0003;z-index:10}.loading{opacity:.55;pointer-events:none}
    @media(max-width:850px){.metrics{grid-template-columns:1fr 1fr}.layout{grid-template-columns:1fr}.top .brand p{display:none}.assign{grid-template-columns:1fr}.toolbar{align-items:stretch;flex-direction:column}.toolbar input{max-width:none}}
  </style>
</head>
<body>
  <section id="gate" class="gate">
    <div class="brand"><div class="logo">P</div><div><h1>Petto Admin Portal</h1><p>Staging operations console</p></div></div>
    <label for="adminKey">Admin API key</label><input id="adminKey" type="password" autocomplete="off" placeholder="Enter the Railway ADMIN_API_KEY">
    <button class="primary" id="unlock">Open portal</button>
    <p class="hint">The key is kept only in this browser tab and is never embedded in the page.</p>
  </section>

  <div id="app" class="hidden">
    <header><div class="top"><div class="brand"><div class="logo">P</div><div><h1>Petto Admin</h1><p>Hospitals & veterinarians</p></div></div><div class="top-actions"><button class="secondary" id="refresh">Refresh</button><button class="secondary danger" id="lock">Lock</button></div></div></header>
    <main>
      <section class="metrics"><div class="metric"><strong id="mProviders">0</strong><span>Providers</span></div><div class="metric"><strong id="mPartner">0</strong><span>Petto partners</span></div><div class="metric"><strong id="mVets">0</strong><span>Veterinarians</span></div><div class="metric"><strong id="mPending">0</strong><span>Pending approval</span></div></section>
      <nav class="tabs"><button class="tab active" data-view="providers">Hospitals</button><button class="tab" data-view="vets">Veterinarians</button></nav>

      <section id="providersView" class="layout">
        <form id="providerForm" class="panel"><h2 id="providerFormTitle">Add hospital or clinic</h2><p class="panel-sub">Create information-only listings or Petto consultation partners.</p>
          <input id="providerId" type="hidden"><label>Name *</label><input id="providerName" required maxlength="200">
          <div class="grid2"><div><label>Type</label><select id="providerType"><option value="hospital">Hospital</option><option value="clinic">Clinic</option><option value="independent">Independent</option></select></div><div><label>Status</label><select id="providerStatus"><option value="listed">Information only</option><option value="partner">Petto partner</option><option value="disabled">Disabled</option></select></div></div>
          <label>Address</label><textarea id="providerAddress" rows="2"></textarea><label>Phone</label><input id="providerPhone" maxlength="50">
          <div class="grid2"><div><label>Latitude</label><input id="providerLat" type="number" step="any" min="-90" max="90"></div><div><label>Longitude</label><input id="providerLng" type="number" step="any" min="-180" max="180"></div></div>
          <label class="check"><input id="providerConsult" type="checkbox"> Enable Petto consultations</label>
          <div class="form-actions"><button type="button" class="secondary hidden" id="cancelProvider">Cancel</button><button class="primary" type="submit">Save provider</button></div>
        </form>
        <section class="panel"><div class="toolbar"><div><h2>Provider directory</h2><p class="panel-sub">Partner and information-only locations.</p></div><input id="providerSearch" type="search" placeholder="Search providers"></div><div id="providerList" class="list"></div></section>
      </section>

      <section id="vetsView" class="layout hidden">
        <form id="vetForm" class="panel"><h2 id="vetFormTitle">Add veterinarian</h2><p class="panel-sub">Create the profile first, then approve and invite the account.</p>
          <input id="vetId" type="hidden"><label>Email *</label><input id="vetEmail" type="email" required maxlength="320"><label>Name *</label><input id="vetName" required maxlength="200">
          <label>Specialty</label><input id="vetSpecialty" maxlength="200"><label>Professional license</label><input id="vetLicense" maxlength="100"><label>Clinic display name</label><input id="vetClinic" maxlength="200">
          <div class="form-actions"><button type="button" class="secondary hidden" id="cancelVet">Cancel</button><button class="primary" type="submit">Save veterinarian</button></div>
        </form>
        <section class="panel"><div class="toolbar"><div><h2>Veterinarian directory</h2><p class="panel-sub">Approval, account invitation and hospital assignment.</p></div><input id="vetSearch" type="search" placeholder="Search veterinarians"></div><div id="vetList" class="list"></div></section>
      </section>
    </main>
  </div>
  <div id="toast" class="hidden"></div>
<script>
let adminKey='', providers=[], vets=[];
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const optional=value=>{const v=String(value??'').trim();return v?v:null};
function toast(message,error=false){const el=$('toast');el.textContent=message;el.style.background=error?'#b13b42':'#4c2326';el.classList.remove('hidden');clearTimeout(el._t);el._t=setTimeout(()=>el.classList.add('hidden'),4200)}
async function api(path,options={}){const response=await fetch('/api/v1/admin'+path,{...options,headers:{'Content-Type':'application/json','X-Admin-Key':adminKey,...(options.headers||{})}});if(!response.ok){let message='Request failed';try{const body=await response.json();message=typeof body.detail==='string'?body.detail:message}catch(_){}if(response.status===401) lock();throw new Error(message)}return response.status===204?null:response.json()}
function lock(){adminKey='';sessionStorage.removeItem('pettoAdminKey');$('app').classList.add('hidden');$('gate').classList.remove('hidden');$('adminKey').value=''}
async function loadAll(){document.body.classList.add('loading');try{[providers,vets]=await Promise.all([api('/providers'),api('/veterinarians')]);render();$('gate').classList.add('hidden');$('app').classList.remove('hidden')}catch(e){toast(e.message,true)}finally{document.body.classList.remove('loading')}}
function render(){ $('mProviders').textContent=providers.length;$('mPartner').textContent=providers.filter(p=>p.provider_status==='partner').length;$('mVets').textContent=vets.length;$('mPending').textContent=vets.filter(v=>v.verification_status==='pending').length;renderProviders();renderVets() }
function providerBadge(p){return p.provider_status==='partner'?'ok':p.provider_status==='disabled'?'bad':'warn'}
function renderProviders(){const q=$('providerSearch').value.toLowerCase();const rows=providers.filter(p=>(p.name+' '+(p.address||'')).toLowerCase().includes(q));$('providerList').innerHTML=rows.length?rows.map(p=>`<article class="item"><div class="item-head"><div><h3>${esc(p.name)}</h3><div class="meta">${esc(p.address||'No address')} · ${esc(p.phone||'No phone')}</div></div><button class="secondary" onclick="editProvider(${p.id})">Edit</button></div><div class="badges"><span class="badge ${providerBadge(p)}">${esc(p.provider_status)}</span><span class="badge">${esc(p.provider_type)}</span><span class="badge ${p.consultation_enabled?'ok':'warn'}">${p.consultation_enabled?'Consultation enabled':'Information only'}</span><span class="badge">${p.veterinarian_ids.length} vets</span></div>${p.latitude!=null?`<div class="meta">Location: ${esc(p.latitude)}, ${esc(p.longitude)}</div>`:''}</article>`).join(''):'<div class="empty">No providers found</div>'}
function renderVets(){const q=$('vetSearch').value.toLowerCase();const rows=vets.filter(v=>(v.name+' '+v.email+' '+(v.specialty||'')).toLowerCase().includes(q));const options=providers.filter(p=>p.provider_status!=='disabled').map(p=>`<option value="${p.id}">${esc(p.name)}${p.consultation_enabled?' · partner':' · info only'}</option>`).join('');$('vetList').innerHTML=rows.length?rows.map(v=>`<article class="item"><div class="item-head"><div><h3>${esc(v.name)}</h3><div class="meta">${esc(v.email)} · ${esc(v.specialty||'No specialty')}</div></div><button class="secondary" onclick="editVet(${v.id})">Edit</button></div><div class="badges"><span class="badge ${v.verification_status==='approved'?'ok':v.verification_status==='pending'?'warn':'bad'}">${esc(v.verification_status)}</span><span class="badge ${v.supabase_uid?'ok':'warn'}">${v.supabase_uid?'Account ready':'No Auth account'}</span><span class="badge ${v.is_online?'ok':'warn'}">${v.is_online?'Online':'Offline'}</span><span class="badge ${v.is_accepting_consultations?'ok':'warn'}">${v.is_accepting_consultations?'Accepting':'Not accepting'}</span></div><div class="actions">${v.verification_status!=='approved'?`<button class="secondary" onclick="verifyVet(${v.id},'approved')">Approve</button>`:''}${!v.supabase_uid?`<button class="secondary" onclick="inviteVet(${v.id})">Create account / Invite</button>`:''}<button class="secondary" onclick="toggleOnline(${v.id},${!v.is_online})">Set ${v.is_online?'offline':'online'}</button></div><div class="assign"><select id="assignProvider${v.id}"><option value="">Assign hospital…</option>${options}</select><label class="check"><input id="assignAccept${v.id}" type="checkbox"> Accept consults</label><button class="secondary" onclick="assignProvider(${v.id})">Assign</button></div><div class="meta">Assigned provider IDs: ${esc(v.provider_ids.join(', ')||'None')}</div></article>`).join(''):'<div class="empty">No veterinarians found</div>'}
function resetProvider(){ $('providerForm').reset();$('providerId').value='';$('providerFormTitle').textContent='Add hospital or clinic';$('cancelProvider').classList.add('hidden') }
function editProvider(id){const p=providers.find(x=>x.id===id);if(!p)return;$('providerId').value=p.id;$('providerName').value=p.name;$('providerType').value=p.provider_type;$('providerStatus').value=p.provider_status;$('providerAddress').value=p.address||'';$('providerPhone').value=p.phone||'';$('providerLat').value=p.latitude??'';$('providerLng').value=p.longitude??'';$('providerConsult').checked=p.consultation_enabled;$('providerFormTitle').textContent='Edit provider';$('cancelProvider').classList.remove('hidden');scrollTo({top:0,behavior:'smooth'})}
function resetVet(){ $('vetForm').reset();$('vetId').value='';$('vetEmail').disabled=false;$('vetFormTitle').textContent='Add veterinarian';$('cancelVet').classList.add('hidden') }
function editVet(id){const v=vets.find(x=>x.id===id);if(!v)return;$('vetId').value=v.id;$('vetEmail').value=v.email;$('vetEmail').disabled=true;$('vetName').value=v.name;$('vetSpecialty').value=v.specialty||'';$('vetLicense').value=v.license_number||'';$('vetClinic').value=v.clinic_name||'';$('vetFormTitle').textContent='Edit veterinarian';$('cancelVet').classList.remove('hidden');scrollTo({top:0,behavior:'smooth'})}
async function mutate(work,success){document.body.classList.add('loading');try{await work();toast(success);await loadAll();return true}catch(e){toast(e.message,true);return false}finally{document.body.classList.remove('loading')}}
$('unlock').onclick=()=>{adminKey=$('adminKey').value.trim();if(!adminKey)return toast('Enter the Admin API key',true);sessionStorage.setItem('pettoAdminKey',adminKey);loadAll()};$('adminKey').onkeydown=e=>{if(e.key==='Enter')$('unlock').click()};$('lock').onclick=lock;$('refresh').onclick=loadAll;
document.querySelectorAll('.tab').forEach(tab=>tab.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===tab));$('providersView').classList.toggle('hidden',tab.dataset.view!=='providers');$('vetsView').classList.toggle('hidden',tab.dataset.view!=='vets')});
$('providerSearch').oninput=renderProviders;$('vetSearch').oninput=renderVets;$('cancelProvider').onclick=resetProvider;$('cancelVet').onclick=resetVet;
$('providerForm').onsubmit=e=>{e.preventDefault();const id=$('providerId').value;const payload={name:$('providerName').value.trim(),provider_type:$('providerType').value,address:optional($('providerAddress').value),phone:optional($('providerPhone').value),latitude:optional($('providerLat').value)==null?null:Number($('providerLat').value),longitude:optional($('providerLng').value)==null?null:Number($('providerLng').value),provider_status:$('providerStatus').value,consultation_enabled:$('providerConsult').checked};mutate(()=>api(id?`/providers/${id}`:'/providers',{method:id?'PATCH':'POST',body:JSON.stringify(payload)}),id?'Provider updated':'Provider created').then(ok=>{if(ok)resetProvider()})};
$('vetForm').onsubmit=e=>{e.preventDefault();const id=$('vetId').value;const payload={name:$('vetName').value.trim(),specialty:optional($('vetSpecialty').value),license_number:optional($('vetLicense').value),clinic_name:optional($('vetClinic').value)};if(!id)payload.email=$('vetEmail').value.trim();mutate(()=>api(id?`/veterinarians/${id}`:'/veterinarians',{method:id?'PATCH':'POST',body:JSON.stringify(payload)}),id?'Veterinarian updated':'Veterinarian created').then(ok=>{if(ok)resetVet()})};
function verifyVet(id,status){mutate(()=>api(`/veterinarians/${id}/verification`,{method:'POST',body:JSON.stringify({verification_status:status})}),'Veterinarian approved')}
function inviteVet(id){if(!confirm('Send an account invitation to this veterinarian email?'))return;mutate(()=>api(`/veterinarians/${id}/invite`,{method:'POST'}),'Invitation sent and account linked')}
function toggleOnline(id,value){mutate(()=>api(`/veterinarians/${id}`,{method:'PATCH',body:JSON.stringify({is_online:value})}),value?'Veterinarian is online':'Veterinarian is offline')}
function assignProvider(id){const providerId=Number($(`assignProvider${id}`).value);if(!providerId)return toast('Choose a hospital first',true);const p=providers.find(x=>x.id===providerId);const accepting=$(`assignAccept${id}`).checked;if(accepting&&!p.consultation_enabled)return toast('Information-only providers cannot accept consultations',true);mutate(()=>api(`/veterinarians/${id}/providers/${providerId}`,{method:'PUT',body:JSON.stringify({is_active:true,accepting_consultations:accepting})}),'Hospital assigned')}
adminKey=sessionStorage.getItem('pettoAdminKey')||'';if(adminKey){$('adminKey').value=adminKey;loadAll()}
</script>
</body></html>'''
