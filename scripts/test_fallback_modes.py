#!/usr/bin/env python3
"""测试 Phase B 降级模式的分层 Mock 测试"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from debate_tool.runner import _fallback_form_filling
from debate_tool.compact_state import validate_participant_state


async def test_level1_form_mode():
    """Level 1: 填表模式成功"""
    print("\n=== Test Level 1: 填表模式 ===")

    # Mock call_llm 返回填表格式
    mock_response = """STANCE:
幕府的失败是财政、军事、合法性三重危机的必然结果。

CORE_CLAIMS:
A1 | 幕府财政枯竭无法支撑军事现代化 | active
A2 | 合法性危机导致民心丧失 | active

KEY_ARGUMENTS:
A1-arg1 | A1 | 天保改革失败证明财政制度性缺陷 | active
A2-arg1 | A2 | 黑船来航后攘夷承诺破产 | active
"""

    debater = {"name": "必然派", "model": "gpt-4o-mini"}
    prev_participant = {
        "name": "必然派",
        "stance_version": 0,
        "stance": "初始立场",
        "core_claims": [],
        "key_arguments": [],
        "abandoned_claims": []
    }
    delta_entries = [{"seq": 1, "name": "必然派", "content": "测试发言"}]

    with patch('debate_tool.runner.call_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_response

        result = await _fallback_form_filling(
            debater, "初始风格", prev_participant, delta_entries, "", ""
        )

        assert result is not None, "Level 1 应返回结果"
        assert validate_participant_state(result), "结果应通过结构校验"
        assert result["stance"] == "幕府的失败是财政、军事、合法性三重危机的必然结果。"
        assert len(result["core_claims"]) == 2
        assert result["core_claims"][0]["id"] == "A1"
        print("✅ Level 1 填表模式测试通过")


async def test_level2_field_by_field():
    """Level 2: 逐字段问模式"""
    print("\n=== Test Level 2: 逐字段模式 ===")

    debater = {"name": "偶然派", "model": "gpt-4o-mini"}
    prev_participant = {
        "name": "偶然派",
        "stance_version": 1,
        "stance": "上一版本立场",
        "core_claims": [
            {"id": "B1", "text": "孝明天皇之死是关键偶然", "status": "active"},
            {"id": "B2", "text": "锦旗事件改变战局", "status": "active"}
        ],
        "key_arguments": [],
        "abandoned_claims": []
    }
    delta_entries = [{"seq": 2, "name": "偶然派", "content": "测试"}]

    # Mock: 填表失败，逐字段成功
    responses = [
        "INVALID FORM",  # Level 1 失败
        "幕府失败是多个偶然事件叠加的结果",  # stance
        "active",  # B1 状态
        "abandoned"  # B2 状态
    ]

    with patch('debate_tool.runner.call_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = responses

        result = await _fallback_form_filling(
            debater, "初始风格", prev_participant, delta_entries, "", ""
        )

        assert result is not None
        assert result["stance"] == "幕府失败是多个偶然事件叠加的结果"
        assert result["core_claims"][0]["status"] == "active"
        assert result["core_claims"][1]["status"] == "abandoned"
        print("✅ Level 2 逐字段模式测试通过")


async def test_level3_multiple_choice():
    """Level 3: 选择题模式"""
    print("\n=== Test Level 3: 选择题模式 ===")

    debater = {"name": "中立派", "model": "gpt-4o-mini"}
    prev_participant = {
        "name": "中立派",
        "stance_version": 2,
        "stance": "上一版本立场",
        "core_claims": [
            {"id": "C1", "text": "结构与偶然并存", "status": "active"},
            {"id": "C2", "text": "胜率约30%", "status": "active"}
        ],
        "key_arguments": [],
        "abandoned_claims": []
    }
    delta_entries = []

    # Mock: Level 1/2 失败，Level 3 成功
    responses = [
        "INVALID",  # Level 1
        Exception("stance 失败"),  # Level 2 stance
        "A",  # C1: A=有效
        "B"   # C2: B=放弃
    ]

    with patch('debate_tool.runner.call_llm', new_callable=AsyncMock) as mock_llm:
        def side_effect_func(*args, **kwargs):
            resp = responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        mock_llm.side_effect = side_effect_func

        result = await _fallback_form_filling(
            debater, "初始风格", prev_participant, delta_entries, "", ""
        )

        assert result is not None
        assert result["core_claims"][0]["status"] == "active"  # A
        assert result["core_claims"][1]["status"] == "abandoned"  # B
        print("✅ Level 3 选择题模式测试通过")


async def test_level4_preserve_previous():
    """Level 4: 完全保留上次状态"""
    print("\n=== Test Level 4: 保留上次状态 ===")

    debater = {"name": "测试派", "model": "gpt-4o-mini"}
    prev_participant = {
        "name": "测试派",
        "stance_version": 3,
        "stance": "上一版本立场",
        "core_claims": [{"id": "D1", "text": "测试主张", "status": "active"}],
        "key_arguments": [],
        "abandoned_claims": []
    }
    delta_entries = []

    # Mock: 所有层级全失败
    with patch('debate_tool.runner.call_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("全部失败")

        result = await _fallback_form_filling(
            debater, "初始风格", prev_participant, delta_entries, "", ""
        )

        assert result is not None
        assert result["stance_version"] == 4  # +1
        assert result["stance"] == "上一版本立场"  # 保留
        assert result["core_claims"] == prev_participant["core_claims"]
        print("✅ Level 4 保留模式测试通过")


async def test_no_previous_fallback():
    """无上次状态时返回 None"""
    print("\n=== Test: 无上次状态 ===")

    debater = {"name": "新辩手", "model": "gpt-4o-mini"}

    with patch('debate_tool.runner.call_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("全失败")

        result = await _fallback_form_filling(
            debater, "初始风格", None, [], "", ""
        )

        assert result is None, "无 prev_participant 时应返回 None"
        print("✅ 无上次状态测试通过")


async def main():
    print("开始分层 Mock 测试 _fallback_form_filling")

    try:
        await test_level1_form_mode()
        await test_level2_field_by_field()
        await test_level3_multiple_choice()
        await test_level4_preserve_previous()
        await test_no_previous_fallback()

        print("\n" + "="*60)
        print("✅ 所有测试通过")
        print("="*60)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
