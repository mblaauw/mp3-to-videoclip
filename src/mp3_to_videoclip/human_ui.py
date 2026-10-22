"""Vanilla Studio confirmation UI; capabilities never enter URLs after bootstrap."""

SCRIPT = r"""
const actionStorageKey='studio-action:'+token;
let storageAvailable=true;
function readCapability(){try{return sessionStorage.getItem(actionStorageKey)||'';}catch(e){storageAvailable=false;return '';}}
function saveCapability(value){try{if(value)sessionStorage.setItem(actionStorageKey,value);else sessionStorage.removeItem(actionStorageKey);}catch(e){storageAvailable=false;}}
let actionCapability=readCapability(), humanSession=null;
if(location.hash.startsWith('#action=')){
 const entry=new URLSearchParams(location.hash.slice(1));actionCapability=entry.get('action')||'';
 saveCapability(actionCapability);
 try{history.replaceState(null,'',location.pathname+location.search);}catch(e){actionCapability='';saveCapability('');try{location.replace(location.pathname+location.search);}catch(ignored){location.hash='';}}
}
const humanStatus=el('p','notice');humanStatus.id='humanStatus';humanStatus.setAttribute('role','status');
document.querySelector('header').append(humanStatus);
const quoteTab=el('button','tab','Quotes');quoteTab.id='tab-quotes';quoteTab.dataset.tab='quotes';quoteTab.setAttribute('role','tab');quoteTab.setAttribute('aria-selected','false');quoteTab.setAttribute('aria-controls','view');quoteTab.tabIndex=-1;document.getElementById('tabs').append(quoteTab);
loaders.quotes=loadQuotes;
async function sessionInfo(){
 if(!humanSession)humanSession=await api('/api/session');
 if(!humanSession.actions_enabled){actionCapability='';saveCapability('');}
 return humanSession;
}
async function humanReady(){const s=await sessionInfo();return s.actions_enabled&&!!actionCapability;}
function noHumanActions(node){node.append(el('p','notice','Read-only session. To decide, run uv run clip serve --actions in your own interactive terminal and open its human action link.')) ;}
function check(label){const wrapper=el('label');wrapper.style.textTransform='none';wrapper.style.fontSize='14px';const box=el('input');box.type='checkbox';box.required=true;box.style.width='auto';wrapper.append(box,document.createTextNode(' '+label));return {wrapper,box};}
function noteInput(form){const label=el('label',null,'Your decision and rationale');const area=el('textarea');area.required=true;area.maxLength=2000;area.rows=3;area.style.cssText='width:100%;font:inherit;font-size:16px;line-height:1.5;background:#0e161d;color:var(--ink);border:1px solid var(--line);padding:10px';label.append(area);form.append(label);return area;}
async function decide(path,body){
 const r=await fetch(withToken(path),{method:'POST',headers:{...hdr,'Content-Type':'application/json','X-Studio-Action':actionCapability},body:JSON.stringify(body)});
 const d=await r.json();if(!r.ok){if(r.status===401){actionCapability='';saveCapability('');humanStatus.textContent='Human capability invalid or expired — reopen the current terminal action link.';}const e=new Error(d.error||('HTTP '+r.status));e.status=r.status;throw e;}return d;
}
async function humanApprovalPanel(gen){
 try{
 const ready=await humanReady();if(gen!==viewGen)return;
 if(!ready){noHumanActions(view);return;}
 const slug=current.slug, section=el('section','decision');section.id='humanApproval';section.append(el('h3',null,'Record a human stage decision'));
 section.append(el('p','notice','Load the exact current artifact below, review it and any required media, then confirm. Existing parent, image-verdict and graphics gates still apply.'));
 const label=el('label',null,'Stage');const select=el('select');select.id='approvalStage';
 for(const stage of humanSession.stages){if(stage==='lyrics'&&currentData.entry.music_mode==='instrumental')continue;const o=el('option',null,stageNames[stage]||stage);o.value=stage;select.append(o);}label.append(select);section.append(label);
 const next=currentData.entry.next_step.split(' ')[0];if(humanSession.stages.includes(next))select.value=next;
 const load=el('button','mini','Load current artifact');load.type='button';section.append(load);
 const artifact=el('div');const feedback=el('p','meta');feedback.setAttribute('role','status');section.append(feedback,artifact);view.prepend(section);
 let reviewed=null;
 select.onchange=()=>{reviewed=null;clear(artifact);feedback.textContent='Load this stage before deciding.';};
 load.onclick=async function(){
  load.disabled=true;reviewed=null;clear(artifact);feedback.textContent='Loading current review identity…';
  const stage=select.value;
  try{const d=await api('/api/project/'+encodeURIComponent(slug)+'/approval/'+encodeURIComponent(stage));if(gen!==viewGen||select.value!==stage)return;reviewed=d;
   artifact.append(el('p','code','Reviewed hash: '+d.expected_hash));const detail=el('details');detail.open=true;detail.append(el('summary',null,'Artifact to review'),el('pre',null,JSON.stringify(d.artifact,null,2)));artifact.append(detail);
   const form=el('form');const note=noteInput(form);
   const confirmation=check(stage==='preview'?'I watched the preview continuously with its actual music.':'I reviewed the required artifacts and media for this exact stage.');form.append(confirmation.wrapper);
   let inspected=null,uncertain=null;
   if(stage==='graphics'){inspected=check('I inspected the actual composited graphics samples.');form.append(inspected.wrapper);}
   if(stage==='lyrics'){uncertain=check('I explicitly acknowledge any remaining flagged lyric uncertainty.');uncertain.box.required=false;form.append(uncertain.wrapper);}
   const submit=el('button',null,'Approve '+(stageNames[stage]||stage));submit.type='submit';form.append(submit);artifact.append(form);feedback.textContent='No decision has been recorded yet.';
   form.onsubmit=async function(e){e.preventDefault();if(!reviewed||submit.disabled)return;submit.disabled=true;
    const body={expected_hash:d.expected_hash,note:note.value,confirmed:confirmation.box.checked};if(stage==='preview')body.preview_watched=confirmation.box.checked;if(inspected)body.inspected=inspected.box.checked;if(uncertain)body.acknowledge_uncertain=uncertain.box.checked;
    try{await decide('/api/project/'+encodeURIComponent(slug)+'/approve/'+stage,body);humanStatus.textContent='Approved '+stage+' for '+slug+'. No generation was started.';verifiedEntries.clear();await loadProjects();if(gen===viewGen)showTab('approvals',true);}
    catch(error){feedback.textContent=error.message;if(error.status===409||error.status===401){reviewed=null;feedback.textContent+=' Reload the artifact in a valid human session before deciding again.';}else submit.disabled=false;}
   };
  }catch(error){if(gen===viewGen)feedback.textContent=error.message;}finally{if(gen===viewGen)load.disabled=false;}
 };
 }catch(error){if(gen===viewGen)view.append(el('p','warn',error.message));}
}
async function loadQuotes(gen){
 const slug=current.slug;const d=await api('/api/project/'+encodeURIComponent(slug)+'/quotes');const ready=await humanReady();if(gen!==viewGen)return;clear(view);
 view.append(el('h3',null,'Quote scope and spending authority'),el('p','notice','Authorization permits a later separately requested executor run. It does not upload, generate, reserve a task or charge anything now. The amount is the exact quoted admission reservation, not a provider-enforced spending guarantee.'));
 if(!ready)noHumanActions(view);
 if(!d.quotes.length)view.append(el('div','empty','No quotes recorded. Prepare a quote through clip, then refresh this view.'));
 for(const q of d.quotes){const card=el('section','decision');card.append(el('h3',null,(q.kind||'Unavailable quote')+' · '+q.id));view.append(card);
  if(q.problem){card.append(el('p','warn',q.problem));continue;}
  card.append(el('p',null,'Exact authority: '+String(q.reserve_total_usd)+' USD · '+q.authorization_state));
  card.append(el('p','meta',q.provider+' · '+(q.model_slug||q.model||'Model not recorded')+' · '+(q.scope||q.kind)+' · '+(q.kind==='images'?q.tasks.length+' image tasks':'Audio inference')));
  if(q.authorization)card.append(el('p','meta','Recorded authority: '+String(q.authorization.cap_usd)+' USD · '+stamp(q.authorization.at)+' · '+(q.authorization.via||'legacy surface')+' · '+(q.authorization.note||'No note')));
  if(q.authorization&&q.uploads_required&&q.authorization.uploads_confirmed!==true)card.append(el('p','meta','Transfer consent is not separately attested in this legacy/incomplete record. Existing authority is not rewritten.'));
  if(q.uploads_required)card.append(el('p','warn','External data transfer: source audio or reference images may be uploaded or reused by the later executor. Review the exact scope below.'));
  const detail=el('details');detail.append(el('summary',null,'Review complete quoted scope'),el('pre',null,JSON.stringify(q,null,2)));card.append(detail);
  if(!ready||q.authorization_state==='current')continue;
  if(q.authorization){card.append(el('p','warn','A different or stale recorded authority exists. Studio will not overwrite it; inspect the record and prepare a new quote if needed.'));continue;}
  const form=el('form');const note=noteInput(form);const confirmed=check('I reviewed this exact quote, model, settings, scope and amount.');form.append(confirmed.wrapper);
  let uploads=null;if(q.uploads_required){uploads=check('I explicitly permit the quoted source/reference data transfer to the named provider.');form.append(uploads.wrapper);}
  const status=el('p','meta');status.setAttribute('role','status');const button=el('button',null,'Authorize '+String(q.reserve_total_usd)+' USD');button.type='submit';form.append(button,status);card.append(form);
  form.onsubmit=async function(e){e.preventDefault();if(button.disabled)return;button.disabled=true;
   const body={expected_quote_hash:q.expected_quote_hash,note:note.value,confirmed:confirmed.box.checked};if(uploads)body.confirm_uploads=uploads.box.checked;
   try{await decide('/api/project/'+encodeURIComponent(slug)+'/authorize/'+encodeURIComponent(q.id),body);status.textContent='Authorized. Nothing was generated, uploaded or spent.';humanStatus.textContent='Authorized quote '+q.id+' for '+slug+'. No executor was started.';}
   catch(error){status.textContent=error.message;if(error.status!==409&&error.status!==401)button.disabled=false;}
  };
 }
}
sessionInfo().then(s=>{humanStatus.textContent=s.actions_enabled&&actionCapability?'Human action session enabled in this browser. Every decision still requires review and confirmation.'+(!storageAvailable?' Storage is blocked: reopen the human link after a reload.':''):'Read-only session — human decisions are disabled in this browser.';}).catch(()=>{humanStatus.textContent='Session capabilities unavailable — decisions remain disabled.';});
"""
