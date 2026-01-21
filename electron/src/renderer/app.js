const apiBase = window.bossApi.baseUrl;
const statusEl = document.getElementById("status");
const messagesEl = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const nudgeBtn = document.getElementById("nudgeBtn");
const clearHistoryBtn = document.getElementById("clearHistory");
const saveConfigBtn = document.getElementById("saveConfigBtn");
const pickDirBtn = document.getElementById("pickDirBtn");
const modelInput = document.getElementById("modelInput");
const baseUrlInput = document.getElementById("baseUrlInput");
const apiKeyInput = document.getElementById("apiKeyInput");
const docsDirInput = document.getElementById("docsDirInput");
const docList = document.getElementById("docList");
const timerStatus = document.getElementById("timerStatus");
const timerRemaining = document.getElementById("timerRemaining");
const timerMeta = document.getElementById("timerMeta");
const timerFill = document.getElementById("timerFill");

async function apiFetch(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`);
  }
  return response.json();
}

function setStatus(text, ok = true) {
  statusEl.textContent = text;
  statusEl.style.borderColor = ok ? "rgba(27, 29, 31, 0.12)" : "rgba(207, 63, 46, 0.6)";
  statusEl.style.color = ok ? "#1b1d1f" : "#cf3f2e";
}

function appendMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;
  bubble.textContent = text;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) {
    return "--:--";
  }
  const total = Math.max(0, Math.round(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

async function loadHistory() {
  const data = await apiFetch("/history");
  messagesEl.innerHTML = "";
  data.items.forEach(item => {
    appendMessage("user", item.user_input);
    appendMessage("assistant", item.response);
  });
}

async function loadConfig() {
  const data = await apiFetch("/config");
  modelInput.value = data.llm_model || "";
  baseUrlInput.value = data.openai_base_url || "";
  apiKeyInput.value = data.openai_api_key || "";
  docsDirInput.value = data.documents_dir || "";
}

async function loadDocuments() {
  const data = await apiFetch("/documents");
  if (data.count === 0) {
    docList.textContent = "未找到 .docx 文案文件";
    return;
  }
  docList.innerHTML = data.files.map(name => `<div>${name}</div>`).join("");
}

async function loadScheduler() {
  try {
    const data = await apiFetch("/scheduler");
    if (!data.active) {
      timerStatus.textContent = "未设置";
      timerRemaining.textContent = "--:--";
      timerMeta.textContent = "";
      timerFill.style.width = "0%";
      return;
    }

    timerStatus.textContent = "进行中";
    timerRemaining.textContent = formatDuration(data.remaining_seconds);
    if (data.deadline) {
      const deadline = data.deadline.replace("T", " ").split(".")[0];
      timerMeta.textContent = `截止时间 ${deadline}`;
    } else {
      timerMeta.textContent = "";
    }

    if (data.interval_minutes) {
      const total = data.interval_minutes * 60;
      const remaining = Math.max(0, data.remaining_seconds || 0);
      const percent = Math.min(100, Math.max(0, ((total - remaining) / total) * 100));
      timerFill.style.width = `${percent}%`;
    } else {
      timerFill.style.width = "0%";
    }
  } catch (err) {
    timerStatus.textContent = "未连接";
    timerRemaining.textContent = "--:--";
    timerMeta.textContent = "";
    timerFill.style.width = "0%";
  }
}

async function sendMessage() {
  const message = messageInput.value;
  if (!message.trim()) {
    return;
  }
  appendMessage("user", message);
  messageInput.value = "";
  messageInput.focus();
  setStatus("思考中...");
  const data = await apiFetch("/chat", {
    method: "POST",
    body: JSON.stringify({ message })
  });
  appendMessage("assistant", data.response || "");
  setStatus("已连接");
}

async function sendNudge() {
  setStatus("思考中...");
  const data = await apiFetch("/chat", {
    method: "POST",
    body: JSON.stringify({ message: "" })
  });
  appendMessage("assistant", data.response || "");
  setStatus("已连接");
}

async function saveConfig() {
  setStatus("正在保存配置...");
  await apiFetch("/config", {
    method: "POST",
    body: JSON.stringify({
      llm_model: modelInput.value.trim(),
      openai_base_url: baseUrlInput.value.trim(),
      openai_api_key: apiKeyInput.value.trim(),
      documents_dir: docsDirInput.value.trim()
    })
  });
  await loadDocuments();
  await loadScheduler();
  setStatus("配置已保存");
}

async function clearHistory() {
  await apiFetch("/history/clear", { method: "POST" });
  messagesEl.innerHTML = "";
  await loadHistory();
  await loadScheduler();
  setStatus("对话已清空");
}

async function pollEvents() {
  try {
    const data = await apiFetch("/events");
    if (Array.isArray(data.items)) {
      data.items.forEach(event => {
        appendMessage("assistant", event.message);
      });
    }
    await loadScheduler();
  } catch (err) {
    setStatus("未连接", false);
  }
}

sendBtn.addEventListener("click", sendMessage);
nudgeBtn.addEventListener("click", sendNudge);
messageInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

saveConfigBtn.addEventListener("click", saveConfig);
clearHistoryBtn.addEventListener("click", clearHistory);

pickDirBtn.addEventListener("click", async () => {
  const selected = await window.bossApi.selectDirectory();
  if (selected) {
    docsDirInput.value = selected;
  }
});

async function init() {
  try {
    await loadConfig();
    await loadHistory();
    await loadDocuments();
    await loadScheduler();
    setStatus("已连接");
  } catch (err) {
    setStatus("未连接", false);
  }
  setInterval(pollEvents, 3000);
}

init();
