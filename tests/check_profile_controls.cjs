// Run the shipped Profile event handlers with a small DOM/storage test double.
// This checks state and handler wiring, not native focus, layout or browser events.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const asset=name=>fs.readFileSync(path.join(__dirname,'../skills/career-context-sheet/assets',name),'utf8');
const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
class Text {
 constructor(value){this.value=String(value);}
 get textContent(){return this.value;}
 get outerHTML(){return escape(this.value);}
}
class Element {
 constructor(tag,document){this.tag=tag;this.document=document;this.children=[];this.attrs={};this.events={};this.dataset={};this.hidden=false;this.disabled=false;this.checked=false;}
 append(...nodes){for(const node of nodes){const n=typeof node==='string'?new Text(node):node;n.parent=this;this.children.push(n);}}
 prepend(...nodes){this.children.unshift(...nodes);for(const node of nodes)node.parent=this;}
 replaceChildren(...nodes){for(const node of this.children)node.parent=null;this.children=[];this.append(...nodes);}
 set textContent(value){this.replaceChildren(new Text(value));}
 get textContent(){return this.children.map(n=>n.textContent).join('');}
 setAttribute(key,value){this.attrs[key]=String(value);}
 getAttribute(key){return this.attrs[key]??(this[key]===undefined?null:String(this[key]));}
 removeAttribute(key){delete this.attrs[key];}
 addEventListener(type,handler){(this.events[type]??=[]).push(handler);}
 dispatch(type){const event={type,target:this,currentTarget:this};this['on'+type]?.(event);for(const fn of this.events[type]||[])fn(event);}
 click(){if(this.disabled)return;this.focus();if(this.type==='checkbox')this.checked=!this.checked;this.dispatch('click');if(this.type==='checkbox')this.dispatch('change');}
 focus(){if(!this.disabled)this.document.activeElement=this;}
 descendants(){return this.children.flatMap(n=>n instanceof Element?[n,...n.descendants()]:[]);}
 matches(selector){
  const tag=selector.match(/^[a-z]+/);if(tag&&tag[0]!==this.tag)return false;
  const id=selector.match(/#([\w-]+)/);if(id&&this.id!==id[1])return false;
  const cls=selector.match(/\.([\w-]+)/);if(cls&&!(this.className||'').split(' ').includes(cls[1]))return false;
  for(const [,key,quoted,bare] of selector.matchAll(/\[([\w-]+)=(?:"([^"]*)"|([^\]]+))\]/g))if(this.getAttribute(key)!==(quoted??bare))return false;
  return true;
 }
 querySelectorAll(selector){
  const parts=selector.match(/(?:\[[^\]]+\]|[^\s])+/g);
  return this.descendants().filter(node=>{
   if(!node.matches(parts.at(-1)))return false;
   let parent=node.parent;
   for(let i=parts.length-2;i>=0;i--){while(parent&&!parent.matches(parts[i]))parent=parent.parent;if(!parent)return false;parent=parent.parent;}
   return true;
  });
 }
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 get outerHTML(){
  const attrs={...this.attrs};
  for(const [prop,key] of Object.entries({id:'id',className:'class',src:'src',alt:'alt',loading:'loading',tabIndex:'tabindex',href:'href',target:'target',rel:'rel',lang:'lang',name:'name',content:'content',httpEquiv:'http-equiv'}))if(this[prop]!==undefined)attrs[key]=this[prop];
  const open='<'+this.tag+Object.entries(attrs).map(([k,v])=>' '+k+'="'+escape(v)+'"').join('')+'>';
  return open+(['img','meta','input'].includes(this.tag)?'':this.children.map(n=>this.tag==='style'?n.textContent:n.outerHTML).join('')+'</'+this.tag+'>');
 }
}
function document(){
 const doc={createElement:tag=>new Element(tag,doc),createTextNode:value=>new Text(value)};
 doc.documentElement=doc.createElement('html');doc.head=doc.createElement('head');doc.body=doc.createElement('body');doc.documentElement.append(doc.head,doc.body);
 doc.getElementById=id=>doc.documentElement.descendants().find(n=>n.id===id)||null;
 doc.querySelector=selector=>doc.documentElement.querySelector(selector);
 doc.querySelectorAll=selector=>doc.documentElement.querySelectorAll(selector);
 doc.implementation={createHTMLDocument:()=>document()};return doc;
}
const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGOQ0NAAAAFMAJnVf7vDAAAAAElFTkSuQmCC';
const initial={contextSha256:'a'.repeat(64),updatedAt:1,name:'Contributor 01',headline:'Shared practical work',overview:'An authored introduction.',shareOverview:true,northStar:'Make help easier to ask for.',shareNorthStar:true,direction:'Keep a small practical commitment.',shareDirection:true,
 examples:[{title:'Session card',summary:'Drafted with another volunteer.',synthetic:true,included:true,detail:'PRIVATE_DETAIL',shareDetail:true}],
 timeline:[{period:'2022',title:'Learning',summary:'Supervised work.',included:true},{period:'2025',title:'Smaller commitment',summary:'Later use unknown.',included:true},{period:'Summer 2024',title:'Parallel work',summary:'Shared contribution.',included:false}],
 media:[{id:'sample',kind:'image',title:'Session card',alt:'A mock paper card',caption:'Draft state only.',credit:'Shared work.',dataUrl:image,included:false},
 {id:'recording',kind:'video',title:'Recording',url:'https://example.org/watch',caption:'Selected clip.',credit:'Another volunteer filmed it.',included:true},
 {id:'unfinished',kind:'video',title:'Unfinished video',url:'unfinished draft',caption:'',credit:'',included:false}]};
function launch(storage=new Map(),failStorage=false){
 const doc=document(),root=doc.createElement('section');root.id='profile';root.dataset.evidence=initial.contextSha256;doc.body.append(root);
 for(const id of ['public-status','public-editor','public-preview','public-export','public-empty','public-freshness','public-mark-reviewed','public-share-count','public-edit-tab','public-preview-tab','public-save','save-html','public-sharing','public-profile-styles']){
  const node=doc.createElement(id.includes('tab')||id==='public-export'?'button':'div');node.id=id;root.append(node);
 }
 doc.getElementById('public-editor').hidden=true;doc.getElementById('public-profile-styles').textContent=asset('public-profile.css');
 const sharing=doc.createElement('details');sharing.className='public-sharing';root.append(sharing);
 const packet={synthetic:true,publicProfile:structuredClone(initial)},downloads=[];
 const context=vm.createContext({document:doc,packet,URL,atob,Date,console,localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>{if(failStorage)throw Error('storage unavailable');storage.set(key,value);}},download:(name,type,content)=>downloads.push({name,type,content})});
 vm.runInContext(asset('public-profile.js'),context);
 return {doc,packet,context,downloads,storage,id:id=>doc.getElementById(id)};
}
const app=launch();
app.id('share-example-0').click();
assert.equal(app.packet.publicProfile.examples[0].included,false);
assert.equal(app.id('share-detail-0').disabled,true);
assert.equal(app.packet.publicProfile.examples[0].shareDetail,true);
assert(!app.id('public-preview').textContent.includes('PRIVATE_DETAIL'));
app.id('share-example-0').click();
assert.equal(app.id('share-detail-0').disabled,false);
assert(app.id('public-preview').textContent.includes('PRIVATE_DETAIL'));
app.id('share-detail-0').click();
app.id('public-edit-tab').click();
const optional=app.packet.publicProfile.timeline[2];
app.id('public-year-up-2').click();
assert.equal(app.packet.publicProfile.timeline[1],optional);
assert.equal(optional.included,false);
assert.equal(app.doc.activeElement,app.id('public-year-up-1'));
app.id('public-year-up-1').click();
assert.equal(app.id('public-year-up-0').disabled,true);
assert.equal(app.doc.activeElement,app.id('public-year-down-0'));
app.id('public-year-down-0').click();
app.id('share-year-1').click();
assert.equal(optional.included,true);
assert.deepEqual(Array.from(app.context.publicProjection(app.packet.publicProfile).timeline,e=>e.period),['2022','Summer 2024','2025']);
app.id('share-media-0').click();app.id('public-preview-tab').click();app.id('public-export').click();
let exported=app.downloads.at(-1).content;
assert(exported.includes(image));assert(exported.includes('https://example.org/watch'));
assert(!exported.includes('PRIVATE_DETAIL'));assert(!exported.includes('unfinished draft'));
app.id('share-media-0').click();app.id('public-export').click();
assert(!app.downloads.at(-1).content.includes(image));
const restored=launch(app.storage);
assert.deepEqual(JSON.parse(JSON.stringify(restored.packet.publicProfile)),JSON.parse(JSON.stringify(app.packet.publicProfile)));
restored.id('public-edit-tab').click();
const urls=restored.doc.querySelectorAll('input[aria-label="Video URL"]');
assert.equal(urls.length,2);
assert.equal(urls[1].getAttribute('aria-invalid'),'true','Saved invalid URL must explain why sharing is disabled when Edit opens');
const errorId=urls[1].getAttribute('aria-describedby');
assert(errorId&&restored.id(errorId).textContent.includes('HTTPS'));
assert.equal(restored.id('share-media-2').disabled,true);
assert(restored.id('share-media-2').parent.textContent.includes('Fix the link in Edit'));
urls[1].value='https://example.org/another';urls[1].dispatch('input');
assert.equal(urls[1].getAttribute('aria-invalid'),'false');
assert.equal(restored.id(errorId).hidden,true);
assert.equal(restored.id('share-media-2').disabled,false);
assert.equal(restored.packet.publicProfile.media[2].included,false,'Repairing a link must not select it for sharing');
urls[0].value='http://example.org/wrong';urls[0].dispatch('input');
assert.equal(restored.packet.publicProfile.media[1].included,false);
assert.equal(restored.id('share-media-1').disabled,true);
restored.id('public-preview-tab').click();restored.id('public-edit-tab').click();
const reopened=restored.doc.querySelectorAll('input[aria-label="Video URL"]');
assert.equal(reopened[0].getAttribute('aria-invalid'),'true');
reopened[1].value='http://example.org/also-wrong';reopened[1].dispatch('input');
reopened[0].value='https://example.org/watch';reopened[0].dispatch('input');
assert.equal(reopened[0].getAttribute('aria-invalid'),'false');
assert.equal(reopened[1].getAttribute('aria-invalid'),'true');
assert.equal(restored.id(reopened[1].getAttribute('aria-describedby')).hidden,false);
assert.equal(restored.packet.publicProfile.media[1].included,false);
const unavailable=launch(new Map(),true);
unavailable.id('share-north-star').click();
assert.equal(unavailable.packet.publicProfile.shareNorthStar,false);
assert(unavailable.id('public-status').textContent.includes('storage unavailable'));
assert(!unavailable.id('public-status').textContent.includes('Saved'));
console.log('Profile handler checks passed: sharing/detail gates, period moves and focus calls, saved drafts, export exclusion, persistent link errors and storage failure. No browser used.');
