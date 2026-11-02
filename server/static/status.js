import {createProgramControls} from "./program-ui.js";
import {createControls} from "./controls-ui.js";
import "./tabs.js";
import {setToken} from "./auth-state.mjs";
import "./preview-ui.js?v=12";
import {configureWire, updateWire, unavailableWire} from "./wire-view.js?v=12";
const byId = id => document.getElementById(id);
const letters = ["X", "Y", "U", "V"];
let socket = null, lastUpdate = 0, lastSample = null, connectedAt = 0, ready = false;
let latest = null;
let commandToken=null, sequence=0;
const pending=new Map();
const controls=createControls(sendCommand);
const programs=createProgramControls(sendCommand);
function sendCommand(payload) {
  if(!ready||socket?.readyState!==WebSocket.OPEN) return Promise.reject(new Error("Disconnected."));
  const id=String(++sequence);
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{
      pending.delete(id);
      reject(new Error("No acknowledgement received. The command will not be retried; check the machine state."));
    },2000);
    pending.set(id,{resolve,reject,timer});
    socket.send(JSON.stringify({...payload,id,command_token:commandToken}));
    commandToken=null;
  });
}
const connectionDialog=byId("connection-dialog");
function syncConnectionButton(){
  byId("connection-toggle").textContent=ready?"Disconnect":socket?"Cancel":"Connect";
}
function cancelConnectionDialog(){
  connectionDialog.close();
  if(socket&&!ready)disconnect();
  byId("token").value="";
}
byId("connection-toggle").addEventListener("click",()=>{
  if(socket){disconnect();return;}
  byId("login-feedback").textContent="";
  connectionDialog.showModal();
  byId("token").focus();
});
byId("login-cancel").addEventListener("click",cancelConnectionDialog);
connectionDialog.addEventListener("cancel",event=>{
  event.preventDefault();cancelConnectionDialog();
});

const rows = {};
for (const [i, axis] of letters.entries()) {
  const row = document.createElement("tr");
  const cells = [axis, "—", "—", "—"].map(text => {
    const cell = document.createElement("td"); cell.textContent = text; row.append(cell); return cell;
  });
  byId(i < 2 ? "left" : "right").append(row);
  rows[axis] = cells;
}
function connection(text, kind = "") {
  byId("connection").textContent = text;
  byId("connection").className = "badge " + kind;
}
function clearValues() {
  unavailableWire();
  latest = null;
  controls.update(null,false,ready);
  programs.update(null,false,ready);
  for (const axis of letters) for (const cell of rows[axis].slice(1)) cell.textContent = "—";
  for (const id of ["estop", "enabled", "mode", "program", "file", "line"]) byId(id).textContent = "—";
  byId("error").hidden = true;
}
function invalid(message) {
  clearValues();
  document.body.classList.add("stale");
  connection("Status unavailable", "warn");
  byId("notice").textContent = message;
}
const format = value => typeof value === "number" && Number.isFinite(value)
  ? (Math.abs(value) < 0.0005 ? 0 : value).toFixed(3) : "—";
function show(data) {
  if (!data || !letters.every(a => typeof data.machine?.[a] === "number" &&
      Number.isFinite(data.machine[a]) && typeof data.work?.[a] === "number" &&
      Number.isFinite(data.work[a])) || !Array.isArray(data.homed)) {
    invalid("Server status data is incomplete."); return;
  }
  // Detect frozen/replayed adapter samples, not merely an open WebSocket.
  if (typeof data.sample_monotonic !== "number" || !Number.isFinite(data.sample_monotonic)) {
    invalid("Status timestamp is missing."); return;
  }
  if (data.sample_monotonic === lastSample) return;
  lastSample = data.sample_monotonic;
  lastUpdate = Date.now();
  latest = data;
  updateWire(data);
  controls.update(data,true,ready);
  programs.update(data,true,ready);
  document.body.classList.remove("stale");
  connection("Connected", "live");
  byId("notice").textContent = "Receiving LinuxCNC status.";
  letters.forEach((a, i) => {
    rows[a][1].textContent = format(data.machine[a]);
    rows[a][2].textContent = format(data.work[a]);
    rows[a][3].textContent = data.homed[i] === 1 || data.homed[i] === true ? "Homed" :
      data.homed[i] === 0 || data.homed[i] === false ? "Not homed" : "—";
  });
  const booleanText = (v, yes, no) => v === true ? yes : v === false ? no : "—";
  byId("estop").textContent = booleanText(data.estop, "Active", "Inactive");
  byId("enabled").textContent = booleanText(data.enabled, "On", "Off");
  byId("mode").textContent = ({1:"Manual",2:"Auto",3:"MDI"})[data.task_mode] ?? "Unknown";
  byId("program").textContent = data.paused ? "Paused" :
    ({1:"Idle",2:"Reading",3:"Waiting",4:"Waiting for motion"})[data.interp_state] ?? "Unknown";
  byId("file").textContent = data.file || "No program";
  byId("line").textContent = Number.isInteger(data.line) ? String(data.line) : "—";
  byId("error").hidden = !data.error;
  byId("error").textContent = data.error ? "LinuxCNC: " + (data.error.message ?? "Unknown error") : "";
}
function disconnect() {
  setToken("");
  commandToken=null;
  for(const request of pending.values()){
    clearTimeout(request.timer);request.reject(new Error("Connection lost; the command will not be retried."));
  }
  pending.clear();
  const old = socket;
  socket = null; ready = false;
  if (old) old.close();
  clearValues();
  connection("Disconnected");
  byId("notice").textContent = "Disconnected.";
  byId("connect").disabled = false;
  syncConnectionButton();
  byId("updated").textContent = "No status updates";
}

byId("login").addEventListener("submit", event => {
  event.preventDefault();
  const token = byId("token").value;
  if (!token || socket) return;
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  socket = ws; ready = false; lastUpdate = 0; lastSample = null; connectedAt = Date.now();
  clearValues(); connection("Connecting…");
  byId("notice").textContent = "Waiting for server confirmation.";
  byId("connect").disabled = true;
  byId("login-feedback").textContent="Connecting…";
  syncConnectionButton();
  ws.addEventListener("open", () => {
    if (socket !== ws) return;
    ws.send(JSON.stringify({token, read_only: false}));
    byId("token").value = "";
  });
  ws.addEventListener("message", event => {
    if (socket !== ws) return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "ready") { ready = true; syncConnectionButton(); connectionDialog.close(); setToken(token); configureWire(msg.geometry); connection("Waiting for status"); }
      if(msg.type==="ack"){
        const request=pending.get(msg.id);
        if(request){clearTimeout(request.timer);pending.delete(msg.id);
          if(msg.ok)request.resolve(msg.data);else request.reject(new Error(msg.error||"Command rejected."));
        }
      }
      if (msg.type === "status" && ready) {
        commandToken=msg.command_token;
        if (msg.ok) show(msg.data);
        else invalid(msg.error || "LinuxCNC status is unavailable.");
      }
    } catch { invalid("Could not read the server message."); }
  });
  ws.addEventListener("close", event => {
    if (socket !== ws) return;
    const authenticated = ready;
    disconnect();
    const reasons = {
      "Invalid token": "The token does not match FOAM_TOKEN in the running container.",
      "Origin not allowed": "This page origin is missing from the server FOAM_ORIGINS setting.",
      "Invalid authentication message": "Invalid authentication message.",
      "Connection timeout": "Server connection timed out.",
      "Internal server error": "Internal server error. Check the container log."
    };
    byId("notice").textContent = (reasons[event.reason] || (authenticated
      ? "Connection lost. Reconnect to receive fresh status."
      : "Connection rejected. Check the token and FOAM_ORIGINS.")) +
      " (WebSocket " + event.code + ")";
    byId("login-feedback").textContent=byId("notice").textContent;
  });
  ws.addEventListener("error", () => {
    if (socket === ws) byId("notice").textContent = "Network connection failed.";
  });
});
setInterval(() => {
  if (!socket) return;
  // Keep an authenticated connection open while the adapter recovers.
  if (!ready && Date.now() - connectedAt > 6000) {
    socket.close(); return;
  }
  if (lastUpdate) {
    const age = (Date.now() - lastUpdate) / 1000;
    byId("updated").textContent = "Last status update " + age.toFixed(1) + " s ago";
    controls.update(latest,age<=1&&!!latest,ready);
    programs.update(latest,age<=1&&!!latest,ready);
    if (age > 3 && latest) invalid("Status is stale. Waiting for a fresh update.");
  }
}, 500);
window.addEventListener("pagehide", disconnect);
