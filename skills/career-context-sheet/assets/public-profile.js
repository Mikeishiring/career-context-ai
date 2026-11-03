// Export is constructed from this allowlist. Never clone the private document.
function publicVideoUrl(value,allowAccessTokens=false){
 if(typeof value!=='string'||!value.startsWith('https://')||/[\s\\\x00-\x1f\x7f]/.test(value))return false;
 try{const u=new URL(value),privateKeys=new Set(['access_token','token','auth','authorization','api_key','apikey','signature','sig','x-amz-credential','x-amz-signature','x-goog-credential','x-goog-signature','key-pair-id']);return Boolean(u.hostname&&!u.username&&!u.password&&(allowAccessTokens||![...u.searchParams.keys(),...new URLSearchParams(u.hash.slice(1)).keys()].some(k=>privateKeys.has(k.toLowerCase()))));}catch{return false;}
}
function publicImageSize(value){
 if(typeof value!=='string'||value.length>2800000)return -1;
 const m=value.match(/^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$/);if(!m||m[2].length%4)return -1;
 try{const raw=atob(m[2]),valid=m[1]==='png'?raw.startsWith('\x89PNG\r\n\x1a\n'):m[1]==='jpeg'?raw.startsWith('\xff\xd8\xff'):raw.startsWith('RIFF')&&raw.slice(8,12)==='WEBP';return valid&&raw.length<=2097152?raw.length:-1;}catch{return -1;}
}
// Match the Python public boundary. Keep private originals; re-import to re-encode.
function publicImageShareable(value){
 if(publicImageSize(value)<0)return false;
 const raw=atob(value.slice(value.indexOf(',')+1)),byte=i=>raw.charCodeAt(i);
 const uint=(i,little=false)=>little?byte(i)+byte(i+1)*256+byte(i+2)*65536+byte(i+3)*16777216:byte(i)*16777216+byte(i+1)*65536+byte(i+2)*256+byte(i+3);
 if(raw.startsWith('\x89PNG')){
  let pos=8,pixels=false,header=false;
  const fixed={IHDR:13,IEND:0,sRGB:1,gAMA:4,cHRM:32,pHYs:9},allowed=new Set([...Object.keys(fixed),'PLTE','tRNS','IDAT']);
  while(pos+12<=raw.length){
   const size=uint(pos),kind=raw.slice(pos+4,pos+8),end=pos+size+12;
   if(end>raw.length||!allowed.has(kind)||!header&&kind!=='IHDR'||kind in fixed&&size!==fixed[kind])return false;
   if(kind==='IHDR'){if(header)return false;header=true;}
   if(kind==='PLTE'&&(!size||size>768||size%3)||kind==='tRNS'&&size>256)return false;
   if(kind==='IDAT')pixels=true;
   if(kind==='IEND')return pixels&&end===raw.length;
   pos=end;
  }
  return false;
 }
 if(raw.startsWith('RIFF')){
  if(uint(4,true)+8!==raw.length)return false;
  let pos=12,pixels=false;
  while(pos+8<=raw.length){
   const kind=raw.slice(pos,pos+4),size=uint(pos+4,true),end=pos+8+size+size%2;
   if(end>raw.length||!['VP8 ','VP8L','VP8X','ALPH'].includes(kind))return false;
   if(kind==='VP8X'&&(size!==10||byte(pos+8)&0x2e))return false;
   if(kind==='VP8 '||kind==='VP8L')pixels=true;
   pos=end;
  }
  return pixels&&pos===raw.length;
 }
 let pos=2,pixels=false;
 while(pos<raw.length){
  if(byte(pos)!==255)return false;
  while(pos<raw.length&&byte(pos)===255)pos++;
  if(pos>=raw.length)return false;
  const marker=byte(pos++);
  if(marker===0xd9)return pixels&&pos===raw.length;
  if(![0xc0,0xc2,0xc4,0xdb,0xdd,0xda,0xe0].includes(marker)||pos+2>raw.length)return false;
  const size=byte(pos)*256+byte(pos+1),end=pos+size;
  if(size<2||end>raw.length)return false;
  if(marker===0xe0&&(size!==16||raw.slice(pos+2,pos+7)!=='JFIF\0'||raw.slice(end-2,end)!=='\0\0'))return false;
  pos=end;
  if(marker===0xda){
   pixels=true;
   while(pos<raw.length){
    if(byte(pos)!==255){pos++;continue;}
    if(pos+1>=raw.length)return false;
    if(byte(pos+1)===0||byte(pos+1)>=0xd0&&byte(pos+1)<=0xd7){pos+=2;continue;}
    break;
   }
  }
 }
 return false;
}
function publicMediaIssue(m){
 if(!m.title?.trim())return 'Add a title in Edit';
 if(m.kind==='image')return !m.alt?.trim()?'Add an image description in Edit':publicImageSize(m.dataUrl)<0?'Replace the image in Edit':!publicImageShareable(m.dataUrl)?'Re-add the screenshot to remove metadata':'';
 return publicVideoUrl(m.url)?'':m.url?.trim()?'Fix the link in Edit':'Add a link in Edit';
}
function publicMediaReady(m){return !publicMediaIssue(m);}
function publicMediaDraft(items){return (items||[]).map(m=>({id:m.id,kind:m.kind,title:m.title,caption:m.caption,credit:m.credit,included:m.included===true,...(m.kind==='image'?{alt:m.alt,dataUrl:m.dataUrl}:{url:m.url})}));}
function publicMediaProjection(items){return publicMediaDraft(items).filter(m=>m.included&&publicMediaReady(m)).map(({id,included,...m})=>m);}
function validPublicMedia(items){
 if(!Array.isArray(items)||items.length>8)return false;
 const ids=new Set();let total=0;const text=(s,n)=>typeof s==='string'&&s.length<=n&&!s.includes('\0');
 for(const m of items){if(!m||typeof m.id!=='string'||!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$/.test(m.id)||ids.has(m.id)||!['image','video'].includes(m.kind)||typeof m.included!=='boolean'||!text(m.title,200)||!text(m.caption,1000)||!text(m.credit,500))return false;ids.add(m.id);
  if(m.kind==='image'){const bytes=publicImageSize(m.dataUrl);if(bytes<0||!text(m.alt,500)||'url' in m)return false;total+=bytes;}
  else if(!text(m.url,2000)||'dataUrl' in m||'alt' in m)return false;
  // Legacy metadata-bearing originals remain recoverable, but cannot be shared.
  if(m.included&&(!m.title.trim()||(m.kind==='image'?!m.alt.trim():!publicVideoUrl(m.url,true))))return false;
 }
 return total<=6291456;
}
function publicProjection(value){
 return {name:value.name,headline:value.headline,overview:value.shareOverview===true?value.overview:'',direction:value.shareDirection===true?(value.direction||''):'',northStar:value.shareNorthStar===true?(value.northStar||''):'',media:publicMediaProjection(value.media),
  examples:value.examples.filter(e=>e.included===true).map(e=>({title:e.title,summary:e.summary,synthetic:e.synthetic,detail:e.shareDetail===true?(e.detail||''):''})),
  timeline:(value.timeline||[]).filter(e=>e.included===true).map(e=>({period:e.period,title:e.title,summary:e.summary}))};
}
// Private persistence retains withheld drafts; the export projection must not be used here.
function publicDraft(value){return {name:value.name,headline:value.headline,overview:value.overview,contextSha256:value.contextSha256,updatedAt:value.updatedAt,shareOverview:value.shareOverview===true,direction:value.direction||'',shareDirection:value.shareDirection===true,northStar:value.northStar||'',shareNorthStar:value.shareNorthStar===true,media:publicMediaDraft(value.media),
 examples:value.examples.map(e=>({title:e.title,summary:e.summary,synthetic:e.synthetic,included:e.included===true,detail:e.detail||'',shareDetail:e.shareDetail===true})),
 timeline:(value.timeline||[]).map(e=>({period:e.period,title:e.title,summary:e.summary,included:e.included===true}))};}
function movePublicPeriod(value,index,step){
 const items=value.timeline,target=index+step;
 if(!Array.isArray(items)||!Number.isInteger(index)||![-1,1].includes(step)||index<0||index>=items.length||target<0||target>=items.length)return -1;
 const [entry]=items.splice(index,1);items.splice(target,0,entry);return target;
}
function validPublicProfile(p){
 const text=(s,n)=>typeof s==='string'&&s.length<=n&&!s.includes('\0');
 if(!p||!Array.isArray(p.examples)||(p.timeline!==undefined&&!Array.isArray(p.timeline)))return false;
 if(!validPublicMedia(p.media||[])||(p.northStar!==undefined&&!text(p.northStar,1000))||(p.shareNorthStar!==undefined&&typeof p.shareNorthStar!=='boolean'))return false;
 if((p.direction!==undefined&&!text(p.direction,1500))||(p.shareDirection!==undefined&&typeof p.shareDirection!=='boolean')||p.examples.some(e=>e&&(e.detail!==undefined&&!text(e.detail,2500)||e.shareDetail!==undefined&&typeof e.shareDetail!=='boolean')))return false;
 if(p.shareOverview!==undefined&&typeof p.shareOverview!=='boolean'||[...(p.examples||[]),...(p.timeline||[])].some(e=>e?.included!==undefined&&typeof e.included!=='boolean'))return false;
 return p&&/^[a-f0-9]{64}$/.test(p.contextSha256)&&Number.isSafeInteger(p.updatedAt)&&p.updatedAt>=0&&text(p.name,200)&&text(p.headline,200)&&text(p.overview,3000)&&Array.isArray(p.examples)&&p.examples.length<=8&&p.examples.every(e=>e&&text(e.title,200)&&text(e.summary,2000)&&typeof e.synthetic==='boolean')&&(p.timeline===undefined||Array.isArray(p.timeline)&&p.timeline.length<=30&&p.timeline.every(e=>e&&text(e.period,60)&&text(e.title,200)&&text(e.summary,1500)));
}
function publicNode(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function publicMediaArticle(items){
 const section=publicNode('section',undefined,'public-media'),gallery=publicNode('div',undefined,'public-gallery');section.append(publicNode('h2','Work samples'),gallery);
 for(const m of items){let item;
  if(m.kind==='image'){item=publicNode('article',undefined,'public-visual');const detail=publicNode('details'),summary=publicNode('summary'),thumb=publicNode('img'),full=publicNode('div',undefined,'public-full-image'),img=publicNode('img');thumb.src=img.src=m.dataUrl;thumb.alt=img.alt=m.alt;thumb.loading=img.loading='lazy';full.tabIndex=0;full.setAttribute('role','region');full.setAttribute('aria-label','Full size screenshot');full.append(img);summary.append(thumb,publicNode('span',m.title),publicNode('span','View full size','public-enlarge'),publicNode('span','Close full size','public-enlarge public-close')); detail.append(summary,full);item.append(detail);}
  else{item=publicNode('article',undefined,'public-video');const link=publicNode('a',m.title+' ↗');link.href=m.url;link.target='_blank';link.rel='noopener noreferrer';item.append(link,publicNode('span',new URL(m.url).hostname,'public-video-host'));}
  if(m.caption)item.append(publicNode('p',m.caption));if(m.credit)item.append(publicNode('p',m.credit,'public-media-credit'));gallery.append(item);
 }
 return section;
}
function publicArticle(value,synthetic=false){
 const p=publicProjection(value),article=publicNode('article',undefined,'profile-page');
 const header=publicNode('header',undefined,'public-intro'),intro=publicNode('div');
 intro.append(publicNode('h1',p.headline),publicNode('p',p.overview,'public-overview'));
 header.append(publicNode('p',p.name,'public-name'),intro);article.append(header);
 if(synthetic)article.append(publicNode('p','Synthetic demo data','public-synthetic'));
 for(const [key,label] of [['northStar','North Star'],['direction','Direction']])if(p[key]){const direction=publicNode('section',undefined,'public-direction');direction.append(publicNode('h2',label),publicNode('p',p[key]));article.append(direction);}
 const examples=publicNode('div',undefined,'public-examples');
 for(const e of p.examples){if(!e.title&&!e.summary)continue;const row=publicNode('article',undefined,'public-example'),body=publicNode('div');if(e.synthetic)body.append(publicNode('p','Synthetic example','public-synthetic'));body.append(publicNode('p',e.summary));if(e.detail){const detail=publicNode('details',undefined,'public-detail');detail.append(publicNode('summary','More context'),publicNode('p',e.detail));body.append(detail);}row.append(publicNode('h2',e.title),body);examples.append(row);}
 article.append(examples);
 if(p.media.length)article.append(publicMediaArticle(p.media));
 if(p.timeline.some(e=>e.period||e.title||e.summary)){
  const section=publicNode('section',undefined,'public-timeline'),list=publicNode('div');section.append(publicNode('h2','Over time'),list);
  for(const e of p.timeline){if(!e.period&&!e.title&&!e.summary)continue;const row=publicNode('details',undefined,'public-year'),summary=publicNode('summary'),mark=publicNode('span','+');mark.setAttribute('aria-hidden','true');summary.append(publicNode('span',e.period),publicNode('strong',e.title),mark);row.append(summary,publicNode('p',e.summary));list.append(row);}
  article.append(section);
 }
 return article;
}
function publicDocument(value,synthetic=false){
 const p=publicProjection(value),doc=document.implementation.createHTMLDocument(p.name+' · Profile');
 doc.documentElement.lang='en';
 const charset=doc.createElement('meta');charset.setAttribute('charset','utf-8');doc.head.prepend(charset);
 const viewport=doc.createElement('meta');viewport.name='viewport';viewport.content='width=device-width, initial-scale=1';doc.head.append(viewport);
 const csp=doc.createElement('meta');csp.httpEquiv='Content-Security-Policy';csp.content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";doc.head.append(csp);
 const style=doc.createElement('style');style.textContent=document.getElementById('public-profile-styles').textContent;doc.head.append(style);
 doc.body.className='public-export';const main=doc.createElement('main');main.append(publicArticle(value,synthetic));doc.body.append(main);
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
 try{const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(validPublicProfile(saved)&&saved.updatedAt>value.updatedAt){value=publicDraft(saved);packet.publicProfile=value;}}catch{}
 const editor=document.getElementById('public-editor'),preview=document.getElementById('public-preview');
 function ready(){const p=publicProjection(value);return Boolean(p.name.trim()&&p.headline.trim()&&(p.overview.trim()||p.direction.trim()||p.northStar.trim()||p.media.length||p.examples.some(e=>e.title.trim()||e.summary.trim())||p.timeline.some(e=>e.period.trim()||e.title.trim()||e.summary.trim())));}
 function shareCount(){const p=publicProjection(value);document.getElementById('public-share-count').textContent=(Number(Boolean(p.overview.trim()))+Number(Boolean(p.direction.trim()))+Number(Boolean(p.northStar.trim()))+p.media.length+p.examples.filter(e=>e.title.trim()||e.summary.trim()).length+p.examples.filter(e=>e.detail.trim()).length+p.timeline.filter(e=>e.period.trim()||e.title.trim()||e.summary.trim()).length)+' selected';for(const [i,e] of value.examples.entries()){const input=document.getElementById('share-detail-'+i);if(input)input.disabled=e.included!==true;}}
 function sharingFields(){
  const host=document.getElementById('public-sharing');host.replaceChildren();
  function group(title){const fieldset=publicNode('fieldset',undefined,'public-sharing-group');fieldset.append(publicNode('legend',title));host.append(fieldset);return fieldset;}
  function toggle(parent,label,object,key,id){const row=publicNode('label'),input=publicNode('input');input.type='checkbox';input.id=id;input.checked=object[key]===true;input.addEventListener('change',()=>{object[key]=input.checked;savePublicProfile();});row.append(input,publicNode('span',label));parent.append(row);return input;}
  const about=group('About');
  toggle(about,'Overview',value,'shareOverview','share-overview');
  if(value.northStar?.trim())toggle(about,'North Star',value,'shareNorthStar','share-north-star');
  if(value.direction?.trim())toggle(about,'Direction',value,'shareDirection','share-direction');
  if(value.examples.length){const work=group('Work');value.examples.forEach((e,i)=>{const example=publicNode('div',undefined,'public-sharing-example');toggle(example,e.title||'Work example '+(i+1),e,'included','share-example-'+i);if(e.detail?.trim())toggle(example,'More context',e,'shareDetail','share-detail-'+i).setAttribute('aria-label','More context: '+(e.title||'Example '+(i+1)));work.append(example);});}
  if(value.timeline?.length){const periods=group('Progression');value.timeline.forEach((e,i)=>toggle(periods,[e.period,e.title].filter(Boolean).join(' · ')||'Period '+(i+1),e,'included','share-year-'+i));}
  if(value.media?.length){const samples=group('Work samples');value.media.forEach((m,i)=>{const issue=publicMediaIssue(m),label=(m.kind==='image'?'Screenshot: ':'Video: ')+(m.title||'Untitled')+(issue?' · '+issue:'');const input=toggle(samples,label,m,'included','share-media-'+i);input.disabled=Boolean(issue);if(issue)input.checked=false;});}
  shareCount();
 }
 function refreshFreshness(){document.getElementById('public-freshness').hidden=value.contextSha256===basis;document.getElementById('public-mark-reviewed').disabled=!ready();}
 savePublicProfile=(message='Saved in this browser. Save the private working file to keep your edits.')=>{
  value=packet.publicProfile;value.updatedAt=Date.now();
  for(const m of value.media||[])if(!publicMediaReady(m))m.included=false;
  try{localStorage.setItem(storageKey,JSON.stringify(value));status.textContent=message;}catch{status.textContent='Browser storage unavailable. Save the private working file to keep your edits.';}
  preview.replaceChildren(publicArticle(value,packet.synthetic));document.getElementById('public-export').disabled=!ready();document.getElementById('public-empty').hidden=ready();
  refreshFreshness();shareCount();
 };
 function field(label,key,object,limit,rows){
  const wrap=publicNode('label',undefined,'public-field');wrap.append(publicNode('span',label));
  const input=publicNode(rows?'textarea':'input');input.value=object[key]||'';input.maxLength=limit;input.setAttribute('aria-label',label);if(rows)input.rows=rows;else input.type=key==='url'?'url':'text';
  const error=key==='url'?publicNode('span',undefined,'public-field-error'):null;
  function refreshError(){
   if(!error)return;const invalid=Boolean(input.value&&!publicVideoUrl(input.value));
   input.setAttribute('aria-invalid',String(invalid));error.hidden=!invalid;
   error.textContent=invalid?'Use a public HTTPS video link without credentials or access tokens. This link is not selected.':'';
  }
  input.addEventListener('input',()=>{object[key]=input.value;savePublicProfile();sharingFields();refreshError();});wrap.append(input);
  if(error){error.id='public-url-error-'+object.id;error.setAttribute('aria-live','polite');input.setAttribute('aria-describedby',error.id);wrap.append(error);refreshError();}
  return wrap;
 }
 async function importScreenshot(file){
  if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>2097152)throw Error('Choose a PNG, JPEG or WebP screenshot up to 2 MiB.');
  const inputUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('This image could not be read. Choose another screenshot.'));reader.readAsDataURL(file);}),img=new Image();
  try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('This image could not be read. Choose another screenshot.'));img.src=inputUrl;});
   if(img.naturalWidth*img.naturalHeight>16000000)throw Error('Choose a screenshot under 16 megapixels.');
   // Decode and re-encode the selected copy to omit file metadata. Keep the original untouched.
   const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;canvas.getContext('2d').drawImage(img,0,0);let dataUrl=canvas.toDataURL(file.type,.95);
   // Some browsers attach ICC profiles to JPEG/WebP encodings. PNG fallback
   // keeps the decoded pixels without copying those opaque metadata blocks.
   if(!publicImageShareable(dataUrl))dataUrl=canvas.toDataURL('image/png');
   if(!publicImageShareable(dataUrl))throw Error('This browser could not create a metadata-free image. Choose another screenshot.');
   const bytes=publicImageSize(dataUrl),used=(value.media||[]).filter(m=>m.kind==='image').reduce((n,m)=>n+publicImageSize(m.dataUrl),0);
   if(bytes<0||used+bytes>6291456)throw Error('Screenshots must be up to 2 MiB each and 6 MiB in total after import. Choose a smaller image.');
   if(value.media.length>=8)throw Error('Keep up to eight work samples.');
   value.media.push({id:'image-'+Date.now()+'-'+Math.random().toString(36).slice(2,8),kind:'image',title:'Screenshot',alt:'Screenshot of the work',caption:'',credit:'',dataUrl,included:false});
   savePublicProfile('Screenshot added. Check the image and its description, then select it to share.');editFields();
  }finally{img.removeAttribute('src');}
 }
 function mediaFields(){
  const bar=publicNode('div',undefined,'public-media-actions');bar.append(publicNode('h3','Work samples','public-editor-heading'));
  const message=publicNode('p',undefined,'public-media-status');message.id='public-media-status';message.setAttribute('role','status');
  if(value.media.length<8){const upload=publicNode('input');upload.type='file';upload.accept='image/png,image/jpeg,image/webp';upload.hidden=true;upload.id='public-image-file';upload.setAttribute('aria-label','Screenshot file');
   const addImage=publicNode('button','Add screenshot','path-secondary');addImage.type='button';addImage.onclick=()=>upload.click();upload.onchange=async()=>{addImage.disabled=true;message.textContent='Reading screenshot…';try{await importScreenshot(upload.files[0]);}catch(error){message.textContent=error.message;}finally{addImage.disabled=false;upload.value='';}};
   const addVideo=publicNode('button','Add video link','path-secondary');addVideo.type='button';addVideo.onclick=()=>{value.media.push({id:'video-'+Date.now(),kind:'video',title:'Video',caption:'',credit:'',url:'',included:false});savePublicProfile();editFields();[...editor.querySelectorAll('input[aria-label="Video URL"]')].at(-1)?.focus();};bar.append(addImage,addVideo,upload);
  }
  editor.append(bar,message);
  value.media.forEach((m,i)=>{const group=publicNode('fieldset',undefined,'public-media-editor');group.append(publicNode('legend',(m.kind==='image'?'Screenshot ':'Video ')+(i+1)));
   if(m.kind==='image'){const img=publicNode('img',undefined,'public-editor-thumb');img.src=m.dataUrl;img.alt=m.alt;group.append(img);}
   group.append(field('Sample title','title',m,200));
   if(m.kind==='image')group.append(field('Image description','alt',m,500));else group.append(field('Video URL','url',m,2000));
   group.append(field('Caption — context or limits','caption',m,1000,2),field('Credit / contribution','credit',m,500));
   const remove=publicNode('button','Remove sample','path-secondary');remove.type='button';remove.onclick=()=>{value.media.splice(i,1);savePublicProfile();editFields();editor.querySelector('.public-media-actions button')?.focus();};group.append(remove);editor.append(group);
  });
 }
 function editFields(){
  value.timeline=value.timeline||[];
  value.media=value.media||[];
  editor.replaceChildren(field('Name','name',value,200),field('Headline','headline',value,200),field('Overview','overview',value,3000,5),field('North Star — what you work towards','northStar',value,1000,2),field('Direction — what you want next','direction',value,1500,3));
  value.examples.forEach((example,index)=>{
   const group=publicNode('fieldset',undefined,'public-example-editor');group.append(publicNode('legend','Work example '+(index+1)),field('Example title','title',example,200),field('General overview','summary',example,2000,4),field('More context — decision, result and limits','detail',example,2500,4));
   const options=publicNode('div',undefined,'public-example-options'),label=publicNode('label'),checkbox=publicNode('input');checkbox.type='checkbox';checkbox.checked=example.synthetic;checkbox.addEventListener('change',()=>{example.synthetic=checkbox.checked;savePublicProfile();});label.append(checkbox,document.createTextNode('Synthetic example'));
   const remove=publicNode('button','Remove','path-secondary');remove.type='button';remove.addEventListener('click',()=>{value.examples.splice(index,1);savePublicProfile();editFields();editor.querySelector('#public-add')?.focus();});options.append(label,remove);group.append(options);editor.append(group);
  });
  if(value.examples.length<8){const add=publicNode('button','Add work example','path-secondary');add.id='public-add';add.type='button';add.addEventListener('click',()=>{value.examples.push({title:'',summary:'',synthetic:false,included:false});savePublicProfile();editFields();editor.querySelectorAll('fieldset input[type=text]')[value.examples.length-1]?.focus();});editor.append(add);}
  mediaFields();
  const timelineHeading=publicNode('h3','Progression');timelineHeading.className='public-editor-heading';editor.append(timelineHeading);
  value.timeline.forEach((entry,index)=>{
   const group=publicNode('fieldset',undefined,'public-year-editor');group.append(publicNode('legend','Period '+(index+1)),field('Year or period','period',entry,60),field('What changed','title',entry,200),field('Public overview','summary',entry,1500,3));
   const actions=publicNode('div',undefined,'public-period-actions');
   for(const [step,direction] of [[-1,'up'],[1,'down']]){
    const move=publicNode('button','Move '+direction,'path-secondary');move.type='button';move.id='public-year-'+direction+'-'+index;
    move.disabled=index+step<0||index+step>=value.timeline.length;move.setAttribute('aria-label','Move period '+(index+1)+' '+direction);
    move.addEventListener('click',()=>{
     const target=movePublicPeriod(value,index,step);if(target<0)return;
     savePublicProfile();editFields();
     const next=document.getElementById('public-year-'+direction+'-'+target),opposite=document.getElementById('public-year-'+(step<0?'down':'up')+'-'+target);
     (next.disabled?opposite:next).focus();
    });actions.append(move);
   }
   const remove=publicNode('button','Remove period','path-secondary');remove.type='button';remove.addEventListener('click',()=>{value.timeline.splice(index,1);savePublicProfile();editFields();document.getElementById('public-add-year')?.focus();});actions.append(remove);group.append(actions);editor.append(group);
  });
  if(value.timeline.length<30){const add=publicNode('button','Add period','path-secondary');add.id='public-add-year';add.type='button';add.addEventListener('click',()=>{value.timeline.push({period:'',title:'',summary:'',included:false});savePublicProfile();editFields();editor.querySelectorAll('.public-year-editor input')[2*(value.timeline.length-1)]?.focus();});editor.append(add);}
  sharingFields();
 }

 function setEdit(edit){editor.hidden=!edit;preview.hidden=edit;document.getElementById('public-preview-tab').setAttribute('aria-pressed',String(!edit));document.getElementById('public-edit-tab').setAttribute('aria-pressed',String(edit));if(edit)editFields();else sharingFields();}
 renderPublicProfile=()=>{value=packet.publicProfile;preview.replaceChildren(publicArticle(value,packet.synthetic));document.getElementById('public-export').disabled=!ready();document.getElementById('public-empty').hidden=ready();refreshFreshness();if(!editor.hidden)editFields();};
 document.querySelector('.public-sharing').addEventListener('toggle',event=>{if(event.currentTarget.open)sharingFields();});
 document.getElementById('public-edit-tab').onclick=()=>setEdit(true);
 document.getElementById('public-preview-tab').onclick=()=>setEdit(false);
 document.getElementById('public-save').onclick=()=>document.getElementById('save-html').click();
 document.getElementById('public-export').onclick=()=>{if(!ready())return;download('public-profile.html','text/html;charset=utf-8',publicDocument(value,packet.synthetic));status.textContent='Public profile download started. Private records are excluded.';};
 document.getElementById('public-mark-reviewed').onclick=()=>{if(!ready())return;value.contextSha256=basis;savePublicProfile('Profile marked reviewed against the current context.');document.getElementById(editor.hidden?'public-preview-tab':'public-edit-tab').focus();};
 renderPublicProfile();sharingFields();
 if(!ready())setEdit(true);
}
function snapshotPublicProfile(clone){
 if(!packet.publicProfile)return;
 clone.querySelector('#public-editor').replaceChildren();clone.querySelector('#public-editor').hidden=true;
 clone.querySelector('#public-preview').replaceChildren(publicArticle(packet.publicProfile,packet.synthetic));clone.querySelector('#public-preview').hidden=false;
 clone.querySelector('#public-preview-tab').setAttribute('aria-pressed','true');clone.querySelector('#public-edit-tab').setAttribute('aria-pressed','false');clone.querySelector('#public-status').textContent='';
}
