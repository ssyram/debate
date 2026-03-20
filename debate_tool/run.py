"""极简 run 入口 — parse topic → init log → core_loop"""

from pathlib import Path

from debate_tool.core_loop import compute_xexam_rounds, judge_phase
from debate_tool.log_io import build_log_path
from debate_tool.log_util import write_summary_file

import debate_tool.core as _core


def init_run_log(cfg, topic_path, log_path):
    from debate_tool.log_io import Log
    if log_path is None:
        log_path = build_log_path(topic_path)
    initial_config = _core._build_initial_config(cfg)
    return Log(log_path, cfg["title"], topic=cfg.get("topic_body", ""), initial_config=initial_config)


async def run(cfg: dict, topic_path: Path, *, cot_length: "int | None" = None, log_path: "Path | None" = None, summary_path: "Path | None" = None, no_judge: bool = False):
    from debate_tool.core_loop import core_loop
    cot = cot_length if cot_length is not None else cfg.get("cot_length", None)
    log = init_run_log(cfg, topic_path, log_path)
    xrounds = compute_xexam_rounds(cfg.get("cross_exam", 0), cfg["rounds"])
    await core_loop(cfg, log, 0, cot, xrounds)
    if no_judge or cfg.get("no_judge"):
        print(f"\n✅ 完成（跳过裁判）。日志: {log.path}")
        return
    summary = await judge_phase(cfg, log)
    write_summary_file(topic_path.parent, topic_path.stem, cfg["title"], summary, log, summary_path=summary_path)
