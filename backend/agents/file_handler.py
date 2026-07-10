"""
agents/file_handler.py — File Upload, Read, Write Agent
"""

import aiofiles
from pathlib import Path

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class FileHandlerAgent:
    """Handles reading and listing files that users upload."""

    async def read_file(self, filename: str) -> str:
        filename = Path(filename).name  # prevent path traversal
        filepath = UPLOAD_DIR / filename
        if not filepath.exists():
            return f"❌ File **'{filename}'** not found. Use the upload button to add files."
        try:
            async with aiofiles.open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = await f.read()
            size = len(content)
            truncated = size > 8000
            if truncated:
                content = content[:8000]
            header = f"📄 **File: {filename}** ({size:,} chars)\n\n"
            footer = "\n\n*... [file truncated to first 8,000 characters]*" if truncated else ""
            return header + content + footer
        except Exception as exc:
            return f"Error reading file: {exc}"

    async def list_files(self) -> str:
        files = sorted(UPLOAD_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return "📂 No files uploaded yet. Use the 📎 button to upload a file."
        lines = ["📂 **Uploaded files:**\n"]
        for f in files:
            size_kb = f.stat().st_size / 1024
            lines.append(f"• **{f.name}** ({size_kb:.1f} KB)")
        return "\n".join(lines)

    async def write_file(self, filename: str, content: str) -> str:
        filename = Path(filename).name
        filepath = UPLOAD_DIR / filename
        try:
            async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                await f.write(content)
            return f"✅ File **'{filename}'** written successfully ({len(content):,} chars)."
        except Exception as exc:
            return f"Error writing file: {exc}"
