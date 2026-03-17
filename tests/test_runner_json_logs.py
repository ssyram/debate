from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from unittest.mock import patch

from debate_tool.runner import (
    LOG_FORMAT,
    LOG_VERSION,
    Log,
    LogFormatError,
    _describe_overrides,
    _extract_cross_exam_json,
    _extract_cross_exam_target,
    _extract_response_text,
    build_log_path,
    compact_log,
    init_debug_logging,
    identify_files,
    parse_resume_topic,
    parse_topic_file,
    resolve_effective_config,
    resume,
    run_cross_exam,
    run,
)
from debate_tool.__main__ import main as cli_main


class _FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, responses: list[_FakeResponse], recorder: list[dict] | None = None, **kwargs):
        self._responses = responses
        self._recorder = recorder if recorder is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self._recorder.append({"url": url, "json": json, "headers": headers})
        if not self._responses:
            raise RuntimeError("no fake response available")
        return self._responses.pop(0)


class TopicParsingTests(unittest.TestCase):
    def test_parse_topic_file_tolerates_malformed_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            topic_path = Path(tmp) / "broken_topic.md"
            topic_path.write_text("---\n: bad\n---\nHello topic", encoding="utf-8")

            cfg = parse_topic_file(topic_path)

            self.assertEqual(cfg["title"], "broken_topic")
            self.assertEqual(cfg["rounds"], 3)
            self.assertEqual(cfg["timeout"], 300)
            self.assertTrue(cfg["debaters"])
            self.assertEqual(cfg["topic_body"], "Hello topic")

    def test_parse_topic_file_tolerates_non_mapping_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            topic_path = Path(tmp) / "scalar_topic.md"
            topic_path.write_text("---\nhello\n---\nBody", encoding="utf-8")

            cfg = parse_topic_file(topic_path)

            self.assertEqual(cfg["title"], "scalar_topic")
            self.assertEqual(cfg["cross_exam"], 0)
            self.assertIsNone(cfg["cot_length"])


class CrossExamParsingTests(unittest.TestCase):
    def test_extract_cross_exam_json_parses_plain_json(self):
        result = '{"target":"Linus Torvalds","reason":"x","questions":["q1","q2"]}'
        payload = _extract_cross_exam_json(result)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["target"], "Linus Torvalds")

    def test_extract_cross_exam_json_parses_fenced_json(self):
        result = "```json\n{\"target\":\"康德（Immanuel Kant）\",\"reason\":\"x\",\"questions\":[\"q1\",\"q2\"]}\n```"
        payload = _extract_cross_exam_json(result)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["target"], "康德（Immanuel Kant）")

    def test_extract_cross_exam_target_supports_json_target(self):
        result = '{"target":"Linus Torvalds","reason":"x","questions":["q1","q2"]}'
        target = _extract_cross_exam_target(
            result,
            questioner_name="Ssyram",
            debater_names=["Linus Torvalds", "Ssyram", "康德（Immanuel Kant）"],
        )
        self.assertEqual(target, "Linus Torvalds")

    def test_extract_cross_exam_target_prefers_explicit_marker(self):
        result = "质询对象：Linus Torvalds\n\n问题1：..."
        target = _extract_cross_exam_target(
            result,
            questioner_name="Ssyram",
            debater_names=["Linus Torvalds", "Ssyram", "康德（Immanuel Kant）"],
        )
        self.assertEqual(target, "Linus Torvalds")

    def test_extract_cross_exam_target_supports_target_tag(self):
        result = "[TARGET]康德（Immanuel Kant）[/TARGET]\n1. ..."
        target = _extract_cross_exam_target(
            result,
            questioner_name="Linus Torvalds",
            debater_names=["Linus Torvalds", "Ssyram", "康德（Immanuel Kant）"],
        )
        self.assertEqual(target, "康德（Immanuel Kant）")

    def test_extract_cross_exam_target_single_opponent_fallback(self):
        result = "下面给出综合方案，不按格式输出。"
        target = _extract_cross_exam_target(
            result,
            questioner_name="猫党代表",
            debater_names=["猫党代表", "狗党代表"],
        )
        self.assertEqual(target, "狗党代表")

    def test_extract_cross_exam_target_unique_mention_fallback(self):
        result = "我认为 Linus Torvalds 的方案有明显漏洞，需要重点质询。"
        target = _extract_cross_exam_target(
            result,
            questioner_name="Ssyram",
            debater_names=["Linus Torvalds", "Ssyram", "康德（Immanuel Kant）"],
        )
        self.assertEqual(target, "Linus Torvalds")

    def test_extract_cross_exam_target_returns_none_when_ambiguous(self):
        result = "Linus Torvalds 和 康德（Immanuel Kant）都有问题。"
        target = _extract_cross_exam_target(
            result,
            questioner_name="Ssyram",
            debater_names=["Linus Torvalds", "Ssyram", "康德（Immanuel Kant）"],
        )
        self.assertIsNone(target)


class CrossExamFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_cross_exam_collects_all_questions_before_logging(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Log(Path(tmp) / "cross_exam_log.json", "同步质询")
            log.add("Linus", "Linus round speech", flush=False)
            log.add("Ssyram", "Ssyram round speech", flush=False)
            log.add("Kant", "Kant round speech", flush=False)
            log._flush()

            debaters = [
                {"name": "Linus", "style": "style-a", "model": "m1"},
                {"name": "Ssyram", "style": "style-b", "model": "m2"},
                {"name": "Kant", "style": "style-c", "model": "m3"},
            ]

            observed_cross_exam_counts: list[int] = []

            async def fake_call_llm(model, system, user_content, **kwargs):
                observed_cross_exam_counts.append(
                    len([e for e in log.entries if e.get("tag") == "cross_exam"])
                )
                payload = json.loads(user_content) if user_content.strip().startswith("{") else {}
                questioner = payload.get("questioner", {}).get("name", "")
                target_map = {
                    "Linus": "Ssyram",
                    "Ssyram": "Kant",
                    "Kant": "Linus",
                }
                target = target_map[questioner]
                if "你的任务是先选择一个要质询的对象" in system:
                    return json.dumps({"target": target}, ensure_ascii=False)
                return json.dumps(
                    {
                        "target": target,
                        "reason": f"质询 {target}",
                        "questions": [f"{target} q1", f"{target} q2"],
                    },
                    ensure_ascii=False,
                )

            with patch("debate_tool.runner.call_llm", side_effect=fake_call_llm):
                challenged = await run_cross_exam(
                    debaters,
                    log,
                    "topic",
                    1,
                    max_reply_tokens=300,
                    timeout=30,
                    debate_base_url="http://example.invalid/v1/chat/completions",
                    debate_api_key="test-key",
                )

            self.assertEqual(len(observed_cross_exam_counts), 6)
            self.assertTrue(all(count == 0 for count in observed_cross_exam_counts))
            self.assertEqual(challenged, {"Ssyram", "Kant", "Linus"})
            self.assertEqual(len([e for e in log.entries if e.get("tag") == "cross_exam"]), 3)

    async def test_run_cross_exam_repairs_non_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Log(Path(tmp) / "cross_exam_repair_log.json", "质询修复")
            log.add("Linus", "Linus round speech", flush=False)
            log.add("Ssyram", "Ssyram round speech", flush=False)
            log.add("Kant", "Kant round speech", flush=False)
            log._flush()

            debaters = [
                {"name": "Linus", "style": "style-a", "model": "m1"},
                {"name": "Ssyram", "style": "style-b", "model": "m2"},
                {"name": "Kant", "style": "style-c", "model": "m3"},
            ]

            calls: list[tuple[str, str]] = []

            async def fake_call_llm(model, system, user_content, **kwargs):
                calls.append((model, system))
                payload = json.loads(user_content) if user_content.strip().startswith("{") else None
                questioner = payload["questioner"]["name"] if payload else "Ssyram"
                target_map = {
                    "Linus": "Ssyram",
                    "Ssyram": "Kant",
                    "Kant": "Linus",
                }
                target = target_map[questioner]

                if "你的任务是先选择一个要质询的对象" in system:
                    return json.dumps({"target": target}, ensure_ascii=False)

                if model == "m2" and "现在必须只输出一个 JSON 对象" not in system:
                    return "我先讲一下总体立场和路线图，暂不按 JSON 输出。"

                return json.dumps(
                    {
                        "target": target,
                        "reason": f"质询 {target}",
                        "questions": [f"{target} q1", f"{target} q2"],
                    },
                    ensure_ascii=False,
                )

            with patch("debate_tool.runner.call_llm", side_effect=fake_call_llm):
                challenged = await run_cross_exam(
                    debaters,
                    log,
                    "topic",
                    1,
                    max_reply_tokens=300,
                    timeout=30,
                    debate_base_url="http://example.invalid/v1/chat/completions",
                    debate_api_key="test-key",
                )

            self.assertEqual(challenged, {"Ssyram", "Kant", "Linus"})
            cross_exam_entries = [e for e in log.entries if e.get("tag") == "cross_exam"]
            self.assertEqual(len(cross_exam_entries), 3)
            self.assertFalse(any("(未解析)" in e["name"] for e in cross_exam_entries))
            self.assertTrue(any("现在必须只输出一个 JSON 对象" in system for _, system in calls))

    async def test_run_cross_exam_logs_no_opinion_when_target_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Log(Path(tmp) / "cross_exam_no_opinion_log.json", "质询无意见")
            log.add("Linus", "Linus round speech", flush=False)
            log.add("Ssyram", "Ssyram round speech", flush=False)
            log.add("Kant", "Kant round speech", flush=False)
            log._flush()

            debaters = [
                {"name": "Linus", "style": "style-a", "model": "m1"},
                {"name": "Ssyram", "style": "style-b", "model": "m2"},
                {"name": "Kant", "style": "style-c", "model": "m3"},
            ]

            async def fake_call_llm(model, system, user_content, **kwargs):
                payload = json.loads(user_content) if user_content.strip().startswith("{") else None
                questioner = payload["questioner"]["name"] if payload else ""
                if "你的任务是先选择一个要质询的对象" in system and questioner == "Ssyram":
                    return "我想质询所有人"
                if "现在必须只输出一个 JSON 对象" in system and questioner == "Ssyram":
                    return "还是不按 JSON"

                target_map = {
                    "Linus": "Ssyram",
                    "Ssyram": "Kant",
                    "Kant": "Linus",
                }
                target = target_map.get(questioner, "Ssyram")
                if "你的任务是先选择一个要质询的对象" in system:
                    return json.dumps({"target": target}, ensure_ascii=False)
                return json.dumps(
                    {
                        "target": target,
                        "reason": f"质询 {target}",
                        "questions": [f"{target} q1", f"{target} q2"],
                    },
                    ensure_ascii=False,
                )

            with patch("debate_tool.runner.call_llm", side_effect=fake_call_llm):
                challenged = await run_cross_exam(
                    debaters,
                    log,
                    "topic",
                    1,
                    max_reply_tokens=300,
                    timeout=30,
                    debate_base_url="http://example.invalid/v1/chat/completions",
                    debate_api_key="test-key",
                )

            self.assertEqual(challenged, {"Ssyram", "Linus"})
            entries = [e for e in log.entries if e.get("tag") == "cross_exam"]
            self.assertTrue(any(e["name"] == "Ssyram → (本轮没有意见)" for e in entries))


class IdentifyFilesTests(unittest.TestCase):
    def _write_valid_log(self, path: Path) -> None:
        payload = {
            "format": LOG_FORMAT,
            "version": LOG_VERSION,
            "title": "Demo",
            "topic": "",
            "initial_config": {
                "debaters": [{"name": "甲", "model": "gpt-4o-mini", "style": ""}],
                "judge": {"name": "裁判", "model": "gpt-4o-mini"},
                "constraints": "",
                "round1_task": "",
                "middle_task": "",
                "final_task": "",
                "judge_instructions": "",
                "max_reply_tokens": 6000,
                "timeout": 300,
                "cross_exam": 0,
                "early_stop": False,
                "cot": None,
                "compact_model": None,
                "compact_check_model": None,
                "compact_max_tokens": None,
                "embedding_model": None,
            },
            "created_at": "2026-03-12T00:00:00",
            "updated_at": "2026-03-12T00:00:00",
            "entries": [
                {
                    "seq": 1,
                    "ts": "2026-03-12T00:00:00",
                    "tag": "",
                    "name": "甲",
                    "content": "hello",
                }
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_identify_files_accepts_one_log_and_one_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "demo_debate_log.json"
            topic_path = tmp_path / "topic.md"
            self._write_valid_log(log_path)
            topic_path.write_text("plain text topic", encoding="utf-8")

            actual_log, actual_topic = identify_files(topic_path, log_path)

            self.assertEqual(actual_log, log_path)
            self.assertEqual(actual_topic, topic_path)

    def test_identify_files_rejects_two_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_a = tmp_path / "a_debate_log.json"
            log_b = tmp_path / "b_debate_log.json"
            self._write_valid_log(log_a)
            self._write_valid_log(log_b)

            with self.assertRaises(SystemExit):
                identify_files(log_a, log_b)

    def test_identify_files_rejects_when_no_log_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_a = tmp_path / "a.md"
            file_b = tmp_path / "b.txt"
            file_a.write_text("---\n---\nA", encoding="utf-8")
            file_b.write_text("B", encoding="utf-8")

            with self.assertRaises(SystemExit):
                identify_files(file_a, file_b)


class ConversionAndLogTests(unittest.TestCase):
    def test_standalone_converter_script_outputs_json_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            legacy_path = tmp_path / "legacy_debate_log.md"
            legacy_path.write_text(
                "# 示例 辩论日志\n\n> 2026-03-12T00:00:00\n\n---\n"
                "\n### [1] 甲\n\n*2026-03-12T00:00:01*\n\n第一轮发言\n\n---\n"
                "\n### [2] ⚖️ **裁判总结** 裁判\n\n*2026-03-12T00:00:02*\n\n总结\n\n---\n",
                encoding="utf-8",
            )

            script_path = Path(__file__).resolve().parent.parent / "scripts" / "convert_md_log_to_json.py"
            result = subprocess.run(
                [sys.executable, str(script_path), str(legacy_path)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            json_path = tmp_path / "legacy_debate_log.json"
            # The converter produces a v2-format skeleton without topic/initial_config,
            # so we read the raw JSON rather than going through Log.load_from_file().
            payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertEqual(json_path.name, "legacy_debate_log.json")
            self.assertEqual(payload["format"], LOG_FORMAT)
            self.assertEqual(payload["title"], "示例")
            entries = payload["entries"]
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[1]["tag"], "summary")

    def test_load_json_log_rejects_unknown_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_log = Path(tmp) / "bad_debate_log.json"
            bad_log.write_text(
                json.dumps({"format": "unknown", "version": 1, "entries": []}),
                encoding="utf-8",
            )

            with self.assertRaises(LogFormatError):
                Log.load_from_file(bad_log)

    def test_compact_log_keeps_json_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            topic_path = Path(tmp) / "topic.md"
            topic_path.write_text(
                "---\n"
                "title: Demo\n"
                "compact_model: gpt-4o-mini\n"
                "compact_check_model: gpt-4o-mini\n"
                "base_url: http://example.invalid/v1/chat/completions\n"
                "api_key: test-key\n"
                "debaters:\n"
                "  - name: 甲0\n"
                "    model: gpt-4o-mini\n"
                "    style: 测试立场0\n"
                "  - name: 甲1\n"
                "    model: gpt-4o-mini\n"
                "    style: 测试立场1\n"
                "  - name: 甲2\n"
                "    model: gpt-4o-mini\n"
                "    style: 测试立场2\n"
                "  - name: 甲3\n"
                "    model: gpt-4o-mini\n"
                "    style: 测试立场3\n"
                "judge:\n"
                "  name: 裁判\n"
                "  model: gpt-4o-mini\n"
                "---\n"
                "测试辩题\n",
                encoding="utf-8",
            )
            log_path = build_log_path(topic_path)
            log = Log(log_path, "Demo")
            for idx in range(4):
                log.add(f"甲{idx}", f"内容{idx}")

            async def _fake_compact_llm(model, system, user_content, **kwargs):
                # Phase A: return valid public info JSON
                if "辩论状态提取器" in system:
                    return json.dumps(
                        {
                            "topic": {"current_formulation": "测试辩题", "notes": None},
                            "axioms": [],
                            "disputes": [],
                            "pruned_paths": [],
                        },
                        ensure_ascii=False,
                    )
                # Phase B validity check: return "yes"
                if "立场校验器" in system:
                    return "yes"
                # Phase B debater stance update
                if "立场追踪器" in system:
                    import re as _re
                    m = _re.search(r"「(.+?)」", system)
                    name = m.group(1) if m else "未知"
                    return json.dumps(
                        {
                            "name": name,
                            "active": True,
                            "stance_version": 1,
                            "stance": f"{name} 测试立场",
                            "core_claims": [],
                            "key_arguments": [],
                            "abandoned_claims": [],
                        },
                        ensure_ascii=False,
                    )
                # Fallback: Phase A main call or field extraction
                return json.dumps(
                    {
                        "topic": {"current_formulation": "测试辩题", "notes": None},
                        "axioms": [],
                        "disputes": [],
                        "pruned_paths": [],
                    },
                    ensure_ascii=False,
                )

            with patch("debate_tool.runner.call_llm", side_effect=_fake_compact_llm):
                compact_log(log_path, keep_last=2, token_budget=200, topic_path=topic_path)
            reloaded = Log.load_from_file(log_path)

            self.assertTrue(any(e["tag"] == "compact_checkpoint" for e in reloaded.entries))
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["format"], LOG_FORMAT)
            self.assertEqual(payload["version"], LOG_VERSION)


class LLMCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        init_debug_logging(None)

    def test_extract_response_text_supports_multiple_shapes(self):
        content, finish = _extract_response_text(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": [
                                {"type": "output_text", "text": "Hello"},
                                {"type": "output_text", "text": " World"},
                            ]
                        },
                    }
                ]
            }
        )
        self.assertEqual(content, "Hello World")
        self.assertEqual(finish, "stop")

        content, finish = _extract_response_text(
            {"choices": [{"finish_reason": "stop", "text": "legacy-text"}]}
        )
        self.assertEqual(content, "legacy-text")
        self.assertEqual(finish, "stop")

        content, finish = _extract_response_text(
            {
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": "responses-api"}
                        ]
                    }
                ]
            }
        )
        self.assertEqual(content, "responses-api")
        self.assertIsNone(finish)

    async def test_call_llm_retries_empty_truncated_response(self):
        from debate_tool.runner import call_llm

        recorder: list[dict] = []
        fake_responses = [
            _FakeResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": ""},
                        }
                    ]
                }
            ),
            _FakeResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "Is-Match: Yes\nReasoning: ok"},
                        }
                    ]
                }
            ),
        ]

        with patch(
            "debate_tool.runner.httpx.AsyncClient",
            side_effect=lambda **kwargs: _FakeAsyncClient(fake_responses, recorder, **kwargs),
        ):
            result = await call_llm(
                "gpt-5-nano",
                "system prompt",
                "user prompt",
                max_reply_tokens=300,
                base_url="http://example.invalid/v1/chat/completions",
                api_key="test-key",
            )

        self.assertEqual(result, "Is-Match: Yes\nReasoning: ok")
        self.assertEqual(len(recorder), 2)
        self.assertEqual(recorder[0]["json"]["max_tokens"], 300)
        self.assertGreater(recorder[1]["json"]["max_tokens"], 300)


class RunAndResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_supports_cot_cross_exam_and_optional_middle_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            topic_path = tmp_path / "topic.md"
            topic_path.write_text(
                """---
title: Test Debate
rounds: 3
cross_exam: 1
cot: true
middle_task_optional: true
base_url: http://example.invalid/v1/chat/completions
api_key: test-key
debaters:
  - name: 甲
    model: gpt-4o-mini
    style: 支持猫
  - name: 乙
    model: gpt-4o-mini
    style: 支持狗
  - name: 丙
    model: gpt-4o-mini
    style: 中立
judge:
  name: 裁判
  model: gpt-4o-mini
  base_url: http://example.invalid/v1/chat/completions
  api_key: test-key
round1_task: 第一轮任务
middle_task: 中间任务
final_task: 最终任务
---
猫和狗谁更好？
""",
                encoding="utf-8",
            )

            cfg = parse_topic_file(topic_path)
            calls: list[dict] = []

            async def fake_call_llm(model, system, user_content, **kwargs):
                calls.append({"model": model, "system": system, "user": user_content})
                if "现在进入质询环节" in system:
                    # Extract the expected target from the system prompt
                    import re as _re
                    m = _re.search(r'target 必须是\s*(.+?)，', system)
                    tgt = m.group(1).strip() if m else "乙"
                    return json.dumps(
                        {"target": tgt, "reason": "质询理由", "questions": ["问题1", "问题2"]},
                        ensure_ascii=False,
                    )
                if system.startswith("你是辩论裁判"):
                    return "最终结论：猫狗各有优势。"
                # Cross-exam target selection prompt (select_prompt): contains "你是「" but no round marker
                if "你是「" in system and "第 " not in system:
                    name = system.split("你是「", 1)[1].split("」", 1)[0]
                    # All debaters select 乙; 乙 selects itself (invalid → no_opinion)
                    if name == "乙":
                        return json.dumps({"target": "乙"}, ensure_ascii=False)
                    return json.dumps({"target": "乙"}, ensure_ascii=False)
                # Fallback for any unrecognized system prompts (retry/repair prompts)
                if "你是「" not in system:
                    return json.dumps({"target": "乙", "reason": "理由", "questions": ["q1", "q2"]}, ensure_ascii=False)

                name = system.split("你是「", 1)[1].split("」", 1)[0]
                round_no = int(system.split("第 ", 1)[1].split(" 轮", 1)[0])
                return f"<thinking>{name}-thought-r{round_no}</thinking>{name}-reply-r{round_no}"

            with patch("debate_tool.runner.call_llm", side_effect=fake_call_llm):
                await run(cfg, topic_path)

            log_path = build_log_path(topic_path)
            self.assertTrue(log_path.exists())
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            tags = [entry["tag"] for entry in payload["entries"]]
            self.assertIn("thinking", tags)
            self.assertIn("cross_exam", tags)
            self.assertIn("summary", tags)

            log = Log.load_from_file(log_path)
            self.assertNotIn("thought-r1", log.since(0))

            round2_prompts = {
                call["system"].split("你是「", 1)[1].split("」", 1)[0]: call
                for call in calls
                if "第 2 轮" in call["system"] and "你是「" in call["system"]
            }
            self.assertIn("逐条回应你收到的每一个质询", round2_prompts["乙"]["system"])
            self.assertNotIn("【推进任务（可选）】", round2_prompts["乙"]["system"])
            self.assertIn("本轮无人向你提出质询", round2_prompts["甲"]["system"])
            self.assertIn("本轮无人向你提出质询", round2_prompts["丙"]["system"])
            self.assertNotIn("thought-r1", round2_prompts["乙"]["user"])

    async def test_resume_appends_human_cross_exam_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            topic_path = tmp_path / "resume_topic.md"
            topic_path.write_text(
                """---
title: Resume Debate
rounds: 1
base_url: http://example.invalid/v1/chat/completions
api_key: test-key
debaters:
  - name: 猫党
    model: gpt-4o-mini
    style: 支持猫
  - name: 狗党
    model: gpt-4o-mini
    style: 支持狗
judge:
  name: 裁判
  model: gpt-4o-mini
  base_url: http://example.invalid/v1/chat/completions
  api_key: test-key
---
猫狗辩题
""",
                encoding="utf-8",
            )

            cfg = parse_topic_file(topic_path)
            calls: list[dict] = []

            async def fake_call_llm(model, system, user_content, **kwargs):
                calls.append({"model": model, "system": system, "user": user_content})
                if "现在进入质询环节" in system:
                    import re as _re
                    m = _re.search(r'target 必须是\s*(.+?)，', system)
                    tgt = m.group(1).strip() if m else "狗党"
                    return json.dumps(
                        {"target": tgt, "reason": "质询理由", "questions": ["问题1", "问题2"]},
                        ensure_ascii=False,
                    )
                if system.startswith("你是辩论裁判"):
                    return "裁判总结完成"
                # Cross-exam target selection prompt: contains "你是「" but no round marker
                if "你是「" in system and "第 " not in system:
                    name = system.split("你是「", 1)[1].split("」", 1)[0]
                    target_map = {"猫党": "狗党", "狗党": "猫党"}
                    return json.dumps({"target": target_map.get(name, "狗党")}, ensure_ascii=False)
                # Fallback for unrecognized repair/retry prompts
                if "你是「" not in system:
                    return json.dumps({"target": "狗党", "reason": "理由", "questions": ["q1", "q2"]}, ensure_ascii=False)
                name = system.split("你是「", 1)[1].split("」", 1)[0]
                return f"{name} 发言"

            with patch("debate_tool.runner.call_llm", side_effect=fake_call_llm):
                await run(cfg, topic_path)
                await resume(
                    log_path=build_log_path(topic_path),
                    message="请补充安全性",
                    extra_rounds=2,
                    cross_exam=1,
                    guide_prompt="重点看安全",
                )

            log = Log.load_from_file(build_log_path(topic_path))
            tags = [entry["tag"] for entry in log.entries]
            self.assertIn("human", tags)
            self.assertIn("cross_exam", tags)
            self.assertIn("summary", tags)
            self.assertTrue(any(entry["tag"] == "human" and "请补充安全性" in entry["content"] for entry in log.entries))
            self.assertTrue(any("观察者指引：重点看安全" in call["system"] for call in calls if "续跑" in call["system"]))


class CliOptionTests(unittest.TestCase):
        def test_run_dry_run_reports_cli_overrides(self):
                with tempfile.TemporaryDirectory() as tmp:
                        topic_path = Path(tmp) / "cli_topic.md"
                        topic_path.write_text(
                                """---
title: CLI Topic
rounds: 1
cross_exam: 0
early_stop: false
base_url: http://example.invalid/v1/chat/completions
api_key: test-key
debaters:
    - name: 甲
        model: gpt-4o-mini
        style: 支持猫
    - name: 乙
        model: gpt-4o-mini
        style: 支持狗
judge:
    name: 裁判
    model: gpt-4o-mini
    base_url: http://example.invalid/v1/chat/completions
    api_key: test-key
---
测试 CLI 覆盖
""",
                                encoding="utf-8",
                        )

                        stdout = io.StringIO()
                        with redirect_stdout(stdout):
                            with patch.object(
                                sys,
                                "argv",
                                [
                                    "debate-tool",
                                    "run",
                                    str(topic_path),
                                    "--dry-run",
                                    "--rounds",
                                    "4",
                                    "--cross-exam",
                                    "2",
                                    "--early-stop",
                                    "0.6",
                                    "--cot",
                                    "120",
                                ],
                            ):
                                cli_main()

                        out = stdout.getvalue()
                        self.assertIn("轮数:     4", out)
                        self.assertIn("质询:     R1~R2 后", out)
                        self.assertIn("早停:     是 (阈值 60%)", out)
                        self.assertIn("CoT:      是 (思考预算 120 token)", out)


class TopicConsistencyCheckTests(unittest.IsolatedAsyncioTestCase):
    # check_topic_log_consistency_with_llm was removed in the v2 refactor.
    # The replacement is validate_topic_log_consistency(log, force=False) which
    # only emits warnings and never raises SystemExit.

    async def test_validate_topic_log_consistency_no_error_when_consistent(self):
        """validate_topic_log_consistency should not raise for a consistent log."""
        from debate_tool.runner import validate_topic_log_consistency
        from debate_tool import core as _core

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            topic_path = tmp_path / "consistency_topic.md"
            topic_path.write_text(
                """---
title: 猫狗辩题
rounds: 1
base_url: http://example.invalid/v1/chat/completions
api_key: test-key
debaters:
  - name: 甲
    model: gpt-4o-mini
    style: 支持猫
  - name: 乙
    model: gpt-4o-mini
    style: 支持狗
judge:
  name: 裁判
  model: gpt-4o-mini
  base_url: http://example.invalid/v1/chat/completions
  api_key: test-key
---
猫和狗哪个更适合作为宠物？
""",
                encoding="utf-8",
            )

            cfg = parse_topic_file(topic_path)
            log_path = build_log_path(topic_path)
            initial_config = _core._build_initial_config(cfg)
            log = Log(log_path, "猫狗辩题", initial_config=initial_config)
            log.add("甲", "猫是最好的宠物选择", "debater")
            log.add("乙", "狗也不错", "debater")

            # Should not raise
            validate_topic_log_consistency(log, force=False)

    async def test_validate_topic_log_consistency_force_skips_all_checks(self):
        """validate_topic_log_consistency(force=True) must return immediately."""
        from debate_tool.runner import validate_topic_log_consistency

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "force_debate_log.json"
            log = Log(log_path, "完全不同的话题")
            log.add("甲", "这是关于完全不同话题的发言")

            # force=True must never raise
            validate_topic_log_consistency(log, force=True)

    async def test_validate_topic_log_consistency_warns_on_mismatch(self):
        """validate_topic_log_consistency should print warnings but not exit."""
        import io as _io
        from debate_tool.runner import validate_topic_log_consistency
        from debate_tool import core as _core

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            topic_path = tmp_path / "mismatch_topic.md"
            topic_path.write_text(
                """---
title: 猫狗辩题
rounds: 1
base_url: http://example.invalid/v1/chat/completions
api_key: test-key
debaters:
  - name: 甲
    model: gpt-4o-mini
    style: 支持猫
  - name: 乙
    model: gpt-4o-mini
    style: 支持狗
judge:
  name: 裁判
  model: gpt-4o-mini
  base_url: http://example.invalid/v1/chat/completions
  api_key: test-key
---
猫和狗哪个更适合作为宠物？
""",
                encoding="utf-8",
            )

            cfg = parse_topic_file(topic_path)
            log_path = build_log_path(topic_path)
            initial_config = _core._build_initial_config(cfg)
            # Log contains an unexpected debater 丙 (not in the config)
            log = Log(log_path, "猫狗辩题", initial_config=initial_config)
            log.add("丙", "我是不在计划里的辩手", "debater")

            stderr_capture = _io.StringIO()
            with patch("sys.stderr", stderr_capture):
                # Should not raise, but should write a warning to stderr
                validate_topic_log_consistency(log, force=False)

            # A warning should have been emitted
            self.assertIn("⚠️", stderr_capture.getvalue())


class LogSchemaV2Tests(unittest.TestCase):
    def test_v2_log_contains_topic_and_initial_config(self):
        """新建 Log 并 flush，确认写入文件包含 topic 和 initial_config"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_debate_log.json"
            initial_config = {
                "debaters": [{"name": "A", "model": "gpt-4o-mini", "style": "支持"}],
                "judge": {"name": "裁判", "model": "gpt-4o-mini"},
                "constraints": "",
                "round1_task": "",
                "middle_task": "回应对方",
                "final_task": "",
                "judge_instructions": "",
                "max_reply_tokens": 800,
                "timeout": 60,
                "cross_exam": 0,
                "early_stop": False,
                "cot": None,
                "compact_model": None,
                "compact_check_model": None,
                "compact_max_tokens": None,
                "embedding_model": None,
            }
            log = Log(path, "测试辩论", topic="辩题正文", initial_config=initial_config)
            log.add("A", "发言内容")
            payload = json.loads(path.read_text())
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["topic"], "辩题正文")
            self.assertIn("initial_config", payload)
            self.assertEqual(payload["initial_config"]["middle_task"], "回应对方")

    def test_v1_log_load_exits_with_error(self):
        """v1 格式 log 加载时应 sys.exit(1)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "v1_debate_log.json"
            v1_payload = {
                "format": "debate-tool-log",
                "version": 1,
                "title": "旧格式",
                "entries": [],
            }
            path.write_text(json.dumps(v1_payload))
            with self.assertRaises(SystemExit):
                Log.load_from_file(path)


class ResolveEffectiveConfigTests(unittest.TestCase):
    def _make_log(self, tmpdir, initial_config=None):
        path = Path(tmpdir) / "test_debate_log.json"
        cfg = initial_config or {
            "debaters": [
                {"name": "A", "model": "gpt-4o-mini", "style": "正方"},
                {"name": "B", "model": "gpt-4o-mini", "style": "反方"},
            ],
            "judge": {"name": "J", "model": "gpt-4o-mini"},
            "constraints": "原始约束",
            "round1_task": "", "middle_task": "原始任务", "final_task": "",
            "judge_instructions": "", "max_reply_tokens": 800, "timeout": 60,
            "cross_exam": 0, "early_stop": False, "cot": None,
            "compact_model": None, "compact_check_model": None,
            "compact_max_tokens": None, "embedding_model": None,
        }
        log = Log(path, "test", topic="辩题", initial_config=cfg)
        return log

    def test_no_overrides_returns_initial_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self._make_log(tmpdir)
            eff = resolve_effective_config(log)
            self.assertEqual(eff["middle_task"], "原始任务")
            self.assertEqual(len(eff["debaters"]), 2)

    def test_single_override_merges_correctly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self._make_log(tmpdir)
            log.add("@系统", "更新 middle_task", "config_override",
                    extra={"overrides": {"middle_task": "新任务"}})
            eff = resolve_effective_config(log)
            self.assertEqual(eff["middle_task"], "新任务")

    def test_multiple_overrides_accumulate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self._make_log(tmpdir)
            log.add("@系统", "更新约束", "config_override",
                    extra={"overrides": {"constraints": "新约束"}})
            log.add("@系统", "更新任务", "config_override",
                    extra={"overrides": {"middle_task": "最新任务"}})
            eff = resolve_effective_config(log)
            self.assertEqual(eff["constraints"], "新约束")
            self.assertEqual(eff["middle_task"], "最新任务")

    def test_add_and_drop_debaters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self._make_log(tmpdir)
            log.add("@系统", "加入C", "config_override",
                    extra={"overrides": {"add_debaters": [{"name": "C", "model": "gpt-4o-mini", "style": "中立"}]}})
            log.add("@系统", "移除A", "config_override",
                    extra={"overrides": {"drop_debaters": ["A"]}})
            eff = resolve_effective_config(log)
            names = {d["name"] for d in eff["debaters"]}
            self.assertIn("B", names)
            self.assertIn("C", names)
            self.assertNotIn("A", names)

    def test_judge_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self._make_log(tmpdir)
            log.add("@系统", "更新裁判", "config_override",
                    extra={"overrides": {"judge": {"model": "claude-opus-4-6"}}})
            eff = resolve_effective_config(log)
            self.assertEqual(eff["judge"]["model"], "claude-opus-4-6")
            self.assertEqual(eff["judge"]["name"], "J")  # 未覆盖的字段保留


class ResumeTopicParseTests(unittest.TestCase):
    def test_yaml_frontmatter_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "phase2.md"
            p.write_text("---\nmiddle_task: 新任务\nrounds: 3\n---\n\n观察者消息正文", encoding="utf-8")
            overrides, body = parse_resume_topic(p)
            # rounds 仍在 overrides 中（调用方负责 pop）
            self.assertEqual(overrides.get("rounds"), 3)
            self.assertEqual(overrides.get("middle_task"), "新任务")
            self.assertEqual(body, "观察者消息正文")

    def test_empty_body_returns_empty_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "no_body.md"
            p.write_text("---\nconstraints: 只做判断\n---\n", encoding="utf-8")
            overrides, body = parse_resume_topic(p)
            self.assertEqual(body, "")
            self.assertEqual(overrides["constraints"], "只做判断")

    def test_add_drop_debaters_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "phase3.md"
            content = "---\nadd_debaters:\n  - name: C\n    model: gpt-4o-mini\n    style: 中立\ndrop_debaters:\n  - A\n---\n"
            p.write_text(content, encoding="utf-8")
            overrides, _ = parse_resume_topic(p)
            self.assertEqual(len(overrides["add_debaters"]), 1)
            self.assertEqual(overrides["add_debaters"][0]["name"], "C")
            self.assertEqual(overrides["drop_debaters"], ["A"])

    def test_no_frontmatter_returns_empty_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "plain.md"
            p.write_text("只有消息正文，没有 front-matter", encoding="utf-8")
            overrides, body = parse_resume_topic(p)
            self.assertEqual(overrides, {})
            self.assertIn("只有消息正文", body)


class BuildInitialConfigTests(unittest.TestCase):
    def test_api_key_excluded_base_url_kept(self):
        from debate_tool.core import _build_initial_config
        cfg = {
            "debaters": [{"name": "A", "model": "gpt-4o-mini", "style": "s",
                          "base_url": "http://localhost:8081/v1/chat/completions",
                          "api_key": "secret-key"}],
            "judge": {"name": "J", "model": "gpt-4o-mini",
                      "base_url": "http://api.example.com", "api_key": "judge-secret"},
            "constraints": "", "round1_task": "", "middle_task": "task",
            "final_task": "", "judge_instructions": "",
            "max_reply_tokens": 800, "timeout": 60, "cross_exam": 0,
            "early_stop": False, "cot_length": None,
            "compact_model": None, "compact_check_model": None,
            "compact_max_tokens": None, "embedding_model": None,
        }
        ic = _build_initial_config(cfg)
        # api_key 排除
        self.assertNotIn("api_key", ic["debaters"][0])
        self.assertNotIn("api_key", ic["judge"])
        # base_url 保留
        self.assertEqual(ic["debaters"][0]["base_url"], "http://localhost:8081/v1/chat/completions")
        self.assertEqual(ic["judge"]["base_url"], "http://api.example.com")
        # compact 字段存在
        self.assertIn("compact_model", ic)


class MigrationScriptTests(unittest.TestCase):
    def test_v1_to_v2_migration(self):
        """迁移脚本将 v1 log 转为 v2，topic 和 initial_config 正确注入"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 复制 test_edo.md 和构造一个假的 v1 log
            topic_src = Path("/Users/ssyram/workspace/github/debate/test_edo.md")
            topic_dst = Path(tmpdir) / "test_edo.md"
            topic_dst.write_text(topic_src.read_text(encoding="utf-8"), encoding="utf-8")

            v1_log = {
                "format": "debate-tool-log",
                "version": 1,
                "title": "江户幕府测试",
                "entries": [{"seq": 1, "ts": "2026-01-01T00:00:00", "tag": "", "name": "偶然派", "content": "发言"}],
            }
            log_path = Path(tmpdir) / "test_debate_log.json"
            log_path.write_text(json.dumps(v1_log), encoding="utf-8")

            out_path = Path(tmpdir) / "test_v2.json"
            result = subprocess.run(
                ["python3", "scripts/migrate_v1_to_v2.py",
                 str(topic_dst), str(log_path), "--output", str(out_path)],
                capture_output=True, text=True,
                cwd="/Users/ssyram/workspace/github/debate"
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            v2 = json.loads(out_path.read_text())
            self.assertEqual(v2["version"], 2)
            self.assertIn("topic", v2)
            self.assertIn("initial_config", v2)
            # api_key 不在 initial_config
            for d in v2["initial_config"]["debaters"]:
                self.assertNotIn("api_key", d)


class DescribeOverridesTests(unittest.TestCase):
    def test_describe_empty(self):
        result = _describe_overrides({})
        self.assertEqual(result, "配置变更")

    def test_describe_middle_task(self):
        result = _describe_overrides({"middle_task": "新任务"})
        self.assertIn("middle_task", result)

    def test_describe_add_debaters(self):
        result = _describe_overrides({"add_debaters": [{"name": "C", "model": "m", "style": "s"}]})
        self.assertIn("C", result)

    def test_describe_drop_debaters(self):
        result = _describe_overrides({"drop_debaters": ["A", "B"]})
        self.assertIn("A", result)
