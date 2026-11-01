// Export is constructed from this allowlist. Never clone the private document.
function publicProjection(value){
 return {name:value.name,headline:value.headline,overview:value.overview,
  examples:value.examples.map(e=>({title:e.title,summary:e.summary,synthetic:e.synthetic}))};
}
function validPublicProfile(p){
 const text=(s,n)=>typeof s==='string'&&s.length<=n&&!s.includes('\0');
 return p&&/^[a-f0-9]{64}$/.test(p.contextSha256)&&Number.isSafeInteger(p.updatedAt)&&p.updatedAt>=0&&text(p.name,200)&&text(p.headline,200)&&text(p.overview,3000)&&Array.isArray(p.examples)&&p.examples.length<=8&&p.examples.every(e=>e&&text(e.title,200)&&text(e.summary,2000)&&typeof e.synthetic==='boolean');
}
function publicNode(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function publicArticle(value,synthetic=false){
 const p=publicProjection(value),article=publicNode('article',undefined,'profile-page');
 const header=publicNode('header',undefined,'public-intro'),intro=publicNode('div');
 intro.append(publicNode('h1',p.headline),publicNode('p',p.overview,'public-overview'));
 header.append(publicNode('p',p.name,'public-name'),intro);article.append(header);
 if(synthetic)article.append(publicNode('p','Synthetic demo data','public-synthetic'));
 const examples=publicNode('div',undefined,'public-examples');
 for(const e of p.examples){if(!e.title&&!e.summary)continue;const row=publicNode('article',undefined,'public-example'),body=publicNode('div');if(e.synthetic)body.append(publicNode('p','Synthetic example','public-synthetic'));body.append(publicNode('p',e.summary));row.append(publicNode('h2',e.title),body);examples.append(row);}
 article.append(examples);return article;
}
function publicDocument(value,synthetic=false){
 const p=publicProjection(value),doc=document.implementation.createHTMLDocument(p.name+' · Profile');
 doc.documentElement.lang='en';
 const charset=doc.createElement('meta');charset.setAttribute('charset','utf-8');doc.head.prepend(charset);
 const viewport=doc.createElement('meta');viewport.name='viewport';viewport.content='width=device-width, initial-scale=1';doc.head.append(viewport);
 const csp=doc.createElement('meta');csp.httpEquiv='Content-Security-Policy';csp.content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";doc.head.append(csp);
 const style=doc.createElement('style');style.textContent=document.getElementById('public-profile-styles').textContent;doc.head.append(style);
 doc.body.className='public-export';const main=doc.createElement('main');main.append(publicArticle(p,synthetic));doc.body.append(main);
 return '<!doctype html>\n'+doc.documentElement.outerHTML;
}
const publicRoot=document.getElementById('profile');
let renderPublicProfile=()=>{};
let savePublicProfile=()=>{};
if(publicRoot){
 const basis=publicRoot.dataset.evidence,storageKey='career-public:'+basis,status=document.getElementById('public-status');
 let value=packet.publicProfile;
 // The storage key identifies the current evidence. The draft fingerprint may
 // intentionally remain older, so its freshness reminder must survive edits.
 try{const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(validPublicProfile(saved)&&saved.updatedAt>value.updatedAt){value={...publicProjection(saved),contextSha256:saved.contextSha256,updatedAt:saved.updatedAt};packet.publicProfile=value;}}catch{}
 const editor=document.getElementById('public-editor'),preview=document.getElementById('public-preview');
 function ready(){return Boolean(value.name.trim()&&value.headline.trim()&&value.overview.trim());}
 savePublicProfile=(message='Saved in this browser. Save the private working file to keep your edits.')=>{
  value=packet.publicProfile;value.updatedAt=Date.now();
  try{localStorage.setItem(storageKey,JSON.stringify(value));status.textContent=message;}catch{status.textContent='Browser storage unavailable. Save the private working file to keep your edits.';}
  preview.replaceChildren(publicArticle(value,packet.synthetic));document.getElementById('public-export').disabled=!ready();document.getElementById('public-empty').hidden=ready();
 };
 function field(label,key,object,limit,rows){
  const wrap=publicNode('label',undefined,'public-field');wrap.append(publicNode('span',label));
  const input=publicNode(rows?'textarea':'input');input.value=object[key];input.maxLength=limit;input.setAttribute('aria-label',label);if(rows)input.rows=rows;else input.type='text';
  input.addEventListener('input',()=>{object[key]=input.value;savePublicProfile();});wrap.append(input);return wrap;
 }
 function editFields(){
  editor.replaceChildren(field('Name','name',value,200),field('Headline','headline',value,200),field('Overview','overview',value,3000,5));
  value.examples.forEach((example,index)=>{
   const group=publicNode('fieldset',undefined,'public-example-editor');group.append(publicNode('legend','Work example '+(index+1)),field('Example title','title',example,200),field('General overview','summary',example,2000,4));
   const options=publicNode('div',undefined,'public-example-options'),label=publicNode('label'),checkbox=publicNode('input');checkbox.type='checkbox';checkbox.checked=example.synthetic;checkbox.addEventListener('change',()=>{example.synthetic=checkbox.checked;savePublicProfile();});label.append(checkbox,document.createTextNode('Synthetic example'));
   const remove=publicNode('button','Remove','path-secondary');remove.type='button';remove.addEventListener('click',()=>{value.examples.splice(index,1);savePublicProfile();editFields();editor.querySelector('#public-add')?.focus();});options.append(label,remove);group.append(options);editor.append(group);
  });
  if(value.examples.length<8){const add=publicNode('button','Add work example','path-secondary');add.id='public-add';add.type='button';add.addEventListener('click',()=>{value.examples.push({title:'',summary:'',synthetic:false});savePublicProfile();editFields();editor.querySelectorAll('fieldset input[type=text]')[value.examples.length-1]?.focus();});editor.append(add);}
 }
 function setEdit(edit){editor.hidden=!edit;preview.hidden=edit;document.getElementById('public-preview-tab').setAttribute('aria-pressed',String(!edit));document.getElementById('public-edit-tab').setAttribute('aria-pressed',String(edit));if(edit)editFields();}
 renderPublicProfile=()=>{value=packet.publicProfile;preview.replaceChildren(publicArticle(value,packet.synthetic));document.getElementById('public-export').disabled=!ready();document.getElementById('public-empty').hidden=ready();if(!editor.hidden)editFields();};
 document.getElementById('public-edit-tab').onclick=()=>setEdit(true);
 document.getElementById('public-preview-tab').onclick=()=>setEdit(false);
 document.getElementById('public-save').onclick=()=>document.getElementById('save-html').click();
 document.getElementById('public-export').onclick=()=>{if(!ready())return;download('public-profile.html','text/html;charset=utf-8',publicDocument(value,packet.synthetic));status.textContent='Public profile download started. Private records are excluded.';};
 if(value.contextSha256!==basis)status.textContent='Your private context has changed. Check this profile against the current record.';
 renderPublicProfile();
 if(!ready())setEdit(true);
}
function snapshotPublicProfile(clone){
 if(!packet.publicProfile)return;
 clone.querySelector('#public-editor').replaceChildren();clone.querySelector('#public-editor').hidden=true;
 clone.querySelector('#public-preview').replaceChildren(publicArticle(packet.publicProfile,packet.synthetic));clone.querySelector('#public-preview').hidden=false;
 clone.querySelector('#public-preview-tab').setAttribute('aria-pressed','true');clone.querySelector('#public-edit-tab').setAttribute('aria-pressed','false');clone.querySelector('#public-status').textContent='';
}
