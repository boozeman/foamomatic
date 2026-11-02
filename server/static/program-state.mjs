let preview=null;
const listeners=new Set();
export const getProgram=()=>preview;
export function setProgram(value){preview=value;for(const listener of listeners)listener(value);}
export function onProgram(listener){listeners.add(listener);}
let generation=0;
export const cancelPreparation=()=>{generation++;};
export const preparationGeneration=()=>generation;
