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
  if(!connected)return "Ei yhteyttä palvelimeen.";
  if(!fresh||!state)return "Odotetaan tuoretta koneen tilaa.";
  if(state.estop!==false)return "Kuittaa hätäseis ennen MDI:tä.";
  if(state.enabled!==true)return "Kytke koneen käyttölupa päälle.";
  if(state.homing?.some(Boolean))return "Kotiajo on käynnissä. Odota sen valmistumista.";
  const letters=["X","Y","U","V"];
  const missing=letters.filter((_,i)=>state.homed?.[i]!==1&&state.homed?.[i]!==true);
  if(missing.length)return "Kotiajamatta: "+missing.join(", ")+". Kotiaja nämä akselit LinuxCNC:ssä.";
  if(state.mdi_pending)return "Odotetaan edellisen MDI-komennon kuittausta tai valmistumista.";
  if(state.interp_state!==1||state.paused)return "Kone suorittaa komentoa tai on tauolla. Keskeytä tarvittaessa.";
  if(state.task_mode!==3)return "Valitse MDI-tila ja odota tilan vahvistusta.";
  return "MDI-tila on käytössä. Voit lähettää yhden komentorivin.";
}
