# MCP-Powered AI Assistant 🤖

> An intelligent AI assistant that connects to external tools, APIs, and real-time data sources using the **Model Context Protocol (MCP)** — built with FastAPI, Llama 3.1 70B (NVIDIA NIM), and a premium real-time chat UI.

---

## ✨ Features

| Tool Agent | Capability |
|---|---|
| 🔍 **Web Search** | Live internet search via DuckDuckGo |
| 🌤️ **Weather** | Real-time weather for any city |
| 📰 **News** | Latest headlines from BBC, Reuters, Al Jazeera |
| 📄 **File Handler** | Upload, read, and summarize files |
| 🗄️ **Database** | Natural-language SQL queries on SQLite |
| ⚙️ **Code Runner** | Execute Python code in a sandbox |

---

## 🚀 Quick Start (Local)

### Prerequisites
- Python 3.10+
- pip

### 1. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure API keys
The `.env` file is already set up. Verify it contains:
```
NVIDIA_API_KEY=your_key
OPENWEATHER_API_KEY=your_key
```

### 3. Run the server
```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Open the app
Visit **http://localhost:8000** in your browser.

---

## 🐳 Docker (Production)

```bash
# Build and start
docker compose up --build -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

---

## 🏗️ Architecture

```
User
  ↓
Chat Interface (HTML/CSS/JS + WebSocket)
  ↓
FastAPI Server (main.py)
  ↓
MCP Router (mcp_router.py)
  ↓ ─────────────────────────────────────────
  ↓              ↓              ↓            ↓
Web Search   Database      Code Runner   Weather/News
Agent        Agent         Agent         Agent
  ↓              ↓              ↓            ↓
 ─────────────────────────────────────────────
  ↓
Context Manager (session memory)
  ↓
NVIDIA NIM LLM (Llama 3.1 70B)
  ↓
Streamed Response → WebSocket → UI
```

---

## 🗂️ Project Structure

```
mcp-ai-assistant/
├── backend/
│   ├── main.py              # FastAPI app + WebSocket
│   ├── mcp_router.py        # MCP routing engine
│   ├── llm_client.py        # NVIDIA NIM wrapper
│   ├── context_manager.py   # Session memory
│   ├── requirements.txt
│   └── agents/
│       ├── web_search.py
│       ├── file_handler.py
│       ├── db_query.py
│       ├── code_runner.py
│       └── weather.py
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── .env
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🛠️ Tech Stack

- **Backend**: Python · FastAPI · Uvicorn · WebSockets
- **LLM**: Llama 3.1 70B via NVIDIA NIM (OpenAI-compatible API)
- **Agents**: DuckDuckGo Search · OpenWeatherMap · feedparser · SQLite · subprocess
- **Frontend**: Vanilla HTML/CSS/JS · marked.js · highlight.js
- **Infrastructure**: Docker · Docker Compose

---

## 📝 Sample Queries to Try

- *"What are the latest AI news?"* → triggers web_search
- *"Weather in Tokyo"* → triggers get_weather
- *"Show all employees earning over $90,000"* → triggers db_query
- *"Run: import math; print(math.pi)"* → triggers run_code
- *"Upload a file and summarize it"* → triggers file upload + read_file
- *"What are today's top news headlines?"* → triggers get_news

---

Built as Portfolio Project #1 — MCP-Powered AI Assistant
