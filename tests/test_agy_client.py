import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import agent.agy_client
from agent.agy_client import AgyClient, render_task
from agent.llm_client import LLMError


class FakeLogger:
    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(row)


class FakeBudget:
    def check(self, cost):
        pass

    def record(self, cost):
        pass


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(agent.agy_client, "_sleep", AsyncMock())


def make_client(tmp_path, outputs):
    settings = SimpleNamespace(openrouter_api_key=None, composio_api_key=None)
    logger = FakeLogger()
    budget = FakeBudget()
    calls = []

    async def fake_runner(cmd, cwd, timeout):
        task_text = (cwd / "task.md").read_text(encoding="utf-8") if (cwd / "task.md").exists() else ""
        schema_exists = (cwd / "schema.json").exists()
        calls.append({"cmd": list(cmd), "task": task_text, "schema_exists": schema_exists})
        ret_code, out, err = outputs.pop(0)
        return ret_code, out, err

    client = AgyClient(
        settings,
        logger,
        budget,
        run_id="test_run",
        runner=fake_runner,
        raw_dir=tmp_path,
        agy_bin="agy",
    )
    return client, logger, calls


def test_success_with_structured_output(tmp_path):
    output_json = {
        "status": "SUCCESS",
        "structured_output": {"a": 1},
        "usage": {"input_tokens": 50, "output_tokens": 10, "thinking_tokens": 5},
    }
    client, logger, calls = make_client(tmp_path, [(0, json.dumps(output_json), "")])

    resp = asyncio.run(
        client.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="gemini-3.8-flash-medium",
            stage="pass1",
            app_id=1,
            prompt_version="v1",
            json_schema={"type": "object"},
        )
    )

    assert resp.text == '{"a": 1}'
    assert resp.tokens_out == 15
    assert resp.tokens_in == 50
    assert resp.cost_usd == 0.0
    assert len(logger.rows) == 1
    assert logger.rows[0]["status"] == "ok"
    assert logger.rows[0]["backend"] == "agy"

    assert len(calls) == 1
    cmd = calls[0]["cmd"]
    assert cmd[-1].startswith("-p=")
    assert cmd[cmd.index("--mode") + 1] == "plan"
    assert calls[0]["schema_exists"] is True


def test_error_then_success_retries(tmp_path):
    err_json = {"status": "ERROR", "error": "rate limited"}
    succ_json = {
        "status": "SUCCESS",
        "response": '{"a":2}',
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    client, logger, calls = make_client(
        tmp_path,
        [(1, json.dumps(err_json), "error"), (0, json.dumps(succ_json), "")],
    )

    resp = asyncio.run(
        client.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="gemini-3.8-flash-medium",
            stage="pass1",
            app_id=2,
            prompt_version="v1",
        )
    )

    assert resp.text == '{"a":2}'
    assert resp.retries == 1
    assert len(calls) == 2


def test_invalid_json_schema_fallback(tmp_path):
    err_json = {"status": "ERROR", "error": "invalid json schema provided"}
    succ_json = {
        "status": "SUCCESS",
        "response": '{"fallback": true}',
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    client, logger, calls = make_client(
        tmp_path,
        [(1, json.dumps(err_json), ""), (0, json.dumps(succ_json), "")],
    )

    resp = asyncio.run(
        client.chat(
            messages=[{"role": "user", "content": "hi"}],
            model="gemini-3.8-flash-medium",
            stage="pass1",
            app_id=3,
            prompt_version="v1",
            json_schema={"type": "object"},
        )
    )

    assert resp.text == '{"fallback": true}'
    assert "gemini-3.8-flash-medium" in client._no_schema
    assert len(calls) == 2
    assert calls[0]["schema_exists"] is True
    assert calls[1]["schema_exists"] is False


def test_success_with_blank_response_raises(tmp_path):
    output_json = {
        "status": "SUCCESS",
        "response": "   ",
        "usage": {"input_tokens": 10, "output_tokens": 0},
    }
    client, logger, calls = make_client(tmp_path, [(0, json.dumps(output_json), "")])

    with pytest.raises(LLMError) as exc_info:
        asyncio.run(
            client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="gemini-3.8-flash-medium",
                stage="pass1",
                app_id=4,
                prompt_version="v1",
            )
        )
    assert exc_info.value.kind == "empty_content"


def test_three_errors_raises_transient(tmp_path):
    err_json = {"status": "ERROR", "error": "temporary failure"}
    client, logger, calls = make_client(
        tmp_path,
        [
            (1, json.dumps(err_json), "err1"),
            (1, json.dumps(err_json), "err2"),
            (1, json.dumps(err_json), "err3"),
        ],
    )

    with pytest.raises(LLMError) as exc_info:
        asyncio.run(
            client.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="gemini-3.8-flash-medium",
                stage="pass1",
                app_id=5,
                prompt_version="v1",
            )
        )
    assert exc_info.value.kind == "transient"
    assert len(logger.rows) == 1
    assert logger.rows[0]["status"] == "error"


def test_render_task():
    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]
    assert render_task(messages) == "# SYSTEM\n\nS\n\n# USER\n\nU\n"
