// The same evidence must survive changes of listener and personal story choice.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

async function main() {
  const [input, output] = process.argv.slice(2);
  const url = pathToFileURL(path.resolve(input)).href;
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge'});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 920}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => Object.defineProperty(navigator, 'clipboard', {value: {
      writeText: async text => { window.copiedRehearsal = text; }
    }}));
    await page.goto(url + '#interview');
    const accounts = await page.evaluate(() => packet.accounts);
    const intake = accounts[0].questions[0];
    await page.locator('#cue-context summary').click();
    assert.ok((await page.locator('#cue-gaps li').allTextContents()).includes(intake));
    await page.locator('#copy-clarification').click();
    assert.ok((await page.evaluate(() => window.copiedRehearsal)).includes(intake));
    await page.locator('#rehearse-copy').click();
    assert.ok(!(await page.evaluate(() => window.copiedRehearsal)).includes(intake));
    const [,guide,prototype] = accounts;
    const storyPicker = page.locator('#rehearsal-story');
    assert.equal(await storyPicker.inputValue(), accounts[0].id);
    assert.equal(await page.locator('#rehearsal-list').getByText('Want to tell').count(), 0);
    await page.goto(url + '#story-review');
    await page.locator('[data-review-story="'+guide.id+'"]').click();
    await page.locator('#review-sheet button[value=lead]').click();
    await page.goto(url + '#interview');
    assert.equal(await storyPicker.inputValue(), guide.id);
    assert.ok(await page.locator('#cue-context').isHidden());
    await page.reload();
    assert.equal(await storyPicker.inputValue(), guide.id);
    const before = await page.evaluate(() => JSON.stringify(packet.accounts));
    const radio = key => page.locator('input[name="prep-audience"][value="'+key+'"]');
    for (const key of ['recruiter','manager','panel']) {
      await radio(key).focus();
      await page.keyboard.press('Space');
      const expected = await page.evaluate(({key,id}) => packet.interview.stories.find(s=>s.id===id).audiences[key], {key,id:guide.id});
      assert.equal(await page.locator('#cue-opening').innerText(), expected.opening);
      assert.equal(await page.locator('#cue-question').innerText(), expected.question);
      await page.locator('.audience-track').evaluate(el=>Promise.all(el.getAnimations({subtree:true}).map(a=>a.finished)));
      await page.locator('#rehearsal-room').screenshot({path: path.join(output, 'rehearsal-'+key+'.png')});
      await page.locator('#rehearse-copy').click();
      const copied = await page.evaluate(() => window.copiedRehearsal);
      assert.ok(copied.includes(expected.opening) && copied.includes(expected.question));
      assert.ok(copied.includes(guide.sharedCredit) && !copied.includes(prototype.title));
    }
    assert.equal(await page.evaluate(() => JSON.stringify(packet.accounts)), before);
    await page.locator('#cue-title').click();
    assert.equal(await page.locator('#cue-opening').isVisible(),false);
    await page.locator('#rehearse-copy').click();
    const cold=await page.evaluate(()=>window.copiedRehearsal);
    assert.ok(cold.includes(await page.locator('#cue-question').innerText())&&!cold.includes('Opening to practise:'));
    await page.locator('#cue-title').click();
    await page.locator('.cue-evidence summary').click();
    assert.ok((await page.locator('#cue-evidence').innerText()).includes(guide.limits[0]));
    await page.locator('.cue-evidence summary').click();
    for (const width of [1440,768,375,320]) {
      await page.setViewportSize({width,height:900});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), 'overflow at '+width);
      if (width===375) await page.screenshot({path:path.join(output,'rehearsal-mobile.png')});
    }
    await storyPicker.selectOption(prototype.id);
    assert.ok((await page.locator('#cue-opening').innerText()).includes('fictional items'));
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('.audience-track').evaluate(n=>getComputedStyle(n,'::before').transitionDuration),'0s');
    await radio('manager').focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await radio('panel').isChecked(),true);
    await page.locator('#rehearse-notes').click();
    assert.ok(await page.locator('#prep-story-'+prototype.id).evaluate(n=>n.open));
    await page.goto(url+'#rehearse-'+guide.id);
    assert.equal(await storyPicker.inputValue(),guide.id);
    assert.ok(await page.locator('.audience-switch').isVisible());
    // Older prepared stories and unprepared accounts use verbatim account fields.
    await page.evaluate(id => {
      const account=packet.accounts.find(a=>a.id===id);
      audienceDesk.show(account, undefined);
    },guide.id);
    assert.equal(await page.locator('#cue-opening').textContent(),guide.contribution+'\n\n'+guide.sharedCredit);
    assert.equal(await page.locator('#cue-question q').count(),0);
    const panelQuestion=await page.locator('#cue-question').innerText();
    assert.ok(panelQuestion.length>10);
    await radio('manager').focus();await page.keyboard.press('Space');
    assert.equal(await page.locator('#cue-question q').textContent(),guide.decisions[0]);
    const legacy=await page.evaluate(()=>{
      const solo={title:'Desk log',summary:'I tested a desk log.',contribution:'I tested it alone.',sharedCredit:'',aim:'Check the desk log.',decisions:['Keep the original log.'],questions:['Which employer was this?'],id:'solo'};
      const other={...solo,id:'other',title:'Second log',decisions:['Keep the second log.']};
      return {
        panel:rehearsalCue(solo,null,'panel'),
        accountOnly:rehearsalCue(solo,null,'recruiter'),
        manager:rehearsalCue(solo,null,'manager'),
        recruiter:rehearsalCue(solo,null,'recruiter',[{storyId:'other',question:'Wrong question?'},{storyId:'solo',question:'Why use a desk log?'}]),
        otherPrompt:audienceDesk.instructions(other,null)
      };
    });
    assert.equal(legacy.panel.opening,'I tested it alone.');
    assert.equal(legacy.accountOnly.question,'How did you try to check the desk log?');
    assert.equal(legacy.manager.question,'What went into the decision to keep the original log?');
    assert.equal(legacy.recruiter.question,'Why use a desk log?');
    assert.ok(legacy.otherPrompt.includes('keep the second log?')&&!legacy.otherPrompt.includes(guide.title));
    await page.goto(url+'#story-review');
    await page.setViewportSize({width:1200,height:900});
    for(const a of accounts){
      await page.locator('[data-review-story="'+a.id+'"]').click();
      await page.locator('#review-sheet button[value=reserve]').click();
    }
    await page.goto(url+'#interview');
    assert.equal(await storyPicker.inputValue(),'');
    assert.ok(await page.locator('#rehearsal-empty').isVisible());
    await page.locator('#rehearsal-list button[value="'+guide.id+'"]').click();
    assert.ok(await page.locator('#audience-desk').isVisible());
    assert.deepEqual(errors,[]);
    console.log('Passed audience openings, practice prompts, unchanged evidence, restored preferences, keyboard, reduced motion, four widths, deep links, legacy accounts and reserve-only selection.');
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
