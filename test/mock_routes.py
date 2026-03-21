"""Mock route table for debate-tool tests.

Design:
  1. On init, scan all test/topics/*.md files, parse YAML `mock_responses` field
  2. On each request, decode prompt → extract (name, round, call_type) → look up table
  3. Topic files are self-contained: mock data lives next to debate config

Topic YAML format (extra field, ignored by production code):

    mock_responses:
      debaters:
        正方:
          1: "R1 发言..."
          2: "R2 发言..."
        反方:
          1: "R1 发言..."
          2: "R2 发言..."
      judge: "裁定：..."
      cx_select:
        乐观派: "谨慎派"     # questioner → target name
      cx_questions:
        乐观派:
          - "问题1？"
          - "问题2？"
      cot_thinking:          # optional CoT thinking content
        实用派:
          1: "thinking text..."

Prompt patterns (from production code, NOT modified):
  Debater sys:  "你是「{name}」，风格为「{style}」。第 {rnd} 轮。"
  Judge sys:    "你是辩论裁判（{name}），负责做出最终裁定。"
  CX select:    "选择一个要质询的对象"
  CX question:  "质询环节" + JSON target/reason/questions
  CX retry:     "你上次输出不合规"
  CX form:      "质询填表助手"
  CX fallback:  "攻击哪位辩手" / "为什么要质疑" / "你想问他什么问题"
  CoT:          "<thinking>" in system
  CoT recovery: "补全任务"
  Compact:      state extraction / validity / drift / correction / tracker
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

# ═══════════════════════════════════════════════════════════════
#  Table loading from topic files
# ═══════════════════════════════════════════════════════════════

# Global tables, populated by load_routes()
_debater_table: dict[tuple[str, int], str] = {}    # (name, round) → speech
_cot_table: dict[tuple[str, int], str] = {}         # (name, round) → thinking
_judge_table: dict[str, str] = {}                    # first_debater_name → verdict
_cx_select_table: dict[str, str] = {}               # questioner → target
_cx_questions_table: dict[str, list[str]] = {}       # questioner → questions
_known_debater_names: set[str] = set()               # all debater names across all topics
_compact_phase_a_table: dict[str, str | list[str]] = {}
_compact_phase_b_table: dict[tuple[str, str], str | list[str]] = {}
# Per-topic validity/drift responses keyed by first_debater name
_compact_validity_table: dict[str, str | list[str]] = {}
_compact_drift_table: dict[str, str | list[str]] = {}
_debater_to_topic: dict[str, str] = {}  # debater_name → first_debater (topic key)

# ── Per-route call counter for sequence cycling ──────────────
_call_counter: dict[str, int] = {}


def reset_call_counters():
    _call_counter.clear()


def _seq_pick(val: "str | list[str]", counter_key: str) -> str:
    """Pick response from a string or a list (cycling by call count)."""
    if isinstance(val, list):
        idx = _call_counter.get(counter_key, 0)
        _call_counter[counter_key] = idx + 1
        return val[idx] if idx < len(val) else val[-1]
    _call_counter[counter_key] = _call_counter.get(counter_key, 0) + 1
    return val


def load_routes(topics_dir: Path | None = None):
    """Scan topic .md files and build route tables from mock_responses YAML field.

    Call once before tests start. Safe to call multiple times (tables are reset).
    Also scans test/resume_topics/ for resume topic mock data.
    """
    global _debater_table, _cot_table, _judge_table
    global _cx_select_table, _cx_questions_table, _known_debater_names
    global _compact_phase_a_table, _compact_phase_b_table
    global _compact_validity_table, _compact_drift_table

    _debater_table.clear()
    _cot_table.clear()
    _judge_table.clear()
    _cx_select_table.clear()
    _cx_questions_table.clear()
    _known_debater_names.clear()
    _compact_phase_a_table.clear()
    _compact_phase_b_table.clear()
    _compact_validity_table.clear()
    _compact_drift_table.clear()
    _debater_to_topic.clear()

    if topics_dir is None:
        topics_dir = Path(__file__).parent / "topics"

    for md_file in sorted(topics_dir.glob("*.md")):
        if md_file.name.endswith("_debate_summary.md"):
            continue
        _load_topic(md_file)

    # Also load resume topics
    resume_dir = Path(__file__).parent / "resume_topics"
    if resume_dir.is_dir():
        for md_file in sorted(resume_dir.glob("*.md")):
            _load_topic(md_file)


def _parse_front_matter(text: str) -> dict:
    """Extract YAML front-matter dict from markdown text."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        raw = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _load_topic(path: Path):
    """Load one topic file's mock_responses into global tables."""

    text = path.read_text(encoding="utf-8")
    front = _parse_front_matter(text)
    mock = front.get("mock_responses")
    if not isinstance(mock, dict):
        return

    # Debater names from this topic (for judge routing)
    debaters_cfg = front.get("debaters", [])
    first_debater = ""
    if isinstance(debaters_cfg, list) and debaters_cfg:
        first_debater = debaters_cfg[0].get("name", "") if isinstance(debaters_cfg[0], dict) else ""
        for d in debaters_cfg:
            if isinstance(d, dict) and d.get("name"):
                _known_debater_names.add(d["name"])

    # Also register add_debaters names
    add_debaters = front.get("add_debaters", [])
    if isinstance(add_debaters, list):
        for d in add_debaters:
            if isinstance(d, dict) and d.get("name"):
                _known_debater_names.add(d["name"])

    # Load debater speeches
    debaters_mock = mock.get("debaters", {})
    if isinstance(debaters_mock, dict):
        for name, rounds in debaters_mock.items():
            if isinstance(rounds, dict):
                for rnd, text_val in rounds.items():
                    _debater_table[(str(name), int(rnd))] = str(text_val)
            elif isinstance(rounds, str):
                # Single string = all rounds same
                _debater_table[(str(name), 1)] = rounds

    # Load CoT thinking
    cot_mock = mock.get("cot_thinking", {})
    if isinstance(cot_mock, dict):
        for name, rounds in cot_mock.items():
            if isinstance(rounds, dict):
                for rnd, text_val in rounds.items():
                    _cot_table[(str(name), int(rnd))] = str(text_val)

    # Load judge verdict
    judge_mock = mock.get("judge")
    if isinstance(judge_mock, str) and first_debater:
        _judge_table[first_debater] = judge_mock

    # Load CX select
    cx_sel = mock.get("cx_select", {})
    if isinstance(cx_sel, dict):
        for questioner, target in cx_sel.items():
            _cx_select_table[str(questioner)] = str(target)

    # Load CX questions
    cx_q = mock.get("cx_questions", {})
    if isinstance(cx_q, dict):
        for questioner, questions in cx_q.items():
            if isinstance(questions, list):
                _cx_questions_table[str(questioner)] = [str(q) for q in questions]

    compact_mock = mock.get("compact", {})
    if isinstance(compact_mock, dict):
        phase_a = compact_mock.get("phase_a")
        if phase_a is not None and first_debater:
            if isinstance(phase_a, (str, list)):
                _compact_phase_a_table[first_debater] = phase_a
        phase_b = compact_mock.get("phase_b", {})
        if isinstance(phase_b, dict) and first_debater:
            for dname, resp in phase_b.items():
                _debater_to_topic[str(dname)] = first_debater
                if isinstance(resp, list):
                    _compact_phase_b_table[(first_debater, str(dname))] = resp
                else:
                    _compact_phase_b_table[(first_debater, str(dname))] = str(resp)
        v = compact_mock.get("validity_check")
        if v is not None and first_debater:
            if isinstance(v, (str, list)):
                _compact_validity_table[first_debater] = v
        d = compact_mock.get("drift_check")
        if d is not None and first_debater:
            if isinstance(d, (str, list)):
                _compact_drift_table[first_debater] = d


# ═══════════════════════════════════════════════════════════════
#  Prompt decoders
# ═══════════════════════════════════════════════════════════════

_DEBATER_RE = re.compile(r"你是「(.+?)」，风格为「(.+?)」。第\s*(\d+)\s*轮")
_JUDGE_RE = re.compile(r"你是辩论裁判（(.+?)）")
_OPPONENTS_RE = re.compile(r"target\s*必须是以下之一[：:]\s*(.+)")
_CX_TARGET_IN_SYS = re.compile(r'"target":\s*"(.+?)"')


def _decode_debater(system: str):
    """→ (name, style, round) or None"""
    m = _DEBATER_RE.search(system)
    return (m.group(1), m.group(2), int(m.group(3))) if m else None


def _decode_judge(system: str):
    m = _JUDGE_RE.search(system)
    return m.group(1) if m else None


def _extract_opponents(system: str) -> list[str]:
    m = _OPPONENTS_RE.search(system)
    if not m:
        return []
    raw = m.group(1).strip()
    parts = [n.strip() for n in raw.split("、") if n.strip()]
    return parts or [n.strip() for n in raw.split(",") if n.strip()]


def _extract_questioner(system: str) -> str:
    m = re.search(r"你是[辩手]*「(.+?)」", system)
    return m.group(1) if m else ""


def _classify(system: str) -> str:
    """Classify the call type from system prompt keywords. Order matters."""
    if "补全任务" in system and "已完成的思考内容" in system:
        return "cot_recovery"
    if "攻击哪位辩手" in system:
        return "cx_fb_select"
    if "为什么要质疑" in system:
        return "cx_fb_reason"
    if "你想问他什么问题" in system:
        return "cx_fb_question"
    if "质询填表助手" in system:
        return "cx_form"
    if "你上次输出不合规" in system:
        return "cx_question_repair" if ("reason" in system or "questions" in system) else "cx_select_retry"
    if "选择一个要质询的对象" in system:
        return "cx_select"
    if "质询环节" in system:
        return "cx_question"
    if "辩论状态提取器" in system:
        if "只输出要求的 JSON 字段" in system:
            return "compact.phase_a.fetch"
        return "compact.phase_a"
    if "辩论立场校验器" in system:
        return "compact.validity_check"
    if "辩论立场漂移检查器" in system:
        return "compact.drift_check"
    if "投敌" in system and "修正立场" in system:
        return "compact.correction"
    if "立场追踪器" in system:
        return "compact.phase_b"
    if _JUDGE_RE.search(system):
        return "judge"
    if _DEBATER_RE.search(system):
        return "debater_cot" if "<thinking>" in system else "debater"
    return "unknown"


def _find_topic_key_in_text(text: str) -> str | None:
    """Find the topic key (first_debater) by scanning text for any known debater name."""
    for dname, topic_key in _debater_to_topic.items():
        if dname in text:
            return topic_key
    return None


# ═══════════════════════════════════════════════════════════════
#  Main router
# ═══════════════════════════════════════════════════════════════

def match_route(system: str, user: str, model: str) -> tuple[str | None, str]:
    """Match request → (route_name, response_text). Returns (None, "") on miss."""
    call_type = _classify(system)

    # ── Debater ──
    if call_type == "debater":
        info = _decode_debater(system)
        if not info:
            return None, ""
        name, style, rnd = info
        text = _debater_table.get((name, rnd))
        if text is None:
            text = f"作为{name}，在第{rnd}轮，我坚持自己的立场并提出论据支持。"
        return "debater", text

    # ── Debater + CoT ──
    if call_type == "debater_cot":
        info = _decode_debater(system)
        if not info:
            return None, ""
        name, style, rnd = info
        thinking = _cot_table.get((name, rnd), f"分析议题，准备第{rnd}轮论点。")
        speech = _debater_table.get((name, rnd), f"经过深思，我的立场是明确且合理的。")
        return "debater.cot", f"<thinking>{thinking}</thinking>{speech}"

    # ── Judge ──
    if call_type == "judge":
        judge_name = _decode_judge(system)
        if not judge_name:
            return None, ""
        # Find topic by scanning user content for known debater names
        for first_debater, verdict in _judge_table.items():
            if first_debater in user:
                return "judge", verdict
        return "judge", "裁定：双方均有合理论据，综合各方观点，辩论结果公正。"

    # ── CX select ──
    if call_type == "cx_select":
        questioner = _extract_questioner(system)
        opponents = _extract_opponents(system)
        target = _cx_select_table.get(questioner, opponents[0] if opponents else "对手")
        return "cx.select", json.dumps({"target": target}, ensure_ascii=False)

    # ── CX select retry ──
    if call_type == "cx_select_retry":
        m = re.search(r"候选 target[：:]\s*(.+)", user)
        if m:
            opponents = [n.strip() for n in re.split(r"[、,]", m.group(1)) if n.strip()]
        else:
            opponents = ["对手"]
        return "cx.select.retry", json.dumps({"target": opponents[0]}, ensure_ascii=False)

    # ── CX question ──
    if call_type == "cx_question":
        questioner = _extract_questioner(system)
        m = _CX_TARGET_IN_SYS.search(system)
        target = m.group(1) if m else "对手"
        questions = _cx_questions_table.get(questioner, [f"请{target}进一步解释论据。", f"是否有数据支撑？"])
        payload = {"target": target, "reason": f"对{target}的论点存在疑问", "questions": questions}
        return "cx.question", json.dumps(payload, ensure_ascii=False, indent=2)

    # ── CX question repair ──
    if call_type == "cx_question_repair":
        return "cx.question.repair", json.dumps({
            "target": "对手", "reason": "论点需要验证",
            "questions": ["请提供更多证据。"],
        }, ensure_ascii=False, indent=2)

    # ── CX form ──
    if call_type == "cx_form":
        questioner = _extract_questioner(system)
        opponents = _extract_opponents(system)
        target = opponents[0] if opponents else "对手"
        return "cx.form", json.dumps({
            "target": target, "reason": f"质疑{target}的论证",
            "questions": [f"请{target}提供数据支持。"],
        }, ensure_ascii=False, indent=2)

    # ── CX fallback ──
    if call_type == "cx_fb_select":
        return "cx.fb.select", "1"

    if call_type == "cx_fb_reason":
        m = re.search(r"「(.+?)」的发言记录", system)
        target = m.group(1) if m else "对手"
        return "cx.fb.reason", f"我质疑{target}的论点缺乏实证支持。"

    if call_type == "cx_fb_question":
        return "cx.fb.question", "请提供具体数据来支持你的论点。"

    # ── CoT recovery ──
    if call_type == "cot_recovery":
        return "cot.recovery", "基于以上分析，应采取务实方案，兼顾各方利益。"

    if call_type == "compact.phase_a":
        for first_debater, pa_json in _compact_phase_a_table.items():
            if first_debater in user:
                return "compact.phase_a", _seq_pick(pa_json, "compact.phase_a")
        return "compact.phase_a", json.dumps({
            "topic": {"current_formulation": "测试议题", "notes": None},
            "axioms": [], "disputes": [], "pruned_paths": []
        }, ensure_ascii=False)

    if call_type == "compact.phase_a.fetch":
        m = re.search(r"请提取「(.+?)」字段", user)
        field_name = m.group(1) if m else "topic"
        if field_name == "topic":
            return "compact.phase_a.fetch.topic", json.dumps(
                {"current_formulation": "测试议题", "notes": None}, ensure_ascii=False)
        if field_name == "axioms":
            return "compact.phase_a.fetch.axioms", '[]'
        if field_name == "disputes":
            return "compact.phase_a.fetch.disputes", '[]'
        if field_name == "pruned_paths":
            return "compact.phase_a.fetch.pruned_paths", '[]'
        return "compact.phase_a.fetch", '[]'

    if call_type == "compact.phase_b":
        m = re.search(r"你是辩手「(.+?)」的立场追踪器", system)
        debater_name = m.group(1) if m else ""
        for (fd, dn), resp in _compact_phase_b_table.items():
            if dn == debater_name:
                return "compact.phase_b", _seq_pick(resp, f"compact.phase_b.{dn}")
        return "compact.phase_b", json.dumps({
            "name": debater_name or "未知辩手", "active": True, "stance_version": 1,
            "stance": "维持原有立场。", "core_claims": [{"id": "C1", "text": "基本主张", "status": "active"}],
            "key_arguments": [{"id": "A1", "claim_id": "C1", "text": "基本论据", "status": "active"}],
            "abandoned_claims": []
        }, ensure_ascii=False)

    if call_type == "compact.validity_check":
        topic_key = _find_topic_key_in_text(user)
        if topic_key and topic_key in _compact_validity_table:
            return "compact.validity_check", _seq_pick(
                _compact_validity_table[topic_key], f"compact.validity_check.{topic_key}")
        return "compact.validity_check", "YES"

    if call_type == "compact.drift_check":
        topic_key = _find_topic_key_in_text(user) or _find_topic_key_in_text(system)
        if topic_key and topic_key in _compact_drift_table:
            return "compact.drift_check", _seq_pick(
                _compact_drift_table[topic_key], f"compact.drift_check.{topic_key}")
        return "compact.drift_check", "REFINEMENT\n合理细化，立场未发生根本倒转。"

    if call_type == "compact.correction":
        m = re.search(r"你是辩手「(.+?)」", system)
        debater_name = m.group(1) if m else ""
        for (fd, dn), resp in _compact_phase_b_table.items():
            if dn == debater_name:
                return "compact.correction", _seq_pick(resp, f"compact.correction.{dn}")
        return "compact.correction", json.dumps({
            "name": debater_name or "未知辩手", "active": True, "stance_version": 1,
            "stance": "修正后的立场。", "core_claims": [], "key_arguments": [], "abandoned_claims": []
        }, ensure_ascii=False)

    if call_type == "unknown" and not system.strip():
        if "你是辩手「" in user:
            if "请填写" in user or "请告诉我" in user or "请列出" in user:
                return "compact.fillForm", "维持现有立场，无新增主张。"
            if "还有下一条" in user:
                return "compact.fillForm.next", "没有"
            return "compact.fillForm", "基于辩论内容，立场保持不变。"

    return None, ""
