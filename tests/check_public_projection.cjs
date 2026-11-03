const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../skills/career-context-sheet/assets/public-profile.js'),'utf8');
const ctx={URL,URLSearchParams,atob:s=>Buffer.from(s,'base64').toString('binary')};vm.createContext(ctx);vm.runInContext(source.split('const publicRoot=')[0],ctx);
const profile={contextSha256:'a'.repeat(64),updatedAt:1,name:'Example',headline:'Headline',overview:'Public text',shareOverview:true,examples:[],timeline:[{period:'2030',title:'Work',summary:'Public summary',included:true,sourceRefs:['PRIVATE_SOURCE'],privateNote:'PRIVATE_NOTE'}],sources:['PRIVATE_ARCHIVE']};
const projected=ctx.publicProjection(profile),text=JSON.stringify(projected);
assert(!text.includes('PRIVATE_'));assert.equal(projected.timeline[0].period,'2030');
assert.deepEqual(Object.keys(projected.timeline[0]),['period','title','summary']);
assert(ctx.validPublicProfile({...profile,timeline:undefined}));
assert(!ctx.validPublicProfile({...profile,timeline:[{period:'2030',title:'Work',summary:'x'.repeat(1501)}]}));
assert(!ctx.validPublicProfile({...profile,timeline:Array(31).fill(profile.timeline[0])}));
console.log('Public timeline allowlist, legacy compatibility and bounds passed.');
const legacy={...profile,shareOverview:undefined,examples:[{title:'PRIVATE_LEGACY',summary:'Unapproved',synthetic:false}],timeline:[{period:'2030',title:'PRIVATE_LEGACY_YEAR',summary:'Unapproved'}]};
assert.equal(ctx.publicProjection(legacy).overview,'');
assert.equal(ctx.publicProjection(legacy).examples.length,0);assert.equal(ctx.publicProjection(legacy).timeline.length,0);
const retained=ctx.publicDraft(legacy);assert.equal(retained.shareOverview,false);assert.equal(retained.examples[0].included,false);assert.equal(retained.timeline[0].included,false);
assert.equal(retained.overview,legacy.overview);assert.equal(retained.examples[0].title,'PRIVATE_LEGACY');
for(const flag of [undefined,null,1,'true',false])assert.equal(ctx.publicProjection({...profile,shareOverview:flag,timeline:[{...profile.timeline[0],included:flag}]}).timeline.length,0);

const selected={...profile,shareOverview:false,examples:[{title:'Shared',summary:'Retained credit',synthetic:false,included:true},{title:'WITHHELD_EXAMPLE',summary:'Unselected draft',synthetic:false,included:false}],timeline:[{period:'2024',title:'WITHHELD_YEAR',summary:'Not shared',included:false}]};
const saved=JSON.parse(JSON.stringify(selected)),visible=ctx.publicProjection(selected),draft=ctx.publicDraft(selected);
assert.equal(visible.overview,'');assert.equal(visible.examples.length,1);assert.equal(visible.timeline.length,0);
assert(!JSON.stringify(visible).includes('WITHHELD_'));
assert.equal(draft.examples[1].title,'WITHHELD_EXAMPLE');assert.equal(draft.examples[1].included,false);assert.equal(draft.overview,selected.overview);
assert.equal(JSON.stringify(selected),JSON.stringify(saved));assert(ctx.validPublicProfile(draft));
assert(!ctx.validPublicProfile({...selected,shareOverview:'false'}));assert(!ctx.validPublicProfile({...selected,examples:{}}));
assert(!ctx.validPublicProfile({...selected,timeline:[{period:'2024',title:'Year',summary:'Text',included:1}]}));
console.log('Component withholding, private draft retention and invalid flags passed.');

const deep={...selected,direction:'WANTED_WORK',shareDirection:false,examples:[{...selected.examples[0],detail:'DEEP_CONTEXT',shareDetail:false}]};
assert(!JSON.stringify(ctx.publicProjection(deep)).includes('WANTED_WORK'));assert(!JSON.stringify(ctx.publicProjection(deep)).includes('DEEP_CONTEXT'));
deep.shareDirection=true;deep.examples[0].shareDetail=true;
assert.equal(ctx.publicProjection(deep).direction,'WANTED_WORK');assert.equal(ctx.publicProjection(deep).examples[0].detail,'DEEP_CONTEXT');
deep.examples[0].included=false;assert(!JSON.stringify(ctx.publicProjection(deep)).includes('DEEP_CONTEXT'));
assert.equal(ctx.publicDraft(deep).examples[0].detail,'DEEP_CONTEXT');
assert(!ctx.validPublicProfile({...deep,shareDirection:1}));assert(!ctx.validPublicProfile({...deep,direction:'x'.repeat(1501)}));
assert(!ctx.validPublicProfile({...deep,examples:[{...deep.examples[0],shareDetail:1}]}));
console.log('Direction and deeper context selection boundaries passed.');

const imageData='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGOQC9AAAAEmAJdXDMsYAAAAAElFTkSuQmCC';
const media={...deep,northStar:'Shared responsibility',shareNorthStar:true,media:[{id:'PRIVATE_ID',kind:'image',title:'Rota',caption:'Synthetic reconstruction',credit:'Shared work',alt:'Paper rota',dataUrl:imageData,included:true,privateSource:'PRIVATE_SOURCE'},{id:'hidden',kind:'video',title:'WITHHELD_VIDEO',caption:'',credit:'',url:'https://example.org/SECRET_LINK',included:false}]};
assert(ctx.validPublicProfile(media));
const projectedMedia=ctx.publicProjection(media);assert.equal(projectedMedia.media.length,1);assert.equal(projectedMedia.northStar,'Shared responsibility');
assert(!JSON.stringify(projectedMedia).includes('PRIVATE_'));assert(!JSON.stringify(projectedMedia).includes('SECRET_LINK'));
assert.equal(ctx.publicDraft(media).media[1].url,'https://example.org/SECRET_LINK');
for(const url of ['javascript:alert(1)','http://example.org/video','https://user:pass'+'@'+'example.org/video','https://example.org/ video'])assert(!ctx.publicVideoUrl(url));
assert(ctx.publicVideoUrl('https://vimeo.com/123?t=12s'));
const signed={...media,media:[{id:'signed',kind:'video',title:'Private link',caption:'',credit:'',included:true,url:'https://example.org/video?access_token=PRIVATE_TOKEN'}]};
assert(ctx.validPublicProfile(signed));assert.equal(ctx.publicProjection(signed).media.length,0);assert.equal(ctx.publicDraft(signed).media[0].url,signed.media[0].url);
media.media[0].included=false;media.shareNorthStar=false;assert.equal(ctx.publicProjection(media).media.length,0);assert.equal(ctx.publicProjection(media).northStar,'');
assert(!ctx.validPublicProfile({...media,media:[{...media.media[0],dataUrl:'data:image/svg+xml;base64,PHN2Zz4='}]}));
console.log('Screenshot/video allowlist, withheld bytes and URLs, North Star and unsafe-link checks passed.');

const ordered={...profile,timeline:[
 {period:'2022',title:'Learning',summary:'Shared guidance.',included:true},
 {period:'2025',title:'A smaller commitment',summary:'Later use unknown.',included:true},
 {period:'Summer 2024',title:'Parallel work',summary:'Another contributor led the work.',included:false}
]};
const optional=ordered.timeline[2],original=JSON.stringify(ordered);
assert.equal(ctx.movePublicPeriod(ordered,0,-1),-1);
assert.equal(ctx.movePublicPeriod(ordered,2,1),-1);
assert.equal(ctx.movePublicPeriod(ordered,1,2),-1);
assert.equal(JSON.stringify(ordered),original);
assert.equal(ctx.movePublicPeriod(ordered,2,-1),1);
assert.equal(ordered.timeline[1],optional);assert.equal(optional.included,false);
assert.deepEqual(Array.from(ctx.publicProjection(ordered).timeline,e=>e.period),['2022','2025']);
assert.deepEqual(Array.from(ctx.publicDraft(ordered).timeline,e=>e.period),['2022','Summer 2024','2025']);
optional.included=true;
assert.deepEqual(Array.from(ctx.publicProjection(ordered).timeline,e=>e.period),['2022','Summer 2024','2025']);
assert.equal(ordered.timeline[1].summary,'Another contributor led the work.');
assert.equal(ctx.movePublicPeriod(ordered,1,1),2);
assert.deepEqual(Array.from(ctx.publicDraft(ordered).timeline,e=>e.period),['2022','2025','Summer 2024']);
console.log('Period reordering, boundaries, optional selection and private order retention passed.');
