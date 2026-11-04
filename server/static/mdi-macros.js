const STORAGE_KEY="foamomatic.mdi.macros";
function validate(command){
  if(command.length>254||/[^\x20-\x7e]/.test(command))throw new Error("Enter one ASCII line, at most 254 characters.");
  return command.trim();
}
export function createMdiMacros(load){
  let macros=Array.from({length:4},(_,i)=>({name:`Macro ${i+1}`,command:""}));
  try{
    const saved=JSON.parse(localStorage.getItem(STORAGE_KEY));
    if(Array.isArray(saved)&&saved.length===4)macros=saved.map((item,i)=>({
      name:String(item.name||`Macro ${i+1}`).slice(0,24),command:validate(String(item.command||""))
    }));
  }catch{}
  const container=document.getElementById("mdi-macros");
  const dialog=document.getElementById("mdi-macro-dialog");
  const fields=document.getElementById("mdi-macro-fields");
  const error=document.getElementById("mdi-macro-error");
  function render(){
    container.replaceChildren();
    macros.forEach(macro=>{
      const button=document.createElement("button");button.type="button";button.className="secondary";
      button.textContent=macro.name;button.disabled=!macro.command;
      button.title=macro.command?`${macro.command}\nLoad into input; press Enter to send.`:"Configure with Edit macros.";
      button.addEventListener("click",()=>load(macro.command));container.append(button);
    });
  }
  let inputs=[];
  document.getElementById("mdi-edit-macros").addEventListener("click",()=>{
    fields.replaceChildren();error.textContent="";
    inputs=macros.map((macro,i)=>{
      const row=document.createElement("div");row.className="mdi-macro-row";
      const pair=[['Button name',macro.name,24],['G-code line',macro.command,254]].map(([title,value,max])=>{
        const label=document.createElement("label");label.textContent=`${title} ${i+1}`;
        const input=document.createElement("input");input.type="text";input.value=value;input.maxLength=max;
        input.autocomplete="off";input.spellcheck=false;label.append(input);row.append(label);return input;
      });fields.append(row);return pair;
    });dialog.showModal();
  });
  document.getElementById("mdi-macro-cancel").addEventListener("click",()=>dialog.close());
  document.getElementById("mdi-macro-form").addEventListener("submit",event=>{
    event.preventDefault();
    try{
      const updated=inputs.map(([name,command],i)=>({name:name.value.trim().slice(0,24)||`Macro ${i+1}`,command:validate(command.value)}));
      localStorage.setItem(STORAGE_KEY,JSON.stringify(updated));macros=updated;render();dialog.close();
    }catch(exc){error.textContent=exc.message||"Could not save macro settings.";}
  });render();
}
