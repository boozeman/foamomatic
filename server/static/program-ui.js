import {getProgram,onProgram,cancelPreparation,preparationGeneration} from "./program-state.mjs";
export function createProgramControls(send){
  const run=document.getElementById("program-run");
  const pause=document.getElementById("program-pause");
  const resume=document.getElementById("program-resume");
  const stop=document.getElementById("program-stop");
  const message=document.getElementById("program-message");
  const progress=document.getElementById("program-progress");
  let state=null,fresh=false,connected=false,busy=false,consumed=null,waiters=[];
  function available(){
    return connected&&fresh&&state?.enabled===true&&state?.estop===false&&
      state.homed?.length===4&&state.homed.every(Boolean)&&!state.homing?.some(Boolean)&&!state.mdi_pending;
  }
  function render(){
    document.getElementById("preview-operations").disabled=busy||(fresh&&(state?.interp_state!==1||state?.paused));
    const p=getProgram(),active=p&&state?.loaded_program_id===p.id&&state?.running_program_id===p.id;
    run.disabled=busy||!p||consumed===p.id||!available()||state?.interp_state!==1||state?.paused;
    pause.disabled=busy||!active||!available()||state?.paused||state?.interp_state===1;
    resume.disabled=busy||!active||!available()||!state?.paused;
    stop.disabled=!connected;
    document.getElementById("program-selection").textContent=p?p.name:"Esikatsele tiedosto ensin.";
    progress.textContent=!fresh?"Ei tuoretta ajotietoa.":active?
      (state.paused?"Tauolla":state.interp_state===1?"Vapaa / ohjelma päättynyt":"Ohjelma käynnissä")+" · rivi "+(state.source_line??state.line):
      "Ei tämän esikatselun ohjelmaa ajossa.";
  }
  function nextStatus(predicate){
    const sample=state?.sample_monotonic;
    return new Promise((resolve,reject)=>{
      const item={predicate:next=>next.sample_monotonic!==sample&&predicate(next),resolve,reject};
      item.timer=setTimeout(()=>{
        waiters=waiters.filter(v=>v!==item);reject(new Error("Valmistelun kuittaus puuttuu; ajoa ei jatketa automaattisesti."));
      },5000);waiters.push(item);
    });
  }
  function cancelWaits(){
    for(const item of waiters){clearTimeout(item.timer);item.reject(new Error("Ajon valmistelu keskeytyi."));}
    waiters=[];
  }
  onProgram(()=>{cancelPreparation();cancelWaits();render();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden){cancelPreparation();cancelWaits();}});
  run.addEventListener("click",async()=>{
    if(run.disabled)return;
    const p=getProgram(),generation=preparationGeneration();
    const check=()=>{if(generation!==preparationGeneration()||getProgram()?.id!==p.id||!connected||!fresh)throw new Error("Ajon valmistelu keskeytyi.");};
    busy=true;render();
    try{
      message.textContent="Valitaan AUTO-tila…";
      const mode=await send({cmd:"program_prepare",program_id:p.id});
      check();
      await nextStatus(s=>s.task_mode===2&&s.echo_serial_number>=mode.serial);
      check();message.textContent="Avataan esikatseltu tiedosto…";
      const opened=await send({cmd:"program_open",program_id:p.id});
      check();
      await nextStatus(s=>s.loaded_program_id===p.id&&s.echo_serial_number>=opened.serial);
      check();message.textContent="Lähetetään käynnistyspyyntö…";
      consumed=p.id;
      await send({cmd:"program_run",program_id:p.id});
      message.textContent="Käynnistyspyyntö välitetty. M0 pysäyttää ohjelman odottamaan Jatka-painiketta.";
    }catch(error){message.textContent=error.message;}
    finally{busy=false;render();}
  });
  async function command(cmd){
    if(busy)return;
    busy=true;render();
    try{await send({cmd,program_id:getProgram()?.id});message.textContent="Komento välitetty. Seuraa ajon tilaa.";}
    catch(error){message.textContent=error.message;}
    finally{busy=false;render();}
  }
  pause.addEventListener("click",()=>{if(!pause.disabled)command("program_pause");});
  resume.addEventListener("click",()=>{if(!resume.disabled)command("program_resume");});
  stop.addEventListener("click",async()=>{
    cancelPreparation();cancelWaits();
    try{await send({cmd:"abort"});message.textContent="Keskeytyspyyntö välitetty.";}
    catch(error){message.textContent=error.message;}
  });
  render();
  return {update(value,isFresh,isConnected){
    state=value;fresh=isFresh;connected=isConnected;
    if(!connected||!fresh){cancelPreparation();cancelWaits();}
    if(state&&fresh){
      for(const item of [...waiters]){
        if(item.predicate(state)){clearTimeout(item.timer);waiters=waiters.filter(v=>v!==item);item.resolve();}
      }
    }
    render();
  }};
}
