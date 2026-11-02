import {getProgram,onProgram} from "./program-state.mjs";
import {locateProgress,interpolate,matchesProgram} from "./preview-progress.mjs";
import {endpoints, changed, project} from "./wire-geometry.mjs";
const canvas = document.getElementById("wire-view");
const ctx = canvas.getContext("2d");
const note = document.getElementById("wire-note");
let config = {width_mm:1000, horizontal_max_mm:710, vertical_max_mm:260};
let position = null, last = null, trails = [], live = false, gap = true;
let yaw = -0.65, pitch = 0.42, dragging = null, previous = null, lastTime = 0;
const LIMIT = 2000;
let preview = [], previewStep = 0, executionCursor = null;
const follow = document.getElementById("follow-program");
const followStatus = document.getElementById("follow-status");
function followLabel(text){
  followStatus.textContent=text??(follow.checked?"Waiting for program":"Manual preview");
}
onProgram(()=>{executionCursor=null;followLabel();draw();});
follow.addEventListener("change",()=>{
  if(follow.checked&&executionCursor){previewStep=executionCursor.index;slider.value=String(previewStep);}
  followLabel(follow.checked&&executionCursor?"Following execution":null);
  updatePreviewLabel();draw();
});
const slider = document.getElementById("preview-step");
slider.addEventListener("input", () => {
  follow.checked=false;
  followLabel();
  previewStep = Number(slider.value); updatePreviewLabel(); draw();
});
function updatePreviewLabel() {
  const segment=preview[previewStep];
  document.getElementById("preview-line").textContent=segment
    ? "Line "+segment.line+" · "+(previewStep+1)+"/"+preview.length : "No preview";
}
export function setPreview(segments) {
  if(!Array.isArray(segments) || segments.length>12000 ||
      !segments.every(s=>["rapid","feed"].includes(s.kind) &&
        [s.start,s.end].every(p=>Array.isArray(p)&&p.length===4&&p.every(Number.isFinite)))) {
    throw new Error("Invalid preview coordinates.");
  }
  preview=segments;previewStep=0;executionCursor=null;
  follow.checked=true;follow.disabled=!segments.length;followLabel();
  slider.max=String(Math.max(0,segments.length-1));slider.value=String(previewStep);
  slider.disabled=!segments.length;updatePreviewLabel();draw();
}
export function clearPreview() {setPreview([]);}
const asPosition = p => ({X:p[0],Y:p[1],U:p[2],V:p[3]});
function draw() {
  const rect = canvas.getBoundingClientRect();
  if(rect.width<1||rect.height<1)return;
  const ratio = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.round(rect.width * ratio));
  canvas.height = Math.max(1, Math.round(rect.height * ratio));
  ctx.setTransform(ratio,0,0,ratio,0,0);
  const w=rect.width,h=rect.height;
  ctx.clearRect(0,0,w,h);
  const {width_mm:span,horizontal_max_mm:xmax,vertical_max_mm:zmax}=config;
  const bounds=[];
  for(const x of [0,xmax]) for(const y of [0,span]) for(const z of [0,zmax]) bounds.push(project([x,y,z],yaw,pitch));
  const minX=Math.min(...bounds.map(p=>p[0])), maxX=Math.max(...bounds.map(p=>p[0]));
  const minY=Math.min(...bounds.map(p=>p[1])), maxY=Math.max(...bounds.map(p=>p[1]));
  const scale=Math.min((w-70)/(maxX-minX || 1),(h-70)/(maxY-minY || 1));
  const at=p=>{const v=project(p,yaw,pitch);return [w/2+(v[0]-(maxX+minX)/2)*scale,h/2+(v[1]-(maxY+minY)/2)*scale];};
  function path(points,color,width=1,fill=null){
    ctx.beginPath(); points.map(at).forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));
    if(fill){ctx.closePath();ctx.fillStyle=fill;ctx.fill();}
    ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();
  }
  for(const y of [0,span]){
    path([[0,y,0],[xmax,y,0],[xmax,y,zmax],[0,y,zmax],[0,y,0]],"#46615b");
    for(let x=100;x<xmax;x+=100)path([[x,y,0],[x,y,zmax]],"#263d37");
    for(let z=100;z<zmax;z+=100)path([[0,y,z],[xmax,y,z]],"#263d37");
  }
  for(const x of [0,xmax])path([[x,0,0],[x,span,0]],"#344c45");
  function previewSegment(start,end,kind,completed){
    const a=endpoints(asPosition(start),span),b=endpoints(asPosition(end),span);
    if(kind==="feed"){
      path([a[0],a[1],b[1],b[0]],completed?"rgba(100,220,170,.16)":"rgba(120,160,240,.1)",1,
        completed?"rgba(80,205,150,.12)":"rgba(110,150,235,.04)");
    }
    ctx.setLineDash(kind==="rapid"?[4,5]:[]);
    path([a[0],b[0]],completed?"#5fd7a5":kind==="rapid"?"#bf8960":"#89b8f1",completed?2:1.2);
    path([a[1],b[1]],completed?"#5fd7a5":kind==="rapid"?"#bf8960":"#b8a4ef",completed?2:1.2);
    ctx.setLineDash([]);
  }
  for(const [index,segment] of preview.entries()){
    if(executionCursor&&index===executionCursor.index){
      const middle=interpolate(segment.start,segment.end,executionCursor.fraction);
      if(executionCursor.fraction>0)previewSegment(segment.start,middle,segment.kind,true);
      if(executionCursor.fraction<1)previewSegment(middle,segment.end,segment.kind,false);
    }else{
      previewSegment(segment.start,segment.end,segment.kind,!!executionCursor&&index<executionCursor.index);
    }
  }
  const selected=preview[previewStep];
  if(selected){
    const marker=follow.checked
      ? executionCursor?interpolate(selected.start,selected.end,executionCursor.fraction):selected.start
      : selected.end;
    path(endpoints(asPosition(marker),span),"#b8a4ef",2);
  }
  for(const segment of trails) {
    const a=endpoints(segment[0],span),b=endpoints(segment[1],span);
    path([a[0],a[1],b[1],b[0]],"rgba(91,191,171,.08)",1,"rgba(91,191,171,.055)");
    path([a[0],b[0]],"#7fd7ba",1.5);
    path([a[1],b[1]],"#e3b979",1.5);
  }
  ctx.font="12px system-ui";
  ctx.fillStyle="#94afa5";
  for(const [text,p] of [["Left XY",[0,0,zmax]],["Right UV",[0,span,zmax]]]){
    const v=at(p);ctx.fillText(text,v[0]+6,v[1]-10);
  }
  if(position&&live){
    const ends=endpoints(position,span);
    path(ends,"#f9e8b1",3);
    for(const [i,p] of ends.entries()){
      const v=at(p);ctx.beginPath();ctx.arc(...v,5,0,2*Math.PI);ctx.fillStyle=i?"#e3b979":"#7fd7ba";ctx.fill();
    }
  }
}
new ResizeObserver(draw).observe(canvas);
canvas.addEventListener("pointerdown",e=>{dragging=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener("pointermove",e=>{
  if(!dragging)return;
  yaw+=(e.clientX-dragging[0])*.007;
  pitch=Math.max(-1.2,Math.min(1.2,pitch+(e.clientY-dragging[1])*.007));
  dragging=[e.clientX,e.clientY];draw();
});
const endDrag=()=>{dragging=null;};
canvas.addEventListener("pointerup",endDrag);
canvas.addEventListener("pointercancel",endDrag);
document.getElementById("clear-trail").addEventListener("click",()=>{trails=[];last=null;draw();});
document.getElementById("reset-view").addEventListener("click",()=>{yaw=-.65;pitch=.42;draw();});
export function configureWire(value){
  if(!value || !["width_mm","horizontal_max_mm","vertical_max_mm"].every(k=>Number.isFinite(value[k])&&value[k]>0))return;
  config=value;trails=[];last=null;draw();
  document.getElementById("wire-size").textContent=value.width_mm+" mm · nominal width";
}
export function updateWire(data){
  const p=data.machine;
  if(!p || !["X","Y","U","V"].every(k=>Number.isFinite(p[k])))return unavailableWire();
  if(preview.length&&matchesProgram(data,getProgram()?.id)){
    const cursor=locateProgress(preview,data.source_line,p,executionCursor);
    if(cursor){
      executionCursor=cursor;
      if(follow.checked){previewStep=cursor.index;slider.value=String(previewStep);updatePreviewLabel();}
      followLabel((follow.checked?"Following":"Manual preview · running")+" line "+data.source_line);
    }
  }else followLabel();
  const now=performance.now();
  const signature=JSON.stringify([data.homed,data.file]);
  if(signature!==previous || now-lastTime>1500)gap=true;
  if(gap)last=null;
  if(changed(last,p)){
    if(last)trails.push([last,{...p}]);
    if(trails.length>LIMIT)trails.shift();
    last={...p};
  }
  gap=false;previous=signature;lastTime=now;
  position={...p};live=true;
  const outside=p.X<0||p.U<0||p.Y<0||p.V<0||p.X>config.horizontal_max_mm||p.U>config.horizontal_max_mm||p.Y>config.vertical_max_mm||p.V>config.vertical_max_mm;
  note.textContent=outside?"A wire endpoint is outside the nominal display area.":"Green: XY · Yellow: UV · White: wire";
  draw();
}
export function unavailableWire(){
  followLabel("No fresh run status");
  live=false;gap=true;last=null;note.textContent="Live wire hidden: no fresh status.";draw();
}
draw();
