const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("bossApi", {
  baseUrl: process.env.BOSS_API_BASE || "http://127.0.0.1:8765",
  selectDirectory: () => ipcRenderer.invoke("select-directory")
});
