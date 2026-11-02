import assert from "node:assert/strict";
import {endpoints,changed,project} from "../server/static/wire-geometry.mjs";
assert.deepEqual(endpoints({X:0,Y:0,U:0,V:0},1000),[[0,0,0],[0,1000,0]]);
const [a,b]=endpoints({X:280,Y:0,U:0,V:120},1000);
assert.ok(Math.hypot(...a.map((v,i)=>v-b[i]))>1000);
assert.equal(changed({X:1,Y:2,U:3,V:4},{X:1,Y:2,U:3,V:4}),false);
assert.equal(changed({X:1,Y:2,U:3,V:4},{X:1,Y:2,U:4,V:4}),true);
assert.deepEqual(project([2,3,4],0,0),[2,-4]);
console.log("XYUV geometry checks passed");
