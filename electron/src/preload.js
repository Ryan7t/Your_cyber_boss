const { contextBridge, ipcRenderer } = require("electron");

const parseNumber = (value, fallback) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

contextBridge.exposeInMainWorld("bossApi", {
  baseUrl: process.env.BOSS_API_BASE || "http://127.0.0.1:8765",
  startupTimeoutMs: parseNumber(process.env.BOSS_STARTUP_TIMEOUT_MS, 30000),
  requestTimeoutMs: parseNumber(process.env.BOSS_REQUEST_TIMEOUT_MS, 12000),
  eventsTimeoutMs: parseNumber(process.env.BOSS_EVENTS_TIMEOUT_MS, 8000),
  streamTimeoutMs: parseNumber(process.env.BOSS_STREAM_TIMEOUT_MS, 150000),
  selectDirectory: () => ipcRenderer.invoke("select-directory")
});
