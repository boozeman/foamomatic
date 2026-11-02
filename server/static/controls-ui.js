import {permissions} from "./control-policy.mjs";
export function createControls(send) {
  const ids={enable:"machine-on",disable:"machine-off",estop:"machine-estop",
    reset_estop:"machine-reset",abort:"machine-abort",mdi_mode:"mdi-mode",manual:"manual-mode",mdi:"mdi-send"};
  let state=null,fresh=false,connected=false,busy=false;
  const message=document.getElementById("control-message");
  const history=document.getElementById("mdi-history");
  function render(){
    const can=permissions(state,fresh,connected);
    for(const [cmd,id] of Object.entries(ids)){
      document.getElementById(id).disabled=!can[cmd]||(busy&&!["estop","abort","disable"].includes(cmd));
    }
    document.getElementById("mdi-input").disabled=!can.mdi||busy;
    document.getElementById("mdi-help").textContent=!fresh?"Odotetaan tuoretta koneen tilaa.":
      !state?.enabled?"Kytke koneen käyttölupa päälle.":
      !state.homed?.every(v=>v===1||v===true)?"Kotiajettava kaikki neljä akselia LinuxCNC:ssä ennen MDI:tä.":
      state.task_mode!==3?"Valitse MDI-tila ja odota tilan vahvistusta.":
      state.interp_state!==1||state.paused?"Kone suorittaa komentoa tai on tauolla.":"Valmis yhden MDI-rivin lähetykseen.";
  }
  function entry(text){
    const row=document.createElement("li");row.textContent=text;
    history.prepend(row);while(history.children.length>30)history.lastElementChild.remove();
  }
  async function execute(cmd,text){
    if(!permissions(state,fresh,connected)[cmd])return;
    const urgent=["estop","abort","disable"].includes(cmd);
    if(busy&&!urgent)return;
    if(!urgent)busy=true;
    render();message.textContent="Lähetetään…";
    try{
      await send({cmd,...(text?{text}:{})});
      message.textContent="Komento välitetty LinuxCNC:lle. Toteutuminen näkyy tilatiedoissa.";
      if(cmd==="mdi"){entry(text+" — välitetty");document.getElementById("mdi-input").value="";}
    }catch(error){
      message.textContent=error.message;
      if(cmd==="mdi")entry(text+" — "+error.message);
    }finally{if(!urgent)busy=false;render();}
  }
  for(const [cmd,id] of Object.entries(ids)){
    if(cmd!=="mdi")document.getElementById(id).addEventListener("click",()=>execute(cmd));
  }
  document.getElementById("mdi-form").addEventListener("submit",event=>{
    event.preventDefault();const text=document.getElementById("mdi-input").value.trim();
    if(text)execute("mdi",text);
  });
  document.getElementById("mdi-clear-history").addEventListener("click",()=>history.replaceChildren());
  render();
  return {update(value,isFresh,isConnected){state=value;fresh=isFresh;connected=isConnected;render();}};
}
