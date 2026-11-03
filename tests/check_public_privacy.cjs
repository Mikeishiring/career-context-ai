// Exercise actual downloaded bytes, private save/reopen, legacy drafts and image containers.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const [input,output]=process.argv.slice(2);
if(!input||!output)throw Error('Usage: node tests/check_public_privacy.cjs private.html output-directory');
function crc(bytes){let c=0xffffffff;for(const b of bytes){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;}
function withMetadata(url){
 const [header,data]=url.split(','),raw=Buffer.from(data,'base64'),secret=Buffer.from('PRIVATE_IMAGE_METADATA');let result;
 if(header.includes('/png')){
  const body=Buffer.concat([Buffer.from('Comment\0'),secret]),chunk=Buffer.alloc(body.length+12);chunk.writeUInt32BE(body.length);chunk.write('tEXt',4);body.copy(chunk,8);chunk.writeUInt32BE(crc(chunk.subarray(4,-4)),chunk.length-4);
  result=Buffer.concat([raw.subarray(0,-12),chunk,raw.subarray(-12)]);
 }else if(header.includes('/jpeg')){
  const segment=Buffer.alloc(secret.length+4);segment[0]=255;segment[1]=254;segment.writeUInt16BE(secret.length+2,2);secret.copy(segment,4);result=Buffer.concat([raw.subarray(0,2),segment,raw.subarray(2)]);
 }else{
  const chunk=Buffer.alloc(8+secret.length+secret.length%2);chunk.write('XMP ');chunk.writeUInt32LE(secret.length,4);secret.copy(chunk,8);result=Buffer.concat([raw,chunk]);result.writeUInt32LE(result.length-8,4);
 }
 return header+','+result.toString('base64');
}
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
 const context=await browser.newContext({acceptDownloads:true}),page=await context.newPage(),checks=[],errors=[],requests=[];
 const check=(name,condition)=>{assert.ok(condition,name);checks.push(name);};
 page.on('pageerror',e=>errors.push(e.message));await context.route(/^https?:/,r=>{requests.push(r.request().url());return r.abort();});
 await page.goto(pathToFileURL(path.resolve(input)).href+'#profile');
 check('Public name is not copied from the private identity',await page.evaluate(()=>packet.publicProfile.name===''&&packet.person.name==='PRIVATE_LEGAL_NAME'));
 const original=await page.evaluate(()=>structuredClone(packet));
 await page.evaluate(()=>{
  packet.publicProfile={contextSha256:packet.journey.contextSha256,updatedAt:0,name:'Chosen public name',headline:'Public work',overview:'PRIVATE_LEGACY_OVERVIEW',
   examples:[{title:'PRIVATE_LEGACY_EXAMPLE',summary:'Unapproved example',synthetic:true}],timeline:[{period:'2030',title:'PRIVATE_LEGACY_YEAR',summary:'Unapproved dates'}]};
  renderPublicProfile();
 });
 check('Missing sharing flags keep every legacy component unselected',await page.locator('#public-sharing input:checked').count()===0&&await page.locator('#public-export').isDisabled());
 check('Legacy drafts remain editable',await page.getByRole('textbox',{name:'Overview',exact:true}).inputValue()==='PRIVATE_LEGACY_OVERVIEW');
 const imageCases=await page.evaluate(()=>{
  const c=document.createElement('canvas');c.width=c.height=2;c.getContext('2d').fillRect(0,0,2,2);
  return ['png','jpeg','webp'].map(type=>({type,clean:c.toDataURL('image/'+type)}));
 });
 for(const entry of imageCases)entry.withMetadata=withMetadata(entry.clean);
 check('Metadata in all three formats is excluded',await page.evaluate(cases=>cases.every(c=>!publicImageShareable(c.withMetadata)),imageCases));
 for(const [i,entry] of imageCases.entries()){
  await page.locator('#public-image-file').setInputFiles({name:'sample.'+entry.type,mimeType:'image/'+entry.type,buffer:Buffer.from(entry.withMetadata.split(',')[1],'base64')});
  await page.waitForFunction(n=>packet.publicProfile.media.length===n,i+1);
  entry.clean=await page.evaluate(i=>packet.publicProfile.media[i].dataUrl,i);
 }
 check('Re-imported PNG, JPEG and WebP lose metadata and remain unselected',await page.evaluate(()=>packet.publicProfile.media.every(m=>publicImageShareable(m.dataUrl)&&m.included===false)));
 await fs.writeFile(path.join(output,'image-cases.json'),JSON.stringify(imageCases));
 await page.evaluate(cases=>{
  packet.publicProfile.examples.unshift({title:'Explicitly selected work',summary:'A public demonstration.',synthetic:true,included:true});
  packet.publicProfile.media=cases.flatMap((c,i)=>[
   {id:'clean-'+i,kind:'image',title:c.type,alt:'A plain test square',caption:'',credit:'',included:true,dataUrl:c.clean},
   {id:'metadata-'+i,kind:'image',title:'PRIVATE_METADATA_SAMPLE',alt:'Private original',caption:'PRIVATE_IMAGE_CAPTION',credit:'',included:true,dataUrl:c.withMetadata}]);
  packet.publicProfile.media.push({id:'signed',kind:'video',title:'PRIVATE_SIGNED_LINK',caption:'',credit:'',included:true,url:'https://example.org/watch?access_token=PRIVATE_TOKEN'});
  renderPublicProfile();
 },imageCases);
 check('Metadata-bearing originals cannot be selected',await page.locator('#public-sharing input:disabled').count()>=3);
 await page.locator('#public-preview-tab').click();
 check('Preview includes only the selected example and clean images',await page.locator('#public-preview .public-example').count()===1&&await page.locator('#public-preview .public-visual').count()===3&&!(await page.locator('#public-preview').innerText()).includes('PRIVATE_'));
 const wait=page.waitForEvent('download');await page.locator('#public-export').click();const exported=path.join(output,'public-profile.html');await(await wait).saveAs(exported);
 const html=await fs.readFile(exported,'utf8');
 check('Downloaded HTML contains no private canaries or canonical payload',!html.includes('PRIVATE_')&&!/career-context-data|career-resume-data|<script\b/i.test(html));
 check('Private source bodies never enter the export',original.sources.every(s=>!html.includes(s.content)));
 check('Downloaded images have no hidden metadata bytes',Array.from(html.matchAll(/data:image\/[^;]+;base64,([A-Za-z0-9+/=]+)/g)).every(m=>!Buffer.from(m[1],'base64').includes(Buffer.from('PRIVATE_'))));
 const save=page.waitForEvent('download');await page.locator('#public-save').click();const privateFile=path.join(output,'private-saved.html');await(await save).saveAs(privateFile);
 const saved=await fs.readFile(privateFile,'utf8'),packet=JSON.parse(saved.match(/<script id="career-context-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
 check('Full private save retains withheld drafts and image originals',saved.includes('PRIVATE_LEGACY_OVERVIEW')&&saved.includes('PRIVATE_LEGAL_NAME')&&packet.publicProfile.media[1].dataUrl===imageCases[0].withMetadata);
 const clean=await browser.newContext(),reopened=await clean.newPage();await reopened.goto(pathToFileURL(privateFile).href+'#profile');
 check('Reopening a private file does not select legacy drafts',await reopened.locator('#public-preview .public-example').count()===1&&await reopened.locator('#share-overview').isChecked()===false);
 check('Signed and credential-bearing links are rejected',await page.evaluate(()=>['https://example.org/video?access_token=PRIVATE_TOKEN','https://example.org/video#token=PRIVATE_TOKEN','https://example.org/video?X-Amz-Signature=PRIVATE_SIGNATURE'].every(u=>!publicVideoUrl(u))));
 // Browser draft restoration must also preserve missing flags as unselected.
 const old=await browser.newContext();await old.addInitScript(p=>localStorage.setItem('career-public:'+p.contextSha256,JSON.stringify({...p,updatedAt:Date.now()+1000,shareOverview:undefined,examples:[{title:'PRIVATE_RESTORED',summary:'Unapproved',synthetic:true}],timeline:[],media:[]})),packet.publicProfile);
 const restored=await old.newPage();await restored.goto(pathToFileURL(privateFile).href+'#profile');
 check('Legacy browser drafts cannot acquire sharing permission on restore',await restored.locator('#public-export').isDisabled()&&await restored.locator('#public-sharing input:checked').count()===0);
 check('No script errors',errors.length===0);check('No network requests',requests.length===0);
 await fs.writeFile(path.join(output,'image-cases.json'),JSON.stringify(imageCases));
 await fs.writeFile(path.join(output,'privacy-checks.json'),JSON.stringify({checks,errors,requests},null,2));
 await browser.close();console.log(JSON.stringify({passed:checks.length,errors,requests}));
})().catch(e=>{console.error(e);process.exit(1);});
