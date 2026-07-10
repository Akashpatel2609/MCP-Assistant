"""
agents/code_runner.py — Sandboxed Python Code Execution Agent
Runs code in a subprocess with a strict 10-second timeout.
"""

import asyncio
import os
import sys
import tempfile


class CodeRunnerAgent:
    """Executes Python code safely inside a subprocess."""

    TIMEOUT = 10  # seconds

    async def execute(self, code: str) -> str:
        if not code.strip():
            return "No code provided."

        # Write to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return f"⏱️ **Timeout** — code execution exceeded {self.TIMEOUT} seconds and was stopped."
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        parts = [f"```python\n{code}\n```\n"]
        if out:
            parts.append(f"✅ **Output:**\n```\n{out}\n```")
        if err:
            parts.append(f"⚠️ **Stderr:**\n```\n{err}\n```")
        if not out and not err:
            parts.append("✅ Code ran successfully with no output.")

        return "\n".join(parts)
