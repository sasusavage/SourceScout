const API_BASE = location.protocol === 'file:' ? 'http://127.0.0.1:5000' : '';
const askForm = document.getElementById("askForm");
const queryInput = document.getElementById("queryInput");
const askBtn = document.getElementById("askBtn");
const statusEl = document.getElementById("status");
const messagesEl = document.getElementById("messages");
const historyList = document.getElementById("historyList");
const clearHistoryBtn = document.getElementById("clearHistory");
const toasts = document.getElementById("toasts");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const themeToggle = document.getElementById("themeToggle");
const modelSelect = document.getElementById("modelSelect");
const personaSelect = document.getElementById("personaSelect");

let convo = []; // {role, content, sources?, pending?}
let historyItems = JSON.parse(localStorage.getItem("history") || "[]"); // [{q,a,ts}]
let settings;
try {
  settings = JSON.parse(localStorage.getItem("settings") || "{}") || {};
} catch (err) {
  settings = {};
}
if (typeof settings !== "object" || settings === null) settings = {};

const availableModels = Array.from(modelSelect.options).map((opt) => opt.value);
if (settings.model && availableModels.includes(settings.model)) {
  modelSelect.value = settings.model;
} else if (settings.model && !availableModels.includes(settings.model)) {
  delete settings.model;
  localStorage.setItem("settings", JSON.stringify(settings));
}

const availablePersonas = Array.from(personaSelect.options).map((opt) => opt.value);
if (settings.personality && availablePersonas.includes(settings.personality)) {
  personaSelect.value = settings.personality;
} else {
  personaSelect.value = availablePersonas[0];
  if (settings.personality && !availablePersonas.includes(settings.personality)) {
    delete settings.personality;
    localStorage.setItem("settings", JSON.stringify(settings));
  }
}

function toast(msg) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  toasts.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function applyTheme(theme, { announce = false } = {}) {
  const next = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  if (themeToggle) {
    const label = next === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    const icon = next === 'dark' ? '🌞' : '🌙';
    themeToggle.textContent = icon;
    themeToggle.setAttribute('aria-label', label);
    themeToggle.setAttribute('title', label);
  }
  settings.theme = next;
  localStorage.setItem('settings', JSON.stringify(settings));
  if (announce) {
    toast(`Theme: ${next === 'dark' ? 'Dark' : 'Light'}`);
  }
}

const prefersDark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)').matches : false;
const initialTheme = settings.theme || (prefersDark ? 'dark' : 'light');
applyTheme(initialTheme);

function renderHistory() {
  historyList.innerHTML = "";
  historyItems.forEach((item, idx) => {
    const li = document.createElement("li");
    const personaLabel = item.personality === "fluent" ? "🗣️" : "🎤";
    li.textContent = `${personaLabel} ${item.q.slice(0, 56)}`;
    li.title = item.q;
    li.addEventListener("click", () => {
      convo = [
        { role: "user", content: item.q },
        { role: "assistant", content: item.a, sources: item.sources || [] },
      ];
      renderMessages();
      queryInput.value = item.q;
      if (item.personality && availablePersonas.includes(item.personality)) {
        personaSelect.value = item.personality;
        settings.personality = item.personality;
        localStorage.setItem("settings", JSON.stringify(settings));
      }
    });
    historyList.appendChild(li);
  });
}

function escapeHtml(str = "") {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatContent(text = "") {
  if (!text.trim()) return "";
  const paragraphs = escapeHtml(text).split(/\n{2,}/);
  return paragraphs
    .map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`)
    .join("");
}

function renderSource(src = {}) {
  let title = src.title || src.name || src.url || "Source";
  const domain = escapeHtml(src.domain || "");
  if (/^source\s+#?\d+/i.test(title) && domain) {
    title = domain;
  }
  title = escapeHtml(title);
  const snippet = escapeHtml(src.snippet || "");
  const url = escapeHtml(src.url || "#");
  return `<div class="source"><div class="source-title"><strong>${title}</strong>${domain ? ` • ${domain}` : ""}</div>${snippet ? `<div class="source-snippet">${snippet}</div>` : ""}<div><a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a></div></div>`;
}

function renderMessages() {
  if (!convo.length) {
    messagesEl.innerHTML = `<div class="empty-state">Start by asking a question to see a sourced answer.</div>`;
    return;
  }

  messagesEl.innerHTML = convo
    .map(m => {
      const label = m.role === 'user' ? 'You' : 'Assistant';
      const body = m.pending
        ? `<div class="message-body thinking">${escapeHtml(m.content || 'Thinking…')}</div>`
        : `<div class="message-body">${formatContent(m.content || '')}</div>`;
      const sourcesHtml = !m.pending && m.role === 'assistant' && m.sources?.length
        ? `<div class="sources">${m.sources.map(renderSource).join("")}</div>`
        : "";
      return `<div class="msg ${m.role}${m.pending ? ' pending' : ''}"><div class="msg-label">${label}</div>${body}${sourcesHtml}</div>`;
    })
    .join("");

  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showThinking() {
  convo.push({ role: "assistant", content: "Thinking…", pending: true });
  renderMessages();
}

async function ask(query) {
  statusEl.textContent = "Thinking...";
  askBtn.disabled = true;
  showThinking();
  try {
    const conversation = convo
      .filter(msg => !msg.pending)
      .map(({ role, content }) => ({ role, content }));

    const historyPayload =
      conversation.length && conversation[conversation.length - 1].role === 'user'
        ? conversation.slice(0, -1)
        : conversation;

    const resp = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        history: historyPayload,
        model: modelSelect.value,
        personality: personaSelect.value,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(err.error || err.details || resp.statusText);
    }
    const data = await resp.json();
    const answer = data.answer || "";
    const citations = data.citations || [];

    if (convo.length && convo[convo.length - 1].pending) {
      convo.pop();
    }

    convo.push({ role: "assistant", content: answer, sources: citations });
    renderMessages();

    // Save to history
    historyItems.unshift({
      q: query,
      a: answer,
      sources: citations,
      personality: data.personality || personaSelect.value,
      ts: Date.now(),
    });
    historyItems = historyItems.slice(0, 50);
    localStorage.setItem("history", JSON.stringify(historyItems));
    renderHistory();
    toast('Answer ready');
  } catch (e) {
    if (convo.length && convo[convo.length - 1].pending) {
      convo.pop();
      renderMessages();
    }
    statusEl.textContent = `Error: ${e.message}`;
    toast(`Error: ${e.message}`);
  } finally {
    if (convo.length && convo[convo.length - 1].pending) {
      convo.pop();
      renderMessages();
    }
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
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next, { announce: true });
});

modelSelect?.addEventListener('change', () => {
  settings.model = modelSelect.value;
  localStorage.setItem('settings', JSON.stringify(settings));
  toast(`Model: ${settings.model}`);
});

personaSelect?.addEventListener('change', () => {
  settings.personality = personaSelect.value;
  localStorage.setItem('settings', JSON.stringify(settings));
  const label = personaSelect.value === 'fluent' ? 'Fluent English' : 'Pidgin Vibes';
  toast(`Personality: ${label}`);
});

renderHistory();
renderMessages();
