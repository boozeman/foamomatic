export function interpolate(start,end,fraction) {
  return start.map((value,i)=>value+(end[i]-value)*fraction);
}
export function matchesProgram(status,programId) {
  return !!programId && status?.task_mode===2 &&
    status.loaded_program_id===programId && status.running_program_id===programId;
}
export function locateProgress(segments,line,position,previous=null) {
  if(!segments.length||!Number.isInteger(line)||line<0)return null;
  if(line===0)return previous??{index:0,fraction:0};
  const point=position&&["X","Y","U","V"].map(axis=>position[axis]);
  if(!point?.every(Number.isFinite))return null;
  let best=null;
  for(let i=0;i<segments.length;i++){
    const segment=segments[i];
    if(segment.line!==line)continue;
    if(previous&&i<previous.index)continue;
    const delta=segment.end.map((value,k)=>value-segment.start[k]);
    const length=delta.reduce((sum,v)=>sum+v*v,0);
    const fraction=length?Math.max(0,Math.min(1,delta.reduce((sum,v,k)=>sum+v*(point[k]-segment.start[k]),0)/length)):1;
    const projected=interpolate(segment.start,segment.end,fraction);
    const error=projected.reduce((sum,v,k)=>sum+(v-point[k])**2,0);
    if(best===null||error<best.error)best={index:i,fraction,error};
  }
  if(best)return {index:best.index,fraction:best.fraction};
  // Non-motion rows (comments, M0, feed settings) retain the last completed move.
  let index=-1;
  for(let i=previous?.index??0;i<segments.length;i++){
    if(segments[i].line<line)index=i;
    else break;
  }
  return index<0?(previous??{index:0,fraction:0}):{index,fraction:1};
}
