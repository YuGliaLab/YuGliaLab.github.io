'use strict';
// Canvas enhancement: the static page never runs scripts; this trusted parent owns editing.
let canvasMode='content', selection=null, elements=new Map(), history=[], historyIndex=-1, historyTimer, applying=false;
const inspector=$('content'), canvas=$('preview');
$('contentTab').textContent='Edit site';$('previewTab').textContent='Preview';$('save').textContent='Save';
$('previewPanel').hidden=false;
const workspace=document.createElement('div');workspace.id='workspace';$('content').before(workspace);workspace.append($('previewPanel'),$('content'));
$('content').querySelector('.intro').innerHTML='<small>INSPECTOR</small><h2 id="selectionTitle">Select an element</h2><p>Click text or an image on the page. Double-click text to type directly.</p>';
$('previewPanel').querySelector('.preview-tools p').textContent='Click to select · Double-click text to edit';
const canvasBar=document.createElement('div');canvasBar.id='canvasBar';canvasBar.innerHTML='<button id="undo" title="Undo last unsaved change">↶ Undo</button><button id="redo" title="Redo">↷ Redo</button><span class="bar-divider"></span><button id="desktop">▱ Desktop</button><button id="phone">▯ Mobile</button><label>Zoom <select id="zoom"><option value="0.65">65%</option><option value="0.8">80%</option><option value="1" selected>100%</option></select></label><span class="canvas-label">LOCAL EDITOR</span>';
$('previewPanel').prepend(canvasBar);$('mobile').hidden=true;
const controls=document.createElement('section');controls.id='design';controls.className='panel';controls.innerHTML='<h3>Design & position</h3><div class="control-grid"><label>Text size<input id="fontSize" type="number" min="8" max="150" placeholder="Original"></label><label>Text color<input id="textColor" type="color" value="#222222"></label><label>Horizontal offset<input id="posX" type="number" min="-4000" max="4000" value="0"></label><label>Vertical offset<input id="posY" type="number" min="-4000" max="4000" value="0"></label><label>Width (px)<input id="elementWidth" type="number" min="20" max="4000" placeholder="Original"></label><label>Alignment<select id="align"><option value="">Original</option><option>left</option><option>center</option><option>right</option></select></label></div><button id="resetPosition">Reset position & width</button><p class="help">Drag the blue Move handle on the canvas. Drag its bottom-right corner to resize. Check mobile after changing placement.</p>';
$('blocks').before(controls);
const sideActions=document.createElement('div');sideActions.className='side-actions';sideActions.innerHTML='<button id="addSection">＋ Add section</button><button id="layersToggle">☷ Page layers</button><div id="layers" hidden></div>';$('pages').after(sideActions);
$('addPanel').hidden=true;
$('addSection').onclick=()=>{if(page.page==='layout')return notice('Choose a page before adding a section.');recordHistory();tab('content');$('addPanel').hidden=false;$('newEntry').hidden=false;$('entryTitle').focus();inspector.scrollTop=inspector.scrollHeight;recordHistory();};
$('layersToggle').onclick=()=>{$('layers').hidden=!$('layers').hidden;};
const baseRender=render;
render=function(){baseRender();selection=null;history=[];historyIndex=-1;$('addPanel').hidden=true;$('design').hidden=true;$('selectionTitle').textContent='Select an element';document.querySelectorAll('.block,.image-row').forEach(e=>e.hidden=true);$('images').closest('.panel').hidden=true;};
tab=function(name){canvasMode=name;workspace.hidden=name==='changes';$('changesPanel').hidden=name!=='changes';$('previewPanel').hidden=false;inspector.hidden=name!=='content';workspace.classList.toggle('preview-only',name==='preview');for(const item of ['content','preview','changes'])$(item+'Tab').setAttribute('aria-pressed',String(item===name));setEditing();};
$('previewTab').onclick=()=>{tab('preview');notice(dirty?'Preview includes your unsaved edits. Save to keep them on this computer.':'Preview of your website.');};
$('contentTab').onclick=()=>tab('content');
$('save').onclick=()=>action(async()=>{await save();tab('content');});
function model(key){const [kind,id]=key.split(':');return (kind==='text'?page.blocks:page.images).find(x=>x.id===Number(id));}
function editorFor(key){return document.querySelector('.editor[data-id="'+key.split(':')[1]+'"]');}
function layout(el,data){el.style.translate=Number(data.x||0)+'px '+Number(data.y||0)+'px';if(data.width)el.style.width=data.width+'px';else if(el.dataset.cmsWidth||el.dataset.visualWidth){el.style.removeProperty('width');}el.dataset.visualWidth=data.width||'';}
function canvasCSS(){return `html{scroll-behavior:smooth} [data-studio-key]{cursor:pointer!important;transition:outline-color .12s} body.studio-edit [data-studio-key]:hover{outline:1px dashed #2677ff!important;outline-offset:3px} body.studio-edit [data-studio-key].studio-selected{outline:2px solid #2677ff!important;outline-offset:3px} [contenteditable=true]{cursor:text!important;outline:2px solid #2677ff!important} #studio-move{position:absolute;z-index:2147483646;display:none;padding:6px 12px;border:0;border-radius:5px;background:#1667ee;color:white;font:12px Arial;cursor:move;touch-action:none} #studio-resize{position:absolute;z-index:2147483646;display:none;width:12px;height:12px;border:2px solid #1667ee;background:white;cursor:nwse-resize;touch-action:none}`;}
function attachCanvas(){
 const doc=canvas.contentDocument;if(!doc||!page)return;elements=new Map();const style=doc.createElement('style');style.textContent=canvasCSS();doc.head.append(style);
 const main=doc.querySelector('main');const candidates=(selector)=>[...doc.querySelectorAll(selector)].filter(e=>page.page==='layout'?!main?.contains(e):main?.contains(e));
 for(const [kind,list,selector]of [['text',page.blocks,'[data-testid="richTextElement"]'],['image',page.images,'img']]){
  const choices=candidates(selector);
  for(const item of list){const el=(item.domId?doc.getElementById(item.domId):null)||choices[item.id];if(!el)continue;const key=kind+':'+item.id;el.dataset.studioKey=key;elements.set(key,el);
   el.addEventListener('click',e=>{if(canvasMode!=='content')return;e.stopPropagation();if(kind==='image')e.preventDefault();select(key);});
   el.addEventListener('dblclick',e=>{if(canvasMode!=='content'||kind!=='text')return;e.preventDefault();select(key);el.contentEditable='true';el.focus();doc.execCommand('defaultParagraphSeparator',false,'p');});
   el.addEventListener('input',()=>{if(kind!=='text')return;editorFor(key).innerHTML=el.innerHTML;changedBlocks.add(item.id);mark();queueHistory();});
   el.addEventListener('paste',e=>{e.preventDefault();doc.execCommand('insertText',false,e.clipboardData.getData('text/plain'));});
   el.addEventListener('blur',()=>{el.contentEditable=canvasMode==='content'?'true':'false';});
  }
 }
 const handle=doc.createElement('button');handle.id='studio-move';handle.textContent='⠿ Move';doc.body.append(handle);const resize=doc.createElement('div');resize.id='studio-resize';doc.body.append(resize);
 installDrag(handle,false);installDrag(resize,true);
 doc.addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;if(canvasMode==='content'){e.preventDefault();return;}const url=new URL(a.href);if(url.origin===location.origin&&url.pathname.startsWith('/preview/')){e.preventDefault();const key=url.pathname.slice(9).split('/')[0]||'index';if(document.querySelector('nav button[data-page="'+CSS.escape(key)+'"]'))action(async()=>{await showPage(key);tab('preview');});}},true);
 doc.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();$('save').click();}});
 doc.addEventListener('scroll',positionHandles,true);
 applyCanvas();setEditing();buildLayers();recordHistory();
}
function setEditing(){const doc=canvas.contentDocument;if(!doc)return;doc.body?.classList.toggle('studio-edit',canvasMode==='content');for(const [key,el] of elements)if(key.startsWith('text:'))el.contentEditable=canvasMode==='content'?'true':'false';positionHandles();}
function select(key){selection=key;const item=model(key);if(!item)return;tab('content');$('addPanel').hidden=true;$('selectionTitle').textContent=key.startsWith('text:')?'Text settings':'Image settings';$('design').hidden=false;
 document.querySelectorAll('.block').forEach((el,i)=>{el.hidden=key!=='text:'+page.blocks[i].id;el.open=!el.hidden;});
 const image=key.startsWith('image:');$('images').closest('.panel').hidden=!image;document.querySelectorAll('.image-row').forEach((el,i)=>el.hidden=key!=='image:'+page.images[i].id);
 for(const [k,el]of elements)el.classList.toggle('studio-selected',k===key);
 if(!image)focusedEditor=editorFor(key);
 for(const id of ['fontSize','textColor','align'])$(id).disabled=image;
 $('posX').value=item.layout.x;$('posY').value=item.layout.y;$('elementWidth').value=item.layout.width;
 const el=elements.get(key);if(el){const cs=canvas.contentWindow.getComputedStyle(el.querySelector('p,h1,h2,h3,h4,h5,h6,span')||el);$('fontSize').value=Math.round(parseFloat(cs.fontSize));const rgb=cs.color.match(/\d+/g);if(rgb?.length>=3)$('textColor').value='#'+rgb.slice(0,3).map(n=>Number(n).toString(16).padStart(2,'0')).join('');$('align').value=['left','center','right'].includes(cs.textAlign)?cs.textAlign:'';}
 inspector.scrollTop=0;positionHandles();
}
function positionHandles(){const doc=canvas.contentDocument;if(!doc)return;const move=doc.getElementById('studio-move'),resize=doc.getElementById('studio-resize');if(!move||!resize)return;const el=elements.get(selection);if(!el||canvasMode!=='content'||el.hidden){move.style.display=resize.style.display='none';return;}const rect=el.getBoundingClientRect(),win=canvas.contentWindow;if(rect.bottom<0||rect.top>win.innerHeight){move.style.display=resize.style.display='none';return;}move.style.display=resize.style.display='block';move.style.left=Math.max(0,rect.left+win.scrollX)+'px';move.style.top=Math.max(0,rect.top+win.scrollY-30)+'px';resize.style.left=rect.right+win.scrollX-5+'px';resize.style.top=rect.bottom+win.scrollY-5+'px';}
function changed(key){if(key.startsWith('text:'))changedBlocks.add(model(key).id);else changedImages.add(model(key).id);mark();}
function installDrag(handle,isResize){handle.addEventListener('pointerdown',e=>{if(!selection||busy)return;e.preventDefault();const key=selection,el=elements.get(key),item=model(key),startX=e.clientX,startY=e.clientY,start={...item.layout},width=el.getBoundingClientRect().width;recordHistory();handle.setPointerCapture(e.pointerId);
 const move=ev=>{if(isResize)item.layout.width=Math.round(Math.max(20,Math.min(4000,width+ev.clientX-startX)));else{item.layout.x=Math.round(Math.max(-4000,Math.min(4000,Number(start.x)+ev.clientX-startX)));item.layout.y=Math.round(Math.max(-4000,Math.min(4000,Number(start.y)+ev.clientY-startY)));}layout(el,item.layout);changed(key);$('posX').value=item.layout.x;$('posY').value=item.layout.y;$('elementWidth').value=item.layout.width;positionHandles();};
 const end=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);recordHistory();};handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
 });}
function applyCanvas(){if(!page)return;for(const [key,el]of elements){const item=model(key);if(key.startsWith('text:')){const input=editorFor(key);if(input&&el.innerHTML!==input.innerHTML)el.innerHTML=input.innerHTML;}else{el.src='/preview/'+item.src;el.alt=item.alt;el.hidden=!!item.remove;}layout(el,item.layout);}positionHandles();}
function buildLayers(){const root=$('layers');root.replaceChildren();for(const [key,el]of elements){const item=model(key);const b=document.createElement('button');b.textContent=(key.startsWith('text:')?'T  ':'▧  ')+(item.label||item.alt||'Image');b.onclick=()=>{select(key);el.scrollIntoView({block:'center'});};root.append(b);}}
inspector.addEventListener('input',e=>{if(e.target.closest('.editor')||e.target.closest('.image-row'))applyCanvas();queueHistory();});
inspector.addEventListener('click',e=>{if(e.target.closest('.image-row'))setTimeout(()=>{applyCanvas();recordHistory();},0);});
$('mediaDialog').addEventListener('close',()=>{applyCanvas();recordHistory();});
for(const id of ['posX','posY','elementWidth'])$(id).onchange=()=>{if(!selection)return;const item=model(selection);const val=$(id).value;if(val!==''&&!Number.isFinite(Number(val)))return;recordHistory();item.layout[id==='posX'?'x':id==='posY'?'y':'width']=val===''?(id==='elementWidth'?'':0):Number(val);changed(selection);applyCanvas();recordHistory();};
$('resetPosition').onclick=()=>{if(!selection)return;recordHistory();model(selection).layout={x:0,y:0,width:''};changed(selection);applyCanvas();select(selection);recordHistory();};
function textDesign(prop,value){if(!selection?.startsWith('text:'))return;recordHistory();const editor=editorFor(selection);editor.querySelectorAll('*').forEach(el=>el.style[prop]=value);if(!editor.firstElementChild){const p=document.createElement('p');p.textContent=editor.textContent;p.style[prop]=value;editor.replaceChildren(p);}changed(selection);applyCanvas();recordHistory();}
$('fontSize').onchange=()=>{const n=Number($('fontSize').value);if(n>=8&&n<=150)textDesign('fontSize',n+'px');};$('textColor').onchange=()=>textDesign('color',$('textColor').value);$('align').onchange=()=>textDesign('textAlign',$('align').value);
// Formatting commands use the existing inspector selection and synchronize the canvas.
document.querySelectorAll('.toolbar button').forEach(b=>b.addEventListener('click',()=>setTimeout(()=>{if(focusedEditor){changedBlocks.add(Number(focusedEditor.dataset.id));mark();applyCanvas();recordHistory();}},0)));
function snapshot(){return JSON.stringify({page:page.page,blocks:page.blocks.map(b=>({id:b.id,html:editorFor('text:'+b.id).innerHTML,layout:b.layout})),images:page.images,changedBlocks:[...changedBlocks],changedImages:[...changedImages],addition:{open:!$('newEntry').hidden,panel:!$('addPanel').hidden,values:['entryTitle','entryBody','entryLink','entryImage'].map(id=>$(id).value)},dirty});}
function recordHistory(){if(!page||applying)return;clearTimeout(historyTimer);const state=snapshot();if(history[historyIndex]===state)return;history=history.slice(0,historyIndex+1);history.push(state);if(history.length>60)history.shift();historyIndex=history.length-1;}
function queueHistory(){clearTimeout(historyTimer);historyTimer=setTimeout(recordHistory,350);}
function restoreHistory(index){if(index<0||index>=history.length)return;applying=true;const state=JSON.parse(history[index]);for(const b of state.blocks){editorFor('text:'+b.id).innerHTML=b.html;page.blocks.find(v=>v.id===b.id).layout=b.layout;}state.images.forEach((pic,i)=>Object.assign(page.images[i],pic));changedBlocks.clear();state.changedBlocks.forEach(x=>changedBlocks.add(x));changedImages.clear();state.changedImages.forEach(x=>changedImages.add(x));if(state.addition){$('newEntry').hidden=!state.addition.open;$('addPanel').hidden=!state.addition.panel;['entryTitle','entryBody','entryLink','entryImage'].forEach((id,i)=>$(id).value=state.addition.values[i]);}dirty=state.dirty;$('saved').textContent=dirty?'Unsaved edits':'Saved locally';historyIndex=index;applyCanvas();for(const [i,pic]of page.images.entries()){const row=$('images').children[i];row.querySelector('img').src='/preview/'+pic.src;row.querySelector('input').value=pic.alt;}if(selection)select(selection);if(state.addition?.panel)$('addPanel').hidden=false;applying=false;}
$('undo').onclick=()=>{recordHistory();restoreHistory(historyIndex-1);};$('redo').onclick=()=>restoreHistory(historyIndex+1);
window.resetHistory=()=>{history=[];historyIndex=-1;recordHistory();};
$('desktop').onclick=()=>{canvas.style.width='100%';canvas.style.maxWidth='';positionHandles();};$('phone').onclick=()=>{canvas.style.width='390px';canvas.style.maxWidth='390px';positionHandles();};$('zoom').onchange=()=>{canvas.style.zoom=$('zoom').value;positionHandles();};
canvas.addEventListener('load',attachCanvas);
window.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'){e.preventDefault();$('save').click();}});

// Inline-first experience: the page itself is the editing surface.
let inspectorOpen=false;
const floating=document.createElement('div');floating.id='inlineTools';floating.hidden=true;floating.setAttribute('role','toolbar');floating.setAttribute('aria-label','Inline editing tools');
floating.innerHTML='<span id="inlineLabel">Text</span><button data-inline="bold" title="Bold selected text"><b>B</b></button><button data-inline="italic" title="Italic selected text"><i>I</i></button><button id="inlineLink">Link</button><button id="inlineImage" hidden>Replace image</button><button id="inlineSettings">Settings</button><button id="inlineDone" title="Hide editing controls">✓</button>';
document.body.append(floating);
const settingsClose=document.createElement('button');settingsClose.id='closeInspector';settingsClose.textContent='Close settings ×';inspector.prepend(settingsClose);
settingsClose.onclick=()=>{inspectorOpen=false;inspector.hidden=true;positionHandles();};
const previousTab=tab;
tab=function(name){previousTab(name);inspector.hidden=name!=='content'||!inspectorOpen;workspace.classList.add('inline-workspace');positionInline();};
const previousSelect=select;
select=function(key){previousSelect(key);inspector.hidden=!inspectorOpen;const isText=key.startsWith('text:');$('inlineLabel').textContent=isText?'Text':'Image';floating.querySelectorAll('[data-inline],#inlineLink').forEach(b=>b.hidden=!isText);$('inlineImage').hidden=isText;positionInline();};
const previousPosition=positionHandles;
positionHandles=function(){previousPosition();if(!inspectorOpen){for(const id of ['studio-move','studio-resize']){const el=canvas.contentDocument?.getElementById(id);if(el)el.style.display='none';}}positionInline();};
function positionInline(){const el=elements.get(selection);if(!el||canvasMode!=='content'){floating.hidden=true;return;}const rect=el.getBoundingClientRect(),frame=canvas.getBoundingClientRect(),scale=frame.width/canvas.clientWidth;if(rect.bottom<0||rect.top>canvas.contentWindow.innerHeight){floating.hidden=true;return;}floating.hidden=false;const x=frame.left+rect.left*scale,y=frame.top+rect.top*scale;floating.style.left=Math.max(frame.left,Math.min(x,window.innerWidth-floating.offsetWidth-15))+'px';floating.style.top=Math.max(frame.top+5,y-42)+'px';}
floating.addEventListener('mousedown',e=>e.preventDefault());
function syncInline(){if(!selection?.startsWith('text:'))return;const el=elements.get(selection);editorFor(selection).innerHTML=el.innerHTML;changed(selection);recordHistory();}
for(const button of floating.querySelectorAll('[data-inline]'))button.onclick=()=>{const el=elements.get(selection);if(!el||!selection.startsWith('text:'))return;recordHistory();el.focus();canvas.contentDocument.execCommand(button.dataset.inline,false,null);syncInline();};
$('inlineLink').onclick=()=>{if(!selection?.startsWith('text:'))return;const doc=canvas.contentDocument,range=doc.getSelection()?.rangeCount?doc.getSelection().getRangeAt(0).cloneRange():null;const url=prompt('Link address (https://… or mailto:…)');if(!url)return;if(!/^(https?:\/\/|mailto:|tel:)/i.test(url))return notice('Enter a full https://, mailto:, or tel: address.',true);recordHistory();elements.get(selection).focus();if(range){const selected=doc.getSelection();selected.removeAllRanges();selected.addRange(range);}doc.execCommand('createLink',false,url);syncInline();};
$('inlineImage').onclick=()=>{selectedImage=model(selection).id;openMedia();};
$('inlineSettings').onclick=()=>{inspectorOpen=!inspectorOpen;inspector.hidden=!inspectorOpen;positionHandles();};
$('inlineDone').onclick=()=>{for(const el of elements.values())el.classList.remove('studio-selected');selection=null;floating.hidden=true;inspectorOpen=false;inspector.hidden=true;positionHandles();};
const previousAdd=$('addSection').onclick;$('addSection').onclick=()=>{inspectorOpen=true;previousAdd();inspector.hidden=false;};
const previousRenderInline=render;render=function(){previousRenderInline();inspectorOpen=false;inspector.hidden=true;floating.hidden=true;};
$('previewPanel').querySelector('.preview-tools p').textContent='Click any text and type · Select words to format · Changes appear as you edit';
$('contentTab').textContent='Edit on page';
canvas.title='Live editable website';
window.addEventListener('resize',positionInline);
$('previewPanel').addEventListener('scroll',positionInline);
