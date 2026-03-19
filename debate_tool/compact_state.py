"""
compact_state.py — debate-tool LLM 语义压缩模块

定义辩论压缩状态的 TypedDict 结构，以及用于构建 LLM prompt、
校验状态一致性、渲染 Markdown 视图等全部工具函数。

此模块仅使用 Python 标准库，不引入外部依赖。
"""

import json
from typing import TypedDict, Literal


# ---------------------------------------------------------------------------
# TypedDict 定义
# ---------------------------------------------------------------------------

class Claim(TypedDict):
    id: str                          # 例如 "A1", "B2"
    text: str
    status: Literal["active", "abandoned"]


class Argument(TypedDict):
    id: str                          # 例如 "A1-arg1"
    claim_id: str
    text: str
    status: Literal["active", "weakened", "refuted"]


class AbandonedClaim(TypedDict):
    id: str
    original_text: str
    reason: str
    decided_by: Literal["self", "opponent", "judge", "consensus"]


class ParticipantState(TypedDict):
    name: str
    active: bool  # True = 在辩论中；False = 已通过 drop_debaters 退出
    stance_version: int
    stance: str  # 基于上一版本增量更新的辩手立场笔记
    core_claims: list[Claim]
    key_arguments: list[Argument]
    abandoned_claims: list[AbandonedClaim]


class Dispute(TypedDict):
    id: str
    title: str
    status: Literal["open", "resolved"]
    positions: dict[str, str]        # {debater_name: position_text}
    resolution: str | None


class PrunedPath(TypedDict):
    id: str
    description: str
    reason: str
    decided_by: str
    merged: bool
    merged_from: list[str] | None


class CompactState(TypedDict):
    compact_version: int             # schema version = 1
    covered_seq_end: int
    prev_compact_seq: int | None
    topic: dict  # LLM 生成的辩题演进摘要（非原始辩题文本，原始文本在 Log.topic）；结构：{"current_formulation": str, "notes": str|None}
    participants: list[ParticipantState]
    axioms: list[str]
    disputes: list[Dispute]
    pruned_paths: list[PrunedPath]


class CompactCheckpointContent(TypedDict):
    state: CompactState
    public_view: str


# ---------------------------------------------------------------------------
# 校验函数
# ---------------------------------------------------------------------------

def validate_public_info(new: dict, prev: dict | None) -> tuple[bool, list[str]]:
    """
    校验 Phase A 生成的公共信息的单调性约束。

    规则：
    - axioms 只能新增，不能删除（new.axioms ⊇ prev.axioms）
    - pruned_paths 只能新增或 merge（不能删除已有 id）
    - resolved disputes 不能逆转（resolved → open 为违规）

    返回 (is_valid, list_of_error_messages)
    """
    errors: list[str] = []

    if prev is None:
        return True, []

    # --- axioms 单调性 ---
    prev_axioms: list[str] = prev.get("axioms", [])
    new_axioms: list[str] = new.get("axioms", [])
    new_axioms_set = set(new_axioms)
    for axiom in prev_axioms:
        if axiom not in new_axioms_set:
            errors.append(f'axiom 被删除（单调性违规）："{axiom}"')

    # --- pruned_paths 单调性（按 id 检查）---
    prev_paths: list[dict] = prev.get("pruned_paths", [])
    new_paths: list[dict] = new.get("pruned_paths", [])

    # 新路径中，merged=True 的条目展开 merged_from 视为覆盖了对应 id
    covered_by_merge: set[str] = set()
    for p in new_paths:
        if p.get("merged") and p.get("merged_from"):
            for mid in p["merged_from"]:
                covered_by_merge.add(mid)

    new_path_ids: set[str] = {p["id"] for p in new_paths}
    for old_path in prev_paths:
        old_id = old_path["id"]
        if old_id not in new_path_ids and old_id not in covered_by_merge:
            errors.append(f"pruned_path 被删除（单调性违规）：id={old_id}")

    # --- resolved disputes 不能逆转 ---
    prev_disputes: list[dict] = prev.get("disputes", [])
    new_disputes: list[dict] = new.get("disputes", [])
    prev_dispute_map: dict[str, str] = {d["id"]: d["status"] for d in prev_disputes}
    new_dispute_map: dict[str, str] = {d["id"]: d["status"] for d in new_disputes}

    for did, prev_status in prev_dispute_map.items():
        if prev_status == "resolved":
            new_status = new_dispute_map.get(did)
            if new_status == "open":
                errors.append(
                    f"dispute id={did} 已 resolved，不能逆转回 open（单调性违规）"
                )

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_participant_state(ps: dict) -> bool:
    """
    JSON 结构校验：检查 ParticipantState 必要字段是否都存在。
    """
    required_fields = [
        "name",
        "active",
        "stance_version",
        "stance",
        "core_claims",
        "key_arguments",
        "abandoned_claims",
    ]
    return all(field in ps for field in required_fields)


# ---------------------------------------------------------------------------
# 渲染函数
# ---------------------------------------------------------------------------

def render_public_markdown(state: CompactState) -> str:
    """
    渲染公共视图 Markdown。
    """
    lines: list[str] = []

    covered_seq_end = state.get("covered_seq_end", "?")
    lines.append(f"## 辩论状态快照（覆盖至第 {covered_seq_end} 条发言）")
    lines.append("")

    # 1. 当前议题
    lines.append("### 1. 当前议题")
    topic = state.get("topic", {})
    current_formulation = topic.get("current_formulation", "（未设置）")
    notes = topic.get("notes")
    lines.append(current_formulation)
    if notes:
        lines.append(f"> {notes}")
    lines.append("")

    # 2. 已达成共识
    lines.append("### 2. 已达成共识（不可再争）")
    axioms: list[str] = state.get("axioms", [])
    if axioms:
        for i, axiom in enumerate(axioms, 1):
            lines.append(f"{i}. {axiom}")
    else:
        lines.append("（暂无）")
    lines.append("")

    # 3. 当前争点
    lines.append("### 3. 当前争点")
    disputes: list[Dispute] = state.get("disputes", [])
    if disputes:
        lines.append("| ID | 争点 | 状态 |")
        lines.append("|-----|------|------|")
        for d in disputes:
            status_icon = "🔴 开放" if d["status"] == "open" else "✅ 已解决"
            lines.append(f"| {d['id']} | {d['title']} | {status_icon} |")
        lines.append("")
        # 展开 open 争点的双方立场
        open_disputes = [d for d in disputes if d["status"] == "open"]
        if open_disputes:
            for d in open_disputes:
                lines.append(f"**[{d['id']}] {d['title']}**")
                positions: dict[str, str] = d.get("positions", {})
                for debater_name, position_text in positions.items():
                    lines.append(f"- {debater_name}：{position_text}")
                lines.append("")
    else:
        lines.append("（暂无）")
        lines.append("")

    # 4. 已否决路径
    lines.append("### 4. 已否决路径（⛔ 禁止以任何变体形式重新提出）")
    pruned_paths: list[PrunedPath] = state.get("pruned_paths", [])
    if pruned_paths:
        for p in pruned_paths:
            lines.append(
                f"- **[{p['id']}]** {p['description']} → 否决原因：{p['reason']}"
            )
    else:
        lines.append("（暂无）")

    return "\n".join(lines)


def render_stance_for_system(participant_state: ParticipantState) -> str:
    """
    渲染辩手独有的 system prompt 注入段。
    """
    lines: list[str] = []

    lines.append("【你当前的辩论立场（已替代初始立场中的观点部分）】")
    lines.append("")
    lines.append("当前立场笔记：")
    lines.append(participant_state['stance'])
    lines.append("")

    # 当前核心主张
    lines.append("当前核心主张：")
    core_claims: list[Claim] = participant_state.get("core_claims", [])
    if core_claims:
        for i, claim in enumerate(core_claims, 1):
            lines.append(f"{i}. [{claim['id']}] {claim['text']}（{claim['status']}）")
    else:
        lines.append("（暂无）")
    lines.append("")

    # 关键论据
    lines.append("关键论据：")
    key_arguments: list[Argument] = participant_state.get("key_arguments", [])
    if key_arguments:
        for arg in key_arguments:
            lines.append(f"- [{arg['id']}] {arg['text']}（{arg['status']}）")
    else:
        lines.append("（暂无）")

    # 已放弃的主张（有才显示）
    abandoned_claims: list[AbandonedClaim] = participant_state.get("abandoned_claims", [])
    if abandoned_claims:
        lines.append("")
        lines.append("已放弃的主张（不得以任何变体重新提出）：")
        for ac in abandoned_claims:
            lines.append(
                f"- ~~[{ac['id']}] {ac['original_text']}~~ "
                f"→ {ac['decided_by']} 放弃。原因：{ac['reason']}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt 构建函数
# ---------------------------------------------------------------------------

_PHASE_A_OUTPUT_SCHEMA = """\
{
  "topic": {
    "current_formulation": "<当前辩题表述（string）>",
    "notes": "<补充说明，可为 null>"
  },
  "axioms": ["<已达成共识的陈述（string）>", ...],
  "disputes": [
    {
      "id": "<争点ID，如 D1>",
      "title": "<争点标题（string）>",
      "status": "open" | "resolved",
      "positions": {
        "<辩手名>": "<该辩手在此争点上的立场（string）>"
      },
      "resolution": "<解决说明，仅 resolved 时填写，否则为 null>"
    }
  ],
  "pruned_paths": [
    {
      "id": "<路径ID，如 P1>",
      "description": "<被否决路径的简述（string）>",
      "reason": "<否决原因（string）>",
      "decided_by": "<谁决定否决，如辩手名或 judge>",
      "merged": false,
      "merged_from": null
    }
  ]
}"""

_PHASE_A_SYSTEM = """\
你是辩论状态提取器。
你的职责是：仅负责公共信息的提取与更新，包括当前辩题、已达成共识（axioms）、当前争点（disputes）、已否决路径（pruned_paths）。
不要涉及任何单个辩手的立场细节，那部分由 Phase B 处理。

输出格式：严格 JSON，不附加任何解释文字。"""

_PHASE_A_MONOTONICITY = """\
【单调性约束（必须严格遵守）】
1. axioms（共识）只能新增，不能删除已有条目。
2. pruned_paths（已否决路径）只能新增或合并，不能删除已有条目的 id。
   - 若 pruned_paths 超过 10 条，应将最早的若干条目合并为一条 merged=true 的条目，
     merged_from 设为被合并条目的 id 列表，description 简要概括合并内容。
3. disputes 中 status=resolved 的条目不能逆转回 open。"""


def build_phase_a_prompt(
    prev_state: dict | None,
    delta_entries: list[dict],
    compact_message: str = "",
) -> tuple[str, str]:
    """
    构建 Phase A（公共信息生成）的 (system, user) prompt。
    """
    system = _PHASE_A_SYSTEM

    user_parts: list[str] = []

    # 前一状态（只保留公共字段）
    if prev_state is not None:
        public_prev = {
            "topic": prev_state.get("topic"),
            "axioms": prev_state.get("axioms", []),
            "disputes": prev_state.get("disputes", []),
            "pruned_paths": prev_state.get("pruned_paths", []),
        }
        user_parts.append("## 上一次压缩快照的公共状态（JSON）")
        user_parts.append("```json")
        user_parts.append(json.dumps(public_prev, ensure_ascii=False, indent=2))
        user_parts.append("```")
        user_parts.append("")
    else:
        user_parts.append("## 说明")
        user_parts.append("这是首次压缩，无上一次快照。")
        user_parts.append("")

    # 增量发言记录
    user_parts.append("## 新增辩论发言（增量）")
    delta_text = format_delta_entries_text(delta_entries)
    if delta_text.strip():
        user_parts.append(delta_text)
    else:
        user_parts.append("（无新增发言）")
    user_parts.append("")

    # 单调性约束
    user_parts.append(_PHASE_A_MONOTONICITY)
    user_parts.append("")

    # 输出 schema
    user_parts.append("## 输出要求")
    user_parts.append(
        "请根据以上信息，输出更新后的公共状态 JSON，严格遵守以下 schema："
    )
    user_parts.append("```json")
    user_parts.append(_PHASE_A_OUTPUT_SCHEMA)
    user_parts.append("```")
    user_parts.append("")
    user_parts.append(
        "注意：disputes.positions 字段是 dict，key 为辩手名称（string），value 为该辩手在此争点上的立场（string）。"
    )

    if compact_message:
        user_parts.append("")
        user_parts.append("## 额外保留/注意事项（用户指定）")
        user_parts.append(compact_message)

    user = "\n".join(user_parts)
    return system, user


_PHASE_B_OUTPUT_SCHEMA = """\
{
  "name": "<辩手名称（string）>",
  "active": true,
  "stance_version": <版本号，整数，每次更新加1>,
  "stance": "<以基底文本（initial_style 或上一版本 stance）为起点，对原文做最小精化：参考 core_claims/key_arguments/abandoned_claims 的变化，只修改确实改变的部分；若立场无实质变化则与基底高度相似；不要压缩成一句话，保留原始风格和语气（string）>",
  "core_claims": [
    {
      "id": "<主张ID，如 A1>",
      "text": "<主张内容（string）>",
      "status": "active" | "abandoned"
    }
  ],
  "key_arguments": [
    {
      "id": "<论据ID，如 A1-arg1>",
      "claim_id": "<所属主张ID>",
      "text": "<论据内容（string）>",
      "status": "active" | "weakened" | "refuted"
    }
  ],
  "abandoned_claims": [
    {
      "id": "<主张ID>",
      "original_text": "<原始主张文本>",
      "reason": "<放弃原因>",
      "decided_by": "self" | "opponent" | "judge" | "consensus"
    }
  ]
}"""

_PHASE_B_SYSTEM_TEMPLATE = """\
你是辩手「{name}」的立场追踪器。
你的任务是：根据辩论过程，更新该辩手的立场状态 JSON。

约束：
- 只更新确实在辩论过程中发生了变化的部分。
- 不要因对方的攻击就轻易改变立场；只有辩手本人明确承认或裁判裁定时，才标记为 abandoned 或 weakened/refuted。
- stance_version 每次更新时加 1。
- stance 字段：这不是新生成的摘要，而是对基底文本（initial_style 或上一版本 stance）的最小精化版本。以基底文本的原文为起点，只做必要的修改：参考 core_claims 中 active/abandoned 的变化、key_arguments 中 status 的变化、abandoned_claims 中明确放弃的主张。修改量应尽量小：如果辩论中立场没有实质变化，stance 应与基底文本高度相似。**不要压缩成一句话；保留原始风格和语气；只精化，不改写**。
- 输出严格 JSON，不附加任何解释文字。"""


def build_phase_b_prompt(
    debater: dict,
    initial_style: str,
    delta_entries: list[dict],
    prev_stance: str = "",
    compact_message: str = "",
    prev_participant: "dict | None" = None,
) -> tuple[str, str]:
    """
    构建 Phase B（辩手立场自更新）的 (system, user) prompt。

    参数：
    - debater: 包含 name, model, style 等字段的 dict
    - initial_style: 原始 topic 中该辩手的 style 字符串
    - delta_entries: 全部增量条目（不过滤辩手，cross_exam 全部给看）
    - prev_stance: 上一次 compact 的 stance（空字符串表示首次）
    - prev_participant: 上一次 compact 的完整辩手状态（含 core_claims / key_arguments / abandoned_claims）

    注意：active 字段过滤由调用方（runner.py）负责——调用方在遍历 participants 时
    应跳过 active == False 的辩手，不再对其调用本函数。
    """
    name = debater.get("name", "未知辩手")
    system = _PHASE_B_SYSTEM_TEMPLATE.format(name=name)

    user_parts: list[str] = []

    # 初始立场
    user_parts.append("## 该辩手的初始立场（style）")
    user_parts.append(initial_style.strip() if initial_style else "（未提供）")
    user_parts.append("")

    # stance 基底文本：上一次的 stance 优先；首次则用 initial_style
    user_parts.append("## stance 的基底文本（以此为起点做最小修改，不要重新生成摘要）")
    user_parts.append(prev_stance if prev_stance else (initial_style.strip() if initial_style else "（未提供）"))
    user_parts.append("")

    # 上一次 compact 的结构化基底（若有）——让模型以此为起点做增量更新而非从零生成
    if prev_participant:
        user_parts.append("## 上一次 compact 的结构化基底（以此为起点，仅对增量发言中变化的部分做最小修改）")
        prev_core = prev_participant.get("core_claims", [])
        prev_args = prev_participant.get("key_arguments", [])
        prev_abandoned = prev_participant.get("abandoned_claims", [])
        prev_struct = {
            "core_claims": prev_core,
            "key_arguments": prev_args,
            "abandoned_claims": prev_abandoned,
        }
        user_parts.append("```json")
        user_parts.append(json.dumps(prev_struct, ensure_ascii=False, indent=2))
        user_parts.append("```")
        user_parts.append("")

    # 辩论增量记录（全部，不过滤）
    user_parts.append("## 辩论发言记录（全部增量）")
    delta_text = format_delta_entries_text(delta_entries)
    if delta_text.strip():
        user_parts.append(delta_text)
    else:
        user_parts.append("（无新增发言）")
    user_parts.append("")

    # 输出 schema
    user_parts.append("## 输出要求")
    user_parts.append(
        f"请根据以上辩论记录，更新辩手「{name}」的立场状态，输出以下格式的 JSON："
    )
    user_parts.append("```json")
    user_parts.append(_PHASE_B_OUTPUT_SCHEMA)
    user_parts.append("```")
    user_parts.append("")
    if prev_participant:
        user_parts.append(
            "特别说明：上方「上一次 compact 的结构化基底」是你的起点。"
            "core_claims / key_arguments / abandoned_claims 以该基底为准，只更新增量发言中确实发生变化的条目；"
            "未在增量发言中出现的条目原样保留，不要删减。"
            "stance 字段同样以「stance 的基底文本」为起点做最小修改。"
        )
    else:
        user_parts.append(
            "特别说明（stance 字段）：上方「stance 的基底文本」就是你的写作起点。"
            "以该原文为基础，只对辩论中确实发生变化的部分做最小修改；"
            "若立场无实质变化，stance 应与基底文本高度相似，不要重新概括或压缩。"
        )

    if compact_message:
        user_parts.append("")
        user_parts.append("## 额外保留/注意事项（用户指定）")
        user_parts.append(compact_message)

    user = "\n".join(user_parts)
    return system, user


def build_validity_check_prompt(stance_json: str) -> tuple[str, str]:
    """
    构建合理性校验的 (system, user) prompt。
    """
    system = "你是辩论立场校验器。判断给定的辩手立场描述是否合理、自洽。"
    user = (
        f"{stance_json}\n\n"
        "这是否是一个合理、自洽的辩论立场？只回答 yes 或 no"
    )
    return system, user


# ---------------------------------------------------------------------------
# 配置提取函数
# ---------------------------------------------------------------------------

def get_compact_model_config(cfg: dict) -> tuple[str, str, str]:
    """
    从 topic cfg 中提取 compact_model 配置，返回 (model, base_url, api_key)。

    # v2 log 中，compact 配置存于 log.initial_config（通过 resolve_effective_config 获取）
    """
    model = cfg.get("compact_model")
    if not model:
        raise ValueError(
            "compact_model 未配置，请在 topic YAML 中设置 compact_model 字段"
        )

    base_url: str = (
        cfg.get("compact_base_url")
        or cfg.get("base_url")
        or ""
    )
    if not base_url:
        raise ValueError(
            "compact_base_url 未配置，请在 topic YAML 中设置 compact_base_url 或 base_url"
        )

    api_key: str = (
        cfg.get("compact_api_key")
        or cfg.get("api_key")
        or ""
    )

    return model, base_url, api_key


def get_check_model_config(cfg: dict) -> tuple[str, str, str]:
    """
    从 topic cfg 中提取 compact_check_model 配置，返回 (model, base_url, api_key)。
    """
    model = cfg.get("compact_check_model")
    if not model:
        raise ValueError(
            "compact_check_model 未配置，请在 topic YAML 中设置 compact_check_model 字段"
        )

    base_url: str = (
        cfg.get("compact_check_base_url")
        or cfg.get("compact_base_url")
        or cfg.get("base_url")
        or ""
    )

    api_key: str = (
        cfg.get("compact_check_api_key")
        or cfg.get("compact_api_key")
        or cfg.get("api_key")
        or ""
    )

    return model, base_url, api_key


def get_embedding_config(cfg: dict) -> tuple[str, str, str]:
    """
    从 topic cfg 中提取 embedding 配置，返回 (model, base_url, api_key)。
    """
    model = cfg.get("compact_embedding_model")
    if not model:
        raise ValueError(
            "compact_embedding_model 未配置，请在 topic YAML 中设置 compact_embedding_model 字段"
        )

    base_url = cfg.get("compact_embedding_url")
    if not base_url:
        raise ValueError(
            "compact_embedding_url 未配置，请在 topic YAML 中设置 compact_embedding_url 字段"
        )

    api_key = cfg.get("compact_embedding_api_key")
    if not api_key:
        raise ValueError(
            "compact_embedding_api_key 未配置，请在 topic YAML 中设置 compact_embedding_api_key 字段"
        )

    return model, base_url, api_key


# ---------------------------------------------------------------------------
# Delta 处理工具
# ---------------------------------------------------------------------------

_TAG_LABEL_MAP: dict[str, str] = {
    "summary": "裁判总结",
    "cross_exam": "质询",
    "compact_checkpoint": "压缩快照",
    "": "发言",
}


def filter_debater_delta(entries: list[dict], debater_name: str) -> list[dict]:
    """
    过滤辩手应看到的增量条目。
    当前实现：直接返回所有 entries（cross_exam 全部给所有辩手看）。
    """
    return entries


def merge_pruned_paths_if_needed(paths: list[PrunedPath]) -> list[PrunedPath]:
    """
    若 paths 超过 10 条，把最早的条目合并为一条 merged=True 的条目，
    使总条数 <= 10。
    """
    max_paths = 10
    if len(paths) <= max_paths:
        return paths

    # 需要合并的数量：使总数 <= 10，保留最后 (max_paths - 1) 条
    keep_tail = max_paths - 1
    to_merge = paths[: len(paths) - keep_tail]
    to_keep = paths[len(paths) - keep_tail :]

    merged_ids = [p["id"] for p in to_merge]
    merged_descriptions = "; ".join(
        f"{p['id']}（{p['description'][:20]}{'…' if len(p['description']) > 20 else ''}）"
        for p in to_merge
    )

    merged_entry: PrunedPath = {
        "id": f"MERGED-{merged_ids[0]}-{merged_ids[-1]}",
        "description": f"合并条目：{merged_descriptions}",
        "reason": "路径数量超限，自动合并最早条目",
        "decided_by": "system",
        "merged": True,
        "merged_from": merged_ids,
    }

    return [merged_entry] + to_keep


def format_delta_entries_text(entries: list[dict]) -> str:
    """
    将 entries 格式化为文本，供 LLM prompt 使用。

    - 跳过 tag == "thinking" 的条目
    - 格式：[{seq}] {name}（{tag_label}）\\n{content}
    - 条目间以 \\n\\n---\\n\\n 分隔
    """
    formatted: list[str] = []

    for entry in entries:
        tag = entry.get("tag", "")
        if tag in ("thinking", "summary", "compact_checkpoint", "config_override"):
            continue

        seq = entry.get("seq", "?")
        name = entry.get("name", "未知")
        content = entry.get("content", "")

        tag_label = _TAG_LABEL_MAP.get(tag, tag if tag else "发言")

        block = f"[{seq}] {name}（{tag_label}）\n{content}"
        formatted.append(block)

    return "\n\n---\n\n".join(formatted)


def build_stance_drift_check_prompt(
    debater_name: str,
    initial_style: str,
    ref_notes: str,
    new_notes: str,
    new_stance_json: str,
    cos_sim: float,
) -> tuple[str, str]:
    """当 embedding cosine similarity < 0.6 时，构造发给 check_model 的 prompt，
    判断辩手新立场是"合理细化"还是"投敌"（立场根本倒转）。

    Returns:
        tuple[str, str]: (system_prompt, user_prompt)
    """
    system_prompt = (
        "你是辩论立场漂移检查器。\n\n"
        "任务：判断一个辩手的新立场是否属于合理细化，还是已经实质性地背叛了自己的阵营（\u201c投敌\u201d）。\n\n"
        "【合理细化的定义】\n"
        "以下情况均属于合理演进，**不是**投敌：\n"
        "- 聚焦到更具体的论点\n"
        "- 引入新证据支持同一阵营\n"
        "- 修辞措辞变化\n"
        "- 放弃被彻底反驳的子论点\n\n"
        "【投敌的定义】\n"
        "以下情况才构成投敌：\n"
        "- 新立场的核心主张与初始立场相反\n"
        "- 开始论证对方阵营的核心观点\n"
        "- 全面认同对方并否定己方阵营\n\n"
        "【重要提示】\n"
        "辩手在辩论中细化立场是正常且健康的。只有在立场根本倒转时才应判定为投敌。\n"
        "cos_sim 值仅供参考，词汇变化可能导致低 cos 但立场一致，不要仅凭 cos 判断。\n\n"
        "【回答格式】\n"
        "第一行必须是 `REFINEMENT` 或 `DEFECTION`，第二行开始是简短理由（50字以内）。"
    )

    user_prompt = (
        f"辩手：{debater_name}\n\n"
        f"初始立场描述：\n{initial_style[:300]}\n\n"
        f"参考立场笔记（上一版本）：\n{ref_notes}\n\n"
        f"新立场笔记：\n{new_notes}\n\n"
        f"新立场完整内容：\n{new_stance_json[:600]}\n\n"
        f"Embedding 余弦相似度：{cos_sim:.3f}（低于 0.6 触发本次检查）\n\n"
        "请判断：这是合理细化还是投敌？"
    )

    return system_prompt, user_prompt


def build_stance_correction_prompt(
    debater_name: str,
    initial_style: str,
    prev_notes: str | None,
    problematic_stance_json: str,
    delta_entries: list[dict],
    defection_feedback: str,
    include_initial: bool = False,
) -> tuple[str, str]:
    """
    构建立场修正的 (system, user) prompt。

    当检查器判定辩手立场发生 DEFECTION（投敌）时，要求辩手在保留合理演进的
    前提下修正立场，使其回到己方阵营。

    参数：
    - debater_name: 辩手名称
    - initial_style: 原始 topic 中该辩手的 style 字符串
    - prev_notes: 上一次 compact 的 stance（可能为 None）
    - problematic_stance_json: 被判断为偏移的立场 JSON 字符串
    - delta_entries: 辩论增量记录
    - defection_feedback: 检查器给出的 DEFECTION 理由
    - include_initial: cos_init < 0.4 时为 True，要求特别强调回到初始阵营

    返回 (system_prompt, user_prompt)
    """
    # 构建 system prompt
    system_parts: list[str] = []
    system_parts.append(f"你是辩手「{debater_name}」。")
    system_parts.append("")
    system_parts.append(
        "说明：你之前生成了一份辩论立场，但被检查器判定为偏离己方阵营（\u201c投敌\u201d）。"
    )
    system_parts.append("")
    system_parts.append(
        "任务：在保留辩论中合理演进（有真实依据的论点调整、放弃被彻底反驳的子论点）的前提下，"
        "修正立场使其回到己方阵营。"
    )
    system_parts.append("")
    system_parts.append("约束：")
    system_parts.append("- 不得论证对方的核心观点")
    system_parts.append("- 不得全面承认失败")
    if include_initial:
        system_parts.append("")
        system_parts.append(
            "⚠️ 特别警告：你的立场距离初始阵营已经非常远，请务必回到初始立场的核心主张，"
            "细化可以，但不能倒戈。"
        )
    system_parts.append("")
    system_parts.append(
        "输出 JSON，字段同 ParticipantState"
        "（name/active/stance_version/stance/core_claims/key_arguments/abandoned_claims）。"
        "输出严格 JSON，不附加任何解释文字。"
    )

    system_prompt = "\n".join(system_parts)

    # 构建 user prompt
    user_parts: list[str] = []

    # 1. 检查器判定反馈（前 200 字）
    user_parts.append("检查器的判定反馈：")
    user_parts.append(defection_feedback[:200])
    user_parts.append("")

    # 2. 上一版本立场笔记（若存在）
    if prev_notes is not None:
        user_parts.append(f"上一版本立场笔记（参考）：{prev_notes}")
        user_parts.append("")

    # 3. 初始立场（cos_init < 0.4 时特别强调）
    if include_initial:
        user_parts.append(f"初始立场（必须回归的核心）：{initial_style[:300]}")
        user_parts.append("")

    # 4. 有问题的立场 JSON
    user_parts.append(f"有问题的立场 JSON：{problematic_stance_json[:800]}")
    user_parts.append("")

    # 5. 辩论增量记录（前 1500 字符）
    user_parts.append("辩论增量记录：")
    delta_text = format_delta_entries_text(delta_entries)
    user_parts.append(delta_text[:1500])
    user_parts.append("")

    # 6. 修正指令
    user_parts.append(
        "请在保留合理论点演进的前提下，修正上述有问题的立场，输出 JSON。"
    )

    user_prompt = "\n".join(user_parts)

    return system_prompt, user_prompt
