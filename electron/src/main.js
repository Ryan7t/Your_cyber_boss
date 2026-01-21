const { app, BrowserWindow, ipcMain, dialog, Menu } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

const DEFAULT_PORT = 8765;
let backendProcess = null;
let mainWindow = null;

function resolveBackendCommand(port) {
  if (app.isPackaged) {
    const backendName = process.platform === "win32" ? "backend.exe" : "backend";
    const backendPath = path.join(process.resourcesPath, "backend", backendName);
    return { command: backendPath, args: ["--host", "127.0.0.1", "--port", String(port)] };
  }

  const pythonCmd = process.env.BOSS_PYTHON || (process.platform === "win32" ? "python" : "python3");
  const serverScript = path.join(__dirname, "..", "..", "server.py");
  return { command: pythonCmd, args: [serverScript, "--host", "127.0.0.1", "--port", String(port)] };
}

function startBackend(port) {
  const { command, args } = resolveBackendCommand(port);
  backendProcess = spawn(command, args, {
    stdio: "ignore",
    windowsHide: true,
    env: {
      ...process.env,
      BOSS_DATA_DIR: app.getPath("userData")
    }
  });
}

function stopBackend() {
  if (!backendProcess) {
    return;
  }
  try {
    backendProcess.kill();
  } catch (err) {
    // ignore shutdown errors
  }
  backendProcess = null;
}

function waitForBackend(port, timeoutMs = 15000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/health`, res => {
        if (res.statusCode === 200) {
          res.resume();
          resolve();
          return;
        }
        res.resume();
        retry();
      });
      req.on("error", retry);
    };

    const retry = () => {
      if (Date.now() - start > timeoutMs) {
        reject(new Error("Backend did not respond in time."));
        return;
      }
      setTimeout(check, 300);
    };

    check();
  });
}

function createMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac
      ? [
          {
            label: "BossAgent",
            submenu: [
              { role: "about", label: "关于" },
              { type: "separator" },
              { role: "hide", label: "隐藏" },
              { role: "hideOthers", label: "隐藏其他" },
              { role: "unhide", label: "显示全部" },
              { type: "separator" },
              { role: "quit", label: "退出" }
            ]
          }
        ]
      : []),
    {
      label: "文件",
      submenu: [
        {
          label: "刷新",
          accelerator: "CmdOrCtrl+R",
          click: () => {
            if (mainWindow) {
              mainWindow.reload();
            }
          }
        },
        {
          label: "重新加载",
          accelerator: "CmdOrCtrl+Shift+R",
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.reloadIgnoringCache();
            }
          }
        },
        { type: "separator" },
        { role: isMac ? "close" : "quit", label: isMac ? "关闭窗口" : "退出" }
      ]
    },
    {
      label: "查看",
      submenu: [
        {
          label: "打开调试面板",
          accelerator: isMac ? "Alt+Cmd+I" : "Ctrl+Shift+I",
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.toggleDevTools();
            }
          }
        },
        { type: "separator" },
        { role: "togglefullscreen", label: "全屏" }
      ]
    },
    {
      label: "窗口",
      submenu: [
        { role: "minimize", label: "最小化" },
        { role: "zoom", label: "缩放" }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function createWindow(port) {
  process.env.BOSS_API_BASE = `http://127.0.0.1:${port}`;

  const win = new BrowserWindow({
    width: 1200,
    height: 760,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#0f1113",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow = win;
  createMenu();
}

app.whenReady().then(async () => {
  const port = Number(process.env.BOSS_BACKEND_PORT || DEFAULT_PORT);
  startBackend(port);

  try {
    await waitForBackend(port);
    createWindow(port);
  } catch (err) {
    dialog.showErrorBox("Backend Error", err.message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  stopBackend();
});

ipcMain.handle("select-directory", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory"]
  });
  if (result.canceled || result.filePaths.length === 0) {
    return "";
  }
  return result.filePaths[0];
});
