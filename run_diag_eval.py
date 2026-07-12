# -*- coding: utf-8 -*-
"""Diagnostic full-eval run: same logic as lawrag.eval.eval_full but persists
per-question detail (answer text, citation check, key check, refusal reason)
to JSON for reporting. Not part of the shipped CLI; ad-hoc analysis script."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from lawrag.eval import load_testset, _expected_files, _contains_key
from lawrag.cli import get_retriever
from lawrag.generator import Generator

META = os.environ['LAWRAG_META']
ts = load_testset(os.path.join(META, 'testset_v1.jsonl'))
r = get_retriever('bm25')
gen = Generator()

rows = []
for q in ts:
    t0 = time.time()
    hits = r.retrieve(q['question'], k=5, include_history=(q.get('qtype') == 'version'))
    ans = gen.generate(q['question'], hits)
    sec = time.time() - t0
    hit_files = [h.chunk.file_name for h in hits]
    if q.get('qtype') == 'refuse':
        ok = ans.refused
        cite_ok = None
        key_ok = None
    else:
        exp_files = _expected_files(q)
        cite_ok = all(any(ef in c for c in ans.citations) for ef in exp_files) or \
            any(q.get('expected_source', {}).get('doc_title', '§') in c for c in ans.citations)
        key_ok = _contains_key(q, ans.text)
        ok = bool(cite_ok and key_ok and not ans.refused)
    row = {
        'qid': q['qid'], 'qtype': q.get('qtype'), 'format': q.get('format'),
        'question': q['question'], 'golden_answer': q.get('golden_answer'),
        'expected_source': q.get('expected_source'),
        'retrieved_files': hit_files,
        'answer_text': ans.text, 'citations': ans.citations,
        'refused': ans.refused, 'degraded': ans.degraded,
        'cite_ok': cite_ok, 'key_ok': key_ok, 'ok': ok, 'sec': round(sec, 2),
    }
    rows.append(row)
    print(f'{q["qid"]:4s} {"OK" if ok else "FAIL":4s} {sec:.1f}s', flush=True)

n = len(rows)
summary = {
    'n': n,
    'accuracy': round(sum(row['ok'] for row in rows) / n, 3),
    'over_5s': sum(row['sec'] > 5 for row in rows),
    'refuse_total': sum(1 for row in rows if row['qtype'] == 'refuse'),
    'refuse_correct': sum(row['ok'] for row in rows if row['qtype'] == 'refuse'),
}
by_qtype = {}
for row in rows:
    d = by_qtype.setdefault(row['qtype'], [0, 0])
    d[0] += 1
    d[1] += row['ok']
summary['by_qtype'] = {k: {'n': v[0], 'acc': round(v[1] / v[0], 3)} for k, v in sorted(by_qtype.items())}
by_format = {}
for row in rows:
    d = by_format.setdefault(row['format'], [0, 0])
    d[0] += 1
    d[1] += row['ok']
summary['by_format'] = {k: {'n': v[0], 'acc': round(v[1] / v[0], 3)} for k, v in sorted(by_format.items())}

out = {'summary': summary, 'rows': rows}
out_path = os.path.join(META, 'eval_full_detail.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
print('written to', out_path)
