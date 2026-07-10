/* ═══════════════════════════════════════════════════════════════════════
   NEXUS AI — app.js (Minimalist Conversational UI)
   ═══════════════════════════════════════════════════════════════════════ */

const WS_PROTOCOL = location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_BASE     = `${WS_PROTOCOL}//${location.host}`;

const SUGGESTIONS = [
  'What is the Model Context Protocol?',
  'Who are the top 3 highest paid employees in the company database?',
  'Show me today\'s top news headlines',
  'Write a Python script to calculate fibonacci(10)'
];

// ── DOM Nodes ────────────────────────────────────────────────────────
const messageScroller    = document.getElementById('message-scroller');
const queryTextInput      = document.getElementById('query-text-input');
const submitQueryBtn     = document.getElementById('submit-query-btn');
const attachDocumentBtn  = document.getElementById('attach-document-btn');
const hiddenFileInput     = document.getElementById('hidden-file-input');
const agentActiveStatus  = document.getElementById('agent-active-status');
const agentStatusText    = document.getElementById('agent-status-text');
const toastWrapper       = document.getElementById('toast-wrapper');
const welcomeHeroPanel   = document.getElementById('welcome-hero-panel');
const dragOverlayPanel   = document.getElementById('drag-overlay-panel');
const activeUploadChips  = document.getElementById('active-upload-chips');
const sessionListCont    = document.getElementById('session-list-container');
const activeSessionTitle = document.getElementById('active-session-title');
const systemStatusBadge  = document.getElementById('system-status-indicator');

const sidebar            = document.getElementById('sidebar');
const closeSidebarBtn    = document.getElementById('close-sidebar-btn');
const openSidebarBtn     = document.getElementById('open-sidebar-btn');

const newChatBtn         = document.getElementById('new-chat-btn');

// ── State ────────────────────────────────────────────────────────────
let currentSessionId = crypto.randomUUID();
let ws = null;
let currentBubble = null;
let currentRawText = "";
let isBusy = false;

// Configure Markdown Parser
marked.setOptions({
  gfm: true, breaks: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value; } catch {}
    }
    return hljs.highlightAuto(code).value;
  }
});

// ═══════════════════════════════════════════════════════════════════════
// WebSocket lifecycle
// ═══════════════════════════════════════════════════════════════════════
function initWebSocket(sessionId) {
  if (ws) {
    ws.close();
  }
  ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`);

  ws.onopen = () => {
    updateSystemStatus('connected', 'Idle');
    submitQueryBtn.disabled = !queryTextInput.value.trim() || isBusy;
  };

  ws.onclose = () => {
    updateSystemStatus('disconnected', 'Connecting...');
    submitQueryBtn.disabled = true;
    setTimeout(() => initWebSocket(sessionId), 3000);
  };

  ws.onerror = () => {
    updateSystemStatus('disconnected', 'Network Error');
  };

  ws.onmessage = (event) => handleMessageEvent(JSON.parse(event.data));
}

function updateSystemStatus(state, text) {
  const dot = systemStatusBadge.querySelector('.status-dot');
  dot.className = `status-dot ${state === 'connected' ? 'green' : 'red'}`;
  systemStatusBadge.querySelector('.status-text').textContent = text;
}

function handleMessageEvent(payload) {
  switch (payload.type) {
    case 'thinking':
      agentStatusText.textContent = payload.text;
      agentActiveStatus.style.display = 'flex';
      break;

    case 'tool_use':
      agentStatusText.textContent = `Nexus triggered: ${payload.tool}...`;
      break;

    case 'stream_start':
      agentActiveStatus.style.display = 'none';
      currentBubble = createMessageBubble('assistant');
      currentRawText = "";
      isBusy = true;
      break;

    case 'stream_token':
      if (currentBubble && payload.content) {
        currentRawText += payload.content;
        currentBubble.bubble.innerHTML = marked.parse(currentRawText) + '<span class="stream-cursor"></span>';
        hljs.highlightAll();
        scrollArena();
      }
      break;

    case 'stream_end':
      isBusy = false;
      if (currentBubble) {
        currentBubble.bubble.innerHTML = marked.parse(currentRawText);
        hljs.highlightAll();
        
        // Render simple citation / activity chips below response
        const traceContainer = document.createElement('div');
        traceContainer.className = 'trace-row';

        if (payload.rag_triggered) {
          const chip = document.createElement('span');
          chip.className = 'trace-chip rag';
          chip.innerHTML = `🧬 Qdrant Match`;
          traceContainer.appendChild(chip);
        }

        payload.tools_used.forEach(tool => {
          const chip = document.createElement('span');
          chip.className = 'trace-chip mcp';
          chip.innerHTML = `🔧 ${tool}`;
          traceContainer.appendChild(chip);
        });

        if (traceContainer.children.length > 0) {
          currentBubble.body.appendChild(traceContainer);
        }

        const metaFooter = document.createElement('div');
        metaFooter.className = 'meta-footer';
        metaFooter.innerHTML = `<span>Latency: ${payload.response_time_ms}ms</span>`;
        currentBubble.body.appendChild(metaFooter);
      }
      
      currentBubble = null;
      currentRawText = "";
      setInputState(false);
      loadSessions(); 
      break;

    case 'error':
      agentActiveStatus.style.display = 'none';
      isBusy = false;
      setInputState(false);
      showToast(`Error: ${payload.message}`, 'error');
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════
// Chat Session Actions
// ═══════════════════════════════════════════════════════════════════════
async function loadSessions() {
  try {
    const res = await fetch('/sessions');
    const data = await res.json();
    sessionListCont.innerHTML = "";
    data.sessions.forEach(sess => {
      const item = document.createElement('div');
      item.className = `session-item ${sess.id === currentSessionId ? 'active' : ''}`;
      item.innerHTML = `
        <span class="session-title-text">${escapeHtml(sess.title)}</span>
        <button class="btn-delete-session" title="Delete session">×</button>
      `;
      item.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-delete-session')) {
          e.stopPropagation();
          deleteSession(sess.id);
        } else {
          switchSession(sess.id, sess.title);
        }
      });
      sessionListCont.appendChild(item);
    });
  } catch (e) {
    console.error("Failed to load historical sessions:", e);
  }
}

async function deleteSession(id) {
  await fetch(`/sessions/${id}`, { method: 'DELETE' });
  if (id === currentSessionId) {
    startNewSession();
  } else {
    loadSessions();
  }
}

function switchSession(id, title) {
  currentSessionId = id;
  activeSessionTitle.textContent = title;
  initWebSocket(id);
  loadSessions();
  restoreMessages(id);
}

async function restoreMessages(id) {
  const res = await fetch(`/sessions/${id}/messages`);
  const data = await res.json();
  clearScroller();
  
  if (data.messages.length === 0) {
    showWelcomeHero();
    return;
  }
  
  hideWelcomeHero();
  data.messages.forEach(msg => {
    const isUser = msg.role === 'user';
    const b = createMessageBubble(msg.role);
    if (isUser) {
      b.bubble.textContent = msg.content;
    } else {
      b.bubble.innerHTML = marked.parse(msg.content);
      
      const traceContainer = document.createElement('div');
      traceContainer.className = 'trace-row';
      msg.tools_used.forEach(tool => {
        const chip = document.createElement('span');
        chip.className = 'trace-chip mcp';
        chip.innerHTML = `🔧 ${tool}`;
        traceContainer.appendChild(chip);
      });
      if (traceContainer.children.length > 0) {
        b.body.appendChild(traceContainer);
      }
    }
  });
  hljs.highlightAll();
  scrollArena();
}

function startNewSession() {
  currentSessionId = crypto.randomUUID();
  activeSessionTitle.textContent = "New Chat";
  initWebSocket(currentSessionId);
  clearScroller();
  showWelcomeHero();
  loadSessions();
}

// ═══════════════════════════════════════════════════════════════════════
// File Upload Ingestion
// ═══════════════════════════════════════════════════════════════════════
async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  
  const progressChip = document.createElement('div');
  progressChip.className = 'upload-chip';
  progressChip.innerHTML = `🧬 Indexing: ${escapeHtml(file.name)}...`;
  activeUploadChips.appendChild(progressChip);

  try {
    const res = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    progressChip.remove();
    
    if (data.status === 'success') {
      showToast(`${file.name} indexed successfully!`, 'success');
      const systemBox = createMessageBubble('assistant');
      systemBox.bubble.innerHTML = `<span style="color:#60a5fa">🧬 **Document Ingestion**</span><br>${data.rag_status}`;
    }
  } catch (e) {
    progressChip.remove();
    showToast(`Upload failed for ${file.name}`, 'error');
  }
}

// ═══════════════════════════════════════════════════════════════════════
// Layout Utility Controls
// ═══════════════════════════════════════════════════════════════════════
function createMessageBubble(role) {
  const wrap = document.createElement('div');
  wrap.className = `message-wrap ${role}`;
  
  const icon = role === 'user' ? '🧑' : '🤖';
  const avatar = document.createElement('div');
  avatar.className = 'avatar-icon';
  avatar.textContent = icon;
  
  const body = document.createElement('div');
  body.className = 'message-body';
  
  const bubble = document.createElement('div');
  bubble.className = 'bubble-card';
  
  body.appendChild(bubble);
  wrap.appendChild(avatar);
  wrap.appendChild(body);
  
  messageScroller.appendChild(wrap);
  scrollArena();
  return { bubble, body };
}

function submitQuery() {
  const text = queryTextInput.value.trim();
  if (!text || isBusy || !ws || ws.readyState !== WebSocket.OPEN) return;
  
  hideWelcomeHero();
  const userBubble = createMessageBubble('user');
  userBubble.bubble.textContent = text;
  
  ws.send(JSON.stringify({ message: text }));
  queryTextInput.value = "";
  autoSizeTextarea();
  setInputState(true);
}

function setInputState(busy) {
  isBusy = busy;
  queryTextInput.disabled = busy;
  submitQueryBtn.disabled = busy || !queryTextInput.value.trim();
  if (!busy) queryTextInput.focus();
}

function scrollArena() {
  requestAnimationFrame(() => {
    messageScroller.scrollTop = messageScroller.scrollHeight;
  });
}

function clearScroller() {
  messageScroller.innerHTML = "";
}

function showWelcomeHero() {
  messageScroller.appendChild(welcomeHeroPanel);
  welcomeHeroPanel.style.display = 'flex';
}

function hideWelcomeHero() {
  welcomeHeroPanel.style.display = 'none';
}

function autoSizeTextarea() {
  queryTextInput.style.height = 'auto';
  queryTextInput.style.height = Math.min(queryTextInput.scrollHeight, 160) + 'px';
}

function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  toastWrapper.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 400);
  }, 4000);
}

function buildSuggestions() {
  const container = document.getElementById('suggestion-pills-container');
  container.innerHTML = SUGGESTIONS.map(s => `
    <button class="suggest-pill">${s}</button>
  `).join('');
  
  container.addEventListener('click', (e) => {
    if (e.target.classList.contains('suggest-pill')) {
      queryTextInput.value = e.target.textContent;
      autoSizeTextarea();
      submitQuery();
    }
  });
}

// ── Event bindings ────────────────────────────────────────────────────
newChatBtn.addEventListener('click', startNewSession);
attachDocumentBtn.addEventListener('click', () => hiddenFileInput.click());
hiddenFileInput.addEventListener('change', (e) => {
  [...e.target.files].forEach(uploadFile);
  hiddenFileInput.value = "";
});

queryTextInput.addEventListener('input', () => {
  autoSizeTextarea();
  submitQueryBtn.disabled = !queryTextInput.value.trim() || isBusy;
});
queryTextInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submitQuery();
  }
});
submitQueryBtn.addEventListener('click', submitQuery);

// Sidebar Drawers
closeSidebarBtn.addEventListener('click', () => sidebar.classList.add('collapsed'));
openSidebarBtn.addEventListener('click', () => sidebar.classList.remove('collapsed'));

// Drag & drop bindings
const mainArea = document.querySelector('.app');
mainArea.addEventListener('dragover', (e) => { e.preventDefault(); dragOverlayPanel.classList.add('active'); });
mainArea.addEventListener('dragleave', (e) => { if (!mainArea.contains(e.relatedTarget)) dragOverlayPanel.classList.remove('active'); });
mainArea.addEventListener('drop', (e) => {
  e.preventDefault();
  dragOverlayPanel.classList.remove('active');
  [...e.dataTransfer.files].forEach(uploadFile);
});

// JSON and string helpers
function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Initialization
buildSuggestions();
startNewSession();
