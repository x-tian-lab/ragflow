# -*- coding: utf-8 -*-
"""Parser 层 (§4)。每格式一个类,输出 DocElement 流;metadata 只增不减。
docx→python-docx (D-13 spike 验证);xlsx→openpyxl 自写 (R4/R5);Unstructured 出局 (D-12)。"""
import os
import re
from .schema import DocElement, Location
from . import law_regex as L

INVIS = re.compile(r'[​‌‍﻿　]')


def _clean(s: str) -> str:
    return INVIS.sub('', s).strip()


# ---------------- 法律结构通用组装 ----------------

def law_elements(paras: list[str], doc_title: str) -> list[DocElement]:
    """任何格式的正文段落,命中法律结构后统一走这里 (§7 结构探测路由)。"""
    skip = L.strip_toc(paras)
    els: list[DocElement] = []
    hpath: list[str] = [doc_title] if doc_title else []
    cur_ch = cur_jie = None
    seq = 0
    for i, t in enumerate(paras):
        if i in skip:
            continue
        seq += 1
        t_sp = re.sub(r'\s+', ' ', t)
        base = [doc_title] if doc_title else []
        if L.RE_CH.match(t):
            cur_ch, cur_jie = t_sp, None
            els.append(DocElement('heading', t_sp, Location(heading_path=base + [t_sp], paragraph_seq=seq)))
        elif L.RE_JIE.match(t):
            cur_jie = t_sp
            els.append(DocElement('heading', t_sp, Location(
                heading_path=base + [x for x in (cur_ch, t_sp) if x], paragraph_seq=seq)))
        elif (m := L.RE_TIAO.match(t)):
            els.append(DocElement('article', t_sp, Location(
                heading_path=base + [x for x in (cur_ch, cur_jie) if x],
                article_no=m.group(1), paragraph_seq=seq)))
        else:
            els.append(DocElement('paragraph', t_sp, Location(
                heading_path=base + [x for x in (cur_ch, cur_jie) if x],
                paragraph_seq=seq, anchor_text=t_sp[:20])))
    return els


# ---------------- 各格式 Parser ----------------

class DocxParser:
    def parse(self, path: str, doc_title: str = '') -> list[DocElement]:
        from docx import Document
        d = Document(path)
        # 文档序遍历:body 级 walk,保持表格与段落相对位置 (竞赛代码教训)
        paras: list[str] = []
        tables_by_pos: list[tuple[int, object]] = []
        body = d.element.body
        ti = 0
        for child in body.iterchildren():
            tag = child.tag.rsplit('}', 1)[-1]
            if tag == 'p':
                # 通过 xml 拿文本(含 run 合并)
                txt = _clean(''.join(node.text or '' for node in child.iter()
                                     if node.tag.endswith('}t')))
                if txt:
                    paras.append(txt)
            elif tag == 'tbl':
                tables_by_pos.append((len(paras), d.tables[ti]))
                ti += 1
        if L.is_law_structured(paras):
            els = law_elements(paras, doc_title)
        else:
            els = []
            for seq, t in enumerate(paras, 1):
                els.append(DocElement('paragraph', t, Location(paragraph_seq=seq, anchor_text=t[:20])))
        # 内嵌表格:行级元素,挂在其位置附近
        for pos, tb in tables_by_pos:
            hdr = [_clean(c.text) for c in tb.rows[0].cells] if tb.rows else []
            for ri, row in enumerate(tb.rows[1:], 1):
                cells = [_clean(c.text) for c in row.cells]
                text = ' | '.join(f'{h}={v}' if h else v for h, v in zip(hdr, cells) if v)
                if text:
                    els.append(DocElement('table_row', text, Location(
                        table_index=1, row_range=f'r{ri}', column_names=hdr or None,
                        paragraph_seq=pos)))
        return els


class TxtParser:
    HEADER_KEYS = ('标题：', '栏目：', '发布日期：', '来源：', '原文链接：')

    def parse(self, path: str, doc_title: str = '') -> list[DocElement]:
        raw = open(path, encoding='utf-8', errors='replace').read()
        m = re.search(r'^正文：\s*$', raw, re.M)
        body = raw[m.end():] if m else raw
        paras = [_clean(p) for p in body.split('\n')]
        paras = [p for p in paras if p and not p.startswith(self.HEADER_KEYS)
                 and p not in ('无障碍浏览',) and '下载文字版' not in p and '下载图片版' not in p]
        if L.is_law_structured(paras):
            return law_elements(paras, doc_title)
        return [DocElement('paragraph', t, Location(paragraph_seq=i, anchor_text=t[:20]))
                for i, t in enumerate(paras, 1)]


class MdParser:
    def parse(self, path: str, doc_title: str = '') -> list[DocElement]:
        lines = open(path, encoding='utf-8').read().split('\n')
        # front matter
        fm = {}
        if lines and lines[0].strip() == '---':
            try:
                end = lines[1:].index('---') + 1
                for ln in lines[1:end]:
                    if ':' in ln:
                        k, v = ln.split(':', 1)
                        fm[k.strip()] = v.strip()
                lines = lines[end + 1:]
            except ValueError:
                pass
        els: list[DocElement] = []
        hstack: list[tuple[int, str]] = []
        seq = 0
        table_hdr: list[str] | None = None
        ti = 0
        for ln in lines:
            t = ln.rstrip()
            if not t.strip():
                continue
            seq += 1
            hm = re.match(r'^(#{1,4})\s+(.*)', t)
            if hm:
                lvl = len(hm.group(1))
                hstack = [(l, h) for l, h in hstack if l < lvl] + [(lvl, hm.group(2).strip())]
                els.append(DocElement('heading', hm.group(2).strip(),
                                      Location(heading_path=[h for _, h in hstack], paragraph_seq=seq)))
                table_hdr = None
                continue
            hp = [h for _, h in hstack]
            if t.startswith('|'):
                cells = [c.strip() for c in t.strip('|').split('|')]
                if all(re.fullmatch(r'-{3,}', c) for c in cells):
                    continue
                if table_hdr is None:
                    table_hdr = cells
                    ti += 1
                    continue
                text = ' | '.join(f'{h}={v}' for h, v in zip(table_hdr, cells) if v)
                els.append(DocElement('table_row', text, Location(
                    heading_path=hp, sheet_name=fm.get('sheet_name'),
                    table_index=ti, row_range=f'r{seq}', column_names=table_hdr,
                    column_names_confidence=fm.get('column_names_confidence', 'ok'),
                    paragraph_seq=seq)))
                continue
            table_hdr = None
            body = re.sub(r'^[-*]\s+', '', t.strip())
            m = L.RE_TIAO.match(body)
            els.append(DocElement('article' if m else 'paragraph', body, Location(
                heading_path=hp, article_no=m.group(1) if m else None,
                paragraph_seq=seq, anchor_text=body[:20])))
        return els


class XlsxParser:
    """R4/R5 实现,移植自 x2md spike v4:签名法表头检测/合并展开/数值行不进表头/列序号行丢弃。"""

    def parse(self, path: str, doc_title: str = '') -> list[DocElement]:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        els: list[DocElement] = []
        for ws in wb.worksheets:
            els.extend(self._sheet(ws))
        wb.close()
        return els

    @staticmethod
    def _cell_type(v):
        if v is None or not str(v).strip():
            return '_'
        if isinstance(v, (int, float)):
            return 'N'
        return 'N' if re.match(r'^-?[\d,，.%\s]+$', str(v).strip()) else 'T'

    def _sheet(self, ws) -> list[DocElement]:
        from collections import Counter
        for rng in list(ws.merged_cells.ranges):                     # R5 展开回填
            v = ws.cell(rng.min_row, rng.min_col).value
            ws.unmerge_cells(str(rng))
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    ws.cell(r, c).value = v
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        if not rows:
            return []
        keep = [c for c in range(len(rows[0]))
                if any(r[c] is not None and str(r[c]).strip() for r in rows)]
        rows = [[r[c] for c in keep] for r in rows]
        sigs = [''.join(self._cell_type(v) for v in r) for r in rows]
        nonempty = [s for s in sigs if set(s) != {'_'}]
        if not nonempty:
            return []
        data_sig = Counter(nonempty).most_common(1)[0][0]
        data_start = sigs.index(data_sig)
        header_rows = []
        for i in range(data_start):
            if set(sigs[i]) == {'_'}:
                continue
            vals = [v for v in rows[i] if v is not None and str(v).strip()]
            if sum(1 for v in vals if self._cell_type(v) == 'N') / len(vals) > 0.3:
                continue                                             # 合计/序号行不进表头
            if len(set(str(v).strip() for v in vals)) > 2:
                header_rows.append(i)
        headers = []
        for c in range(len(rows[0])):
            parts = []
            for r in header_rows:
                s = re.sub(r'\s+', ' ', str(rows[r][c]).strip()) if rows[r][c] is not None else ''
                if s and s not in parts:
                    parts.append(s)
            headers.append('.'.join(parts))
        conf = 'ok' if header_rows and len(header_rows) <= 3 and \
            sum(1 for h in headers if not h) < len(headers) * 0.3 else 'uncertain'   # R4 降级
        els, ti, streak = [], 1, 0
        for ri, r in enumerate(rows[data_start:], data_start + 1):
            vals = ['' if v is None else str(v).strip() for v in r]
            if not any(vals):
                streak += 1
                if streak == 2:
                    ti += 1                                          # R5 纵向分表
                continue
            streak = 0
            nums = [v for v in vals if re.fullmatch(r'\d{1,3}', v)]
            ne = [v for v in vals if v]
            if len(nums) >= 3 and len(nums) >= len(ne) - 1 and \
                    [int(v) for v in nums] == list(range(int(nums[0]), int(nums[0]) + len(nums))):
                continue                                             # 列序号行
            text = ' | '.join(f'{h}={v}' if h else v
                              for h, v in zip(headers, vals) if v)
            els.append(DocElement('table_row', text, Location(
                sheet_name=ws.title, table_index=ti, row_range=f'r{ri}',
                column_names=[h for h in headers if h] or None,
                column_names_confidence=conf)))
        return els


PARSERS = {'docx': DocxParser, 'doc': DocxParser, 'doc_converted': DocxParser,
           'txt': TxtParser, 'md': MdParser, 'xlsx': XlsxParser}


def route(file_path: str, fmt: str | None = None):
    fmt = fmt or os.path.splitext(file_path)[1].lstrip('.').lower()
    cls = PARSERS.get(fmt)
    if cls is None:
        raise ValueError(f'不支持的格式: {fmt} ({file_path})')
    return cls()
