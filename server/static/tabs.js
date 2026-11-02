const tabs=[...document.querySelectorAll('[role="tab"]')];
function select(tab,focus=false){
  for(const item of tabs){
    const selected=item===tab;
    item.setAttribute("aria-selected",String(selected));item.tabIndex=selected?0:-1;
    document.getElementById(item.getAttribute("aria-controls")).hidden=!selected;
  }
  if(focus)tab.focus();
}
for(const [index,tab] of tabs.entries()){
  tab.addEventListener("click",()=>select(tab));
  tab.addEventListener("keydown",event=>{
    let target;
    if(event.key==="ArrowRight")target=tabs[(index+1)%tabs.length];
    if(event.key==="ArrowLeft")target=tabs[(index+tabs.length-1)%tabs.length];
    if(event.key==="Home")target=tabs[0];
    if(event.key==="End")target=tabs.at(-1);
    if(target){event.preventDefault();select(target,true);}
  });
}
