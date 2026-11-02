import {setProgram} from "./program-state.mjs";
import {getToken} from "./auth-state.mjs";
import {setPreview, clearPreview} from "./wire-view.js?v=11";
const form=document.getElementById("preview-form");
const input=document.getElementById("preview-file");
const message=document.getElementById("preview-message");
const button=document.getElementById("preview-load");
let controller=null, revision=0;
document.getElementById("preview-clear").addEventListener("click",()=>{
  revision++;controller?.abort();clearPreview();setProgram(null);input.value="";
  message.textContent="Preview cleared.";button.disabled=false;
});
form.addEventListener("submit",async event=>{
  event.preventDefault();
  const token=getToken(), file=input.files[0];
  if(!token){message.textContent="Connect with your token first.";return;}
  if(!file){message.textContent="Select a G-code file.";return;}
  if(file.size>256*1024){message.textContent="Maximum file size is 256 KiB.";return;}
  const current=++revision;
  controller?.abort();controller=new AbortController();
  const timeout=setTimeout(()=>controller?.abort(),25000);
  button.disabled=true;clearPreview();setProgram(null);
  message.textContent="Parsing "+file.name+"…";
  try{
    const response=await fetch("/preview",{method:"POST",headers:{"Authorization":"Bearer "+token,"Content-Type":"text/plain; charset=utf-8"},
      body:file,signal:controller.signal});
    const result=await response.json();
    if(current!==revision)return;
    if(!response.ok||!result.ok)throw new Error(result.error||"Could not generate the preview.");
    setPreview(result.data.segments);
    setProgram(result.data.program_id?{id:result.data.program_id,name:file.name}:null);
    message.textContent=file.name+" · "+result.data.segments.length+" moves · Dashed orange: G0; blue surface: G1. Preview uses machine coordinates captured at upload.";
  }catch(error){
    if(current===revision)message.textContent=error.name==="AbortError"?"Preview was cancelled or timed out.":error.message;
  }finally{
    clearTimeout(timeout);
    if(current===revision)button.disabled=false;
  }
});
