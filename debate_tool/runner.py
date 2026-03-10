#!/usr/bin/env python3
"""
通用辩论框架 — 读取 Markdown + YAML front-matter 驱动多模型辩论。

用法:
    debate-tool run my_topic.md
    debate-tool run my_topic.md --rounds 5
    debate-tool run my_topic.md --dry-run
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from debate_tool.core import (
    DEFAULT_DEBATERS,
    DEFAULT_JUDGE,
    DEFAULT_EARLY_STOP_THRESHOLD,
    check_convergence,
    estimate_tokens,
    build_compact_context,
    build_full_compact,
    DEFAULT_COMPACT_TRIGGER,
)

# ── 环境变量 ────────────────────────────────────────────
ENV_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
ENV_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()


# ── YAML Front-matter 解析 ───────────────────────────────


def _parse_early_stop(val) -> float:
    """Parse early_stop: False → 0, True → default threshold, float → that value."""
    if val is False or val is None or val == 0:
        return 0.0
    if val is True:
        return DEFAULT_EARLY_STOP_THRESHOLD
    f = float(val)
    if not (0 < f < 1):
        raise ValueError(f"early_stop must be true or a float in (0,1), got {val!r}")
    return f


def _parse_cot(val) -> int | None:
    """Parse cot YAML field.

    cot: false / null / 0  → None (disabled)
    cot: true              → 0   (enabled, no token limit)
    cot: 2000              → 2000 (enabled, 2000-token thinking budget)
    """
    if val is False or val is None or val == 0:
        return None
    if val is True:
        return 0
    return int(val)


def _expand_env(value: str) -> str:
    import re as _re_env
    def _replace(m: "_re_env.Match") -> str:
        var = m.group(1) or m.group(2) or ""
        return os.environ.get(var, m.group(0) or "") or ""
    return _re_env.sub(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)", _replace, value)


def parse_topic_file(path: Path) -> dict:
    """解析 Markdown 文件的 YAML front-matter + body。"""
    text = path.read_text(encoding="utf-8")

    # 分离 front-matter 和 body
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            front = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
        else:
            front, body = {}, text
    else:
        front, body = {}, text

    # 组装配置（带默认值）
    cfg = {
        "title": front.get("title", path.stem),
        "rounds": front.get("rounds", 3),
        "timeout": front.get("timeout", 300),
        "max_reply_tokens": front.get("max_reply_tokens")
        or front.get("max_tokens", 6000),
        "debaters": [
            {**d, "base_url": _expand_env(str(d.get("base_url", "") or "")), "api_key": _expand_env(str(d.get("api_key", "") or ""))}
            for d in front.get("debaters", DEFAULT_DEBATERS)
        ],
        "judge": {
            **DEFAULT_JUDGE,
            **{k: (_expand_env(str(v)) if k in ("base_url", "api_key") else v) for k, v in front.get("judge", {}).items()},
        },
        "constraints": front.get("constraints", "").strip(),
        "round1_task": front.get(
            "round1_task", "针对各议题给出立场和建议，每个 200-300 字"
        ).strip(),
        "middle_task": front.get(
            "middle_task", "回应其他辩手观点，深化立场，400-600 字"
        ).strip(),
        "final_task": front.get(
            "final_task", "最终轮，给出最终建议，标注优先级，300-500 字"
        ).strip(),
        "judge_instructions": front.get("judge_instructions", "").strip(),
        "topic_body": body,
        # API 配置：front-matter > 环境变量（支持 ${VAR} 占位符展开）
        "base_url": _expand_env(front.get("base_url", "").strip()),
        "api_key": _expand_env(front.get("api_key", "").strip()),
        # Mode fields
        "cross_exam": int(front.get("cross_exam", 0)),
        "early_stop": _parse_early_stop(front.get("early_stop", False)),
        "cot_length": _parse_cot(front.get("cot", None)),
    }
    return cfg


# ── LLM 调用 ─────────────────────────────────────────────

import re as _re

_TOKEN_LIMIT_PATTERNS = [
    _re.compile(r"maximum context length is (\d+)", _re.I),
    _re.compile(r"max_tokens.*?(\d+)", _re.I),
    _re.compile(r"context_length_exceeded.*?(\d+)", _re.I),
    _re.compile(r"this model's maximum context length is (\d+)", _re.I),
    _re.compile(r"tokens? (?:in|exceeds?) .*?(\d+)", _re.I),
    _re.compile(r"(\d+)\s*tokens", _re.I),
]


class TokenLimitError(Exception):
    def __init__(self, model: str, model_max_tokens: int, raw: str):
        self.model = model
        self.model_max_tokens = model_max_tokens
        self.raw = raw
        super().__init__(f"Token limit: {model_max_tokens} for {model}")


def _parse_token_limit(text: str) -> int | None:
    for pat in _TOKEN_LIMIT_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def _is_token_limit_error(status: int, body: str) -> bool:
    if status == 400:
        low = body.lower()
        return any(
            k in low
            for k in (
                "context_length_exceeded",
                "maximum context length",
                "max_tokens",
                "tokens",
                "context length",
            )
        )
    return False


async def call_llm(
    model: str,
    system: str,
    user_content: str,
    *,
    temperature: float = 0.7,
    max_reply_tokens: int = 6000,
    timeout: int = 300,
    base_url: str = "",
    api_key: str = "",
) -> str:
    """调用 LLM API，支持按角色覆盖 base_url/api_key。"""
    url = base_url or ENV_BASE_URL
    key = api_key or ENV_API_KEY
    if not url:
        return "[调用失败: 未配置 API Base URL，请设置 DEBATE_BASE_URL 或在 front-matter 提供 base_url]"
    if not key:
        return "[调用失败: 未配置 API Key，请设置 DEBATE_API_KEY 或在 front-matter 提供 api_key]"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_reply_tokens,
    }
    async with httpx.AsyncClient(timeout=timeout) as c:
        for attempt in range(3):
            try:
                r = await c.post(
                    url.rstrip("/"),
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                body_text = r.text
                if _is_token_limit_error(r.status_code, body_text):
                    limit = _parse_token_limit(body_text) or 0
                    raise TokenLimitError(model, limit, body_text)
                r.raise_for_status()
                choice = r.json()["choices"][0]
                content = choice["message"]["content"]
                if choice.get("finish_reason") == "length":
                    content += "\n\n[WARNING: output was truncated due to max_tokens limit]"
                return content
            except TokenLimitError:
                raise
            except Exception as e:
                if attempt == 2:
                    return f"[调用失败: {e}]"
                print(f"  ⚠️ {model} retry {attempt + 1}: {e}", file=sys.stderr)
                await asyncio.sleep(2**attempt)
    return "[调用失败]"


# ── Token 超限时的分段 compact 重试 ─────────────────────

_MIN_SEGMENT_CHARS = 30_000


def _compact_for_retry(
    entries: list[dict],
    model_max_tokens: int,
    num_debaters: int,
    system_text: str,
) -> str:
    budget = int(model_max_tokens * 0.7)
    segment_chars = max(budget * 3, _MIN_SEGMENT_CHARS)

    while True:
        result = build_compact_context(
            entries,
            token_budget=budget,
            num_debaters=num_debaters,
            system_text=system_text,
        )
        if len(result) <= segment_chars:
            return result
        segment_chars = int(segment_chars * 0.8)
        if segment_chars < _MIN_SEGMENT_CHARS:
            raise RuntimeError(
                f"compact 后上下文仍超限且段长已压至 {segment_chars} 字符 (<{_MIN_SEGMENT_CHARS})，"
                f"无法继续压缩。请手动 compact 或缩减辩论轮次。"
            )
        print(
            f"  ⚠️ compact 后仍超限，段长缩至 {segment_chars}，重新压缩...",
            file=sys.stderr,
        )


# ── CoT 辅助 ──────────────────────────────────────────────

import re as _re_cot

_THINKING_RE = _re_cot.compile(r"<thinking>(.*?)</thinking>", _re_cot.DOTALL)


def _split_cot_response(response: str) -> tuple[str, str]:
    """Split a COT response into (thinking_content, actual_reply).

    If <thinking>...</thinking> tags are present, extract the thinking block and
    treat everything after </thinking> as the actual reply (leading whitespace
    stripped).  If no tags are found, return ("", response) as a fallback.
    """
    m = _THINKING_RE.search(response)
    if m:
        thinking = m.group(1).strip()
        after = response[m.end():].lstrip()
        return thinking, after
    # Fallback: no tags found — treat entire response as reply
    return "", response


# ── 日志 ──────────────────────────────────────────────────


class Log:
    def __init__(self, path: Path, title: str):
        self.path = path
        self.title = title
        self.entries: list[dict] = []
        self._pre_checkpoint_text: str = ""

    @classmethod
    def load_from_file(cls, path: Path) -> "Log":
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        title = "辩论"
        for line in lines:
            if line.startswith("# ") and "辩论日志" in line:
                title = line.lstrip("# ").replace(" 辩论日志", "").strip()
                break

        all_entries: list[dict] = []
        import re

        entry_pattern = re.compile(r"^### \[(\d+)\]\s*(.*)")
        i = 0
        while i < len(lines):
            m = entry_pattern.match(lines[i])
            if m:
                seq = int(m.group(1))
                header = m.group(2).strip()
                tag = ""
                name = header
                if "📦 **Checkpoint**" in header:
                    tag = "compact_checkpoint"
                    name = (
                        header.replace("📦 **Checkpoint**", "").strip()
                        or "Compact Checkpoint"
                    )
                elif "⚖️ **裁判总结**" in header:
                    tag = "summary"
                    name = header.replace("⚖️ **裁判总结**", "").strip() or "裁判"
                elif "🔍 **质询**" in header:
                    tag = "cross_exam"
                    name = header.replace("🔍 **质询**", "").strip() or "质询"
                elif "📝 **Meta**" in header:
                    tag = "meta"
                    name = header.replace("📝 **Meta**", "").strip() or "@meta"
                elif "🧠 **思考**" in header:
                    tag = "thinking"
                    name = header.replace("🧠 **思考**", "").strip() or "思考"

                ts = ""
                i += 1
                # Skip blank lines between header and timestamp
                while i < len(lines) and lines[i] == "":
                    i += 1
                if (
                    i < len(lines)
                    and lines[i].startswith("*")
                    and lines[i].endswith("*")
                ):
                    ts = lines[i].strip("*").strip()
                    i += 1

                # Skip blank lines between timestamp and content
                while i < len(lines) and lines[i] == "":
                    i += 1

                content_lines = []
                while i < len(lines) and not lines[i].startswith("---"):
                    content_lines.append(lines[i])
                    i += 1

                while content_lines and content_lines[-1] == "":
                    content_lines.pop()

                all_entries.append(
                    {
                        "seq": seq,
                        "ts": ts or datetime.now().isoformat(),
                        "tag": tag,
                        "name": name if name else f"Entry {seq}",
                        "content": "\n".join(content_lines),
                    }
                )
            else:
                i += 1

        # Find last checkpoint — only load from there onward
        last_checkpoint_idx = -1
        for idx, e in enumerate(all_entries):
            if e["tag"] == "compact_checkpoint":
                last_checkpoint_idx = idx

        log = cls(path, title)
        if last_checkpoint_idx >= 0:
            log.entries = all_entries[last_checkpoint_idx:]
            skipped = all_entries[:last_checkpoint_idx]
            pre_lines = [
                f"# {title} 辩论日志\n\n> {datetime.now().isoformat()}\n\n---\n"
            ]
            for e in skipped:
                label = {
                    "summary": "⚖️ **裁判总结**",
                    "cross_exam": "🔍 **质询**",
                    "compact_checkpoint": "📦 **Checkpoint**",
                }.get(e["tag"], "")
                hdr = f"[{e['seq']}] {label}" if label else f"[{e['seq']}] {e['name']}"
                pre_lines.append(
                    f"\n### {hdr}\n\n*{e['ts']}*\n\n{e['content']}\n\n---\n"
                )
            log._pre_checkpoint_text = "\n".join(pre_lines)
            print(
                f"  📦 从 checkpoint #{all_entries[last_checkpoint_idx]['seq']} 恢复，跳过 {last_checkpoint_idx} 条旧记录"
            )
        else:
            log.entries = all_entries

        return log

    def add(self, name: str, content: str, tag: str = "", flush: bool = True):
        e = {
            "seq": len(self.entries) + 1,
            "ts": datetime.now().isoformat(),
            "tag": tag,
            "name": name,
            "content": content,
        }
        self.entries.append(e)
        icon = {
            "summary": "⚖️ 裁判",
            "cross_exam": "🔍",
            "compact_checkpoint": "📦",
            "meta": "📝",
            "thinking": "🧠",
        }.get(tag, "💬")
        print(f"\n{'=' * 60}\n[{e['seq']}] {icon} {name}\n{'=' * 60}")
        t = content
        print(t[:800] + "\n...(见日志)" if len(t) > 800 else t)
        if flush:
            self._flush()

    def _flush(self):
        if self._pre_checkpoint_text:
            lines = [self._pre_checkpoint_text]
        else:
            lines = [
                f"# {self.title} 辩论日志\n\n> {datetime.now().isoformat()}\n\n---\n"
            ]
        for e in self.entries:
            tag_label = {
                "summary": "⚖️ **裁判总结**",
                "cross_exam": "🔍 **质询**",
                "compact_checkpoint": "📦 **Checkpoint**",
                "meta": "📝 **Meta**",
                "thinking": "🧠 **思考**",
            }.get(e["tag"], "")
            if tag_label:
                hdr = f"[{e['seq']}] {tag_label} {e['name']}"
            else:
                hdr = f"[{e['seq']}] {e['name']}"
            lines.append(f"\n### {hdr}\n\n*{e['ts']}*\n\n{e['content']}\n\n---\n")
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(self.path)

    def since(self, after_seq: int) -> str:
        news = [
            e for e in self.entries
            if e["seq"] > after_seq and e.get("tag") != "thinking"
        ]
        if not news:
            return "(无新内容)"
        return "\n\n".join(f"--- {e['name']} ---\n{e['content']}" for e in news)

    def compact(self) -> str:
        parts = []
        for e in self.entries:
            tag = f"[{e['tag'].upper()}] " if e["tag"] else ""
            t = e["content"][:1200]
            if len(e["content"]) > 1200:
                t += "...(截断)"
            parts.append(f"### [{e['seq']}] {tag}{e['name']}\n{t}")
        return "\n\n".join(parts)


# ── 质询子回合 ────────────────────────────────────────────


async def run_cross_exam(
    debaters: list[dict],
    log: Log,
    topic: str,
    rnd: int,
    *,
    max_reply_tokens: int,
    timeout: int,
    debate_base_url: str,
    debate_api_key: str,
) -> set[str]:
    """Dynamic cross-examination after a debate round.

    Each questioner sees all debaters' latest speeches, then chooses whom to challenge.
    Returns the set of debater names who were challenged (parsed from LLM responses).
    """
    n = len(debaters)
    # Collect latest round speeches — skip thinking entries, take last N non-thinking entries
    non_thinking = [e for e in log.entries if e.get("tag") != "thinking"]
    latest_entries = non_thinking[-n:]
    speech_by_name: dict[str, str] = {e["name"]: e["content"] for e in latest_entries}

    # Build summary of all debaters' latest speeches
    all_speeches_parts = []
    for d in debaters:
        speech = speech_by_name.get(d["name"], "(无发言)")
        all_speeches_parts.append(f"## {d['name']} 的第 {rnd} 轮发言\n\n{speech}")
    all_speeches_summary = "\n\n---\n\n".join(all_speeches_parts)

    challenged_set: set[str] = set()
    debater_names = [d["name"] for d in debaters]

    for questioner in debaters:
        q_base_url = (questioner.get("base_url", "") or debate_base_url).strip()
        q_api_key = (questioner.get("api_key", "") or debate_api_key).strip()

        sys_prompt = (
            f"你是「{questioner['name']}」（{questioner['style']}），"
            f"现在进入质询环节。\n\n"
            f"请先选择你最想质询的对手（说明理由），然后针对该对手提出 2-3 个尖锐质疑，"
            f"指出其论证中的薄弱环节、遗漏或矛盾之处。\n\n"
            f"【格式要求】回复必须以如下一行开头（不得省略）：\n"
            f"质询对象：{{被质询者姓名}}\n\n"
            f"其中姓名必须是以下辩手之一：{', '.join(d for d in debater_names if d != questioner['name'])}"
        )
        user_ctx = (
            f"## 辩论议题\n\n{topic}\n\n"
            f"## 各辩手第 {rnd} 轮发言\n\n{all_speeches_summary}"
        )

        result = await call_llm(
            questioner["model"],
            sys_prompt,
            user_ctx,
            max_reply_tokens=max_reply_tokens,
            timeout=timeout,
            base_url=q_base_url,
            api_key=q_api_key,
        )

        # Extract challenged debater name from "质询对象：{name}" at start of reply
        challenged_name: str | None = None
        for line in result.splitlines():
            line = line.strip()
            if line.startswith("质询对象：") or line.startswith("质询对象:"):
                candidate = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                # Validate: must be a known debater (not the questioner)
                for dname in debater_names:
                    if dname == candidate or dname in candidate or candidate in dname:
                        if dname != questioner["name"]:
                            challenged_name = dname
                            break
                break

        if challenged_name:
            challenged_set.add(challenged_name)
            log.add(f"{questioner['name']} → {challenged_name}", result, "cross_exam")
        else:
            # Fallback: log without a resolved target name
            log.add(f"{questioner['name']} → (未解析)", result, "cross_exam")

    return challenged_set


# ── 主流程 ────────────────────────────────────────────────


async def run(cfg: dict, topic_path: Path, *, cot_length: int | None = None):
    stem = topic_path.stem
    out_dir = topic_path.parent

    log = Log(out_dir / f"{stem}_debate_log.md", cfg["title"])
    topic = cfg["topic_body"]
    debaters = cfg["debaters"]
    judge = cfg["judge"]
    rounds = cfg["rounds"]
    timeout = cfg["timeout"]
    max_reply_tokens = cfg["max_reply_tokens"]
    constraints = cfg["constraints"]
    cross_exam = cfg.get("cross_exam", 0)  # number of rounds with cross-exam
    early_stop = cfg.get("early_stop", 0.0)  # 0=off, (0,1)=threshold
    # COT: CLI > YAML > None (disabled)
    if cot_length is None:
        cot_length = cfg.get("cot_length", None)
    # Per-debate API config
    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()

    # cross_exam == -1 means every round (except last)
    if cross_exam < 0:
        cross_exam_rounds = set(range(1, rounds))  # all except final
    else:
        cross_exam_rounds = set(range(1, min(cross_exam, rounds) + 1))

    print("=" * 60)
    print(f"  {cfg['title']}")
    flags = []
    if cross_exam_rounds:
        if cross_exam < 0:
            flags.append("质询(全轮)")
        elif cross_exam == 1:
            flags.append("质询(R1)")
        else:
            flags.append(f"质询(R1~R{max(cross_exam_rounds)})")
    if early_stop:
        flags.append(f"早停(≥{early_stop:.0%})")
    if cot_length is not None:
        if cot_length > 0:
            flags.append(f"CoT(≤{cot_length}t)")
        else:
            flags.append("CoT")
    if flags:
        print(f"  [{', '.join(flags)}]")
    print(f"  {rounds} 轮 | 辩手: {', '.join(d['name'] for d in debaters)}")
    print(f"  裁判: {judge['name']}")
    if debate_base_url:
        print(f"  API: {debate_base_url}")
    print("=" * 60)

    last_seq = 0
    challenged_last: set[str] | None = None

    for rnd in range(1, rounds + 1):
        print(f"\n\n📢 第 {rnd}/{rounds} 轮\n")
        new_log = log.since(last_seq)

        # ── Phase A: 并行辩手发言 ──
        if rnd == 1:
            user_ctx = f"## 辩论议题\n\n{topic}"
            base_task_desc = cfg["round1_task"]
        elif rnd == rounds:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            base_task_desc = cfg["final_task"]
        else:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            base_task_desc = cfg["middle_task"]

        constraints_block = ""
        if constraints:
            constraints_block = f"\n\n核心约束：\n{constraints}"

        mark = log.entries[-1]["seq"] if log.entries else 0
        current_user_ctx = user_ctx
        replies = []

        for _ in range(10):

            async def speak(
                d,
                rnd=rnd,
                base_task_desc=base_task_desc,
                _ctx=current_user_ctx,
                constraints_block=constraints_block,
                _challenged_last=challenged_last,
            ):
                debater_base_url = (d.get("base_url", "") or debate_base_url).strip()
                debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
                # Determine per-debater task_desc based on whether challenged last round
                if _challenged_last is not None:
                    if d["name"] in _challenged_last:
                        if rnd == rounds:
                            task_desc = (
                                "逐条回应你收到的质询，指出对方质疑中的不当之处，"
                                "并可修正自己的方案。\n\n此外，" + base_task_desc
                            )
                        else:
                            task_desc = (
                                "逐条回应你收到的质询，指出对方质疑中的不当之处，"
                                "并可修正自己的方案。400-600 字"
                            )
                    else:
                        if rnd == rounds:
                            task_desc = base_task_desc
                        else:
                            task_desc = (
                                "本轮无人向你提出质询。如有新论点或补充可继续阐发；"
                                "若你认为本轮无新内容可补充，可简短表示等待本轮，无需强行发言。200-400 字"
                            )
                else:
                    task_desc = base_task_desc
                sys_prompt = (
                    f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮。\n\n"
                    f"任务：{task_desc}{constraints_block}"
                )
                if cot_length is not None:
                    cot_note = "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"
                    if cot_length > 0:
                        cot_note += f" 思考内容不超过 {cot_length} token。"
                    sys_prompt = sys_prompt + "\n\n" + cot_note
                    call_max_tokens = (
                        (cot_length + max_reply_tokens) if cot_length > 0
                        else (max_reply_tokens + 2000)
                    )
                else:
                    call_max_tokens = max_reply_tokens
                raw = await call_llm(
                    d["model"],
                    sys_prompt,
                    _ctx,
                    max_reply_tokens=call_max_tokens,
                    timeout=timeout,
                    base_url=debater_base_url,
                    api_key=debater_api_key,
                )
                if cot_length is not None:
                    thinking, reply = _split_cot_response(raw)
                else:
                    thinking, reply = "", raw
                return thinking, reply

            try:
                raw_results = await asyncio.gather(*[speak(d) for d in debaters])
                break
            except TokenLimitError as e:
                print(
                    f"\n  📦 Token 超限 (model_max={e.model_max_tokens})，compact 后重试...",
                    file=sys.stderr,
                )
                compact_text = _compact_for_retry(
                    log.entries,
                    e.model_max_tokens,
                    len(debaters),
                    f"## 辩论议题\n\n{topic}",
                )
                log.add("Compact Checkpoint", compact_text, "compact_checkpoint")
                sys_text = f"## 辩论议题\n\n{topic}"
                current_user_ctx = f"{sys_text}\n\n## 辩论历史\n\n{compact_text}"
        else:
            raise RuntimeError(
                f"第 {rnd} 轮经过多次 compact 仍无法完成，请手动压缩日志"
            )
        for d, (thinking, reply) in zip(debaters, raw_results):
            if thinking:
                log.add(d["name"], thinking, "thinking", flush=False)
            log.add(d["name"], reply, flush=False)
            replies.append(reply)
        log._flush()  # 一次性写入
        last_seq = mark

        # ── Phase B: 早停检查 ──
        if early_stop and rnd < rounds:
            converged, avg_sim = check_convergence(replies, early_stop)
            print(f"\n  📊 收敛检查: 平均相似度 {avg_sim:.1%} (阈值 {early_stop:.0%})")
            if converged:
                print("  ⚡ 观点已收敛，跳过剩余轮次，直接进入裁判阶段")
                break

        # ── Phase C: 质询（若当前轮在 cross_exam_rounds 中且非最后一轮） ──
        if rnd in cross_exam_rounds and rnd < rounds:
            print(f"\n\n🔍 质询环节 (R{rnd}.5)\n")
            challenged_set = await run_cross_exam(
                debaters,
                log,
                topic,
                rnd,
                max_reply_tokens=max_reply_tokens,
                timeout=timeout,
                debate_base_url=debate_base_url,
                debate_api_key=debate_api_key,
            )
            challenged_last = challenged_set
        else:
            challenged_last = None

    # ══════════════════════════════════════════════════
    #  裁判总结
    # ══════════════════════════════════════════════════
    print("\n\n⚖️ 裁判总结\n")

    # 默认裁判指令
    judge_instructions = cfg["judge_instructions"]
    if not judge_instructions:
        judge_instructions = (
            "输出结构化 Summary：\n\n"
            "## 一、各辩手表现评价（每位 2-3 句）\n\n"
            "## 二、逐一裁定\n"
            "对每个议题给出：\n"
            "- **裁定**：最终方案\n"
            "- **理由**：引用辩论中的关键论据\n"
            "- **优先级**：P0 / P1 / P2\n\n"
            "## 三、完整修改清单"
        )

    human_entries = [e for e in log.entries if e.get("tag") == "human"]
    if human_entries:
        human_block = "\n".join(f"- {e['content']}" for e in human_entries)
        judge_instructions += (
            f"\n\n## 四、观察者意见回应\n"
            f"本次辩论中有观察者注入了以下意见：\n{human_block}\n"
            f"请逐条说明各辩手对这些意见的吸收和回应情况。"
        )

    judge_sys = (
        f"你是辩论裁判（{judge['name']}），负责做出最终裁定。\n\n"
        f"{judge_instructions}\n\n"
        f"裁定规则：\n"
        f"- 基于事实和数据\n"
        f"- 引用辩论中的关键论据\n"
        f"- 简洁、可操作"
    )

    judge_max_tokens = judge.get("max_tokens", 8000)
    judge_base_url = (judge.get("base_url", "") or debate_base_url).strip()
    judge_api_key = (judge.get("api_key", "") or debate_api_key).strip()
    summary = await call_llm(
        judge["model"],
        judge_sys,
        f"全部辩论（压缩版）：\n\n{log.compact()}",
        temperature=0.3,
        max_reply_tokens=judge_max_tokens,
        timeout=timeout,
        base_url=judge_base_url,
        api_key=judge_api_key,
    )
    log.add(judge["name"], summary, "summary")

    sp = out_dir / f"{stem}_debate_summary.md"
    sp.write_text(
        f"# {cfg['title']} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}",
        encoding="utf-8",
    )

    print(f"\n✅ 完成！ 日志: {log.path} | 总结: {sp}")


# ── 续跑（resume） ───────────────────────────────────────


async def resume(
    cfg: dict,
    topic_path: Path,
    *,
    message: str = "",
    extra_rounds: int = 1,
    cross_exam: int = 0,
    guide_prompt: str = "",
    judge_at_end: bool = True,
    force: bool = False,
    cot_length: int | None = None,
) -> None:
    stem = topic_path.stem
    out_dir = topic_path.parent
    log_path = out_dir / f"{stem}_debate_log.md"

    if not log_path.exists():
        print(f"❌ 日志文件不存在: {log_path}", file=sys.stderr)
        print("请先运行 debate-tool run 进行首次辩论", file=sys.stderr)
        sys.exit(1)

    log = Log.load_from_file(log_path)
    print(f"📂 已加载 {len(log.entries)} 条日志记录")

    validate_topic_log_consistency(cfg, log, force=force)

    topic = cfg["topic_body"]
    debaters = cfg["debaters"]
    judge = cfg["judge"]
    timeout = cfg["timeout"]
    max_reply_tokens = cfg["max_reply_tokens"]
    constraints = cfg["constraints"]
    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()
    num_debaters = len(debaters)
    system_text = f"## 辩论议题\n\n{topic}"
    # COT: CLI > YAML > None (disabled)
    if cot_length is None:
        cot_length = cfg.get("cot_length", None)

    if message:
        log.add("👤 观察者", message, "human")
        print(f"\n💬 已注入观察者消息")

    base_round = len([e for e in log.entries if not e.get("tag")]) // max(
        num_debaters, 1
    )

    for r_offset in range(1, extra_rounds + 1):
        rnd = base_round + r_offset
        print(f"\n\n📢 续跑第 {rnd} 轮\n")

        new_log = log.since(0)

        if guide_prompt:
            task_desc = (
                f"回应其他辩手观点，深化立场。400-600 字\n\n观察者指引：{guide_prompt}"
            )
        elif message and r_offset == 1:
            task_desc = "请回应观察者提出的问题/意见，同时深化自己的立场。400-600 字"
        else:
            task_desc = cfg["middle_task"]

        constraints_block = f"\n\n核心约束：\n{constraints}" if constraints else ""

        async def speak(
            d,
            rnd=rnd,
            task_desc=task_desc,
            constraints_block=constraints_block,
            _new_log=None,
        ):
            debater_base_url = (d.get("base_url", "") or debate_base_url).strip()
            debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
            sys_prompt = (
                f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮（续跑）。\n\n"
                f"任务：{task_desc}{constraints_block}"
            )
            if cot_length is not None:
                cot_note = "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"
                if cot_length > 0:
                    cot_note += f" 思考内容不超过 {cot_length} token。"
                sys_prompt = sys_prompt + "\n\n" + cot_note
                call_max_tokens = (
                    (cot_length + max_reply_tokens) if cot_length > 0
                    else (max_reply_tokens + 2000)
                )
            else:
                call_max_tokens = max_reply_tokens
            ctx = f"{system_text}\n\n## 辩论历史\n\n{_new_log or new_log}"
            raw = await call_llm(
                d["model"],
                sys_prompt,
                ctx,
                max_reply_tokens=call_max_tokens,
                timeout=timeout,
                base_url=debater_base_url,
                api_key=debater_api_key,
            )
            if cot_length is not None:
                thinking, reply = _split_cot_response(raw)
            else:
                thinking, reply = "", raw
            return thinking, reply

        for compact_attempt in range(10):
            try:
                raw_results = await asyncio.gather(*[speak(d) for d in debaters])
                break
            except TokenLimitError as e:
                print(
                    f"\n  📦 Token 超限 (model_max={e.model_max_tokens})，触发 compact 后重试...",
                    file=sys.stderr,
                )
                compact_text = _compact_for_retry(
                    log.entries, e.model_max_tokens, num_debaters, system_text
                )
                log.add("Compact Checkpoint", compact_text, "compact_checkpoint")
                new_log = compact_text

                async def speak_retry(
                    d,
                    rnd=rnd,
                    task_desc=task_desc,
                    constraints_block=constraints_block,
                    _nl=compact_text,
                ):
                    debater_base_url = (
                        d.get("base_url", "") or debate_base_url
                    ).strip()
                    debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
                    sys_prompt = (
                        f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮（续跑）。\n\n"
                        f"任务：{task_desc}{constraints_block}"
                    )
                    if cot_length is not None:
                        cot_note = "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"
                        if cot_length > 0:
                            cot_note += f" 思考内容不超过 {cot_length} token。"
                        sys_prompt = sys_prompt + "\n\n" + cot_note
                        call_max_tokens = (
                            (cot_length + max_reply_tokens) if cot_length > 0
                            else (max_reply_tokens + 2000)
                        )
                    else:
                        call_max_tokens = max_reply_tokens
                    ctx = f"{system_text}\n\n## 辩论历史\n\n{_nl}"
                    raw = await call_llm(
                        d["model"],
                        sys_prompt,
                        ctx,
                        max_reply_tokens=call_max_tokens,
                        timeout=timeout,
                        base_url=debater_base_url,
                        api_key=debater_api_key,
                    )
                    if cot_length is not None:
                        thinking, reply = _split_cot_response(raw)
                    else:
                        thinking, reply = "", raw
                    return thinking, reply

                try:
                    raw_results = await asyncio.gather(*[speak_retry(d) for d in debaters])
                    break
                except TokenLimitError as e2:
                    print(
                        f"  ⚠️ compact 后仍超限 (attempt {compact_attempt + 1})，继续缩...",
                        file=sys.stderr,
                    )
                    compact_text = _compact_for_retry(
                        log.entries, e2.model_max_tokens, num_debaters, system_text
                    )
                    log.add("Compact Checkpoint", compact_text, "compact_checkpoint")
                    new_log = compact_text
        else:
            raise RuntimeError(
                f"第 {rnd} 轮经过多次 compact 仍无法完成，请手动压缩日志"
            )

        for d, (thinking, reply) in zip(debaters, raw_results):
            if thinking:
                log.add(d["name"], thinking, "thinking", flush=False)
            log.add(d["name"], reply, flush=False)
        log._flush()  # 一次性写入

        do_cross_exam = (
            cross_exam != 0
            and (cross_exam < 0 or r_offset <= cross_exam)
            and r_offset < extra_rounds
        )
        if do_cross_exam:
            print(f"\n\n🔍 质询环节 (续跑 R{rnd}.5)\n")
            await run_cross_exam(
                debaters,
                log,
                topic,
                rnd,
                max_reply_tokens=max_reply_tokens,
                timeout=timeout,
                debate_base_url=debate_base_url,
                debate_api_key=debate_api_key,
            )  # resume 中不使用返回的 challenged_set，无需处理

    if judge_at_end:
        print("\n\n⚖️ 裁判总结\n")
        judge_instructions = cfg.get("judge_instructions", "")
        if not judge_instructions:
            judge_instructions = (
                "输出结构化 Summary：\n\n"
                "## 一、各辩手表现评价（每位 2-3 句）\n\n"
                "## 二、逐一裁定\n"
                "对每个议题给出：\n"
                "- **裁定**：最终方案\n"
                "- **理由**：引用辩论中的关键论据\n"
                "- **优先级**：P0 / P1 / P2\n\n"
                "## 三、完整修改清单"
            )

        human_entries = [e for e in log.entries if e.get("tag") == "human"]
        if human_entries:
            human_block = "\n".join(f"- {e['content']}" for e in human_entries)
            judge_instructions += (
                f"\n\n## 四、观察者意见回应\n"
                f"本次辩论中有观察者注入了以下意见：\n{human_block}\n"
                f"请逐条说明各辩手对这些意见的吸收和回应情况。"
            )

        judge_sys = (
            f"你是辩论裁判（{judge['name']}），负责做出最终裁定。\n\n"
            f"{judge_instructions}\n\n"
            f"裁定规则：\n"
            f"- 基于事实和数据\n"
            f"- 引用辩论中的关键论据\n"
            f"- 简洁、可操作"
        )

        judge_max_tokens = judge.get("max_tokens", 8000)
        judge_base_url = (judge.get("base_url", "") or debate_base_url).strip()
        judge_api_key = (judge.get("api_key", "") or debate_api_key).strip()
        judge_ctx = log.since(0)

        for _ in range(5):
            try:
                summary = await call_llm(
                    judge["model"],
                    judge_sys,
                    f"全部辩论（含续跑）：\n\n{judge_ctx}",
                    temperature=0.3,
                    max_reply_tokens=judge_max_tokens,
                    timeout=timeout,
                    base_url=judge_base_url,
                    api_key=judge_api_key,
                )
                break
            except TokenLimitError as e:
                print(
                    f"\n  📦 裁判 token 超限 (max={e.model_max_tokens})，compact 后重试...",
                    file=sys.stderr,
                )
                judge_ctx = _compact_for_retry(
                    log.entries, e.model_max_tokens, num_debaters, ""
                )
        else:
            summary = "[裁判总结失败：多次 compact 后仍超限]"
        log.add(judge["name"], summary, "summary")

        sp = out_dir / f"{stem}_debate_summary.md"
        sp.write_text(
            f"# {cfg['title']} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}",
            encoding="utf-8",
        )

    print(f"\n✅ 续跑完成！ 日志: {log.path}")


# ── 手动压缩 ─────────────────────────────────────────────


def compact_log(
    log_path: Path,
    *,
    keep_last: int = 0,
    token_budget: int = 60000,
) -> None:
    if not log_path.exists():
        print(f"❌ 日志文件不存在: {log_path}", file=sys.stderr)
        sys.exit(1)

    log = Log.load_from_file(log_path)
    total = len(log.entries)
    print(f"📂 已加载 {total} 条日志记录")

    if keep_last >= total:
        print(f"⚠️  keep_last={keep_last} >= 总条目数 {total}，无需压缩")
        return

    compact_text, kept = build_full_compact(
        log.entries,
        token_budget=token_budget,
        keep_last=keep_last,
    )

    before_tokens = estimate_tokens("\n\n".join(e["content"] for e in log.entries))
    after_tokens = estimate_tokens(compact_text)
    compressed_count = total - keep_last

    log.add("Compact Checkpoint", compact_text, "compact_checkpoint")

    for e in kept:
        log.add(e["name"], e["content"], e.get("tag", ""))

    print(f"\n📦 压缩完成:")
    print(f"   压缩条目: {compressed_count}/{total}")
    print(f"   保留条目: {keep_last}")
    print(f"   Token: {before_tokens} → {after_tokens} (checkpoint)")
    print(f"   日志: {log.path}")


def _mask_key(key: str) -> str:
    if len(key) <= 7:
        return "****"
    return key[:3] + "****" + key[-4:]


# ── modify 子命令 ─────────────────────────────────────────


def modify_topic(
    topic_path: Path,
    *,
    set_fields: list[str] | None = None,
    add_debaters: list[str] | None = None,
    drop_debaters: list[str] | None = None,
    pivot_stances: list[str] | None = None,
    reason: str = "",
    force: bool = False,
) -> None:
    """Modify topic file and append a @meta/modify event to the log.

    --set  debater.A.model=gpt-5        (or judge.model=claude, or rounds=5)
    --add  "C|gpt-5.2|激进派风格"        (name|model|style)
    --drop B
    --pivot "A|新的立场描述"             (name|new_style)
    --reason "why this change"
    """
    import yaml

    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    raw_text = topic_path.read_text(encoding="utf-8")
    # Split frontmatter
    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        print("❌ topic 文件格式错误（缺少 YAML frontmatter）", file=sys.stderr)
        sys.exit(1)
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]

    log_path = topic_path.parent / f"{topic_path.stem}_debate_log.md"
    log_exists = log_path.exists()

    if log_exists:
        log = Log.load_from_file(log_path)
        log_debater_names = {
            e["name"]
            for e in log.entries
            if e.get("tag")
            not in ("summary", "cross_exam", "compact_checkpoint", "human", "meta", "thinking")
        }
    else:
        log = None
        log_debater_names: set[str] = set()

    changes: list[str] = []

    # ── --set ──
    for field_expr in set_fields or []:
        if "=" not in field_expr:
            print(f"⚠️ --set 格式应为 key=value: {field_expr}", file=sys.stderr)
            continue
        key, val = field_expr.split("=", 1)
        parts_key = key.strip().split(".")

        if parts_key[0] == "judge":
            if len(parts_key) == 2:
                fm.setdefault("judge", {})
                if isinstance(fm["judge"], str):
                    fm["judge"] = {"name": fm["judge"]}
                old = fm["judge"].get(parts_key[1], "")
                fm["judge"][parts_key[1]] = val
                changes.append(f"set judge.{parts_key[1]}: {old!r} → {val!r}")
        elif parts_key[0] == "debater" and len(parts_key) >= 3:
            target_name = parts_key[1]
            attr = parts_key[2]
            debaters_list = fm.get("debaters", [])
            matched = next(
                (d for d in debaters_list if d.get("name") == target_name), None
            )
            if matched is None:
                matched = next(
                    (d for d in debaters_list if d.get("name", "").startswith(target_name)),
                    None,
                )
            if matched is None:
                matched = next(
                    (d for d in debaters_list if target_name in d.get("name", "")),
                    None,
                )
            if matched is not None:
                old = matched.get(attr, "")
                matched[attr] = val
                changes.append(
                    f"set debater.{matched['name']}.{attr}: {old!r} → {val!r}"
                )
            else:
                print(f"⚠️ 未找到辩手 {target_name}", file=sys.stderr)
        else:
            # Top-level field
            old = fm.get(parts_key[0], "")
            fm[parts_key[0]] = int(val) if val.isdigit() else val
            changes.append(f"set {parts_key[0]}: {old!r} → {val!r}")

    # ── --add ──
    for spec in add_debaters or []:
        parts_spec = spec.split("|", 2)
        if len(parts_spec) < 2:
            print(f"⚠️ --add 格式: name|model|style  got: {spec}", file=sys.stderr)
            continue
        name, model_ = parts_spec[0].strip(), parts_spec[1].strip()
        style = parts_spec[2].strip() if len(parts_spec) > 2 else "中立观察者"
        fm.setdefault("debaters", [])
        if any(d.get("name") == name for d in fm["debaters"]):
            print(f"⚠️ 辩手 {name} 已存在，跳过 --add", file=sys.stderr)
            continue
        fm["debaters"].append({"name": name, "model": model_, "style": style})
        changes.append(f"add debater: {name} ({model_})")

    # ── --drop ──
    for name in drop_debaters or []:
        before = len(fm.get("debaters", []))
        fm["debaters"] = [d for d in fm.get("debaters", []) if d.get("name") != name]
        if len(fm.get("debaters", [])) < before:
            changes.append(f"drop debater: {name}")
            if name in log_debater_names and not force:
                print(
                    f"⚠️ 辩手 {name} 在 log 中有历史条目。"
                    f"其历史将保留在 log 中（以 [INACTIVE] 标记）。"
                    f"使用 --force 跳过此提示。"
                )
        else:
            print(f"⚠️ 未找到辩手 {name}", file=sys.stderr)

    # ── --pivot ──
    for spec in pivot_stances or []:
        parts_spec = spec.split("|", 1)
        if len(parts_spec) < 2:
            print(f"⚠️ --pivot 格式: name|new_style  got: {spec}", file=sys.stderr)
            continue
        name, new_style = parts_spec[0].strip(), parts_spec[1].strip()
        for d in fm.get("debaters", []):
            if d.get("name") == name:
                old_style = d.get("style", "")
                d["style"] = new_style
                changes.append(
                    f"pivot debater.{name}.style: {old_style!r} → {new_style!r}"
                )
                break
        else:
            print(f"⚠️ --pivot: 未找到辩手 {name}", file=sys.stderr)

    if not changes:
        print("⚠️ 没有任何修改", file=sys.stderr)
        return

    # Write updated topic file
    updated_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False)
    topic_path.write_text(f"---\n{updated_fm}---{body}", encoding="utf-8")
    print(f"✅ topic 文件已更新: {topic_path}")
    for c in changes:
        print(f"   • {c}")

    # Append @meta/modify event to log
    if log is not None:
        ts = datetime.now().isoformat()
        change_lines = "\n".join(f"- {c}" for c in changes)
        reason_line = f"\n\n原因：{reason}" if reason else ""
        meta_content = (
            f"**@meta/modify** `{ts}`\n\n"
            f"变更列表：\n{change_lines}"
            f"{reason_line}\n\n"
            f"_注：历史日志条目不受影响，以下续跑使用新配置。_"
        )
        log.add("@meta/modify", meta_content, "meta")
        print(f"   • 已追加 @meta/modify 事件到 log: {log_path}")


def validate_topic_log_consistency(
    cfg: dict, log: "Log", *, force: bool = False
) -> None:
    topic_names: set[str] = {d["name"] for d in cfg.get("debaters", [])}

    NON_DEBATER_TAGS = {
        "summary",
        "cross_exam",
        "compact_checkpoint",
        "meta",
        "human",
        "thinking",
    }
    log_speaker_names: set[str] = set()
    log_judge_names: set[str] = set()
    for e in log.entries:
        tag = e.get("tag", "") or ""
        name = e.get("name", "") or ""
        if tag == "summary":
            if name:
                log_judge_names.add(name)
        elif tag in NON_DEBATER_TAGS:
            continue
        elif (
            name.startswith("@meta")
            or name.startswith("👤")
            or name == "Compact Checkpoint"
        ):
            continue
        elif name:
            log_speaker_names.add(name)

    ghost_names = log_speaker_names - topic_names
    if ghost_names:
        msg = (
            f"❌ Log 中存在 topic 未配置的辩手: {', '.join(sorted(ghost_names))}\n"
            f"   使用 --force 跳过此检查，或用 modify --add 将其添加到 topic"
        )
        if force:
            print(f"⚠️ [force 忽略] {msg}", file=sys.stderr)
        else:
            print(msg, file=sys.stderr)
            sys.exit(1)

    new_names = topic_names - log_speaker_names
    if new_names and log.entries:
        print(
            f"ℹ️ Topic 中有 log 未出现的辩手（将作为新辩手参与）: "
            f"{', '.join(sorted(new_names))}"
        )

    topic_judge = (
        cfg.get("judge", {}).get("name", "")
        if isinstance(cfg.get("judge"), dict)
        else ""
    )
    if log_judge_names and topic_judge and topic_judge not in log_judge_names:
        print(
            f"⚠️ 裁判名变更: log 中记录的裁判为 {sorted(log_judge_names)}，"
            f"topic 当前为 {topic_judge!r}"
        )


def _validate_api_config(cfg: dict) -> list[str]:
    issues: list[str] = []

    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()

    for idx, debater in enumerate(cfg.get("debaters", []), start=1):
        debater_name = debater.get("name", f"debater#{idx}")
        url = (debater.get("base_url", "") or debate_base_url).strip()
        key = (debater.get("api_key", "") or debate_api_key).strip()
        missing_fields: list[str] = []
        if not url:
            missing_fields.append("base_url")
        if not key:
            missing_fields.append("api_key")
        if missing_fields:
            issues.append(
                f"debaters[{idx}]({debater_name}): " + ", ".join(missing_fields)
            )

    judge = cfg.get("judge", {}) or {}
    judge_name = judge.get("name", "judge")
    judge_url = (judge.get("base_url", "") or debate_base_url).strip()
    judge_key = (judge.get("api_key", "") or debate_api_key).strip()
    judge_missing: list[str] = []
    if not judge_url:
        judge_missing.append("base_url")
    if not judge_key:
        judge_missing.append("api_key")
    if judge_missing:
        issues.append(f"judge({judge_name}): " + ", ".join(judge_missing))

    return issues


# ── CLI ───────────────────────────────────────────────────


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="运行辩论 — 读取 Markdown + YAML front-matter 驱动多模型辩论",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  debate-tool run my_topic.md\n"
            "  debate-tool run my_topic.md --rounds 5\n"
            "  debate-tool run my_topic.md --dry-run\n"
            "  debate-tool run my_topic.md --cross-exam\n"
            "  debate-tool run my_topic.md --cross-exam 3\n"
            "  debate-tool run my_topic.md --cross-exam -1\n"
            "  debate-tool run my_topic.md --cross-exam --early-stop\n"
            "\n"
            "质询:\n"
            "  --cross-exam [N]  每轮后增加质询子回合 (默认 N=1, 仅 R1 后)\n"
            "                    N=2 → R1, R2 后均质询; N=-1 → 每轮都质询\n"
            "\n"
            "早停:\n"
            "  --early-stop      启用收敛早停 (观点趋同时跳过剩余轮次)\n"
            "\n"
            "环境变量:\n"
            "  DEBATE_API_KEY    API 密钥\n"
            "  DEBATE_BASE_URL   API 端点\n"
            "\n"
            "也可在 topic 文件的 YAML front-matter 中设置 base_url / api_key\n"
            "优先级: front-matter > 环境变量\n"
        ),
    )
    ap.add_argument(
        "topic", type=Path, help="议题 Markdown 文件（含 YAML front-matter）"
    )
    ap.add_argument("--rounds", type=int, default=None, help="覆盖辩论轮数")
    ap.add_argument("--dry-run", action="store_true", help="仅解析配置，不调用 LLM")
    ap.add_argument(
        "--cross-exam",
        nargs="?",
        type=int,
        const=1,
        default=None,
        metavar="N",
        help="质询轮数 (默认 1; -1=每轮都质询)",
    )
    ap.add_argument(
        "--early-stop",
        nargs="?",
        type=float,
        const=DEFAULT_EARLY_STOP_THRESHOLD,
        default=None,
        metavar="T",
        help="启用收敛早停 (默认阈值 0.55; 可指定 0~1 之间的值)",
    )
    ap.add_argument(
        "--cot",
        "--think",
        dest="cot_length",
        nargs="?",
        type=int,
        const=0,
        default=None,
        metavar="LENGTH",
        help="为辩手启用思考空间 (CoT)。LENGTH 为可选思考 token 预算，省略则不限制。",
    )

    args = ap.parse_args(argv)

    # 验证文件存在
    topic_path = args.topic.resolve()
    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    # 解析配置
    cfg = parse_topic_file(topic_path)

    # ── CLI 覆盖 ──
    # --cross-exam: CLI > YAML > 默认 0
    if args.cross_exam is not None:
        cfg["cross_exam"] = args.cross_exam

    # --early-stop: CLI > YAML
    if args.early_stop is not None:
        cfg["early_stop"] = args.early_stop

    # --rounds 总是覆盖
    if args.rounds is not None:
        cfg["rounds"] = args.rounds

    # --cot: CLI > YAML > None (disabled)
    # args.cot_length: None=not provided, 0=--cot without value, N=--cot=N
    cli_cot = args.cot_length  # None | 0 | positive int

    # 确保默认值
    cfg.setdefault("cross_exam", 0)
    cfg.setdefault("early_stop", 0.0)

    # 解析与校验 API 配置
    effective_url = (cfg["base_url"] or ENV_BASE_URL).strip()
    effective_key = (cfg["api_key"] or ENV_API_KEY).strip()
    api_issues = _validate_api_config(cfg)

    # Dry run — 打印配置后退出
    if args.dry_run:
        stem = topic_path.stem
        out_dir = topic_path.parent
        print("=" * 60)
        print(f"  🔍 Dry Run — {cfg['title']}")
        print("=" * 60)
        print(f"\n  文件:     {topic_path}")
        print(f"  轮数:     {cfg['rounds']}")
        cx = cfg.get("cross_exam", 0)
        if cx < 0:
            print(f"  质询:     每轮")
        elif cx == 1:
            print(f"  质询:     R1 后")
        elif cx > 1:
            print(f"  质询:     R1~R{cx} 后")
        else:
            print(f"  质询:     否")
        print(
            f"  早停:     {'是 (阈值 {:.0%})'.format(cfg.get('early_stop', 0.0)) if cfg.get('early_stop') else '否'}"
        )
        effective_cot = cli_cot if cli_cot is not None else cfg.get("cot_length", None)
        if effective_cot is not None:
            if effective_cot > 0:
                print(f"  CoT:      是 (思考预算 {effective_cot} token)")
            else:
                print(f"  CoT:      是 (无预算限制)")
        else:
            print(f"  CoT:      否")
        print(f"  超时:     {cfg['timeout']}s")
        print(f"  max_reply_tokens: {cfg['max_reply_tokens']}")
        print(f"\n  辩手:")
        for d in cfg["debaters"]:
            print(f"    - {d['name']} ({d['model']}) — {d['style']}")
        j = cfg["judge"]
        print(
            f"\n  裁判:     {j['name']} ({j['model']}, max_tokens={j.get('max_tokens', 8000)})"
        )
        if cfg["constraints"]:
            print(f"\n  约束:\n    {cfg['constraints'][:200]}")
        print(f"\n  议题 (前 300 字):\n    {cfg['topic_body'][:300]}...")
        print(f"\n  输出:")
        print(f"    日志:   {out_dir / f'{stem}_debate_log.md'}")
        print(f"    总结:   {out_dir / f'{stem}_debate_summary.md'}")
        print(f"\n  API:     {effective_url}")
        print(f"  API Key: {_mask_key(effective_key) if effective_key else '(未设置)'}")
        if cfg["base_url"]:
            print("  (来源: front-matter)")
        elif os.environ.get("DEBATE_BASE_URL"):
            print("  (来源: 环境变量)")
        else:
            print("  (来源: 未设置)")
        if api_issues:
            print("\n  ⚠️ API 配置不完整:")
            for issue in api_issues:
                print(f"    - {issue}")
            print(
                "    请通过 front-matter（全局/辩手/裁判）或环境变量补齐 base_url / api_key"
            )
        print(f"\n  Round 1: {cfg['round1_task'][:80]}...")
        print(f"  Middle:  {cfg['middle_task'][:80]}...")
        print(f"  Final:   {cfg['final_task'][:80]}...")
        if cfg["judge_instructions"]:
            print(f"  Judge:   {cfg['judge_instructions'][:80]}...")
        print("\n✅ 配置有效")
        return

    if api_issues:
        print(
            "❌ 缺少 API 配置:\n  - "
            + "\n  - ".join(api_issues)
            + "\n请设置 DEBATE_BASE_URL / DEBATE_API_KEY，或在 topic front-matter 提供全局/辩手/裁判级 base_url / api_key",
            file=sys.stderr,
        )
        sys.exit(2)

    # 正式运行
    asyncio.run(run(cfg, topic_path, cot_length=cli_cot))


if __name__ == "__main__":
    main()
