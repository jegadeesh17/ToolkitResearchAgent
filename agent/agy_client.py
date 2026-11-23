"""LLM backend that runs the Antigravity CLI (`agy`) in print mode instead of calling an HTTP API.

Same `chat()` contract as `agent.llm_client.LLMClient`, so the pipeline, verification loops and run log
are unchanged. Each call writes the messages to `task.md` (and the JSON schema to `schema.json`) in a fresh
temp folder, because Windows caps a command line at ~32K characters; runs `agy` in that folder in plan mode
(it can read the file but cannot edit anything); takes `structured_output` when present; and logs exactly
one `kind: "llm"` line. Cost is recorded as 0: calls run on the user's Antigravity plan, not an API key.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from agent.budget import BudgetGuard
from agent.config import Settings, secret_values
from agent.llm_client import LLMError, LLMResponse
from agent.observability import RunLogger, redact, save_raw

PRINT_PROMPT = ("Read the file task.md in the current directory and follow its instructions exactly. "
                "Do not search the web, do not run commands and do not edit files: use only the text in task.md. "
                "Your final answer must be only the JSON object it asks for.")
TIMEOUT_S = 300
ATTEMPTS = 3
_sleep = asyncio.sleep  # patched in tests

Runner = Callable[[list[str], Path, float], Awaitable[tuple[int, str, str]]]


async def _run_subprocess(cmd: list[str], cwd: Path, timeout: float) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return 124, "", f"timeout after {timeout:.0f}s"
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def render_task(messages: list[dict]) -> str:
    """Messages -> one markdown task file (each turn under its role)."""
    parts = []
    for m in messages:
        content = m.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        parts.append(f"# {str(m.get('role', 'user')).upper()}\n\n{text}")
    return "\n\n".join(parts) + "\n"


class AgyClient:
    def __init__(self, settings: Settings, logger: RunLogger, budget: BudgetGuard, *, run_id: str,
                 runner: Runner | None = None, raw_dir: Path | None = None, agy_bin: str | None = None):
        self.logger = logger
        self.budget = budget
        self.run_id = run_id
        self.raw_dir = raw_dir
        self._secrets = secret_values(settings)
        self._runner = runner or _run_subprocess
        self._bin = agy_bin or shutil.which("agy") or "agy"
        self._counter = itertools.count(1)
        self._no_schema: set[str] = set()  # models whose CLI rejected --json-schema

    async def aclose(self) -> None:
        return None

    async def key_status(self) -> dict:
        return {}

    def _command(self, model: str, schema_file: Path | None) -> list[str]:
        cmd = [self._bin, "--output-format", "json", "--model", model, "--mode", "plan",
               "--print-timeout", f"{TIMEOUT_S}s"]
        if schema_file is not None:
            cmd += ["--json-schema", str(schema_file)]
        return [*cmd, f"-p={PRINT_PROMPT}"]

    async def chat(self, *, messages: list[dict], model: str, stage: str, app_id: int | None, prompt_version: str,
                   json_schema: dict | None = None, max_tokens: int = 4000,
                   reasoning: dict | None = None) -> LLMResponse:
        started = time.monotonic()
        raw_name = f"llm_{stage}_{app_id}_{next(self._counter)}.json"
        attempts = 0
        notes: list[str] = []
        data: dict = {}
        task = render_task(messages)

        def log(status: str, error: str | None, **extra) -> None:
            self.logger.append({
                "kind": "llm", "run_id": self.run_id, "app_id": app_id, "stage": stage, "model": model,
                "prompt_version": prompt_version, "latency_ms": int((time.monotonic() - started) * 1000),
                "retries": max(attempts - 1, 0), "status": status, "backend": "agy",
                "error": "; ".join([*notes, error] if error else notes) or None, **extra})

        last_error = "no attempt"
        while attempts < ATTEMPTS:
            attempts += 1
            self.budget.check(0.0)
            use_schema = json_schema is not None and model not in self._no_schema
            work = Path(tempfile.mkdtemp(prefix="agy_"))
            try:
                (work / "task.md").write_text(task, encoding="utf-8")
                schema_file = None
                if use_schema:
                    schema_file = work / "schema.json"
                    schema_file.write_text(json.dumps(json_schema), encoding="utf-8")
                code, out, err = await self._runner(self._command(model, schema_file), work, TIMEOUT_S + 60)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            try:
                data = json.loads(out) if out.strip() else {}
            except ValueError:
                data = {}
            if str(data.get("status") or "") == "SUCCESS":
                break
            last_error = redact(str(data.get("error") or err or f"exit {code}")[:300], self._secrets)
            if use_schema and "schema" in last_error.lower():
                self._no_schema.add(model)
                notes.append("format_downgraded:none")
                attempts -= 1  # a schema rejection is not a failed attempt
                continue
            notes.append(f"attempt {attempts}: {last_error}")
            if attempts < ATTEMPTS:
                await _sleep(2 ** attempts)
        else:
            log("error", last_error)
            raise LLMError(f"agy: {last_error}", kind="transient")

        structured = data.get("structured_output")
        text = json.dumps(structured, ensure_ascii=False) if structured is not None else str(data.get("response") or "")
        usage = data.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or 0) + int(usage.get("thinking_tokens") or 0)
        self.budget.record(0.0)
        raw_path = save_raw(self.run_id, raw_name, {"request": {"model": model, "task": task, "schema": json_schema},
                                                    "response": data}, self.raw_dir, self._secrets)
        common = {"tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": 0.0, "cost_estimated": False,
                  "raw_path": raw_path}
        if not text.strip():
            log("error", "empty_content", **common)
            raise LLMError("empty_content", kind="empty_content")
        log("ok", None, **common)
        return LLMResponse(text=text, model=model, tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=0.0,
                           cost_estimated=False, latency_ms=int((time.monotonic() - started) * 1000),
                           retries=attempts - 1, raw_path=raw_path)
