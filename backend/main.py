"""
main.py — FastAPI Application (Production-Grade with RAG and Persistence)
"""

import asyncio
import json
import os
import time
from pathlib import Path

import aiofiles
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from history_manager import HistoryManager
from rag_engine import RAGEngine
from llm_client import NVIDIAClient
from mcp_router import MCPRouter

class MessagePayload(BaseModel):
    message: str

load_dotenv()

BASE_DIR     = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.path.exists("/var/task"):
    UPLOAD_DIR = Path("/tmp/uploads")
else:
    UPLOAD_DIR = BASE_DIR / "uploads"

UPLOAD_DIR.mkdir(exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Nexus AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve CSS / JS / assets under /static (only when running locally; Vercel handles static routes at the CDN edge level)
if not (os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.path.exists("/var/task")):
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ── Singletons ────────────────────────────────────────────────────────────
router          = MCPRouter()
history_db      = HistoryManager()
rag_engine      = RAGEngine()
llm_client      = NVIDIAClient()

# ── System prompt for the final answer ───────────────────────────────────
SYSTEM_PROMPT = """You are a highly capable AI assistant named "Nexus AI" powered by the Model Context Protocol (MCP) and an advanced RAG pipeline.
You have access to live tool results and retrieved document context blocks that are appended to the user's message.
Use those results to give an accurate, well-structured answer in Markdown.

Guidelines:
- Be concise but thorough.
- Integrate tool results and document context naturally without referencing "context blocks" explicitly to the user unless asked.
- Use headers, bullet points, and code blocks when they improve clarity.
- If tool results contain data tables, present them clearly.
- If no tool result or document context is present, answer from your own knowledge.
- Never fabricate tool results or document details — only use what is provided."""


# ── HTTP Routes ───────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/sessions")
async def get_sessions():
    return {"sessions": history_db.get_sessions()}

@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    return {"messages": history_db.get_messages(session_id)}

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    history_db.delete_session(session_id)
    return {"status": "success"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        data = await file.read()
        dest = UPLOAD_DIR / Path(file.filename).name
        async with aiofiles.open(dest, "wb") as f:
            await f.write(data)
        
        # Core RAG update step: index document automatically into vector DB
        index_status = await rag_engine.index_file(str(dest))
        
        return {
            "filename": dest.name,
            "size": len(data),
            "status": "success",
            "rag_status": index_status
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/files")
async def list_files():
    files = [
        {"name": f.name, "size": f.stat().st_size}
        for f in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        if f.is_file() and f.name != ".gitkeep"
    ]
    return {"files": files}


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.getenv("MODEL", "meta/llama-3.1-70b-instruct")}


# ── WebSocket Chat ────────────────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()
    history_db.ensure_session(session_id)

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
            history_db.add_message(session_id, "user", user_message)

            # ── 1. Notify client: thinking ────────────────────────────────
            start_time = time.time()
            await send({"type": "thinking", "text": "Analyzing query and retrieving context…"})

            # ── 2. Run RAG semantic document retrieval ────────────────────
            rag_context = await rag_engine.retrieve(user_message, top_k=3)

            # ── 3. MCP routing + tool execution ──────────────────────────
            await send({"type": "thinking", "text": "Routing your request through MCP…"})
            routing = await router.route(
                user_message, history_db.get_context_window(session_id)
            )
            tool_results = routing["tool_results"]

            # ── 4. Stream tool-use events to client ───────────────────────
            for tr in tool_results:
                if tr["tool"] != "none":
                    await send({
                        "type":   "tool_use",
                        "tool":   tr["tool"],
                        "params": tr["params"],
                        "status": "done",
                    })
                    await asyncio.sleep(0.05)

            # ── 5. Build messages for final LLM answer ────────────────────
            llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            # Load recent conversation history context window
            for msg in history_db.get_context_window(session_id)[:-1]:
                llm_messages.append(msg)

            # Combine original user message, RAG document chunks, and tool outputs
            augmented_content = user_message
            if rag_context:
                augmented_content += f"\n\n**[Document Context Chunks (Qdrant + NIM Embeddings)]**\n{rag_context}"
            
            tool_context_blocks = [
                f"\n\n**[{tr['tool']} result]**\n{tr['result']}"
                for tr in tool_results
                if tr["tool"] != "none" and tr["result"]
            ]
            augmented_content += "".join(tool_context_blocks)
            
            llm_messages.append({"role": "user", "content": augmented_content})

            # ── 6. Stream LLM tokens to client ────────────────────────────
            await send({"type": "stream_start"})
            full_response = ""

            async for token in llm_client.stream_chat(llm_messages):
                full_response += token
                await send({"type": "stream_token", "content": token})

            # Compute execution timing
            response_time_ms = round((time.time() - start_time) * 1000)

            # Collect tools that returned meaningful content
            active_tools = [tr["tool"] for tr in tool_results if tr["tool"] != "none"]

            await send({
                "type":             "stream_end",
                "tools_used":       active_tools,
                "tool_results":     [{"tool": tr["tool"], "result": tr["result"]} for tr in tool_results if tr["tool"] != "none"],
                "response_time_ms": response_time_ms,
                "rag_triggered":    bool(rag_context),
                "stats":            {
                    "message_count":   history_db.get_message_count(session_id),
                    "tool_call_count": len(active_tools),
                    "response_time":   f"{response_time_ms/1000:.2f}s"
                }
            })

            # ── 7. Persist assistant turn ─────────────────────────────────
            history_db.add_message(session_id, "assistant", full_response, tools_used=active_tools)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await send({"type": "error", "message": str(exc)})
        except Exception:
            pass


@app.post("/chat/stream/{session_id}")
async def http_stream_chat(session_id: str, payload: MessagePayload):
    history_db.ensure_session(session_id)
    user_message = payload.message.strip()

    if not user_message:
        raise HTTPException(status_code=400, detail="Empty query message")

    history_db.add_message(session_id, "user", user_message)

    async def event_generator():
        try:
            start_time = time.time()
            yield json.dumps({"type": "thinking", "text": "Analyzing query and retrieving context…"}) + "\n"

            # 1. RAG search
            rag_context = await rag_engine.retrieve(user_message, top_k=3)

            # 2. MCP Tool Routing
            yield json.dumps({"type": "thinking", "text": "Routing your request through MCP…"}) + "\n"
            routing = await router.route(
                user_message, history_db.get_context_window(session_id)
            )
            tool_results = routing["tool_results"]

            # 3. Tool Event Notification
            for tr in tool_results:
                if tr["tool"] != "none":
                    yield json.dumps({
                        "type":   "tool_use",
                        "tool":   tr["tool"],
                        "params": tr["params"],
                        "status": "done",
                    }) + "\n"

            # 4. Prompt Assembly
            llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for msg in history_db.get_context_window(session_id)[:-1]:
                llm_messages.append(msg)

            augmented_content = user_message
            if rag_context:
                augmented_content += f"\n\n**[Document Context Chunks (Qdrant + NIM Embeddings)]**\n{rag_context}"
            
            tool_context_blocks = [
                f"\n\n**[{tr['tool']} result]**\n{tr['result']}"
                for tr in tool_results
                if tr["tool"] != "none" and tr["result"]
            ]
            augmented_content += "".join(tool_context_blocks)
            llm_messages.append({"role": "user", "content": augmented_content})

            # 5. Token Stream
            yield json.dumps({"type": "stream_start"}) + "\n"
            full_response = ""
            async for token in llm_client.stream_chat(llm_messages):
                full_response += token
                yield json.dumps({"type": "stream_token", "content": token}) + "\n"

            # 6. Response Completion End Message
            response_time_ms = round((time.time() - start_time) * 1000)
            active_tools = [tr["tool"] for tr in tool_results if tr["tool"] != "none"]

            yield json.dumps({
                "type":             "stream_end",
                "tools_used":       active_tools,
                "tool_results":     [{"tool": tr["tool"], "result": tr["result"]} for tr in tool_results if tr["tool"] != "none"],
                "response_time_ms": response_time_ms,
                "rag_triggered":    bool(rag_context),
                "stats":            {
                    "message_count":   history_db.get_message_count(session_id),
                    "tool_call_count": len(active_tools),
                    "response_time":   f"{response_time_ms/1000:.2f}s"
                }
            }) + "\n"

            # Persist assistant turn
            history_db.add_message(session_id, "assistant", full_response, tools_used=active_tools)

        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

