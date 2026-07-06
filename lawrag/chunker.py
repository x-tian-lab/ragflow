# -*- coding: utf-8 -*-
"""Chunker 层 (§7)。法律结构=按条,一条一 chunk,超长按款切;metadata 只增不减。
chunk 上限按 embedding 模型反推 (D-06: bge-large-zh-v1.5 => ~400 汉字)。"""
import hashlib
import re
from .schema import Chunk, DocElement, Location

CN_SEPS = ['。', '！', '？', '；', '\n']


def _split_recursive(text: str, limit: int) -> list[str]:
    """迭代式多级分隔切分(修复:原始语料-73.txt 触发的递归深度爆炸)。"""
    pending = [text]
    for sep in CN_SEPS:
        nxt = []
        for t in pending:
            if len(t) <= limit or sep not in t:
                nxt.append(t)
                continue
            cur = ''
            for seg in t.split(sep):
                seg = seg + sep if seg else seg
                if len(cur) + len(seg) > limit and cur:
                    nxt.append(cur)
                    cur = seg
                else:
                    cur += seg
            if cur:
                nxt.append(cur)
        pending = nxt
        if all(len(p) <= limit for p in pending):
            return pending
    out = []
    for p in pending:
        if len(p) <= limit:
            out.append(p)
        else:
            out.extend(p[i:i + limit] for i in range(0, len(p), limit))
    return out


def _split_article(text: str, limit: int) -> list[str]:
    """超长条按款(（一）（二）…)切,再兜底递归。"""
    if len(text) <= limit:
        return [text]
    pieces = re.split(r'(?=（[一二三四五六七八九十]+）)', text)
    if len(pieces) > 1:
        merged, cur = [], ''
        for p in pieces:
            if len(cur) + len(p) > limit and cur:
                merged.append(cur)
                cur = p
            else:
                cur += p
        if cur:
            merged.append(cur)
        out = []
        for m in merged:
            out.extend(_split_recursive(m, limit) if len(m) > limit else [m])
        return out
    return _split_recursive(text, limit)


class Chunker:
    def __init__(self, limit: int = 400, overlap: int = 50):
        self.limit = limit
        self.overlap = overlap

    def chunk(self, elements: list[DocElement], *, doc_id: str, doc_version: str,
              file_name: str, doc_title: str, fmt: str,
              effective_date=None, source_url=None, is_latest=1) -> list[Chunk]:
        chunks: list[Chunk] = []

        def emit(text: str, loc: Location, suffix: str = ''):
            cid = hashlib.sha1(f'{doc_id}|{loc.article_no}|{loc.paragraph_seq}|'
                               f'{loc.sheet_name}|{loc.row_range}|{suffix}|{text[:32]}'
                               .encode()).hexdigest()[:16]
            c = Chunk(chunk_id=cid, doc_id=doc_id, doc_version=doc_version,
                      file_name=file_name, doc_title=doc_title, format=fmt,
                      text=text, location=loc, effective_date=effective_date,
                      source_url=source_url, is_latest=is_latest)
            c.compute_citation_level()
            chunks.append(c)

        buf: list[DocElement] = []

        def flush():
            """相邻普通段落合并到 limit,保首段定位。"""
            nonlocal buf
            if not buf:
                return
            cur_text, cur_loc = '', None
            for el in buf:
                if cur_loc is None:
                    cur_loc = el.location
                if len(cur_text) + len(el.text) > self.limit and cur_text:
                    emit(cur_text, cur_loc)
                    cur_text, cur_loc = el.text, el.location
                else:
                    cur_text = (cur_text + '\n' + el.text) if cur_text else el.text
            if cur_text:
                emit(cur_text, cur_loc)
            buf = []

        for el in elements:
            if el.kind == 'article':
                flush()
                for j, piece in enumerate(_split_article(el.text, self.limit)):
                    emit(piece, el.location, suffix=str(j))
            elif el.kind == 'table_row':
                flush()
                emit(el.text[:self.limit * 2], el.location)      # 行文本天然短,超长截断可见
            elif el.kind == 'heading':
                flush()                                          # 标题不单独成 chunk,只影响路径
            else:
                buf.append(el)
        flush()
        return chunks
