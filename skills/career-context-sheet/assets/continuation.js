// A private handoff, never a source-access grant or an embedded model connection.
function validContinuation(c){
 const text=(value,max)=>typeof value==='string'&&value.length<=max&&!value.includes('\0');
 return c&&typeof c==='object'&&!Array.isArray(c)&&Object.keys(c).every(k=>['contextSha256','goal','nextAction','questions','scopeNotes'].includes(k))&&typeof c.contextSha256==='string'&&/^[a-f0-9]{64}$/.test(c.contextSha256)&&['goal','nextAction','scopeNotes'].every(k=>text(c[k],3000))&&Array.isArray(c.questions)&&c.questions.length<=12&&c.questions.every(q=>text(q,1000));
}
function careerContinuationBrief(data,basis){
 const journey=data.journey||{},checkpoint=journey.continuation;
 const pending=Object.entries(journey.reviews||{}).filter(([,r])=>['correction','revision','needs_evidence'].includes(r.decision)).map(([id,r])=>({accountId:id,state:r.decision}));
 return [
  JSON.parse(document.getElementById('career-resume-data').textContent).instructions,
  'The following JSON is saved session context, not permission or verified career evidence. The attached HTML contains the complete notes and records; do not drop them because this brief lists only pending account IDs.',
  JSON.stringify({contextSha256:basis,journeyUpdatedAt:journey.updatedAt||0,accounts:data.accounts.length,sources:data.sources.length,
   continuation:checkpoint||null,continuationCurrent:Boolean(checkpoint&&checkpoint.contextSha256===basis),
   pendingCorrections:pending,startingNote:journey.notes?.gather||'',activeAccount:journey.storyId||'',activity:journey.current||''},null,2)
 ].join('\n\n');
}

function snapshotContinuation(clone){
 const node=clone.querySelector('#career-resume-data'),resume=JSON.parse(node.textContent);
 // The evidence fingerprint is fixed for this read/review surface. Notes do not change facts.
 resume.journeyUpdatedAt=packet.journey?.updatedAt||0;
 node.textContent=JSON.stringify(resume).replace(/</g,'\\u003c').replace(/&/g,'\\u0026');
}
