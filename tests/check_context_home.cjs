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
 check('Saved context opens on the private overview',await page.locator('#context').isVisible());
 check('Synthetic ownership is explicit',!before.synthetic||(await page.locator('.demo-notice').innerText()).includes('sample person'));
 check('Overview reads the actual saved person',await page.locator('#context .overview').innerText()===before.person.overview);
 for(const width of [1440,768,375,320]){
  await page.setViewportSize({width,height:1000});
  check('Overview fits '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(output,'context-'+width+'.png'),fullPage:true});
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
  await page.screenshot({path:path.join(output,'timeline-'+width+'.png'),fullPage:true});
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
 check('Account opens its original source',await page.locator(sourceHash).isVisible()&&await page.locator(sourceHash).evaluate(n=>n.open));
 await page.locator('.top [data-area="context"]').click();
 await page.locator('.context-add').click();
 check('Add context opens the ongoing workspace',await page.locator('#starting-note').isVisible());
 await page.locator('#starting-note').fill('PRIVATE_CONTEXT_HOME_NOTE');
 await page.locator('.top [data-area="context"]').click();
 const download=page.waitForEvent('download');await page.locator('#context-save').click();
 const saved=path.join(output,'context-private-save.html');await(await download).saveAs(saved);
 const clean=await browser.newContext(),reopened=await clean.newPage();await reopened.goto(pathToFileURL(saved).href);
 check('Saved file reopens on overview',await reopened.locator('#context').isVisible());
 check('Save preserves evidence and permissions',await reopened.evaluate(b=>JSON.stringify(packet.accounts)===JSON.stringify(b.accounts)&&JSON.stringify(packet.sources)===JSON.stringify(b.sources)&&JSON.stringify(packet.publicProfile)===JSON.stringify(b.publicProfile),before));
 await reopened.locator('.context-add').click();
 check('Ongoing context note survives a clean browser',await reopened.locator('#starting-note').inputValue()==='PRIVATE_CONTEXT_HOME_NOTE');
 await page.emulateMedia({reducedMotion:'reduce'});
 check('Reduced motion keeps year controls still',await page.locator('.timeline-year-label').first().evaluate(n=>getComputedStyle(n).transitionDuration==='0s'));
 check('No script errors',!errors.length);check('No external requests',!requests.length);
 await fs.writeFile(path.join(output,'context-checks.json'),JSON.stringify({checks,errors,requests},null,2));
 await browser.close();console.log(JSON.stringify({passed:checks.length,errors,requests}));
})().catch(e=>{console.error(e);process.exit(1);});
