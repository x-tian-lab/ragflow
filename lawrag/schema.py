# -*- coding: utf-8 -*-
"""lawrag 核心数据结构 (spec_dev §5)。阶段间只传这些结构,不传框架对象 (D-11)。"""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Location:
    heading_path: list[str] = field(default_factory=list)
    article_no: Optional[str] = None        # 法律结构文档必填 (D-20)
    paragraph_seq: Optional[int] = None
    anchor_text: Optional[str] = None       # txt 首句锚点
    sheet_name: Optional[str] = None
    table_index: Optional[int] = None
    row_range: Optional[str] = None
    column_names: Optional[list[str]] = None
    column_names_confidence: str = "ok"     # ok | uncertain (R4)


@dataclass
class DocElement:
    """Parser 输出单元。kind: title|heading|article|paragraph|table_row|front_matter"""
    kind: str
    text: str
    location: Location


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_version: str
    file_name: str
    doc_title: str
    format: str                              # docx|doc|txt|md|xlsx
    text: str
    location: Location
    citation_level: str = "C"                # A|B|C (§6, 自动判定)
    effective_date: Optional[str] = None
    source_url: Optional[str] = None
    is_latest: int = 1

    def compute_citation_level(self) -> str:
        """§6: 按格式所需字段是否齐全自动判级,不人工标。"""
        loc = self.location
        if self.format == "xlsx":
            ok = all([self.file_name, loc.sheet_name, loc.table_index is not None,
                      loc.row_range, loc.column_names])
            if ok:
                self.citation_level = "B" if loc.column_names_confidence == "uncertain" else "A"
            elif loc.sheet_name:
                self.citation_level = "B"
            else:
                self.citation_level = "C"
        elif loc.article_no:                              # 法律结构 (D-20)
            self.citation_level = "A" if self.doc_title else "B"
        elif loc.heading_path and loc.paragraph_seq is not None:
            self.citation_level = "A" if self.doc_title else "B"
        elif loc.paragraph_seq is not None and (loc.anchor_text or self.doc_title):
            self.citation_level = "A" if (self.doc_title and loc.anchor_text) else "B"
        elif self.doc_title or self.file_name:
            self.citation_level = "C"
        else:
            self.citation_level = "C"
        return self.citation_level

    def citation(self) -> str:
        """人类可读引用串,带 doc_version (D-10) 与历史版本标注 (D-21)。"""
        loc = self.location
        parts = [f"《{self.doc_title}》" if self.doc_title else self.file_name]
        if loc.article_no:
            if loc.heading_path[1:]:
                parts.append(" > ".join(loc.heading_path[1:]))
            parts.append(loc.article_no)
        elif self.format == "xlsx" and loc.sheet_name:
            parts.append(f"sheet:{loc.sheet_name} 表{loc.table_index} 行{loc.row_range}")
        elif loc.heading_path:
            parts.append(" > ".join(loc.heading_path))
            if loc.paragraph_seq is not None:
                parts.append(f"段{loc.paragraph_seq}")
        elif loc.paragraph_seq is not None:
            parts.append(f"段{loc.paragraph_seq}")
            if loc.anchor_text:
                parts.append(f"“{loc.anchor_text}…”")
        s = " · ".join(parts) + f" [v{self.doc_version}]"
        if not self.is_latest:
            s += "（历史版本）"
        if self.citation_level == "B":
            s += "（引用定位不完整）"
        if self.location.column_names_confidence == "uncertain":
            s += "（列名可能不准确,请核对原表）"
        return s

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    retriever: str = "dense"                  # dense|bm25|hybrid


@dataclass
class Answer:
    text: str
    citations: list[str]
    refused: bool = False
    degraded: bool = False                    # R1: 仅低可信来源
    chunks_used: list[str] = field(default_factory=list)   # chunk_ids
