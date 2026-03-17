#!/usr/bin/env python3
"""debate-tool 安装脚本

默认全量安装所有依赖；安装失败的包会精确报告影响哪个组件，不阻塞其余安装。

也支持命令行参数按需选装。

用法:
    python install.py                    # 全量安装（推荐）
    python install.py --all              # 同上
    python install.py --core             # 仅核心依赖
    python install.py --web              # 核心 + Web UI 依赖
    python install.py --skill            # 仅安装 Claude Code Skill
    python install.py --env              # 仅写入 DEBATE_TOOL_DIR 环境变量
    python install.py --core --skill     # 组合使用
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ─── 常量 ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_SRC = SCRIPT_DIR / ".claude" / "commands" / "debate.md"
SKILL_DST = Path.home() / ".claude" / "commands" / "debate.md"
MARKER = "# debate-tool"

# 每个包 -> 影响的组件描述 和 涉及的文件
PACKAGE_COMPONENT_MAP: dict[str, tuple[str, list[str]]] = {
    "httpx": ("核心辩论引擎", ["debate_tool/runner.py"]),
    "pyyaml": (
        "核心辩论引擎（YAML 解析）",
        ["debate_tool/runner.py", "debate_tool/core.py"],
    ),
    "flask": (
        "Web 向导界面",
        ["debate_tool/web/app.py", "debate_tool/web/__main__.py"],
    ),
}

# 依赖分组
CORE_PACKAGES = ["httpx", "pyyaml"]
WEB_PACKAGES = ["flask>=3.0"]

ALL_PACKAGES = CORE_PACKAGES + WEB_PACKAGES

# 分组 -> 受影响的功能说明
GROUP_INFO = {
    "core": (
        "核心依赖",
        CORE_PACKAGES,
        "运行辩论引擎 (debate-tool run/resume/compact/modify)",
    ),
    "web": (
        "Web UI 依赖",
        WEB_PACKAGES,
        "Web 向导 + 实时查看器 (debate-tool live)",
    ),
}


# ─── 工具函数 ────────────────────────────────────────────────────────────────


def _pip_cmd() -> list[str]:
    """返回 pip 调用命令列表。"""
    return [sys.executable, "-m", "pip"]


def _install_packages(packages: list[str]) -> dict[str, bool]:
    """逐个安装包，返回 {包名: 是否成功}。"""
    results: dict[str, bool] = {}
    for pkg in packages:
        # 提取纯包名用于显示 (去掉版本约束)
        name = re.split(r"[><=!]", pkg)[0]
        cmd = _pip_cmd() + ["install", pkg]
        print(f"  $ pip install {pkg}")
        rc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if rc.returncode == 0:
            print(f"    ✓ {name}")
            results[name] = True
        else:
            stderr = rc.stderr.decode(errors="replace").strip()
            # 只打印最后几行错误
            err_lines = stderr.splitlines()[-3:]
            print(f"    ✗ {name} 安装失败")
            for line in err_lines:
                print(f"      {line}")
            results[name] = False
    return results


def _report_failures(results: dict[str, bool]) -> None:
    """汇总报告安装失败的包及其影响的组件。"""
    failures = {k: v for k, v in results.items() if not v}
    if not failures:
        return

    print()
    print("┌─────────────────────────────────────────────────────┐")
    print("│  以下依赖安装失败，对应组件将无法使用：              │")
    print("├─────────────────────────────────────────────────────┤")
    for pkg in failures:
        comp, files = PACKAGE_COMPONENT_MAP.get(pkg, (pkg, []))
        file_list = ", ".join(files) if files else "—"
        print(f"│  ✗ {pkg:<20s} → {comp}")
        print(f"│    涉及文件: {file_list}")
    print("└─────────────────────────────────────────────────────┘")

    # 给出可运行的组件
    print()
    print("可用组件:")
    successes = {k for k, v in results.items() if v}
    core_ok = {"httpx", "pyyaml"}.issubset(successes)
    web_ok = core_ok and "flask" in successes

    print(f"  {'✓' if core_ok else '✗'} debate-tool run/resume/compact/modify 辩论引擎")
    print(f"  {'✓' if web_ok else '✗'} debate-tool live  Web UI")


# ─── 安装动作 ────────────────────────────────────────────────────────────────


def install_requirements(variant: str) -> dict[str, bool]:
    """安装指定变体的 Python 依赖。variant: core | web | all"""
    if variant == "all":
        packages = list(ALL_PACKAGES)
    elif variant == "core":
        packages = list(CORE_PACKAGES)
    elif variant == "web":
        packages = list(CORE_PACKAGES + WEB_PACKAGES)
    else:
        print(f"  ✗ 未知的安装变体: {variant}")
        return {}

    group_name = (
        "全部依赖" if variant == "all" else GROUP_INFO.get(variant, (variant,))[0]
    )
    header(f"安装 Python 依赖 [{group_name}]")

    return _install_packages(packages)


def install_skill() -> bool:
    """安装 Claude Code /debate Skill 到全局目录。"""
    header("安装 Claude Code Skill")

    if not SKILL_SRC.exists():
        print(f"  ✗ Skill 源文件不存在: {SKILL_SRC}")
        return False

    SKILL_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SRC, SKILL_DST)
    print(f"  ✓ Skill 已安装: {SKILL_DST}")
    return True


def install_env_var() -> bool:
    """将 DEBATE_TOOL_DIR 写入 shell profile。"""
    header("设置环境变量 DEBATE_TOOL_DIR")

    if os.name == "nt":
        cmd = f'setx DEBATE_TOOL_DIR "{SCRIPT_DIR}"'
        print(f"  $ {cmd}")
        rc = subprocess.run(cmd, shell=True).returncode
        if rc == 0:
            print(f"  ✓ DEBATE_TOOL_DIR={SCRIPT_DIR}")
        else:
            print(f"  ✗ 设置失败 (exit {rc})")
        return rc == 0

    profile = _detect_profile()
    export_line = f'export DEBATE_TOOL_DIR="{SCRIPT_DIR}"'
    tagged_line = f"{export_line}  {MARKER}"

    if profile.exists():
        content = profile.read_text()
        if MARKER in content:
            content = re.sub(
                rf"^.*{re.escape(MARKER)}.*$",
                tagged_line,
                content,
                flags=re.MULTILINE,
            )
            profile.write_text(content)
            print(f"  ✓ 已更新 {profile} 中的 DEBATE_TOOL_DIR")
            return True

    with open(profile, "a") as f:
        f.write(f"\n{tagged_line}\n")
    print(f"  ✓ 已写入 {profile}")
    print(f"  DEBATE_TOOL_DIR={SCRIPT_DIR}")
    print(f"  运行 'source {profile}' 或打开新终端以生效")
    return True


def _detect_profile() -> Path:
    """检测当前 shell 的 profile 文件。"""
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return Path.home() / ".zshrc"
    if (Path.home() / ".bash_profile").exists():
        return Path.home() / ".bash_profile"
    return Path.home() / ".bashrc"


# ─── 辅助 ───────────────────────────────────────────────────────────────────


def header(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ─── 交互式菜单 ──────────────────────────────────────────────────────────────

MENU = """\
debate-tool 安装向导
====================

请选择安装方式（输入编号，多选用逗号分隔）:

  [1] 全量安装（推荐） 所有 Python 依赖（httpx, pyyaml, flask）
  [2] 仅核心依赖       httpx, pyyaml — 仅运行辩论引擎
  [3] 核心 + Web UI    核心 + flask — Web 向导 + 实时查看器
  [4] Claude Code Skill 安装 /debate 命令到 Claude Code
  [5] 环境变量          设置 DEBATE_TOOL_DIR
  [6] 一键全装          全部依赖 + Skill + 环境变量

  [q] 退出
"""


def interactive() -> None:
    """交互式安装菜单。"""
    print(MENU)
    raw = input("请输入选项编号: ").strip()
    if not raw or raw.lower() == "q":
        print("已取消。")
        return

    choices = {c.strip() for c in raw.replace(" ", ",").split(",")}

    if "6" in choices:
        choices = {"1", "4", "5"}

    all_results: dict[str, bool] = {}

    if "1" in choices:
        all_results.update(install_requirements("all"))
    else:
        if "2" in choices:
            all_results.update(install_requirements("core"))
        if "3" in choices:
            all_results.update(install_requirements("web"))

    if "4" in choices:
        install_skill()

    if "5" in choices:
        install_env_var()

    if all_results:
        _report_failures(all_results)

    header("完成")


# ─── CLI 入口 ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="debate-tool 安装脚本 — 默认全量安装，失败时报告受影响的组件",
        epilog="不带参数进入交互式菜单。",
    )
    parser.add_argument(
        "--core", action="store_true", help="安装核心依赖 (httpx, pyyaml)"
    )
    parser.add_argument(
        "--web", action="store_true", help="安装 Web UI 依赖 (核心 + flask)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="install_all",
        help="安装全部 Python 依赖（默认行为）",
    )
    parser.add_argument(
        "--skill", action="store_true", help="安装 Claude Code /debate Skill"
    )
    parser.add_argument(
        "--env", action="store_true", help="设置 DEBATE_TOOL_DIR 环境变量"
    )
    args = parser.parse_args()

    has_flag = any([args.core, args.web, args.install_all, args.skill, args.env])
    if not has_flag:
        interactive()
        return

    all_results: dict[str, bool] = {}

    if args.install_all:
        all_results.update(install_requirements("all"))
    else:
        if args.core:
            all_results.update(install_requirements("core"))
        if args.web:
            all_results.update(install_requirements("web"))

    if args.skill:
        install_skill()

    if args.env:
        install_env_var()

    if all_results:
        _report_failures(all_results)

    header("完成")


if __name__ == "__main__":
    main()
