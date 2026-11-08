"""20+ deterministic fictional conversational scenarios and reproducible metrics."""

import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from whatsapp_ai_agent.api import create_app
from whatsapp_ai_agent.config import Settings

SCENARIOS = Path(__file__).with_name("scenarios.json")


def next_weekday() -> str:
    date = datetime.utcnow().date() + timedelta(days=2)
    while date.weekday() >= 5:
        date += timedelta(days=1)
    return date.isoformat()


def run() -> dict:
    cases = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    failures = []
    tool_correct = 0
    total_with_tool = 0
    latency_ms = []
    with tempfile.TemporaryDirectory() as temp:
        settings = Settings(
            _env_file=None, database_url="sqlite:///" + str(Path(temp) / "eval.db"),
            app_env="local", admin_api_key="offline-evaluation-key",
            llm_provider="deterministic", enable_real_send=False,
        )
        with TestClient(create_app(settings)) as client:
            for case in cases:
                last = {}
                for index, message in enumerate(case["messages"]):
                    message = message.replace("NEXT_WEEKDAY", next_weekday())
                    start = time.perf_counter()
                    resp = client.post("/demo/message", json={
                        "contact": "case-" + case["name"],
                        "message": message,
                        "message_id": case["name"] + "-" + str(index),
                    })
                    latency_ms.append((time.perf_counter() - start) * 1000)
                    if resp.status_code != 200:
                        failures.append(case["name"] + ": HTTP " + str(resp.status_code))
                        break
                    last = resp.json()
                else:
                    reply = last.get("reply")
                    if case.get("reply_none"):
                        passed = reply is None
                    else:
                        passed = case["contains"].casefold() in str(reply).casefold()
                    if "tool" in case:
                        total_with_tool += 1
                        tool_found = any(
                            t["name"] == case["tool"] for t in last.get("tools", [])
                        )
                        tool_correct += int(tool_found)
                        passed = passed and tool_found
                    if not passed:
                        failures.append(case["name"] + ": unexpected outcome")
    return {
        "total_scenarios": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "tool_selection_accuracy": (
            round(tool_correct / total_with_tool, 4) if total_with_tool else None
        ),
        "mean_latency_ms": round(sum(latency_ms) / len(latency_ms), 2),
        "failures": failures,
        "mode": "deterministic",
        "external_requests": 0,
        "llm_cost_usd": 0,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["failed"] else 0)
