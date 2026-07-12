# -*- coding: utf-8 -*-
"""eval harness (§8) — MVP 交付物的一部分,不是附属品。
两种模式:
  retrieval  不调 LLM:检索命中率基线 (文件命中@k / 定位命中@k, A 与 A+B 双口径 D-05)
  full       调 LLM:准确率 + 引用命中 + 拒答正确率 + 延迟 (需要 API key)
2026-07-12 修订(eval_full_report 发现2/3):cite_ok 用结构化 file_name 比对;
关键串判定加全半角归一化、插入语抗性(碎片投票)、数值相对误差容差。
"""
import json
import re
import time


def load_testset(path: str) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]


def _expected_files(q: dict) -> list[str]:
    src = q.get('expected_source')
    if not src:
        return []
    fp = src.get('file_path', '')
    return [p.strip().split('/')[-1] for p in fp.split('+')] if fp else []


def _expected_article(q: dict) -> str | None:
    src = q.get('expected_source') or {}
    m = re.search(r'第[一二三四五六七八九十零百千]+条', str(src.get('locator', '')))
    return m.group(0) if m else None


def eval_retrieval(retriever, testset: list[dict], k: int = 5, log=print) -> dict:
    n = file_hit = loc_hit = 0
    per_format = {}
    misses = []
    for q in testset:
        if q.get('qtype') == 'refuse':
            continue                       # 拒答题需 LLM 环节,检索基线不计
        n += 1
        exp_files = _expected_files(q)
        exp_art = _expected_article(q)
        t0 = time.time()
        hits = retriever.retrieve(q['question'], k=k,
                                  include_history=(q.get('qtype') == 'version'))
        ms = (time.time() - t0) * 1000
        hit_files = [h.chunk.file_name for h in hits]
        f_ok = all(any(ef == hf for hf in hit_files) for ef in exp_files) if exp_files else False
        l_ok = f_ok
        if f_ok and exp_art:
            l_ok = any(h.chunk.location.article_no == exp_art for h in hits
                       if h.chunk.file_name in exp_files)
        file_hit += f_ok
        loc_hit += l_ok
        st = per_format.setdefault(q['format'], [0, 0, 0])
        st[0] += 1; st[1] += f_ok; st[2] += l_ok
        if not f_ok:
            misses.append((q['qid'], exp_files, hit_files[:3], f'{ms:.0f}ms'))
    res = {'n': n, 'file_hit@k': round(file_hit / n, 3), 'loc_hit@k': round(loc_hit / n, 3),
           'per_format': {f: {'n': a, 'file': round(b / a, 2), 'loc': round(c / a, 2)}
                          for f, (a, b, c) in sorted(per_format.items())},
           'k': k}
    log(json.dumps(res, ensure_ascii=False, indent=1))
    if misses:
        log('--- 未命中 ---')
        for m in misses:
            log(f'  {m[0]} 期望{m[1]} 实得{m[2]} {m[3]}')
    return res


def eval_full(retriever, generator, testset: list[dict], k: int = 5,
              judge=None, log=print) -> dict:
    """完整评测:引用错 = 判负 (D-05)。judge 缺省用关键串粗判,正式验收应人工复核。"""
    rows = []
    for q in testset:
        t0 = time.time()
        hits = retriever.retrieve(q['question'], k=k,
                                  include_history=(q.get('qtype') == 'version'))
        ans = generator.generate(q['question'], hits)
        sec = time.time() - t0
        if q.get('qtype') == 'refuse':
            ok = ans.refused
            cite_ok = None
        else:
            exp_files = _expected_files(q)
            # 修复(2026-07-12 发现2):用检索命中的结构化 file_name/doc_title 比对,
            # 不依赖渲染后的引用文本(doc_title 截断时子串匹配必然误判)
            hit_files = {h.chunk.file_name for h in hits}
            hit_titles = {h.chunk.doc_title for h in hits if h.chunk.doc_title}
            exp_title = (q.get('expected_source') or {}).get('doc_title', '')
            cite_ok = all(ef in hit_files for ef in exp_files) or \
                any(exp_title and (exp_title in t or t in exp_title) for t in hit_titles)
            key_ok = judge(q, ans.text) if judge else _contains_key(q, ans.text)
            ok = bool(cite_ok and key_ok and not ans.refused)   # 引用错=判负
        rows.append({'qid': q['qid'], 'ok': ok, 'cite_ok': cite_ok,
                     'refused': ans.refused, 'sec': round(sec, 2)})
        log(f'{q["qid"]} {"✓" if ok else "✗"} {sec:.1f}s')
    n = len(rows)
    res = {'n': n, 'accuracy': round(sum(r['ok'] for r in rows) / n, 3),
           'over_5s': sum(r['sec'] > 5 for r in rows),
           'refuse_correct': sum(r['ok'] for r in rows if r['refused'] is True)}
    log(json.dumps(res, ensure_ascii=False))
    return {'summary': res, 'rows': rows}

# ---------------- 关键串粗判 (2026-07-12 修订) ----------------

_FW = str.maketrans('０１２３４５６７８９％（）：，；．', '0123456789%():,;.')


def _norm(s: str) -> str:
    return re.sub(r'\s+', '', s.translate(_FW))


def _num_match(key: str, text: str) -> bool:
    if key in text:
        return True
    m = re.match(r'^\d+(?:\.\d+)?', key)
    if not m or '.' not in m.group(0):
        return False
    kf = float(m.group(0))
    for t in re.findall(r'\d+\.\d+', text):
        if abs(float(t) - kf) / max(abs(kf), 1e-12) < 1e-3:
            return True
    return False


def _contains_key(q: dict, text: str) -> bool:
    golden = _norm(q.get('golden_answer', ''))
    text = _norm(text)
    keys = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日|[〔\[]\d{4}[〕\]]\S{0,6}号'
                      r'|\d+(?:\.\d+)?(?:%|年|日|个月|万元|元|倍)?'
                      r'|[一二三四五六七八九十百千]+[万元年日个月]', golden)
    keys = [k for k in keys if len(k) >= 2][:4]
    if not keys:
        shingles = [golden[:8], golden[len(golden) // 2:len(golden) // 2 + 8], golden[-8:]]
        return sum(1 for s in shingles if s and s in text) >= 2
    return all(_num_match(k, text) if re.match(r'^\d', k) else k in text for k in keys)
