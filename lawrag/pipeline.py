# -*- coding: utf-8 -*-
"""索引构建编排:registry.jsonl(可信源) -> Parser -> Chunker -> Retriever.build。
范围 = duplicate_of IS NULL 的全部文档,含历史版本(检索期默认过滤, D-21/D-22)。"""
import json
import os
from .chunker import Chunker
from .parsers import route

FMT_MAP = {'docx': 'docx', 'doc_converted': 'doc', 'txt': 'txt', 'xlsx': 'xlsx', 'md': 'md'}


def load_registry(registry_jsonl: str) -> list[dict]:
    recs = {}
    for line in open(registry_jsonl, encoding='utf-8'):
        r = json.loads(line)
        recs[r['doc_id']] = r
    return list(recs.values())


def apply_manual_layers(recs: list[dict], meta_dir: str | None = None) -> list[dict]:
    """人工覆盖层(D-26 日期 / eval-2026-07-12 标题):meta_dir 下的 manual_*.json,最高优先级。"""
    if not meta_dir:
        return recs

    def _load(name):
        p = os.path.join(meta_dir, name)
        return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}

    md, mt = _load('manual_dates.json'), _load('manual_titles.json')
    for r in recs:
        fp = r['file_path'].replace('\\', '/')
        if fp in md:
            r['effective_date'] = md[fp]
        if fp in mt:
            r['doc_title'] = mt[fp]
            r['title_source'] = 'manual'
    return recs


def mark_versions(recs: list[dict]):
    """与 finalize_registry 相同的指纹去重 + 版本归组(内联,保证索引与登记表一致)。
    若登记表已含 duplicate_of/is_latest 字段,直接信任。"""
    for r in recs:
        r.setdefault('duplicate_of', None)
        r.setdefault('is_latest', 1)
    return recs


def iter_chunks(recs: list[dict], corpus_root: str, extra_md_dirs: list[str] = (),
                limit_chars: int = 400, log=print):
    """产出全部 chunk;extra_md_dirs 用于合成 md 语料(law_md/xlsx_md)。"""
    ck = Chunker(limit=limit_chars)
    n_doc = n_fail = 0
    for r in recs:
        if r.get('duplicate_of') or str(r.get('status', '')).startswith('ERROR'):
            continue
        fmt = FMT_MAP.get(r['format'])
        if not fmt:
            continue
        path = os.path.join(corpus_root, r['file_path'])
        try:
            els = route(path, r['format'] if r['format'] != 'doc_converted' else 'docx') \
                .parse(path, doc_title=r.get('doc_title') or '')
            yield from ck.chunk(
                els, doc_id=r['doc_id'], doc_version=r.get('doc_version') or '????????',
                file_name=os.path.basename(r['file_path']),
                doc_title=r.get('doc_title') or '', fmt=fmt,
                effective_date=r.get('effective_date'), source_url=r.get('source_url'),
                is_latest=r.get('is_latest', 1))
            n_doc += 1
        except Exception as e:
            n_fail += 1
            log(f'PARSE FAIL {r["file_path"]}: {e}')
    import hashlib
    for d in extra_md_dirs:
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.md'):
                continue
            path = os.path.join(d, fn)
            doc_id = hashlib.sha1(('synthetic/' + fn).encode()).hexdigest()[:16]
            title = os.path.splitext(fn)[0].split('_')[0]
            try:
                els = route(path, 'md').parse(path, doc_title=title)
                yield from ck.chunk(els, doc_id=doc_id, doc_version='synthmd0',
                                    file_name=fn, doc_title=title, fmt='md')
                n_doc += 1
            except Exception as e:
                n_fail += 1
                log(f'PARSE FAIL {fn}: {e}')
    log(f'解析完成: 成功 {n_doc} 失败 {n_fail}')
