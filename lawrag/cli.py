# -*- coding: utf-8 -*-
"""lawrag CLI — MVP 终端形态 (D-01:开发者自我验证工具)。

用法:
  python -m lawrag.cli index   --retriever bm25|dense     # 建索引
  python -m lawrag.cli search  "问题" [-k 5] [--history]  # 只检索,验证引用链路
  python -m lawrag.cli ask     "问题"                      # 检索+LLM (需 LAWRAG_LLM_API_KEY)
  python -m lawrag.cli eval    --mode retrieval|full       # 跑 testset (§8)

环境变量: LAWRAG_ROOT(语料根) LAWRAG_META(metadata_output) LAWRAG_LLM_API_KEY/_MODEL/_BASE_URL
"""
import argparse
import os
import sys

ROOT = os.environ.get('LAWRAG_ROOT', '/sessions/peaceful-vigilant-hopper/mnt/rag sys')
META = os.environ.get('LAWRAG_META', '/sessions/peaceful-vigilant-hopper/mnt/metadata_output')
INDEX_DIR = os.environ.get('LAWRAG_INDEX', os.path.join(META, 'index'))


def get_retriever(kind: str, for_build: bool = False):
    if kind == 'dense':
        from .retriever import DenseRetriever
        return DenseRetriever(os.path.join(INDEX_DIR, 'dense'))
    from .retriever import BM25Retriever
    r = BM25Retriever(os.path.join(INDEX_DIR, 'bm25'))
    return r if for_build else r.load()


def cmd_index(args):
    from .pipeline import apply_manual_layers, iter_chunks, load_registry
    recs = load_registry(os.path.join(META, 'registry.jsonl'))
    recs = apply_manual_layers(recs, meta_dir=META)
    extra = [os.path.join(META, d) for d in ('law_md', 'xlsx_md')]
    extra = [d for d in extra if os.path.isdir(d)]
    chunks = list(iter_chunks(recs, ROOT, extra_md_dirs=extra))
    lv = {'A': 0, 'B': 0, 'C': 0}
    for c in chunks:
        lv[c.citation_level] += 1
    total = len(chunks)
    print(f'chunks: {total} | 引用级别 A {lv["A"]}({lv["A"]/total:.0%}) '
          f'B {lv["B"]}({lv["B"]/total:.0%}) C {lv["C"]}({lv["C"]/total:.0%})')
    r = get_retriever(args.retriever, for_build=True)
    r.build(chunks)
    if hasattr(r, 'save'):
        r.save()
    print(f'索引已写入 {INDEX_DIR}/{args.retriever}')


def cmd_search(args):
    r = get_retriever(args.retriever)
    hits = r.retrieve(args.query, k=args.k, include_history=args.history)
    for i, h in enumerate(hits, 1):
        print(f'[{i}] ({h.score:.2f}|{h.chunk.citation_level}) {h.chunk.citation()}')
        print('    ' + h.chunk.text[:120].replace('\n', ' '))


def cmd_ask(args):
    from .generator import Generator
    r = get_retriever(args.retriever)
    hits = r.retrieve(args.query, k=args.k, include_history=args.history)
    ans = Generator().generate(args.query, hits)
    print(ans.text)
    print('\n来源:')
    for c in ans.citations:
        print(' -', c)


def cmd_eval(args):
    from .eval import eval_full, eval_retrieval, load_testset
    ts = load_testset(os.path.join(META, args.testset))
    r = get_retriever(args.retriever)
    if args.mode == 'retrieval':
        eval_retrieval(r, ts, k=args.k)
    else:
        from .generator import Generator
        eval_full(r, Generator(), ts, k=args.k)


def main():
    p = argparse.ArgumentParser(prog='lawrag')
    sub = p.add_subparsers(dest='cmd', required=True)
    pi = sub.add_parser('index')
    pi.add_argument('--retriever', default='bm25', choices=['bm25', 'dense'])
    pi.add_argument('--manual-dates', default=None)
    ps = sub.add_parser('search')
    ps.add_argument('query')
    ps.add_argument('-k', type=int, default=5)
    ps.add_argument('--retriever', default='bm25', choices=['bm25', 'dense'])
    ps.add_argument('--history', action='store_true')
    pa = sub.add_parser('ask')
    pa.add_argument('query')
    pa.add_argument('-k', type=int, default=5)
    pa.add_argument('--retriever', default='bm25', choices=['bm25', 'dense'])
    pa.add_argument('--history', action='store_true')
    pe = sub.add_parser('eval')
    pe.add_argument('--mode', default='retrieval', choices=['retrieval', 'full'])
    pe.add_argument('--testset', default='testset_v1.jsonl')
    pe.add_argument('-k', type=int, default=5)
    pe.add_argument('--retriever', default='bm25', choices=['bm25', 'dense'])
    args = p.parse_args()
    {'index': cmd_index, 'search': cmd_search, 'ask': cmd_ask, 'eval': cmd_eval}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
