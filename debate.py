#!/usr/bin/env python3
"""
通用辩论框架 — 读取 Markdown + YAML front-matter 驱动多模型辩论。

用法:
    python debate.py my_topic.md
    python debate.py my_topic.md --rounds 5
    python debate.py my_topic.md --dry-run
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import yaml

# ── 环境变量 ────────────────────────────────────────────
ENV_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
ENV_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()

DEFAULT_DEBATERS = [
    {"name": "GPT-5.2",    "model": "gpt-5.2",          "style": "务实工程派"},
    {"name": "Kimi-K2.5",  "model": "kimi-k2.5",        "style": "创新挑战派"},
    {"name": "Sonnet-4-6", "model": "claude-sonnet-4-6", "style": "严谨分析派"},
]
DEFAULT_JUDGE = {"model": "claude-opus-4-6", "name": "Opus-4-6 (裁判)", "max_tokens": 8000}


# ── YAML Front-matter 解析 ───────────────────────────────

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
    }
    return cfg


# ── LLM 调用 ─────────────────────────────────────────────

async def call_llm(model: str, system: str, user_content: str,
                   *, temperature: float = 0.7, max_tokens: int = 6000,
                   timeout: int = 300,
                   base_url: str = "", api_key: str = "") -> str:
    """调用 LLM API，支持 per-debate 的 base_url/api_key 覆盖。"""
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
                r = await c.post(f"{url}/chat/completions",
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
        icon = {"summary": "⚖️ 裁判"}.get(tag, "💬")
        print(f"\n{'='*60}\n[{e['seq']}] {icon} {name}\n{'='*60}")
        t = content
        print(t[:800] + "\n...(见日志)" if len(t) > 800 else t)
        self._flush()

    def _flush(self):
        lines = [f"# {self.title} 辩论日志\n\n> {datetime.now().isoformat()}\n\n---\n"]
        for e in self.entries:
            label = {"summary": "⚖️ **裁判总结**"}.get(e["tag"], "")
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
    # Per-debate API config
    debate_base_url = cfg.get("base_url", "")
    debate_api_key = cfg.get("api_key", "")

    print("=" * 60)
    print(f"  {cfg['title']}")
    print(f"  {rounds} 轮 | 辩手: {', '.join(d['name'] for d in debaters)}")
    print(f"  裁判: {judge['name']}")
    if debate_base_url:
        print(f"  API: {debate_base_url}")
    print("=" * 60)

    last_seq = 0

    for rnd in range(1, rounds + 1):
        print(f"\n\n📢 第 {rnd}/{rounds} 轮\n")
        new_log = log.since(last_seq)

        # 构建 user context
        if rnd == 1:
            user_ctx = f"## 辩论议题\n\n{topic}"
            task_desc = cfg["round1_task"]
        elif rnd == rounds:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            task_desc = cfg["final_task"]
        else:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            task_desc = cfg["middle_task"]

        # 构建约束段落
        constraints_block = ""
        if constraints:
            constraints_block = f"\n\n核心约束：\n{constraints}"

        async def speak(d, rnd=rnd, task_desc=task_desc,
                        user_ctx=user_ctx, constraints_block=constraints_block):
            sys_prompt = (f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮。\n\n"
                          f"任务：{task_desc}"
                          f"{constraints_block}")
            return await call_llm(d["model"], sys_prompt, user_ctx,
                                  max_tokens=max_tokens, timeout=timeout,
                                  base_url=debate_base_url, api_key=debate_api_key)

        mark = log.entries[-1]["seq"] if log.entries else 0
        results = await asyncio.gather(*[speak(d) for d in debaters])
        for d, resp in zip(debaters, results):
            log.add(d["name"], resp)
        last_seq = mark

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
    summary = await call_llm(judge["model"], judge_sys,
                             f"全部辩论（压缩版）：\n\n{log.compact()}",
                             temperature=0.3, max_tokens=judge_max_tokens,
                             timeout=timeout,
                             base_url=debate_base_url, api_key=debate_api_key)
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


def _validate_api_config(base_url: str, api_key: str) -> list[str]:
    missing: list[str] = []
    if not base_url.strip():
        missing.append("base_url")
    if not api_key.strip():
        missing.append("api_key")
    return missing


# ── CLI ───────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="通用辩论框架 — 读取 Markdown + YAML front-matter 驱动多模型辩论",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python debate.py my_topic.md\n"
            "  python debate.py my_topic.md --rounds 5\n"
            "  python debate.py my_topic.md --dry-run\n"
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
    args = ap.parse_args()

    # 验证文件存在
    topic_path = args.topic.resolve()
    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    # 解析配置
    cfg = parse_topic_file(topic_path)

    # CLI 覆盖
    if args.rounds is not None:
        cfg["rounds"] = args.rounds

    # 解析实际使用的 API 配置（用于 dry-run 显示）
    effective_url = cfg["base_url"] or ENV_BASE_URL
    effective_key = cfg["api_key"] or ENV_API_KEY
    missing_api = _validate_api_config(effective_url, effective_key)

    # Dry run — 打印配置后退出
    if args.dry_run:
        stem = topic_path.stem
        out_dir = topic_path.parent
        print("=" * 60)
        print(f"  🔍 Dry Run — {cfg['title']}")
        print("=" * 60)
        print(f"\n  文件:     {topic_path}")
        print(f"  轮数:     {cfg['rounds']}")
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
            print(f"  (来源: front-matter)")
        elif os.environ.get("DEBATE_BASE_URL"):
            print(f"  (来源: 环境变量)")
        else:
            print(f"  (来源: 未设置)")
        if missing_api:
            print("\n  ⚠️ API 配置不完整: " + ", ".join(missing_api))
            print("    请在 front-matter 或环境变量中提供 base_url / api_key")
        print(f"\n  Round 1: {cfg['round1_task'][:80]}...")
        print(f"  Middle:  {cfg['middle_task'][:80]}...")
        print(f"  Final:   {cfg['final_task'][:80]}...")
        if cfg["judge_instructions"]:
            print(f"  Judge:   {cfg['judge_instructions'][:80]}...")
        print(f"\n✅ 配置有效")
        return

    if missing_api:
        print(
            "❌ 缺少 API 配置: " + ", ".join(missing_api) +
            "。请设置 DEBATE_BASE_URL / DEBATE_API_KEY 或在 topic front-matter 提供 base_url / api_key",
            file=sys.stderr,
        )
        sys.exit(2)

    # 正式运行
    asyncio.run(run(cfg, topic_path))


if __name__ == "__main__":
    main()
