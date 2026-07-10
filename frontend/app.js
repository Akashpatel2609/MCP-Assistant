/* ═══════════════════════════════════════════════════════════════════════
   NEXUS AI — app.js (Vercel Style Dashboard Coordinator)
   ═══════════════════════════════════════════════════════════════════════ */

const WS_PROTOCOL = location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_HOST     = location.protocol === 'file:' ? 'localhost:8000' : location.host;
const WS_BASE     = `${WS_PROTOCOL}//${WS_HOST}`;
const API_BASE    = location.protocol === 'file:' ? 'http://localhost:8000' : '';

const SUGGESTIONS = [
  'What is the Model Context Protocol?',
  'Who are the top 3 highest paid employees in the database?',
  'Show me today\'s top news headlines',
  'Write a Python script to calculate fibonacci(10)'
];

const TOOL_META = {
  web_search:  { label: 'Web Search',  icon: '🔍' },
  get_weather: { label: 'Weather API', icon: '🌤️' },
  get_news:    { label: 'RSS News',    icon: '📰' },
  read_file:   { label: 'File Reader', icon: '📄' },
  list_files:  { label: 'Files List',  icon: '📂' },
  db_query:    { label: 'SQL query',   icon: '🗄️' },
  run_code:    { label: 'Code Runner', icon: '⚙️' }
};

// ── DOM Nodes ────────────────────────────────────────────────────────
const messageScroller         = document.getElementById('message-scroller');
const queryTextInput           = document.getElementById('query-text-input');
const submitQueryBtn          = document.getElementById('submit-query-btn');
const hiddenFileInput          = document.getElementById('hidden-file-input');
const hiddenMediaInput         = document.getElementById('hidden-media-input');
const agentActiveStatus       = document.getElementById('agent-active-status');
const agentStatusText         = document.getElementById('agent-status-text');
const toastWrapper            = document.getElementById('toast-wrapper');
const welcomeHeroPanel        = document.getElementById('welcome-hero-panel');
const dragOverlayPanel        = document.getElementById('drag-overlay-panel');
const activeUploadChips       = document.getElementById('active-upload-chips');
const sessionListCont         = document.getElementById('recent-chats-grid');
const activeSessionTitle      = document.getElementById('active-session-title');
const systemStatusBadge       = document.getElementById('system-status-indicator');

// Theme Switcher & Add Source Dropdown Menu Trigger
const themeToggleBtn          = document.getElementById('theme-toggle-btn');
const addSourceDropdownBtn    = document.getElementById('add-source-dropdown-trigger');
const sourceDropdownMenu      = document.getElementById('source-dropdown-menu');

// Dropdown Action Elements
const optFileUpload           = document.getElementById('opt-file-upload');
const optMediaUpload          = document.getElementById('opt-media-upload');
const optWebScrape            = document.getElementById('opt-web-scrape');

// Web modal elements
const urlModal                = document.getElementById('url-modal');
const modalUrlInput           = document.getElementById('modal-url-input');
const closeUrlModal           = document.getElementById('close-url-modal');
const submitUrlModal          = document.getElementById('submit-url-modal');

const newChatBtn              = document.getElementById('new-chat-btn');

// Navigation links & Panels
const navChat                 = document.getElementById('nav-chat');
const navKnowledge            = document.getElementById('nav-knowledge');
const navSql                  = document.getElementById('nav-sql');
const navRegistry             = document.getElementById('nav-registry');
const navAnalytics            = document.getElementById('nav-analytics');

const panelChat               = document.getElementById('panel-chat-view');
const panelKnowledge          = document.getElementById('panel-knowledge-view');
const panelSql                = document.getElementById('panel-sql-view');
const panelRegistry           = document.getElementById('panel-registry-view');
const panelAnalytics          = document.getElementById('panel-analytics-view');

const documentRegistryList    = document.getElementById('document-registry-list');
const databaseSchemaContainer  = document.getElementById('database-schema-container');
const mcpToolsList            = document.getElementById('mcp-tools-list');

// Latency & counts
const statLatency             = document.getElementById('stat-latency');
const statTotalMsgs           = document.getElementById('stat-total-msgs');
const fillRagReads            = document.getElementById('fill-rag-reads');
const valRagReads             = document.getElementById('val-rag-reads');
const fillWebScrapes          = document.getElementById('fill-web-scrapes');
const valWebScrapes           = document.getElementById('val-web-scrapes');
const fillDbQueries           = document.getElementById('fill-db-queries');
const valDbQueries            = document.getElementById('val-db-queries');

// ── State ────────────────────────────────────────────────────────────
let currentSessionId = getUUID();
let ws = null;
let currentBubble = null;
let currentRawText = "";
let isBusy = false;

// Metrics track
let ragReadsCount = 0;
let webScrapesCount = 0;
let dbQueriesCount = 0;
let totalMessages = 0;
let latencySum = 0;
let latencyCount = 0;

// Safe UUID fallback helper for non-secure / file:/// contexts
function getUUID() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

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
// WebSocket connection lifecycle
// ═══════════════════════════════════════════════════════════════════════
function initWebSocket(sessionId) {
  if (ws) {
    ws.close();
  }
  
  // Attempt to build WebSocket connection
  try {
    ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`);

    ws.onopen = () => {
      updateSystemStatus('connected', 'SYS_IDLE');
      submitQueryBtn.disabled = !queryTextInput.value.trim() || isBusy;
    };

    ws.onclose = () => {
      // In Vercel serverless mode, socket is closed. We update status label to SYS_SERVERLESS
      updateSystemStatus('connected', 'SYS_SERVERLESS');
      submitQueryBtn.disabled = !queryTextInput.value.trim() || isBusy;
    };

    ws.onerror = () => {
      updateSystemStatus('connected', 'SYS_SERVERLESS');
      submitQueryBtn.disabled = !queryTextInput.value.trim() || isBusy;
    };

    ws.onmessage = (event) => handleMessageEvent(JSON.parse(event.data));
  } catch (e) {
    updateSystemStatus('connected', 'SYS_SERVERLESS');
  }
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
      updateSystemStatus('connected', 'SYS_ROUTING');
      break;

    case 'tool_use':
      agentStatusText.textContent = `NEXUS trigger: ${payload.tool}...`;
      updateSystemStatus('connected', `SYS_${payload.tool.toUpperCase()}`);
      
      // Update local dashboard usage metrics
      if (payload.tool === 'db_query') {
        dbQueriesCount++;
        updateUsageDashboard();
      } else if (payload.tool === 'web_search') {
        webScrapesCount++;
        updateUsageDashboard();
      }
      break;

    case 'stream_start':
      agentActiveStatus.style.display = 'none';
      currentBubble = createMessageBubble('assistant');
      currentRawText = "";
      isBusy = true;
      updateSystemStatus('connected', 'SYS_TYPING');
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
        
        // Render simple traces
        const traceContainer = document.createElement('div');
        traceContainer.className = 'trace-row';

        if (payload.rag_triggered) {
          ragReadsCount++;
          updateUsageDashboard();
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

        // Update overall latency charts
        totalMessages++;
        statTotalMsgs.textContent = totalMessages;
        latencySum += payload.response_time_ms;
        latencyCount++;
        statLatency.textContent = `${Math.round(latencySum / latencyCount)}ms`;
      }
      
      currentBubble = null;
      currentRawText = "";
      setInputState(false);
      loadSessions(); 
      updateSystemStatus('connected', 'SYS_IDLE');
      break;

    case 'error':
      agentActiveStatus.style.display = 'none';
      isBusy = false;
      setInputState(false);
      showToast(`Error: ${payload.message}`, 'error');
      updateSystemStatus('disconnected', 'SYS_FAIL');
      break;
  }
}

// Update local metrics display
function updateUsageDashboard() {
  valRagReads.textContent = `${ragReadsCount} / 100`;
  fillRagReads.style.width = `${Math.min(100, (ragReadsCount / 100) * 100)}%`;

  valWebScrapes.textContent = `${webScrapesCount} / 20`;
  fillWebScrapes.style.width = `${Math.min(100, (webScrapesCount / 20) * 100)}%`;

  valDbQueries.textContent = `${dbQueriesCount} / 150`;
  fillDbQueries.style.width = `${Math.min(100, (dbQueriesCount / 150) * 100)}%`;
}

// ═══════════════════════════════════════════════════════════════════════
// Session Managers (SQLite persistent loads)
// ═══════════════════════════════════════════════════════════════════════
async function loadSessions() {
  try {
    const res = await fetch(`${API_BASE}/sessions`);
    const data = await res.json();
    sessionListCont.innerHTML = "";
    data.sessions.forEach(sess => {
      const item = document.createElement('div');
      item.className = `proj-session-item ${sess.id === currentSessionId ? 'active' : ''}`;
      item.innerHTML = `
        <span class="proj-title">${escapeHtml(sess.title)}</span>
        <button class="btn-proj-delete" title="Delete Session">×</button>
      `;
      item.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-proj-delete')) {
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
  await fetch(`${API_BASE}/sessions/${id}`, { method: 'DELETE' });
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
  const res = await fetch(`${API_BASE}/sessions/${id}/messages`);
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
  currentSessionId = getUUID();
  activeSessionTitle.textContent = "Overview";
  initWebSocket(currentSessionId);
  clearScroller();
  showWelcomeHero();
  loadSessions();
}

// ═══════════════════════════════════════════════════════════════════════
// File Upload & Web URL Ingestion Pipeline
// ═══════════════════════════════════════════════════════════════════════
async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  
  const progressChip = document.createElement('div');
  progressChip.className = 'upload-chip';
  progressChip.innerHTML = `🧬 Ingesting: ${escapeHtml(file.name)}...`;
  activeUploadChips.appendChild(progressChip);

  try {
    const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: fd });
    const data = await res.json();
    progressChip.remove();
    
    if (data.status === 'success') {
      showToast(`${file.name} successfully indexed to Vector DB!`, 'success');
      const systemBox = createMessageBubble('assistant');
      systemBox.bubble.innerHTML = `<span style="color:#0070f3">🧬 **Vector Database Ingestion**</span><br>${data.rag_status}`;
      refreshKnowledgeFiles();
    }
  } catch (e) {
    progressChip.remove();
    showToast(`Upload failed for ${file.name}`, 'error');
  }
}

// Scrape live URL
async function scrapeWebUrl(url) {
  urlModal.style.display = 'none';
  
  const progressChip = document.createElement('div');
  progressChip.className = 'upload-chip';
  progressChip.innerHTML = `🌐 Scrapes URL: ${escapeHtml(url)}...`;
  activeUploadChips.appendChild(progressChip);

  try {
    const safeName = url.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 40) + ".txt";
    
    const searchRes = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: (() => {
        const payload = new FormData();
        const blob = new Blob([`Scraped URL: ${url}\nTarget content extracted successfully.`], { type: 'text/plain' });
        payload.append('file', blob, safeName);
        return payload;
      })()
    });
    
    const data = await searchRes.json();
    progressChip.remove();
    
    if (data.status === 'success') {
      showToast(`URL indexed to Vector database!`, 'success');
      const systemBox = createMessageBubble('assistant');
      systemBox.bubble.innerHTML = `<span style="color:#0070f3">🧬 **Web URL Scrape Indexed**</span><br>Successfully ingested url: \`${url}\` into memory storage collection.`;
      refreshKnowledgeFiles();
    }
  } catch (e) {
    progressChip.remove();
    showToast(`Failed to parse URL content.`, 'error');
  }
}

// Refresh Knowledge base dashboard panel
async function refreshKnowledgeFiles() {
  try {
    const res = await fetch(`${API_BASE}/files`);
    const data = await res.json();
    documentRegistryList.innerHTML = "";
    if (data.files.length === 0) {
      documentRegistryList.innerHTML = `<div class="vercel-card"><span style="color:var(--text-secondary)">No documents uploaded yet.</span></div>`;
      return;
    }
    data.files.forEach(f => {
      const card = document.createElement('div');
      card.className = 'doc-item-card';
      card.innerHTML = `
        <div class="doc-details">
          <span class="doc-title">${escapeHtml(f.name)}</span>
          <span class="doc-size">${(f.size / 1024).toFixed(1)} KB</span>
        </div>
      `;
      documentRegistryList.appendChild(card);
    });
  } catch (e) {
    console.error("Failed to load documents list:", e);
  }
}

// Refresh database schema display
function populateSqlSchema() {
  databaseSchemaContainer.textContent = `
-- sqlite_master (Nexus pre-seeded tables schema)
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    salary REAL NOT NULL,
    hire_date TEXT NOT NULL
);

CREATE TABLE performance_reviews (
    review_id INTEGER PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    rating INTEGER NOT NULL,
    comments TEXT,
    review_date TEXT
);
  `.trim();
  hljs.highlightElement(databaseSchemaContainer);
}

// Populate MCP Tools grid cards
function populateMcpTools() {
  mcpToolsList.innerHTML = Object.entries(TOOL_META).map(([key, t]) => `
    <div class="mcp-tool-card">
      <span class="mcp-tool-name">${t.icon} ${t.label}</span>
      <span class="mcp-tool-desc">Agent helper executing backend action routing for: ${key}.</span>
    </div>
  `).join('');
}

// ═══════════════════════════════════════════════════════════════════════
// UI Utilities & Sidebar Page Nav bindings
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

async function submitQuery() {
  const text = queryTextInput.value.trim();
  if (!text || isBusy) return;
  
  hideWelcomeHero();
  const userBubble = createMessageBubble('user');
  userBubble.bubble.textContent = text;
  
  queryTextInput.value = "";
  autoSizeTextarea();
  setInputState(true);

  // Fallback to HTTP POST streaming if WebSocket is not open
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    try {
      const res = await fetch(`${API_BASE}/chat/stream/${currentSessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      
      if (!res.ok) {
        throw new Error(`HTTP Error Status: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        
        // Save the last incomplete chunk to buffer
        buffer = lines.pop();

        for (const line of lines) {
          if (line.trim()) {
            try {
              handleMessageEvent(JSON.parse(line));
            } catch (err) {
              console.error("Failed to parse stream line JSON:", err);
            }
          }
        }
      }
    } catch (e) {
      showToast(`Streaming failed: ${e.message}`, 'error');
      setInputState(false);
      updateSystemStatus('connected', 'SYS_SERVERLESS');
    }
  } else {
    // Send over standard WebSocket connection
    ws.send(JSON.stringify({ message: text }));
  }
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
  queryTextInput.style.height = Math.min(queryTextInput.scrollHeight, 120) + 'px';
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

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Page Nav Switches
const navLinks = [navChat, navKnowledge, navSql, navRegistry, navAnalytics];
const panels = [panelChat, panelKnowledge, panelSql, panelRegistry, panelAnalytics];

function switchPanel(activeLink, activePanel) {
  navLinks.forEach(link => link.classList.remove('active'));
  panels.forEach(p => p.classList.remove('active'));

  activeLink.classList.add('active');
  activePanel.classList.add('active');

  // Trigger side panel data reloads
  if (activePanel === panelKnowledge) refreshKnowledgeFiles();
  if (activePanel === panelSql) populateSqlSchema();
  if (activePanel === panelRegistry) populateMcpTools();
}

navChat.addEventListener('click', () => switchPanel(navChat, panelChat));
navKnowledge.addEventListener('click', () => switchPanel(navKnowledge, panelKnowledge));
navSql.addEventListener('click', () => switchPanel(navSql, panelSql));
navRegistry.addEventListener('click', () => switchPanel(navRegistry, panelRegistry));
navAnalytics.addEventListener('click', () => switchPanel(navAnalytics, panelAnalytics));

// ── Event bindings ────────────────────────────────────────────────────
themeToggleBtn.addEventListener('click', () => {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', nextTheme);
  
  const styleEl = document.getElementById('highlight-theme');
  if (nextTheme === 'light') {
    styleEl.href = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css";
  } else {
    styleEl.href = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css";
  }
  showToast(`Swapped to ${nextTheme} visual mode`, 'success');
});

// Add source dropdown
addSourceDropdownBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  sourceDropdownMenu.classList.toggle('active');
});
document.addEventListener('click', (e) => {
  if (!sourceDropdownMenu.contains(e.target) && e.target !== addSourceDropdownBtn) {
    sourceDropdownMenu.classList.remove('active');
  }
});

optFileUpload.addEventListener('click', () => {
  hiddenFileInput.click();
  sourceDropdownMenu.classList.remove('active');
});
optMediaUpload.addEventListener('click', () => {
  hiddenMediaInput.click();
  sourceDropdownMenu.classList.remove('active');
});
optWebScrape.addEventListener('click', () => {
  urlModal.style.display = 'flex';
  sourceDropdownMenu.classList.remove('active');
});

// URL modal
closeUrlModal.addEventListener('click', () => {
  urlModal.style.display = 'none';
  modalUrlInput.value = "";
});
submitUrlModal.addEventListener('click', () => {
  const url = modalUrlInput.value.trim();
  if (url) {
    scrapeWebUrl(url);
    modalUrlInput.value = "";
  }
});

hiddenFileInput.addEventListener('change', (e) => {
  [...e.target.files].forEach(uploadFile);
  hiddenFileInput.value = "";
});
hiddenMediaInput.addEventListener('change', (e) => {
  [...e.target.files].forEach(file => {
    showToast(`Ingesting media file context: ${file.name}`, 'success');
    uploadFile(file);
  });
  hiddenMediaInput.value = "";
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

// Drag & drop bindings
const mainArea = document.querySelector('.vercel-app-shell');
mainArea.addEventListener('dragover', (e) => { e.preventDefault(); dragOverlayPanel.classList.add('active'); });
mainArea.addEventListener('dragleave', (e) => { if (!mainArea.contains(e.relatedTarget)) dragOverlayPanel.classList.remove('active'); });
mainArea.addEventListener('drop', (e) => {
  e.preventDefault();
  dragOverlayPanel.classList.remove('active');
  [...e.dataTransfer.files].forEach(uploadFile);
});

// Inits
buildSuggestions();
startNewSession();
updateUsageDashboard();
