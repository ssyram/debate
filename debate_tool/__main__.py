"""debate-tool — 多模型辩论框架

用法:
    python -m debate_tool <command> [options]
    debate-tool <command> [options]

命令:
    run      运行辩论
    resume   续跑辩论（同一日志 append，支持意见注入）
    compact  手动压缩日志（生成 checkpoint）
    modify   修改 topic 配置（辩手/裁判/立场）并记录变更
    live     启动辩论 + Web 实时查看器

示例:
    debate-tool run my_topic.md
    debate-tool resume my_topic_debate_log.json my_topic.md --message "请重点讨论安全性"
    debate-tool resume my_topic_debate_log.json my_topic.md --rounds 2 --cross-exam
    debate-tool compact my_log.json --compress ALL
    debate-tool compact my_log.json --compress -2
    debate-tool modify my_topic.md --set debater.A.model=gpt-5
    debate-tool modify my_topic.md --add "C|kimi-k2.5|激进派风格" --reason "增加新辩手"
    debate-tool modify my_topic.md --drop B --force
    debate-tool modify my_topic.md --pivot "A|新的立场描述"
    debate-tool live my_topic.md
"""

import re
import sys


def _print_help():
    print(__doc__.strip())


def _normalize_argv(argv: list[str]) -> list[str]:
    """Normalize CLI flags: lowercase + '_' → '-' for argparse compatibility.

    Positional args and flag values are left untouched.
    Only tokens starting with '--' are normalised:
      --Cross_Exam  →  --cross-exam
      --NO_JUDGE    →  --no-judge
      --Rounds      →  --rounds
    """
    result: list[str] = []
    for token in argv:
        if token.startswith("--"):
            if "=" in token:
                flag, val = token.split("=", 1)
                flag = "--" + re.sub(r"[_\-]+", "-", flag[2:].lower())
                result.append(f"{flag}={val}")
            else:
                result.append("--" + re.sub(r"[_\-]+", "-", token[2:].lower()))
        elif token.startswith("-") and len(token) == 2:
            result.append(token)
        else:
            result.append(token)
    return result


def _handle_resume(argv):
    import argparse
    from pathlib import Path

    argv = _normalize_argv(argv)

    parser = argparse.ArgumentParser(prog="debate-tool resume")
    parser.add_argument("log_file", type=Path, help="v2 日志文件 (.json)")
    parser.add_argument("resume_topic", type=Path, nargs="?", default=None,
                        help="Resume Topic 文件 (.md, 可选)")
    parser.add_argument("--rounds", "-r", type=int, default=1,
                        help="追加轮数 (默认 1, 0=仅执行 judge)")
    parser.add_argument("--message", "-m", default="", help="观察者消息")
    parser.add_argument("--guide", default="", help="辩手引导提示")
    parser.add_argument("--cross-exam", nargs="?", const="1", default=None,
                        dest="cross_exam",
                        help="质询: N=前N轮, -1/ALL/*=全轮, [1,3,5]=指定轮次")
    parser.add_argument("--cot", nargs="?", const=True, default=None,
                        dest="cot", help="CoT 长度")
    parser.add_argument("--force", action="store_true", help="跳过一致性校验；add/drop 辩手时必须指定")
    parser.add_argument("--no-judge", action="store_true", dest="no_judge", help="跳过裁判总结阶段")
    parser.add_argument("--output-summary", type=Path, default=None, metavar="SUMMARY_FILE", dest="output_summary", help="指定总结文件输出路径")
    parser.add_argument("--debug", nargs="?", const=True, default=None, metavar="DEBUG_LOG",
                        help="开启 debug 日志，可选文件路径")
    args = parser.parse_args(argv)

    if args.debug is not None:
        from debate_tool.debug_log import init_debug_logging
        init_debug_logging(args.debug)

    cot_length = None
    if args.cot is not None:
        if args.cot is True:
            cot_length = 0
        else:
            try:
                cot_length = int(args.cot)
            except (ValueError, TypeError):
                cot_length = 0

    cfg_overrides: "dict | None" = None

    import asyncio
    from debate_tool.resume import resume
    asyncio.run(resume(
        log_path=args.log_file,
        resume_topic_path=args.resume_topic,
        message=args.message,
        extra_rounds=args.rounds,
        cross_exam=args.cross_exam,
        guide_prompt=args.guide,
        force=args.force,
        cot_length=cot_length,
        cfg_overrides=cfg_overrides,
        summary_path=args.output_summary,
        no_judge=args.no_judge,
    ))


def _handle_compact(argv):
    import argparse
    from pathlib import Path

    argv = _normalize_argv(argv)

    parser = argparse.ArgumentParser(
        description="手动压缩辩论日志 — 生成 checkpoint 写入日志",
    )
    parser.add_argument("log", type=Path, help="辩论日志文件 (*_debate_log.json)")
    parser.add_argument(
        "--compress",
        "-c",
        type=str,
        default="ALL",
        help=(
            "压缩范围（向后兼容参数，新版 LLM 压缩忽略此参数）: "
            "ALL=全部压缩(默认), "
            "N(正数)=从后往前压缩N条, "
            "-N(负数)=保留最后N条其余全压"
        ),
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=60000,
        help="checkpoint 的 token 预算（向后兼容参数，新版 LLM 压缩忽略此参数，默认 60000）",
    )
    parser.add_argument(
        "--topic",
        type=Path,
        default=None,
        metavar="TOPIC_FILE",
        help="议题 Markdown 文件（含 compact_model 等配置）；不提供时自动在日志同目录查找",
    )
    parser.add_argument(
        "--message",
        "-m",
        default="",
        help="compact 附加指令（优先级最高，覆盖 topic/log 内嵌的 compact_message）",
    )
    parser.add_argument(
        "--debug",
        nargs="?",
        const=True,
        metavar="DEBUG_LOG",
        help="开启 debug 日志，可选文件路径",
    )
    args = parser.parse_args(argv)

    log_path = args.log.resolve()
    if not log_path.exists():
        print(f"❌ 文件不存在: {log_path}", file=sys.stderr)
        sys.exit(1)

    topic_path = args.topic.resolve() if args.topic else None

    from debate_tool.runner import compact_log
    from debate_tool.debug_log import init_debug_logging
    debug_target = args.debug if hasattr(args, 'debug') and args.debug is not None else None
    init_debug_logging(debug_target)

    compact_log(log_path, keep_last=0, token_budget=args.token_budget, topic_path=topic_path, message=args.message)


def _handle_live(argv):
    import argparse
    import threading
    import time
    import webbrowser

    argv = _normalize_argv(argv)

    parser = argparse.ArgumentParser(
        description="启动辩论 + Web 实时查看器",
    )
    parser.add_argument(
        "topic",
        nargs="?",
        help="议题 Markdown 文件（可选，也可在网页中选择）",
    )
    parser.add_argument("--port", "-p", type=int, default=5000)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    from debate_tool.web.app import create_app

    app = create_app()

    if args.topic:
        from pathlib import Path

        topic_path = Path(args.topic).resolve()
        if not topic_path.exists():
            print(
                f"❌ 文件不存在: {topic_path}", file=sys.stderr
            )
            sys.exit(1)
        app.config["AUTO_START_TOPIC"] = str(topic_path)

    url = f"http://{args.host}:{args.port}/debate/"
    if not args.no_browser:

        def _open():
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  辩论实时查看器 (Web)")
    print(f"  {url}\n")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


def main():
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        _print_help()
        sys.exit(0)

    if argv[0] in ("-V", "--version"):
        from debate_tool import __version__

        print(f"debate-tool {__version__}")
        sys.exit(0)

    command = argv[0].lower()
    remaining = argv[1:]

    if command == "run":
        from debate_tool.runner import main as run_main

        run_main(_normalize_argv(remaining) or None)
    elif command == "resume":
        _handle_resume(remaining)
    elif command == "compact":
        _handle_compact(remaining)
    elif command == "live":
        _handle_live(remaining)
    else:
        print(f"未知命令: {command}\n", file=sys.stderr)
        _print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
