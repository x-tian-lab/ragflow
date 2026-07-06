# -*- coding: utf-8 -*-
"""法律结构解析层 (D-20)。来源:law2md spike 2026-07-05,含目录剔除与条号质量门。"""
import re

CN = '一二三四五六七八九十零百千'
RE_BIAN = re.compile(rf'^第[{CN}]+编')
RE_CH   = re.compile(rf'^第[{CN}]+章')
RE_JIE  = re.compile(rf'^第[{CN}]+节')
RE_TIAO = re.compile(rf'^(第[{CN}]+条)\s*(.*)$', re.S)
RE_KUAN = re.compile(r'^（[一二三四五六七八九十]+）')

_D = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def cn2int(s: str) -> int:
    if s.startswith('十'):
        s = '一' + s
    total = num = 0
    for c in s:
        if c == '百':
            total += (num or 1) * 100; num = 0
        elif c == '十':
            total += (num or 1) * 10; num = 0
        elif c in _D:
            num = _D[c]
    return total + num


def is_law_structured(paras: list[str], min_articles: int = 3) -> bool:
    """结构探测 (§7 前置路由):条 数量达到阈值即走法律分块。"""
    return sum(1 for t in paras if RE_TIAO.match(t)) >= min_articles


def strip_toc(paras: list[str]) -> set[int]:
    """目录剔除 (D-20):首个「条」之前的章标题只保留最后一个,其余判为目录。
    返回应跳过的下标集合。spike 实测三部法剔除 33 行零误伤。"""
    first_tiao = next((i for i, t in enumerate(paras) if RE_TIAO.match(t)), None)
    if first_tiao is None:
        return set()
    pre_ch = [i for i, t in enumerate(paras[:first_tiao]) if RE_CH.match(t)]
    skip = set(pre_ch[:-1]) if len(pre_ch) > 1 else set()
    if skip:
        lo, hi = min(skip), max(skip)
        skip |= {i for i, t in enumerate(paras[:first_tiao])
                 if (RE_JIE.match(t) or RE_BIAN.match(t)) and lo <= i <= hi}
    skip |= {i for i, t in enumerate(paras[:first_tiao]) if re.sub(r'\s', '', t) == '目录'}
    return skip


def article_numbers(paras: list[str]) -> list[int]:
    return [cn2int(m.group(1)[1:-1]) for t in paras if (m := RE_TIAO.match(t))]


def sequence_gaps(nums: list[int]) -> list[tuple[int, int]]:
    """条号连续性质量门 (D-20):返回断号对,非空即报警。"""
    return [(a, b) for a, b in zip(nums, nums[1:]) if b != a + 1]
