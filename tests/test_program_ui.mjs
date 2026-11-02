import assert from "node:assert/strict";
const elements={};
globalThis.document={hidden:false,addEventListener(){},getElementById(id){
  return elements[id]??(elements[id]={disabled:false,textContent:"",events:{},addEventListener(k,v){this.events[k]=v;}});
}};
const {createProgramControls}=await import("../server/static/program-ui.js");
const {setProgram}=await import("../server/static/program-state.mjs");
const calls=[];
const ui=createProgramControls(async message=>{calls.push(message);return {serial:calls.length};});
const base={enabled:true,estop:false,homed:[1,1,1,1],homing:[false,false,false,false],
  interp_state:1,task_mode:1,paused:false,mdi_pending:false,sample_monotonic:1,echo_serial_number:0};
setProgram({id:"preview",name:"test.nc"});ui.update(base,true,true);
assert.equal(elements["program-run"].disabled,false);
const starting=elements["program-run"].events.click();
await new Promise(resolve=>setTimeout(resolve,0));
assert.deepEqual(calls.map(c=>c.cmd),["program_prepare"]);
ui.update({...base,task_mode:2,echo_serial_number:1,sample_monotonic:2},true,true);
await new Promise(resolve=>setTimeout(resolve,0));
assert.deepEqual(calls.map(c=>c.cmd),["program_prepare","program_open"]);
ui.update({...base,task_mode:2,echo_serial_number:2,sample_monotonic:3,loaded_program_id:"preview"},true,true);
await starting;
assert.deepEqual(calls.map(c=>c.cmd),["program_prepare","program_open","program_run"]);
assert.equal(elements["program-run"].disabled,true);
// Connection loss between mode selection and file-open must not advance to Run.
setProgram({id:"another",name:"other.nc"});ui.update({...base,sample_monotonic:4},true,true);
const cancelled=elements["program-run"].events.click();
await new Promise(resolve=>setTimeout(resolve,0));
ui.update(null,false,false);
await cancelled;
assert.equal(calls.filter(c=>c.cmd==="program_run").length,1);
console.log("Program UI: acknowledged sequence, duplicate prevention and disconnect cancellation OK");
