"""The five-step guided Studio experience.

Presentation only: every canonical edit goes through the typed local routes in
``serve``/``human_actions``. Feedback is a durable request for the agent, never an
approval and never a generation trigger.
"""

CSS = """
/* Guided five-step studio: one Project utility, five creative steps. */
.workflow-tabs{grid-template-columns:repeat(5,minmax(150px,1fr))}
#tab-quotes{display:none!important}
.still-cell{min-width:0;display:flex;flex-direction:column}
.still-cell .still{border-radius:9px 9px 0 0;border-bottom:0;flex:1}
.still-actions{display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:8px;border:1px solid var(--line);border-top:0;border-radius:0 0 9px 9px;background:var(--surface)}
.still-actions .mini{font-size:11px;min-height:30px;padding:5px 8px}
.still-actions .mini.on{background:var(--ok);color:#102016;border-color:var(--ok)}
.shot-feedback{width:100%;margin-top:6px;padding:10px;background:var(--panel);border:1px solid var(--line);border-radius:7px}
.shot-feedback textarea{min-height:70px}
.progress-track{height:8px;background:var(--line);border-radius:999px;overflow:hidden;margin:10px 0}
.progress-fill{height:100%;background:var(--gold)}
.feedback-item{padding:12px 0;border-bottom:1px solid var(--line)}
.feedback-item:last-child{border:0}
.credit-row{display:grid;grid-template-columns:1fr 1.4fr auto;gap:8px;margin:8px 0;align-items:center}
.credit-row input{min-height:38px}
.confirmation input{width:20px;min-height:20px;height:20px}
input[type=file]{padding:9px;background:var(--surface);border:1px solid var(--line);border-radius:8px;width:100%}
input[type=file]::file-selector-button{margin-right:10px;padding:7px 11px;border:0;border-radius:6px;background:var(--gold);color:#1a1408;font:600 12px/1.2 inherit;cursor:pointer}
#sourceStatus.ok{color:var(--ok)}#sourceStatus.warn{color:var(--warn)}
.content-card details{border:0;padding:0;margin:8px 0}
.content-card details summary{min-height:28px}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0}
.approval-table{table-layout:auto}.approval-table th:nth-child(3),.approval-table td:nth-child(3){width:auto}
code{font-family:ui-monospace,Menlo,monospace;font-size:12px;overflow-wrap:anywhere}
@media(max-width:600px){.workflow-tabs{grid-template-columns:repeat(5,150px)}.stillgrid{grid-template-columns:1fr}.credit-row{grid-template-columns:1fr}}
"""

SCRIPT = r"""
// Five visible steps. Project details live in one utility panel, not four menus.
const FLOW_STEPS = [
  {id:'track', number:'01', label:'Track'},
  {id:'story', number:'02', label:'Story'},
  {id:'style', number:'03', label:'Style check'},
  {id:'images', number:'04', label:'Images'},
  {id:'finish', number:'05', label:'Finish'},
];
const STAGE_STEP = {analysis:'track', lyrics:'track', events:'track', brief:'story', storyboard:'story', proof:'style', preview:'images', stills:'images', graphics:'finish'};
const STEP_STAGES = {track:['analysis'], story:['brief','storyboard'], style:['proof'], images:['stills'], finish:['graphics']};
let humanEnabled=false, flowData=null, boardCache=null, storyReview=null;
const initialWelcome=view.firstElementChild.cloneNode(true);

const btn=(text,cls,onClick)=>{const b=el('button',cls||'mini',text);b.type='button';b.onclick=onClick;return b;};
const actionButton=(text,onClick,cls='mini')=>btn(text,cls,onClick);
const textarea=(value,placeholder,rows=4)=>{const t=el('textarea');t.rows=rows;t.value=value||'';t.placeholder=placeholder||'';return t;};
const checkbox=(label,required=true)=>{const w=el('label','confirmation');const c=el('input');c.type='checkbox';c.required=required;w.append(c,document.createTextNode(' '+label));return {wrapper:w,box:c};};
const field=(labelText,control)=>{const l=el('label',null,labelText);l.append(control);return l;};
const notice=(text,cls='notice')=>el('p',cls,text);
const prettyLabel=value=>String(value??'').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
const stageRecord=stage=>[...(currentData?.approvals?.stages||[]),...(currentData?.approvals?.supporting_stages||[])].find(s=>s.stage===stage)||null;
const approved=stage=>{const s=stageRecord(stage);return !!s&&s.state==='approved';};
const stageState=stage=>stageRecord(stage)?.state||'unavailable';
const shotRows=data=>data&&data.shots?data.shots:[];
const proofShots=(data,ids)=>shotRows(data).filter(s=>ids.includes(s.id));
const accepted=shot=>shot.verdict==='accept';
const allAccepted=shots=>shots.length>0&&shots.every(accepted);
const statusText=shot=>shot.version?('v'+String(shot.version).padStart(3,'0')):'not generated';

function currentStep(){
  if(!currentData?.entry)return 'story';
  if(!approved('brief')||!approved('storyboard'))return 'story';
  if(!approved('proof'))return 'style';
  if(!approved('stills'))return 'images';
  return 'finish';
}
function humanBanner(node){
  if(humanEnabled)return;
  const banner=el('div','callout');
  banner.append(document.createTextNode('Viewing only. To approve or request changes, start '));
  banner.append(el('code',null,'uv run clip serve --actions'));
  banner.append(document.createTextNode(' in your own terminal and open its human action link. Nothing is approved or spent here without that session.'));
  node.append(banner);
}
function stepState(id){
  const s=currentData?.entry?.stages||{};
  if(id==='track'){
    const analysed=s.analysis==='approved'||(!!currentData?.entry?.guided&&!!flowData?.artifacts?.analysis?.available);
    return analysed?'Analysed':'Preparing';
  }
  if(id==='story')return approved('brief')&&approved('storyboard')?'Approved':(s.brief==='stale'||s.storyboard==='stale'?'Changed':'Needs review');
  if(id==='style')return approved('proof')?'Approved':(s.proof==='stale'?'Changed':'Review samples');
  if(id==='images'){
    if(approved('stills'))return 'Approved';
    if(flowData?.flow?.preview_gate&&!approved('preview'))return 'Preview needed';
    return 'Review images';
  }
  if(approved('graphics')){
    const latest=currentData?.entry?.renders?.[0];
    return latest?.exists?'Ready':'Render';
  }
  return 'Credits & final';
}
function updateWorkflow(){
  document.getElementById('tabs').hidden=!current;
  if(!currentData?.entry)return;
  const e=currentData.entry;
  document.getElementById('projectEyebrow').textContent='Production · '+e.slug;
  document.getElementById('projectMeta').textContent=clock(e.duration)+' soundtrack · '+e.aspect+' · '+e.fps+' fps · '+(e.shots||0)+' shots';
  for(const step of FLOW_STEPS){
    const button=document.getElementById('tab-'+step.id);
    if(!button)continue;
    const state=stepState(step.id);
    const cls=state==='Approved'||state==='Analysed'||state==='Ready'?'approved':(['Changed'].includes(state)?'stale':'open');
    button.dataset.state=cls;
    button.querySelector('.step-state').textContent=state;
    button.title=STEP_STAGES[step.id].map(s=>(stageNames[s]||s)+': '+stageState(s)).join(' · ');
  }
  document.getElementById('projectSwitch').value=current?.slug||'';
}
function renderLibrary(){
  const box=document.getElementById('list');if(!box)return;
  const query=(document.getElementById('projectSearch').value||'').trim().toLowerCase();
  clear(box);const picker=document.getElementById('projectSwitch');clear(picker);
  const choose=el('option',null,'Choose a production');choose.value='';picker.append(choose);
  const count=document.getElementById('projectCount');if(count)count.textContent=projects.length;
  for(const summary of projects){
    const p=verifiedEntries.get(summary.slug)||summary;
    const option=el('option',null,p.title+' · '+p.slug);option.value=p.slug;picker.append(option);
    if(query&&!(p.title+' '+p.slug).toLowerCase().includes(query))continue;
    const stepRoute=!p.stages?'story':(p.stages.storyboard!=='approved'?'story':p.stages.proof!=='approved'?'style':p.stages.stills!=='approved'?'images':'finish');
    const card=el('a','card');card.href='#/'+encodeURIComponent(p.slug)+'/'+stepRoute;card.dataset.slug=p.slug;
    if(current?.slug===p.slug){card.classList.add('on');card.setAttribute('aria-current','page');}
    card.append(el('b',null,p.title),el('div','meta',clock(p.duration)+' · '+p.shots+' shots'));
    const step=!p.stages?null:(p.stages.storyboard!=='approved'?'Story':p.stages.proof!=='approved'?'Style check':p.stages.stills!=='approved'?'Images':'Finish');
    card.append(el('div','card-state',step?'Next: '+step:'Production complete'),el('div','card-check',p.checked_at?'Checked '+stamp(p.checked_at):'Media not checked'));
    box.append(card);
  }
  picker.value=current?.slug||'';
  if(!box.children.length)box.append(el('p','notice',projects.length?'No productions match your search.':'No productions yet. Start with a local track.'));
}
renderProjects=renderLibrary;
document.getElementById('projectSearch')?.addEventListener('input',renderLibrary);
document.getElementById('projectSwitch').onchange=function(){if(this.value)navigate(this.value,'overview');else location.hash='';};

function heading(title,description){const box=el('div','view-heading'),left=el('div');left.append(el('h2',null,title));if(description)left.append(el('p',null,description));box.append(left);return box;}
function technical(title,value){const d=el('details','technical');d.append(el('summary',null,title),el('pre',null,JSON.stringify(value,null,2)));return d;}
function progress(count,total,label){const box=el('div','content-card');const pct=total?Math.round(count/total*100):0;box.append(el('h3',null,label||'Review progress'));const bar=el('div','progress-track');const fill=el('div','progress-fill');fill.style.width=pct+'%';bar.append(fill);box.append(bar,el('p','meta',count+' of '+total+' approved'));return box;}
function feedbackFor(stage){
  const rows=(flowData?.feedback||[]).filter(r=>r.stage===stage);
  if(!rows.length)return null;
  const box=el('section','content-card');box.append(el('h3',null,'Revision notes'));
  for(const request of rows.slice().reverse()){
    const item=el('div','feedback-item');item.append(el('div','meta',stamp(request.created_at)+' · '+request.status+(request.scope!=='whole'?' · '+request.scope+': '+request.target:'')));
    item.append(el('p',null,request.message));
    if(request.style){const style=el('details');style.append(el('summary',null,'Requested style'),el('pre',null,request.style));item.append(style);}
    if(request.reply)item.append(el('p','meta','Agent reply: '+request.reply));
    box.append(item);
  }
  return box;
}
function feedbackForm(stage,{shots=null,styleControl=null,defaultMessage=''}={}){
  if(!humanEnabled)return null;
  const form=el('form','content-card feedback-form');form.append(el('h3',null,'Notes for your agent'));
  form.append(el('p','notice','Describe what should change. This records a direction request; your agent applies it and replies. It does not generate or spend.'));
  const message=textarea(defaultMessage,'What should change?',4);message.required=true;message.maxLength=4000;
  form.append(field('What should change?',message));
  let scope=null,target=null;
  if(shots&&shots.length){
    scope=el('select');for(const pair of [['whole','Whole film'],['shot','One shot']]){const o=el('option',null,pair[1]);o.value=pair[0];scope.append(o);}
    target=el('select');for(const shot of shots){const o=el('option',null,shot.id+' · '+(shot.purpose||shot.framing||''));o.value=shot.id;target.append(o);}
    target.disabled=true;scope.onchange=()=>{target.disabled=scope.value!=='shot';};
    form.append(field('Scope',scope),field('Shot',target));
  }
  const style=styleControl;
  if(style)form.append(el('p','meta','The film-style field above is included with this request.'));
  const confirm=checkbox('I want my agent to apply this revision.',true);form.append(confirm.wrapper);
  const status=el('p','meta');status.setAttribute('role','status');
  const submit=el('button',null,'Request revision');submit.type='submit';
  form.append(submit,status);
  form.onsubmit=async e=>{
    e.preventDefault();if(submit.disabled)return;
    if(!message.value.trim()){message.focus();return;}
    submit.disabled=true;status.textContent='Saving your revision request…';
    try{
      await decide('/api/project/'+encodeURIComponent(current.slug)+'/feedback',{
        stage,scope:scope?scope.value:'whole',target:scope&&scope.value==='shot'?target.value:null,
        message:message.value.trim(),style:style?style.value:null,confirmed:true
      });
      status.textContent='Saved. Your agent will apply this and reply in the workspace.';
      submit.disabled=false;
    }catch(error){status.textContent=error.message;submit.disabled=false;}
  };
  return form;
}
function storyBoardTable(board){
  if(!board||!board.available)return notice(board?.warning||'No storyboard available yet.');
  const box=el('div','scroll');box.tabIndex=0;const table=el('table','board-table');
  const head=el('tr');for(const label of ['Shot','Timing','Framing','Purpose']){const th=el('th',null,label);th.scope='col';head.append(th);}
  const thead=el('thead');thead.append(head);table.append(thead);const body=el('tbody');
  for(const shot of board.shots){
    const tr=el('tr');const cell=el('td');const inspect=btn(shot.id,'mini',()=>showShot(shot.id));inspect.setAttribute('aria-label','Inspect shot '+shot.id);cell.append(inspect);tr.append(cell);
    const timing=el('td',null,shot.seconds.toFixed(1)+'s');timing.append(el('div','meta',clock(shot.start_seconds)+'–'+clock(shot.start_seconds+shot.seconds)));tr.append(timing);
    tr.append(el('td',null,(shot.framing||'—').replaceAll('_',' ')+' · '+shot.transition));
    tr.append(el('td','shot-purpose',shot.purpose));body.append(tr);
  }
  table.append(body);box.append(table);return box;
}
function renderArtifactSummary(node,stage,artifact){
  const a=artifact||{};
  if(stage==='analysis'){
    const facts=el('dl');
    for(const [label,value] of [['Duration',a.duration===undefined?null:clock(a.duration)],['Tempo estimate',a.estimated_tempo_bpm??a.tempo_bpm??a.bpm],['Estimated beats',Array.isArray(a.beats)?a.beats.length:null],['Sections',Array.isArray(a.sections)?a.sections.length:null]])if(value!==null&&value!==undefined)facts.append(el('dt',null,label),el('dd',null,String(value)));
    node.append(facts);return;
  }
  if(stage==='brief'){
    const concept=el('section','content-card');concept.append(el('h3',null,'Concept'));
    const treatment=a.treatment||'';
    if(treatment){concept.append(el('p','notice',treatment.length>680?treatment.slice(0,680)+'…':treatment));if(treatment.length>680){const more=el('details');more.append(el('summary',null,'Read full treatment'),el('p',null,treatment));concept.append(more);}}
    if(a.direction){const more=el('details');more.append(el('summary',null,'Direction'),el('p',null,a.direction));concept.append(more);}
    node.append(concept);
    const detail=el('details','content-card');detail.append(el('summary',null,'Visual arc, scenes and characters'));
    const body=el('div');
    for(const [label,value] of [['Sequence arc',a.creative?.arc],['Scenes',a.creative?.scenes],['Characters',a.characters]])if(value&&(!Array.isArray(value)||value.length)){body.append(el('h3',null,label));readable(body,value);}
    detail.append(body);node.append(detail);return;
  }
  readable(node,a);
}
function renderArtifact(node,stage,artifact){
  if(stage==='brief'){
    const a=artifact||{};
    for(const [label,value] of [['Treatment',a.treatment],['Direction',a.direction],['Visual style',a.creative?.look||a.style],['Sequence arc',a.creative?.arc],['Scenes',a.creative?.scenes],['Characters',a.characters]]){
      if(!value||(Array.isArray(value)&&!value.length))continue;
      const block=el('section','content-card');block.append(el('h3',null,label));readable(block,value);node.append(block);
    }
  }else renderArtifactSummary(node,stage,artifact);
  node.append(technical('Complete artifact · technical details',artifact||{}));
}
function readable(node,value,depth=0){
  if(value===null||value===undefined||value==='')return;
  if(typeof value!=='object'){node.append(el('p',null,String(value)));return;}
  if(depth>4){node.append(technical('Complete structure',value));return;}
  if(Array.isArray(value)){const ul=el('ul');for(const item of value){const li=el('li');readable(li,item,depth+1);ul.append(li);}node.append(ul);return;}
  const dl=el('dl');for(const [key,item] of Object.entries(value)){if(item===null||item===undefined||item==='')continue;dl.append(el('dt',null,String(key).replaceAll('_',' ')),);const dd=el('dd');readable(dd,item,depth+1);dl.append(dd);}node.append(dl);
}
async function refreshStudio(){currentData=null;verifiedEntries.clear();await loadProjects();}
async function approveStage(stage,note,extra={}){
  const slug=current.slug;
  const snapshot=await api('/api/project/'+encodeURIComponent(slug)+'/approval/'+encodeURIComponent(stage));
  if(!snapshot?.expected_hash)throw new Error('Current content hash is unavailable; refresh first.');
  return decide('/api/project/'+encodeURIComponent(slug)+'/approve/'+encodeURIComponent(stage),{expected_hash:snapshot.expected_hash,note,confirmed:true,...extra});
}
async function workflow(gen){
  const d=await api('/api/project/'+encodeURIComponent(current.slug)+'/workflow');
  if(gen!==viewGen)return null;flowData=d;if(currentData?.entry)updateWorkflow();return d;
}
async function board(gen){
  const d=await api('/api/project/'+encodeURIComponent(current.slug)+'/board');
  if(gen!==viewGen)return null;boardCache=d;return d;
}
async function fetchStills(gen){
  const d=await api('/api/project/'+encodeURIComponent(current.slug)+'/stills');
  return gen===viewGen?d:null;
}

async function loadOverview(gen){
  if(gen!==viewGen)return;
  const step=currentStep();
  if(step!=='project'){navigate(current.slug,step);return;}
  await loadProjectPanel(gen);
}
async function loadProjectPanel(gen){
  if(gen!==viewGen||!currentData)return;
  humanEnabled=await humanReady();flowData=flowData||await workflow(gen);if(gen!==viewGen)return;
  const e=currentData.entry;clear(view);
  view.append(heading('Project details','Budget, decisions, activity and revision history. The five steps above are the normal path.'));
  const stats=el('div','stats');stats.append(stat(clock(e.duration),'soundtrack'),stat(e.shots||0,'shots'),stat(money(e.spend.accounted_usd),'accounted spend'),stat(money(e.spend.cap_usd),'production allowance'));view.append(stats);
  humanBanner(view);
  const budget=el('section','content-card');budget.append(el('h3',null,'Budget'));const dl=el('dl');
  for(const [label,value] of [['Allowance',money(e.spend.cap_usd)],['Accounted (costs + reserves)',money(e.spend.accounted_usd)],['Remaining',money(e.spend.remaining_usd)],['Over cap',e.spend.over_cap===null?'Not checked':(e.spend.over_cap?'Yes':'No')]])dl.append(el('dt',null,label),el('dd',null,String(value)));
  budget.append(dl,el('p','notice','A quote is not a charge. Every paid batch still needs its own exact authorization.'),btn('Budget & quotes',null,()=>showTab('quotes')));
  view.append(budget);
  const decisions=el('details','content-card');decisions.append(el('summary',null,'Decision history'));
  const table=el('table','approval-table');const head=el('tr');for(const label of ['Stage','State','Recorded','Note']){const th=el('th',null,label);th.scope='col';head.append(th);}const thead=el('thead');thead.append(head);const body=el('tbody');
  for(const s of [...(currentData.approvals?.stages||[]),...(currentData.approvals?.supporting_stages||[])]){
    const tr=el('tr');tr.append(el('td',null,stageNames[s.stage]||s.stage),el('td',null,s.state),el('td',null,s.at?stamp(s.at):'—'),el('td','decision-note',s.note||'No decision recorded'));body.append(tr);
  }
  table.append(thead,body);decisions.append(table);
  view.append(decisions,btn('Open advanced decision form',null,()=>{pendingApprovalStage=null;humanApprovalPanel(viewGen);}));
  const activity=el('details','content-card');activity.append(el('summary',null,'Activity'));
  const ops=e.operations||{};activity.append(el('p','notice',ops.newest_running?'Running: '+ops.newest_running.command+' · '+ops.newest_running.phase:'No operation is running.'),btn('Open activity log',null,()=>showTab('runs')));
  view.append(activity);
  const commands=el('details','content-card');commands.append(el('summary',null,'Technical commands & local artifacts'),copyCommand('uv run clip status projects/'+current.slug),copyCommand('uv run clip backup projects/'+current.slug));view.append(commands);
  const feedback=feedbackFor('track')||feedbackFor('story')||feedbackFor('style')||feedbackFor('images')||feedbackFor('finish');
  if(feedback){const all=el('section','content-card');all.append(el('h3',null,'Recent revision requests'));for(const stage of ['track','story','style','images','finish']){const block=feedbackFor(stage);if(block)all.append(block);}view.append(all);}
  if(flowData?.feedback_problem)view.append(el('p','warn',flowData.feedback_problem));
}

async function loadTrack(gen){
  const d=await workflow(gen);if(!d||gen!==viewGen)return;
  humanEnabled=await humanReady();if(gen!==viewGen)return;
  clear(view);view.append(heading('Track','Listen first. The recording is measured locally; you do not need to approve technical estimates.'));
  humanBanner(view);
  const analysis=d.artifacts.analysis;
  const card=el('section','content-card');card.append(el('h3',null,'Recording analysis'));
  if(analysis?.available)renderArtifactSummary(card,'analysis',analysis.artifact);else card.append(notice(analysis?.problem||'No analysis available yet.'));
  card.append(el('p','notice','Measurements are estimates—not verified meter, genre or hearing. Tempo, beats and sections are creative reference points, not a gate.'),technical('Measurement details',analysis?.artifact||{}));
  view.append(card);
  const lyrics=d.artifacts.lyrics;
  if(d.music_mode==='instrumental')view.append(el('div','callout','Instrumental track · lyric review is not required.'));
  else{const l=el('section','content-card');l.append(el('h3',null,'Lyrics'));if(lyrics?.available){const segs=lyrics.artifact.segments||[];l.append(el('p','notice','These words remain drafts until reviewed. Your agent checks uncertainty where it matters.'));for(const s of segs.slice(0,24)){const p=el('p');p.append(el('span','mono',clock(s.start)+'–'+clock(s.end)+'  '),document.createTextNode(s.text||''));l.append(p);}if(segs.length>24)l.append(el('p','meta','… '+segs.length+' lines total'));}else l.append(notice(lyrics?.problem||'No lyric draft yet. Your agent will prepare it if needed.'));view.append(l);}
  const note=feedbackFor('track');if(note)view.append(note);
  const more=feedbackForm('track');if(more)view.append(more);
  const next=el('div','actions');next.append(btn('Continue to story',null,()=>showTab('story')));view.append(next);
}

async function loadStory(gen){
  const [d,b,review]=await Promise.all([workflow(gen),board(gen),api('/api/project/'+encodeURIComponent(current.slug)+'/story-review').catch(()=>null)]);
  if(!d||gen!==viewGen)return;
  humanEnabled=await humanReady();if(gen!==viewGen)return;storyReview=review;
  const shots=b?.shots||[];
  const guided=!!d.flow?.guided;
  clear(view);view.append(heading('Story & storyboard',guided?'Agree the story, the visual style and the shot plan together. Then approve both as one decision.':'Review the concept, film style and shot plan. Recorded v2 productions keep separate brief and storyboard decisions.'));
  humanBanner(view);
  const status=el('div','callout');status.textContent=approved('brief')&&approved('storyboard')?'Story and storyboard are approved.':(guided?'Needs your agreement. The brief and storyboard are approved together.':'Needs your agreement. Approve the brief and the storyboard as separate recorded decisions.');
  view.append(status);
  if(d.artifacts.brief?.available)renderArtifactSummary(view,'brief',d.artifacts.brief.artifact);
  else view.append(el('div','empty','No creative brief yet. Ask your agent to propose a direction.'));
  const style=el('section','content-card');style.append(el('h3',null,'Film style'));
  const styleText=textarea(d.artifacts.brief?.artifact?.creative?.look||d.artifacts.brief?.artifact?.style||'','The look applied to every generated still',7);
  styleText.id='styleText';style.append(el('p','notice','This style is applied to every still. Edit it here and request a revision; your agent applies it to the brief and rehashes the downstream work.'),field('Style prompt',styleText));
  view.append(style);
  const boardCard=el('section','content-card');boardCard.append(el('h3',null,'Storyboard'),el('p','meta',shots.length+' shots · '+new Set(shots.map(s=>s.framing)).size+' framing types · '+(b?clock(b.duration):'not prepared')));
  const panel=el('div','detailbox');panel.id='shotPanel';panel.hidden=true;boardCard.append(panel);
  const boardDetails=el('details');boardDetails.append(el('summary',null,'Review all '+shots.length+' shots'),storyBoardTable(b));boardCard.append(boardDetails);view.append(boardCard);
  const note=feedbackFor('story');if(note)view.append(note);
  const more=feedbackForm('story',{shots,styleControl:styleText,defaultMessage:''});if(more)view.append(more);
  const approval=el('section','content-card');approval.append(el('h3',null,'Agree the story'));
  if(approved('brief')&&approved('storyboard')){approval.append(el('p','notice','Approved. You can move on to the style check.'),btn('Continue to style check',null,()=>showTab('style')));}
  else if(!guided){approval.append(el('p','notice','This recorded production keeps separate brief and storyboard approvals. Use the Project panel to record each decision against its current content.'),btn('Open project decisions',null,()=>showTab('project')));}
  else if(!humanEnabled){approval.append(notice('Start a human action session to approve.'));}
  else if(!storyReview){approval.append(el('p','warn','The current brief and storyboard hashes are unavailable. Refresh and try again.'));}
  else{
    const noteInput=textarea('','What did you agree to?',3);noteInput.required=true;
    const confirm=checkbox('I reviewed this brief and storyboard and approve both as the current plan.');confirm.box.required=true;
    const statusLine=el('p','meta');statusLine.setAttribute('role','status');
    const submit=el('button',null,'Approve story & storyboard');submit.type='submit';
    const form=el('form');form.append(field('Decision note',noteInput),confirm.wrapper,submit,statusLine);
    form.onsubmit=async e=>{e.preventDefault();if(submit.disabled)return;submit.disabled=true;statusLine.textContent='Recording your decision…';try{await decide('/api/project/'+encodeURIComponent(current.slug)+'/approve-story',{expected_hash:storyReview.combined_hash,note:noteInput.value.trim(),confirmed:true});await refreshStudio();showTab('style',true);}catch(error){statusLine.textContent=error.message;submit.disabled=false;}};
    approval.append(form);
  }
  view.append(approval);
}

function shotActions(shot,mode){
  const box=el('div','still-actions');
  if(!humanEnabled){box.append(el('span','mini','Read-only'));return box;}
  if(!shot.version){box.append(el('span','mini','Not generated'));return box;}
  box.append(btn(accepted(shot)?'Approved':'Approve',accepted(shot)?'mini on':'mini',async()=>{
    try{await decide('/api/project/'+encodeURIComponent(current.slug)+'/review',{shot_id:shot.id,version:shot.version,sha256:shot.sha256,verdict:'accept',note:'Approved in Studio after inspecting this exact image',confirmed:true});await refreshStudio();showTab(tab,true);}catch(error){window.alert(error.message);}
  }));
  const changes=btn('Request changes','mini',()=>{
    const form=el('form','shot-feedback');const msg=textarea('','What should change in this image?',3);msg.required=true;form.append(field('Feedback',msg));const status=el('p','meta');status.setAttribute('role','status');const send=el('button',null,'Send change request');send.type='submit';form.append(send,status);
    form.onsubmit=async e=>{e.preventDefault();if(send.disabled)return;send.disabled=true;status.textContent='Saving…';try{await decide('/api/project/'+encodeURIComponent(current.slug)+'/review',{shot_id:shot.id,version:shot.version,sha256:shot.sha256,verdict:'reject',note:msg.value.trim(),confirmed:true});await decide('/api/project/'+encodeURIComponent(current.slug)+'/feedback',{stage:mode==='style'?'style':'images',scope:'shot',target:shot.id,message:msg.value.trim(),confirmed:true});await refreshStudio();showTab(tab,true);}catch(error){status.textContent=error.message;send.disabled=false;}};
    box.append(form);
  });
  box.append(changes);return box;
}
function renderShotGrid(container,shots,mode){
  const panel=el('div','detailbox');panel.id='shotPanel';panel.hidden=true;container.append(panel);
  const grid=el('div','stillgrid');
  for(const shot of shots){
    const cell=el('div','still-cell');cell.dataset.shot=shot.id;
    const card=el('button','still');
    if(shot.has_image){const img=document.createElement('img');img.loading='lazy';img.alt=shot.id+' still';img.src=withToken(shot.thumb);img.addEventListener('error',()=>img.replaceWith(el('div','noimg','image unreadable')));card.append(img);}
    else card.append(el('div','noimg','Not generated'));
    const cap=el('div','cap');const line=el('div');line.append(el('b',null,shot.id));line.append(badge(shot.verdict));cap.append(line);
    cap.append(el('div','p',(shot.framing||'no framing').replaceAll('_',' ')+' · '+shot.seconds.toFixed(1)+'s · '+statusText(shot)));
    if(shot.alias_of)cap.append(el('div','mono','reuses '+shot.alias_of));
    card.append(cap);card.onclick=()=>showShot(shot.id);cell.append(card,shotActions(shot,mode));grid.append(cell);
  }
  if(!shots.length)grid.append(el('div','empty','No shots in this step yet.'));
  container.append(grid);
}

async function loadStyle(gen){
  const [d,stills]=await Promise.all([workflow(gen),fetchStills(gen)]);if(!d||!stills||gen!==viewGen)return;
  humanEnabled=await humanReady();if(gen!==viewGen)return;
  clear(view);view.append(heading('Style check','Generate a few representative shots, adjust the look if needed, and approve the direction before the full set.'));
  humanBanner(view);
  const proof=proofShots(stills,d.proof_shot_ids||[]);
  const prompt=d.artifacts.brief?.artifact?.creative?.look||d.artifacts.brief?.artifact?.style||'';
  const style=el('section','content-card');style.append(el('h3',null,'Film style'),el('p','notice',prompt?(prompt.length>300?prompt.slice(0,300)+'…':prompt):'No style prompt recorded yet.'));
  if(prompt.length>300){const more=el('details');more.append(el('summary',null,'Show full style prompt'),el('p',null,prompt));style.append(more);}
  style.append(btn('Edit film style in Story',null,()=>showTab('story')));view.append(style);
  const progressBox=progress(proof.filter(accepted).length,proof.length,'Style samples approved');view.append(progressBox);
  if(!proof.length)view.append(el('div','callout','No proof selection yet. Your agent chooses the representative shots in the storyboard.'));
  renderShotGrid(view,proof,'style');
  const note=feedbackFor('style');if(note)view.append(note);
  const more=feedbackForm('style',{shots:proof});if(more)view.append(more);
  const approval=el('section','content-card');approval.append(el('h3',null,'Approve the style'));
  if(approved('proof'))approval.append(el('p','notice','The style check is approved.'),btn('Continue to images',null,()=>showTab('images')));
  else{
    const ready=allAccepted(proof);
    approval.append(el('p','notice',ready?'All selected samples are approved. Confirm the style direction to move on.':'Approve each sample first ('+proof.filter(accepted).length+'/'+proof.length+').'));
    if(humanEnabled){const noteInput=textarea('','What direction are you approving?',3);noteInput.required=true;const confirm=checkbox('I reviewed the selected samples and approve this artistic direction.');const statusLine=el('p','meta');statusLine.setAttribute('role','status');const submit=el('button',null,'Approve style check');submit.type='submit';submit.disabled=!ready;const form=el('form');form.append(field('Decision note',noteInput),confirm.wrapper,submit,statusLine);form.onsubmit=async e=>{e.preventDefault();if(submit.disabled)return;submit.disabled=true;statusLine.textContent='Recording…';try{await approveStage('proof',noteInput.value.trim());await refreshStudio();showTab('images',true);}catch(error){statusLine.textContent=error.message;submit.disabled=false;}};approval.append(form);}
  }
  view.append(approval);
}

async function loadImages(gen){
  const [d,stills]=await Promise.all([workflow(gen),fetchStills(gen)]);if(!d||!stills||gen!==viewGen)return;
  humanEnabled=await humanReady();if(gen!==viewGen)return;
  clear(view);view.append(heading('Images','Review every selected still. Approve the ones that work; send the others back with a clear change request.'));
  humanBanner(view);
  if(d.flow?.preview_gate&&!approved('preview')){
    const preview=el('section','content-card');preview.append(el('h3',null,'Pacing preview'),el('p','notice','This production requires a watched preview before the full set.'));
    if(d.preview_movie?.path){const target=el('p','code',d.preview_movie.path);target.id='previewTarget';preview.append(target,el('p','notice',d.preview_movie.exists?'Open this exact movie locally and watch it with sound.':'This recorded movie is missing; ask your agent to restore it.'));}
    else preview.append(notice(d.preview_movie?.problem||'No review-bound preview yet.'));
    if(!d.preview_movie?.exists)preview.append(el('p','warn','The recorded preview movie is missing; the review binding cannot pass until that exact file is restored.'));
    const latest=currentData.entry.preview;if(latest&&(!d.preview_movie?.path||latest.name!==d.preview_movie.path.split('/').pop()))preview.append(el('p','meta','Other local preview: '+latest.name+' · not the approval target. Newer exports never replace the review-bound movie.'));
    if(humanEnabled&&d.preview_movie?.path){const noteInput=textarea('','What did you hear and see?',3);noteInput.required=true;const watched=checkbox('I watched this exact movie continuously with its actual music.');const statusLine=el('p','meta');statusLine.setAttribute('role','status');const submit=el('button',null,'Approve pacing preview');submit.type='submit';const form=el('form');form.append(field('Decision note',noteInput),watched.wrapper,submit,statusLine);form.onsubmit=async e=>{e.preventDefault();if(submit.disabled)return;submit.disabled=true;statusLine.textContent='Recording…';try{await approveStage('preview',noteInput.value.trim(),{preview_watched:true});await refreshStudio();showTab('images',true);}catch(error){statusLine.textContent=error.message;submit.disabled=false;}};preview.append(form);}
    view.append(preview);
  }else if(d.flow?.preview_gate&&approved('preview'))view.append(el('div','callout','Pacing preview approved.'));
  const total=stills.shots.length,acceptedCount=stills.shots.filter(accepted).length,missing=stills.counts?.unreviewed||0;
  view.append(progress(acceptedCount,total,'Image review progress'));
  if(missing)view.append(el('p','notice',missing+' shot(s) still need a decision. Missing images are labelled; ask your agent to generate them when you are ready.'));
  const note=feedbackFor('images');if(note)view.append(note);
  const more=feedbackForm('images',{shots:stills.shots});if(more)view.append(more);
  const approval=el('section','content-card');approval.append(el('h3',null,'Approve the full image set'));
  if(approved('stills'))approval.append(el('p','notice','All images are approved.'),btn('Continue to finish',null,()=>showTab('finish')));
  else{
    const ready=allAccepted(stills.shots);
    approval.append(el('p','notice',ready?'Every selected image has an accepted verdict. Confirm the full set to continue.':'Approve every image first ('+acceptedCount+'/'+total+').'));
    if(humanEnabled){const noteInput=textarea('','What did you approve?',3);noteInput.required=true;const confirm=checkbox('I reviewed the full selected set and approve these images for the film.');const statusLine=el('p','meta');statusLine.setAttribute('role','status');const submit=el('button',null,'Approve full image set');submit.type='submit';submit.disabled=!ready;const form=el('form');form.append(field('Decision note',noteInput),confirm.wrapper,submit,statusLine);form.onsubmit=async e=>{e.preventDefault();if(submit.disabled)return;submit.disabled=true;statusLine.textContent='Recording…';try{await approveStage('stills',noteInput.value.trim());await refreshStudio();showTab('finish',true);}catch(error){statusLine.textContent=error.message;submit.disabled=false;}};approval.append(form);}
  }
  view.append(approval);
  renderShotGrid(view,stills.shots,'images');
}

function creditsRows(spec){
  const box=el('div','credits-rows');
  const add=(role='',name='')=>{
    const row=el('div','credit-row');const r=el('input');r.value=role;r.placeholder='Role';const n=el('input');n.value=name;n.placeholder='Name';const remove=btn('Remove','mini',()=>row.remove());row.append(r,n,remove);box.append(row);
  };
  for(const card of spec?.credits?.cards||[])add(card[0],card[1]);
  if(!(spec?.credits?.cards||[]).length)add();
  return {box,add};
}
async function loadFinish(gen){
  const d=await workflow(gen);if(!d||gen!==viewGen)return;
  humanEnabled=await humanReady();if(gen!==viewGen)return;
  clear(view);view.append(heading('Finish','Confirm the credits, inspect the composited titles and create the final film.'));
  humanBanner(view);
  const brief=d.artifacts.brief?.artifact;
  const style=el('section','content-card');style.append(el('h3',null,'Film style'));const prompt=brief?.creative?.look||brief?.style||'No style recorded.';const details=el('details');details.append(el('summary',null,'Show film style prompt'),el('p','notice',prompt));style.append(details,el('p','meta','The film style is agreed in Story. Changing it there may require new image generation.'));view.append(style);
  const spec=d.graphics_spec?.artifact;
  const credits=el('section','content-card');credits.append(el('h3',null,'Credits and titles'));
  if(d.flow?.late_credits){
    credits.append(el('p','notice','These factual roles are prefilled from the last production. Edit them for this film; the title and shared production identity stay fixed.'));
    const rows=creditsRows(spec);credits.append(rows.box,btn('Add another role',null,()=>rows.add()));
    if(approved('graphics'))credits.append(el('p','warn','Final graphics are already approved. Saving different credits changes the signature and requires fresh composited samples; the current graphics approval will become stale.'));
    if(humanEnabled){
      const noteInput=textarea('','Confirm the factual roles for this film',3);noteInput.required=true;
      const confirm=checkbox('I confirm these role/name pairs are factually correct for this film.');confirm.box.required=true;
      const template=checkbox('Use these credits to prefill new productions.',false);
      const statusLine=el('p','meta');statusLine.setAttribute('role','status');const submit=el('button',null,'Save credits');submit.type='submit';
      const form=el('form');form.append(field('Confirmation note',noteInput),confirm.wrapper,template.wrapper,submit,statusLine);
      form.onsubmit=async e=>{e.preventDefault();if(submit.disabled)return;submit.disabled=true;statusLine.textContent='Saving credits…';const inputs=[...rows.box.querySelectorAll('.credit-row')];const cards=inputs.map(row=>{const fields=row.querySelectorAll('input');return [fields[0].value.trim(),fields[1].value.trim()];}).filter(card=>card[0]||card[1]);try{await decide('/api/project/'+encodeURIComponent(current.slug)+'/credits',{expected_spec_hash:d.graphics_spec_hash,title:currentData.entry.title,cards,confirmed:true,note:noteInput.value.trim(),use_as_template:template.box.checked});statusLine.textContent='Credits saved.';await refreshStudio();showTab('finish',true);}catch(error){statusLine.textContent=error.message;submit.disabled=false;}};
      credits.append(form);
    }else credits.append(notice('Start a human action session to edit credits.'));
  }else{
    credits.append(el('div','callout','This production predates guided credits: its credit block is part of the approved creative brief. Ask your agent to revise the signature and reapprove the brief; it is not silently rewritten here.'));
    if(spec)credits.append(technical('Current recorded signature',spec));
  }
  view.append(credits);
  const graphics=el('section','content-card');graphics.append(el('h3',null,'Titles and final film'));
  if(approved('graphics'))graphics.append(el('p','notice','Final graphics approval is recorded.'));
  else{
    const review=d.artifacts.graphics?.artifact;
    if(review&&review.samples){const list=el('ul');for(const path of Object.keys(review.samples).slice(0,24))list.append(el('li','code',path));graphics.append(el('p','notice','Inspect these actual composited samples locally before approving:'),list);
      if(humanEnabled){const noteInput=textarea('','What did you inspect?',3);noteInput.required=true;const inspected=checkbox('I inspected the actual composited samples for this film.');const statusLine=el('p','meta');statusLine.setAttribute('role','status');const submit=el('button',null,'Approve final graphics');submit.type='submit';const form=el('form');form.append(field('Decision note',noteInput),inspected.wrapper,submit,statusLine);form.onsubmit=async e=>{e.preventDefault();if(submit.disabled)return;submit.disabled=true;statusLine.textContent='Recording…';try{await approveStage('graphics',noteInput.value.trim(),{inspected:true});await refreshStudio();showTab('finish',true);}catch(error){statusLine.textContent=error.message;submit.disabled=false;}};graphics.append(form);}
    }else graphics.append(el('p','notice','No composited samples yet. Ask your agent to render a base and prepare preflight samples.'));
  }
  const renders=currentData.entry.renders||[];const latest=renders[0];
  const renderCard=el('div','content-card');renderCard.append(el('h3',null,'Final film'));
  if(latest&&latest.exists)renderCard.append(el('p','notice','Latest export: '+latest.name),el('p','code','projects/'+current.slug+'/renders/'+latest.name),el('p','meta',latest.delivery_ready?'Marked delivery-ready.':'Not yet marked delivery-ready; verify playback and archive.'));
  else renderCard.append(el('p','notice','No final export yet.'));
  const renderForm=feedbackForm('finish',{defaultMessage:'Render the final film, then prepare the composited samples for my approval.'});if(renderForm)renderCard.append(renderForm);
  graphics.append(renderCard);view.append(graphics);
}

// --- local setup wizard -------------------------------------------------- //
let setupStep=0;
function scrollWorkflow(){const selected=document.querySelector('#tabs .tab.on');if(selected?.classList.contains('step')){const rail=selected.parentElement,delta=selected.getBoundingClientRect().left-rail.getBoundingClientRect().left;if(delta<0||delta+selected.offsetWidth>rail.clientWidth)rail.scrollLeft+=delta;}}
function validSetupStep(){const step=document.querySelector('[data-setup-step="'+setupStep+'"]');if(!step)return false;if(setupStep===1){const title=document.getElementById('title');title.setCustomValidity(title.value.trim()?'':'Enter a film title.');}if(setupStep===0&&(uploading||!selectedSource))return false;for(const control of step.querySelectorAll('input,select'))if(!control.reportValidity())return false;return true;}
function showSetupStep(step){setupStep=step;document.querySelectorAll('[data-setup-step]').forEach((node,index)=>node.hidden=index!==step);document.querySelectorAll('.wizard-steps li').forEach((node,index)=>{if(index===step)node.setAttribute('aria-current','step');else node.removeAttribute('aria-current');});const back=document.getElementById('setupBack'),next=document.getElementById('setupNext'),create=document.getElementById('create');if(back)back.hidden=step===0;if(next)next.hidden=step===2;if(create)create.hidden=step!==2;
 const summary=document.getElementById('setupSummary');if(summary){clear(summary);for(const [label,value] of [['Track',selectedSource?.title||'Not selected'],['Film',document.getElementById('title').value||'Not named'],['Format',document.getElementById('aspect').selectedOptions[0].text+' · '+document.getElementById('fps').value+' fps'],['Approach',document.getElementById('mode').selectedOptions[0].text]])summary.append(el('dt',null,label),el('dd',null,value));}
 document.querySelector('[data-setup-step="'+step+'"] input, [data-setup-step="'+step+'"] select')?.focus();syncCreate();}
function openSetup(){document.getElementById('createDialog').showModal();showSetupStep(setupStep);}
document.getElementById('newProduction').onclick=openSetup;
document.getElementById('closeCreate').onclick=()=>document.getElementById('createDialog').close();
view.addEventListener('click',event=>{if(event.target.id==='welcomeCreate')openSetup();});
document.getElementById('setupNext').onclick=()=>{if(validSetupStep())showSetupStep(Math.min(2,setupStep+1));};
document.getElementById('setupBack').onclick=()=>showSetupStep(Math.max(0,setupStep-1));
document.getElementById('aspect').onchange=function(){document.getElementById('aspectHelp').textContent=this.value==='9:16'?'Portrait needs an explicit titles/credits plan before spending. The current signature compositor is landscape-only.':'Landscape supports the complete titles and credits package.';document.getElementById('aspectHelp').className=this.value==='9:16'?'warn':'meta';};
document.getElementById('createForm').noValidate=true;
document.getElementById('title').addEventListener('input',function(){this.setCustomValidity('');});

// Keep the old routes available for bookmarks, but the five steps are the path.
Object.assign(loaders,{
  overview:loadOverview, project:loadProjectPanel, track:loadTrack, story:loadStory,
  style:loadStyle, images:loadImages, finish:loadFinish
});
// A new project must not inherit the previous project's cached review data.
const baseOpenProject=openProject;
openProject=function(...args){flowData=null;boardCache=null;storyReview=null;return baseOpenProject(...args);};
"""
