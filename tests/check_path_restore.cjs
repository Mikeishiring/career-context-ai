// Run the shipped startup logic without a browser; migration must not outrank saved edits.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../skills/career-context-sheet/assets/path.js'),'utf8');
const startup=code.slice(0,code.indexOf(" const note=document.getElementById('path-note')"));
assert(startup.includes('localStorage.getItem'));
const review={decision:'kept',draft:'Retain this correction',reason:'Source wording',sourceRefs:['source'],depth:'clear',practised:true};
const embedded={contextSha256:'old',updatedAt:100,current:'review',completed:['review'],notes:{review:'embedded note'},storyId:'work',baseline:{overview:'Original',accounts:{work:'Original account'}},reviews:{work:review},writing:{guideName:'',guideText:'',draft:'embedded draft'}};
const saved={...structuredClone(embedded),contextSha256:'current',updatedAt:200,notes:{review:'browser note'},writing:{guideName:'My style',guideText:'Plain words',draft:'browser draft'},coverage:{marker:'browser receipt'},baseline:{overview:'Do not replace the original baseline'}};
function restore(original,draft,{storageFails=false,reviewBasis}={}){
 const packet={accounts:[{id:'work'},{id:'other'}],sources:[{id:'source'},{id:'extra'}],journey:structuredClone(original)};
 const ctx={packet,document:{getElementById:()=>({dataset:{evidence:'current',reviewBasis:reviewBasis&&JSON.stringify(reviewBasis)}})},localStorage:{getItem:()=>{if(storageFails)throw Error('denied');return JSON.stringify(draft);}},Date:{now:()=>1000},coverageError:()=>'',coverageInitial:()=>({})};
 vm.runInNewContext(startup+'\nglobalThis.result={state,changedEvidence};}',ctx);
 return JSON.parse(JSON.stringify(ctx.result));
}
let result=restore(embedded,saved);
assert.equal(result.state.notes.review,'browser note');
assert.equal(result.state.writing.draft,'browser draft');
assert.equal(result.state.reviews.work.decision,'kept');
assert.equal(result.state.coverage.marker,'browser receipt');
assert.equal(result.state.updatedAt,200);
assert.equal(result.state.baseline.overview,'Original');
assert.equal(result.changedEvidence,false);
for(const draft of [null,{...saved,contextSha256:'unrelated'},{...saved,notes:{unknown:'invalid'}}]){
 result=restore(embedded,draft);
 assert.equal(result.state.contextSha256,'current');
 assert.equal(result.state.notes.review,'embedded note');
 assert.equal(result.state.reviews.work.draft,'Retain this correction');
 assert.equal(result.state.reviews.work.decision,'pending');
 assert.equal(result.state.reviews.work.depth,'pending');
 assert.equal(result.state.reviews.work.practised,false);
 assert.deepEqual(result.state.completed,[]);
 assert.equal(result.state.updatedAt,1000);
 assert.equal(result.changedEvidence,true);
}
result=restore({...embedded,contextSha256:'current',updatedAt:300},saved);
assert.equal(result.state.notes.review,'embedded note');
assert.equal(result.state.updatedAt,300);
result=restore(embedded,saved,{storageFails:true});
assert.equal(result.state.notes.review,'embedded note');
console.log('Path restore: matching browser drafts survive evidence migration; invalid/older drafts and unavailable storage handled.');
const basis={accounts:{work:'a'.repeat(64),other:'b'.repeat(64)},sources:{source:'c'.repeat(64),extra:'d'.repeat(64)}};
const reviewed={...structuredClone(embedded),reviewBasis:structuredClone(basis),completed:['gather','review','deepen','connect','write'],reviews:{work:structuredClone(review),other:{...structuredClone(review),sourceRefs:[]}},coverage:{marker:'retain coverage'}};
result=restore(reviewed,null,{reviewBasis:basis});
assert.equal(result.state.reviews.work.decision,'kept');
assert.equal(result.state.reviews.other.decision,'kept');
assert.equal(result.state.coverage.marker,'retain coverage');
assert.deepEqual(result.state.completed,['gather','review','deepen']);
const changed=structuredClone(basis);changed.accounts.work='e'.repeat(64);
result=restore(reviewed,null,{reviewBasis:changed});
assert.equal(result.state.reviews.work.decision,'pending');
assert.equal(result.state.reviews.other.decision,'kept');
assert.equal(result.state.reviews.work.draft,'Retain this correction');
assert.equal(result.state.notes.review,'embedded note');
assert.deepEqual(result.state.completed,['gather']);
// Changed dependency snapshots must reopen reviews even with a matching context fingerprint.
result=restore({...reviewed,contextSha256:'current'},null,{reviewBasis:changed});
assert.equal(result.state.reviews.work.decision,'pending');
assert.equal(result.state.reviews.other.decision,'kept');
// A proposed correction's extra source is also a review dependency.
reviewed.reviews.work.sourceRefs.push('extra');
const sourceChanged=structuredClone(basis);sourceChanged.sources.extra='f'.repeat(64);
result=restore(reviewed,null,{reviewBasis:sourceChanged});
assert.equal(result.state.reviews.work.decision,'pending');
assert.equal(result.state.reviews.other.decision,'kept');
console.log('Review dependencies: overview edits preserve account decisions; changed claims, evidence and correction sources reopen only affected accounts.');
for(const decision of ['correction','needs_evidence']){
 const unresolved=structuredClone(reviewed);unresolved.reviews.work.decision=decision;unresolved.reviews.work.depth='open';
 result=restore(unresolved,null,{reviewBasis:changed});
 assert.equal(result.state.reviews.work.decision,decision);
 assert.equal(result.state.reviews.work.depth,'open');
 assert.equal(result.state.reviews.work.reason,unresolved.reviews.work.reason);
}
console.log('Unresolved corrections remain flagged after dependency changes.');
// Investigation is assistant-authored state; an old browser draft must not replace it.
const investigation={contextSha256:'old-evidence',goal:'Current research',rounds:[],leads:[],stopReason:''};
const incomingResearch={...structuredClone(embedded),contextSha256:'current',investigation};
const browserResearch={...structuredClone(saved),investigation:{goal:'Obsolete or malformed browser research'}};
result=restore(incomingResearch,browserResearch);
assert.deepEqual(result.state.investigation,investigation);
assert.equal(result.state.notes.review,'browser note');
result=restore({...structuredClone(embedded),contextSha256:'current'},browserResearch);
assert.equal(result.state.investigation,undefined);
console.log('Incoming investigation survives browser-note restoration without accepting obsolete research state.');
