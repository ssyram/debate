"""debate-tool — 多模型辩论框架

用法:
    python -m debate_tool <command> [options]
    debate-tool <command> [options]

命令:
    run     运行辩论
    build   生成辩论配置（向导）
    stance  生成辩手立场推荐

示例:
    debate-tool run my_topic.md
    debate-tool run my_topic.md --rounds 5 --dry-run
    debate-tool run my_topic.md --cross-exam
    debate-tool run my_topic.md --cross-exam 3
    debate-tool run my_topic.md --cross-exam -1
    debate-tool run my_topic.md --cross-exam --early-stop
    debate-tool run my_topic.md --early-stop 0.6
    debate-tool build
    debate-tool build --cli
    debate-tool stance my_topic.md --num 5
"""
import sys


def _print_help():
    print(__doc__.strip())


def _handle_build(argv):
    """Route build subcommand to web or CLI wizard."""
    use_cli = "--cli" in argv
    remaining = [a for a in argv if a != "--cli"]

    if use_cli:
        from debate_tool.wizard import main as wizard_main
        wizard_main(remaining or None)
    else:
        from debate_tool.web.__main__ import main as web_main
        web_main(remaining or None)


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
    elif command in ("build", "start"):
        _handle_build(remaining)
    elif command == "stance":
        from debate_tool.stance import main as stance_main
        stance_main(remaining or None)
    else:
        print(f"未知命令: {command}\n", file=sys.stderr)
        _print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
