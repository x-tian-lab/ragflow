# -*- coding: utf-8 -*-
"""LLM-judge 判分器 (spec 验收后 backlog #1, 2026-07-13)。
定位:替换 eval 的 key_ok 字符串粗判;cite_ok 保持结构化比对不变(确定性判定不交给 LLM)。

设计规则(不可妥协):
1. judge 只看 问题/标准答案/模型答案 三样,不看引用、检索结果、系统内部状态。
2. 判定范围 = 问题所问(D07 教训:标准答案可能包含超出问题范围的补充信息,模型未提及不扣分)。
3. API 失败 => 回退 _contains_key 并在结果里标 source='fallback',绝不静默放行。
4. 上岗前必须过校准:对 v3 的 60 题人工复核结论跑 calibrate(),一致率 >=95% 才可用于回归。
   (同模型评同模型存在宽松偏置,校准门槛是唯一防线。)
5. temperature=0,严格 JSON 输出;correct 记 1 分,partial/incorrect 记 0 分(D-05 严格口径),
   partial 单独统计(双口径,与 A/A+B 同风格)。
"""
import hashlib
import json
import os
import re

JUDGE_PROMPT = '''你是严格的评分员。根据【标准答案】判断【模型答案】是否正确回答了【问题】。

评分规则:
1. 只判断问题所问的内容。标准答案可能包含超出问题范围的补充信息,模型未提及这些不扣分。
2. 问题所问的事实、数字、日期、文号必须与标准答案一致才算正确;数值精度不同但有效数字前几位一致视为一致(如 1.1404 与 1.140392605969845)。
3. 同义改写、语序调整、插入合理的限定语或机构全称,不影响判定。
4. 模型拒答、声称"未找到依据/无法回答",判 incorrect。
5. 模型答案与标准答案存在事实冲突(数字、日期、条号、名称错误),判 incorrect。
6. 问题问了多个要点,模型只答对其中一部分,判 partial。
7. 引用编号如 [1][2] 是格式要求,不参与内容判定。

只输出一行 JSON,不要输出其他任何内容:
{"verdict": "correct" 或 "partial" 或 "incorrect", "reason": "不超过30字的理由"}

【问题】
%s

【标准答案】
%s

【模型答案】
%s'''


class LLMJudge:
    """可调用对象,签名兼容 eval_full 的 judge 参数: judge(q, answer_text) -> bool。"""

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, cache_path: str | None = None,
                 timeout: float = 30.0, log=print):
        self.model = model or os.environ.get('LAWRAG_JUDGE_MODEL',
                                             os.environ.get('LAWRAG_LLM_MODEL', 'deepseek-chat'))
        self.base_url = base_url or os.environ.get('LAWRAG_LLM_BASE_URL',
                                                   'https://api.deepseek.com/v1')
        self.api_key = api_key or os.environ.get('LAWRAG_LLM_API_KEY', '')
        self.timeout = timeout
        self.log = log
        self.cache_path = cache_path
        self._cache = {}
        if cache_path and os.path.exists(cache_path):
            try:
                self._cache = json.load(open(cache_path, encoding='utf-8'))
            except Exception:
                self._cache = {}
        self.records: list[dict] = []      # 每次判定的明细,评测后可导出

    # ---- eval_full 兼容入口:严格口径,correct 才算过 ----
    def __call__(self, q: dict, answer_text: str) -> bool:
        r = self.judge(q, answer_text)
        return r['verdict'] == 'correct'

    def judge(self, q: dict, answer_text: str) -> dict:
        key = hashlib.sha1((q.get('qid', '') + '|' + q.get('golden_answer', '')
                            + '|' + answer_text).encode()).hexdigest()[:20]
        if key in self._cache:
            r = dict(self._cache[key]); r['cached'] = True
            self.records.append({'qid': q.get('qid'), **r})
            return r
        r = self._judge_llm(q, answer_text)
        if r is None:                       # 规则3:回退,显式标记
            from .eval import _contains_key
            ok = bool(_contains_key(q, answer_text))
            r = {'verdict': 'correct' if ok else 'incorrect',
                 'reason': 'LLM-judge 不可用,回退字符串粗判', 'source': 'fallback'}
        else:
            r['source'] = 'llm'
            self._cache[key] = r
            self._save_cache()
        self.records.append({'qid': q.get('qid'), **r})
        return r

    def _judge_llm(self, q: dict, answer_text: str, retries: int = 2) -> dict | None:
        if not self.api_key:
            return None
        prompt = JUDGE_PROMPT % (q.get('question', ''), q.get('golden_answer', ''), answer_text)
        for attempt in range(retries):
            try:
                raw = self._call(prompt)
                v = self._parse(raw)
                if v:
                    return v
            except Exception as e:
                self.log(f'judge 调用失败({attempt + 1}/{retries}): {str(e)[:80]}')
        return None

    def _call(self, prompt: str) -> str:
        import urllib.request
        req = urllib.request.Request(
            self.base_url.rstrip('/') + '/chat/completions',
            data=json.dumps({'model': self.model, 'temperature': 0, 'max_tokens': 120,
                             'messages': [{'role': 'user', 'content': prompt}]}).encode(),
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {self.api_key}'})
        import urllib.error
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())['choices'][0]['message']['content']

    @staticmethod
    def _parse(raw: str) -> dict | None:
        """容错解析:裸 JSON / 代码围栏 / 前后杂讯,全半角引号归一。"""
        raw = raw.replace('“', '"').replace('”', '"')
        m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', raw, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            vm = re.search(r'"verdict"\s*:\s*"(correct|partial|incorrect)"', m.group(0))
            if not vm:
                return None
            d = {'verdict': vm.group(1), 'reason': ''}
        if d.get('verdict') not in ('correct', 'partial', 'incorrect'):
            return None
        return {'verdict': d['verdict'], 'reason': str(d.get('reason', ''))[:60]}

    def _save_cache(self):
        if self.cache_path:
            try:
                json.dump(self._cache, open(self.cache_path, 'w', encoding='utf-8'),
                          ensure_ascii=False)
            except Exception:
                pass

    def stats(self) -> dict:
        n = len(self.records)
        c = sum(1 for r in self.records if r['verdict'] == 'correct')
        p = sum(1 for r in self.records if r['verdict'] == 'partial')
        fb = sum(1 for r in self.records if r.get('source') == 'fallback')
        return {'n': n, 'correct': c, 'partial': p, 'incorrect': n - c - p,
                'strict_rate': round(c / n, 3) if n else None,
                'lenient_rate': round((c + p) / n, 3) if n else None,
                'fallback_used': fb}


# ---------------- 校准:judge 对人工复核结论的一致率 ----------------

def calibrate(judge: 'LLMJudge', detail_path: str, labels_path: str,
              threshold: float = 0.95, log=print) -> dict:
    """规则4:用 v3 逐题明细(含模型答案)+人工复核标签校准 judge。
    一致率 >= threshold 才允许 judge 进回归流程;失配清单全部打印供人工仲裁。"""
    detail = json.load(open(detail_path, encoding='utf-8'))
    rows = detail.get('rows') or detail.get('detail') or []
    labels = json.load(open(labels_path, encoding='utf-8'))
    agree = total = 0
    mismatches = []
    for r in rows:
        qid = r['qid']
        if qid not in labels or r.get('qtype') == 'refuse':
            continue
        total += 1
        human = bool(labels[qid])
        verdict = judge.judge(
            {'qid': qid, 'question': r['question'], 'golden_answer': r['golden_answer']},
            r['answer_text'])
        got = verdict['verdict'] == 'correct'
        if got == human:
            agree += 1
        else:
            mismatches.append((qid, 'human=' + str(human), 'judge=' + verdict['verdict'],
                               verdict.get('reason', '')))
    rate = round(agree / total, 3) if total else 0.0
    passed = rate >= threshold
    log(f'校准: {agree}/{total} 一致率 {rate:.1%} | 门槛 {threshold:.0%} | '
        f'{"通过,judge 可用于回归" if passed else "未通过,禁止用于回归,先仲裁失配项"}')
    for m in mismatches:
        log('  失配: ' + ' | '.join(m))
    return {'agreement': rate, 'passed': passed, 'n': total, 'mismatches': mismatches}
