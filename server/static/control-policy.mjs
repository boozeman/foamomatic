export function permissions(state, fresh, connected) {
  const idle=connected&&fresh&&state?.interp_state===1&&!state?.paused&&!state?.homing?.some(Boolean);
  const base=idle&&state?.enabled===true&&state?.estop===false&&!state?.mdi_pending;
  const homed=Array.isArray(state?.homed)&&state.homed.length===4&&state.homed.every(v=>v===1||v===true);
  return {
    estop:connected, abort:connected, disable:connected,
    enable:fresh&&state?.estop===false&&state?.enabled===false&&idle,
    reset_estop:connected&&fresh&&state?.estop===true,
    home_all:base&&state.task_mode===1,
    home_axis:base&&state.task_mode===1,
    mdi_mode:base&&homed&&state.task_mode!==3,
    manual:base&&state.task_mode!==1,
    mdi:base&&homed&&state.task_mode===3
  };
}

export function mdiStatus(state, fresh, connected) {
  if(!connected)return "Not connected to the server.";
  if(!fresh||!state)return "Waiting for fresh machine status.";
  if(state.estop!==false)return "Reset E-stop before using MDI.";
  if(state.enabled!==true)return "Turn Machine On before using MDI.";
  if(state.homing?.some(Boolean))return "Homing is in progress. Wait for it to finish.";
  const letters=["X","Y","U","V"];
  const missing=letters.filter((_,i)=>state.homed?.[i]!==1&&state.homed?.[i]!==true);
  if(missing.length)return "Not homed: "+missing.join(", ")+". Home these axes in LinuxCNC.";
  if(state.mdi_pending)return "Waiting for the previous MDI command to be acknowledged or completed.";
  if(state.interp_state!==1||state.paused)return "The machine is running a command or paused. Abort if needed.";
  if(state.task_mode!==3)return "Select MDI mode and wait for confirmation.";
  return "MDI mode is active. You can submit one command line.";
}
