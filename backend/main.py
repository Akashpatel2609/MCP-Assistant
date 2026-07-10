"""
main.py — FastAPI Application
Exposes:
  GET  /           → serves frontend/index.html
  POST /upload     → file upload endpoint
  GET  /files      → list uploaded files
  GET  /health     → health check
  WS   /ws/{sid}  → real-time chat via WebSocket
"""

import asyncio
import json
import os
from pathlib import Path

import aiofiles
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from context_manager import ContextManager
from llm_client import NVIDIAClient
from mcp_router import MCPRouter

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
UPLOAD_DIR   = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(title="MCP AI Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve CSS / JS / assets under /static
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ── Singletons ────────────────────────────────────────────────────────────
router          = MCPRouter()
context_manager = ContextManager()
llm_client      = NVIDIAClient()

# ── System prompt for the final answer ───────────────────────────────────
SYSTEM_PROMPT = """You are a highly capable AI assistant powered by the Model Context Protocol (MCP).
You have access to live tool results that are appended to the user's message.
Use those results to give an accurate, well-structured answer in Markdown.

Guidelines:
- Be concise but thorough.
- Use headers, bullet points, and code blocks when they improve clarity.
- If tool results contain data tables, present them clearly.
- If no tool result was needed, answer from your own knowledge.
- Never fabricate tool results — only use what is provided."""


# ── HTTP Routes ───────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        data = await file.read()
        dest = UPLOAD_DIR / Path(file.filename).name
        async with aiofiles.open(dest, "wb") as f:
            await f.write(data)
        return {
            "filename": dest.name,
            "size": len(data),
            "status": "success",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/files")
async def list_files():
    files = [
        {"name": f.name, "size": f.stat().st_size}
        for f in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        if f.is_file()
    ]
    return {"files": files}


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.getenv("MODEL", "meta/llama-3.1-70b-instruct")}


# ── WebSocket Chat ────────────────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()

    async def send(payload: dict):
        await websocket.send_text(json.dumps(payload))

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            user_message = data.get("message", "").strip()

            if not user_message:
                continue

            # Persist user turn
            context_manager.add_message(session_id, "user", user_message)

            # ── 1. Notify client: thinking ────────────────────────────────
            await send({"type": "thinking", "text": "Routing your request through MCP…"})

            # ── 2. MCP routing + tool execution ──────────────────────────
            routing = await router.route(
                user_message, context_manager.get_messages(session_id)
            )
            tool_results = routing["tool_results"]

            # ── 3. Stream tool-use events to client ───────────────────────
            for tr in tool_results:
                if tr["tool"] != "none":
                    context_manager.increment_tool_count(session_id)
                    await send({
                        "type":   "tool_use",
                        "tool":   tr["tool"],
                        "params": tr["params"],
                        "status": "done",
                    })
                    await asyncio.sleep(0.05)

            # ── 4. Build messages for final LLM answer ────────────────────
            llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            # Recent history (exclude the just-added user message)
            for msg in context_manager.get_messages(session_id)[:-1][-12:]:
                llm_messages.append(msg)

            # Append tool context to user message
            tool_context_blocks = [
                f"\n\n**[{tr['tool']} result]**\n{tr['result']}"
                for tr in tool_results
                if tr["tool"] != "none" and tr["result"]
            ]
            augmented_message = user_message + "".join(tool_context_blocks)
            llm_messages.append({"role": "user", "content": augmented_message})

            # ── 5. Stream LLM tokens to client ────────────────────────────
            await send({"type": "stream_start"})
            full_response = ""

            async for token in llm_client.stream_chat(llm_messages):
                full_response += token
                await send({"type": "stream_token", "content": token})

            await send({
                "type":       "stream_end",
                "tools_used": [tr["tool"] for tr in tool_results if tr["tool"] != "none"],
                "stats":      context_manager.get_stats(session_id),
            })

            # ── 6. Persist assistant turn ─────────────────────────────────
            context_manager.add_message(session_id, "assistant", full_response)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await send({"type": "error", "message": str(exc)})
        except Exception:
            pass
