import assert from 'node:assert/strict';
class Element {
  constructor(){this.events={};this.children=[];this.value='';this.disabled=false;this.open=true;this.maxLength=254;}
  addEventListener(name,fn){this.events[name]=fn;}
  append(child){this.children.push(child);}
  prepend(child){this.children.unshift(child);}
  replaceChildren(){this.children=[];}
  querySelectorAll(){return [];}
  focus(){}
  showModal(){this.open=true;}
  close(){this.open=false;}
}
const elements={};
globalThis.document={getElementById(id){return elements[id]??=new Element();},createElement(){return new Element();}};
let stored=null;
globalThis.localStorage={getItem(){return stored;},setItem(key,value){stored=value;}};
const {createControls}=await import('../server/static/controls-ui.js');
const calls=[];let fail=false;
const ui=createControls(async command=>{if(fail)throw Error('Rejected');calls.push(command);});
const state={enabled:true,estop:false,homed:[1,1,1,1],homing:[false,false,false,false],interp_state:1,task_mode:3,paused:false,mdi_pending:false};
const click=async id=>{elements[id].events.click();await new Promise(resolve=>setTimeout(resolve,0));};
const input=elements['mdi-input'];
ui.update(state,true,true);input.value='G90';
await click('mdi-heater-on');await click('mdi-heater-off');
assert.deepEqual(calls.map(c=>c.text),['M8','M9']);assert.equal(input.value,'G90');
const history=elements['mdi-history'];history.children[0].events.dblclick();assert.equal(input.value,'M9');
elements['mdi-form'].events.submit({preventDefault(){}});await new Promise(resolve=>setTimeout(resolve,0));assert.equal(input.value,'');
fail=true;input.value='G91';const count=history.children.length;
elements['mdi-form'].events.submit({preventDefault(){}});await new Promise(resolve=>setTimeout(resolve,0));assert.equal(input.value,'G91');assert.equal(history.children.length,count);
ui.update(state,false,false);await click('mdi-heater-on');assert.equal(calls.length,3);assert.equal(elements['mdi-heater-on'].disabled,true);
await click('mdi-edit-macros');
const fields=elements['mdi-macro-fields'].children;
fields[0].children[0].children[0].value='Absolute';fields[0].children[1].children[0].value='G90';
elements['mdi-macro-form'].events.submit({preventDefault(){}});
assert.equal(JSON.parse(stored)[0].command,'G90');
const macros=elements['mdi-macros'].children;assert.equal(macros[1].disabled,true);
macros[0].events.click();assert.equal(input.value,'G90');assert.equal(calls.length,3);
await click('mdi-edit-macros');elements['mdi-macro-fields'].children[0].children[1].children[0].value='G90\nM8';
elements['mdi-macro-form'].events.submit({preventDefault(){}});assert.ok(elements['mdi-macro-error'].textContent);assert.equal(JSON.parse(stored)[0].command,'G90');
console.log('MDI controls: heater gating, input preservation, history recall, macro loading, persistence and validation OK');
