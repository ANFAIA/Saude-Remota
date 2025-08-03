import { initializeApp } from "https://www.gstatic.com/firebasejs/9.22.1/firebase-app.js";
import { getAuth, signInAnonymously } from "https://www.gstatic.com/firebasejs/9.22.1/firebase-auth.js";
import {
    getDatabase,
    ref,
    get,
    query,
    orderByKey,
    limitToLast,
    startAt,
    onChildAdded
} from "https://www.gstatic.com/firebasejs/9.22.1/firebase-database.js";

const firebaseConfig = {
    apiKey: "AIzaSyCZPe0DeM15cQiU7tzpQ5qsI6XtUqXvJ7E",
    authDomain: "saude-remota.firebaseapp.com",
    databaseURL: "https://saude-remota-default-rtdb.europe-west1.firebasedatabase.app",
    projectId: "saude-remota",
    storageBucket: "saude-remota.firebasestorage.app",
    messagingSenderId: "789764262166",
    appId: "1:789764262166:web:f6240399915558976a6837",
    measurementId: "G-HVXM66YC4G"
};

const connectionStatus = [
    "Desconectado",
    "Conectando",
    "Conectado"
];

function changeStatus(mode, message = "") {
    const connectionStatusSpan = document.getElementById('remota-saude-conection-status');
    const connectionStatusVisualSpan = document.getElementById('remota-saude-conection-animation');

    connectionStatusVisualSpan.classList.remove('loading', 'ok', 'error');

    switch (mode) {
        case 1:
            connectionStatusSpan.textContent = connectionStatus[1];
            connectionStatusVisualSpan.classList.add('loading');
            //console.log(`[Estado: ${connectionStatus[1]}] ${message}`);
            break;
        case 2:
            connectionStatusSpan.textContent = connectionStatus[2];
            connectionStatusVisualSpan.classList.add('ok');
            //console.log(`[Estado: ${connectionStatus[2]}] ${message}`);
            break;
        default:
            connectionStatusVisualSpan.classList.add('error');
            connectionStatusSpan.textContent = connectionStatus[0];
            console.warn(`[Estado: ${connectionStatus[0]}] ${message}`);
            break;
    }
}

function checkDataConnection(timestamp, timeLimitMins = 10) {
    const now = Date.now();
    const diffMs = now - timestamp;
    return diffMs <= timeLimitMins * 60 * 1000;
}

function getTimeSinceLastMessage(timestamp) {
    const now = Date.now();
    let diff = now - Number(timestamp);

    if (isNaN(diff) || diff < 0) return null;

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(diff / (60 * 1000));
    const hours = Math.floor(diff / (60 * 60 * 1000));
    const days = Math.floor(diff / (24 * 60 * 60 * 1000));

    return { days, hours, minutes, seconds };
}

function updateInstantData(data) {
    const lastMessageSpan = document.getElementById('remota-saude-last-data-received');
    const lastTemp = document.getElementById('remota-saude-last-temperature-received');
    const lastBpm = document.getElementById('remota-saude-last-bpm-received');
    const lastSpo2 = document.getElementById('remota-saude-last-spo2-received');
    const lastRisk = document.getElementById('remota-saude-last-risk-received');
    const lastAccuracy = document.getElementById('remota-saude-last-accuracy-received');

    const riskContainer = document.querySelector('.rs-body__risk__color-wrapper');

    if (!data) {
        lastMessageSpan.textContent = '-';
        lastTemp.textContent = '-';
        lastBpm.textContent = '-';
        lastSpo2.textContent = '-';
        lastRisk.textContent = '-';
        lastAccuracy.textContent = '-';
        return;
    }

    const timeSinceLastMessage = getTimeSinceLastMessage(data.timestamp);
    if (timeSinceLastMessage) {
        if (timeSinceLastMessage.days > 0) {
            lastMessageSpan.textContent = `${timeSinceLastMessage.days} días`;
        } else if (timeSinceLastMessage.hours > 0) {
            lastMessageSpan.textContent = `${timeSinceLastMessage.hours} horas`;
        } else if (timeSinceLastMessage.minutes > 0) {
            lastMessageSpan.textContent = `${timeSinceLastMessage.minutes} minutos`;
        } else if (timeSinceLastMessage.seconds > 0) {
            lastMessageSpan.textContent = `${timeSinceLastMessage.seconds} segundos`;
        } else {
            lastMessageSpan.textContent = `0 segundos`;
        }
    } else {
        lastMessageSpan.textContent = '-';
    }

    const formatter = new Intl.NumberFormat('es-ES', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });

    lastTemp.textContent = formatter.format(Number(data.temperature));
    lastBpm.textContent = formatter.format(Number(data.bmp));
    lastSpo2.textContent = formatter.format(Number(data.spo2));
    lastRisk.textContent = formatter.format(Number(data.riskScore * 100));
    lastAccuracy.textContent = formatter.format(Number(data.modelPrecision));

    const colorValues = interpolateRiskColor(data.riskScore * 100);
    console.log(`linear-gradient(to top, ${colorValues[1]}, ${colorValues[0]})`);
    riskContainer.style.background = `linear-gradient(to top, ${colorValues[1]}, ${colorValues[0]})`;

}

function interpolateRiskColor(percent) {
    const clamped = Math.min(100, Math.max(0, percent));

    const successColor = getComputedStyle(document.documentElement).getPropertyValue('--success').trim() || '#009b62';
    const warningColor = getComputedStyle(document.documentElement).getPropertyValue('--warning').trim() || '#dcac00';
    const errorColor = getComputedStyle(document.documentElement).getPropertyValue('--error').trim() || '#9b0027';

    const hexToRgb = hex => {
        let h = hex.replace(/^#/, '');
        if (h.length === 3) h = h.split('').map(c => c + c).join('');
        const int = parseInt(h, 16);
        return {
            r: (int >> 16) & 255,
            g: (int >> 8) & 255,
            b: int & 255
        };
    };

    const rgbToHex = ({ r, g, b }) => {
        const toHex = n => n.toString(16).padStart(2, '0');
        return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
    };

    const lerp = (a, b, t) => a + (b - a) * t;

    const mixHex = (fromHex, toHex, t) => {
        const from = hexToRgb(fromHex);
        const to = hexToRgb(toHex);
        const r = Math.round(lerp(from.r, to.r, t));
        const g = Math.round(lerp(from.g, to.g, t));
        const b = Math.round(lerp(from.b, to.b, t));
        return rgbToHex({ r, g, b });
    };

    const rgbToHsl = ({ r, g, b }) => {
        r /= 255; g /= 255; b /= 255;
        const max = Math.max(r, g, b), min = Math.min(r, g, b);
        let h, s;
        const l = (max + min) / 2;

        if (max === min) {
            h = s = 0;
        } else {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            switch (max) {
                case r: h = ((g - b) / d + (g < b ? 6 : 0)); break;
                case g: h = ((b - r) / d + 2); break;
                case b: h = ((r - g) / d + 4); break;
            }
            h /= 6;
        }
        return { h, s, l };
    };

    const hslToRgb = ({ h, s, l }) => {
        const hue2rgb = (p, q, t) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1 / 6) return p + (q - p) * 6 * t;
            if (t < 1 / 2) return q;
            if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
            return p;
        };

        let r, g, b;
        if (s === 0) {
            r = g = b = l;
        } else {
            const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
            const p = 2 * l - q;
            r = hue2rgb(p, q, h + 1 / 3);
            g = hue2rgb(p, q, h);
            b = hue2rgb(p, q, h - 1 / 3);
        }
        return { r: Math.round(r * 255), g: Math.round(g * 255), b: Math.round(b * 255) };
    };

    let baseColor;
    if (clamped <= 50) {
        baseColor = mixHex(successColor, warningColor, clamped / 50);
    } else {
        baseColor = mixHex(warningColor, errorColor, (clamped - 50) / 50);
    }

    const baseRgb = hexToRgb(baseColor);
    const baseHsl = rgbToHsl(baseRgb);
    const adjustDelta = 0.12;
    let gradientLightness = baseHsl.l;
    if (baseHsl.l < 0.5) {
        gradientLightness = Math.min(1, baseHsl.l + adjustDelta);
    } else {
        gradientLightness = Math.max(0, baseHsl.l - adjustDelta);
    }
    const gradientRgb = hslToRgb({ h: baseHsl.h, s: baseHsl.s, l: gradientLightness });
    const gradientColor = rgbToHex(gradientRgb);

    return [baseColor, gradientColor];
}

async function setup() {
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);
    const db = getDatabase(app);

    const start = Date.now();
    let lastTimestamp = 0;

    async function check() {
        const ready = auth && db;

        if (ready) {
            try {
                await signInAnonymously(auth);
                console.log("Autentificado anónimamente");

                const rawRef = ref(db, 'raw');

                // 1. Obtener el último dato inicial
                const latestQuery = query(rawRef, orderByKey(), limitToLast(1));
                const snapshot = await get(latestQuery);
                const data = snapshot.val();

                if (!data) {
                    changeStatus(0, 'Conectado, pero sin datos');
                    updateInstantData(null);
                } else {
                    const [[ts, val]] = Object.entries(data);
                    lastTimestamp = Number(ts);
                    const lastEntry = {
                        timestamp: lastTimestamp,
                        temperature: val.temperature,
                        bmp: val.bmp,
                        spo2: val.spo2,
                        modelPrecision: val.modelPrecision,
                        riskScore: val.riskScore
                    };
                    updateInstantData(lastEntry);
                    if (!checkDataConnection(lastEntry.timestamp, 10)) {
                        changeStatus(0, 'No se reciben datos desde hace más de 10 minutos');
                    } else {
                        changeStatus(2);
                    }
                }

                // 2. Escuchar solo los nuevos (clave > lastTimestamp)
                const newEntriesQuery = query(rawRef, orderByKey(), startAt(String(lastTimestamp + 1)));
                onChildAdded(newEntriesQuery, childSnap => {
                    const key = childSnap.key;
                    if (!key) return;
                    const ts = Number(key);
                    if (ts <= lastTimestamp) return; // seguridad extra

                    const val = childSnap.val();
                    lastTimestamp = ts;
                    const newEntry = {
                        timestamp: ts,
                        temperature: val.temperature,
                        bmp: val.bmp,
                        spo2: val.spo2,
                        modelPrecision: val.modelPrecision,
                        riskScore: val.riskScore
                    };
                    updateInstantData(newEntry);
                    if (!checkDataConnection(newEntry.timestamp, 10)) {
                        changeStatus(0, 'No se reciben datos desde hace más de 10 minutos');
                    } else {
                        changeStatus(2);
                    }
                }, err => {
                    console.warn('Error al recibir un nuevo dato en raw:', err);
                });

            } catch (err) {
                changeStatus(0, 'Error autentificándose: ' + err);
            }
        } else if (Date.now() - start > 10000) {
            changeStatus(0, 'Las librerías de firebase no se cargaron en el tiempo esperado');
        } else {
            setTimeout(check, 500);
        }
    }

    check();
}

document.addEventListener('DOMContentLoaded', setup);
