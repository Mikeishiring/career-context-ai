// Edit the portable packet. Accounts and their source IDs stay in place.
function editExperience() {
 const existing = packet.presentation?.experienceRoles || [];
 const roles = structuredClone(existing);
 const dialog = document.createElement('dialog');
 dialog.className = 'experience-editor';
 dialog.setAttribute('aria-labelledby','experience-editor-title');
 dialog.innerHTML = '<form><header><h2 id="experience-editor-title">Edit work experience</h2><button type="button" data-close>Cancel</button></header><div class="experience-inputs"></div><button type="button" data-add>Add role or engagement</button><fieldset class="experience-assign"><legend>Work examples</legend></fieldset><footer><span>Open the downloaded HTML to keep editing or continue with your AI.</span><button class="path-primary" type="submit">Save private HTML</button></footer><p role="status" data-error></p></form>';
 const form = dialog.querySelector('form'), inputs = dialog.querySelector('.experience-inputs');
 const assignments = dialog.querySelector('.experience-assign'), selectors = new Map();
 const add = dialog.querySelector('[data-add]'), error = dialog.querySelector('[data-error]');
 const text = (tag,value) => {const n=document.createElement(tag);n.textContent=value;return n;};
 if(packet.journey){
  const ai=text('button','Save for AI review');ai.type='submit';ai.value='ai';
  dialog.querySelector('footer').insertBefore(ai,dialog.querySelector('footer button'));
 }
 function refreshChoices() {
  for(const select of selectors.values()){
   const selected=select.value;
   select.replaceChildren(new Option('No role assigned',''));
   for(const r of roles)select.add(new Option([r.title || 'Untitled role',r.organization,r.period].filter(Boolean).join(' · '),r.id));
   select.value=roles.some(r=>r.id===selected)?selected:'';
  }
  add.disabled=roles.length>=80;
 }
 let uploads=0;
 function roleFields(role) {
  const row=document.createElement('fieldset');row.className='experience-fields';
  function field(label,key) {
   const wrap=text('label',label), input=document.createElement('input');
   input.value=role[key]||'';input.maxLength=160;input.required=key==='title';
   input.addEventListener('input',()=>{role[key]=input.value;refreshChoices();});
   wrap.append(input);row.append(wrap);
  }
  row.append(text('legend','Role or engagement'));
  field('Role or type of work','title');field('Organization or client (optional)','organization');field('Dates (optional)','period');
  const current=document.createElement('input');current.type='checkbox';current.checked=Boolean(role.current);
  current.onchange=()=>{role.current=current.checked;};
  const active=document.createElement('label');active.className='role-current';active.append(current,' Current role');row.append(active);
  const logoLabel=text('label','Logo (optional)'),file=document.createElement('input');
  file.type='file';file.accept='image/png,image/jpeg,image/webp';logoLabel.append(file);row.append(logoLabel);
  const clear=text('button','Remove logo');clear.type='button';clear.hidden=!role.logo;
  clear.onclick=()=>{delete role.logo;file.value='';clear.hidden=true;};
  file.onchange=async()=>{
   const upload=file.files[0];if(!upload)return;
   error.textContent='';file.disabled=true;clear.disabled=true;uploads++;
   try{
    if(!['image/png','image/jpeg','image/webp'].includes(upload.type)||upload.size>8*1024*1024)throw Error();
    const bitmap=await createImageBitmap(upload);
    try{
     const canvas=document.createElement('canvas'),scale=Math.min(1,96/Math.max(bitmap.width,bitmap.height));
     canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
     canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);role.logo=canvas.toDataURL('image/png');
    }finally{bitmap.close();}
    clear.hidden=false;
   }catch{error.textContent='Choose a PNG, JPEG or WebP image under 8 MB.';file.value='';}
   finally{file.disabled=false;clear.disabled=false;uploads--;}
  };
  const remove=text('button','Remove role');remove.type='button';
  remove.onclick=()=>{roles.splice(roles.indexOf(role),1);row.remove();refreshChoices();add.focus();};
  const actions=document.createElement('div');actions.className='role-row-actions';actions.append(clear,remove);row.append(actions);inputs.append(row);
  return row;
 }
 add.onclick=()=>{
  const role={id:'role-'+crypto.randomUUID(),title:'',accountIds:[]};roles.push(role);
  const row=roleFields(role);refreshChoices();row.querySelector('input').focus();
 };
 for(const r of roles)roleFields(r);
 for(const a of packet.accounts){
  const label=text('label',a.title),select=document.createElement('select');
  label.append(select);assignments.append(label);selectors.set(a.id,select);
 }
 assignments.hidden=!selectors.size;refreshChoices();
 for(const r of roles)for(const id of r.accountIds)selectors.get(id).value=r.id;
 function close(){dialog.close();dialog.remove();document.getElementById('edit-experience').focus();}
 dialog.querySelector('[data-close]').onclick=close;
 dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
 form.onsubmit=event=>{
  event.preventDefault();
  if(uploads){error.textContent='Wait for the logo to finish loading.';return;}
  for(const r of roles){
   r.title=r.title.trim();
   if(!r.title){error.textContent='Give each role a title or remove it.';return;}
   const original=existing.find(x=>x.id===r.id);
   const assigned=[...selectors].filter(([,select])=>select.value===r.id).map(([id])=>id);
   r.accountIds=[...r.accountIds.filter(id=>assigned.includes(id)),...assigned.filter(id=>!r.accountIds.includes(id))];
   const changed=!original||['title','organization','period','current'].some(k=>r[k]!==original[k]);
   if(changed)delete r.sourceRefs;
   if(changed||r.accountIds.join()!==original.accountIds.join())r.personEdited=true;
  }
  const presentation={...packet.presentation,experienceRoles:roles};
  if(new TextEncoder().encode(JSON.stringify({...packet,presentation})).length>24*1024*1024){
   error.textContent='This file is full. Remove a logo before saving.';return;
  }
  packet.presentation=presentation;
  renderExperienceRoles(roles);
  close();
  const status=document.getElementById('experience-status');
  status.textContent='';
  if(event.submitter?.value==='ai'){
   window.dispatchEvent(new CustomEvent('career-output-request',{detail:{kind:'custom',accountId:'',
    direction:'Organize My context by role or engagement using the authorized records in this file. Preserve my edits in presentation.experienceRoles. Find supported titles, organizations, dates and the examples that belong under each role. Distinguish clients from employers and parallel work from promotions. Leave unclear assignments open and ask only if the distinction matters. Return an updated private HTML I can edit.'}}));
   status.textContent='Attach the downloaded private HTML to your AI to review the role groupings.';
  }else{saveFullHtml(packet);status.textContent='Open the downloaded private HTML to continue with these edits.';}
 };
 document.body.append(dialog);dialog.showModal();
}

function renderExperienceRoles(roles) {
 const host=document.getElementById('experience-groups');
 const files=new Map([...host.querySelectorAll('[data-experience]')].map(n=>[n.dataset.experience,n.closest('li')]));
 const fragment=document.createDocumentFragment();
 function group(ids,role) {
  const section=document.createElement('section'),list=document.createElement('ol');
  section.className=role?'experience-role':'ungrouped-experience';
  if(role){
   const header=document.createElement('header'),mark=document.createElement('span'),info=document.createElement('div');
   header.className='experience-role-heading';mark.className='role-mark';mark.setAttribute('aria-hidden','true');
   if(role.logo){const img=new Image();img.src=role.logo;img.alt='';mark.append(img);}
   else mark.textContent=(role.organization||role.title).trim().split(/\s+/).slice(0,2).map(w=>w[0].toUpperCase()).join('');
   const title=document.createElement('h3'),meta=document.createElement('p');title.textContent=role.title;
   meta.textContent=[role.organization,role.period,role.current?'Current':''].filter(Boolean).join(' · ');
   info.append(title,meta);header.append(mark,info);section.append(header);
  }else if(roles.length){const h=document.createElement('h3');h.textContent='Other work';section.append(h);}
  for(const id of ids){const row=files.get(id);if(row){list.append(row);files.delete(id);}}
  section.append(list);fragment.append(section);
 }
 for(const r of [...roles].sort((a,b)=>Number(!!b.current)-Number(!!a.current)))group(r.accountIds,r);
 if(files.size)group(packet.accounts.map(a=>a.id).filter(id=>files.has(id)),null);
 host.replaceChildren(fragment);
 document.getElementById('experience-heading').textContent=roles.length?'Work experience':'Work examples';
}
document.getElementById('edit-experience')?.addEventListener('click',editExperience);
