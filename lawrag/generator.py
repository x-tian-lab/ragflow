# -*- coding: utf-8 -*-
"""Generator 层 (§4, §6 R1)。拼 context、调 LLM(OpenAI 兼容 API)、产出带引用答案。
降级规则 R1:C 级不得为唯一依据;top-k 全 C 级 => 拒答「找到疑似相关内容但无法可信溯源」。"""
import os
from .schema import Answer, ScoredChunk

SYSTEM_PROMPT = (
    '你是金融法规问答助手。只依据【检索到的法规内容】回答,禁止使用任何外部知识。\n'
    '规则:\n'
    '1. 答案末尾必须列出所用来源的编号,如 [1][3]。\n'
    '2. 检索内容不足以回答时,只能回答:「知识库中未找到足够依据,无法回答。」\n'
    '3. 不得推测、补充或综合检索内容之外的信息;数字、日期、文号必须与原文完全一致。'
)

REFUSE_NO_HIT = '知识库中未找到足够依据,无法回答。'
REFUSE_LOW_TRUST = '找到疑似相关内容,但无法可信溯源,不作答。'


class Generator:
    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.1,
                 max_tokens: int = 800, timeout: float = 30.0):
        self.model = model or os.environ.get('LAWRAG_LLM_MODEL', 'deepseek-chat')
        self.base_url = base_url or os.environ.get('LAWRAG_LLM_BASE_URL',
                                                   'https://api.deepseek.com/v1')
        self.api_key = api_key or os.environ.get('LAWRAG_LLM_API_KEY', '')
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    # ---- R1 前置裁决 ----
    @staticmethod
    def triage(hits: list[ScoredChunk], min_score: float | None = None) -> tuple[str, list[ScoredChunk]]:
        """返回 (verdict, usable)。verdict: ok|refuse_no_hit|refuse_low_trust|degraded"""
        if min_score is not None:
            hits = [h for h in hits if h.score >= min_score]
        if not hits:
            return 'refuse_no_hit', []
        non_c = [h for h in hits if h.chunk.citation_level in ('A', 'B')]
        if not non_c:
            return 'refuse_low_trust', hits           # R1: 全 C 级 => 拒答
        has_c = any(h.chunk.citation_level == 'C' for h in hits)
        return ('degraded' if has_c else 'ok'), hits

    def build_prompt(self, query: str, hits: list[ScoredChunk]) -> str:
        blocks = []
        for i, h in enumerate(hits, 1):
            tag = '' if h.chunk.citation_level != 'C' else '【来源定位不完整】'
            blocks.append(f'[{i}] {h.chunk.citation()}{tag}\n{h.chunk.text}')
        ctx = '\n\n'.join(blocks)
        return f'【检索到的法规内容】\n{ctx}\n\n【问题】\n{query}'

    def _call_llm(self, prompt: str) -> str:
        import json as _json
        import urllib.request
        req = urllib.request.Request(
            self.base_url.rstrip('/') + '/chat/completions',
            data=_json.dumps({
                'model': self.model, 'temperature': self.temperature,
                'max_tokens': self.max_tokens,
                'messages': [{'role': 'system', 'content': SYSTEM_PROMPT},
                             {'role': 'user', 'content': prompt}]}).encode(),
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {self.api_key}'})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return _json.loads(r.read())['choices'][0]['message']['content']

    def generate(self, query: str, hits: list[ScoredChunk]) -> Answer:
        verdict, usable = self.triage(hits)
        if verdict == 'refuse_no_hit':
            return Answer(REFUSE_NO_HIT, [], refused=True)
        if verdict == 'refuse_low_trust':
            return Answer(REFUSE_LOW_TRUST, [h.chunk.citation() for h in usable],
                          refused=True, degraded=True)
        if not self.api_key:
            raise RuntimeError('未配置 LAWRAG_LLM_API_KEY,无法调用 LLM。'
                               '检索与引用链路可用 cli.py search 验证。')
        text = self._call_llm(self.build_prompt(query, usable))
        # 修复(eval 2026-07-12 发现1):LLM 生成阶段自主拒答必须置 refused 并清空引用,
        # 否则拒答语下挂无关引用 => 违反「引用错=最高级事故」
        if REFUSE_NO_HIT.rstrip('。') in text.replace(' ', '')[:40]:
            return Answer(REFUSE_NO_HIT, [], refused=True)
        return Answer(text=text,
                      citations=[h.chunk.citation() for h in usable],
                      degraded=(verdict == 'degraded'),
                      chunks_used=[h.chunk.chunk_id for h in usable])
