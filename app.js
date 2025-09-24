const API_BASE = (location.origin.includes('127.0.0.1:5000') || location.origin.includes('localhost:5000')) ? '' : 'http://127.0.0.1:5000';
const askForm = document.getElementById("askForm");
const queryInput = document.getElementById("queryInput");
const askBtn = document.getElementById("askBtn");
const statusEl = document.getElementById("status");
const answerEl = document.getElementById("answer");
const sourcesEl = document.getElementById("sources");
const messagesEl = document.getElementById("messages");
const historyList = document.getElementById("historyList");
const clearHistoryBtn = document.getElementById("clearHistory");
const toasts = document.getElementById("toasts");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const themeToggle = document.getElementById("themeToggle");
const modelSelect = document.getElementById("modelSelect");

let convo = []; // {role, content}
let historyItems = JSON.parse(localStorage.getItem("history") || "[]"); // [{q,a,ts}]
let settings = JSON.parse(localStorage.getItem("settings") || "{}");
if (settings.model) modelSelect.value = settings.model;

function toast(msg) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  toasts.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function renderHistory() {
  historyList.innerHTML = "";
  historyItems.forEach((item, idx) => {
    const li = document.createElement("li");
    li.textContent = item.q.slice(0, 60);
    li.title = item.q;
    li.addEventListener("click", () => {
      answerEl.textContent = item.a;
      sourcesEl.innerHTML = (item.sources || []).map(renderSource).join("");
      queryInput.value = item.q;
    });
    historyList.appendChild(li);
  });
}

function renderSource(src) {
  const title = src.title || src.url || "Source";
  const domain = src.domain || "";
  const snippet = src.snippet || "";
  const url = src.url || "#";
  return `<div class="source"><div><strong>${title}</strong> ${domain ? `• ${domain}` : ""}</div><div>${snippet}</div><div><a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a></div></div>`;
}

function renderMessages() {
  messagesEl.innerHTML = convo
    .map(m => `<div class="msg ${m.role}">${m.role === 'user' ? '<strong>You:</strong> ' : '<strong>Assistant:</strong> '}${m.content}</div>`) 
    .join("");
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setSkeleton(on) {
  if (on) {
    answerEl.innerHTML = '<div class="msg assistant">Thinking…</div>';
  }
}

async function ask(query) {
  statusEl.textContent = "Thinking...";
  askBtn.disabled = true;
  setSkeleton(true);
  try {
    const resp = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, history: convo, model: modelSelect.value }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(err.error || err.details || resp.statusText);
    }
    const data = await resp.json();
    const answer = data.answer || "";
    const citations = data.citations || [];

    convo.push({ role: "assistant", content: answer });
    renderMessages();

    answerEl.textContent = answer;
    sourcesEl.innerHTML = citations.map(renderSource).join("");

    // Save to history
    historyItems.unshift({ q: query, a: answer, sources: citations, ts: Date.now() });
    historyItems = historyItems.slice(0, 50);
    localStorage.setItem("history", JSON.stringify(historyItems));
    renderHistory();
    toast('Answer ready');
  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
    toast(`Error: ${e.message}`);
  } finally {
    askBtn.disabled = false;
    setTimeout(() => (statusEl.textContent = ""), 2000);
  }
}

askForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = queryInput.value.trim();
  if (!q) return;
  convo.push({ role: "user", content: q });
  renderMessages();
  answerEl.textContent = "";
  sourcesEl.innerHTML = "";
  queryInput.value = "";
  ask(q);
});

clearHistoryBtn.addEventListener("click", () => {
  historyItems = [];
  localStorage.removeItem("history");
  renderHistory();
  toast('History cleared');
});

sidebarToggle?.addEventListener('click', () => {
  sidebar?.classList.toggle('open');
});

themeToggle?.addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme !== 'light';
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
});

modelSelect?.addEventListener('change', () => {
  settings.model = modelSelect.value;
  localStorage.setItem('settings', JSON.stringify(settings));
  toast(`Model: ${settings.model}`);
});

renderHistory();
renderMessages();
