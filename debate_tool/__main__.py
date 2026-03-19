"""debate-tool \u2014 \u591a\u6a21\u578b\u8fa9\u8bba\u6846\u67b6

\u7528\u6cd5:
    python -m debate_tool <command> [options]
    debate-tool <command> [options]

\u547d\u4ee4:
    run      \u8fd0\u884c\u8fa9\u8bba
    resume   \u7eed\u8dd1\u8fa9\u8bba\uff08\u540c\u4e00\u65e5\u5fd7 append\uff0c\u652f\u6301\u610f\u89c1\u6ce8\u5165\uff09
    compact  \u624b\u52a8\u538b\u7f29\u65e5\u5fd7\uff08\u751f\u6210 checkpoint\uff09
    modify   \u4fee\u6539 topic \u914d\u7f6e\uff08\u8fa9\u624b/\u88c1\u5224/\u7acb\u573a\uff09\u5e76\u8bb0\u5f55\u53d8\u66f4
    live     \u542f\u52a8\u8fa9\u8bba + Web \u5b9e\u65f6\u67e5\u770b\u5668

\u793a\u4f8b:
    debate-tool run my_topic.md
    debate-tool resume my_topic_debate_log.json my_topic.md --message "\u8bf7\u91cd\u70b9\u8ba8\u8bba\u5b89\u5168\u6027"
    debate-tool resume my_topic_debate_log.json my_topic.md --rounds 2 --cross-exam
    debate-tool compact my_log.json --compress ALL
    debate-tool compact my_log.json --compress -2
    debate-tool modify my_topic.md --set debater.A.model=gpt-5
    debate-tool modify my_topic.md --add "C|kimi-k2.5|\u6fc0\u8fdb\u6d3e\u98ce\u683c" --reason "\u589e\u52a0\u65b0\u8fa9\u624b"
    debate-tool modify my_topic.md --drop B --force
    debate-tool modify my_topic.md --pivot "A|\u65b0\u7684\u7acb\u573a\u63cf\u8ff0"
    debate-tool live my_topic.md
"""

import sys


def _print_help():
    print(__doc__.strip())


def _handle_resume(argv):
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="debate-tool resume")
    parser.add_argument("log_file", type=Path, help="v2 日志文件 (.json)")
    parser.add_argument("resume_topic", type=Path, nargs="?", default=None,
                        help="Resume Topic 文件 (.md, 可选)")
    parser.add_argument("--rounds", "-r", type=int, default=1,
                        help="追加轮数 (默认 1, 0=仅执行 judge)")
    parser.add_argument("--message", "-m", default="", help="观察者消息")
    parser.add_argument("--guide", default="", help="辩手引导提示")
    parser.add_argument("--cross-exam", nargs="?", const=1, default=None,
                        type=int, dest="cross_exam",
                        help="质询频率 (不填=不质询, --cross-exam=N)")
    parser.add_argument("--cot", nargs="?", const=True, default=None,
                        dest="cot", help="CoT 长度")
    parser.add_argument("--force", action="store_true", help="跳过一致性校验；add/drop 辩手时必须指定")
    parser.add_argument("--debug", default="", help="Debug 标志")
    args = parser.parse_args(argv)

    # debug 设置
    if args.debug:
        import os
        os.environ["DEBATE_DEBUG"] = args.debug

    # cot_length 解析
    cot_length = None
    if args.cot is not None:
        if args.cot is True:
            cot_length = 0  # unlimited
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
    ))


def _handle_compact(argv):
    import argparse
    from pathlib import Path

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

    parser = argparse.ArgumentParser(
        description="\u542f\u52a8\u8fa9\u8bba + Web \u5b9e\u65f6\u67e5\u770b\u5668",
    )
    parser.add_argument(
        "topic",
        nargs="?",
        help="\u8bae\u9898 Markdown \u6587\u4ef6\uff08\u53ef\u9009\uff0c\u4e5f\u53ef\u5728\u7f51\u9875\u4e2d\u9009\u62e9\uff09",
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
                f"\u274c \u6587\u4ef6\u4e0d\u5b58\u5728: {topic_path}", file=sys.stderr
            )
            sys.exit(1)
        app.config["AUTO_START_TOPIC"] = str(topic_path)

    url = f"http://{args.host}:{args.port}/debate/"
    if not args.no_browser:

        def _open():
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  \u8fa9\u8bba\u5b9e\u65f6\u67e5\u770b\u5668 (Web)")
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

    command = argv[0]
    remaining = argv[1:]

    if command == "run":
        from debate_tool.runner import main as run_main

        run_main(remaining or None)
    elif command == "resume":
        _handle_resume(remaining)
    elif command == "compact":
        _handle_compact(remaining)
    elif command == "live":
        _handle_live(remaining)
    else:
        print(f"\u672a\u77e5\u547d\u4ee4: {command}\n", file=sys.stderr)
        _print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
