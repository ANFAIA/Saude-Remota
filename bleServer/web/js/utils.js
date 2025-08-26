// /js/utils.js
// Cliente WS + DOM + envío a Firebase RTDB (usa config externa).

import { initializeApp } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-app.js";
import { getDatabase, ref, push, serverTimestamp as rtdbTs } from "https://www.gstatic.com/firebasejs/9.22.2/firebase-database.js";

// ⬇️ Importa tu configuración desde archivo ignorado en git
import { firebaseConfig } from "./firebaseConfig.js";

// Inicializa Firebase con config externa
const app = initializeApp(firebaseConfig);
const rtdb = getDatabase(app);
const readingsRef = ref(rtdb, "readings");

(function () {
  const $ = (id) => document.getElementById(id);

  const elStatus = $("remota-saude-conection-status");
  const elDot = $("remota-saude-conection-animation");
  const elRisk = $("remota-saude-last-risk-received");
  const elAcc = $("remota-saude-last-accuracy-received");
  const elAgo = $("remota-saude-last-data-received");
  const elTemp = $("remota-saude-last-temperature-received");
  const elBpm = $("remota-saude-last-bpm-received");
  const elSpo2 = $("remota-saude-last-spo2-received");
  const riskWrapper = document.querySelector(".rs-body__risk__color-wrapper");

  function setStatus(txt, cls) {
    if (elStatus) elStatus.textContent = txt;
    if (elDot) {
      elDot.classList.remove("ok", "error", "loading");
      if (cls) elDot.classList.add(cls);
    }
  }

  function timeAgo(ms) {
    const d = new Date(ms);
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - d.getTime()) / 1000));
    const mins = Math.floor(diffSec / 60);
    const hours = Math.floor(mins / 60);
    const days = Math.floor(hours / 24);
    if (days > 0) return `${days} ${days === 1 ? "día" : "días"}`;
    if (hours > 0) return `${hours} ${hours === 1 ? "hora" : "horas"}`;
    if (mins > 0) return `${mins} ${mins === 1 ? "minuto" : "minutos"}`;
    return `${diffSec} ${diffSec === 1 ? "segundo" : "segundos"}`;
  }

  function riskColor(p) {
    if (p >= 80) return ["#b32020", "#ef6868"]; // high risk
    if (p >= 50) return ["#c9741c", "#f0b06e"]; // medium
    if (p >= 20) return ["#c2c02b", "#f0ec7e"]; // low-moderate
    return ["#2b9c73", "#90e2c3"];              // very low
  }

  let lastTs = null;
  let agoTimer = null;
  function updateAgo() {
    if (!elAgo) return;
    if (!lastTs) { elAgo.textContent = "-"; return; }
    elAgo.textContent = timeAgo(lastTs);
  }

  function setRiskBackground(p) {
    if (!riskWrapper) return;
    const [c1,c2] = riskColor(p);
    riskWrapper.style.background = `linear-gradient(to top, ${c1}, ${c2})`;
  }

  function onData(msg) {
    if (!msg || !msg.data || typeof msg.ts !== "number") return;
    lastTs = msg.ts;

    const d = msg.data;
    const t = Number(d.temperature);
    const bpm = Number(d.bmp);
    const spo2 = Number(d.spo2);
    const prec = Number(d.modelPreccision); // 0..1
    const risk = Number(d.riskScore);       // 0..1

    if (elTemp && !Number.isNaN(t)) elTemp.textContent = t.toFixed(2);
    if (elBpm && !Number.isNaN(bpm)) elBpm.textContent = bpm.toFixed(0);
    if (elSpo2 && !Number.isNaN(spo2)) elSpo2.textContent = spo2.toFixed(1);

    if (elAcc && !Number.isNaN(prec)) elAcc.textContent = (prec * 100).toFixed(1);
    if (elRisk && !Number.isNaN(risk)) {
      const riskPct = risk <= 1 ? risk * 100 : risk;
      elRisk.textContent = riskPct.toFixed(1);
      setRiskBackground(riskPct);
    }

    if (!agoTimer) agoTimer = setInterval(updateAgo, 1000);
    updateAgo();

    // --- Enviar a RTDB ---
    const rec = {
      temperature: Number.isFinite(t) ? t : 0,
      bpm: Number.isFinite(bpm) ? bpm : 0,
      spo2: Number.isFinite(spo2) ? spo2 : 0,
      modelPreccision: Number.isFinite(prec) ? prec : 0,
      riskScore: Number.isFinite(risk) ? risk : 0,
      ts_ms: msg.ts || null,
      source: "web-proxy"
    };

    // Si quieres ignorar keep-alive, descomenta:
    // if (rec.spo2 === 0 && rec.bpm === 0) return;

    push(readingsRef, { ...rec, createdAt: rtdbTs() })
      .catch((e) => console.error("RTDB push error:", e));
  }

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
      } catch {
        console.warn("Mensaje no JSON:", ev.data);
      }
    });

    let closed = false;
    ws.addEventListener("close", () => {
      if (closed) return;
      closed = true;
      setTimeout(startWS, 1500);
    });
  }

  document.addEventListener("DOMContentLoaded", startWS);
})();
