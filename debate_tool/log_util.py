"""日志读写操作层"""

import sys
from datetime import datetime
from pathlib import Path

from debate_tool.debug_log import dlog
from debate_tool.log_io import Log, SUMMARY_FILE_SUFFIX


def save_replies(log, debaters, results):
    dlog("flow.save_replies", f"count={len(results)}", count=len(results))
    for d, (thinking, reply) in zip(debaters, results):
        if thinking:
            log.add(d["name"], thinking, "thinking", flush=False)
        log.add(d["name"], reply, flush=False)
    log._flush()


def write_summary_file(out_dir, stem, title, summary, log, *, summary_path=None):
    dlog("flow.write_summary", f"stem={stem}", stem=stem)
    sp = Path(summary_path) if summary_path else out_dir / f"{stem}{SUMMARY_FILE_SUFFIX}"
    sp.write_text(f"# {title} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}", encoding="utf-8")
    log.add(log.title or title, summary, "summary")
    print(f"\n✅ 完成！ 日志: {log.path} | 总结: {sp}")


def write_summary_resume(log, cfg, summary, *, summary_path=None):
    dlog("flow.write_summary_resume", "resume summary")
    stem = log.path.stem.removesuffix("_debate_log")
    sp = Path(summary_path) if summary_path else log.path.parent / f"{stem}{SUMMARY_FILE_SUFFIX}"
    sp.write_text(f"# {log.title} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}", encoding="utf-8")
    log.add(cfg["judge"]["name"], summary, "summary")
    print(f"\n✅ 续跑完成！ 日志: {log.path}")


def load_log_or_die(path):
    if not path.exists():
        print(f"❌ 日志文件不存在: {path}\n请先运行 debate-tool run 进行首次辩论", file=sys.stderr)
        sys.exit(1)
    log = Log.load_from_file(path)
    print(f"📂 已加载 {len(log.entries)} 条日志记录")
    return log
