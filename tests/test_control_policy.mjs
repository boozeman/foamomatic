import assert from "node:assert/strict";
import {permissions} from "../server/static/control-policy.mjs";
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
