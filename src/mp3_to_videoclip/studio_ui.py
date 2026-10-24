"""Workflow presentation for the vanilla Studio; no authority or persistent state.

The CSS layer refines the existing review primitives. The script uses the same
read-only projections and routing as the shell; human decisions remain in human_ui.
"""

CSS = """
:root{--bg:#101215;--panel:#181b20;--panel2:#20242b;--ink:#f2f1ee;--muted:#a3aab5;
--gold:#e2bc80;--teal:#92b8c0;--line:#30353e;--ok:#92d4ad;--warn:#edc584;--bad:#f09e9a;
--surface:#13161a;--radius:12px}
body{background:var(--bg);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
[hidden]{display:none!important}button,input,select,textarea{transition:border-color .15s,background .15s}
button{min-height:42px;margin:0;border-radius:8px;padding:10px 16px;font-size:13px;letter-spacing:.01em}
button:hover{filter:none;background:#efd0a0}button:disabled{cursor:not-allowed;background:#30353e;color:#a3aab5}
input,select,textarea{background:var(--surface);border-color:var(--line);min-height:44px;font-size:16px;border-radius:8px}
input:hover,select:hover,textarea:hover{border-color:#626b79}textarea{padding:12px;font:inherit;width:100%}
label{font-size:13px;text-transform:none;letter-spacing:0;color:var(--ink);font-weight:550;margin:18px 0 7px}
a{text-underline-offset:4px}:focus-visible{outline:2px solid var(--gold);outline-offset:4px}
h1,h2,h3{letter-spacing:-.025em;line-height:1.25}h3{font-size:17px;margin:24px 0 12px}
p{margin:8px 0 16px}.wrap{max-width:1720px;padding:0 32px 48px;margin:auto}
.app-header{display:flex;align-items:center;flex-wrap:wrap;gap:16px;padding:24px 0;border-bottom:1px solid var(--line);margin-bottom:28px}
.brand{display:flex;align-items:center;gap:13px;margin-right:auto}.brand-mark{display:grid;place-items:center;width:42px;height:46px;background:var(--gold);color:#191715;border-radius:9px;font-size:26px;font-weight:750}
.kicker{font-size:10px;color:var(--gold);letter-spacing:.16em}.app-header h1{font-size:21px;margin:3px 0 0;font-weight:650}
#humanStatus{order:3;flex-basis:100%;margin:0;font-size:12px;max-width:none;color:var(--muted)}
.grid{grid-template-columns:254px minmax(0,1fr);gap:28px;align-items:start}
.panel{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:22px}
aside.panel{background:transparent;border:0;padding:0;position:sticky;top:24px}
.library-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.library-heading h2{font-size:14px;margin:0;letter-spacing:0}
#projectSearch{font-size:16px;min-height:40px;margin-bottom:18px}#list{max-height:calc(100dvh - 325px);overflow-y:auto;padding:1px 5px 1px 1px;scrollbar-width:thin;scrollbar-color:#4b515b transparent}
.card{background:transparent;border:1px solid transparent;border-radius:9px;padding:13px 12px;margin-bottom:7px;position:relative}
.card:hover{background:var(--panel);border-color:var(--line)}.card.on{background:var(--panel2);border-color:#59513f}
.card.on:before{content:"";position:absolute;left:-1px;top:18px;bottom:18px;width:3px;border-radius:3px;background:var(--gold)}
.card b{font-size:14px;line-height:1.4;display:block}.card .meta{font-size:12px;line-height:1.6;margin-top:5px}
.card .card-state{color:var(--gold);font-size:11px;margin-top:9px}.card .card-check{font-size:10px;color:var(--muted);margin-top:3px}
.library-foot{padding:18px 10px 0;border-top:1px solid var(--line);font-size:11px;color:var(--muted);line-height:1.8;margin-top:18px}
.workspace{padding:0;overflow:hidden;min-height:650px}.project-heading{display:flex;align-items:start;gap:24px;justify-content:space-between;padding:26px 28px 20px}
#detailTitle{font-size:26px;margin:7px 0 0;letter-spacing:-.025em;font-weight:650}#projectMeta{margin:9px 0 0;font-size:12px}
.toolbar{display:flex;flex-direction:column;align-items:flex-end;gap:8px;margin:0;flex-shrink:0}#freshness{font-size:10px;max-width:230px;text-align:right}
.utility-tabs{display:flex;gap:4px;padding:0 28px 16px}.utility-tabs button.tab{border-radius:7px;border:0;background:transparent;min-height:36px;font-size:12px;padding:7px 13px}
.utility-tabs button.tab.on{background:var(--panel2);color:var(--ink)}
.workflow-tabs{display:grid;grid-template-columns:repeat(8,minmax(142px,1fr));overflow-x:auto;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:var(--surface);scrollbar-width:thin;scroll-padding-inline:6px}
button.tab.step{display:flex;gap:9px;align-items:start;text-align:left;padding:18px 12px;min-height:80px;border:0;border-radius:0;border-right:1px solid var(--line);background:transparent;font-size:12px;white-space:nowrap;color:var(--muted)}
button.tab.step:last-child{border-right:0}button.tab.step.on{background:#29261f;color:var(--gold);box-shadow:inset 0 -2px var(--gold)}
button.tab.step:focus-visible{outline-offset:-4px}
.step-number{font-size:10px;font-variant-numeric:tabular-nums;color:var(--muted);padding-top:2px}.step-state{display:block;font-size:10px;font-weight:400;color:var(--muted);margin-top:5px}
.step[data-state=approved] .step-number{color:var(--ok)}.step[data-state=stale] .step-state,.step[data-state=blocked] .step-state{color:var(--bad)}
button.tab:hover,button.mini:hover,button.chip:hover{background:#30353e;color:var(--ink)}
#view{padding:28px;min-height:350px}.view-heading{display:flex;align-items:start;justify-content:space-between;gap:18px;margin-bottom:24px}.view-heading h2{font-size:21px;margin:0 0 7px}.view-heading p{color:var(--muted);font-size:13px;max-width:72ch;margin:0}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:0 0 28px}.stats:has(.stat:nth-child(5)){grid-template-columns:repeat(5,minmax(0,1fr))}
.stat{background:transparent;border:0;border-right:1px solid var(--line);border-radius:0;padding:17px 20px;min-width:0}.stat:last-child{border:0}.stat b{font-size:24px;letter-spacing:-.04em;font-weight:600;overflow-wrap:anywhere}.stat span{font-size:11px;color:var(--muted)}
.decision{padding:23px 24px;border:1px solid #66563d;border-left:3px solid var(--gold);border-radius:10px;background:linear-gradient(110deg,#29251f,var(--panel));margin:0 0 24px}
.decision h3{font-size:22px;letter-spacing:-.03em;margin:8px 0}.decision p{max-width:80ch}.decision .actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:18px}
.content-card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:20px;margin:16px 0}.content-card h3{margin:0 0 10px}.content-card p:last-child{margin-bottom:0}
.content-card .content-card{background:var(--panel);margin:12px 0;padding:16px}.content-card ul{padding-left:20px}.content-card li{margin:6px 0}
.review-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.review-grid>.content-card{margin:0}
.meta,.notice{color:var(--muted)}.notice{font-size:13px;line-height:1.7}.mono,.code{font-size:12px}.tag,.badge{font-size:11px;padding:3px 8px;border-radius:5px;line-height:1.5}
.badge{margin:0}.tag.ok,.badge.accept,.badge.approved{color:var(--ok);border-color:#385445;background:#1b2b22}
.tag.bad,.badge.reject,.badge.stale,.badge.blocked{color:var(--bad);border-color:#694545;background:#302223}.tag.warn,.badge.uncertain{color:var(--warn);border-color:#65543c;background:#2c271f}
.badge.unavailable{color:var(--muted)}.stage-review{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:20px 0 4px;padding-top:16px;border-top:1px solid var(--line)}
button.mini{min-height:36px;border-radius:7px;padding:7px 12px;font-size:12px;background:var(--panel2);border:1px solid var(--line);color:var(--ink)}
details{border-top:1px solid var(--line);padding-top:10px;margin:18px 0}summary{color:var(--muted);font-size:12px;min-height:36px}details[open]>summary{color:var(--ink)}
.technical{margin-top:28px}pre{font-size:12px;padding:14px;background:var(--surface)}dl{font-size:13px;grid-template-columns:130px minmax(0,1fr);gap:10px 16px}dt{color:var(--muted)}
.filters{gap:8px;margin:0 0 20px}button.chip{min-height:38px;padding:7px 13px;border-radius:7px}button.chip.on{background:var(--gold);color:#171614}
.stillgrid{grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px}.still{border-radius:9px;background:var(--surface);min-width:0}
.still .cap{padding:12px;font-size:12px}.still .cap b{font-size:13px}.still .cap .p{margin-top:5px}.still:hover,.still.on{background:var(--panel2);border-color:var(--gold)}
.still .noimg{font-size:12px}.detailbox{padding:20px;background:var(--surface);margin:0 0 22px}.detailbox h3{font-size:16px}.detailbox .cols{grid-template-columns:minmax(240px,.7fr) minmax(0,1fr)}
.detail-actions{display:flex;justify-content:space-between;gap:12px;margin-bottom:15px}.detailbox img{max-height:480px;object-fit:contain;background:#0e1013}
.scroll{max-height:62vh;border-color:var(--line)}table{font-size:13px}th,td{padding:13px 14px}th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;font-weight:500}
.board-table{table-layout:fixed}.board-table th:nth-child(1){width:24%}.board-table th:nth-child(2){width:12%}.board-table th:nth-child(3){width:18%}.board-table .mini{width:100%;text-align:left;overflow-wrap:anywhere;white-space:normal}.board-table .shot-purpose{line-height:1.65;color:var(--muted)}
.section-list{display:flex;gap:8px;overflow-x:auto;padding-bottom:12px;margin-bottom:18px}.section-item{min-width:160px;max-width:240px;flex-shrink:0;padding:10px 12px;border:1px solid var(--line);border-radius:7px;font-size:12px}.section-item span{display:block;color:var(--muted);font-size:10px;margin-top:5px}.track{height:32px;margin:0 0 24px}.bands{display:none}
.approval-table th:nth-child(3),.approval-table td:nth-child(3){width:34%}.approval-table th,.approval-table td{width:13.2%}.approval-table td details{margin:0;border:0;padding:0}
.approval-table .decision-note{display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden}.approval-table .full-note{margin-top:8px}
.callout{border-left:2px solid var(--gold);padding:12px 16px;background:var(--panel2);font-size:13px;color:var(--muted);margin:18px 0}
.confirmation{display:flex;align-items:flex-start;gap:10px;font-size:13px;line-height:1.6;font-weight:400;margin:20px 0}.confirmation input{width:20px;min-height:20px;height:20px;flex:0 0 20px;margin:1px 0;accent-color:var(--gold)}form>label textarea{margin-top:8px}
.empty{padding:32px 24px;font-size:13px;background:var(--surface)}.empty h3{color:var(--ink)}
.welcome{padding:48px 20px 60px;max-width:650px;margin:auto;text-align:center}.welcome-icon{display:grid;place-items:center;width:76px;height:76px;background:#29261f;border:1px solid #5f513b;border-radius:22px;color:var(--gold);font-size:38px;margin:0 auto 28px}.welcome h2{font-size:32px;margin:12px 0 18px}.welcome p{color:var(--muted);font-size:14px;line-height:1.8}.welcome button{margin:12px 0}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.mobile-projects{display:none}
dialog{color:var(--ink);background:var(--panel);border:1px solid #525965;border-radius:16px;width:min(620px,calc(100vw - 32px));max-height:calc(100dvh - 48px);overflow:auto;padding:28px;box-shadow:0 24px 100px #0009}
dialog::backdrop{background:#080b10bf;backdrop-filter:blur(5px)}.dialog-heading{display:flex;align-items:start;justify-content:space-between;gap:16px}.dialog-heading h2{font-size:25px;margin:7px 0 24px}
.wizard-steps{display:flex;list-style:none;gap:16px;margin:0 0 28px;padding:0 0 18px;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px}.wizard-steps [aria-current]{color:var(--gold);font-weight:650}
fieldset{padding:0;margin:0;border:0;min-width:0}legend{font-size:18px;font-weight:600;margin-bottom:8px;letter-spacing:-.025em}.wizard-actions{display:flex;justify-content:flex-end;gap:12px;margin-top:22px}.wizard-actions #setupBack{margin-right:auto}.setup-summary{padding:18px;background:var(--surface);border:1px solid var(--line);border-radius:9px;margin:22px 0}.setup-summary dd{overflow-wrap:anywhere}
@media(min-width:1500px){.workflow-tabs{grid-template-columns:repeat(8,minmax(0,1fr))}button.tab.step{padding:20px 15px}}
@media(max-width:1100px){.wrap{padding:0 20px 32px}.grid{grid-template-columns:220px minmax(0,1fr);gap:20px}.project-heading{flex-direction:column;gap:12px}.toolbar{flex-direction:row;align-items:center;flex-wrap:wrap}#freshness{text-align:left;max-width:none}.stat{padding:14px}.detailbox .cols{grid-template-columns:1fr}.review-grid{grid-template-columns:1fr}}
@media(max-width:1000px){.app-header{margin-bottom:18px;padding:20px 0;gap:12px}.grid{display:block}.grid>aside{display:none}.mobile-projects{display:block;margin-bottom:20px}.mobile-projects label{margin:0 0 7px}.mobile-projects select{width:100%}.workspace{min-height:540px}#view{padding:22px}.project-heading{padding:22px}.utility-tabs{padding:0 22px 16px}}
@media(max-width:600px){.wrap{padding:0 14px 24px}.app-header{padding:18px 0}.brand-mark{width:32px;height:36px;font-size:22px}.brand{gap:9px}.app-header h1{font-size:17px}.app-header .kicker{font-size:8px}.app-header>button{font-size:11px;padding:9px 11px;min-height:40px}#humanStatus{font-size:10px}#detailTitle{font-size:22px}.project-heading{padding:20px 18px 16px}.toolbar{gap:8px}#freshness{font-size:10px}.utility-tabs{padding:0 14px 14px;gap:0}.utility-tabs button.tab{padding:7px 10px;font-size:11px}.workflow-tabs{grid-template-columns:repeat(8,116px)}#view{padding:20px 16px}.view-heading{flex-direction:column;gap:12px}.view-heading h2{font-size:20px}.stats{grid-template-columns:repeat(2,minmax(0,1fr));margin-bottom:22px}.stat{padding:14px 16px;border-bottom:1px solid var(--line)}.stat:nth-child(2){border-right:0}.stat:nth-child(3){border-bottom:0}.stat b{font-size:22px}.decision{padding:18px}.decision h3{font-size:21px}.content-card{padding:16px}.stillgrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.still .cap{padding:9px}.still .cap b{font-size:11px;overflow-wrap:anywhere}.still .cap .p{font-size:11px}.still .badge{margin:5px 0}.board-table{min-width:620px}.welcome{padding:26px 4px}.welcome h2{font-size:26px}.welcome-icon{width:60px;height:60px;font-size:30px}.row{grid-template-columns:1fr}dialog{padding:22px}.wizard-steps{gap:12px;font-size:10px}dl{grid-template-columns:100px minmax(0,1fr);font-size:12px}.wizard-actions button{min-height:44px}.approval-table td{padding:8px 0}.approval-table tr{padding:16px}}
@media(max-width:600px){.workflow-tabs{grid-template-columns:repeat(8,142px)}.project-heading{gap:10px}.stats:has(.stat:nth-child(5)){grid-template-columns:repeat(2,minmax(0,1fr))}.stats:has(.stat:nth-child(5)) .stat:last-child{grid-column:1/-1;border-top:1px solid var(--line)}.toolbar{align-items:center}#detailTitle:focus-visible{outline-offset:5px;outline-width:1px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
"""

SCRIPT = r"""
// All state below is presentation-only. Canonical artifacts and gates stay on disk.
const stageViews={analysis:'music',lyrics:'music',listening:'music',brand:'direction',events:'music',brief:'direction',storyboard:'board',proof:'proof',preview:'preview',stills:'stills',graphics:'graphics'};
const workflowGroups={music:['analysis','events'],direction:['brief'],board:['storyboard'],proof:['proof'],preview:['preview'],stills:['stills'],graphics:['graphics']};
const viewDescriptions={music:['Listen first. Understand the recording.','Review measured music, edit opportunities and any supplied lyrics before choosing a creative direction.'],direction:['Shape the world of your film.','Review the treatment, visual language and sequence arc before approving the creative brief.'],proof:['Prove the difficult shots first.','Review the selected three-shot proof for style, identity and interaction fidelity before expanding the film.'],preview:['Find the rhythm on the actual music.','Watch the exact review-bound preview continuously with audio. Still images and signal checks do not establish a playback review.'],graphics:['Make the finishing details count.','Review the opening identity, factual credits and actual composited samples—not just the graphics specification.'],delivery:['One complete, verified film.','Only the final composite is a deliverable. Check the final sequence with audio and archive the production before handover.']};
let pendingApprovalStage=null,setupStep=0;
const initialWelcome=view.firstElementChild.cloneNode(true);
function actionButton(text,fn,cls='mini'){const b=el('button',cls,text);b.type='button';b.onclick=fn;return b;}
function heading(title,description){const box=el('div','view-heading'),text=el('div');text.append(el('h2',null,title));if(description)text.append(el('p',null,description));box.append(text);return box;}
function technical(title,value){const box=el('details','technical');box.append(el('summary',null,title),el('pre',null,JSON.stringify(value,null,2)));return box;}
function stageReview(stage){const row=el('div','stage-review');const s=[...currentData.approvals.stages,...(currentData.approvals.supporting_stages||[])].find(s=>s.stage===stage);if(s){const state=stateTag(s.state);state.textContent=(stageNames[stage]||stage)+': '+state.textContent;row.append(state);if(s.problem)row.append(el('p','meta',s.problem));}row.append(actionButton('Review decision',()=>{pendingApprovalStage=stage;showTab('approvals');}));return row;}
function updateWorkflow(){
 document.getElementById('tabs').hidden=!current;
 const e=currentData?.entry;document.getElementById('projectSwitch').value=current?.slug||'';
 if(!e)return;
 document.getElementById('projectEyebrow').textContent='Production · '+e.slug;
 document.getElementById('projectMeta').textContent=clock(e.duration)+' soundtrack · '+e.aspect+' · '+e.fps+' fps · '+(e.shots||0)+' shots';
 for(const [name,stages] of Object.entries(workflowGroups)){
  const button=document.getElementById('tab-'+name),support=(currentData.approvals.supporting_stages||[]).filter(s=>name==='music'?['lyrics','listening'].includes(s.stage):name==='direction'&&s.stage==='brand'),states=[...stages.map(s=>e.stages[s]),...support.map(s=>s.state)];
  const state=states.every(s=>s==='approved')?'approved':states.includes('stale')?'stale':states.includes('blocked')?'blocked':states.includes('unavailable')?'unavailable':states.includes('recorded')?'recorded':'missing';
  button.dataset.state=state;button.querySelector('.step-state').textContent=state==='approved'?'Approved':state==='recorded'?'Not checked':state==='missing'?'Needs review':state==='unavailable'?'Not ready':state==='stale'?'Changed':state==='blocked'?'Blocked':state;
  button.title=[...stages.map(s=>(stageNames[s]||s)+': '+(e.stages[s]||'unavailable')),...support.map(s=>(stageNames[s.stage]||s.stage)+': '+s.state)].join(' · ');
 }
 document.querySelector('#tab-delivery .step-state').textContent=e.next_step==='delivered'?'Recorded':'Verify export';
}
function renderLibrary(){
 const box=document.getElementById('list'),query=document.getElementById('projectSearch').value.trim().toLowerCase();clear(box);
 const picker=document.getElementById('projectSwitch');clear(picker);const prompt=el('option',null,'Choose a production');prompt.value='';picker.append(prompt);
 document.getElementById('projectCount').textContent=projects.length;
 for(const summary of projects){
  const p=verifiedEntries.get(summary.slug)||summary,option=el('option',null,p.title+' · '+p.slug);option.value=p.slug;picker.append(option);
  if(query&&!(p.title+' '+p.slug).toLowerCase().includes(query))continue;
  const card=el('a','card');card.href='#/'+encodeURIComponent(p.slug)+'/overview';card.dataset.slug=p.slug;
  if(current?.slug===p.slug){card.classList.add('on');card.setAttribute('aria-current','page');}
  card.append(el('b',null,p.title),el('div','meta',clock(p.duration)+' · '+p.shots+' shots'));
  if(projects.some(other=>other.slug!==p.slug&&other.title===p.title))card.append(el('div','meta',p.slug));
  const bad=Object.entries(p.stages).find(([,s])=>['stale','blocked'].includes(s));
  const stage=bad?.[0]||p.next_step.split(' ')[0],state=p.stages[stage];
  const next=state?(stageNames[stage]||stage)+': '+(state==='recorded'?'not checked':state):p.next_step==='delivered'?'Delivery recorded':p.next_step==='verify approvals'?'Verify media approvals':p.next_step;
  card.append(el('div','card-state',next),el('div','card-check',p.checked_at?'Checked '+stamp(p.checked_at):'Media not checked'));box.append(card);
 }
 picker.value=current?.slug||'';
 if(!box.children.length)box.append(el('p','notice',projects.length?'No productions match your search.':'No productions yet. Start with a local track.'));
}
document.getElementById('projectSearch').addEventListener('input',renderLibrary);
document.getElementById('projectSwitch').onchange=function(){if(this.value)navigate(this.value,'overview');else{location.hash='';}};
function scrollWorkflow(){const selected=document.querySelector('#tabs .tab.on');if(selected?.classList.contains('step')){const rail=selected.parentElement,delta=selected.getBoundingClientRect().left-rail.getBoundingClientRect().left;if(delta<0||delta+selected.offsetWidth>rail.clientWidth)rail.scrollLeft+=delta;}}
async function workflowData(gen){const d=await api('/api/project/'+encodeURIComponent(current.slug)+'/workflow');return gen===viewGen?d:null;}
function prettyLabel(value){return String(value).replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());}
function readableValue(node,value,depth=0){
 if(value===null||value===undefined||value==='')return;
 if(typeof value!=='object'){node.append(el('p',null,String(value)));return;}
 if(depth>3){node.append(technical('View complete structure',value));return;}
 if(Array.isArray(value)){const list=el('ul');for(const item of value){const li=el('li');readableValue(li,item,depth+1);list.append(li);}node.append(list);return;}
 const dl=el('dl');for(const [key,item] of Object.entries(value)){if(item===null||item===undefined||item==='')continue;dl.append(el('dt',null,prettyLabel(key)));const dd=el('dd');readableValue(dd,item,depth+1);dl.append(dd);}node.append(dl);
}
function renderArtifact(node,stage,artifact){
 const a=artifact||{};
 if(stage==='brief'){
  for(const [label,value] of [['Treatment',a.treatment],['Direction',a.direction],['Visual style',a.creative?.look||a.style],['Sequence arc',a.creative?.arc],['Image rules',a.creative?.image_rules||a.visual_rules],['Scenes',a.creative?.scenes],['Characters',a.characters]]){
   if(!value||(Array.isArray(value)&&!value.length))continue;
   const block=el('section','content-card');block.append(el('h3',null,label));
   if(label==='Characters'&&Array.isArray(value)){for(const character of value){const identity=el('article','content-card');readableValue(identity,character);block.append(identity);}}
   else readableValue(block,value);
   node.append(block);
  }
 }else if(stage==='analysis'){
  const info=el('div','callout','Measurements are estimates—not verified meter, genre, hearing or emotional interpretation.');node.append(info);
  const facts=el('dl');for(const [label,value] of [['Duration',a.duration===undefined?null:clock(a.duration)],['Tempo estimate',a.estimated_tempo_bpm??a.tempo_bpm??a.bpm??a.tempo],['Estimated beats',Array.isArray(a.beats)?a.beats.length:null],['Source',a.provider??a.source]]){if(value!==null&&value!==undefined){facts.append(el('dt',null,label),el('dd',null,String(value)));}}node.append(facts);
 }else if(stage==='events'){
  const events=Array.isArray(a.events)?a.events:[];if(!events.length)node.append(el('p','notice','No musical edit opportunities have been recorded yet.'));
  for(const event of events){const card=el('section','content-card');card.append(el('h3',null,event.label||event.id||'Music event'));readableValue(card,Object.fromEntries(Object.entries(event).filter(([k])=>!['label','id'].includes(k))));node.append(card);}
 }else if(stage==='lyrics'){
  node.append(el('p','notice','Supplied or transcribed words remain drafts until reviewed. Timing may be uncertain.'));
  for(const segment of Array.isArray(a.segments)?a.segments:[]){const p=el('p');p.append(el('span','mono',clock(segment.start)+'–'+clock(segment.end)+'  '),document.createTextNode(segment.text||''));node.append(p);}
  if(!Array.isArray(a.segments))readableValue(node,a);
 }else readableValue(node,a);
 node.append(technical('Complete artifact · technical details',a));
}
function artifactCard(stage,record){const card=el('section','content-card');card.append(el('h3',null,stageNames[stage]||prettyLabel(stage)));if(record?.available)renderArtifact(card,stage,record.artifact);else{card.append(el('p','notice',record?.problem||'No artifact is available yet.'),el('p','meta','Ask the agent to prepare this artifact, then refresh. Availability alone is not an approval.'));}if(workflowGroups.music.includes(stage)||['brief','graphics'].includes(stage))card.append(stageReview(stage));return card;}
async function loadHome(gen){
 if(gen!==viewGen)return;clear(view);const e=currentData.entry,s=currentData.status;
 view.append(heading('Production overview'));
 const stats=el('div','stats');stats.append(stat(clock(s.duration),'soundtrack'),stat((s.shots||[]).length,'planned shots'),stat(money(e.spend.accounted_usd),'accounted spend'),stat(money(e.spend.cap_usd),'production allowance'));
 const support=(currentData.approvals.supporting_stages||[]).find(s=>s.state!=='approved');
 const nextStage=e.stages.analysis==='approved'&&support&&e.next_step.split(' ')[0]!=='events'?support.stage:e.next_step.split(' ')[0],action=(e.actions||[]).find(a=>a.severity==='blocker')||(e.actions||[])[0];
 const operational=action?.severity==='blocker'&&!action.id.startsWith('approve-');
 const box=el('section','decision');box.append(el('div','kicker',e.next_step==='delivered'?'Delivery recorded':'Your next step'));
 box.append(el('h3',null,operational?action.label:nextStage in stageViews?'Review '+(stageNames[nextStage]||nextStage):action?.label||'Verify final delivery'));
 box.append(el('p','notice',!operational&&support?.stage===nextStage?'This supporting music or identity decision is required before the creative brief can pass. Review its evidence first.':action?.reason||'Check the finished composite, complete playback review and archive before handover.'));
 if(nextStage in stageViews){const state=stateTag(e.stages[nextStage]||support?.state);state.textContent=(stageNames[nextStage]||nextStage)+': '+state.textContent;box.append(state);}
 const actions=el('div','actions');actions.append(actionButton(operational?'Show required command':nextStage in stageViews?'Open '+(stageNames[nextStage]||nextStage):'Inspect delivery',()=>{if(operational){const technical=view.querySelector('details.technical');technical.open=true;technical.querySelector('summary').focus();technical.scrollIntoView({block:'nearest'});}else showTab(stageViews[nextStage]||'delivery');},''));actions.append(actionButton('Review decisions',()=>{pendingApprovalStage=nextStage in stageViews?nextStage:null;showTab('approvals');}));box.append(actions);view.append(box,stats);
 const summary=el('section','content-card');summary.append(el('h3',null,'What happens next'));
 summary.append(el('p','notice','Music → creative direction → storyboard → three-shot proof → watched music preview → reviewed rollout → full still set → titles & credits → delivery.'));
 summary.append(el('p','meta','Lyrics are skipped for instrumental tracks. The small rollout is a deliberate review checkpoint, not a separate automatic approval. Stage states are checked against the real gates—not an estimated completion percentage.'));view.append(summary);
 if(e.blockers.length){const card=el('section','content-card');card.append(el('h3',null,'Needs attention'));for(const [kind,text] of e.blockers)card.append(el('p',kind,text));view.append(card);}
 const commands=el('details','technical');commands.append(el('summary',null,'Technical commands & local artifacts'));
 for(const a of e.actions||[]){commands.append(el('h3',null,a.label),el('p','meta',a.reason));if(a.command)commands.append(copyCommand(a.id.startsWith('approve-')?'uv run clip serve --actions':a.command));if(a.href)commands.append(el('p','code',a.href+' · open this artifact locally'));}view.append(commands);
}
async function loadMusic(gen){const d=await workflowData(gen);if(!d)return;clear(view);view.append(heading(...viewDescriptions.music));view.append(artifactCard('analysis',d.artifacts.analysis),artifactCard('events',d.artifacts.events));if(d.music_mode==='instrumental')view.append(el('div','callout','Instrumental production · lyric review is not required. Music structure still needs review.'));else{const lyrics=artifactCard('lyrics',d.artifacts.lyrics);if(d.music_mode==='music-led')lyrics.append(el('p','meta','Lyrics are optional for music-led productions; supplied intent is not measured evidence.'));lyrics.append(stageReview('lyrics'));view.append(lyrics);}for(const s of currentData.approvals.supporting_stages||[])if(s.stage==='listening'){const card=el('section','content-card');card.append(el('h3',null,'Music listening'),el('p','notice',s.note||'Review the recorded listening evidence in the Decisions screen.'),stageReview(s.stage));view.append(card);}}
async function loadDirection(gen){const d=await workflowData(gen);if(!d)return;clear(view);view.append(heading(...viewDescriptions.direction),artifactCard('brief',d.artifacts.brief));for(const s of currentData.approvals.supporting_stages||[])if(s.stage==='brand'){const card=el('section','content-card');card.append(el('h3',null,'Brand identity'),el('p','notice',s.note||'A supplied brand package requires review before the creative brief.'),stageReview('brand'));view.append(card);}}
async function loadGraphics(gen){const d=await workflowData(gen);if(!d)return;clear(view);view.append(heading(...viewDescriptions.graphics),el('div','callout','Inspect actual composited samples locally before confirming. A specification cannot replace reviewing the required output.'));const card=el('section','content-card');card.append(el('h3',null,'Titles and credits specification'));if(d.graphics_spec?.available)renderArtifact(card,'graphics',d.graphics_spec.artifact);else card.append(el('p','notice',d.graphics_spec?.problem||'No graphics specification available.'));if(d.artifacts.graphics?.available)card.append(technical('Recorded composite review evidence',d.artifacts.graphics.artifact));else card.append(el('p','notice','No composite review evidence available. Render and inspect actual samples before approving.'));card.append(stageReview('graphics'));view.append(card);}
async function loadProof(gen){const d=await workflowData(gen);if(!d)return;stillFilter=null;await loadStills(gen);if(gen!==viewGen)return;const grid=view.querySelector('.stillgrid'),ids=new Set(d.proof_shot_ids);if(grid){for(const child of [...grid.children])if(!ids.has(child.dataset.shot))child.remove();}view.querySelector('.filters')?.remove();view.querySelector('.stats')?.remove();view.prepend(heading(...viewDescriptions.proof));if(!ids.size)view.prepend(el('div','callout',d.proof_problem||'Proof selection is not available.'));view.append(stageReview('proof'));}
async function loadPreview(gen){
 const d=await workflowData(gen);if(!d)return;clear(view);const e=currentData.entry,movie=d.preview_movie||{},gate=currentData.approvals.stages.find(s=>s.stage==='preview');
 view.append(heading(...viewDescriptions.preview));const card=el('section','content-card');
 card.append(el('h3',null,movie.path?(movie.exists?'Review-bound local preview':'Recorded preview movie is missing'):'No local preview recorded for the approval gate'));
 if(movie.path){const target=el('p','code',movie.path);target.id='previewTarget';card.append(target);card.append(el('p','notice',movie.exists?'Open this exact movie in your local player and watch it with sound. Studio does not stream it.':'Ask the agent to restore or re-render this exact review target. A newer movie is not a substitute.'));}
 else card.append(el('p','notice',movie.problem||'Ask the agent to render and bind the proof-only preview after the proof is accepted.'));
 if(!gate?.hash)card.append(el('p','warn','The preview review binding is missing or invalid. Resolve it and refresh before making a decision.'));
 card.append(el('div','callout','The review-bound preview may include labelled placeholders. It is not the finished film. Approval requires your explicit continuous-playback confirmation for this exact movie.'),stageReview('preview'));
 if(d.preview_review?.available)card.append(technical('Recorded preview binding',d.preview_review.artifact));view.append(card);
 if(e.preview&&(!movie.path||e.preview.name!==movie.path.split('/').pop()))view.append(el('p','notice','Other local preview: '+e.preview.name+' · not the approval target. Newer available-set exports never replace the review-bound movie.'));
 view.append(el('p','notice','After preview approval, review a small, varied rollout before releasing the remaining stills. No paid batch starts from this screen.'));
}
async function loadDelivery(gen){if(gen!==viewGen)return;clear(view);const e=currentData.entry;view.append(heading(...viewDescriptions.delivery));const card=el('section','content-card');card.append(el('h3',null,e.next_step==='delivered'?'Delivery recorded':'Delivery is not verified'));
 const dl=el('dl');for(const [label,value] of [['Graphics gate',e.stages.graphics],['Export',e.renders?.[0]?.name||'No export recorded'],['Playback review','Must be confirmed against the actual final movie'],['Archive','Verify the local backup before handing over']])dl.append(el('dt',null,label),el('dd',null,value));card.append(dl);view.append(card);
 view.append(el('div','callout','A render file alone is not delivery evidence. Base-only exports, stale approvals, sampled frames and audio signal checks do not establish a watched final film.'));
 const commands=el('details','technical');commands.append(el('summary',null,'Local verification & archive commands'),copyCommand('uv run clip status projects/'+current.slug),copyCommand('uv run clip backup projects/'+current.slug));view.append(commands);
}
// Native dialog supplies Escape, focus containment and return-to-trigger behavior.
function openSetup(){document.getElementById('createDialog').showModal();showSetupStep(setupStep);}
document.getElementById('newProduction').onclick=openSetup;document.getElementById('welcomeCreate').onclick=openSetup;
document.getElementById('closeCreate').onclick=()=>document.getElementById('createDialog').close();
function validSetupStep(){const step=document.querySelector('[data-setup-step="'+setupStep+'"]');if(setupStep===1){const title=document.getElementById('title');title.setCustomValidity(title.value.trim()?'':'Enter a film title.');}for(const control of step.querySelectorAll('input,select'))if(!control.reportValidity())return false;return setupStep!==0||(!document.getElementById('src').disabled&&document.getElementById('src').value!=='');}
function showSetupStep(step){setupStep=step;document.querySelectorAll('[data-setup-step]').forEach((e,i)=>e.hidden=i!==step);document.querySelectorAll('.wizard-steps li').forEach((e,i)=>{if(i===step)e.setAttribute('aria-current','step');else e.removeAttribute('aria-current');});document.getElementById('setupBack').hidden=step===0;document.getElementById('setupNext').hidden=step===2;document.getElementById('create').hidden=step!==2;
 const summary=document.getElementById('setupSummary');clear(summary);for(const [label,value] of [['Track',sourceTracks[Number(document.getElementById('src').value)]?.title||'Not selected'],['Film',document.getElementById('title').value||'Not named'],['Format',document.getElementById('aspect').selectedOptions[0].text+' · '+document.getElementById('fps').value+' fps'],['Approach',document.getElementById('mode').selectedOptions[0].text]])summary.append(el('dt',null,label),el('dd',null,value));
 document.querySelector('[data-setup-step="'+step+'"] input, [data-setup-step="'+step+'"] select')?.focus();syncCreate();}
document.getElementById('setupNext').onclick=()=>{if(validSetupStep())showSetupStep(Math.min(2,setupStep+1));};document.getElementById('setupBack').onclick=()=>showSetupStep(Math.max(0,setupStep-1));
document.getElementById('aspect').onchange=function(){document.getElementById('aspectHelp').textContent=this.value==='9:16'?'Portrait needs an explicit titles/credits plan before spending. The current signature compositor is landscape-only.':'Landscape supports the complete titles and credits package.';document.getElementById('aspectHelp').className=this.value==='9:16'?'warn':'meta';};
document.getElementById('createForm').noValidate=true;
document.getElementById('title').addEventListener('input',function(){this.setCustomValidity('');});
"""
