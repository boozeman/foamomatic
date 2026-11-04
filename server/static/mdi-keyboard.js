export function createMdiKeyboard() {
  const input=document.getElementById("mdi-input");
  const keys=document.getElementById("mdi-keyboard-keys");
  const form=document.getElementById("mdi-form");
  const submit=document.getElementById("mdi-send");
  input.inputMode="none";
  for(const button of keys.querySelectorAll("button")){
    // Keep the input selection when tapping a key.
    button.addEventListener("pointerdown",event=>event.preventDefault());
    button.addEventListener("click",()=>{
      if(input.disabled||keys.disabled||button.type==="submit")return;
      const action=button.dataset.mdiAction;
      if(action==="enter"){
        if(!submit.disabled&&input.value.trim())form.requestSubmit(submit);
        return;
      }
      let start=input.selectionStart??input.value.length;
      let end=input.selectionEnd??start;
      let text=button.dataset.mdiKey??"";
      if(action==="clear"){start=0;end=input.value.length;}
      if(action==="backspace"&&start===end)start=Math.max(0,start-1);
      if(input.value.length-(end-start)+text.length>input.maxLength)return;
      input.setRangeText(text,start,end,"end");
      input.dispatchEvent(new Event("input",{bubbles:true}));
      input.focus({preventScroll:true});
    });
  }
  return {setEnabled(enabled){keys.disabled=!enabled;}};
}
