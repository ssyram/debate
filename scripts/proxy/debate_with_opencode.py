#!/usr/bin/env python3
"""
scripts/debate_with_opencode.py

启动器：解析 topic 文件，自动为 localhost proxy debater 启动 opencode_proxy，
然后运行辩论（输出实时透传），同时定期打印各 OpenCode session 的最新动态，
结束后自动清理所有 proxy 进程。

用法：
    python3 scripts/debate_with_opencode.py examples/xxx/topic.md [--rounds N] [--cross-exam [N]] [--opencode-url URL] [--monitor-interval N]

Topic 文件中，需要 opencode session 的辩手配置示例：
    debaters:
      - name: 辩手A
        model: yunwu/claude-sonnet-4-6      # provider/model，proxy 自动解析
        base_url: http://localhost:8081/v1/chat/completions
        api_key: dummy
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml  # debate_tool 已依赖 pyyaml


# ── 解析 topic ───────────────────────────────────────────────────────────────

def _load_topic_debaters(topic_path: Path) -> list[dict]:
    text = topic_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []
    front = text[3:end]
    cfg = yaml.safe_load(front) or {}
    return cfg.get("debaters", [])


def _is_localhost(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname in ("localhost", "127.0.0.1", "::1")


def _extract_port(url: str) -> int | None:
    parsed = urllib.parse.urlparse(url)
    return parsed.port or {"http": 80, "https": 443}.get(parsed.scheme)


def _parse_model(model_str: str) -> tuple[str, str]:
    if "/" in model_str:
        parts = model_str.split("/", 1)
        return parts[0], parts[1]
    return "", model_str


# ── OpenCode session 监控 ────────────────────────────────────────────────────

def _get_proxy_session_id(proxy_port: int) -> str | None:
    try:
        url = f"http://localhost:{proxy_port}/health"
        with urllib.request.urlopen(url, timeout=2) as r:
            data = json.loads(r.read())
            return data.get("session")
    except Exception:
        return None


def _get_session_latest(opencode_url: str, session_id: str) -> str | None:
    """获取 session 最新一条消息的摘要。"""
    try:
        url = f"{opencode_url.rstrip('/')}/session/{session_id}/message"
        with urllib.request.urlopen(url, timeout=3) as r:
            msgs = json.loads(r.read())
        if not msgs:
            return None
        last = msgs[-1]
        role = last.get("info", {}).get("role", "?")
        parts = last.get("parts", [])
        text = ""
        for p in parts:
            if p.get("type") == "text":
                text = p.get("text", "")
                break
            if p.get("type") == "tool-invocation":
                inv = p.get("toolInvocation", {})
                text = f"[tool: {inv.get('toolName','?')}]"
                break
            if p.get("type") == "tool-result":
                text = f"[tool-result: {str(p.get('result',''))[:80]}]"
                break
        # 截断显示
        text = text.replace("\n", " ").strip()
        if len(text) > 120:
            text = text[:120] + "…"
        return f"{role}: {text}" if text else f"{role}: (no text)"
    except Exception as e:
        return f"(读取失败: {e})"


def _monitor_sessions(
    debaters: list[dict],
    opencode_url: str,
    interval: float,
    stop_event: threading.Event,
) -> None:
    """后台线程：每隔 interval 秒打印各 session 最新动态。"""
    # 找到所有 localhost debater 的端口和名字
    targets = []
    for d in debaters:
        url = d.get("base_url", "")
        if _is_localhost(url):
            port = _extract_port(url)
            if port:
                targets.append((d.get("name", f"port:{port}"), port))

    if not targets:
        return

    while not stop_event.wait(interval):
        lines = []
        for name, port in targets:
            session_id = _get_proxy_session_id(port)
            if not session_id:
                lines.append(f"  [{name}] session 未创建")
                continue
            latest = _get_session_latest(opencode_url, session_id)
            lines.append(f"  [{name}] {latest or '(无消息)'}")
        if lines:
            print("\n\033[36m── Session 动态 ──────────────────────────────\033[0m", flush=True)
            for l in lines:
                print(f"\033[36m{l}\033[0m", flush=True)
            print(flush=True)


# ── 启动 proxy ───────────────────────────────────────────────────────────────

def _wait_proxy_ready(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://localhost:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _free_port(port: int) -> None:
    """Kill any process occupying the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except Exception:
                pass
        if pids:
            time.sleep(0.5)
    except Exception:
        pass


def start_proxies(
    debaters: list[dict],
    opencode_url: str,
    cwd: str,
    topic_path: "Path | None" = None,
) -> list[subprocess.Popen]:
    script = Path(__file__).parent / "opencode_proxy.py"
    procs: list[subprocess.Popen] = []
    ports_to_wait: list[int] = []

    for d in debaters:
        base_url = d.get("base_url", "")
        if not _is_localhost(base_url):
            continue

        port = _extract_port(base_url)
        if not port:
            print(f"[launcher] 警告：无法解析 {d['name']} 的端口，跳过", file=sys.stderr)
            continue

        model_str = d.get("model", "")
        provider_id, model_id = _parse_model(model_str)
        if not provider_id:
            print(
                f"[launcher] 警告：{d['name']} model '{model_str}' 无 provider"
                f"（格式应为 provider/model），跳过",
                file=sys.stderr,
            )
            continue

        name = d.get("name", f"debater_{port}")
        log_file = Path(f"/tmp/proxy_{port}.log")

        # Compact state file path: {topic_stem}_compact_state.json (predictable)
        compact_state_args: list[str] = []
        if topic_path is not None:
            cs_path = topic_path.parent / f"{topic_path.stem}_compact_state.json"
            compact_state_args = ["--compact-state-file", str(cs_path)]

        cmd = [
            sys.executable, str(script),
            "--port", str(port),
            "--opencode-url", opencode_url,
            "--provider-id", provider_id,
            "--model-id", model_id,
            "--debater-name", name,
            "--cwd", cwd,
            *compact_state_args,
        ]

        # 先清理可能占用该端口的旧进程
        _free_port(port)

        print(f"[launcher] 启动 proxy: {name} → {provider_id}/{model_id} @ :{port}", file=sys.stderr)
        with open(log_file, "w") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=lf)
        procs.append(proc)
        ports_to_wait.append(port)

    if ports_to_wait:
        print(f"[launcher] 等待 proxy 就绪…", file=sys.stderr)
        for port in ports_to_wait:
            ok = _wait_proxy_ready(port)
            status = "✓" if ok else "✗ 超时"
            print(f"[launcher] {status} proxy:{port}", file=sys.stderr)

    return procs


def stop_proxies(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    if procs:
        print(f"\n[launcher] 已停止 {len(procs)} 个 proxy", file=sys.stderr)


# ── 主入口 ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="自动启动 opencode proxy 并运行 debate-tool，实时透传输出 + 监控 session 动态"
    )
    parser.add_argument("topic", help="topic.md 文件路径")
    parser.add_argument("--rounds", "-r", type=int, help="辩论轮数")
    parser.add_argument("--cross-exam", nargs="?", const=1, type=int, metavar="N")
    parser.add_argument("--opencode-url", default="http://localhost:4096", help="OpenCode URL（默认 http://localhost:4096）")
    parser.add_argument("--cwd", default=str(Path(__file__).parent.parent), help="proxy 工作目录")
    parser.add_argument("--monitor-interval", type=float, default=20.0, help="session 监控间隔秒数（默认 20）")
    args = parser.parse_args()

    topic_path = Path(args.topic).resolve()
    if not topic_path.exists():
        print(f"错误：topic 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    debaters = _load_topic_debaters(topic_path)

    # 检查 OpenCode 可用性
    localhost_debaters = [d for d in debaters if _is_localhost(d.get("base_url", ""))]
    if localhost_debaters:
        try:
            urllib.request.urlopen(args.opencode_url, timeout=3).close()
            print(f"[launcher] ✓ OpenCode 连通：{args.opencode_url}", file=sys.stderr)
        except Exception:
            print(f"[launcher] ✗ OpenCode 在 {args.opencode_url} 无响应！", file=sys.stderr)
            sys.exit(1)

    # 启动 proxy
    procs = start_proxies(debaters, args.opencode_url, args.cwd, topic_path=topic_path)

    # 启动 session 监控线程
    stop_monitor = threading.Event()
    if localhost_debaters and args.monitor_interval > 0:
        monitor_thread = threading.Thread(
            target=_monitor_sessions,
            args=(debaters, args.opencode_url, args.monitor_interval, stop_monitor),
            daemon=True,
        )
        monitor_thread.start()
    else:
        monitor_thread = None

    # 注册清理
    def _cleanup(signum=None, frame=None):
        stop_monitor.set()
        stop_proxies(procs)
        sys.exit(1 if signum else 0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # 构建并运行 debate-tool（输出直接透传到 stdout/stderr）
    cmd = [sys.executable, "-m", "debate_tool", "run", str(topic_path)]
    if args.rounds:
        cmd += ["--rounds", str(args.rounds)]
    if args.cross_exam is not None:
        cmd += ["--cross-exam", str(args.cross_exam)]

    print(f"[launcher] 运行辩论：{' '.join(cmd)}", file=sys.stderr)
    print("=" * 60, flush=True)

    try:
        result = subprocess.run(cmd)  # 不捕获 stdout/stderr，直接透传
    finally:
        stop_monitor.set()
        if monitor_thread:
            monitor_thread.join(timeout=2)
        stop_proxies(procs)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
