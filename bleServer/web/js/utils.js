// /js/utils.js
// Minimal client: connects to WS, updates the DOM, and shows relative time
// Expects messages shaped as: { timestamp: <ms>, data: { temperature, bpm, spo2, modelPrecision, riskScore } }
(function () { //esto crea una función y la ejecuta inmediatamente
  const $ = (id) => document.getElementById(id); //define una función flecha $ que recibe un id y devuelve el elemento HTML con ese id

  const elStatus = $("remota-saude-conection-status");
  const elDot = $("remota-saude-conection-animation");
  const elRisk = $("remota-saude-last-risk-received");
  const elAcc = $("remota-saude-last-accuracy-received");
  const elAgo = $("remota-saude-last-data-received");
  const elTemp = $("remota-saude-last-temperature-received");
  const elBpm = $("remota-saude-last-bpm-received");
  const elSpo2 = $("remota-saude-last-spo2-received");
  const riskWrapper = document.querySelector(".rs-body__risk__color-wrapper"); //se guardan en variables los elementos de la página que se va a actualizar

  function setStatus(txt, cls) {
    if (elStatus) elStatus.textContent = txt;
    if (elDot) {
      elDot.classList.remove("ok", "error", "loading");
      if (cls) elDot.classList.add(cls);
    }
  } //el estado se ve y se colorea/animará por CSS según la clase

  //relative time en español
  function timeAgo(ms) {
    const d = new Date(ms); //convierte timestamp a fecha
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - d.getTime()) / 1000));
    const mins = Math.floor(diffSec / 60);
    const hours = Math.floor(mins / 60);
    const days = Math.floor(hours / 24);
    if (days > 0) return `${days} ${days === 1 ? "día" : "días"}`;
    if (hours > 0) return `${hours} ${hours === 1 ? "hora" : "horas"}`;
    if (mins > 0) return `${mins} ${mins === 1 ? "minuto" : "minutos"}`;
    return `${diffSec} ${diffSec === 1 ? "segundo" : "segundos"}`; //si es menos de 1 minuto, devuelve segundos
  }

  function riskColor(p) {
    //p de [0,100]
    if (p >= 80) return ["#b32020", "#ef6868"]; //riesgo alto (rojo)
    if (p >= 50) return ["#c9741c", "#f0b06e"]; //riesgo medio (naranja)
    if (p >= 20) return ["#c2c02b", "#f0ec7e"]; //riesgo moderado (amarillo)
    return ["#2b9c73", "#90e2c3"]; //riesgo bajo (verde)
  }

  let lastTs = null; //guardará el timestamp del último mensaje recibido
  let agoTimer = null;
  function updateAgo() {
    if (!elAgo) return;
    if (!lastTs) { elAgo.textContent = "-"; return; }
    elAgo.textContent = timeAgo(lastTs);
  }

  function setRiskBackground(p) {
    if (!riskWrapper) return;
    const [c1,c2] = riskColor(p);
    riskWrapper.style.background = `linear-gradient(to top, ${c1}, ${c2})`; //degradado vertical
  }

  function onData(msg) { //esta función se llama cuando llega un mensaje JSON
    if (!msg || !msg.data || typeof msg.ts !== "number") return;
    lastTs = msg.ts;
    const d = msg.data;
    const t = Number(d.temperature);
    const bpm = Number(d.bmp);
    const spo2 = Number(d.spo2);
    const prec = Number(d.modelPreccision); //0..1
    const risk = Number(d.riskScore); //0..1

    if (elTemp && !Number.isNaN(t)) elTemp.textContent = t.toFixed(2); //temperatura con 2 decimales
    if (elBpm && !Number.isNaN(bpm)) elBpm.textContent = bpm.toFixed(0);
    if (elSpo2 && !Number.isNaN(spo2)) elSpo2.textContent = spo2.toFixed(1);

    if (elAcc && !Number.isNaN(prec)) elAcc.textContent = (prec * 100).toFixed(1);
    if (elRisk && !Number.isNaN(risk)) {
      const riskPct = risk <= 1 ? risk * 100 : risk; //si ya viene en porcentaje, lo deja tal cual
      elRisk.textContent = riskPct.toFixed(1);
      setRiskBackground(riskPct);
    }

    if (!agoTimer) {
      agoTimer = setInterval(updateAgo, 1000);
    }
    updateAgo(); //se llama a updateAgo inmediatamente para que no tarde 1 segundo en aparecer
  }

  //conectar WS
  function startWS() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${proto}://${location.host}/ws`;
    setStatus("Conectando…", "loading");
    const ws = new WebSocket(wsUrl);

    ws.addEventListener("open", () => setStatus("Conectado", "ok"));
    ws.addEventListener("close", () => setStatus("Desconectado", "error"));
    ws.addEventListener("error", () => setStatus("Error", "error"));
    ws.addEventListener("message", (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        onData(msg);
      } catch (e) {
        console.warn("Mensaje no JSON:", ev.data); //no rompe el programa
      }
    });

    //lógica de reconexión
    let closed = false; //closed es un candado para que la reconexión sólo se programe una vez
    ws.addEventListener("close", () => {
      if (closed) return;
      closed = true; 
      setTimeout(startWS, 1500);
    });
  }

  document.addEventListener("DOMContentLoaded", startWS);
})();