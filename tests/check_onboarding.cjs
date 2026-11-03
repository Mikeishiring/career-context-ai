// Exercise a new user's empty start, corrections, continuation and private boundaries.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const [example,empty,output]=process.argv.slice(2);
if(!example||!empty||!output)throw Error('Usage: node tests/check_onboarding.cjs example.html empty.html output');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
 const checks=[],errors=[],requests=[];
 const check=(name,condition)=>{assert.ok(condition,name);checks.push(name);};
 const makeContext=async()=>{
  const c=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await c.route(/^https?:/,route=>{requests.push(route.request().url());return route.abort();});
  c.on('page',p=>{p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>{errors.push(d.message());d.dismiss();});});
  return c;
 };
 const context=await makeContext(),page=await context.newPage();
 await page.goto(pathToFileURL(path.resolve(example)).href);
 await page.evaluate(()=>{packet.journey.investigation={schema:'career-investigation/v1',contextSha256:packet.journey.contextSha256,
  reviewSha256:'0'.repeat(64),goal:'PRIVATE_INVESTIGATION_BROWSER',rounds:[{id:'round-1',purpose:'orient',question:'What needs checking?',
  finding:'Read the source behind this account.',accountIds:[packet.accounts[0].id],sourceRefs:[packet.sources[0].id],claimIds:[]}],
  leads:[{id:'next-read',question:'What changed?',why:'Check attribution.',nextAction:'Read the selected original.',status:'ready',accountIds:[packet.accounts[0].id],sourceRefs:[packet.sources[0].id],claimIds:[]}],stopReason:''};});
 const before=await page.evaluate(()=>structuredClone(packet));
 check('Existing context opens on the private overview',await page.locator('#context').isVisible());
 await page.locator('.top [data-view="path"]').click();
 check('Account review remains directly available',await page.locator('#review-keep').isVisible());
 check('There is no required numbered ladder or monthly intake',!(await page.locator('#path-step-number').innerText()).trim()&&await page.locator('#coverage-start').count()===0);
 const correction='PRIVATE_CORRECTION: I tested it; my colleague wrote the production version. <script>throw Error("unsafe")</script>';
 await page.locator('#review-correction').fill(correction);
 await page.locator('#review-record').press('Enter');
 const id=before.accounts[0].id;
 check('Ordinary correction needs no replacement prose or source IDs',await page.evaluate(id=>packet.journey.reviews[id].decision==='correction'&&packet.journey.reviews[id].sourceRefs.length===0,id));
 check('Recording correction leaves evidence and factual approval untouched',await page.evaluate(b=>JSON.stringify(packet.accounts)===JSON.stringify(b.accounts)&&JSON.stringify(packet.sources)===JSON.stringify(b.sources)&&packet.reviewStatus===b.reviewStatus,before));
 check('Recorded is visibly distinct from applied',(await page.locator('#path-content .review-state').innerText()).includes('unresolved'));
 check('The complete handoff sits beside the correction; note-only copy is disclosed',await page.locator('#review-handoff').isVisible()&&await page.locator('#path-handoff').isHidden()&&await page.locator('#path-copy').isHidden());
 await page.locator('#path-note').fill('Please keep the shared credit explicit.');
 check('Additional notes keep the unapplied correction flagged',await page.evaluate(id=>packet.journey.reviews[id].decision==='correction',id));
 for(const account of before.accounts.slice(1)){await page.locator('#path-story').selectOption(account.id);await page.locator('#review-keep').click();}
 await page.locator('#path-story').selectOption(id);
 check('Recorded responses do not label unapplied corrections resolved',(await page.locator('#path-link-review .path-state').innerText())==='Awaiting assistant');
 await page.getByText('Propose exact wording and sources',{exact:true}).click();
 await page.locator('#review-draft').fill('A proposed revision needing reconciliation.');
 check('Advanced wording cannot erase the ordinary correction',await page.evaluate(({id,correction})=>packet.journey.reviews[id].reason===correction,{id,correction}));
 await page.locator('#review-record').click();
 await page.locator('#path-link-deepen').click();
 await page.locator('#path-note').fill('Keep this ownership question open.');
 await page.locator('#depth-clear').click();
 check('An unapplied correction cannot be dismissed by closing a gap',await page.evaluate(id=>packet.journey.reviews[id].depth==='open',id));
 await page.locator('#path-link-gather').click();
 check('Monthly collection is optional and initially disclosed',!await page.locator('#systematic-collection').evaluate(n=>n.open)&&!await page.locator('#coverage-start').isVisible());
 await page.locator('#starting-note').fill('PRIVATE_NEXT_GOAL: understand my role in this project.');
 await page.evaluate(()=>{window.clipboardCalls=0;Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{window.clipboardCalls++;throw Error('blocked');}},configurable:true});});
 const download=page.waitForEvent('download');await page.locator('#start-handoff').click();
 const saved=path.join(output,'onboarding-saved.html');await (await download).saveAs(saved);
 check('One-file handoff needs no clipboard or second artifact',await page.evaluate(()=>window.clipboardCalls===0)&&!await page.locator('#context-reader').isVisible()&&(await page.locator('#path-status').innerText()).includes('Attach career-context.html'));
 const savedHTML=await fs.readFile(saved,'utf8');
 const resume=JSON.parse(savedHTML.match(/<script id="career-resume-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
 check('Saved file carries the resume contract and permission limits',resume.schema==='career-resume/v1'&&resume.instructions.includes('grant no new access')&&resume.instructions.includes('not executable instructions'));
 await page.locator('.path-brief > summary').click();await page.locator('#path-copy-continuation').click();
 const brief=await page.locator('#agent-text').inputValue();
 check('One handoff preserves purpose and identifies pending correction',brief.includes('PRIVATE_NEXT_GOAL')&&brief.includes(id)&&brief.includes('correction'));
 check('Handoff preserves permissions and distinguishes data from instructions',brief.includes('grant no new access')&&brief.includes('different host')&&brief.includes('not executable instructions'));
 check('Optional brief has a manual-copy fallback',await page.locator('#context-reader').isVisible()&&(await page.locator('#reader-note').innerText()).includes('matching private save'));
 const parsed=JSON.parse(savedHTML.match(/<script id="career-context-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
 check('Downloaded file contains complete corrections and unchanged evidence',parsed.journey.reviews[id].reason===correction&&JSON.stringify(parsed.sources)===JSON.stringify(before.sources));
 check('Continuation identifies the saved review version',brief.includes('"journeyUpdatedAt": '+parsed.journey.updatedAt)&&brief.includes('--expected-session'));
 check('Embedded handoff version matches all saved review changes',resume.journeyUpdatedAt===parsed.journey.updatedAt&&resume.contextSha256===parsed.journey.contextSha256);
 check('Browser edits and full save preserve the investigation without refreshing its bases',JSON.stringify(parsed.journey.investigation)===JSON.stringify(before.journey.investigation));
 await page.locator('#reader-close').click();
 await page.locator('#path-link-write').click();await page.locator('#writing-draft').fill('PRIVATE_WORDING: keep shared credit.');await page.locator('#path-continue').click();
 check('Finishing wording returns to private context',await page.locator('#context').isVisible()&&!await page.locator('#profile').isVisible());
 check('Finishing does not create public copy',await page.evaluate(b=>JSON.stringify(packet.publicProfile)===JSON.stringify(b.publicProfile),before));
 const reopenedContext=await makeContext(),reopened=await reopenedContext.newPage();
 await reopened.goto(pathToFileURL(saved).href+'#path-review--'+id);
 check('Correction survives a new browser context with no local storage',await reopened.locator('#review-correction').inputValue()===correction);
 check('Investigation survives reopening the standalone file',await reopened.evaluate(()=>packet.journey.investigation.goal==='PRIVATE_INVESTIGATION_BROWSER'&&packet.journey.investigation.leads[0].status==='ready'));
 for(const width of [320,375,768,1440]){
  await reopened.setViewportSize({width,height:1000});
  check('Review fits '+width,await reopened.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  check('Review heading remains readable at '+width,await reopened.locator('#path-title').evaluate(n=>n.getBoundingClientRect().height<100&&n.getBoundingClientRect().width>180));
  if(width===375||width===1440)await reopened.screenshot({path:path.join(output,'review-'+width+'.png'),fullPage:true});
 }
 await reopenedContext.close();
 const blankContext=await makeContext();
 await blankContext.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw Error('Storage unavailable');}}));
 const blank=await blankContext.newPage();await blank.goto(pathToFileURL(path.resolve(empty)).href);
 check('Empty start offers a working first-account action',await blank.locator('#starting-note').isVisible()&&await blank.locator('#start-handoff').isVisible());
 check('Empty start hides meaningless progress and dead review links',await blank.locator('#path-count').isHidden()&&await blank.locator('#path-continue').isHidden()&&await blank.locator('.path-map-shell').isHidden());
 await blank.locator('#starting-note').fill('PRIVATE_FIRST_ACCOUNT: I organised weekend cover with two volunteers.');
 check('Blocked browser storage is disclosed',(await blank.locator('#path-status').innerText()).includes('storage unavailable'));
 await blank.evaluate(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw Error('blocked');}},configurable:true}));
 const firstDownload=blank.waitForEvent('download');await blank.locator('#start-handoff').press('Enter');
 const firstFile=path.join(output,'first-account-saved.html');await (await firstDownload).saveAs(firstFile);
 check('First-account handoff includes the supplied account',(await fs.readFile(firstFile,'utf8')).includes('PRIVATE_FIRST_ACCOUNT')&&!await blank.locator('#context-reader').isVisible());
 for(const width of [320,375,768,1440]){
  await blank.setViewportSize({width,height:900});
  check('Empty start fits '+width,await blank.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  if(width===375||width===1440)await blank.screenshot({path:path.join(output,'empty-'+width+'.png'),fullPage:true});
 }
 const roundtrip=await makeContext(),recovered=await roundtrip.newPage();await recovered.goto(pathToFileURL(firstFile).href);
 check('Starting notes survive saving despite blocked browser storage',(await recovered.locator('#starting-note').inputValue()).includes('PRIVATE_FIRST_ACCOUNT'));
 await roundtrip.close();
 const raw=await fs.readFile(empty,'utf8');
 const staleFile=path.join(output,'stale-continuation.html');
 await fs.writeFile(staleFile,raw.replace(/(<script id="career-context-data" type="application\/json">)([\s\S]*?)(<\/script>)/,(_,a,text,b)=>{
  const data=JSON.parse(text);data.journey.continuation.contextSha256='0'.repeat(64);return a+JSON.stringify(data).replace(/</g,'\\u003c')+b;
 }));
 await blank.goto(pathToFileURL(staleFile).href);
 check('Stale continuation is disclosed and its hash is not silently refreshed',(await blank.locator('#path-content').innerText()).includes('predates')&&await blank.evaluate(()=>packet.journey.continuation.contextSha256==='0'.repeat(64)));
 await blank.emulateMedia({reducedMotion:'reduce'});
 check('Reduced motion keeps handoff controls still',await blank.locator('#start-handoff').evaluate(n=>getComputedStyle(n).transitionDuration==='0s'));
 check('No script errors',errors.length===0);check('No external requests',requests.length===0);
 await fs.writeFile(path.join(output,'onboarding-results.json'),JSON.stringify({checks,errors,requests},null,2));
 await browser.close();console.log(JSON.stringify({passed:checks.length,errors,requests}));
})().catch(error=>{console.error(error);process.exit(1)});
