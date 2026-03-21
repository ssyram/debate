"""Structural assertion helpers for debate-tool log validation.

Verify debate structure independently of exact golden text.
Operate on parsed log data dicts.
"""


class StructuralError(AssertionError):
    """Raised when a structural check fails."""
    pass


def _speech_entries(log_data: dict) -> list[dict]:
    """Entries that are regular speeches (no tag or empty tag)."""
    return [e for e in log_data.get("entries", []) if not e.get("tag")]


def _tagged(log_data: dict, tag: str) -> list[dict]:
    return [e for e in log_data.get("entries", []) if e.get("tag") == tag]


def _unique_names(entries: list[dict]) -> set[str]:
    return {e["name"] for e in entries if e.get("name")}


# ── Cross-exam ────────────────────────────────────────────────

def assert_cross_exam_rounds(
    log_data: dict,
    expected_rounds: "set[int]",
    debater_count: int,
):
    """Verify cross-exam entries appear only at expected round positions.

    expected_rounds: e.g. {1, 2, 5} means R1.5, R2.5, R5.5 should exist.
    """
    cx = _tagged(log_data, "cross_exam")

    if not expected_rounds:
        if cx:
            raise StructuralError(
                f"Expected no cross_exam but found {len(cx)}"
            )
        return

    # Count: each round has debater_count cross_exam entries (round-robin)
    expected_count = len(expected_rounds) * debater_count
    if len(cx) != expected_count:
        raise StructuralError(
            f"Cross-exam count: expected {expected_count} "
            f"({len(expected_rounds)} rounds × {debater_count}), got {len(cx)}"
        )

    # Determine which rounds actually have cross_exam by entry ordering
    actual_cx_rounds: set[int] = set()
    speech_count = 0
    current_round = 0
    for e in log_data.get("entries", []):
        tag = e.get("tag", "")
        if not tag:  # speech
            speech_count += 1
            current_round = (speech_count - 1) // debater_count + 1
        elif tag == "cross_exam":
            actual_cx_rounds.add(current_round)

    if actual_cx_rounds != expected_rounds:
        raise StructuralError(
            f"Cross-exam rounds: expected {sorted(expected_rounds)}, "
            f"got {sorted(actual_cx_rounds)}"
        )


def assert_no_cross_exam(log_data: dict):
    """Verify no cross_exam entries exist."""
    cx = _tagged(log_data, "cross_exam")
    if cx:
        raise StructuralError(f"Expected no cross_exam, found {len(cx)}")


# ── Judge ─────────────────────────────────────────────────────

def assert_no_judge(log_data: dict):
    """Verify no judge summary entry exists."""
    summaries = _tagged(log_data, "summary")
    if summaries:
        raise StructuralError(
            f"Expected no judge summary, found {len(summaries)}"
        )


def assert_has_judge(log_data: dict):
    """Verify exactly one judge summary entry exists."""
    summaries = _tagged(log_data, "summary")
    if len(summaries) != 1:
        raise StructuralError(
            f"Expected 1 judge summary, found {len(summaries)}"
        )


# ── Debaters ──────────────────────────────────────────────────

def assert_debater_count(log_data: dict, expected: int):
    """Verify correct number of unique debater names in speeches."""
    names = _unique_names(_speech_entries(log_data))
    if len(names) != expected:
        raise StructuralError(
            f"Debater count: expected {expected}, got {len(names)} ({names})"
        )


# ── Rounds ────────────────────────────────────────────────────

def assert_round_count(log_data: dict, expected_rounds: int, debater_count: int):
    """Verify speech entries / debater_count == expected_rounds."""
    speeches = len(_speech_entries(log_data))
    actual = speeches // max(debater_count, 1)
    if actual != expected_rounds:
        raise StructuralError(
            f"Round count: expected {expected_rounds}, "
            f"got {actual} ({speeches} speeches / {debater_count} debaters)"
        )


def assert_entry_count(log_data: dict, expected: int):
    """Verify total entry count."""
    actual = len(log_data.get("entries", []))
    if actual != expected:
        raise StructuralError(
            f"Entry count: expected {expected}, got {actual}"
        )


# ── CoT ───────────────────────────────────────────────────────

def assert_has_cot(log_data: dict, min_count: int = 1):
    """Verify at least min_count thinking entries exist."""
    thinking = _tagged(log_data, "thinking")
    if len(thinking) < min_count:
        raise StructuralError(
            f"CoT: expected >= {min_count} thinking entries, got {len(thinking)}"
        )


def assert_no_cot(log_data: dict):
    """Verify no thinking entries."""
    thinking = _tagged(log_data, "thinking")
    if thinking:
        raise StructuralError(
            f"Expected no CoT thinking, found {len(thinking)}"
        )


# ── Resume ────────────────────────────────────────────────────

def assert_resume_appended(before_data: dict, after_data: dict):
    """Verify after_data has strictly more entries and prefix matches."""
    before_entries = before_data.get("entries", [])
    after_entries = after_data.get("entries", [])

    if len(after_entries) <= len(before_entries):
        raise StructuralError(
            f"Resume didn't append: before={len(before_entries)}, "
            f"after={len(after_entries)}"
        )

    # Verify prefix: all before entries exist in after (by seq, tag, name, content)
    for i, be in enumerate(before_entries):
        ae = after_entries[i]
        for key in ("seq", "tag", "name", "content"):
            if be.get(key) != ae.get(key):
                raise StructuralError(
                    f"Resume prefix mismatch at entry {i+1}, "
                    f"key={key}: {be.get(key)!r} != {ae.get(key)!r}"
                )


# ── Compact ──────────────────────────────────────────────────

def assert_has_compact_checkpoint(log_data: dict, min_count: int = 1):
    """Verify at least min_count compact_checkpoint entries exist."""
    cps = _tagged(log_data, "compact_checkpoint")
    if len(cps) < min_count:
        raise StructuralError(
            f"Compact: expected >= {min_count} compact_checkpoint, got {len(cps)}"
        )


def assert_compact_idempotent(before_data: dict, after_data: dict):
    """Verify double compact doesn't break semantics.

    After a second compact with no new debate entries, the number of
    compact_checkpoint entries should not increase (no new delta → no
    new checkpoint) OR should increase by at most 1 with equivalent state.
    Non-checkpoint entries must remain unchanged.
    """
    before_cps = [e for e in before_data.get("entries", [])
                  if e.get("tag") == "compact_checkpoint"]
    after_cps = [e for e in after_data.get("entries", [])
                 if e.get("tag") == "compact_checkpoint"]

    before_non_cp = [e for e in before_data.get("entries", [])
                     if e.get("tag") != "compact_checkpoint"]
    after_non_cp = [e for e in after_data.get("entries", [])
                    if e.get("tag") != "compact_checkpoint"]

    # Non-checkpoint entries must be identical
    if len(before_non_cp) != len(after_non_cp):
        raise StructuralError(
            f"Compact idempotent: non-checkpoint entries changed "
            f"{len(before_non_cp)} → {len(after_non_cp)}"
        )

    for i, (be, ae) in enumerate(zip(before_non_cp, after_non_cp)):
        for key in ("name", "tag", "content"):
            if be.get(key) != ae.get(key):
                raise StructuralError(
                    f"Compact idempotent: non-checkpoint entry {i+1} "
                    f"differs at key={key}"
                )

    # Checkpoint count should be stable or grow by at most 1
    if len(after_cps) > len(before_cps) + 1:
        raise StructuralError(
            f"Compact idempotent: checkpoint count jumped "
            f"{len(before_cps)} → {len(after_cps)}"
        )
