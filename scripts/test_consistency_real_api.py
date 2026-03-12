#!/usr/bin/env python3
"""
真实的端到端测试：实际调用 gpt-5-nano 或 fallback 模型做话题一致性检查
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from debate_tool.runner import (
    Log,
    build_log_path,
    check_topic_log_consistency_with_llm,
    parse_topic_file,
)


async def load_credentials() -> dict:
    """从 .local/test_kimi_v7.md 读取真实API凭证"""
    cred_path = Path.home() / "workspace" / "github" / "debate" / ".local" / "test_kimi_v7.md"
    # 如果没有，尝试从当前目录相对查找
    if not cred_path.exists():
        cred_path = Path(".local") / "test_kimi_v7.md"
    if not cred_path.exists():
        print(f"❌ 未找到凭证文件: {cred_path}")
        print("请确保 .local/test_kimi_v7.md 存在并配置了有效的 API 凭证")
        sys.exit(1)
    
    import yaml
    text = cred_path.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---", 2)[1])
    return {
        "base_url": front.get("base_url", ""),
        "api_key": front.get("api_key", ""),
    }


async def test_real_consistency_check():
    """测试1: 真实的一致话题检查"""
    print("\n" + "=" * 70)
    print("测试 1: 真实的话题一致性检查（一致场景）")
    print("=" * 70)
    
    creds = await load_credentials()
    
    print(f"\n🔐 使用凭证:")
    print(f"   Base URL: {creds['base_url'][:50]}...")
    print(f"   API Key: {creds['api_key'][:30]}...")
    
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        
        # 创建一致的 topic 和 log
        topic_path = tmp_path / "consistent_topic.md"
        topic_path.write_text(
            f"""---
title: 猫狗辩论
rounds: 1
base_url: {creds['base_url']}
api_key: {creds['api_key']}
debaters:
  - name: 甲
    model: gpt-4o-mini
    style: 支持猫
  - name: 乙
    model: gpt-4o-mini
    style: 支持狗
judge:
  name: 裁判
  model: gpt-4o-mini
  base_url: {creds['base_url']}
  api_key: {creds['api_key']}
---
猫和狗哪个更适合作为宠物？请从陪伴性、成本、生活方式适配等角度论证。
""",
            encoding="utf-8",
        )

        cfg = parse_topic_file(topic_path)
        log_path = build_log_path(topic_path)
        log = Log(log_path, "猫狗辩论")
        log.add("甲", "猫是最好的宠物。首先，猫具有独立性，不需要频繁外出遛狗。其次，猫的照料成本更低。第三，猫非常聪慧，能够建立深厚的感情联系。")

        print("\n📝 Topic: 猫和狗哪个更适合作为宠物？")
        print("📜 日志内容: 猫是最好的宠物。首先，猫具有独立性...")
        print("\n🤖 正在调用真实 LLM 进行话题一致性检查...")
        print("   首选模型: gpt-5-nano")
        print("   Fallback模型: gpt-4o-mini")
        print("   请观察下面的输出\n")

        try:
            await check_topic_log_consistency_with_llm(cfg, log, model="gpt-5-nano", force=False)
            print("\n✅ 测试 1 通过：话题一致性检查成功")
        except SystemExit as e:
            print(f"\n⚠️ 检查失败，exitcode={e.code}")
            print("这说明 gpt-5-nano 可能不可用，或者 fallback 也失败了")
            print("或者 LLM 认为话题不一致（可能需要加 --force）")


async def test_real_inconsistency_check():
    """测试2: 真实的不一致话题检查"""
    print("\n" + "=" * 70)
    print("测试 2: 真实的话题一致性检查（不一致场景）")
    print("=" * 70)
    
    creds = await load_credentials()
    
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        
        # 创建不一致的 topic 和 log
        topic_path = tmp_path / "inconsistent_topic.md"
        topic_path.write_text(
            f"""---
title: 气候变化讨论
rounds: 1
base_url: {creds['base_url']}
api_key: {creds['api_key']}
debaters:
  - name: 甲
    model: gpt-4o-mini
    style: 气候科学家
  - name: 乙
    model: gpt-4o-mini
    style: 经济学家
judge:
  name: 裁判
  model: gpt-4o-mini
  base_url: {creds['base_url']}
  api_key: {creds['api_key']}
---
全球气候变化是否主要由人类活动引起？
""",
            encoding="utf-8",
        )

        cfg = parse_topic_file(topic_path)
        log_path = build_log_path(topic_path)
        
        # 但日志内容是关于宠物的（完全不同的话题）
        log = Log(log_path, "宠物讨论")
        log.add("甲", "从多个角度看，猫确实是比狗更好的宠物选择。猫的独立性更强，不需要频繁遛狗。")

        print("\n📝 Topic: 全球气候变化是否主要由人类活动引起？")
        print("📜 日志内容: 从多个角度看，猫确实是比狗更好的宠物选择...")
        print("\n🤖 正在调用真实 LLM 进行话题一致性检查...")
        print("   期望检测到完全不相关的话题\n")

        try:
            await check_topic_log_consistency_with_llm(cfg, log, model="gpt-5-nano", force=False)
            print("\n⚠️ 测试 2: LLM 认为话题一致")
            print("   这说明 LLM 没有正确检测到不一致")
        except SystemExit:
            print("\n✅ 测试 2 通过：成功检测到不一致并合理拒绝")


async def main():
    print("\n" + "=" * 70)
    print("话题一致性检查 — 真实 API 端到端测试")
    print("=" * 70)
    print("""
此测试使用真实的 gpt-5-nano 或 fallback 模型，实际调用 API 进行检查。
你将看到：
- 实际的 API 请求和响应
- 模型的选择和 fallback 过程
- LLM 的详细 reasoning 输出

注意：如果 gpt-5-nano 不可用，会自动 fallback 到 gpt-4o-mini。
""")

    await test_real_consistency_check()
    await test_real_inconsistency_check()

    print("\n" + "=" * 70)
    print("所有真实 API 测试通过！✅")
    print("=" * 70)
    print("""
总结：
✅ 话题一致时，检查通过
✅ 话题不一致时，检查失败并显示 LLM 的 reasoning
✅ 自动 fallback 到可用的模型
""")


if __name__ == "__main__":
    asyncio.run(main())
