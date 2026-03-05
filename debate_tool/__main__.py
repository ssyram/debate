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
    stance   \u751f\u6210\u8fa9\u624b\u7acb\u573a\u63a8\u8350

\u793a\u4f8b:
    debate-tool run my_topic.md
    debate-tool resume my_topic.md --message "\u8bf7\u91cd\u70b9\u8ba8\u8bba\u5b89\u5168\u6027"
    debate-tool resume my_topic.md --rounds 2 --cross-exam
    debate-tool compact my_log.md --compress ALL
    debate-tool compact my_log.md --compress -2
    debate-tool modify my_topic.md --set debater.A.model=gpt-5
    debate-tool modify my_topic.md --add "C|kimi-k2.5|\u6fc0\u8fdb\u6d3e\u98ce\u683c" --reason "\u589e\u52a0\u65b0\u8fa9\u624b"
    debate-tool modify my_topic.md --drop B --force
    debate-tool modify my_topic.md --pivot "A|\u65b0\u7684\u7acb\u573a\u63cf\u8ff0"
    debate-tool live my_topic.md
    debate-tool stance my_topic.md --num 5
"""

import sys


def _print_help():
    print(__doc__.strip())


def _handle_resume(argv):
    import argparse
    import asyncio
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="续跑辩论 — 在已有日志基础上追加轮次",
    )
    parser.add_argument("topic", type=Path, help="议题 Markdown 文件")
    parser.add_argument(
        "--message", "-m", type=str, default="", help="注入观察者消息（问题/意见/指导）"
    )
    parser.add_argument(
        "--rounds", "-r", type=int, default=1, help="追加辩论轮数 (默认 1)"
    )
    parser.add_argument("--cross-exam", action="store_true", help="续跑轮次间启用质询")
    parser.add_argument("--guide", type=str, default="", help="辩手引导提示")
    parser.add_argument("--no-judge", action="store_true", help="续跑后不执行裁判总结")
    parser.add_argument(
        "--force", action="store_true", help="跳过 topic/log 一致性校验"
    )
    parser.add_argument(
        "--cot",
        "--think",
        dest="enable_cot",
        action="store_true",
        help="为辩手启用思考空间 (CoT)，思考内容不记入日志（--debug 除外）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试模式：将辩手思考过程也写入日志",
    )
    args = parser.parse_args(argv)

    topic_path = args.topic.resolve()
    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    from debate_tool.runner import parse_topic_file, resume

    cfg = parse_topic_file(topic_path)
    asyncio.run(
        resume(
            cfg,
            topic_path,
            message=args.message,
            extra_rounds=args.rounds,
            cross_exam=args.cross_exam,
            guide_prompt=args.guide,
            judge_at_end=not args.no_judge,
            force=args.force,
            enable_cot=args.enable_cot,
            debug=args.debug,
        )
    )


def _handle_compact(argv):
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="手动压缩辩论日志 — 生成 checkpoint 写入日志",
    )
    parser.add_argument("log", type=Path, help="辩论日志文件 (*_debate_log.md)")
    parser.add_argument(
        "--compress",
        "-c",
        type=str,
        default="ALL",
        help=(
            "压缩范围: "
            "ALL=全部压缩(默认), "
            "N(正数)=从后往前压缩N条, "
            "-N(负数)=保留最后N条其余全压"
        ),
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=60000,
        help="checkpoint 的 token 预算 (默认 60000)",
    )
    args = parser.parse_args(argv)

    log_path = args.log.resolve()
    if not log_path.exists():
        print(f"❌ 文件不存在: {log_path}", file=sys.stderr)
        sys.exit(1)

    from debate_tool.runner import compact_log, Log

    log = Log.load_from_file(log_path)
    total = len(log.entries)

    compress_val = args.compress.strip()
    if compress_val.upper() == "ALL":
        keep_last = 0
    else:
        n = int(compress_val)
        if n >= 0:
            keep_last = max(total - n, 0)
        else:
            keep_last = abs(n)

    compact_log(log_path, keep_last=keep_last, token_budget=args.token_budget)


def _handle_modify(argv):
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="修改 topic 配置并追加变更事件到 log",
    )
    parser.add_argument("topic", type=Path, help="议题 Markdown 文件")
    parser.add_argument(
        "--set",
        dest="set_fields",
        action="append",
        default=[],
        metavar="KEY=VAL",
        help="设置字段，如 debater.A.model=gpt-5、judge.model=claude、rounds=3",
    )
    parser.add_argument(
        "--add",
        dest="add_debaters",
        action="append",
        default=[],
        metavar="name|model|style",
        help="添加辩手，格式: name|model|style",
    )
    parser.add_argument(
        "--drop",
        dest="drop_debaters",
        action="append",
        default=[],
        metavar="NAME",
        help="移除辩手",
    )
    parser.add_argument(
        "--pivot",
        dest="pivot_stances",
        action="append",
        default=[],
        metavar="name|new_style",
        help="变更辩手立场（扬弃），格式: name|new_style",
    )
    parser.add_argument("--reason", type=str, default="", help="变更原因说明")
    parser.add_argument("--force", action="store_true", help="跳过一致性警告强制执行")
    args = parser.parse_args(argv)

    topic_path = args.topic.resolve()
    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    from debate_tool.runner import modify_topic

    modify_topic(
        topic_path,
        set_fields=args.set_fields,
        add_debaters=args.add_debaters,
        drop_debaters=args.drop_debaters,
        pivot_stances=args.pivot_stances,
        reason=args.reason,
        force=args.force,
    )


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
    elif command == "modify":
        _handle_modify(remaining)
    elif command == "live":
        _handle_live(remaining)
    elif command == "stance":
        from debate_tool.stance import main as stance_main

        stance_main(remaining or None)
    else:
        print(f"\u672a\u77e5\u547d\u4ee4: {command}\n", file=sys.stderr)
        _print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
