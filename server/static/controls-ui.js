import {createMdiMacros} from "./mdi-macros.js";
import {cancelPreparation} from "./program-state.mjs";
import {createMdiKeyboard} from "./mdi-keyboard.js";
import {permissions, mdiStatus} from "./control-policy.mjs";
export function createControls(send) {
  const keyboard=createMdiKeyboard();
  const input=document.getElementById("mdi-input");
  const load=text=>{input.value=text;input.focus({preventScroll:true});};
  createMdiMacros(load);
  const heaters=[document.getElementById("mdi-heater-on"),document.getElementById("mdi-heater-off")];
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
    for(const button of heaters)button.disabled=!can.mdi||busy;
    const help=mdiStatus(state,fresh,connected);
    document.getElementById("mdi-help").textContent=help;
    const modeButton=document.getElementById("mdi-mode");
    modeButton.textContent=fresh&&state?.task_mode===3?"MDI mode active":"Select MDI mode";
    modeButton.title=help;
    document.getElementById("homing-help").textContent=!fresh?"Waiting for machine status.":state.homing?.some(Boolean)?"Homing in progress.":state.task_mode!==1?"Select Manual mode to home the axes.":"Select an axis to home, or home all axes.";
  }
  function entry(text){
    const row=document.createElement("li");row.textContent=text;
    row.tabIndex=0;row.title="Double-click to load into input; press Enter to send.";
    row.addEventListener("dblclick",()=>load(text));
    row.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();load(text);}});
    history.prepend(row);while(history.children.length>30)history.lastElementChild.remove();
  }
  async function execute(cmd,text,clearInput=true){
    const axisHome=cmd.startsWith("home_")&&cmd!=="home_all";
    if(!permissions(state,fresh,connected)[axisHome?"home_axis":cmd])return;
    const urgent=["estop","abort","disable"].includes(cmd);
    if(busy&&!urgent)return;
    cancelPreparation();
    if(!urgent)busy=true;
    render();message.textContent="Sending…";
    try{
      await send({cmd:axisHome?"home_axis":cmd,...(axisHome?{axis:cmd.slice(5)}:{}),...(text?{text}:{})});
      message.textContent="Command submitted to LinuxCNC. Follow the status to confirm the result.";
      if(cmd==="mdi"){entry(text);if(clearInput)input.value="";}
    }catch(error){
      message.textContent=error.message;
    }finally{if(!urgent)busy=false;render();}
  }
  for(const [cmd,id] of Object.entries(ids)){
    if(cmd!=="mdi")document.getElementById(id).addEventListener("click",()=>execute(cmd));
  }
  document.getElementById("mdi-form").addEventListener("submit",event=>{
    event.preventDefault();const text=document.getElementById("mdi-input").value.trim();
    if(text)execute("mdi",text);
  });
  heaters.forEach((button,index)=>button.addEventListener("click",()=>execute("mdi",index===0?"M8":"M9",false)));
  document.getElementById("mdi-clear-history").addEventListener("click",()=>history.replaceChildren());
  render();
  return {update(value,isFresh,isConnected){state=value;fresh=isFresh;connected=isConnected;render();}};
}
