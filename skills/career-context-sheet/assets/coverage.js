// A local collection ledger. Planning a period never marks its records as read.
const coverageStatuses={pending:'Not started',in_progress:'In progress',checked:'Checked',empty:'No records found',blocked:'Blocked',excluded:'Excluded'};
const githubProjectChecks=['Inventory relevant repositories, including small, archived, unfinished projects and forks; record why a lead is selected, deferred or excluded.', 'Read the purpose, tree and one relevant implementation path. Record a revision and distinguish working code from plans or README claims.', 'Inspect a relevant test and a meaningful commit or PR. A test file is not a passing result; a merge is not deployment.', 'Separate personal contribution, collaborators, upstream code and AI assistance. Ask where ownership is unclear.', 'Record evidence of use or feedback, or say it is unknown. Keep prototypes without inventing impact.', 'Save stable source references, read scope and the next useful read. Deeper review follows consequential gaps; do not execute the project just to inspect it.'];
const coverageView={stream:'',year:'',month:'',editing:false};
function coverageMonth(value){
 if(typeof value!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(value))return NaN;
 const [y,m]=value.split('-').map(Number);return y>=1900&&y<=2199?y*12+m-1:NaN;
}
function coverageMonths(c){
 const start=coverageMonth(c.startMonth),end=coverageMonth(c.endMonth);
 if(!Number.isFinite(start)||!Number.isFinite(end)||end<start||end-start>=600)return [];
 return Array.from({length:end-start+1},(_,i)=>{const n=start+i;return Math.floor(n/12)+'-'+String(n%12+1).padStart(2,'0');});
}
function coverageInitial(packet){return {startMonth:'',endMonth:'',streams:(packet.collection||[]).map((c,i)=>({id:'source-'+(i+1),platform:c.platform,location:c.location,scope:c.scope})),checks:[]};}
function coverageError(c,packet){
 const shape=(o,ks)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).every(k=>ks.includes(k));
 const str=(s,n)=>typeof s==='string'&&s.length<=n&&!s.includes('\0');
 if(!shape(c,['startMonth','endMonth','streams','checks'])||!(c.startMonth===''&&c.endMonth==='')&&!coverageMonths(c).length)return 'Choose an ordered range of up to 600 months.';
 if(!Array.isArray(c.streams)||c.streams.length>80||!Array.isArray(c.checks)||c.checks.length>48000)return 'Invalid source checklist.';
 const ids=new Set(),sources=new Set(packet.sources.map(s=>s.id)),seen=new Set();
 for(const s of c.streams){
  if(!shape(s,['id','platform','location','scope'])||typeof s.id!=='string'||! /^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(s.id)||ids.has(s.id)||!str(s.platform,3000)||!s.platform.trim()||!str(s.location,3000)||!s.location.trim()||!str(s.scope,3000))return 'Name each platform and source location.';
  ids.add(s.id);
 }
 const months=new Set(coverageMonths(c));
 for(const x of c.checks){
  const key=x?.streamId+':'+x?.month;
  if(!shape(x,['streamId','month','status','note','sourceRefs','cursor','found','read'])||!ids.has(x.streamId)||!months.has(x.month)||seen.has(key)||!Object.hasOwn(coverageStatuses,x.status)||!str(x.note,2000)||!str(x.cursor,1000))return 'Invalid source/month receipt.';
  seen.add(key);
  if(!Array.isArray(x.sourceRefs)||new Set(x.sourceRefs).size!==x.sourceRefs.length||x.sourceRefs.some(r=>!sources.has(r)))return 'Link sources already saved in this document.';
  if(!['found','read'].every(k=>Number.isInteger(x[k])&&x[k]>=0&&x[k]<=1000000)||x.read>x.found)return 'Use whole counts; read cannot exceed found.';
  if(['checked','empty','blocked','excluded'].includes(x.status)&&!x.note.trim())return 'Record what was checked, or why this period is blocked or excluded.';
  if(x.status==='checked'&&(!x.sourceRefs.length||!x.read||x.read!==x.found||x.cursor.trim()))return 'To mark checked, link saved evidence, read all selected records and finish pagination. Otherwise use In progress.';
  if(x.status==='empty'&&(x.found||x.read||x.sourceRefs.length||x.cursor.trim()))return 'No records found requires zero records and finished pagination.';
 }
 return '';
}
function coverageComplete(c){const total=coverageMonths(c).length*c.streams.length;return total>0&&c.checks.filter(x=>['checked','empty','excluded'].includes(x.status)).length===total;}
function coverageSummary(c){const checked=c.checks.filter(x=>['checked','empty'].includes(x.status)).length,excluded=c.checks.filter(x=>x.status==='excluded').length,blocked=c.checks.filter(x=>x.status==='blocked').length;return checked+' of '+coverageMonths(c).length*c.streams.length+' source-months checked'+(excluded?' · '+excluded+' excluded':'')+(blocked?' · '+blocked+' blocked':'');}
function mountCoverage(root,state,packet,changed,copy){
 const c=state.coverage,months=coverageMonths(c);
 const el=(t,text,cls)=>{const n=document.createElement(t);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const button=(label,fn,id)=>{const b=el('button',label,'path-secondary');b.type='button';if(id)b.id=id;b.addEventListener('click',fn);return b;};
 const field=(label,input)=>{const l=el('label',label,'path-field');l.append(input);return l;};
 const input=(type,value,max)=>{const n=el('input');n.type=type;n.value=value;if(max)n.maxLength=max;return n;};
 const message=el('p','','coverage-message');message.setAttribute('role','status');
 const repaint=(focusId=document.activeElement?.id)=>{
  root.replaceChildren();mountCoverage(root,state,packet,changed,copy);
  const previous=document.getElementById(focusId),target=previous&&root.contains(previous)&&!previous.closest('details:not([open])')&&previous.getClientRects().length?previous:root.querySelector('.coverage-month[aria-pressed=true]')||root.querySelector('#coverage-start');
  target?.focus({preventScroll:true});
 };
 const commit=(candidate)=>{const error=coverageError(candidate,packet);if(error){message.textContent=error;message.scrollIntoView({block:'nearest'});return false;}state.coverage=candidate;changed('Checklist saved in this browser. Save full HTML to carry it to your coach.');repaint();return true;};
 const setup=el('details',undefined,'coverage-setup');setup.open=!months.length||!c.streams.length;setup.append(el('summary',months.length?'Edit scope':'Set collection scope'));
 const dates=el('div',undefined,'coverage-fields'),start=input('month',c.startMonth),end=input('month',c.endMonth);start.id='coverage-start';end.id='coverage-end';start.min=end.min='1900-01';start.max=end.max='2199-12';
 dates.append(field('From',start),field('Through',end));setup.append(dates,button(months.length?'Update dates':'Build checklist',()=>{
  const next={...c,startMonth:start.value,endMonth:end.value};
  if(!coverageMonths(next).length){message.textContent='Choose start and end months, in order, within 50 years.';return;}
  if(c.checks.some(x=>x.month<next.startMonth||x.month>next.endMonth)){message.textContent='This range would hide saved checks. Keep those months in scope.';return;}
  coverageView.month='';coverageView.year='';commit(next);
 },'coverage-build'));
 const add=el('details');add.append(el('summary','Add a source location'));
 const platform=input('text','',100),location=input('text','',300),scope=el('textarea');platform.id='coverage-platform';location.id='coverage-location';scope.id='coverage-scope';scope.maxLength=2000;scope.rows=2;platform.placeholder='Email, Slack, documents, code…';location.placeholder='Account, folder, channel or export';
 add.append(field('Platform',platform),field('Location',location),field('Scope and exclusions',scope),button('Add location',()=>{
  let number=c.streams.length+1;while(c.streams.some(s=>s.id==='source-'+number))number++;
  const stream={id:'source-'+number,platform:platform.value.trim(),location:location.value.trim(),scope:scope.value};
  if(c.streams.some(s=>s.platform.toLowerCase()===stream.platform.toLowerCase()&&s.location.toLowerCase()===stream.location.toLowerCase())){message.textContent='This source location is already listed.';return;}
  coverageView.stream=stream.id;commit({...c,streams:[...c.streams,stream]});
 },'coverage-add'));setup.append(add);
 if(!months.length||!c.streams.length){root.append(setup,message,el('p','Existing excerpts do not establish month-by-month coverage.','path-question'));return;}
 const count=el('p',coverageSummary(c),'coverage-count'),toolbar=el('div',undefined,'coverage-toolbar');toolbar.append(count,setup);root.append(toolbar,message);
 if(!c.streams.some(s=>s.id===coverageView.stream))coverageView.stream=c.streams[0].id;
 const years=[...new Set(months.map(m=>m.slice(0,4)))];if(!years.includes(coverageView.year))coverageView.year=years[0];
 const selectors=el('div',undefined,'coverage-fields coverage-selectors'),streamSelect=el('select'),yearSelect=el('select');streamSelect.id='coverage-stream';yearSelect.id='coverage-year';
 for(const s of c.streams){const o=el('option',s.platform+' · '+s.location);o.value=s.id;streamSelect.append(o);}streamSelect.value=coverageView.stream;
 for(const y of years){const o=el('option',y);o.value=y;yearSelect.append(o);}yearSelect.value=coverageView.year;
 streamSelect.addEventListener('change',()=>{coverageView.stream=streamSelect.value;coverageView.month='';repaint();});yearSelect.addEventListener('change',()=>{coverageView.year=yearSelect.value;coverageView.month='';repaint();});selectors.append(field('Source location',streamSelect));
 if(years.length>1)selectors.append(field('Year',yearSelect));else{const year=el('div',undefined,'path-field');year.append(el('span','Year'),el('span',years[0],'coverage-year-value'));selectors.append(year);}root.append(selectors);
 const visible=months.filter(m=>m.startsWith(coverageView.year));if(!visible.includes(coverageView.month))coverageView.month=visible[0];
 const grid=el('div',undefined,'coverage-months');grid.setAttribute('aria-label','Monthly collection status');
 for(const month of visible){const x=c.checks.find(x=>x.streamId===coverageView.stream&&x.month===month),status=x?.status||'pending';const b=button('',()=>{coverageView.month=month;repaint();},'coverage-month-'+month);b.className='coverage-month';b.dataset.status=status;b.setAttribute('aria-pressed',String(month===coverageView.month));b.setAttribute('aria-label',month+' · '+coverageStatuses[status]);b.append(el('strong',new Date(month+'-01T12:00:00Z').toLocaleString('en',{month:'short',timeZone:'UTC'})),el('span',coverageStatuses[status]));grid.append(b);}root.append(grid);
 const stream=c.streams.find(s=>s.id===coverageView.stream),month=coverageView.month;
 const receipt=c.checks.find(x=>x.streamId===stream.id&&x.month===month)||{streamId:stream.id,month,status:'pending',note:'',sourceRefs:[],cursor:'',found:0,read:0};
 const github=/github|gitlab|repository|repositories/i.test(stream.platform+' '+stream.location);
 if(github){const guide=el('details',undefined,'github-checklist');guide.append(el('summary','Project review checklist'));const list=el('ul');for(const step of githubProjectChecks)list.append(el('li',step));guide.append(list);root.append(guide);}
 const actions=el('div',undefined,'coverage-actions');
 const task=button('Copy collection task',()=>{const latest=c.checks.find(x=>x.streamId===stream.id&&x.month===month)||receipt;return copy([
  'Continue my career-context collection for ONE source/month. Use the latest private HTML and existing local archive. This checklist does not grant access: use only already-authorized sources and the approved model. If access is unavailable, save a blocked receipt and the next access step; do not invent collected records.',
  'SOURCE: '+stream.platform+' / '+stream.location+'\nSCOPE: '+stream.scope+'\nMONTH: '+month+' (calendar month; record the source timezone)\nCHECKPOINT: '+(latest.cursor||'Start with discovery')+'\nPREVIOUS NOTE: '+latest.note,
  'Inventory dated records, then inspect originals in bounded batches. Finish pagination in the selected scope, retain threads/attachments and surrounding context when relevant, and separate event date from capture date. Deduplicate with stable source IDs. Count discovered and actually read records separately; do not treat a search snippet as a read. Email: preserve thread context and useful attachments within the agreed mailbox, dates and exclusions.',
  ...(github?['For GitHub projects, complete this minimum review for each relevant selected repository:\n'+githubProjectChecks.map((s,i)=>(i+1)+'. '+s).join('\n')]:[]),
  'Save useful evidence and relevant accounts in the same private database; do not put an entire mailbox in the model context. Keep a compact checkpoint after each batch: query/filter, timezone, cursor, found/read counts, retained source IDs, limitations and next action. Stop on access failure or exhausted budget with In progress/Blocked, never Checked.',
  'Update journey.coverage.checks for streamId '+stream.id+' and month '+month+'. Fields: streamId, month, status (pending/in_progress/checked/empty/blocked/excluded), note, sourceRefs, cursor, found, read. Checked requires all selected records read, exhausted pagination, a receipt note and resolving source references. Empty requires an exhausted zero-result search and its exact scope in note. Excluded requires a reason. A month with some existing excerpts is not automatically checked.',
  'Run focused deepening and a contrary-evidence check on consequential gaps. Preserve the first wording and all review annotations. Retain evidence/corrections and refresh affected views; save a recoverable archive revision and return the updated HTML. Continue the next pending source/month within authorization and the remaining budget; hand back a checkpoint when stopping.'
 ].join('\n\n'),task,'Collection task copied. Give it and the saved private HTML to your coach.');});task.id='coverage-task';task.className='path-primary';actions.append(task);
 const editor=el('details',undefined,'coverage-receipt');editor.id='coverage-receipt-details';editor.open=coverageView.editing;editor.addEventListener('toggle',()=>{coverageView.editing=editor.open;});editor.append(el('summary','Receipt & scope'));
 if(stream.scope)editor.append(el('p',stream.scope,'coverage-scope-text'));
 const status=el('select');status.id='coverage-status';for(const [v,label]of Object.entries(coverageStatuses)){const o=el('option',label);o.value=v;status.append(o);}status.value=receipt.status;
 const note=el('textarea');note.id='coverage-note';note.rows=3;note.maxLength=2000;note.value=receipt.note;
 editor.append(field('Status on save',status),field('Search receipt or remaining gap',note));
 const counts=el('div',undefined,'coverage-fields'),found=input('number',receipt.found),read=input('number',receipt.read),cursor=input('text',receipt.cursor,1000);found.id='coverage-found';read.id='coverage-read';cursor.id='coverage-cursor';found.min=read.min=0;found.max=read.max=1000000;found.step=read.step=1;counts.append(field('Records found in scope',found),field('Records read',read));
 const refs=el('select');refs.id='coverage-refs';refs.multiple=true;refs.size=4;for(const s of packet.sources){const o=el('option',s.label);o.value=s.id;o.selected=receipt.sourceRefs.includes(s.id);refs.append(o);}
 editor.append(counts,field('Saved evidence (select any that support this receipt)',refs),field('Next page / continuation cursor',cursor));
 const fieldsReceipt=()=>({streamId:stream.id,month,status:status.value,note:note.value,sourceRefs:[...refs.selectedOptions].map(o=>o.value),cursor:cursor.value,found:Number(found.value),read:Number(read.value)});
 const saveDraft=()=>{
  const draft={...fieldsReceipt(),status:'in_progress'},next={...c,checks:[...c.checks.filter(x=>!(x.streamId===stream.id&&x.month===month)),draft]};
  const error=coverageError(next,packet);if(error){message.textContent=error;return;}
  c.checks=next.checks;state.coverage=c;changed('Receipt draft saved. Save check confirms the selected status.');
  message.textContent='';count.textContent=coverageSummary(c);
  const tile=grid.querySelector('#coverage-month-'+month);tile.dataset.status=draft.status;tile.setAttribute('aria-label',month+' · '+coverageStatuses[draft.status]);tile.querySelector('span').textContent=coverageStatuses[draft.status];
  const summary=inventory.querySelector('[data-coverage-stream="'+stream.id+'"]');if(summary)summary.textContent=sourceSummary(stream);
 };
 for(const control of [note,found,read,cursor])control.addEventListener('input',saveDraft);
 refs.addEventListener('change',saveDraft);
 editor.append(button('Save check',()=>{
  const item=fieldsReceipt();
  const next={...c,checks:[...c.checks.filter(x=>!(x.streamId===stream.id&&x.month===month)),item]};commit(next);
 },'coverage-save'));
 const nextButton=button('Next unchecked',()=>{
  const current=c.streams.flatMap(s=>months.map(m=>({stream:s.id,month:m}))),index=current.findIndex(x=>x.stream===stream.id&&x.month===month);
  const pending=[...current.slice(index+1),...current.slice(0,index+1)].find(x=>!c.checks.some(r=>r.streamId===x.stream&&r.month===x.month&&['checked','empty','excluded'].includes(r.status)));
  if(pending){Object.assign(coverageView,{...pending,year:pending.month.slice(0,4)});repaint('coverage-month-'+pending.month);}else message.textContent='Every source-month has a check or an explicit exclusion.';
 },'coverage-next');nextButton.setAttribute('aria-label','Next unchecked month');actions.append(nextButton);root.append(actions,editor);
 const sourceSummary=s=>s.platform+' · '+s.location+' — '+c.checks.filter(x=>x.streamId===s.id&&['checked','empty'].includes(x.status)).length+'/'+months.length+' checked';
 const inventory=el('details');inventory.append(el('summary','All source locations'));const list=el('ul');for(const s of c.streams){const item=el('li',sourceSummary(s));item.dataset.coverageStream=s.id;list.append(item);}inventory.append(list);setup.append(inventory);
}
