/* ═══════════════════════════════════════════════════════════════════════
   MCP AI ASSISTANT — app.js
   WebSocket client, message rendering, tool animations, file uploads
   ═══════════════════════════════════════════════════════════════════════ */

// ── Config ────────────────────────────────────────────────────────────
const WS_PROTOCOL = location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_BASE     = `${WS_PROTOCOL}//${location.host}`;
const SESSION_ID  = crypto.randomUUID();

// ── Tool metadata ─────────────────────────────────────────────────────
const TOOLS = {
  web_search:  { label: 'Web Search',  icon: '🔍', color: '#06b6d4' },
  get_weather: { label: 'Weather',     icon: '🌤️', color: '#f59e0b' },
  get_news:    { label: 'News Feed',   icon: '📰', color: '#ec4899' },
  read_file:   { label: 'File Reader', icon: '📄', color: '#8b5cf6' },
  list_files:  { label: 'Files',       icon: '📂', color: '#8b5cf6' },
  db_query:    { label: 'Database',    icon: '🗄️', color: '#10b981' },
  run_code:    { label: 'Code Runner', icon: '⚙️', color: '#f97316' },
  none:        { label: 'Direct',      icon: '💬', color: '#475569' },
};

const QUICK_PROMPTS = [
  '🔍 What is the Model Context Protocol?',
  '🌤️ Weather in New York',
  '📰 Show me today\'s top news',
  '🗄️ Who are the top 3 highest paid employees?',
  '⚙️ Run: print("Hello from MCP!")',
  '📊 List all products sorted by price',
];

// ── DOM refs ──────────────────────────────────────────────────────────
const messagesEl    = document.getElementById('messages');
const msgInput      = document.getElementById('msg-input');
const sendBtn       = document.getElementById('send-btn');
const attachBtn     = document.getElementById('attach-btn');
const fileInput     = document.getElementById('file-input');
const thinkingBar   = document.getElementById('thinking-bar');
const thinkingText  = document.getElementById('thinking-text');
const connDot       = document.getElementById('conn-dot');
const connLabel     = document.getElementById('conn-label');
const headerAct     = document.getElementById('header-activity');
const toolsGrid     = document.getElementById('tools-grid');
const quickPrompts  = document.getElementById('quick-prompts');
const fileChips     = document.getElementById('file-chips');
const dropOverlay   = document.getElementById('drop-overlay');
const clearChatBtn  = document.getElementById('clear-chat-btn');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar       = document.getElementById('sidebar');
const statMsgs      = document.getElementById('stat-msgs');
const statTools     = document.getElementById('stat-tools');
const toastCont     = document.getElementById('toast-container');
const welcomeCard   = document.getElementById('welcome-card');

// ── State ─────────────────────────────────────────────────────────────
let ws            = null;
let isStreaming   = false;
let currentBubble = null;
let currentRaw    = '';
let msgCount      = 0;
let toolCallCount = 0;
let uploadedFiles = [];

// ── Configure marked.js ───────────────────────────────────────────────
marked.setOptions({
  gfm: true, breaks: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value; } catch {}
    }
    return hljs.highlightAuto(code).value;
  },
});

// ═══════════════════════════════════════════════════════════════════════
// WebSocket
// ═══════════════════════════════════════════════════════════════════════
function connectWS() {
  ws = new WebSocket(`${WS_BASE}/ws/${SESSION_ID}`);

  ws.onopen = () => {
    connDot.className = 'conn-dot connected';
    connLabel.textContent = 'Connected';
    headerAct.textContent = 'Ready to help';
    sendBtn.disabled = false;
    showToast('Connected to MCP Assistant', 'success');
  };

  ws.onclose = () => {
    connDot.className = 'conn-dot disconnected';
    connLabel.textContent = 'Disconnected';
    sendBtn.disabled = true;
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => {
    connDot.className = 'conn-dot disconnected';
    connLabel.textContent = 'Error — retrying…';
  };

  ws.onmessage = (e) => handleServerMsg(JSON.parse(e.data));
}

// ── Handle incoming server events ─────────────────────────────────────
function handleServerMsg(data) {
  switch (data.type) {

    case 'thinking':
      thinkingText.textContent = data.text || 'Thinking…';
      thinkingBar.style.display = 'flex';
      headerAct.textContent = data.text || 'Thinking…';
      break;

    case 'tool_use':
      activateTool(data.tool);
      thinkingText.textContent = `Using ${TOOLS[data.tool]?.label || data.tool}…`;
      headerAct.textContent = `🔧 ${TOOLS[data.tool]?.label || data.tool}`;
      toolCallCount++;
      statTools.textContent = toolCallCount;
      break;

    case 'stream_start':
      thinkingBar.style.display = 'none';
      headerAct.textContent = 'Generating response…';
      currentBubble = createAssistantBubble();
      currentRaw = '';
      isStreaming = true;
      break;

    case 'stream_token':
      if (currentBubble && data.content) {
        currentRaw += data.content;
        renderStreamingBubble(currentBubble, currentRaw);
      }
      break;

    case 'stream_end':
      isStreaming = false;
      if (currentBubble) {
        finaliseBubble(currentBubble, currentRaw, data.tools_used || []);
      }
      currentBubble = null;
      currentRaw = '';
      headerAct.textContent = 'Ready to help';
      deactivateAllTools();
      // Sync stats from server
      if (data.stats) {
        statMsgs.textContent  = data.stats.message_count  ?? msgCount;
        statTools.textContent = data.stats.tool_call_count ?? toolCallCount;
        toolCallCount = data.stats.tool_call_count ?? toolCallCount;
      }
      setInputBusy(false);
      break;

    case 'error':
      thinkingBar.style.display = 'none';
      isStreaming = false;
      setInputBusy(false);
      showToast(`Error: ${data.message}`, 'error');
      appendErrorMsg(data.message);
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════
// Sending messages
// ═══════════════════════════════════════════════════════════════════════
function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || isStreaming || !ws || ws.readyState !== WebSocket.OPEN) return;

  hideWelcome();
  appendUserMsg(text);
  msgCount++;
  statMsgs.textContent = msgCount;

  ws.send(JSON.stringify({ message: text }));
  msgInput.value = '';
  autoResizeTextarea();
  setInputBusy(true);
}

function setInputBusy(busy) {
  isStreaming = busy;
  sendBtn.disabled = busy;
  msgInput.disabled = busy;
  if (!busy) msgInput.focus();
}

// ═══════════════════════════════════════════════════════════════════════
// Message rendering
// ═══════════════════════════════════════════════════════════════════════
function appendUserMsg(text) {
  const wrap = document.createElement('div');
  wrap.className = 'msg-wrap user';
  wrap.innerHTML = `
    <div class="msg-avatar" aria-label="You">🧑</div>
    <div class="msg-body">
      <div class="msg-bubble">${escapeHtml(text)}</div>
    </div>`;
  messagesEl.appendChild(wrap);
  scrollBottom();
}

function createAssistantBubble() {
  const wrap = document.createElement('div');
  wrap.className = 'msg-wrap assistant';
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = '<span class="stream-cursor"></span>';
  wrap.innerHTML = `<div class="msg-avatar" aria-label="AI Assistant">🤖</div>`;
  const body = document.createElement('div');
  body.className = 'msg-body';
  body.appendChild(bubble);
  wrap.appendChild(body);
  messagesEl.appendChild(wrap);
  scrollBottom();
  return { wrap, bubble, body };
}

function renderStreamingBubble({ bubble }, raw) {
  bubble.innerHTML = marked.parse(raw) + '<span class="stream-cursor"></span>';
  hljs.highlightAll();
  scrollBottom();
}

function finaliseBubble({ bubble, body }, raw, toolsUsed) {
  bubble.innerHTML = marked.parse(raw);
  hljs.highlightAll();

  if (toolsUsed.length > 0) {
    const toolRow = document.createElement('div');
    toolRow.className = 'msg-tools';
    toolsUsed.forEach(t => {
      const meta = TOOLS[t] || { icon: '🔧', label: t, color: '#6366f1' };
      const badge = document.createElement('span');
      badge.className = 'tool-badge';
      badge.style.cssText = `
        --tc-bg: ${meta.color}22;
        --tc-border: ${meta.color}44;
        --tc-color: ${meta.color};
      `;
      badge.textContent = `${meta.icon} ${meta.label}`;
      toolRow.appendChild(badge);
    });
    body.appendChild(toolRow);
  }
  scrollBottom();
}

function appendErrorMsg(msg) {
  const wrap = document.createElement('div');
  wrap.className = 'msg-wrap assistant';
  wrap.innerHTML = `
    <div class="msg-avatar">⚠️</div>
    <div class="msg-body">
      <div class="msg-bubble" style="border-color:rgba(239,68,68,.3);background:rgba(239,68,68,.06);">
        <strong style="color:#ef4444;">Error</strong><br>${escapeHtml(msg)}
      </div>
    </div>`;
  messagesEl.appendChild(wrap);
  scrollBottom();
}

// ═══════════════════════════════════════════════════════════════════════
// Tools sidebar
// ═══════════════════════════════════════════════════════════════════════
function buildToolCards() {
  const entries = Object.entries(TOOLS).filter(([k]) => k !== 'none');
  toolsGrid.innerHTML = entries.map(([key, t]) => `
    <div class="tool-card" id="tc-${key}" style="--tc:${t.color}">
      <span class="tool-icon">${t.icon}</span>
      <span class="tool-name">${t.label}</span>
      <span class="tool-status">idle</span>
    </div>`).join('');
}

function activateTool(toolKey) {
  deactivateAllTools();
  const card = document.getElementById(`tc-${toolKey}`);
  if (card) {
    card.classList.add('active');
    card.querySelector('.tool-status').textContent = 'running';
  }
}

function deactivateAllTools() {
  document.querySelectorAll('.tool-card').forEach(c => {
    c.classList.remove('active');
    c.querySelector('.tool-status').textContent = 'idle';
  });
}

// ═══════════════════════════════════════════════════════════════════════
// Quick prompts
// ═══════════════════════════════════════════════════════════════════════
function buildQuickPrompts() {
  quickPrompts.innerHTML = QUICK_PROMPTS.map(p => `
    <button class="qp-chip" data-prompt="${escapeAttr(p)}">${p}</button>`
  ).join('');

  quickPrompts.addEventListener('click', e => {
    const chip = e.target.closest('.qp-chip');
    if (!chip) return;
    const prompt = chip.dataset.prompt;
    if (isStreaming) return;
    msgInput.value = prompt;
    autoResizeTextarea();
    sendMessage();
  });
}

// ── Cap chips in welcome card ─────────────────────────────────────────
document.querySelectorAll('.cap-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const map = {
      web_search:  '🔍 Search the web for the latest AI news',
      get_weather: '🌤️ What\'s the weather in London?',
      read_file:   '📂 List my uploaded files',
      db_query:    '🗄️ Show me all employees in Engineering',
      run_code:    '⚙️ Write Python code to calculate fibonacci(10)',
      get_news:    '📰 Show me today\'s top news headlines',
    };
    const tool = chip.dataset.tool;
    if (map[tool]) { msgInput.value = map[tool]; autoResizeTextarea(); msgInput.focus(); }
  });
});

// ═══════════════════════════════════════════════════════════════════════
// File Upload
// ═══════════════════════════════════════════════════════════════════════
async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.status === 'success') {
      uploadedFiles.push(data.filename);
      addFileChip(data.filename);
      showToast(`📎 ${data.filename} uploaded`, 'success');
    }
  } catch {
    showToast('Upload failed', 'error');
  }
}

function addFileChip(name) {
  const chip = document.createElement('div');
  chip.className = 'file-chip';
  chip.innerHTML = `📎 ${escapeHtml(name)} <button title="Remove" onclick="this.parentElement.remove()">×</button>`;
  fileChips.appendChild(chip);
}

attachBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => {
  [...e.target.files].forEach(uploadFile);
  fileInput.value = '';
});

// Drag-and-drop
const dropZone = document.querySelector('.input-zone');
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropOverlay.classList.add('active'); });
dropZone.addEventListener('dragleave', e => { if (!dropZone.contains(e.relatedTarget)) dropOverlay.classList.remove('active'); });
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropOverlay.classList.remove('active');
  [...e.dataTransfer.files].forEach(uploadFile);
});

// ═══════════════════════════════════════════════════════════════════════
// Input handling
// ═══════════════════════════════════════════════════════════════════════
msgInput.addEventListener('input', () => {
  autoResizeTextarea();
  sendBtn.disabled = !msgInput.value.trim() || isStreaming;
});

msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

sendBtn.addEventListener('click', sendMessage);

function autoResizeTextarea() {
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 180) + 'px';
}

// ═══════════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════════
function scrollBottom() {
  requestAnimationFrame(() => {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

function hideWelcome() {
  if (welcomeCard) {
    welcomeCard.style.opacity = '0';
    welcomeCard.style.transform = 'scale(.96)';
    welcomeCard.style.transition = 'all .3s ease';
    setTimeout(() => welcomeCard.remove(), 300);
  }
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}
function escapeAttr(str) { return str.replace(/"/g, '&quot;'); }

function showToast(msg, type = 'info', duration = 3500) {
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = `${icons[type] || ''} ${msg}`;
  toastCont.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(20px)'; toast.style.transition = 'all .3s'; setTimeout(() => toast.remove(), 300); }, duration);
}

// Clear chat
clearChatBtn.addEventListener('click', () => {
  messagesEl.innerHTML = '';
  msgCount = 0; toolCallCount = 0;
  statMsgs.textContent = '0'; statTools.textContent = '0';
  showToast('Conversation cleared', 'info');
  // Re-insert welcome
  const wc = document.createElement('div');
  wc.id = 'welcome-card';
  wc.className = 'welcome-card';
  wc.innerHTML = `<div class="welcome-glow"></div>
    <div class="welcome-icon"><svg width="48" height="48" viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="23" stroke="url(#wlg2)" stroke-width="2"/><circle cx="24" cy="24" r="5" fill="url(#wlg2)"/><defs><linearGradient id="wlg2" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse"><stop stop-color="#6366f1"/><stop offset="1" stop-color="#a78bfa"/></linearGradient></defs></svg></div>
    <h2 class="welcome-title">Chat cleared! Ready to help again.</h2>
    <p class="welcome-subtitle">Ask me anything — I can search the web, query databases, run code, and more.</p>`;
  messagesEl.appendChild(wc);
});

// Sidebar toggle (mobile)
sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('open'));

// ═══════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════
buildToolCards();
buildQuickPrompts();
connectWS();
msgInput.focus();
