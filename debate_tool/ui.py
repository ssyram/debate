"""Curses TUI primitives — drawing helpers, layout, input widgets."""
from __future__ import annotations

import curses
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Sentinel for back-navigation
# ---------------------------------------------------------------------------

class StepResult:
    BACK = object()


# -- Color pair IDs ---------------------------------------------------------
CP_INPUT_HL = 1    # cursor / input highlight
CP_HEADER = 2      # headers, active placeholder
CP_FILLED = 3      # filled values, selected
CP_HELP = 4        # help text, structure chars
CP_ERROR = 5       # errors
CP_NORMAL = 6      # normal text, structure
CP_ACTIVE_BG = 7   # active placeholder background highlight


def init_colors() -> None:
    """Initialize curses color pairs."""
    curses.start_color()
    curses.use_default_colors()
    curses.set_escdelay(25)  # Reduce Esc key delay from 1000ms default
    curses.init_pair(CP_INPUT_HL, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(CP_HEADER, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_FILLED, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_HELP, curses.COLOR_CYAN, -1)
    curses.init_pair(CP_ERROR, curses.COLOR_RED, -1)
    curses.init_pair(CP_NORMAL, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_ACTIVE_BG, curses.COLOR_BLACK, curses.COLOR_YELLOW)


# -- Esc key detection -------------------------------------------------------

def is_esc(stdscr: Any, key: int) -> bool:
    """Detect bare Esc vs Alt+key sequence.

    After receiving 27 (Esc), briefly check if another key follows.
    If not, it's a bare Esc press.
    """
    if key != 27:
        return False
    stdscr.nodelay(True)
    try:
        next_key = stdscr.getch()
    finally:
        stdscr.nodelay(False)
    if next_key == -1:
        return True
    # It was an Alt+key sequence; push back via ungetch
    try:
        curses.ungetch(next_key)
    except Exception:
        pass
    return False


# -- Drawing helpers ---------------------------------------------------------

def safe_addstr(stdscr: Any, y: int, x: int, text: str, attr: int = 0,
                max_x: int | None = None) -> None:
    """addstr that silently clips to screen bounds."""
    scr_h, scr_w = stdscr.getmaxyx()
    if y < 0 or y >= scr_h or x >= scr_w:
        return
    if max_x is not None:
        avail = max_x - x
    else:
        avail = scr_w - x
    if avail <= 0:
        return
    text = text[:avail]
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def safe_addstr_wrap(stdscr: Any, y: int, x: int, text: str, attr: int = 0,
                     max_w: int = 0, max_lines: int = 1) -> int:
    """Write text with word wrapping. Returns number of lines used."""
    scr_h, scr_w = stdscr.getmaxyx()
    if max_w <= 0:
        max_w = scr_w - x
    if max_w <= 0:
        return 0
    lines_used = 0
    remaining = text
    row = y
    while remaining and lines_used < max_lines and row < scr_h:
        chunk = remaining[:max_w]
        remaining = remaining[max_w:]
        safe_addstr(stdscr, row, x, chunk, attr)
        row += 1
        lines_used += 1
    return lines_used


def draw_box(stdscr: Any, y: int, x: int, h: int, w: int,
             title: str = "", attr: int = 0) -> None:
    """Draw a box border with optional title."""
    scr_h, scr_w = stdscr.getmaxyx()
    h = min(h, max(scr_h - y, 0))
    w = min(w, max(scr_w - x, 0))
    if h < 2 or w < 2:
        return
    TL, TR, BL, BR, H, V = "\u250c", "\u2510", "\u2514", "\u2518", "\u2500", "\u2502"
    if title:
        ts = f" {title} "
        fl = 3
        fr = max(w - 2 - fl - len(ts), 0)
        top = TL + H * fl + ts + H * fr + TR
    else:
        top = TL + H * (w - 2) + TR
    safe_addstr(stdscr, y, x, top[:w], attr)
    for row in range(y + 1, y + h - 1):
        safe_addstr(stdscr, row, x, V, attr)
        safe_addstr(stdscr, row, x + w - 1, V, attr)
    bottom = BL + H * (w - 2) + BR
    safe_addstr(stdscr, y + h - 1, x, bottom[:w], attr)


def draw_segments(stdscr: Any, y: int, x: int, segments: list[tuple[str, int]],
                  max_w: int) -> None:
    """Draw a line of (text, attr) segments starting at y, x within max_w."""
    col = x
    for text, attr in segments:
        remaining = max_w - (col - x)
        if remaining <= 0:
            break
        piece = text[:remaining]
        safe_addstr(stdscr, y, col, piece, attr)
        col += len(piece)


# -- Full-screen layout engine -----------------------------------------------

class Layout:
    """Computed layout positions for the two-panel wizard screen."""

    def __init__(self, scr_h: int, scr_w: int):
        self.scr_h = scr_h
        self.scr_w = scr_w

        self.outer_y = 0
        self.outer_x = 0
        self.outer_h = scr_h
        self.outer_w = scr_w

        self.title_y = 1
        self.help_y = scr_h - 2

        self.panel_top = 3
        self.panel_bot = max(scr_h - 3, self.panel_top + 3)
        self.panel_h = max(self.panel_bot - self.panel_top + 1, 4)

        self.stacked = scr_w < 90

        if self.stacked:
            self.left_x = 2
            self.left_w = max(scr_w - 4, 10)
            self.left_y = self.panel_top
            self.left_h = min(self.panel_h // 2, 18)

            self.right_x = 2
            self.right_w = max(scr_w - 4, 10)
            self.right_y = self.left_y + self.left_h + 1
            self.right_h = max(self.panel_bot - self.right_y + 1, 4)
        else:
            left_w = min(44, (scr_w - 6) // 2)
            self.left_x = 2
            self.left_w = left_w
            self.left_y = self.panel_top
            self.left_h = self.panel_h

            self.right_x = self.left_x + left_w + 1
            self.right_w = max(scr_w - self.right_x - 2, 10)
            self.right_y = self.panel_top
            self.right_h = self.panel_h

        # Interior of right panel (inside box border)
        self.ri_y = self.right_y + 1
        self.ri_x = self.right_x + 2
        self.ri_w = max(self.right_w - 4, 10)
        self.ri_h = max(self.right_h - 2, 3)


# -- Topic Preview (curses version) -----------------------------------------

@dataclass
class TopicPreview:
    """Tracks wizard state for live topic preview rendering."""

    title: str = ""
    output_path: str = ""
    rounds: int = 3
    base_url: str = ""
    api_key: str = ""
    debaters: list[Any] = field(default_factory=list)
    judge: dict[str, Any] = field(default_factory=dict)
    constraints: str = ""
    round1_task: str = ""
    middle_task: str = ""
    final_task: str = ""
    judge_instructions: str = ""
    topic_body: str = ""
    active_field: str = ""  # which field is currently being filled

    def _val_or_placeholder(
        self, value: str, placeholder: str, field_name: str,
        max_len: int = 0,
    ) -> tuple[str, int]:
        """Return (display_text, curses_attr) for a field."""
        if value:
            display = f'"{value}"'
            if max_len and len(display) > max_len:
                display = display[: max(max_len - 1, 1)] + "\u2026"
            return display, curses.color_pair(CP_FILLED)
        if field_name == self.active_field:
            return f"<?{placeholder}?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD
        return f"<?{placeholder}?>", curses.color_pair(CP_NORMAL) | curses.A_DIM

    def _mask_key(self, key: str) -> str:
        """Mask API key: first 3 + **** + last 4."""
        if len(key) <= 7:
            return "****"
        return key[:3] + "****" + key[-4:]

    def _multiline_summary(self, text: str, default_hint: str = "") -> str:
        """Summarize multi-line text as '(N lines)' or '(默认)' etc."""
        if not text:
            return ""
        if default_hint and text.strip() == default_hint.strip():
            return "(默认)"
        lines = text.strip().split("\n")
        count = len(lines)
        if count == 1 and len(lines[0]) <= 20:
            return f'"{lines[0]}"'
        return f"({count} 行)"

    def render_lines(self, max_width: int = 0) -> list[list[tuple[str, int]]]:
        """Render topic preview as list of lines, each a list of (text, attr) segments."""
        struct = curses.color_pair(CP_NORMAL)
        filled = curses.color_pair(CP_FILLED)
        dim = curses.color_pair(CP_NORMAL) | curses.A_DIM
        lines: list[list[tuple[str, int]]] = []
        mw = max_width

        def _avail(prefix: str, suffix: str = "") -> int:
            return max(mw - len(prefix) - len(suffix), 8) if mw else 0

        # title
        pfx = "title: "
        val, attr = self._val_or_placeholder(
            self.title, "辩论标题", "title",
            max_len=_avail(pfx),
        )
        lines.append([(pfx, struct), (val, attr)])

        # rounds
        pfx = "rounds: "
        lines.append([(pfx, struct), (str(self.rounds), filled)])

        # base_url
        pfx = "base_url: "
        val, attr = self._val_or_placeholder(
            self.base_url, "base-url", "base_url",
            max_len=_avail(pfx),
        )
        lines.append([(pfx, struct), (val, attr)])

        # api_key
        pfx = "api_key: "
        if self.api_key:
            masked = self._mask_key(self.api_key)
            key_text = f'"{masked}"'
            key_avail = _avail(pfx)
            if key_avail and len(key_text) > key_avail:
                key_text = key_text[: max(key_avail - 1, 1)] + "\u2026"
            lines.append([(pfx, struct), (key_text, filled)])
        elif self.active_field == "api_key":
            lines.append([
                (pfx, struct),
                ("<?api-key?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?api-key?>", dim)])

        # debaters
        pfx = "debaters: "
        if self.debaters:
            count = len(self.debaters)
            lines.append([(pfx, struct), (f"[{count} 已配置]", filled)])
        elif self.active_field == "debaters":
            lines.append([
                (pfx, struct),
                ("<?debaters?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?debaters?>", dim)])

        # judge
        pfx = "judge: "
        if self.judge:
            jname = self.judge.get("model", "?")
            jrole = self.judge.get("role", "裁判")
            disp = f"{jname} ({jrole})"
            if mw and len(pfx) + len(disp) > mw:
                disp = disp[: max(mw - len(pfx) - 1, 1)] + "\u2026"
            lines.append([(pfx, struct), (disp, filled)])
        elif self.active_field == "judge":
            lines.append([
                (pfx, struct),
                ("<?judge?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?judge?>", dim)])

        # constraints
        pfx = "constraints: "
        if self.constraints:
            summary = self._multiline_summary(self.constraints)
            lines.append([(pfx, struct), (summary, filled)])
        elif self.active_field == "constraints":
            lines.append([
                (pfx, struct),
                ("<?constraints?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?constraints?>", dim)])

        # round1_task
        pfx = "round1_task: "
        if self.round1_task:
            summary = self._multiline_summary(self.round1_task)
            lines.append([(pfx, struct), (summary, filled)])
        elif self.active_field == "round1_task":
            lines.append([
                (pfx, struct),
                ("<?round1-task?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?round1-task?>", dim)])

        # middle_task
        pfx = "middle_task: "
        if self.middle_task:
            summary = self._multiline_summary(self.middle_task)
            lines.append([(pfx, struct), (summary, filled)])
        elif self.active_field == "middle_task":
            lines.append([
                (pfx, struct),
                ("<?middle-task?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?middle-task?>", dim)])

        # final_task
        pfx = "final_task: "
        if self.final_task:
            summary = self._multiline_summary(self.final_task)
            lines.append([(pfx, struct), (summary, filled)])
        elif self.active_field == "final_task":
            lines.append([
                (pfx, struct),
                ("<?final-task?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?final-task?>", dim)])

        # judge_instructions
        pfx = "judge_instructions: "
        if self.judge_instructions:
            summary = self._multiline_summary(self.judge_instructions)
            lines.append([(pfx, struct), (summary, filled)])
        elif self.active_field == "judge_instructions":
            lines.append([
                (pfx, struct),
                ("<?judge-instr?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?judge-instr?>", dim)])

        # topic_body
        pfx = "topic_body: "
        if self.topic_body:
            summary = self._multiline_summary(self.topic_body)
            lines.append([(pfx, struct), (summary, filled)])
        elif self.active_field == "topic_body":
            lines.append([
                (pfx, struct),
                ("<?topic-body?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?topic-body?>", dim)])

        # separator
        sep = "\u2500" * min(mw, 20) if mw else "\u2500" * 20
        lines.append([(sep, curses.color_pair(CP_HELP))])

        # output path
        pfx = "\u2192 "
        if self.output_path:
            disp = self.output_path
            if mw and len(pfx) + len(disp) > mw:
                disp = disp[: max(mw - len(pfx) - 1, 1)] + "\u2026"
            lines.append([(pfx, struct), (disp, filled)])
        elif self.active_field == "output_path":
            lines.append([
                (pfx, struct),
                ("<?output-path?>", curses.color_pair(CP_ACTIVE_BG) | curses.A_BOLD),
            ])
        else:
            lines.append([(pfx, struct), ("<?output-path?>", dim)])

        return lines


# -- draw_frame --------------------------------------------------------------

def draw_frame(
    stdscr: Any,
    preview: TopicPreview,
    step_title: str,
    help_text: str,
    layout: Layout,
) -> None:
    """Draw the full screen layout."""
    lo = layout
    border_attr = curses.color_pair(CP_HELP)

    # Outer border
    draw_box(stdscr, lo.outer_y, lo.outer_x, lo.outer_h, lo.outer_w,
             title="辩论议题向导",
             attr=curses.color_pair(CP_HEADER) | curses.A_BOLD)

    # Left panel: Topic Preview
    draw_box(stdscr, lo.left_y, lo.left_x, lo.left_h, lo.left_w,
             title="议题预览", attr=border_attr)

    # Render preview lines inside left panel
    inner_w = lo.left_w - 4
    plines = preview.render_lines(max_width=inner_w)
    for i, segments in enumerate(plines):
        row = lo.left_y + 1 + i
        if row >= lo.left_y + lo.left_h - 1:
            break
        draw_segments(stdscr, row, lo.left_x + 2, segments, inner_w)

    # Right panel
    draw_box(stdscr, lo.right_y, lo.right_x, lo.right_h, lo.right_w,
             title=step_title,
             attr=curses.color_pair(CP_HEADER) | curses.A_BOLD)

    # Help bar
    safe_addstr(stdscr, lo.help_y, 3, help_text, curses.color_pair(CP_HELP))


# -- Curses text input -------------------------------------------------------

def curses_text_input(
    stdscr: Any,
    y: int,
    x: int,
    max_width: int,
    default: str = "",
    validate: Any = None,
    redraw: Any = None,
) -> str | object:
    """Curses-based text input field.

    - Shows cursor, handles typing, backspace
    - Enter confirms, Esc returns StepResult.BACK
    - Optional validate callback: returns error string or None
    - Optional redraw callback: called before each refresh to repaint frame

    Returns the input string or StepResult.BACK.
    """
    curses.curs_set(1)
    buf = list(default)
    cursor_pos = len(buf)
    error_msg = ""
    scroll_offset = 0

    while True:
        if redraw:
            redraw()

        field_w = max(max_width - 2, 5)
        text = "".join(buf)
        if cursor_pos - scroll_offset >= field_w:
            scroll_offset = cursor_pos - field_w + 1
        if cursor_pos < scroll_offset:
            scroll_offset = cursor_pos
        visible = text[scroll_offset:scroll_offset + field_w]

        safe_addstr(stdscr, y, x, "> ",
                    curses.color_pair(CP_HEADER) | curses.A_BOLD)
        safe_addstr(stdscr, y, x + 2, " " * field_w,
                    curses.color_pair(CP_NORMAL))
        safe_addstr(stdscr, y, x + 2, visible,
                    curses.color_pair(CP_NORMAL))

        # Clear error line then show error if any
        safe_addstr(stdscr, y + 2, x, " " * max_width,
                    curses.color_pair(CP_NORMAL))
        if error_msg:
            safe_addstr(stdscr, y + 2, x, error_msg[:max_width],
                        curses.color_pair(CP_ERROR))

        cursor_screen_x = x + 2 + (cursor_pos - scroll_offset)
        scr_h, scr_w = stdscr.getmaxyx()
        if 0 <= y < scr_h and 0 <= cursor_screen_x < scr_w:
            try:
                stdscr.move(y, cursor_screen_x)
            except curses.error:
                pass

        stdscr.refresh()
        key = stdscr.getch()

        if is_esc(stdscr, key):
            curses.curs_set(0)
            return StepResult.BACK

        if key in (curses.KEY_ENTER, 10, 13):
            result = "".join(buf).strip()
            if validate:
                err = validate(result)
                if err:
                    error_msg = err
                    continue
            curses.curs_set(0)
            return result

        if key in (curses.KEY_BACKSPACE, 127, 8):
            if cursor_pos > 0:
                buf.pop(cursor_pos - 1)
                cursor_pos -= 1
            error_msg = ""
        elif key == curses.KEY_DC:
            if cursor_pos < len(buf):
                buf.pop(cursor_pos)
            error_msg = ""
        elif key == curses.KEY_LEFT:
            if cursor_pos > 0:
                cursor_pos -= 1
        elif key == curses.KEY_RIGHT:
            if cursor_pos < len(buf):
                cursor_pos += 1
        elif key == curses.KEY_HOME or key == 1:  # Ctrl-A
            cursor_pos = 0
        elif key == curses.KEY_END or key == 5:  # Ctrl-E
            cursor_pos = len(buf)
        elif key == 21:  # Ctrl-U
            buf.clear()
            cursor_pos = 0
            error_msg = ""
        elif key == 11:  # Ctrl-K
            buf = buf[:cursor_pos]
            error_msg = ""
        elif 32 <= key <= 126:
            buf.insert(cursor_pos, chr(key))
            cursor_pos += 1
            error_msg = ""
        elif key == curses.KEY_RESIZE:
            pass


# -- Inline radio select (renders in right panel) ----------------------------

def curses_radio_inline(
    stdscr: Any,
    options: list[str],
    y: int,
    x: int,
    max_w: int,
    max_h: int,
    redraw: Any = None,
) -> int | object:
    """Single-select radio in a specific area. Returns index or StepResult.BACK."""
    curses.curs_set(0)
    cursor = 0

    while True:
        if redraw:
            redraw()

        for i, opt in enumerate(options):
            if i >= max_h:
                break
            marker = "\u25cf" if i == cursor else "\u25cb"
            line = f" {marker}  {opt}"
            attr = (curses.color_pair(CP_INPUT_HL) | curses.A_BOLD
                    if i == cursor
                    else curses.color_pair(CP_NORMAL))
            safe_addstr(stdscr, y + i, x, " " * max_w,
                        curses.color_pair(CP_NORMAL))
            safe_addstr(stdscr, y + i, x, line[:max_w], attr)

        stdscr.refresh()
        key = stdscr.getch()

        if is_esc(stdscr, key):
            return StepResult.BACK

        if key in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % len(options)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % len(options)
        elif key in (curses.KEY_ENTER, 10, 13):
            return cursor
        elif key == curses.KEY_RESIZE:
            return StepResult.BACK  # let outer loop re-layout


# -- Number input (wrapper) --------------------------------------------------

def curses_number_input(
    stdscr: Any,
    y: int,
    x: int,
    max_w: int,
    default: int = 3,
    min_val: int = 1,
    max_val: int = 99,
    redraw: Any = None,
) -> int | object:
    """Integer input with range validation. Returns int or StepResult.BACK."""

    def _validate(text: str) -> str | None:
        try:
            val = int(text)
        except ValueError:
            return f"必须为 {min_val}-{max_val} 的整数"
        if val < min_val or val > max_val:
            return f"必须为 {min_val}-{max_val} 的整数"
        return None

    result = curses_text_input(
        stdscr, y, x, max_w,
        default=str(default),
        validate=_validate,
        redraw=redraw,
    )
    assert isinstance(result, str)
    return int(result)


# -- Multi-line text input ---------------------------------------------------

def curses_multiline_input(
    stdscr: Any,
    y: int,
    x: int,
    max_w: int,
    max_h: int,
    default: str = "",
    redraw: Any = None,
) -> str | object:
    """Full-area multi-line text editor for right panel.

    - Line numbers on left (3-char wide), content on right
    - Navigation: ↑↓←→, Home/End per line, PgUp/PgDn
    - Editing: printable chars, Backspace, Delete, Enter (newline)
    - Ctrl+D = confirm, Esc = StepResult.BACK

    Returns the joined text (\\n) or StepResult.BACK.
    """
    curses.curs_set(1)

    # Initialize buffer from default
    if default:
        buf: list[list[str]] = [list(line) for line in default.split("\n")]
    else:
        buf = [[]]

    cy = 0  # cursor line index
    cx = 0  # cursor column index
    scroll_top = 0

    LNUM_W = 4  # "NNN " line number width
    content_w = max(max_w - LNUM_W, 5)
    # Reserve 1 row at bottom for hint bar
    view_h = max(max_h - 1, 2)

    hint = "Ctrl+D=确认  Esc=返回  ↑↓=移动"

    while True:
        if redraw:
            redraw()

        # Adjust scroll to keep cursor visible
        if cy < scroll_top:
            scroll_top = cy
        if cy >= scroll_top + view_h:
            scroll_top = cy - view_h + 1

        # Draw visible lines
        for vi in range(view_h):
            row = y + vi
            line_idx = scroll_top + vi
            # Clear the row
            safe_addstr(stdscr, row, x, " " * max_w, curses.color_pair(CP_NORMAL))
            if line_idx < len(buf):
                # Line number
                lnum_str = f"{line_idx + 1:>3} "
                safe_addstr(stdscr, row, x, lnum_str,
                            curses.color_pair(CP_HELP))
                # Content
                line_text = "".join(buf[line_idx])
                # Horizontal scroll: simple clip from left
                disp = line_text[:content_w]
                safe_addstr(stdscr, row, x + LNUM_W, disp,
                            curses.color_pair(CP_NORMAL))

        # Hint bar
        hint_row = y + view_h
        safe_addstr(stdscr, hint_row, x, " " * max_w,
                    curses.color_pair(CP_NORMAL))
        safe_addstr(stdscr, hint_row, x, hint[:max_w],
                    curses.color_pair(CP_HELP) | curses.A_DIM)

        # Position cursor
        screen_cy = y + (cy - scroll_top)
        screen_cx = x + LNUM_W + min(cx, content_w - 1)
        scr_h, scr_w = stdscr.getmaxyx()
        if 0 <= screen_cy < scr_h and 0 <= screen_cx < scr_w:
            try:
                stdscr.move(screen_cy, screen_cx)
            except curses.error:
                pass

        stdscr.refresh()
        key = stdscr.getch()

        # --- Key handling ---
        if is_esc(stdscr, key):
            curses.curs_set(0)
            return StepResult.BACK

        if key == 4:  # Ctrl+D = confirm
            curses.curs_set(0)
            return "\n".join("".join(line) for line in buf)

        if key in (curses.KEY_ENTER, 10, 13):
            # Insert newline: split current line at cursor
            rest = buf[cy][cx:]
            buf[cy] = buf[cy][:cx]
            buf.insert(cy + 1, rest)
            cy += 1
            cx = 0

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if cx > 0:
                buf[cy].pop(cx - 1)
                cx -= 1
            elif cy > 0:
                # Merge with previous line
                cx = len(buf[cy - 1])
                buf[cy - 1].extend(buf[cy])
                buf.pop(cy)
                cy -= 1

        elif key == curses.KEY_DC:
            if cx < len(buf[cy]):
                buf[cy].pop(cx)
            elif cy < len(buf) - 1:
                # Merge next line into current
                buf[cy].extend(buf[cy + 1])
                buf.pop(cy + 1)

        elif key == curses.KEY_LEFT:
            if cx > 0:
                cx -= 1
            elif cy > 0:
                cy -= 1
                cx = len(buf[cy])

        elif key == curses.KEY_RIGHT:
            if cx < len(buf[cy]):
                cx += 1
            elif cy < len(buf) - 1:
                cy += 1
                cx = 0

        elif key == curses.KEY_UP:
            if cy > 0:
                cy -= 1
                cx = min(cx, len(buf[cy]))

        elif key == curses.KEY_DOWN:
            if cy < len(buf) - 1:
                cy += 1
                cx = min(cx, len(buf[cy]))

        elif key == curses.KEY_HOME or key == 1:  # Ctrl-A
            cx = 0

        elif key == curses.KEY_END or key == 5:  # Ctrl-E
            cx = len(buf[cy])

        elif key == curses.KEY_PPAGE:
            cy = max(0, cy - view_h)
            cx = min(cx, len(buf[cy]))

        elif key == curses.KEY_NPAGE:
            cy = min(len(buf) - 1, cy + view_h)
            cx = min(cx, len(buf[cy]))

        elif key == curses.KEY_RESIZE:
            pass  # outer loop handles resize

        elif 32 <= key <= 126:
            buf[cy].insert(cx, chr(key))
            cx += 1


# -- File path input with Tab completion ----------------------------------------

def _path_completions(partial: str) -> list[str]:
    """Return filesystem completions for a partial path."""
    import os
    from pathlib import Path as _Path

    if not partial:
        # List cwd entries
        try:
            entries = sorted(os.listdir("."))
            return [e + "/" if os.path.isdir(e) else e for e in entries[:20]]
        except OSError:
            return []

    p = _Path(partial)

    # If partial ends with /, list that directory
    if partial.endswith("/") or partial.endswith(os.sep):
        if p.is_dir():
            try:
                entries = sorted(os.listdir(p))
                return [
                    partial + e + ("/" if (p / e).is_dir() else "")
                    for e in entries[:20]
                ]
            except OSError:
                return []
        return []

    # Otherwise, complete the last path component
    parent = p.parent
    prefix = p.name
    if not parent.is_dir():
        return []

    try:
        entries = sorted(os.listdir(parent))
    except OSError:
        return []

    matches = []
    for e in entries:
        if e.lower().startswith(prefix.lower()):
            full = str(parent / e) if str(parent) != "." else e
            if (parent / e).is_dir():
                full += "/"
            matches.append(full)
        if len(matches) >= 20:
            break
    return matches


def curses_path_input(
    stdscr: Any,
    y: int,
    x: int,
    max_width: int,
    max_h: int,
    default: str = "",
    validate: Any = None,
    redraw: Any = None,
) -> str | object:
    """File path input with Tab completion.

    Like curses_text_input but Tab triggers filesystem auto-completion.
    Shows completion suggestions below the input line.

    Returns the path string or StepResult.BACK.
    """
    curses.curs_set(1)
    buf = list(default)
    cursor_pos = len(buf)
    error_msg = ""
    scroll_offset = 0
    completions: list[str] = []
    comp_scroll = 0
    comp_cursor = -1  # -1 = not browsing completions

    while True:
        if redraw:
            redraw()

        field_w = max(max_width - 2, 5)
        text = "".join(buf)

        # Scrolling
        if cursor_pos - scroll_offset >= field_w:
            scroll_offset = cursor_pos - field_w + 1
        if cursor_pos < scroll_offset:
            scroll_offset = cursor_pos
        visible = text[scroll_offset:scroll_offset + field_w]

        # Draw input line
        safe_addstr(stdscr, y, x, "> ",
                    curses.color_pair(CP_HEADER) | curses.A_BOLD)
        safe_addstr(stdscr, y, x + 2, " " * field_w,
                    curses.color_pair(CP_NORMAL))
        safe_addstr(stdscr, y, x + 2, visible,
                    curses.color_pair(CP_NORMAL))

        # Error line
        safe_addstr(stdscr, y + 1, x, " " * max_width,
                    curses.color_pair(CP_NORMAL))
        if error_msg:
            safe_addstr(stdscr, y + 1, x, error_msg[:max_width],
                        curses.color_pair(CP_ERROR))

        # Completion suggestions (below error line)
        comp_area_y = y + 2
        comp_area_h = max(max_h - 3, 1)  # leave room for input + error + hint
        for ci in range(comp_area_h):
            row = comp_area_y + ci
            safe_addstr(stdscr, row, x, " " * max_width,
                        curses.color_pair(CP_NORMAL))
            idx = comp_scroll + ci
            if idx < len(completions):
                entry = completions[idx]
                is_cur = (idx == comp_cursor)
                if is_cur:
                    attr = curses.color_pair(CP_INPUT_HL) | curses.A_BOLD
                elif entry.endswith("/"):
                    attr = curses.color_pair(CP_HEADER)
                else:
                    attr = curses.color_pair(CP_FILLED)
                prefix = "\u25b8 " if is_cur else "  "
                safe_addstr(stdscr, row, x, (prefix + entry)[:max_width], attr)

        # Hint at bottom of completion area
        hint_row = comp_area_y + comp_area_h
        safe_addstr(stdscr, hint_row, x, " " * max_width,
                    curses.color_pair(CP_NORMAL))
        if completions:
            hint = f"Tab=\u5b8c\u6210  \u2191\u2193=\u9009\u62e9  Enter=\u786e\u8ba4  ({len(completions)} \u9879)"
        else:
            hint = "Tab=\u81ea\u52a8\u5b8c\u6210  Enter=\u786e\u8ba4  Esc=\u8fd4\u56de"
        safe_addstr(stdscr, hint_row, x, hint[:max_width],
                    curses.color_pair(CP_HELP))

        # Position cursor
        cursor_screen_x = x + 2 + (cursor_pos - scroll_offset)
        scr_h, scr_w = stdscr.getmaxyx()
        if 0 <= y < scr_h and 0 <= cursor_screen_x < scr_w:
            try:
                stdscr.move(y, cursor_screen_x)
            except curses.error:
                pass

        stdscr.refresh()
        key = stdscr.getch()

        if is_esc(stdscr, key):
            curses.curs_set(0)
            return StepResult.BACK

        if key in (curses.KEY_ENTER, 10, 13):
            if comp_cursor >= 0 and comp_cursor < len(completions):
                # Accept the highlighted completion
                selected = completions[comp_cursor]
                buf = list(selected)
                cursor_pos = len(buf)
                completions = []
                comp_cursor = -1
                error_msg = ""
                continue
            result = "".join(buf).strip()
            if validate:
                err = validate(result)
                if err:
                    error_msg = err
                    continue
            curses.curs_set(0)
            return result

        if key == ord("\t"):
            # Trigger completion
            text = "".join(buf)
            completions = _path_completions(text)
            comp_scroll = 0
            if len(completions) == 1:
                # Single match — auto-complete immediately
                buf = list(completions[0])
                cursor_pos = len(buf)
                completions = []
                comp_cursor = -1
            elif completions:
                # Find common prefix among completions
                common = completions[0]
                for c in completions[1:]:
                    while not c.startswith(common):
                        common = common[:-1]
                if len(common) > len(text):
                    buf = list(common)
                    cursor_pos = len(buf)
                comp_cursor = 0
            else:
                comp_cursor = -1
            error_msg = ""
            continue

        # Arrow keys in completion mode
        if comp_cursor >= 0 and completions:
            if key in (curses.KEY_UP, ord("k")):
                comp_cursor = (comp_cursor - 1) % len(completions)
                if comp_cursor < comp_scroll:
                    comp_scroll = comp_cursor
                if comp_cursor >= comp_scroll + comp_area_h:
                    comp_scroll = comp_cursor - comp_area_h + 1
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                comp_cursor = (comp_cursor + 1) % len(completions)
                if comp_cursor < comp_scroll:
                    comp_scroll = comp_cursor
                if comp_cursor >= comp_scroll + comp_area_h:
                    comp_scroll = comp_cursor - comp_area_h + 1
                continue

        # Typing dismisses completion list
        if completions and key not in (
            curses.KEY_LEFT, curses.KEY_RIGHT,
            curses.KEY_HOME, curses.KEY_END,
            curses.KEY_BACKSPACE, 127, 8,
            curses.KEY_DC,
        ):
            completions = []
            comp_cursor = -1
            comp_scroll = 0

        # Standard text editing (same as curses_text_input)
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if cursor_pos > 0:
                buf.pop(cursor_pos - 1)
                cursor_pos -= 1
            error_msg = ""
            # Refresh completions on backspace
            completions = _path_completions("".join(buf))
            comp_cursor = 0 if completions else -1
            comp_scroll = 0
        elif key == curses.KEY_DC:
            if cursor_pos < len(buf):
                buf.pop(cursor_pos)
            error_msg = ""
        elif key == curses.KEY_LEFT:
            if cursor_pos > 0:
                cursor_pos -= 1
        elif key == curses.KEY_RIGHT:
            if cursor_pos < len(buf):
                cursor_pos += 1
        elif key == curses.KEY_HOME or key == 1:  # Ctrl-A
            cursor_pos = 0
        elif key == curses.KEY_END or key == 5:  # Ctrl-E
            cursor_pos = len(buf)
        elif key == 21:  # Ctrl-U
            buf.clear()
            cursor_pos = 0
            error_msg = ""
            completions = []
            comp_cursor = -1
        elif 32 <= key <= 126:
            buf.insert(cursor_pos, chr(key))
            cursor_pos += 1
            error_msg = ""
            # Live-update completions while typing /
            if chr(key) == "/":
                completions = _path_completions("".join(buf))
                comp_cursor = 0 if completions else -1
                comp_scroll = 0
        elif key == curses.KEY_RESIZE:
            pass
