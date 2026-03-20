"""Configuration operations for debate-tool."""
from __future__ import annotations

import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .log_io import Log, build_log_path, LogFormatError  # noqa: F401
from .topic_parser import parse_topic_file, _expand_env  # noqa: F401

ENV_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
ENV_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()


def _apply_overrides(cfg: dict, overrides: dict) -> None:
    """将单次 override dict 就地合并到 cfg。

    执行顺序：先 drop_debaters，后 add_debaters。
    先删后加支持同名辩手替换（drop 旧模型 → add 新模型），
    有意排除 round1_task（resume 不存在"第一轮"语义）。
    """
    # 先执行 drop_debaters（先删，允许同名替换）
    if "drop_debaters" in overrides:
        drop_set = set(overrides["drop_debaters"])
        cfg["debaters"] = [d for d in cfg["debaters"] if d["name"] not in drop_set]
    # 后执行 add_debaters
    if "add_debaters" in overrides:
        existing_names = {d["name"] for d in cfg["debaters"]}
        for d in overrides["add_debaters"]:
            if d["name"] not in existing_names:
                cfg["debaters"].append(d)
    # judge 替换（部分覆盖），展开 base_url / api_key 中的环境变量占位符
    if "judge" in overrides:
        expanded_judge = {
            k: (_expand_env(str(v)) if k in ("base_url", "api_key") else v)
            for k, v in overrides["judge"].items()
        }
        cfg["judge"].update(expanded_judge)
    # 简单字段覆盖（有意排除 round1_task）
    for key in ("middle_task", "final_task", "constraints", "judge_instructions",
                "max_reply_tokens", "timeout", "cross_exam", "early_stop", "cot",
                "compact_threshold", "compact_message"):
        if key in overrides:
            cfg[key] = overrides[key]


def resolve_effective_config(log: "Log") -> dict:
    """从 log 的 initial_config + 所有 config_override entries 合并出当前有效配置。"""
    cfg = deepcopy(log.initial_config)
    for entry in log.all_entries():
        if entry.get("tag") == "config_override":
            _apply_overrides(cfg, entry.get("overrides", {}))
    return cfg


def _describe_overrides(overrides: dict) -> str:
    """生成 config_override entry 的人类可读摘要字符串。纯函数。"""
    parts = []
    for key in ("middle_task", "final_task", "constraints", "judge_instructions",
                "max_reply_tokens", "timeout", "cross_exam", "early_stop", "cot",
                "compact_threshold", "compact_message"):
        if key in overrides:
            parts.append(f"更新 {key}")
    if "add_debaters" in overrides:
        names = [d["name"] for d in overrides["add_debaters"]]
        parts.append(f"新增辩手：{', '.join(names)}")
    if "drop_debaters" in overrides:
        parts.append(f"移除辩手：{', '.join(overrides['drop_debaters'])}")
    if "judge" in overrides:
        parts.append("更新裁判配置")
    return "；".join(parts) if parts else "配置变更"


def modify_topic(
    topic_path: Path,
    *,
    set_fields: list[str] | None = None,
    add_debaters: list[str] | None = None,
    drop_debaters: list[str] | None = None,
    pivot_stances: list[str] | None = None,
    reason: str = "",
    force: bool = False,
) -> None:
    """Modify topic file and append a @meta/modify event to the log.

    --set  debater.A.model=gpt-5        (or judge.model=claude, or rounds=5)
    --add  "C|gpt-5.2|激进派风格"        (name|model|style)
    --drop B
    --pivot "A|新的立场描述"             (name|new_style)
    --reason "why this change"
    """
    import yaml

    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    raw_text = topic_path.read_text(encoding="utf-8")
    # Split frontmatter
    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        print("❌ topic 文件格式错误（缺少 YAML frontmatter）", file=sys.stderr)
        sys.exit(1)
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]

    log_path = build_log_path(topic_path)
    log_exists = log_path.exists()

    if log_exists:
        log = Log.load_from_file(log_path)
        log_debater_names = {
            e["name"]
            for e in log.entries
            if e.get("tag")
            not in ("summary", "cross_exam", "compact_checkpoint", "human", "meta", "thinking")
        }
    else:
        log = None
        log_debater_names: set[str] = set()

    changes: list[str] = []

    # ── --set ──
    for field_expr in set_fields or []:
        if "=" not in field_expr:
            print(f"⚠️ --set 格式应为 key=value: {field_expr}", file=sys.stderr)
            continue
        key, val = field_expr.split("=", 1)
        parts_key = key.strip().split(".")

        if parts_key[0] == "judge":
            if len(parts_key) == 2:
                fm.setdefault("judge", {})
                if isinstance(fm["judge"], str):
                    fm["judge"] = {"name": fm["judge"]}
                old = fm["judge"].get(parts_key[1], "")
                fm["judge"][parts_key[1]] = val
                changes.append(f"set judge.{parts_key[1]}: {old!r} → {val!r}")
        elif parts_key[0] == "debater" and len(parts_key) >= 3:
            target_name = parts_key[1]
            attr = parts_key[2]
            debaters_list = fm.get("debaters", [])
            matched = next(
                (d for d in debaters_list if d.get("name") == target_name), None
            )
            if matched is None:
                matched = next(
                    (d for d in debaters_list if d.get("name", "").startswith(target_name)),
                    None,
                )
            if matched is None:
                matched = next(
                    (d for d in debaters_list if target_name in d.get("name", "")),
                    None,
                )
            if matched is not None:
                old = matched.get(attr, "")
                matched[attr] = val
                changes.append(
                    f"set debater.{matched['name']}.{attr}: {old!r} → {val!r}"
                )
            else:
                print(f"⚠️ 未找到辩手 {target_name}", file=sys.stderr)
        else:
            # Top-level field
            old = fm.get(parts_key[0], "")
            fm[parts_key[0]] = int(val) if val.isdigit() else val
            changes.append(f"set {parts_key[0]}: {old!r} → {val!r}")

    # ── --add ──
    for spec in add_debaters or []:
        parts_spec = spec.split("|", 2)
        if len(parts_spec) < 2:
            print(f"⚠️ --add 格式: name|model|style  got: {spec}", file=sys.stderr)
            continue
        name, model_ = parts_spec[0].strip(), parts_spec[1].strip()
        style = parts_spec[2].strip() if len(parts_spec) > 2 else "中立观察者"
        fm.setdefault("debaters", [])
        if any(d.get("name") == name for d in fm["debaters"]):
            print(f"⚠️ 辩手 {name} 已存在，跳过 --add", file=sys.stderr)
            continue
        fm["debaters"].append({"name": name, "model": model_, "style": style})
        changes.append(f"add debater: {name} ({model_})")

    # ── --drop ──
    for name in drop_debaters or []:
        before = len(fm.get("debaters", []))
        fm["debaters"] = [d for d in fm.get("debaters", []) if d.get("name") != name]
        if len(fm.get("debaters", [])) < before:
            changes.append(f"drop debater: {name}")
            if name in log_debater_names and not force:
                print(
                    f"⚠️ 辩手 {name} 在 log 中有历史条目。"
                    f"其历史将保留在 log 中（以 [INACTIVE] 标记）。"
                    f"使用 --force 跳过此提示。"
                )
        else:
            print(f"⚠️ 未找到辩手 {name}", file=sys.stderr)

    # ── --pivot ──
    for spec in pivot_stances or []:
        parts_spec = spec.split("|", 1)
        if len(parts_spec) < 2:
            print(f"⚠️ --pivot 格式: name|new_style  got: {spec}", file=sys.stderr)
            continue
        name, new_style = parts_spec[0].strip(), parts_spec[1].strip()
        for d in fm.get("debaters", []):
            if d.get("name") == name:
                old_style = d.get("style", "")
                d["style"] = new_style
                changes.append(
                    f"pivot debater.{name}.style: {old_style!r} → {new_style!r}"
                )
                break
        else:
            print(f"⚠️ --pivot: 未找到辩手 {name}", file=sys.stderr)

    if not changes:
        print("⚠️ 没有任何修改", file=sys.stderr)
        return

    # Write updated topic file
    updated_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False)
    topic_path.write_text(f"---\n{updated_fm}---{body}", encoding="utf-8")
    print(f"✅ topic 文件已更新: {topic_path}")
    for c in changes:
        print(f"   • {c}")

    # Append @meta/modify event to log
    if log is not None:
        ts = datetime.now().isoformat()
        change_lines = "\n".join(f"- {c}" for c in changes)
        reason_line = f"\n\n原因：{reason}" if reason else ""
        meta_content = (
            f"**@meta/modify** `{ts}`\n\n"
            f"变更列表：\n{change_lines}"
            f"{reason_line}\n\n"
            f"_注：历史日志条目不受影响，以下续跑使用新配置。_"
        )
        log.add("@meta/modify", meta_content, "meta")
        print(f"   • 已追加 @meta/modify 事件到 log: {log_path}")


def validate_topic_log_consistency(log: "Log", *, force: bool = False) -> None:
    """v2 版本：比较 effective config 中的辩手列表与 log 中实际发言辩手，差异则 warning。

    Args:
        log: 已加载的 v2 Log 对象（含 initial_config + config_override entries）
        force: 若 True，跳过所有校验
    """
    if force:
        return
    planned = {d["name"] for d in resolve_effective_config(log)["debaters"]}
    actual = {e["name"] for e in log.all_entries() if e.get("tag") == "debater"}
    in_plan_not_spoke = planned - actual
    spoke_not_in_plan = actual - planned
    # Only warn if there are truly no entries — after compact, speeches are in checkpoint content
    if in_plan_not_spoke and not log.entries and not log._archived_entries:
        print(f"⚠️  计划辩手未发言：{in_plan_not_spoke}", file=sys.stderr)
    if spoke_not_in_plan:
        print(f"⚠️  发言辩手不在当前计划中：{spoke_not_in_plan}（可能已通过 drop_debaters 移除）", file=sys.stderr)


def _validate_api_config(cfg: dict) -> list[str]:
    issues: list[str] = []

    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()

    for idx, debater in enumerate(cfg.get("debaters", []), start=1):
        debater_name = debater.get("name", f"debater#{idx}")
        url = (debater.get("base_url", "") or debate_base_url).strip()
        key = (debater.get("api_key", "") or debate_api_key).strip()
        missing_fields: list[str] = []
        if not url:
            missing_fields.append("base_url")
        if not key:
            missing_fields.append("api_key")
        if missing_fields:
            issues.append(
                f"debaters[{idx}]({debater_name}): " + ", ".join(missing_fields)
            )

    judge = cfg.get("judge", {}) or {}
    judge_name = judge.get("name", "judge")
    judge_url = (judge.get("base_url", "") or debate_base_url).strip()
    judge_key = (judge.get("api_key", "") or debate_api_key).strip()
    judge_missing: list[str] = []
    if not judge_url:
        judge_missing.append("base_url")
    if not judge_key:
        judge_missing.append("api_key")
    if judge_missing:
        issues.append(f"judge({judge_name}): " + ", ".join(judge_missing))

    return issues
