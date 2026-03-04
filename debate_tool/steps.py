"""Wizard step functions — one per wizard screen."""

from __future__ import annotations

import curses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from debate_tool.core import (
    DEFAULT_DEBATERS,
    DEFAULT_JUDGE,
    DEFAULT_ROUNDS,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_TOKENS,
    DEFAULT_BASE_URL,
    DEFAULT_API_KEY,
    DEFAULT_ROUND1_TASK,
    DEFAULT_MIDDLE_TASK,
    DEFAULT_FINAL_TASK,
    DEFAULT_JUDGE_INSTRUCTIONS,
    DEFAULT_CONSTRAINTS,
    DEFAULT_DEBATE_MODELS,
    title_to_filename,
    mask_key,
    generate_topic_file,
    write_topic_file,
    get_run_command,
    get_dryrun_command,
)
from debate_tool.ui import (
    StepResult,
    TopicPreview,
    Layout,
    CP_INPUT_HL,
    CP_HEADER,
    CP_FILLED,
    CP_HELP,
    CP_ERROR,
    CP_NORMAL,
    CP_ACTIVE_BG,
    draw_frame,
    safe_addstr,
    safe_addstr_wrap,
    is_esc,
    curses_text_input,
    curses_radio_inline,
    curses_number_input,
    curses_multiline_input,
    curses_path_input,
)
from debate_tool.stance import (
    generate_stances_sync,
    check_stances,
    StanceResult,
)
from debate_tool.core import (
    DEFAULT_DEBATERS,
    DEFAULT_JUDGE,
    DEFAULT_ROUNDS,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_TOKENS,
    DEFAULT_BASE_URL,
    DEFAULT_API_KEY,
    DEFAULT_ROUND1_TASK,
    DEFAULT_MIDDLE_TASK,
    DEFAULT_FINAL_TASK,
    DEFAULT_JUDGE_INSTRUCTIONS,
    DEFAULT_CONSTRAINTS,
    DEFAULT_DEBATE_MODELS,
    title_to_filename,
    mask_key,
    generate_topic_file,
    write_topic_file,
    get_run_command,
    get_dryrun_command,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEP_TITLES = [
    "Step 1/14 · 辩论标题",
    "Step 2/14 · 输出文件",
    "Step 3/14 · 辩论轮数",
    "Step 4/14 · API Base URL",
    "Step 5/14 · API Key",
    "Step 6/14 · 辩论议题",
    "Step 7/14 · AI 立场推荐",
    "Step 8/14 · 辩手配置",
    "Step 9/14 · 裁判配置",
    "Step 10/14 · 约束条件",
    "Step 11/14 · 各轮任务",
    "Step 12/14 · 裁判指令",
    "Step 13/14 · 预览",
    "完成",
]


# ---------------------------------------------------------------------------
# Stance workspace data model
# ---------------------------------------------------------------------------


@dataclass
class StanceItem:
    """A single debater item in the stance workspace."""

    name: str
    model: str
    style: str
    base_url: str = ""
    api_key: str = ""
    selected: bool = True
    source: str = "llm"  # "llm" or "custom"


# ---------------------------------------------------------------------------
# Step 0: Title
# ---------------------------------------------------------------------------


def step_title(
    stdscr: Any, preview: TopicPreview, lo: Layout, current: str
) -> str | object:
    """Step 1: Debate title input (required, non-empty)."""
    preview.active_field = "title"
    help_text = "Esc=退出  Enter=确认  输入辩论标题"

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[0], help_text, lo)
        safe_addstr(
            stdscr,
            lo.ri_y,
            lo.ri_x,
            "输入本次辩论的标题 (必填)",
            curses.color_pair(CP_NORMAL),
        )

    def _validate(val: str) -> str | None:
        if not val.strip():
            return "标题不能为空"
        return None

    _redraw()
    result = curses_text_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        default=current,
        validate=_validate,
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    return result.strip()


# ---------------------------------------------------------------------------
# Step 1: Output path
# ---------------------------------------------------------------------------


def step_output_path(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current: str,
    title: str,
) -> str | object:
    """Step 2: Output file path with Tab completion."""
    preview.active_field = "output_path"
    help_text = "Esc=返回  Tab=自动补全  Enter=确认"
    default_path = current or title_to_filename(title)

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[1], help_text, lo)
        safe_addstr(
            stdscr, lo.ri_y, lo.ri_x, "输出文件路径", curses.color_pair(CP_NORMAL)
        )
        # Show file-exists warning if applicable
        cur_path = Path(default_path)
        if cur_path.exists():
            safe_addstr(
                stdscr,
                lo.ri_y + 1,
                lo.ri_x,
                "文件已存在，将覆盖",
                curses.color_pair(CP_HEADER),
            )

    _redraw()
    result = curses_path_input(
        stdscr,
        lo.ri_y + 3,
        lo.ri_x,
        lo.ri_w,
        lo.ri_h - 3,
        default=default_path,
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    path_str = result.strip()
    # Show warning if file exists after user entered the path
    if Path(path_str).exists():
        safe_addstr(
            stdscr,
            lo.ri_y + 1,
            lo.ri_x,
            "文件已存在，将覆盖" + " " * 20,
            curses.color_pair(CP_HEADER),
        )
        stdscr.refresh()
    return path_str


# ---------------------------------------------------------------------------
# Step 2: Rounds
# ---------------------------------------------------------------------------


def step_rounds(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current: int,
) -> int | object:
    """Step 3: Number of debate rounds."""
    preview.active_field = "rounds"
    help_text = "Esc=返回  Enter=确认  范围 1-20"

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[2], help_text, lo)
        safe_addstr(
            stdscr, lo.ri_y, lo.ri_x, "辩论轮数 (1-20)", curses.color_pair(CP_NORMAL)
        )

    _redraw()
    result = curses_number_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        default=current,
        min_val=1,
        max_val=20,
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    return result


# ---------------------------------------------------------------------------
# Step 3: Base URL
# ---------------------------------------------------------------------------


def step_base_url(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current: str,
) -> str | object:
    """Step 4: API base URL (optional)."""
    preview.active_field = "base_url"
    help_text = "Esc=返回  Enter=确认"

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[3], help_text, lo)
        safe_addstr(
            stdscr,
            lo.ri_y,
            lo.ri_x,
            "API Base URL (可选，留空使用环境变量)",
            curses.color_pair(CP_NORMAL),
        )

    _redraw()
    result = curses_text_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        default=current,
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    return result.strip()


# ---------------------------------------------------------------------------
# Step 4: API Key
# ---------------------------------------------------------------------------


def step_api_key(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current: str,
) -> str | object:
    """Step 5: API key (optional)."""
    preview.active_field = "api_key"
    help_text = "Esc=返回  Enter=确认"

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[4], help_text, lo)
        safe_addstr(
            stdscr,
            lo.ri_y,
            lo.ri_x,
            "API Key (可选，留空使用 DEBATE_API_KEY 环境变量)",
            curses.color_pair(CP_NORMAL),
        )

    _redraw()
    result = curses_text_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        default=current,
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    return result.strip()


# ---------------------------------------------------------------------------
# Step 5: Topic body — inline or file
# ---------------------------------------------------------------------------


def step_topic_body(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    preloaded_text: str = "",
) -> str | object:
    """Step 6: Topic body — choose inline editor or file path."""
    preview.active_field = "topic_body"
    help_text = "Esc=返回  Enter=确认  ↑↓=选择"

    if preloaded_text:
        return preloaded_text

    # --- Radio: choose input method ---
    def _redraw_radio() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[5], help_text, lo)
        safe_addstr(
            stdscr, lo.ri_y, lo.ri_x, "选择议题输入方式:", curses.color_pair(CP_NORMAL)
        )

    _redraw_radio()
    choice = curses_radio_inline(
        stdscr,
        ["直接输入", "从文件读取"],
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        lo.ri_h - 2,
        redraw=_redraw_radio,
    )
    if choice is StepResult.BACK:
        return StepResult.BACK

    if choice == 0:
        # Inline multiline editor
        help_text_edit = "Ctrl+D=确认  Esc=返回  ↑↓=移动"

        def _redraw_editor() -> None:
            stdscr.erase()
            draw_frame(stdscr, preview, STEP_TITLES[5], help_text_edit, lo)
            safe_addstr(
                stdscr,
                lo.ri_y,
                lo.ri_x,
                "输入辩论议题内容:",
                curses.color_pair(CP_NORMAL),
            )

        _redraw_editor()
        result = curses_multiline_input(
            stdscr,
            lo.ri_y + 2,
            lo.ri_x,
            lo.ri_w,
            lo.ri_h - 2,
            default=preview.topic_body,
            redraw=_redraw_editor,
        )
        if result is StepResult.BACK:
            return StepResult.BACK
        return result.strip()

    # choice == 1: Read from file
    help_text_file = "Esc=返回  Tab=补全  Enter=确认"

    def _redraw_file() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[5], help_text_file, lo)
        safe_addstr(
            stdscr, lo.ri_y, lo.ri_x, "输入议题文件路径:", curses.color_pair(CP_NORMAL)
        )

    def _validate_file(val: str) -> str | None:
        if not val.strip():
            return "文件路径不能为空"
        if not Path(val.strip()).exists():
            return f"文件不存在: {val.strip()}"
        return None

    _redraw_file()
    file_path = curses_path_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        lo.ri_h - 2,
        validate=_validate_file,
        redraw=_redraw_file,
    )
    if file_path is StepResult.BACK:
        return StepResult.BACK

    # Read the file content
    p = Path(file_path.strip())
    content = p.read_text(encoding="utf-8")

    # Strip YAML front-matter if present
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    # Show brief preview and confirm
    lines = content.strip().split("\n")
    preview_lines = lines[:3]

    stdscr.erase()
    draw_frame(stdscr, preview, STEP_TITLES[5], "Enter=确认  Esc=重选", lo)
    safe_addstr(
        stdscr,
        lo.ri_y,
        lo.ri_x,
        f"文件: {p.name} ({len(lines)} 行)",
        curses.color_pair(CP_FILLED),
    )
    safe_addstr(
        stdscr, lo.ri_y + 1, lo.ri_x, "─" * min(lo.ri_w, 30), curses.color_pair(CP_HELP)
    )
    for i, line in enumerate(preview_lines):
        safe_addstr(
            stdscr,
            lo.ri_y + 2 + i,
            lo.ri_x,
            line[: lo.ri_w],
            curses.color_pair(CP_NORMAL),
        )
    if len(lines) > 3:
        safe_addstr(
            stdscr,
            lo.ri_y + 5,
            lo.ri_x,
            f"... ({len(lines) - 3} 行省略)",
            curses.color_pair(CP_NORMAL) | curses.A_DIM,
        )
    safe_addstr(
        stdscr,
        lo.ri_y + 7,
        lo.ri_x,
        "使用此内容？(Enter=是, Esc=重选)",
        curses.color_pair(CP_HEADER),
    )
    stdscr.refresh()

    while True:
        key = stdscr.getch()
        if is_esc(stdscr, key):
            return step_topic_body(stdscr, preview, lo)
        if key in (curses.KEY_ENTER, 10, 13):
            return content.strip()


# ---------------------------------------------------------------------------
# Step 6: Stance generator — complex mini state machine
# ---------------------------------------------------------------------------


def _render_stance_workspace(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    items: list[StanceItem],
    cursor: int,
    scroll_top: int,
    message: str = "",
) -> None:
    """Render the stance workspace in the right panel."""
    stdscr.erase()
    draw_frame(
        stdscr,
        preview,
        STEP_TITLES[6],
        "[C] 继续  [R] 重新  [V] 检查  [A] 添加  [D] 删除  [E] 编辑  Enter=确认  Esc=跳过",
        lo,
    )

    y = lo.ri_y
    x = lo.ri_x
    w = lo.ri_w
    max_rows = lo.ri_h - 4  # reserve bottom rows for status + message

    # Header
    safe_addstr(
        stdscr, y, x, "AI 立场推荐", curses.color_pair(CP_HEADER) | curses.A_BOLD
    )
    y += 1

    # Item list
    if not items:
        safe_addstr(stdscr, y, x, "(空)", curses.color_pair(CP_NORMAL) | curses.A_DIM)
    else:
        visible_count = min(len(items) - scroll_top, max_rows)
        for vi in range(visible_count):
            idx = scroll_top + vi
            if idx >= len(items):
                break
            item = items[idx]
            is_cur = idx == cursor

            # Build display line
            check = "[x]" if item.selected else "[ ]"
            src_tag = "✦" if item.source == "custom" else ""

            label = f"{item.name} | {item.model} | {item.style}"
            line = f"  {check} {src_tag}{label}"

            if is_cur:
                attr = curses.color_pair(CP_INPUT_HL) | curses.A_BOLD
            elif item.selected:
                attr = curses.color_pair(CP_FILLED)
            else:
                attr = curses.color_pair(CP_NORMAL) | curses.A_DIM

            safe_addstr(stdscr, y + vi, x, line[:w], attr)

    # Separator + status at bottom
    status_y = lo.ri_y + lo.ri_h - 3
    selected_count = sum(1 for it in items if it.selected)
    safe_addstr(stdscr, status_y, x, "─" * min(w, 30), curses.color_pair(CP_HELP))
    safe_addstr(
        stdscr,
        status_y + 1,
        x,
        f"已选择: {selected_count} 位辩手",
        curses.color_pair(CP_FILLED)
        if selected_count >= 2
        else curses.color_pair(CP_ERROR),
    )

    # Message line
    if message:
        safe_addstr(stdscr, status_y + 2, x, message[:w], curses.color_pair(CP_ERROR))


def step_stance_generator(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    topic_body: str,
    base_url: str,
    api_key: str,
    current_debaters: list[dict[str, str]],
) -> list[dict[str, str]] | None | object:
    """Step 7: AI stance recommendation — mini state machine."""
    preview.active_field = "debaters"
    help_text = "Esc=返回  Enter=确认  ↑↓=选择"

    # --- Phase 1: Ask whether to use AI recommendation ---
    def _redraw_ask() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[6], help_text, lo)
        safe_addstr(
            stdscr,
            lo.ri_y,
            lo.ri_x,
            "是否使用 AI 推荐辩手立场？",
            curses.color_pair(CP_NORMAL),
        )

    _redraw_ask()
    choice = curses_radio_inline(
        stdscr,
        ["是", "否"],
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        lo.ri_h - 2,
        redraw=_redraw_ask,
    )
    if choice is StepResult.BACK:
        return StepResult.BACK
    if choice == 1:
        return None  # Skip, use defaults

    # --- Phase 2: Generate stances ---
    stdscr.erase()
    draw_frame(stdscr, preview, STEP_TITLES[6], "请稍候...", lo)
    safe_addstr(
        stdscr, lo.ri_y + 2, lo.ri_x, "正在分析议题...", curses.color_pair(CP_HELP)
    )
    stdscr.refresh()

    result = generate_stances_sync(topic_body, base_url=base_url, api_key=api_key)

    # Build items list from LLM result
    items: list[StanceItem] = []
    for d in result.debaters:
        items.append(
            StanceItem(
                name=d.name,
                model=d.model,
                style=d.style,
                selected=True,
                source="llm",
                base_url="",
                api_key="",
            )
        )

    # --- Phase 3: Interactive workspace ---
    cursor = 0
    scroll_top = 0
    message = ""

    while True:
        _render_stance_workspace(
            stdscr, preview, lo, items, cursor, scroll_top, message
        )
        stdscr.refresh()
        curses.curs_set(0)
        key = stdscr.getch()
        message = ""

        if is_esc(stdscr, key):
            if not items:
                return None
            # Confirm abandoning
            safe_addstr(
                stdscr,
                lo.ri_y + lo.ri_h - 1,
                lo.ri_x,
                "放弃已选立场？(y/n)",
                curses.color_pair(CP_ERROR),
            )
            stdscr.refresh()
            confirm_key = stdscr.getch()
            if confirm_key in (ord("y"), ord("Y")):
                return None
            continue

        if key in (curses.KEY_UP, ord("k")):
            if items:
                cursor = (cursor - 1) % len(items)
                if cursor < scroll_top:
                    scroll_top = cursor
            continue

        if key in (curses.KEY_DOWN, ord("j")):
            if items:
                cursor = (cursor + 1) % len(items)
                max_visible = lo.ri_h - 5
                if cursor >= scroll_top + max_visible:
                    scroll_top = cursor - max_visible + 1
            continue

        if key == ord(" "):
            # Toggle selection — any item, regardless of source
            if items:
                items[cursor].selected = not items[cursor].selected
            continue

        if key in (curses.KEY_ENTER, 10, 13):
            # Confirm: check count
            selected_count = sum(1 for it in items if it.selected)
            if selected_count < 2:
                message = "至少需要 2 位辩手"
                continue
            # Build return list
            debater_list = []
            for it in items:
                if it.selected:
                    row = {
                        "name": it.name,
                        "model": it.model,
                        "style": it.style,
                    }
                    if it.base_url.strip():
                        row["base_url"] = it.base_url.strip()
                    if it.api_key.strip():
                        row["api_key"] = it.api_key.strip()
                    debater_list.append(row)
            return debater_list

        if key in (ord("a"), ord("A")):
            # Add custom debater
            _add_custom_debater(stdscr, preview, lo, items)
            if items:
                cursor = len(items) - 1
            continue

        if key in (ord("c"), ord("C")):
            # Continue generating
            extra_prompt = _ask_extra_prompt(stdscr, preview, lo)
            if extra_prompt is StepResult.BACK:
                continue
            # Show loading
            stdscr.erase()
            draw_frame(stdscr, preview, STEP_TITLES[6], "请稍候...", lo)
            safe_addstr(
                stdscr,
                lo.ri_y + 2,
                lo.ri_x,
                "正在生成更多推荐...",
                curses.color_pair(CP_HELP),
            )
            stdscr.refresh()
            new_result = generate_stances_sync(
                topic_body,
                base_url=base_url,
                api_key=api_key,
                user_prompt=extra_prompt if extra_prompt else "",
            )
            # Continue: pure append — keep ALL existing items, append new
            for d in new_result.debaters:
                items.append(
                    StanceItem(
                        name=d.name,
                        model=d.model,
                        style=d.style,
                        selected=True,
                        source="llm",
                        base_url="",
                        api_key="",
                    )
                )
            if items:
                cursor = min(cursor, len(items) - 1)
            continue

        if key in (ord("r"), ord("R")):
            # Regenerate
            extra_prompt = _ask_extra_prompt(stdscr, preview, lo)
            if extra_prompt is StepResult.BACK:
                continue
            stdscr.erase()
            draw_frame(stdscr, preview, STEP_TITLES[6], "请稍候...", lo)
            safe_addstr(
                stdscr,
                lo.ri_y + 2,
                lo.ri_x,
                "正在重新生成...",
                curses.color_pair(CP_HELP),
            )
            stdscr.refresh()
            new_result = generate_stances_sync(
                topic_body,
                base_url=base_url,
                api_key=api_key,
                user_prompt=extra_prompt if extra_prompt else "",
            )
            # Regenerate: keep selected, remove unselected, append new
            items = [it for it in items if it.selected]
            for d in new_result.debaters:
                items.append(
                    StanceItem(
                        name=d.name,
                        model=d.model,
                        style=d.style,
                        selected=True,
                        source="llm",
                        base_url="",
                        api_key="",
                    )
                )
            cursor = 0
            scroll_top = 0
            continue

        if key in (ord("d"), ord("D")):
            # Delete item under cursor
            if items:
                items.pop(cursor)
                if not items:
                    cursor = 0
                elif cursor >= len(items):
                    cursor = len(items) - 1
            continue
        if key in (ord("e"), ord("E")):
            # Edit item under cursor
            if items:
                edited = _edit_stance_item(stdscr, preview, lo, items[cursor])
                if edited is not None:
                    items[cursor].name = edited["name"]
                    items[cursor].model = edited["model"]
                    items[cursor].style = edited["style"]
                    items[cursor].base_url = edited["base_url"]
                    items[cursor].api_key = edited["api_key"]
            continue
        if key in (ord("v"), ord("V")):
            # Stance check
            selected_debaters = [
                {"name": it.name, "model": it.model, "style": it.style}
                for it in items
                if it.selected
            ]
            warnings = check_stances(selected_debaters)
            _show_stance_warnings(stdscr, preview, lo, warnings)
            continue


def _ask_extra_prompt(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
) -> str | object:
    """Ask for optional extra prompt for stance generation."""

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[6], "Enter=确认  Esc=取消", lo)
        safe_addstr(
            stdscr,
            lo.ri_y,
            lo.ri_x,
            "额外指示 (可选，直接 Enter 跳过):",
            curses.color_pair(CP_NORMAL),
        )

    _redraw()
    result = curses_text_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        default="",
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    return result.strip()


def _add_custom_debater(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    items: list[StanceItem],
) -> None:
    """Add a custom debater via sequential text inputs."""
    fields = [
        ("辩手名称 (name):", ""),
        (
            f"模型 ID (model, 默认 {DEFAULT_DEBATE_MODELS[0]}):",
            DEFAULT_DEBATE_MODELS[0],
        ),
        ("立场描述 (style):", ""),
        ("API Base URL (可选):", ""),
        ("API Key (可选):", ""),
    ]
    values: list[str] = []

    for prompt_text, default in fields:

        def _redraw(pt: str = prompt_text) -> None:
            stdscr.erase()
            draw_frame(stdscr, preview, STEP_TITLES[6], "Enter=确认  Esc=取消", lo)
            safe_addstr(
                stdscr,
                lo.ri_y,
                lo.ri_x,
                "添加自定义辩手",
                curses.color_pair(CP_HEADER) | curses.A_BOLD,
            )
            safe_addstr(stdscr, lo.ri_y + 1, lo.ri_x, pt, curses.color_pair(CP_NORMAL))
            # Show already-entered values
            for i, v in enumerate(values):
                label = fields[i][0]
                safe_addstr(
                    stdscr,
                    lo.ri_y + 4 + i,
                    lo.ri_x,
                    f"  {label} {v}",
                    curses.color_pair(CP_FILLED),
                )

        _redraw()
        result = curses_text_input(
            stdscr,
            lo.ri_y + 3,
            lo.ri_x,
            lo.ri_w,
            default=default,
            redraw=_redraw,
        )
        if result is StepResult.BACK:
            return
        val = result.strip()
        if not val and len(values) < 3:
            return  # Cancel if any field empty
        values.append(val if val else default)

    items.append(
        StanceItem(
            name=values[0],
            model=values[1],
            style=values[2],
            base_url=values[3],
            api_key=values[4],
            selected=True,
            source="custom",
        )
    )


def _edit_stance_item(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    item: StanceItem,
) -> dict[str, str] | None:
    """Edit an existing stance item via sequential text inputs. Returns dict or None if cancelled."""
    fields = [
        ("辩手名称 (name):", item.name),
        ("模型 ID (model):", item.model or DEFAULT_DEBATE_MODELS[0]),
        ("立场描述 (style):", item.style),
        ("API Base URL (可选):", item.base_url),
        ("API Key (可选):", item.api_key),
    ]
    values: list[str] = []

    for prompt_text, default in fields:

        def _redraw(pt: str = prompt_text) -> None:
            stdscr.erase()
            draw_frame(stdscr, preview, STEP_TITLES[6], "Enter=确认  Esc=取消", lo)
            safe_addstr(
                stdscr,
                lo.ri_y,
                lo.ri_x,
                "编辑辩手",
                curses.color_pair(CP_HEADER) | curses.A_BOLD,
            )
            safe_addstr(stdscr, lo.ri_y + 1, lo.ri_x, pt, curses.color_pair(CP_NORMAL))
            # Show already-entered values
            for i, v in enumerate(values):
                label = fields[i][0]
                safe_addstr(
                    stdscr,
                    lo.ri_y + 4 + i,
                    lo.ri_x,
                    f"  {label} {v}",
                    curses.color_pair(CP_FILLED),
                )

        _redraw()
        result = curses_text_input(
            stdscr,
            lo.ri_y + 3,
            lo.ri_x,
            lo.ri_w,
            default=default,
            redraw=_redraw,
        )
        if result is StepResult.BACK:
            return None
        val = result.strip()
        values.append(val if val else default)

    return {
        "name": values[0],
        "model": values[1] or "gpt-5.2",
        "style": values[2],
        "base_url": values[3],
        "api_key": values[4],
    }


def _show_stance_warnings(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    warnings: list[str],
) -> None:
    """Show stance check warnings in a popup-like display."""
    stdscr.erase()
    draw_frame(stdscr, preview, STEP_TITLES[6], "按任意键关闭", lo)

    y = lo.ri_y
    x = lo.ri_x
    w = lo.ri_w

    if not warnings:
        safe_addstr(
            stdscr,
            y,
            x,
            "✅ 检查通过，未发现问题",
            curses.color_pair(CP_FILLED) | curses.A_BOLD,
        )
    else:
        safe_addstr(
            stdscr,
            y,
            x,
            f"⚠ 发现 {len(warnings)} 个问题:",
            curses.color_pair(CP_ERROR) | curses.A_BOLD,
        )
        for i, warn in enumerate(warnings):
            if y + 2 + i >= lo.ri_y + lo.ri_h - 1:
                break
            safe_addstr(
                stdscr, y + 2 + i, x, f"  • {warn}"[:w], curses.color_pair(CP_ERROR)
            )

    stdscr.refresh()
    stdscr.getch()


# ---------------------------------------------------------------------------
# Step 7: Debaters — edit finalized list
# ---------------------------------------------------------------------------


def step_debaters(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    initial_debaters: list[dict[str, str]],
) -> list[dict[str, str]] | object:
    """Step 8: Edit the debater list (must have >= 2)."""
    preview.active_field = "debaters"
    help_text = "↑↓=移动  Enter=编辑  A=添加  D=删除  Tab=确认  Esc=返回"

    debaters = [dict(d) for d in initial_debaters]
    cursor = 0
    scroll_top = 0
    message = ""

    while True:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[7], help_text, lo)

        y = lo.ri_y
        x = lo.ri_x
        w = lo.ri_w

        safe_addstr(
            stdscr,
            y,
            x,
            f"辩手列表 ({len(debaters)} 位)",
            curses.color_pair(CP_HEADER) | curses.A_BOLD,
        )
        y += 1

        # Render debater list
        max_rows = lo.ri_h - 5
        n_items = len(debaters) + 1  # +1 for confirm button

        if cursor < scroll_top:
            scroll_top = cursor
        if cursor >= scroll_top + max_rows:
            scroll_top = cursor - max_rows + 1

        for vi in range(max_rows):
            idx = scroll_top + vi
            if idx >= n_items:
                break
            is_cur = idx == cursor

            if idx < len(debaters):
                d = debaters[idx]
                line = f"  {idx + 1}. {d.get('name', '?')} | {d.get('model', '?')} | {d.get('style', '?')}"
                attr = (
                    curses.color_pair(CP_INPUT_HL) | curses.A_BOLD
                    if is_cur
                    else curses.color_pair(CP_NORMAL)
                )
            else:
                line = "  ✔ 确认"
                attr = (
                    curses.color_pair(CP_FILLED) | curses.A_BOLD
                    if is_cur
                    else curses.color_pair(CP_FILLED)
                )

            safe_addstr(stdscr, y + vi, x, line[:w], attr)

        # Message
        if message:
            msg_y = lo.ri_y + lo.ri_h - 2
            safe_addstr(stdscr, msg_y, x, message[:w], curses.color_pair(CP_ERROR))

        stdscr.refresh()
        curses.curs_set(0)
        key = stdscr.getch()
        message = ""

        if is_esc(stdscr, key):
            return StepResult.BACK

        if key in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % n_items
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % n_items
        elif key == ord("\t"):
            # Jump to confirm button
            cursor = n_items - 1
        elif key in (curses.KEY_ENTER, 10, 13):
            if cursor >= len(debaters):
                # Confirm button
                if len(debaters) < 2:
                    message = "至少需要 2 位辩手"
                    continue
                return debaters
            # Edit debater at cursor
            d = debaters[cursor]
            new_d = _edit_single_debater(stdscr, preview, lo, d)
            if new_d is not None:
                debaters[cursor] = new_d
        elif key in (ord("d"), ord("D")):
            if cursor < len(debaters):
                if len(debaters) <= 2:
                    message = "至少需要 2 位辩手，无法删除"
                else:
                    debaters.pop(cursor)
                    if cursor >= len(debaters):
                        cursor = len(debaters) - 1

        elif key in (ord("a"), ord("A")):
            new_d = _edit_single_debater(stdscr, preview, lo, None)
            if new_d is not None:
                debaters.append(new_d)
                cursor = len(debaters) - 1


def _edit_single_debater(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current: dict[str, str] | None,
) -> dict[str, str] | None:
    """Edit or add a single debater via text inputs. Returns dict or None if cancelled."""
    is_new = current is None
    title = "添加辩手" if is_new else "编辑辩手"
    fields = [
        ("名称 (name):", current.get("name", "") if current else ""),
        (
            "模型 (model):",
            current.get("model", DEFAULT_DEBATE_MODELS[0])
            if current
            else DEFAULT_DEBATE_MODELS[0],
        ),
        ("立场 (style):", current.get("style", "") if current else ""),
        ("API Base URL (可选):", current.get("base_url", "") if current else ""),
        ("API Key (可选):", current.get("api_key", "") if current else ""),
    ]
    values: list[str] = []

    for prompt_text, default in fields:

        def _redraw(pt: str = prompt_text) -> None:
            stdscr.erase()
            draw_frame(stdscr, preview, STEP_TITLES[7], "Enter=确认  Esc=取消", lo)
            safe_addstr(
                stdscr,
                lo.ri_y,
                lo.ri_x,
                title,
                curses.color_pair(CP_HEADER) | curses.A_BOLD,
            )
            safe_addstr(stdscr, lo.ri_y + 1, lo.ri_x, pt, curses.color_pair(CP_NORMAL))
            for i, v in enumerate(values):
                label = fields[i][0]
                safe_addstr(
                    stdscr,
                    lo.ri_y + 4 + i,
                    lo.ri_x,
                    f"  {label} {v}",
                    curses.color_pair(CP_FILLED),
                )

        _redraw()
        result = curses_text_input(
            stdscr,
            lo.ri_y + 3,
            lo.ri_x,
            lo.ri_w,
            default=default,
            redraw=_redraw,
        )
        if result is StepResult.BACK:
            return None
        val = result.strip()
        if not val and is_new and len(values) < 3:
            return None
        values.append(val if val else default)

    output = {
        "name": values[0],
        "model": values[1] or DEFAULT_DEBATE_MODELS[0],
        "style": values[2],
    }
    if values[3].strip():
        output["base_url"] = values[3].strip()
    if values[4].strip():
        output["api_key"] = values[4].strip()
    return output


# ---------------------------------------------------------------------------
# Step 8: Judge
# ---------------------------------------------------------------------------


def step_judge(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current_judge: dict[str, Any],
) -> dict[str, Any] | object:
    """Step 9: Edit judge configuration."""
    preview.active_field = "judge"
    help_text = "↑↓=移动  Enter=编辑/确认  Esc=返回"

    judge = dict(current_judge) if current_judge else dict(DEFAULT_JUDGE)
    field_keys = ["model", "name", "max_tokens"]
    field_labels = ["模型 (model)", "名称 (name)", "最大 tokens"]
    cursor = 0
    n_items = len(field_keys) + 1  # +1 for confirm

    while True:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[8], help_text, lo)

        y = lo.ri_y
        x = lo.ri_x
        w = lo.ri_w

        safe_addstr(
            stdscr, y, x, "裁判配置", curses.color_pair(CP_HEADER) | curses.A_BOLD
        )
        y += 2

        for i, (fk, fl) in enumerate(zip(field_keys, field_labels)):
            is_cur = i == cursor
            val = str(judge.get(fk, ""))
            line = f"  {fl}: {val}"
            attr = (
                curses.color_pair(CP_INPUT_HL) | curses.A_BOLD
                if is_cur
                else curses.color_pair(CP_NORMAL)
            )
            safe_addstr(stdscr, y + i, x, line[:w], attr)

        # Confirm button
        confirm_y = y + len(field_keys) + 1
        is_cur = cursor == len(field_keys)
        attr = (
            curses.color_pair(CP_FILLED) | curses.A_BOLD
            if is_cur
            else curses.color_pair(CP_FILLED)
        )
        safe_addstr(stdscr, confirm_y, x, "  ✔ 确认", attr)

        stdscr.refresh()
        curses.curs_set(0)
        key = stdscr.getch()

        if is_esc(stdscr, key):
            return StepResult.BACK

        if key in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % n_items
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % n_items
        elif key in (curses.KEY_ENTER, 10, 13):
            if cursor >= len(field_keys):
                return judge
            # Edit the selected field
            fk = field_keys[cursor]
            fl = field_labels[cursor]

            def _redraw_edit(fl: str = fl) -> None:
                stdscr.erase()
                draw_frame(stdscr, preview, STEP_TITLES[8], "Enter=确认  Esc=取消", lo)
                safe_addstr(
                    stdscr,
                    lo.ri_y,
                    lo.ri_x,
                    f"编辑: {fl}",
                    curses.color_pair(CP_HEADER) | curses.A_BOLD,
                )

            _redraw_edit()
            result = curses_text_input(
                stdscr,
                lo.ri_y + 2,
                lo.ri_x,
                lo.ri_w,
                default=str(judge.get(fk, "")),
                redraw=_redraw_edit,
            )
            if result is not StepResult.BACK and result.strip():
                if fk == "max_tokens":
                    try:
                        judge[fk] = int(result.strip())
                    except ValueError:
                        pass
                else:
                    judge[fk] = result.strip()


# ---------------------------------------------------------------------------
# Step 9: Constraints
# ---------------------------------------------------------------------------


def step_constraints(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current: str,
) -> str | object:
    """Step 10: Constraints (optional multiline)."""
    preview.active_field = "constraints"
    help_text = "Ctrl+D=确认  Esc=返回 (可选，Ctrl+D=跳过)"

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[9], help_text, lo)
        safe_addstr(
            stdscr,
            lo.ri_y,
            lo.ri_x,
            "约束条件 (可选，Ctrl+D=跳过)",
            curses.color_pair(CP_NORMAL),
        )

    _redraw()
    result = curses_multiline_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        lo.ri_h - 2,
        default=current or DEFAULT_CONSTRAINTS,
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    return result.strip()


# ---------------------------------------------------------------------------
# Step 10: Round tasks
# ---------------------------------------------------------------------------


def step_round_tasks(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    round1_task: str,
    middle_task: str,
    final_task: str,
) -> tuple[str, str, str] | object:
    """Step 11: Edit 3 round task descriptions."""
    preview.active_field = "round1_task"
    help_text = "↑↓=移动  Enter=编辑  Tab=确认  Esc=返回"

    tasks = {
        "round1_task": round1_task or DEFAULT_ROUND1_TASK,
        "middle_task": middle_task or DEFAULT_MIDDLE_TASK,
        "final_task": final_task or DEFAULT_FINAL_TASK,
    }
    task_keys = ["round1_task", "middle_task", "final_task"]
    task_labels = ["第一轮任务", "中间轮任务", "最终轮任务"]
    task_defaults = [DEFAULT_ROUND1_TASK, DEFAULT_MIDDLE_TASK, DEFAULT_FINAL_TASK]
    cursor = 0
    n_items = len(task_keys) + 1  # +1 for confirm

    while True:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[10], help_text, lo)

        y = lo.ri_y
        x = lo.ri_x
        w = lo.ri_w

        safe_addstr(
            stdscr,
            y,
            x,
            "各轮任务 (可选，Enter 编辑，默认值已预填)",
            curses.color_pair(CP_NORMAL),
        )
        y += 2

        for i, (tk, tl) in enumerate(zip(task_keys, task_labels)):
            is_cur = i == cursor
            val = tasks[tk]
            # Show summary
            summary = val.split("\n")[0][: w - len(tl) - 10]
            if val == task_defaults[i]:
                tag = "(默认)"
            else:
                tag = "(自定义)"
            line = f"  {tl}: {summary} {tag}"
            attr = (
                curses.color_pair(CP_INPUT_HL) | curses.A_BOLD
                if is_cur
                else curses.color_pair(CP_NORMAL)
            )
            safe_addstr(stdscr, y + i * 2, x, line[:w], attr)

        # Confirm button
        confirm_y = y + len(task_keys) * 2 + 1
        is_cur = cursor == len(task_keys)
        attr = (
            curses.color_pair(CP_FILLED) | curses.A_BOLD
            if is_cur
            else curses.color_pair(CP_FILLED)
        )
        safe_addstr(stdscr, confirm_y, x, "  ✔ 确认", attr)

        stdscr.refresh()
        curses.curs_set(0)
        key = stdscr.getch()

        if is_esc(stdscr, key):
            return StepResult.BACK

        if key in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % n_items
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % n_items
        elif key == ord("\t"):
            cursor = n_items - 1
        elif key in (curses.KEY_ENTER, 10, 13):
            if cursor >= len(task_keys):
                return (tasks["round1_task"], tasks["middle_task"], tasks["final_task"])
            # Edit the selected task
            tk = task_keys[cursor]
            tl = task_labels[cursor]
            edit_help = "Ctrl+D=确认  Esc=取消"

            # Update preview active_field
            preview.active_field = tk

            def _redraw_task(tl: str = tl) -> None:
                stdscr.erase()
                draw_frame(stdscr, preview, STEP_TITLES[10], edit_help, lo)
                safe_addstr(
                    stdscr,
                    lo.ri_y,
                    lo.ri_x,
                    f"编辑: {tl}",
                    curses.color_pair(CP_HEADER) | curses.A_BOLD,
                )

            _redraw_task()
            result = curses_multiline_input(
                stdscr,
                lo.ri_y + 2,
                lo.ri_x,
                lo.ri_w,
                lo.ri_h - 2,
                default=tasks[tk],
                redraw=_redraw_task,
            )
            if result is not StepResult.BACK:
                tasks[tk] = result.strip() if result.strip() else task_defaults[cursor]


# ---------------------------------------------------------------------------
# Step 11: Judge instructions
# ---------------------------------------------------------------------------


def step_judge_instructions(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    current: str,
) -> str | object:
    """Step 12: Judge instructions (optional multiline)."""
    preview.active_field = "judge_instructions"
    help_text = "Ctrl+D=确认  Esc=返回"

    def _redraw() -> None:
        stdscr.erase()
        draw_frame(stdscr, preview, STEP_TITLES[11], help_text, lo)
        safe_addstr(
            stdscr,
            lo.ri_y,
            lo.ri_x,
            "裁判指令 (可选，默认值已预填)",
            curses.color_pair(CP_NORMAL),
        )

    _redraw()
    result = curses_multiline_input(
        stdscr,
        lo.ri_y + 2,
        lo.ri_x,
        lo.ri_w,
        lo.ri_h - 2,
        default=current or DEFAULT_JUDGE_INSTRUCTIONS,
        redraw=_redraw,
    )
    if result is StepResult.BACK:
        return StepResult.BACK
    return result.strip()


# ---------------------------------------------------------------------------
# Step 12: Preview — scrollable .md preview
# ---------------------------------------------------------------------------


def step_preview(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    content: str,
    out_path: Any,
) -> bool | object:
    """Step 13: Full-screen scrollable preview of generated .md file."""
    curses.curs_set(0)
    scroll = 0

    raw_lines = content.split("\n")
    display_lines: list[tuple[str, int]] = []

    in_frontmatter = False
    for line in raw_lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            display_lines.append((line, curses.color_pair(CP_FILLED)))
        elif in_frontmatter:
            display_lines.append((line, curses.color_pair(CP_FILLED)))
        else:
            display_lines.append((line, curses.color_pair(CP_NORMAL)))

    while True:
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()

        safe_addstr(
            stdscr,
            0,
            2,
            " 预览 — 生成的 .md 文件 ",
            curses.color_pair(CP_HEADER) | curses.A_BOLD,
        )

        content_h = max_y - 3
        for i in range(content_h):
            li = scroll + i
            if li >= len(display_lines):
                break
            text, attr = display_lines[li]
            safe_addstr(stdscr, i + 1, 2, text[: max_x - 4], attr)

        total = len(display_lines)
        pct = min(100, int((scroll + content_h) / max(total, 1) * 100))
        help_line = f"y=保存  n/Esc=返回编辑  ↑↓/j/k/PgUp/PgDn=滚动  ({pct}%)"
        safe_addstr(
            stdscr, max_y - 1, 2, help_line[: max_x - 4], curses.color_pair(CP_HELP)
        )

        stdscr.refresh()
        key = stdscr.getch()

        if is_esc(stdscr, key) or key == ord("n"):
            return StepResult.BACK
        if key == ord("y"):
            return True
        if key in (curses.KEY_UP, ord("k")):
            scroll = max(0, scroll - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            scroll = min(max(len(display_lines) - content_h, 0), scroll + 1)
        elif key == curses.KEY_PPAGE:
            scroll = max(0, scroll - content_h)
        elif key == curses.KEY_NPAGE:
            scroll = min(max(len(display_lines) - content_h, 0), scroll + content_h)


# ---------------------------------------------------------------------------
# Step 13: Success
# ---------------------------------------------------------------------------


def step_success(
    stdscr: Any,
    preview: TopicPreview,
    lo: Layout,
    out_path: Any,
    run_cmd: str,
    dryrun_cmd: str,
) -> None:
    """Final screen: show success message and run commands."""
    curses.curs_set(0)
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    lines: list[tuple[str, int]] = [
        (
            f"✅ 辩论议题文件已保存: ./{str(out_path)}",
            curses.color_pair(CP_FILLED) | curses.A_BOLD,
        ),
        ("", curses.color_pair(CP_NORMAL)),
        ("运行辩论:", curses.color_pair(CP_HEADER) | curses.A_BOLD),
        (f"  {run_cmd}", curses.color_pair(CP_NORMAL)),
        ("", curses.color_pair(CP_NORMAL)),
        ("预览配置 (dry-run):", curses.color_pair(CP_HEADER) | curses.A_BOLD),
        (f"  {dryrun_cmd}", curses.color_pair(CP_NORMAL)),
        ("", curses.color_pair(CP_NORMAL)),
        ("立场生成器 (独立使用):", curses.color_pair(CP_HEADER) | curses.A_BOLD),
        (
            f"  python -m debate_tool.stance ./{str(out_path)}",
            curses.color_pair(CP_NORMAL),
        ),
        ("", curses.color_pair(CP_NORMAL)),
        ("按任意键退出", curses.color_pair(CP_HELP)),
    ]

    cy = max(max_y // 2 - len(lines) // 2, 2)
    for i, (text, attr) in enumerate(lines):
        safe_addstr(stdscr, cy + i, 4, text[: max_x - 8], attr)

    stdscr.refresh()
    stdscr.getch()
