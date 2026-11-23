// Preview the exact retained artifact, without a duplicate image payload in the file.
for(const preview of document.querySelectorAll('[data-studio-image]')){
 const original=document.getElementById(preview.dataset.studioImage);
 if(original?.getAttribute('src')?.startsWith('data:image/'))preview.src=original.src;
 else preview.closest('.studio-preview').hidden=true;
}
const studioDialog=document.getElementById('studio-request');
if(studioDialog){
 let studioOpener;
 const kind=document.getElementById('studio-kind'),direction=document.getElementById('studio-direction');
 function updateRequestField(){
  const custom=kind.value==='custom';
  direction.required=custom;
  direction.setCustomValidity('');
  document.getElementById('studio-direction-label').textContent=custom?'What would you like help with?':'Audience or role';
  document.getElementById('studio-optional').hidden=custom;
 }
 kind.addEventListener('change',updateRequestField);
 direction.addEventListener('input',()=>direction.setCustomValidity(''));
 for(const button of document.querySelectorAll('[data-studio-kind]'))button.addEventListener('click',()=>{
  studioOpener=button;kind.value=button.dataset.studioKind;updateRequestField();
  document.getElementById('studio-status').textContent='';studioDialog.showModal();
 });
 document.getElementById('studio-close').addEventListener('click',()=>studioDialog.close());
 studioDialog.addEventListener('close',()=>studioOpener?.focus());
 document.getElementById('studio-request-form').addEventListener('submit',event=>{
  event.preventDefault();
  if(kind.value==='custom'&&!direction.value.trim()){
   direction.setCustomValidity('Enter your request.');direction.reportValidity();return;
  }
  window.dispatchEvent(new CustomEvent('career-output-request',{detail:{
   kind:document.getElementById('studio-kind').value,
   accountId:document.getElementById('studio-account').value,
   direction:document.getElementById('studio-direction').value
  }}));
 });
}
