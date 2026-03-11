---
topic: "2025-2026 年当前最强 AI 模型之争：GPT-5/Grok、Claude 4、Gemini 3/DeepSeek，谁才是综合最强？"
rounds: 1
cross_exam: 0
max_reply_tokens: 2000
timeout: 900

debaters:
  - name: "GPT-Grok-Advocate"
    base_url: "http://localhost:8081/v1/chat/completions"
    api_key: "dummy"
    model: "yunwu/kimi-k2.5"
    style: "你是 GPT-5 系列和 Grok 3 的坚定支持者。你的任务是为 GPT-5 或 Grok 3 中更强的那个进行辩护，论证它是目前综合最强的 AI 模型。你可以联网搜索最新基准测试、开发者评价和实测报告来支撑论点。"

  - name: "Claude-Advocate"
    base_url: "http://localhost:8082/v1/chat/completions"
    api_key: "dummy"
    model: "yunwu/kimi-k2.5"
    style: "你是 Claude 4 系列（Claude Opus 4、Claude Sonnet 4）的坚定支持者。你的任务是论证 Claude 4 是目前综合最强的 AI 模型，尤其在推理、代码、安全性和指令遵循方面。你可以联网搜索最新数据支撑论点。"

  - name: "Gemini-DeepSeek-Advocate"
    base_url: "http://localhost:8083/v1/chat/completions"
    api_key: "dummy"
    model: "yunwu/kimi-k2.5"
    style: "你是 Gemini 3 系列和 DeepSeek V3/R2 的坚定支持者。你的任务是为 Gemini 3 或 DeepSeek 中更强的那个进行辩护，论证它是目前综合最强的 AI 模型。你可以联网搜索最新数据支撑论点。"

judge:
  base_url: "http://localhost:8084/v1/chat/completions"
  api_key: "dummy"
  model: "yunwu/qwen3.5-397b-a17b"
  max_tokens: 2000

judge_instructions: "根据三位辩手的论据，评估各模型系列的实际综合能力，给出有依据的裁定：哪个模型系列在当前（2025-2026）综合表现最强，理由是什么。"

round1_task: "你**必须先使用 websearch 工具搜索**最新信息（搜索关键词如：GPT-5 benchmark 2025、Grok 3 vs Claude、Gemini 3 MMLU、DeepSeek v3 SWE-bench 等），收集至少 2-3 条真实数据后，再撰写论点。不允许仅凭训练数据作答。"
---

## 辩题说明

2025-2026 年 AI 模型竞争白热化，各大厂商旗舰模型你追我赶：

- **GPT-5 系列 / Grok 3**：OpenAI 和 xAI 的旗舰，主打通用能力和工具使用
- **Claude 4 系列**：Anthropic 的旗舰，主打推理深度、代码质量和安全性
- **Gemini 3 系列 / DeepSeek**：Google DeepMind 和 DeepSeek 的旗舰，主打多模态、长上下文和性价比

请三位辩手各自论证自己支持的模型为何是综合最强，可引用基准测试（MMLU、HumanEval、SWE-bench、GPQA 等）、开发者实测反馈、以及具体任务场景表现。
