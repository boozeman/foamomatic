import {configureWire, updateWire, unavailableWire} from "./wire-view.js";
const byId = id => document.getElementById(id);
const letters = ["X", "Y", "U", "V"];
let socket = null, lastUpdate = 0, lastSample = null, connectedAt = 0, ready = false;
let latest = null;
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
  for (const axis of letters) for (const cell of rows[axis].slice(1)) cell.textContent = "—";
  for (const id of ["estop", "enabled", "mode", "program", "file", "line"]) byId(id).textContent = "—";
  byId("error").hidden = true;
}
function invalid(message) {
  clearValues();
  document.body.classList.add("stale");
  connection("Tilatieto puuttuu", "warn");
  byId("notice").textContent = message;
}
const format = value => typeof value === "number" && Number.isFinite(value)
  ? (Math.abs(value) < 0.0005 ? 0 : value).toFixed(3) : "—";
function show(data) {
  if (!data || !letters.every(a => typeof data.machine?.[a] === "number" &&
      Number.isFinite(data.machine[a]) && typeof data.work?.[a] === "number" &&
      Number.isFinite(data.work[a])) || !Array.isArray(data.homed)) {
    invalid("Palvelimen tilatieto on puutteellinen."); return;
  }
  // Detect frozen/replayed adapter samples, not merely an open WebSocket.
  if (typeof data.sample_monotonic !== "number" || !Number.isFinite(data.sample_monotonic)) {
    invalid("Tilatiedon aikaleima puuttuu."); return;
  }
  if (data.sample_monotonic === lastSample) return;
  lastSample = data.sample_monotonic;
  lastUpdate = Date.now();
  latest = data;
  updateWire(data);
  document.body.classList.remove("stale");
  connection("Yhteys kunnossa", "live");
  byId("notice").textContent = "LinuxCNC:n tilatiedot päivittyvät. Näkymä ei lähetä ohjauskomentoja.";
  letters.forEach((a, i) => {
    rows[a][1].textContent = format(data.machine[a]);
    rows[a][2].textContent = format(data.work[a]);
    rows[a][3].textContent = data.homed[i] === 1 || data.homed[i] === true ? "Kotiajettu" :
      data.homed[i] === 0 || data.homed[i] === false ? "Ei kotiajettu" : "—";
  });
  const booleanText = (v, yes, no) => v === true ? yes : v === false ? no : "—";
  byId("estop").textContent = booleanText(data.estop, "Aktiivinen", "Ei aktiivinen");
  byId("enabled").textContent = booleanText(data.enabled, "Päällä", "Pois päältä");
  byId("mode").textContent = ({1:"Käsiajo",2:"Automaatti",3:"MDI"})[data.task_mode] ?? "Tuntematon";
  byId("program").textContent = data.paused ? "Tauolla" :
    ({1:"Valmis",2:"Luetaan",3:"Odottaa",4:"Odottaa liikettä"})[data.interp_state] ?? "Tuntematon";
  byId("file").textContent = data.file || "Ei ohjelmaa";
  byId("line").textContent = Number.isInteger(data.line) ? String(data.line) : "—";
  byId("error").hidden = !data.error;
  byId("error").textContent = data.error ? "LinuxCNC: " + (data.error.message ?? "Tuntematon virhe") : "";
}
function disconnect() {
  const old = socket;
  socket = null; ready = false;
  if (old) old.close();
  clearValues();
  connection("Ei yhteyttä");
  byId("notice").textContent = "Yhteys katkaistu.";
  byId("connect").disabled = false;
  byId("disconnect").disabled = true;
  byId("updated").textContent = "Ei tilapäivityksiä";
}
byId("disconnect").addEventListener("click", disconnect);
byId("login").addEventListener("submit", event => {
  event.preventDefault();
  const token = byId("token").value;
  if (!token || socket) return;
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  socket = ws; ready = false; lastUpdate = 0; lastSample = null; connectedAt = Date.now();
  clearValues(); connection("Yhdistetään…");
  byId("notice").textContent = "Odotetaan palvelimen vahvistusta.";
  byId("connect").disabled = true; byId("disconnect").disabled = false;
  ws.addEventListener("open", () => {
    if (socket !== ws) return;
    ws.send(JSON.stringify({token, read_only: true}));
    byId("token").value = "";
  });
  ws.addEventListener("message", event => {
    if (socket !== ws) return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "ready") { ready = true; configureWire(msg.geometry); connection("Odotetaan tilatietoa"); }
      if (msg.type === "status" && ready) {
        if (msg.ok) show(msg.data);
        else invalid(msg.error || "LinuxCNC:n tilatietoa ei saada.");
      }
    } catch { invalid("Palvelimen viestiä ei voitu lukea."); }
  });
  ws.addEventListener("close", event => {
    if (socket !== ws) return;
    const authenticated = ready;
    disconnect();
    const reasons = {
      "Invalid token": "Yhteysavain ei vastaa käynnissä olevan kontin FOAM_TOKEN-arvoa.",
      "Origin not allowed": "Sivun osoite puuttuu palvelimen FOAM_ORIGINS-asetuksesta.",
      "Invalid authentication message": "Tunnistautumisviesti oli virheellinen.",
      "Connection timeout": "Palvelimen yhteysaikakatkaisu.",
      "Internal server error": "Palvelimen sisäinen virhe. Tarkista kontin loki."
    };
    byId("notice").textContent = (reasons[event.reason] || (authenticated
      ? "Yhteys katkesi. Yhdistä uudelleen nähdäksesi tuoreen tilan."
      : "Yhteyttä ei hyväksytty. Tarkista yhteysavain ja FOAM_ORIGINS.")) +
      " (WebSocket " + event.code + ")";
  });
  ws.addEventListener("error", () => {
    if (socket === ws) byId("notice").textContent = "Verkkoyhteys ei onnistu.";
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
    byId("updated").textContent = "Viimeisin tilapäivitys " + age.toFixed(1) + " s sitten";
    if (age > 3 && latest) invalid("Tilatieto on vanhentunut. Odotetaan uutta päivitystä.");
  }
}, 500);
window.addEventListener("pagehide", disconnect);
