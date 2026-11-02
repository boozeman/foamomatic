import {setProgram} from "./program-state.mjs";
import {getToken} from "./auth-state.mjs";
import {setPreview, clearPreview} from "./wire-view.js";
const form=document.getElementById("preview-form");
const input=document.getElementById("preview-file");
const message=document.getElementById("preview-message");
const button=document.getElementById("preview-load");
let controller=null, revision=0;
document.getElementById("preview-clear").addEventListener("click",()=>{
  revision++;controller?.abort();clearPreview();setProgram(null);input.value="";
  message.textContent="Esikatselu tyhjennetty.";button.disabled=false;
});
form.addEventListener("submit",async event=>{
  event.preventDefault();
  const token=getToken(), file=input.files[0];
  if(!token){message.textContent="Yhdistä ensin yhteysavaimella.";return;}
  if(!file){message.textContent="Valitse G-kooditiedosto.";return;}
  if(file.size>256*1024){message.textContent="Tiedoston enimmäiskoko on 256 KiB.";return;}
  const current=++revision;
  controller?.abort();controller=new AbortController();
  const timeout=setTimeout(()=>controller?.abort(),25000);
  button.disabled=true;clearPreview();setProgram(null);
  message.textContent="Tulkitaan "+file.name+"…";
  try{
    const response=await fetch("/preview",{method:"POST",headers:{"Authorization":"Bearer "+token,"Content-Type":"text/plain; charset=utf-8"},
      body:file,signal:controller.signal});
    const result=await response.json();
    if(current!==revision)return;
    if(!response.ok||!result.ok)throw new Error(result.error||"Esikatselun muodostus epäonnistui.");
    setPreview(result.data.segments);
    setProgram(result.data.program_id?{id:result.data.program_id,name:file.name}:null);
    message.textContent=file.name+" · "+result.data.segments.length+" liikettä · Oranssi katkoviiva: G0, sininen pinta: G1. Esikatselu käyttää lataushetken konekoordinaatteja.";
  }catch(error){
    if(current===revision)message.textContent=error.name==="AbortError"?"Esikatselu keskeytyi tai aikakatkaistiin.":error.message;
  }finally{
    clearTimeout(timeout);
    if(current===revision)button.disabled=false;
  }
});
