import assert from "node:assert/strict";
import {permissions, mdiStatus} from "../server/static/control-policy.mjs";
const state={estop:false,enabled:true,homed:[1,1,1,1],interp_state:1,task_mode:3,paused:false};
assert.equal(permissions(state,true,true).mdi,true);
for(const value of [{...state,estop:true},{...state,enabled:false},{...state,homed:[1,1,0,0]},
  {...state,interp_state:2},{...state,paused:true},{...state,task_mode:1}]){
  assert.equal(permissions(value,true,true).mdi,false);
}
assert.equal(permissions(state,false,true).mdi,false);
assert.equal(permissions(null,false,true).estop,true);
assert.equal(permissions(null,false,false).estop,false);
console.log("Control policy checks passed");

assert.match(mdiStatus({...state,homed:[1,1,0,0]},true,true),/Not homed: U, V/);
assert.match(mdiStatus(state,true,true),/MDI mode is active/);
assert.match(mdiStatus({...state,interp_state:2,task_mode:1},true,true),/running/);
assert.match(mdiStatus({...state,estop:true},true,true),/E-stop/);

assert.equal(permissions({...state,task_mode:1},true,true).home_axis,true);
assert.equal(permissions({...state,task_mode:1,homing:[false,true,false,false]},true,true).home_axis,false);
assert.equal(permissions(state,true,true).home_axis,false);
