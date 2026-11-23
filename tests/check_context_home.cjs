// Verify the private overview → year → account → source → saved-file journey.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const [input,output]=process.argv.slice(2);
if(!input||!output)throw Error('Usage: node tests/check_context_home.cjs input.html output-directory');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 const page=await context.newPage(),checks=[],errors=[],requests=[];
 const check=(name,condition)=>{assert.ok(condition,name);checks.push(name);};
 page.on('pageerror',e=>errors.push(e.message));
 await context.route(/^https?:/,r=>{requests.push(r.request().url());return r.abort();});
 await page.goto(pathToFileURL(path.resolve(input)).href);
 const before=await page.evaluate(()=>structuredClone(packet));
 check('Saved context opens on Career studio',await page.locator('#studio').isVisible());
 await page.locator('.top [data-area="context"]').click();
 check('Synthetic ownership is explicit',!before.synthetic||await page.locator('.workspace-owner').innerText()===before.person.name+'\nFictional example');
 check('Overview reads the actual saved person',await page.locator('#context .overview').innerText()===before.person.overview);
 const files=page.locator('.experience-file');
 if(await files.count()>1){
  const file=files.nth(1),summary=file.locator('summary'),chevron=file.locator('.file-chevron');
  const atRest=await chevron.evaluate(n=>getComputedStyle(n).transform);
  await summary.focus();await page.keyboard.press('Enter');
  check('Keyboard opens an experience file',await file.evaluate(n=>n.open));
  await page.waitForFunction(()=>document.querySelectorAll('.experience-file')[1].querySelector('.file-chevron').getAnimations().length===0);
  check('Chevron reaches its open position',await chevron.evaluate(n=>getComputedStyle(n).transform)!==atRest);
  await summary.press('Space');await summary.press('Space');await summary.press('Space');
  check('Rapid reversal leaves the requested file closed',!await file.evaluate(n=>n.open));
  await summary.blur();
 }
 for(const width of [1440,768,375,320]){
  await page.setViewportSize({width,height:1000});
  check('Overview fits '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const background=page.locator('.context-portrait .background');
  if(await background.count())check('Background adapts at '+width,await background.evaluate(n=>n.open)===(width>760));
  await page.screenshot({path:path.join(output,'context-'+width+'.png'),fullPage:true,animations:'disabled'});
 }
 await page.locator('.context-nav [data-view="timeline"]').click();
 for(const width of [1440,768,375,320]){
  await page.setViewportSize({width,height:1000});
  const year=await page.locator('#timeline-year-select option').last().getAttribute('value');
  if(width<=700){
   await page.locator('#timeline-year-select').selectOption(year);
   check('Year selection retains focus target '+width,await page.locator('#timeline-year-select').inputValue()===year);
  }else{
   await page.locator('.timeline-year-label').last().press('Enter');
   check('Year selection keeps keyboard focus '+width,await page.locator('.timeline-year-label').last().evaluate(n=>n===document.activeElement));
  }
  const range=await page.evaluate(()=>selectedTimelineContext(packet,timelineSelection.fromId,timelineSelection.toId,timelineSelection.contextSha256,timelineSelection.year));
  check('Only records overlapping the selected year are shown '+width,await page.evaluate(()=>selectedTimelineContext(packet,timelineSelection.fromId,timelineSelection.toId,timelineSelection.contextSha256,timelineSelection.year).periods.every(p=>timelineYears(p).includes(timelineSelection.year)))&&await page.locator('.quarter-reading:visible').count()===range.periods.length);
  check('Timeline fits '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(output,'timeline-'+width+'.png'),fullPage:true,animations:'disabled'});
 }
 const middle=await page.locator('#timeline-year-select option[value="2019"]').count();
 if(middle){
  await page.locator('#timeline-year-select').selectOption('2019');
  check('Middle year finds the original multi-year record',await page.locator('.quarter-reading:visible > summary .period').innerText()==='2018–2019');
  check('Year filter retains the original record and cautions against narrowing its events',await page.evaluate(()=>timelineBrief(packet,timelineSelection).includes('Do not assign every event')));
 }
 await page.locator('#timeline-year-select').selectOption(await page.locator('#timeline-year-select option').nth(1).getAttribute('value'));
 await page.locator('#timeline-work').click();
 const ids=await page.evaluate(()=>[...timelineWorkIds]);
 check('Year opens its linked work',await page.locator('.account:visible').count()===ids.length);
 await page.locator('.account:visible .context-details > summary').first().click();
 const source=page.locator('.account:visible .references a').first();
 const sourceHash=await source.getAttribute('href');await source.click();
 await page.locator(sourceHash+'[open]').waitFor({state:'visible'});
 check('Account opens its original source',await page.locator(sourceHash).isVisible()&&await page.locator(sourceHash).evaluate(n=>n.open));
 await page.locator('.top [data-area="context"]').click();
 await page.locator('.context-add').click();
 check('Add context opens the ongoing workspace',await page.locator('#starting-note').isVisible());
 await page.locator('#starting-note').fill('PRIVATE_CONTEXT_HOME_NOTE');
 await page.locator('.top [data-area="context"]').click();
 const download=page.waitForEvent('download');await page.locator('#context-save').click();
 const saved=path.join(output,'context-private-save.html');await(await download).saveAs(saved);
 const clean=await browser.newContext(),reopened=await clean.newPage();await reopened.goto(pathToFileURL(saved).href);
 check('Saved file reopens on studio',await reopened.locator('#studio').isVisible());
 await reopened.locator('.top [data-area="context"]').click();
 check('Save preserves evidence and permissions',await reopened.evaluate(b=>JSON.stringify(packet.accounts)===JSON.stringify(b.accounts)&&JSON.stringify(packet.sources)===JSON.stringify(b.sources)&&JSON.stringify(packet.publicProfile)===JSON.stringify(b.publicProfile),before));
 await reopened.locator('.context-add').click();
 check('Ongoing context note survives a clean browser',await reopened.locator('#starting-note').inputValue()==='PRIVATE_CONTEXT_HOME_NOTE');
 await reopened.locator('.top [data-area="context"]').click();
 await reopened.locator('#edit-experience').click();
 let editor=reopened.locator('.experience-editor');
 await editor.locator('[data-add]').click();
 let role=editor.locator('.experience-fields').last();
 await role.getByLabel('Role or type of work').fill('Independent project');
 await role.getByLabel('Organization or client').fill('Client <A>');
 await role.getByLabel('Dates').fill('Spring term');
 await role.getByLabel('Current role').check();
 const id=await editor.locator('.experience-assign select').first().locator('option').last().getAttribute('value');
 await editor.locator('.experience-assign select').first().selectOption(id);
 const png=await reopened.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=8;return c.toDataURL().split(',')[1];});
 await role.locator('input[type=file]').setInputFiles({name:'logo.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
 await role.getByRole('button',{name:'Remove logo'}).waitFor();
 await reopened.setViewportSize({width:320,height:800});
 check('Role editor fits a narrow screen',await editor.evaluate(n=>n.scrollWidth<=n.clientWidth+1));
 const editedDownload=reopened.waitForEvent('download');await editor.getByRole('button',{name:'Save private HTML'}).click();
 const editedFile=path.join(output,'edited-experience.html');await(await editedDownload).saveAs(editedFile);
 const firstRole=reopened.locator('.experience-role').first();
 check('Current role contains its assigned example and local logo',await firstRole.locator('h3').innerText()==='Independent project'&&
  await firstRole.locator('[data-experience]').first().getAttribute('data-experience')===before.accounts[0].id&&await firstRole.locator('img').evaluate(n=>n.naturalWidth===8));
 await reopened.locator('#edit-experience').click();editor=reopened.locator('.experience-editor');
 await editor.locator('.experience-fields').last().getByRole('button',{name:'Remove role'}).click();
 await editor.getByRole('button',{name:'Cancel'}).click();
 check('Cancelling removal keeps the role and its work',await firstRole.locator('h3').innerText()==='Independent project');
 await reopened.locator('#edit-experience').click();
 const assistDownload=reopened.waitForEvent('download');
 await reopened.locator('.experience-editor').getByRole('button',{name:'Save for AI review'}).click();
 const assistFile=path.join(output,'experience-for-assistant.html');await(await assistDownload).saveAs(assistFile);
 const handoff=JSON.parse((await fs.readFile(assistFile,'utf8')).match(/<script[^>]*id="career-context-data"[^>]*>([\s\S]*?)<\/script>/)[1]);
 check('AI handoff carries role edits and the targeted request',
  handoff.presentation.experienceRoles.some(r=>r.id===id&&r.personEdited)&&handoff.journey.notes.output.includes('Organize My context by role'));
 const plain=await browser.newContext({javaScriptEnabled:false}),staticPage=await plain.newPage();
 await staticPage.goto(pathToFileURL(editedFile).href);
 const savedData=JSON.parse(await staticPage.locator('#career-context-data').textContent());
 check('Edited HTML reopens offline with the same evidence',JSON.stringify(savedData.accounts)===JSON.stringify(before.accounts)&&
   JSON.stringify(savedData.sources)===JSON.stringify(before.sources)&&savedData.presentation.experienceRoles.some(r=>r.id===id&&r.personEdited&&r.organization==='Client <A>')&&
   (await staticPage.locator('.experience-role h3').first().textContent())==='Independent project');
 await plain.close();
 await page.emulateMedia({reducedMotion:'reduce'});
 check('Reduced motion keeps year controls still',await page.locator('.timeline-year-label').first().evaluate(n=>getComputedStyle(n).transitionDuration==='0s'));
 await page.locator('.top [data-area="context"]').click();
 check('Reduced motion keeps tab and file motion instant',await page.evaluate(()=>getComputedStyle(document.querySelector('.context-nav'),'::before').transitionDuration==='0s'&&getComputedStyle(document.querySelector('.file-chevron')).transitionDuration==='0s'));
 check('No script errors',!errors.length);check('No external requests',!requests.length);
 await fs.writeFile(path.join(output,'context-checks.json'),JSON.stringify({checks,errors,requests},null,2));
 await browser.close();console.log(JSON.stringify({passed:checks.length,errors,requests}));
})().catch(e=>{console.error(e);process.exit(1);});
