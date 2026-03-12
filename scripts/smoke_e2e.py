#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SECRETS_SOURCE = ROOT / ".local" / "test_kimi_v7.md"
WORKDIR = ROOT / ".local" / "smoke_e2e"
LEGACY_SOURCE = ROOT / "examples" / "court-mode" / "topic1_debate_log.md"


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def prepare_env() -> dict[str, str]:
    text = SECRETS_SOURCE.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---", 2)[1])
    env = os.environ.copy()
    env["DEBATE_BASE_URL"] = front["base_url"]
    env["DEBATE_API_KEY"] = front["api_key"]
    return env


def prepare_workspace() -> Path:
    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir(parents=True, exist_ok=True)

    topic_path = WORKDIR / "catdog.md"
    topic_path.write_text(
        """---
title: "Smoke Cat vs Dog GPT-4o-mini"
rounds: 2
cross_exam: 1
cot: 80
middle_task_optional: true
max_reply_tokens: 180
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 猫党代表
    model: gpt-4o-mini
    style: 简洁、直接、偏爱猫咪
  - name: 狗党代表
    model: gpt-4o-mini
    style: 简洁、直接、偏爱狗狗
judge:
  name: 裁判
  model: gpt-4o-mini
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 240
round1_task: "论证你支持的宠物更好，100-150字。"
middle_task: "回应对方观点并补充新论点，120-180字。"
final_task: "给出最终结论，120-180字。"
judge_instructions: |
  用简短结构化方式输出：
  1. 谁胜出
  2. 关键理由（2点）
  3. 最终建议
---
猫和狗谁更适合作为城市独居者的宠物？请考虑陪伴性、照料成本、生活方式适配。
""",
        encoding="utf-8",
    )
    (WORKDIR / "legacy_debate_log.md").write_text(
        LEGACY_SOURCE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return topic_path


def assert_expected_failure(cmd: list[str], *, env: dict[str, str], label: str) -> None:
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        raise RuntimeError(f"expected failure did not occur: {label}")


def main() -> int:
    env = prepare_env()
    topic_path = prepare_workspace()
    log_path = WORKDIR / "catdog_debate_log.json"
    summary_path = WORKDIR / "catdog_debate_summary.md"
    converted_path = WORKDIR / "legacy_debate_log.json"

    run([sys.executable, "-m", "debate_tool", "run", str(topic_path)], env=env)
    run(
        [
            sys.executable,
            "-m",
            "debate_tool",
            "resume",
            str(topic_path),
            str(log_path),
            "--rounds",
            "2",
            "--cross-exam",
            "1",
            "--message",
            "请加入成本与陪伴性角度",
        ],
        env=env,
    )
    run(
        [
            sys.executable,
            "-m",
            "debate_tool",
            "compact",
            str(log_path),
            "--compress",
            "-3",
        ],
        env=env,
    )
    run([sys.executable, str(ROOT / "scripts" / "convert_md_log_to_json.py"), str(WORKDIR / "legacy_debate_log.md")], env=env)

    assert_expected_failure(
        [sys.executable, "-m", "debate_tool", "resume", str(topic_path), str(topic_path)],
        env=env,
        label="no log provided",
    )
    assert_expected_failure(
        [sys.executable, "-m", "debate_tool", "resume", str(log_path), str(log_path)],
        env=env,
        label="two logs provided",
    )

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["format"] == "debate-tool-log"
    assert payload["version"] == 1
    assert any(e["tag"] == "summary" for e in payload["entries"])
    assert any(e["tag"] == "cross_exam" for e in payload["entries"])
    assert summary_path.exists()
    assert converted_path.exists()

    print(f"SMOKE_DIR={WORKDIR}")
    print(f"LOG_ENTRIES={len(payload['entries'])}")
    print(f"SUMMARY_EXISTS={int(summary_path.exists())}")
    print(f"CONVERTED_EXISTS={int(converted_path.exists())}")
    print("EXPECTED_ERROR_NO_LOG=1")
    print("EXPECTED_ERROR_TWO_LOGS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
