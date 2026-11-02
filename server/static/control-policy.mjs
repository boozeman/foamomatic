export function permissions(state, fresh, connected) {
  const idle=fresh&&state?.interp_state===1&&!state?.paused;
  const base=idle&&state?.enabled===true&&state?.estop===false&&!state?.mdi_pending;
  const homed=Array.isArray(state?.homed)&&state.homed.length===4&&state.homed.every(v=>v===1||v===true);
  return {
    estop:connected, abort:connected, disable:connected,
    enable:fresh&&state?.estop===false&&state?.enabled===false&&idle,
    reset_estop:fresh&&state?.estop===true,
    mdi_mode:base&&homed&&state.task_mode!==3,
    manual:base&&state.task_mode!==1,
    mdi:base&&homed&&state.task_mode===3
  };
}
