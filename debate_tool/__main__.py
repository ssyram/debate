"""CLI entry point + wizard state machine."""
from __future__ import annotations

import copy
import curses
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from debate_tool.core import (
    DEFAULT_DEBATERS, DEFAULT_JUDGE, DEFAULT_ROUNDS,
    DEFAULT_BASE_URL, DEFAULT_API_KEY,
    DEFAULT_ROUND1_TASK, DEFAULT_MIDDLE_TASK, DEFAULT_FINAL_TASK,
    DEFAULT_JUDGE_INSTRUCTIONS, DEFAULT_CONSTRAINTS,
    is_curses_supported, detect_platform,
    generate_topic_file, write_topic_file,
    get_run_command, get_dryrun_command,
)
from debate_tool.ui import (
    StepResult, init_colors, TopicPreview, Layout,
    safe_addstr, is_esc, CP_ERROR, CP_NORMAL, CP_HELP,
)


def _import_steps() -> dict[str, Any]:
    """Lazy import step functions to avoid circular imports
    and allow compilation even if steps.py doesn't exist yet."""
    from debate_tool.steps import (
        step_title, step_output_path, step_rounds,
        step_base_url, step_api_key, step_topic_body,
        step_stance_generator, step_debaters, step_judge,
        step_constraints, step_round_tasks, step_judge_instructions,
        step_preview, step_success,
    )
    return {
        "step_title": step_title,
        "step_output_path": step_output_path,
        "step_rounds": step_rounds,
        "step_base_url": step_base_url,
        "step_api_key": step_api_key,
        "step_topic_body": step_topic_body,
        "step_stance_generator": step_stance_generator,
        "step_debaters": step_debaters,
        "step_judge": step_judge,
        "step_constraints": step_constraints,
        "step_round_tasks": step_round_tasks,
        "step_judge_instructions": step_judge_instructions,
        "step_preview": step_preview,
        "step_success": step_success,
    }


console = Console()


# -- Active field names mapped to step indices --------------------------------
_STEP_ACTIVE_FIELDS = {
    0: "title",
    1: "output_path",
    2: "rounds",
    3: "base_url",
    4: "api_key",
    5: "topic_body",
    6: "debaters",     # stance_generator populates debaters
    7: "debaters",
    8: "judge",
    9: "constraints",
    10: "round1_task",  # round_tasks covers 3 sub-items
    11: "judge_instructions",
    12: "",             # preview
    13: "",             # success
}


# ---------------------------------------------------------------------------
# Wizard state machine
# ---------------------------------------------------------------------------

def wizard_curses(
    stdscr: Any,
    output_hint: str | None,
    topic_file_content: str | None,
) -> None:
    """Main wizard flow inside curses."""
    init_colors()
    curses.curs_set(0)
    stdscr.keypad(True)

    steps = _import_steps()

    # -- State variables -------------------------------------------------------
    title = ""
    output_path = output_hint or ""
    rounds = DEFAULT_ROUNDS
    base_url = DEFAULT_BASE_URL
    api_key = DEFAULT_API_KEY
    topic_body = topic_file_content or ""
    debaters = [copy.deepcopy(d) for d in DEFAULT_DEBATERS]
    judge = copy.deepcopy(DEFAULT_JUDGE)
    constraints = DEFAULT_CONSTRAINTS
    round1_task = DEFAULT_ROUND1_TASK
    middle_task = DEFAULT_MIDDLE_TASK
    final_task = DEFAULT_FINAL_TASK
    judge_instructions = DEFAULT_JUDGE_INSTRUCTIONS

    preview = TopicPreview(
        title=title,
        output_path=output_path,
        rounds=rounds,
        base_url=base_url,
        api_key=api_key,
        debaters=debaters,
        judge=judge,
        constraints=constraints,
        round1_task=round1_task,
        middle_task=middle_task,
        final_task=final_task,
        judge_instructions=judge_instructions,
        topic_body=topic_body,
    )

    step = 0

    while step <= 13:
        max_y, max_x = stdscr.getmaxyx()
        if max_y < 12 or max_x < 50:
            stdscr.erase()
            safe_addstr(
                stdscr, 0, 0,
                "Terminal too small! Need 50x12 minimum.",
                curses.color_pair(CP_ERROR),
            )
            stdscr.refresh()
            key = stdscr.getch()
            if is_esc(stdscr, key):
                return
            continue

        lo = Layout(max_y, max_x)

        # Update active field highlight in preview
        preview.active_field = _STEP_ACTIVE_FIELDS.get(step, "")

        # ---- Step 0: title ---------------------------------------------------
        if step == 0:
            result = steps["step_title"](stdscr, preview, lo, title)
            if result is StepResult.BACK:
                return  # exit wizard
            title = result
            preview.title = title
            step = 1

        # ---- Step 1: output_path --------------------------------------------
        elif step == 1:
            result = steps["step_output_path"](stdscr, preview, lo, output_path, title)
            if result is StepResult.BACK:
                step = 0
                continue
            output_path = result
            preview.output_path = output_path
            step = 2

        # ---- Step 2: rounds -------------------------------------------------
        elif step == 2:
            result = steps["step_rounds"](stdscr, preview, lo, rounds)
            if result is StepResult.BACK:
                step = 1
                continue
            rounds = result
            preview.rounds = rounds
            step = 3

        # ---- Step 3: base_url -----------------------------------------------
        elif step == 3:
            result = steps["step_base_url"](stdscr, preview, lo, base_url)
            if result is StepResult.BACK:
                step = 2
                continue
            base_url = result
            preview.base_url = base_url
            step = 4

        # ---- Step 4: api_key ------------------------------------------------
        elif step == 4:
            result = steps["step_api_key"](stdscr, preview, lo, api_key)
            if result is StepResult.BACK:
                step = 3
                continue
            api_key = result
            preview.api_key = api_key
            step = 5

        # ---- Step 5: topic_body ---------------------------------------------
        elif step == 5:
            # Skip if topic_file_content was provided via CLI
            if topic_file_content is not None:
                step = 6
                continue
            result = steps["step_topic_body"](stdscr, preview, lo, topic_body)
            if result is StepResult.BACK:
                step = 4
                continue
            topic_body = result
            preview.topic_body = topic_body
            step = 6

        # ---- Step 6: stance_generator ---------------------------------------
        elif step == 6:
            # Skip stance_generator if no topic_body
            if not topic_body.strip():
                step = 7
                continue
            result = steps["step_stance_generator"](
                stdscr, preview, lo,
                topic_body, base_url, api_key, debaters,
            )
            if result is StepResult.BACK:
                # Go back to step 5, or step 4 if topic was provided via CLI
                step = 4 if topic_file_content is not None else 5
                continue
            if result is not None:
                # stance_generator returned a debater list
                debaters = result
            # else: keep current debaters (skipped)
            preview.debaters = debaters
            step = 7

        # ---- Step 7: debaters (>= 2 enforced) ------------------------------
        elif step == 7:
            result = steps["step_debaters"](stdscr, preview, lo, debaters)
            if result is StepResult.BACK:
                # Go back to stance_generator or topic_body
                if topic_body.strip():
                    step = 6
                elif topic_file_content is not None:
                    step = 4
                else:
                    step = 5
                continue
            debaters = result
            preview.debaters = debaters
            step = 8

        # ---- Step 8: judge --------------------------------------------------
        elif step == 8:
            result = steps["step_judge"](stdscr, preview, lo, judge)
            if result is StepResult.BACK:
                step = 7
                continue
            judge = result
            preview.judge = judge
            step = 9

        # ---- Step 9: constraints --------------------------------------------
        elif step == 9:
            result = steps["step_constraints"](stdscr, preview, lo, constraints)
            if result is StepResult.BACK:
                step = 8
                continue
            constraints = result
            preview.constraints = constraints
            step = 10

        # ---- Step 10: round_tasks (3 sub-items) ----------------------------
        elif step == 10:
            result = steps["step_round_tasks"](
                stdscr, preview, lo,
                round1_task, middle_task, final_task,
            )
            if result is StepResult.BACK:
                step = 9
                continue
            round1_task, middle_task, final_task = result
            preview.round1_task = round1_task
            preview.middle_task = middle_task
            preview.final_task = final_task
            step = 11

        # ---- Step 11: judge_instructions ------------------------------------
        elif step == 11:
            result = steps["step_judge_instructions"](
                stdscr, preview, lo, judge_instructions,
            )
            if result is StepResult.BACK:
                step = 10
                continue
            judge_instructions = result
            preview.judge_instructions = judge_instructions
            step = 12

        # ---- Step 12: preview (scrollable) ----------------------------------
        elif step == 12:
            config = {
                "title": title,
                "rounds": rounds,
                "base_url": base_url,
                "api_key": api_key,
                "debaters": debaters,
                "judge": judge,
                "constraints": constraints,
                "round1_task": round1_task,
                "middle_task": middle_task,
                "final_task": final_task,
                "judge_instructions": judge_instructions,
                "topic_body": topic_body,
            }
            file_content = generate_topic_file(config)
            out_path = Path(output_path)

            result = steps["step_preview"](
                stdscr, preview, lo, file_content, out_path,
            )
            if result is StepResult.BACK:
                step = 11
                continue
            # result is True → write file and proceed
            write_topic_file(out_path, file_content)
            step = 13

        # ---- Step 13: success -----------------------------------------------
        elif step == 13:
            out_path = Path(output_path)
            run_cmd = get_run_command(out_path)
            dryrun_cmd = get_dryrun_command(out_path)
            steps["step_success"](stdscr, preview, lo, out_path, run_cmd, dryrun_cmd)
            return


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--output", "-o", type=click.Path(), default=None,
    help="默认输出路径",
)
@click.option(
    "--topic-file", "-t", type=click.Path(exists=True), default=None,
    help="从文件读取辩论正文（跳过正文输入步骤）",
)
def main(output: str | None, topic_file: str | None) -> None:
    """交互式向导 — 生成辩论议题 Markdown 文件"""
    topic_file_content: str | None = None
    if topic_file is not None:
        raw = Path(topic_file).read_text(encoding="utf-8")
        # Strip YAML front-matter if present
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                topic_file_content = parts[2].strip()
            else:
                topic_file_content = raw.strip()
        else:
            topic_file_content = raw.strip()

    if not is_curses_supported():
        console.print("\n[yellow]Curses TUI 不支持当前终端[/yellow]")
        console.print("请使用 template.md 手动创建辩论文件:")
        console.print("  cp template.md my_topic.md")
        console.print("  # 编辑 my_topic.md")
        console.print("  python debate.py my_topic.md")
        return

    try:
        curses.wrapper(wizard_curses, output, topic_file_content)
    except KeyboardInterrupt:
        console.print("\n[dim]已取消。[/dim]")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
