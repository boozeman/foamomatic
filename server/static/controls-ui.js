import {createMdiKeyboard} from "./mdi-keyboard.js";
import {permissions, mdiStatus} from "./control-policy.mjs";
export function createControls(send) {
  const keyboard=createMdiKeyboard();
  const ids={enable:"machine-on",disable:"machine-off",estop:"machine-estop",
    reset_estop:"machine-reset",abort:"machine-abort",mdi_mode:"mdi-mode",manual:"manual-mode",mdi:"mdi-send",home_all:"home-all",home_X:"home-X",home_Y:"home-Y",home_U:"home-U",home_V:"home-V"};
  let state=null,fresh=false,connected=false,busy=false;
  const message=document.getElementById("control-message");
  const history=document.getElementById("mdi-history");
  function render(){
    const can=permissions(state,fresh,connected);
    for(const [cmd,id] of Object.entries(ids)){
      document.getElementById(id).disabled=!(cmd.startsWith("home_")&&cmd!=="home_all"?can.home_axis:can[cmd])||(busy&&!["estop","abort","disable"].includes(cmd));
    }
    document.getElementById("mdi-input").disabled=!can.mdi||busy;
    keyboard.setEnabled(can.mdi&&!busy);
    const help=mdiStatus(state,fresh,connected);
    document.getElementById("mdi-help").textContent=help;
    const modeButton=document.getElementById("mdi-mode");
    modeButton.textContent=fresh&&state?.task_mode===3?"MDI-tila käytössä":"Valitse MDI-tila";
    modeButton.title=help;
    document.getElementById("homing-help").textContent=!fresh?"Odotetaan koneen tilaa.":state.homing?.some(Boolean)?"Kotiajo käynnissä.":state.task_mode!==1?"Valitse käsiajotila kotiajoa varten.":"Valitse kotiajettava akseli tai kaikkien akselien kotiajo.";
  }
  function entry(text){
    const row=document.createElement("li");row.textContent=text;
    history.prepend(row);while(history.children.length>30)history.lastElementChild.remove();
  }
  async function execute(cmd,text){
    const axisHome=cmd.startsWith("home_")&&cmd!=="home_all";
    if(!permissions(state,fresh,connected)[axisHome?"home_axis":cmd])return;
    const urgent=["estop","abort","disable"].includes(cmd);
    if(busy&&!urgent)return;
    if(!urgent)busy=true;
    render();message.textContent="Lähetetään…";
    try{
      await send({cmd:axisHome?"home_axis":cmd,...(axisHome?{axis:cmd.slice(5)}:{}),...(text?{text}:{})});
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
