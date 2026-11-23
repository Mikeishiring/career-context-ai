// Exercise the output desk and portable assistant handoff without a network.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const [input,output]=process.argv.slice(2);
(async()=>{
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
 try{
  const context=await browser.newContext({acceptDownloads:true}),page=await context.newPage(),errors=[],requests=[],checks=[];
  const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);};
  page.on('pageerror',e=>errors.push(e.message));
  await context.route(/^https?:/,r=>{requests.push(r.request().url());return r.abort();});
  await page.goto(pathToFileURL(path.resolve(input)).href);
  const before=await page.evaluate(()=>structuredClone(packet));
  check('Opens on Career studio',await page.locator('#studio').isVisible());
  for(const width of [1440,768,375,320]){
   await page.setViewportSize({width,height:1000});
   check('Fits '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(output,'studio-'+width+'.png'),fullPage:true});
  }
  for(const preview of await page.locator('[data-studio-image]').all()){
   check('Preview is the retained artifact',await preview.evaluate(n=>n.src===document.getElementById(n.dataset.studioImage).src&&n.naturalWidth>0));
  }
  if(before.accounts.length){
   const first=before.accounts[0],last=before.accounts[before.accounts.length-1];
   await page.locator('.review-launch').click();
   const desk=page.locator('#review-sheet');
   await page.reload();
   check('Direct review link opens a populated story',await desk.getByRole('heading',{name:first.title,exact:true}).isVisible());
   const wording=desk.locator('summary').filter({hasText:'Compare draft wording'});
   if(await wording.count()){
    await wording.click();
    check('Draft comparison reveals the actual account wording',await desk.getByText(first.summary,{exact:true}).isVisible());
    await wording.click();
   }
   await desk.getByRole('link',{name:'Full account and sources'}).click();
   check('Full account link opens evidence',await page.locator('#account-'+first.id).isVisible());
   await page.goBack();
   for(const width of [1440,768,375,320]){
    await page.setViewportSize({width,height:900});
    check('Story review fits '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(output,'review-'+width+'.png'),fullPage:true});
   }
   await page.locator('.review-omission summary').click();
   await page.locator('#missing-work').fill('Private omitted assignment');
   await page.selectOption('#review-picker',last.id);
   check('Review shows this account',await desk.getByRole('heading',{name:last.title,exact:true}).isVisible());
   const assessment=before.presentation?.storyReview?.accounts[last.id];
   if(assessment)check('Assistant assessment is separate from personal choices',(await desk.innerText()).includes(assessment)&&await desk.locator('[aria-pressed=true]').count()===0);
   if(last.questions.length)check('Review shows an account-specific gap',(await desk.innerText()).includes(last.questions[0]));
   const choose=value=>desk.locator('button[value="'+value+'"]');
   await choose('minor').click();
   check('One personal choice counts the story once',await page.locator('#studio-rating-progress').evaluate(n=>n.value===1));
   await choose('minor').click();
   check('Clearing its last rating returns a story to the queue',await page.locator('#studio-rating-progress').evaluate(n=>n.value===0));
   await choose('minor').click();
   await choose('over').focus();await page.keyboard.press('Space');
   check('Keyboard can select a rating',await choose('over').getAttribute('aria-pressed')==='true');
   await page.emulateMedia({reducedMotion:'reduce'});
   check('Reduced motion keeps rating changes immediate',await choose('over').evaluate(node=>getComputedStyle(node).transitionDuration==='0s'));
   await page.emulateMedia({reducedMotion:'no-preference'});
   await choose('over').click();
   check('A preference can be cleared',await choose('over').getAttribute('aria-pressed')==='false');
   await choose('over').click();
   await choose('lead').click();
   await desk.locator('textarea').fill('Private recollection to check');
   check('Review fits mobile',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(output,'personal-review-mobile.png')});
   check('Interest promotes a story independently of importance',await page.locator('#studio-stories li>a').first().getAttribute('href')==='#rehearse-'+last.id);
   check('Work list shows my assessment',(await page.locator('[data-story-verdict="'+last.id+'"]').innerText()).includes('Oversold'));
   if(first.id!==last.id){
    await page.setViewportSize({width:1440,height:900});
    await page.locator('[data-review-story="'+first.id+'"]').click();
    await choose('reserve').click();
    check('Set-aside story remains reviewable',await page.locator('[data-review-story="'+first.id+'"]').isVisible()&&!await page.locator('#studio-stories a[href="#rehearse-'+first.id+'"]').count());
    await page.locator('[data-review-story="'+last.id+'"]').click();
    check('Story selection restores my own ratings',await choose('lead').getAttribute('aria-pressed')==='true'&&await desk.locator('textarea').inputValue()==='Private recollection to check');
    await page.screenshot({path:path.join(output,'review-selected.png'),fullPage:true});
    await page.goto(pathToFileURL(path.resolve(input)).href+'#path-review--'+last.id);
    check('Guided editor shares the same assessment',await page.locator('#path-content button[value=lead]').getAttribute('aria-pressed')==='true');
    await page.locator('#path-content a[href="#story-review"]').click();
   }
   const reviewDownload=page.waitForEvent('download');await page.locator('#save-story-review').click();
   const reviewFile=path.join(output,'saved-review.html');await(await reviewDownload).saveAs(reviewFile);
   const fresh=await browser.newContext(),reviewPage=await fresh.newPage();await reviewPage.goto(pathToFileURL(reviewFile).href);
   check('Private review reopens independently',await reviewPage.evaluate(({id,old})=>{
    const r=packet.journey.reviews[id];
    return r.importance==='minor'&&r.emphasis==='over'&&r.interest==='lead'&&r.missingContext==='Private recollection to check'&&
     packet.journey.notes.missingWork==='Private omitted assignment'&&packet.reviewStatus===old.reviewStatus&&
     ['accounts','sources','publicProfile'].every(k=>JSON.stringify(packet[k])===JSON.stringify(old[k]));
   },{id:last.id,old:before}));
   await fresh.close();
   await page.locator('[data-view="studio"]').click();
   const featured=await page.locator('.review-launch').getAttribute('data-featured');
   const expected=before.accounts.find(a=>a.id!==first.id&&a.id!==last.id)||first;
   check('Cover shows the next unrated story or the first once all are rated',featured===expected.id&&await page.locator('.folder-title').innerText()===expected.title);
   check('Progress counts distinct rated stories',await page.locator('#studio-rating-progress').evaluate(n=>n.value)===(first.id===last.id?1:2));
   await page.locator('.review-launch').click();
   check('Opening the cover reviews the advertised story',await desk.getByRole('heading',{name:expected.title,exact:true}).isVisible());
   await page.locator('[data-view="studio"]').click();
   await page.locator('[data-studio-kind]').click();
   check('Create opens resume request',await page.locator('#studio-kind').inputValue()==='resume');
   await page.keyboard.press('Escape');
   check('Escape returns keyboard focus',await page.locator('[data-studio-kind]').evaluate(n=>n===document.activeElement));
   for(const kind of ['resume','example','story','custom']){
    await page.locator('[data-studio-kind]').click();
    await page.locator('#studio-kind').selectOption(kind);
    await page.locator('#studio-account').selectOption(before.accounts[0].id);
    const direction=page.locator('#studio-direction');
    const request=kind==='custom'?'Which part of working with visitors would I like to do more of?':'Talent and AI tools';
    if(kind==='custom'){
     await direction.fill('  ');
     await page.locator('#studio-request-form [type="submit"]').click();
     check('Custom request needs a task',await direction.evaluate(n=>!n.validity.valid));
    }
    await direction.fill(request);
    check('Request fits mobile',await page.evaluate(()=>document.querySelector('#studio-request').scrollWidth<=document.querySelector('#studio-request').clientWidth));
    const download=page.waitForEvent('download');await page.locator('#studio-request-form [type="submit"]').click();
    const saved=path.join(output,'saved-request.html');await(await download).saveAs(saved);
    const clean=await browser.newContext(),reopened=await clean.newPage();await reopened.goto(pathToFileURL(saved).href);
    check('Saved '+kind+' opens on studio',await reopened.locator('#studio').isVisible());
    check('Saved dialog closes',!await reopened.locator('#studio-request').isVisible());
    check('Request and scope travel in file',await reopened.evaluate(({kind,id,request})=>packet.journey.notes.output.includes({resume:'resume draft',example:'visual work example',story:'career story',custom:'Request: '}[kind])&&packet.journey.notes.output.includes('[account '+id+']')&&packet.journey.notes.output.includes(request),{kind,id:before.accounts[0].id,request}));
    check('Creating a handoff preserves open request',await page.evaluate(original=>packet.journey.notes.output===original,before.journey.notes.output));
    if(kind==='custom'){
     await reopened.locator('[data-studio-kind]').click();
     await reopened.selectOption('#studio-kind','custom');
     await reopened.fill('#studio-direction','Birch offer: what is the rota?');
     const nextDownload=reopened.waitForEvent('download');
     await reopened.locator('#studio-request-form [type="submit"]').click();
     const nextFile=path.join(output,'second-request.html');
     await(await nextDownload).saveAs(nextFile);
     await reopened.reload();
     check('Reopening first handoff keeps its own task',await reopened.evaluate(first=>packet.journey.notes.output.includes(first)&&!packet.journey.notes.output.includes('Birch offer'),request));
     await reopened.goto(pathToFileURL(nextFile).href);
     check('Second handoff contains only its own request',await reopened.evaluate(first=>packet.journey.notes.output.includes('Birch offer')&&!packet.journey.notes.output.includes(first),request));
     await reopened.goto(pathToFileURL(saved).href);
    }
    check('Records and sharing unchanged',await reopened.evaluate(b=>['accounts','sources','publicProfile'].every(k=>JSON.stringify(packet[k])===JSON.stringify(b[k])),before));
    await clean.close();await page.locator('#studio-close').click();
   }
   const story=page.locator('.studio-stories li>a').first();
   if(await story.count()){await story.click();check('Story opens prepared content',await page.locator('#audience-desk').isVisible());await page.locator('[data-view="studio"]').click();}
   const example=page.locator('.studio-preview').first();
   if(await example.count()){const id=await example.getAttribute('href');await example.click();check('Example reaches its account',await page.locator(id).isVisible());}
  }else{
   await page.locator('.studio-empty a').click();check('Empty studio starts a real account',await page.locator('#starting-note').isVisible());
  }
  check('No script errors',!errors.length);check('No external requests',!requests.length);
  await fs.writeFile(path.join(output,'checks.json'),JSON.stringify({checks,errors,requests},null,2));
  console.log(JSON.stringify({passed:checks.length,errors,requests}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
