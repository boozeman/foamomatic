import assert from "node:assert/strict";
import {locateProgress,interpolate,matchesProgram} from "../server/static/preview-progress.mjs";
const segments=[
 {line:9,start:[0,0,0,0],end:[10,0,100,0]},
 {line:11,start:[10,0,100,0],end:[10,20,100,40]},
 {line:13,start:[10,20,100,40],end:[30,20,120,40]}];
assert.deepEqual(locateProgress(segments,3,{X:0,Y:0,U:0,V:0}),{index:0,fraction:0});
assert.deepEqual(locateProgress(segments,9,{X:5,Y:0,U:50,V:0}),{index:0,fraction:.5});
assert.deepEqual(locateProgress(segments,10,{X:10,Y:0,U:100,V:0}),{index:0,fraction:1});
const paused=locateProgress(segments,11,{X:10,Y:10,U:100,V:20});
assert.deepEqual(paused,{index:1,fraction:.5});
assert.deepEqual(locateProgress(segments,0,{X:10,Y:10,U:100,V:20},paused),paused);
assert.deepEqual(locateProgress(segments,13,{X:30,Y:20,U:120,V:40}),{index:2,fraction:1});
assert.deepEqual(interpolate(segments[1].start,segments[1].end,.5),[10,10,100,20]);
assert.equal(matchesProgram({task_mode:2,loaded_program_id:"a",running_program_id:"a"},"a"),true);
assert.equal(matchesProgram({task_mode:2,loaded_program_id:"b",running_program_id:"a"},"a"),false);
assert.equal(matchesProgram({task_mode:3,loaded_program_id:"a",running_program_id:"a"},"a"),false);
console.log("Preview progress: XYUV interpolation, non-motion rows, pauses, completion and program identity OK");
