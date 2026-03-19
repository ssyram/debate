"""CoT 注入与调用模块"""

from debate_tool.debug_log import dlog
from debate_tool.llm_client import call_llm, _split_cot_or_regenerate_reply


def inject_cot(sys_prompt, cot_length, max_reply):
    """给系统提示追加 CoT 指令，返回 (new_sys, max_tokens)"""
    if cot_length is None:
        return sys_prompt, max_reply
    note = "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"
    if cot_length > 0:
        note += f" 思考内容不超过 {cot_length} token。"
    max_tok = (cot_length + max_reply) if cot_length > 0 else (max_reply + 2000)
    return sys_prompt + "\n\n" + note, max_tok


async def call_with_cot(model, sys_prompt, ctx, cot_len, max_reply, timeout, url, key):
    dlog(f"[call_with_cot] model={model} cot={cot_len}")
    sys_final, max_tok = inject_cot(sys_prompt, cot_len, max_reply)
    raw = await call_llm(model, sys_final, ctx, max_reply_tokens=max_tok, timeout=timeout, base_url=url, api_key=key)
    if cot_len is None:
        return "", raw
    return await _split_cot_or_regenerate_reply(raw, model=model, base_sys_prompt=sys_prompt, user_ctx=ctx, max_reply_tokens=max_reply, timeout=timeout, base_url=url, api_key=key)
