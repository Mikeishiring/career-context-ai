// Real browser review/save/update/export over the fixed fictional career history.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const [stage,input,output]=process.argv.slice(2);
if(!['review','update'].includes(stage)||!input||!output)throw Error('Expected review|update, input HTML and run directory');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
 try{
  const checks=[],errors=[],requests=[];
  const guard=async context=>{
   context.on('page',page=>{
    page.on('pageerror',e=>errors.push(e.message));
    page.on('dialog',async d=>{errors.push('Unexpected dialog: '+d.type());await d.dismiss();});
   });
   await context.route(/^https?:/,async route=>{requests.push(route.request().url());await route.abort();});
   return context;
  };
  const context=await guard(await browser.newContext({acceptDownloads:true,viewport:{width:1440,height:1000}}));
  const page=await context.newPage();
  const check=(name,condition)=>{assert.ok(condition,name);checks.push(name);};
  const save=async(file,button)=>{const waiting=page.waitForEvent('download');await page.locator(button).click();await (await waiting).saveAs(path.join(output,file));};
  await page.goto(pathToFileURL(path.resolve(input)).href+'#path-review');
  const before=await page.evaluate(()=>structuredClone(packet));
  if(stage==='review'){
   for(const account of before.accounts){
    await page.locator('#path-story').selectOption(account.id);
    await page.locator('#path-note').fill('PRIVATE_REVIEW_NOTE: Preserve credit and uncertainty for '+account.id+'.');
    await page.locator('#review-keep').click();
   }
   check('All six account review choices can be retained',await page.evaluate(()=>Object.values(packet.journey.reviews).every(r=>r.decision==='kept')));
   check('Keeping drafts does not invent factual approval',await page.evaluate(()=>packet.reviewStatus==='draft'));
   await page.locator('#path-link-write').click();
   await page.locator('#writing-draft').fill('I help teams agree the next step and check practical tools with other people. PRIVATE_WRITING_NOTE.');
   await page.evaluate(()=>location.hash='profile');
   await page.locator('#public-edit-tab').click();
   await page.getByRole('textbox',{name:'Name',exact:true}).fill('Public example');
   await page.getByRole('textbox',{name:'Headline',exact:true}).fill('Operations work, explained plainly');
   await page.getByRole('textbox',{name:'Overview',exact:true}).fill('I help people agree the next step, check practical tools and retain the limits of the evidence.');
   await page.locator('#public-add').click();
   await page.getByRole('textbox',{name:'Example title',exact:true}).first().fill('A reception guide tested with volunteers');
   await page.getByRole('textbox',{name:'General overview',exact:true}).first().fill('I drafted the guide and revised it after two supervised shifts. A colleague checked the procedures. Independent use was not established.');
   await page.getByLabel('Synthetic example',{exact:true}).first().check();
   await page.locator('#public-preview-tab').click();
   const sharing=page.locator('.public-sharing');if(!await sharing.evaluate(n=>n.open))await sharing.locator('summary').click();
   await page.locator('#share-overview').check();await page.locator('#share-example-0').check();
   await save('reviewed.html','#public-save');
   const saved=JSON.parse((await fs.readFile(path.join(output,'reviewed.html'),'utf8')).match(/<script id="career-context-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
   check('Saved HTML preserves every claim and exact source',JSON.stringify(saved.memory)===JSON.stringify(before.memory)&&JSON.stringify(saved.sources)===JSON.stringify(before.sources));
   check('Saved HTML preserves review notes and private wording',Object.keys(saved.journey.notes).length===6&&saved.journey.writing.draft.includes('PRIVATE_WRITING_NOTE'));
  }else{
   const state=await page.evaluate(()=>structuredClone(packet.journey));
   check('Only the account changed by the follow-up reopens',Object.entries(state.reviews).filter(([,r])=>r.decision==='pending').map(([id])=>id).join(',')==='renewal-reminders');
   check('Five unrelated review decisions survive',Object.values(state.reviews).filter(r=>r.decision==='kept').length===5);
   check('All private review notes and wording survive',Object.keys(state.notes).length===6&&state.writing.draft.includes('PRIVATE_WRITING_NOTE'));
   check('First wording survives reconciliation',state.baseline.accounts['renewal-reminders'].includes('disputed pending follow-up'));
   const claims=await page.evaluate(()=>packet.memory.claims);
   check('Old adoption claim is rejected and the correction is retained',claims.find(c=>c.id==='reminder-wide').status==='rejected'&&claims.find(c=>c.id==='reminder-retired').status==='supported');
   await page.locator('#path-story').selectOption('renewal-reminders');
   check('Updated account displays the retired prototype',await page.locator('#path-content').innerText().then(t=>t.includes('retired')));
   await page.locator('#review-keep').click();
   await page.evaluate(()=>location.hash='profile');
   check('Private evidence changes do not auto-approve the public projection',await page.locator('#public-freshness').isVisible());
   await page.locator('#public-mark-reviewed').click();
   check('Public approval remains a separate explicit action',await page.locator('#public-freshness').isHidden());
   await save('public-profile.html','#public-export');
   const publicText=await fs.readFile(path.join(output,'public-profile.html'),'utf8');
   check('Public export excludes private sources, memory and notes',!publicText.includes('PRIVATE_')&&!publicText.includes('career-context-data')&&!publicText.includes('reminder-wide')&&!/<script\b/i.test(publicText));
   check('Public export keeps the selected qualifications',publicText.includes('supervised')&&publicText.includes('Independent use was not established'));
   await save('saved-current.html','#public-save');
   const clean=await guard(await browser.newContext()),reopened=await clean.newPage();
   await reopened.goto(pathToFileURL(path.join(output,'saved-current.html')).href+'#path-review');
   check('Review state and memory survive reopening without browser storage',await reopened.evaluate(()=>Object.values(packet.journey.reviews).every(r=>r.decision==='kept')&&packet.memory.claims.some(c=>c.id==='reminder-retired')));
   await clean.close();
   for(const width of [375,1440]){
    await page.setViewportSize({width,height:1000});
    for(const route of ['timeline','work','profile']){
     await page.evaluate(hash=>location.hash=hash,route);
     check(route+' fits '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
   }
   await page.screenshot({path:path.join(output,'profile.png'),fullPage:true});
  }
  check('No browser script errors',errors.length===0);
  check('No external requests',requests.length===0);
  const receipt={stage,passed:checks.length,checks,errors,requests};
  await fs.writeFile(path.join(output,'browser-'+stage+'.json'),JSON.stringify(receipt,null,2));
  console.log(JSON.stringify(receipt));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
