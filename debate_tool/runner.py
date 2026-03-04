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
    DEFAULT_DEBATERS, DEFAULT_JUDGE, DEFAULT_EARLY_STOP_THRESHOLD,
    check_convergence,
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
        "title":       front.get("title", path.stem),
        "rounds":      front.get("rounds", 3),
        "timeout":     front.get("timeout", 300),
        "max_tokens":  front.get("max_tokens", 6000),
        "debaters":    front.get("debaters", DEFAULT_DEBATERS),
        "judge":       {**DEFAULT_JUDGE, **front.get("judge", {})},
        "constraints": front.get("constraints", "").strip(),
        "round1_task": front.get("round1_task",
                                 "针对各议题给出立场和建议，每个 200-300 字").strip(),
        "middle_task": front.get("middle_task",
                                 "回应其他辩手观点，深化立场，400-600 字").strip(),
        "final_task":  front.get("final_task",
                                 "最终轮，给出最终建议，标注优先级，300-500 字").strip(),
        "judge_instructions": front.get("judge_instructions", "").strip(),
        "topic_body":  body,
        # API 配置：front-matter > 环境变量
        "base_url":    front.get("base_url", "").strip(),
        "api_key":     front.get("api_key", "").strip(),
        # Mode fields
        "cross_exam":  int(front.get("cross_exam", 0)),
        "early_stop":  _parse_early_stop(front.get("early_stop", False)),
    }
    return cfg


# ── LLM 调用 ─────────────────────────────────────────────

async def call_llm(model: str, system: str, user_content: str,
                   *, temperature: float = 0.7, max_tokens: int = 6000,
                   timeout: int = 300,
                   base_url: str = "", api_key: str = "") -> str:
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
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=timeout) as c:
        for attempt in range(3):
            try:
                r = await c.post(url.rstrip('/'),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"},
                                 json=payload)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                if attempt == 2:
                    return f"[调用失败: {e}]"
                print(f"  ⚠️ {model} retry {attempt+1}: {e}", file=sys.stderr)
                await asyncio.sleep(2 ** attempt)
    return "[调用失败]"


# ── 日志 ──────────────────────────────────────────────────

class Log:
    def __init__(self, path: Path, title: str):
        self.path = path
        self.title = title
        self.entries: list[dict] = []

    def add(self, name: str, content: str, tag: str = ""):
        e = {"seq": len(self.entries)+1, "ts": datetime.now().isoformat(),
             "tag": tag, "name": name, "content": content}
        self.entries.append(e)
        icon = {"summary": "⚖️ 裁判", "cross_exam": "🔍"}.get(tag, "💬")
        print(f"\n{'='*60}\n[{e['seq']}] {icon} {name}\n{'='*60}")
        t = content
        print(t[:800] + "\n...(见日志)" if len(t) > 800 else t)
        self._flush()

    def _flush(self):
        lines = [f"# {self.title} 辩论日志\n\n> {datetime.now().isoformat()}\n\n---\n"]
        for e in self.entries:
            label = {"summary": "⚖️ **裁判总结**", "cross_exam": "🔍 **质询**"}.get(e["tag"], "")
            hdr = f"[{e['seq']}] {label}" if label else f"[{e['seq']}] {e['name']}"
            lines.append(f"\n### {hdr}\n\n*{e['ts']}*\n\n{e['content']}\n\n---\n")
        self.path.write_text("\n".join(lines), encoding="utf-8")

    def since(self, after_seq: int) -> str:
        news = [e for e in self.entries if e["seq"] > after_seq]
        if not news:
            return "(无新内容)"
        return "\n\n".join(
            f"--- {e['name']} ---\n{e['content']}" for e in news)

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

async def run_cross_exam(debaters: list[dict], log: Log, topic: str,
                         rnd: int,
                         *, max_tokens: int, timeout: int,
                         debate_base_url: str, debate_api_key: str):
    """Round-robin cross-examination after a debate round.

    Pairing: d1→d2, d2→d3, ..., dN→d1.
    Each questioner references the target's latest speech and poses 2-3 challenges.
    """
    n = len(debaters)
    # Collect latest round speeches (last N entries in log)
    latest_entries = log.entries[-n:]
    speech_by_name: dict[str, str] = {e["name"]: e["content"] for e in latest_entries}

    for i in range(n):
        questioner = debaters[i]
        target = debaters[(i + 1) % n]
        target_speech = speech_by_name.get(target["name"], "(无发言)")

        q_base_url = (questioner.get("base_url", "") or debate_base_url).strip()
        q_api_key = (questioner.get("api_key", "") or debate_api_key).strip()

        sys_prompt = (
            f"你是「{questioner['name']}」（{questioner['style']}），"
            f"现在进入质询环节。\n\n"
            f"请针对「{target['name']}」的第 {rnd} 轮发言提出 2-3 个尖锐质疑，"
            f"指出其论证中的薄弱环节、遗漏或矛盾之处。"
        )
        user_ctx = (
            f"## 辩论议题\n\n{topic}\n\n"
            f"## {target['name']} 的第 {rnd} 轮发言\n\n{target_speech}"
        )

        result = await call_llm(
            questioner["model"], sys_prompt, user_ctx,
            max_tokens=max_tokens, timeout=timeout,
            base_url=q_base_url, api_key=q_api_key,
        )
        log.add(f"{questioner['name']} → {target['name']}", result, "cross_exam")


# ── 主流程 ────────────────────────────────────────────────

async def run(cfg: dict, topic_path: Path):
    stem = topic_path.stem
    out_dir = topic_path.parent

    log = Log(out_dir / f"{stem}_debate_log.md", cfg["title"])
    topic = cfg["topic_body"]
    debaters = cfg["debaters"]
    judge = cfg["judge"]
    rounds = cfg["rounds"]
    timeout = cfg["timeout"]
    max_tokens = cfg["max_tokens"]
    constraints = cfg["constraints"]
    cross_exam = cfg.get("cross_exam", 0)   # number of rounds with cross-exam
    early_stop = cfg.get("early_stop", 0.0)  # 0=off, (0,1)=threshold
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
    if flags:
        print(f"  [{', '.join(flags)}]")
    print(f"  {rounds} 轮 | 辩手: {', '.join(d['name'] for d in debaters)}")
    print(f"  裁判: {judge['name']}")
    if debate_base_url:
        print(f"  API: {debate_base_url}")
    print("=" * 60)

    last_seq = 0
    had_cross_exam_last = False

    for rnd in range(1, rounds + 1):
        print(f"\n\n📢 第 {rnd}/{rounds} 轮\n")
        new_log = log.since(last_seq)

        # ── Phase A: 并行辩手发言 ──
        if rnd == 1:
            user_ctx = f"## 辩论议题\n\n{topic}"
            task_desc = cfg["round1_task"]
        elif rnd == rounds:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            task_desc = cfg["final_task"]
        else:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            task_desc = cfg["middle_task"]

        # If cross_exam happened last round, ask debaters to respond to challenges
        if had_cross_exam_last:
            task_desc = (
                "逐条回应你收到的质询，指出对方质疑中的不当之处，"
                "并可修正自己的方案。400-600 字"
            )

        constraints_block = ""
        if constraints:
            constraints_block = f"\n\n核心约束：\n{constraints}"

        async def speak(d, rnd=rnd, task_desc=task_desc,
                        user_ctx=user_ctx, constraints_block=constraints_block):
            debater_base_url = (d.get("base_url", "") or debate_base_url).strip()
            debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
            sys_prompt = (f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮。\n\n"
                          f"任务：{task_desc}"
                          f"{constraints_block}")
            return await call_llm(d["model"], sys_prompt, user_ctx,
                                  max_tokens=max_tokens, timeout=timeout,
                                  base_url=debater_base_url, api_key=debater_api_key)

        mark = log.entries[-1]["seq"] if log.entries else 0
        results = await asyncio.gather(*[speak(d) for d in debaters])
        for d, resp in zip(debaters, results):
            log.add(d["name"], resp)
        last_seq = mark

        # ── Phase B: 早停检查 ──
        if early_stop and rnd < rounds:
            converged, avg_sim = check_convergence(results, early_stop)
            print(f"\n  📊 收敛检查: 平均相似度 {avg_sim:.1%} (阈值 {early_stop:.0%})")
            if converged:
                print("  ⚡ 观点已收敛，跳过剩余轮次，直接进入裁判阶段")
                break

        # ── Phase C: 质询（若当前轮在 cross_exam_rounds 中且非最后一轮） ──
        had_cross_exam_last = False
        if rnd in cross_exam_rounds and rnd < rounds:
            print(f"\n\n🔍 质询环节 (R{rnd}.5)\n")
            await run_cross_exam(
                debaters, log, topic, rnd,
                max_tokens=max_tokens, timeout=timeout,
                debate_base_url=debate_base_url, debate_api_key=debate_api_key,
            )
            had_cross_exam_last = True

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
            "## 三、完整修改清单")

    judge_sys = (f"你是辩论裁判（{judge['name']}），负责做出最终裁定。\n\n"
                 f"{judge_instructions}\n\n"
                 f"裁定规则：\n"
                 f"- 基于事实和数据\n"
                 f"- 引用辩论中的关键论据\n"
                 f"- 简洁、可操作")

    judge_max_tokens = judge.get("max_tokens", 8000)
    judge_base_url = (judge.get("base_url", "") or debate_base_url).strip()
    judge_api_key = (judge.get("api_key", "") or debate_api_key).strip()
    summary = await call_llm(judge["model"], judge_sys,
                             f"全部辩论（压缩版）：\n\n{log.compact()}",
                             temperature=0.3, max_tokens=judge_max_tokens,
                             timeout=timeout,
                             base_url=judge_base_url, api_key=judge_api_key)
    log.add(judge["name"], summary, "summary")

    sp = out_dir / f"{stem}_debate_summary.md"
    sp.write_text(f"# {cfg['title']} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}",
                  encoding="utf-8")

    print(f"\n✅ 完成！ 日志: {log.path} | 总结: {sp}")


def _mask_key(key: str) -> str:
    """Mask API key for display."""
    if len(key) <= 7:
        return "****"
    return key[:3] + "****" + key[-4:]


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
            issues.append(f"debaters[{idx}]({debater_name}): " + ", ".join(missing_fields))

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
    ap.add_argument("topic", type=Path, help="议题 Markdown 文件（含 YAML front-matter）")
    ap.add_argument("--rounds", type=int, default=None, help="覆盖辩论轮数")
    ap.add_argument("--dry-run", action="store_true", help="仅解析配置，不调用 LLM")
    ap.add_argument("--cross-exam", nargs="?", type=int, const=1, default=None,
                    metavar="N", help="质询轮数 (默认 1; -1=每轮都质询)")
    ap.add_argument("--early-stop", nargs="?", type=float, const=DEFAULT_EARLY_STOP_THRESHOLD,
                    default=None, metavar="T", help="启用收敛早停 (默认阈值 0.55; 可指定 0~1 之间的值)")

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
        print(f"  早停:     {'是 (阈值 {:.0%})'.format(cfg.get('early_stop', 0.0)) if cfg.get('early_stop') else '否'}")
        print(f"  超时:     {cfg['timeout']}s")
        print(f"  max_tok:  {cfg['max_tokens']}")
        print(f"\n  辩手:")
        for d in cfg["debaters"]:
            print(f"    - {d['name']} ({d['model']}) — {d['style']}")
        j = cfg["judge"]
        print(f"\n  裁判:     {j['name']} ({j['model']}, max_tokens={j.get('max_tokens', 8000)})")
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
            print("    请通过 front-matter（全局/辩手/裁判）或环境变量补齐 base_url / api_key")
        print(f"\n  Round 1: {cfg['round1_task'][:80]}...")
        print(f"  Middle:  {cfg['middle_task'][:80]}...")
        print(f"  Final:   {cfg['final_task'][:80]}...")
        if cfg["judge_instructions"]:
            print(f"  Judge:   {cfg['judge_instructions'][:80]}...")
        print("\n✅ 配置有效")
        return

    if api_issues:
        print(
            "❌ 缺少 API 配置:\n  - " + "\n  - ".join(api_issues) +
            "\n请设置 DEBATE_BASE_URL / DEBATE_API_KEY，或在 topic front-matter 提供全局/辩手/裁判级 base_url / api_key",
            file=sys.stderr,
        )
        sys.exit(2)

    # 正式运行
    asyncio.run(run(cfg, topic_path))


if __name__ == "__main__":
    main()
