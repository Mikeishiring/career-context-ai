// Run the shipped startup logic without a browser; migration must not outrank saved edits.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../skills/career-context-sheet/assets/path.js'),'utf8');
const startup=code.slice(0,code.indexOf(" const note=document.getElementById('path-note')"));
assert(startup.includes('localStorage.getItem'));
const review={decision:'kept',draft:'Retain this correction',reason:'Source wording',sourceRefs:['source'],depth:'clear',practised:true};
const embedded={contextSha256:'old',updatedAt:100,current:'review',completed:['review'],notes:{review:'embedded note'},storyId:'work',baseline:{overview:'Original',accounts:{work:'Original account'}},reviews:{work:review},writing:{guideName:'',guideText:'',draft:'embedded draft'}};
const saved={...structuredClone(embedded),contextSha256:'current',updatedAt:200,notes:{review:'browser note'},writing:{guideName:'My style',guideText:'Plain words',draft:'browser draft'},coverage:{marker:'browser receipt'},baseline:{overview:'Do not replace the original baseline'}};
function restore(original,draft,{storageFails=false}={}){
 const packet={accounts:[{id:'work'}],sources:[{id:'source'}],journey:structuredClone(original)};
 const ctx={packet,document:{getElementById:()=>({dataset:{evidence:'current'}})},localStorage:{getItem:()=>{if(storageFails)throw Error('denied');return JSON.stringify(draft);}},Date:{now:()=>1000},coverageError:()=>'',coverageInitial:()=>({})};
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
