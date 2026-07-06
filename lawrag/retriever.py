# -*- coding: utf-8 -*-
"""Retriever 层 (§4, D-17)。接口一个,实现可插:BM25(纯Python,零重依赖) / Dense(bge+Chroma)。
默认检索范围 = 非重复 + 最新版;历史版本可显式放开 (D-21)。"""
import json
import math
import os
import pickle
import re
from collections import Counter, defaultdict
from .schema import Chunk, Location, ScoredChunk


def _tokenize_zh(text: str) -> list[str]:
    """轻量中文分词:优先 jieba,缺则2-gram+术语保留。检索器内部实现细节,可换。"""
    try:
        import jieba
        return [t for t in jieba.lcut(text) if t.strip()]
    except ImportError:
        text = re.sub(r'\s+', '', text)
        toks = re.findall(r'[A-Za-z0-9〔〕\[\]第条章节%．.-]+', text)
        han = re.sub(r'[^一-鿿]', '', text)
        toks += [han[i:i + 2] for i in range(len(han) - 1)]
        return toks


def _chunk_to_record(c: Chunk) -> dict:
    d = c.to_dict()
    return d


def _record_to_chunk(d: dict) -> Chunk:
    loc = Location(**d.pop('location'))
    return Chunk(location=loc, **d)


class BM25Retriever:
    """spec D-17 混合检索插槽的 BM25 分支;沙盒/无GPU环境下的基线检索器。"""

    def __init__(self, index_dir: str, k1: float = 1.6, b: float = 0.75):
        self.index_dir = index_dir
        self.k1, self.b = k1, b
        self.chunks: list[dict] = []
        self.df: Counter = Counter()
        self.tf: list[Counter] = []
        self.dl: list[int] = []
        self.avgdl = 1.0

    # ---- Indexer 职责 (build) ----
    def build(self, chunks: list[Chunk]):
        self.chunks = [_chunk_to_record(c) for c in chunks]
        self.tf, self.dl = [], []
        self.df = Counter()
        for c in chunks:
            toks = _tokenize_zh(c.doc_title + ' ' + c.text)
            cnt = Counter(toks)
            self.tf.append(cnt)
            self.dl.append(sum(cnt.values()))
            for t in cnt:
                self.df[t] += 1
        self.avgdl = (sum(self.dl) / len(self.dl)) if self.dl else 1.0

    def save(self):
        os.makedirs(self.index_dir, exist_ok=True)
        with open(os.path.join(self.index_dir, 'bm25.pkl'), 'wb') as f:
            pickle.dump({'chunks': self.chunks, 'df': self.df, 'tf': self.tf,
                         'dl': self.dl, 'avgdl': self.avgdl}, f)

    def load(self):
        with open(os.path.join(self.index_dir, 'bm25.pkl'), 'rb') as f:
            d = pickle.load(f)
        self.__dict__.update({k: d[k] for k in ('chunks', 'df', 'tf', 'dl', 'avgdl')})
        return self

    # ---- Retriever 接口 ----
    def retrieve(self, query: str, k: int = 5, include_history: bool = False) -> list[ScoredChunk]:
        q = _tokenize_zh(query)
        N = len(self.chunks)
        scores = defaultdict(float)
        for t in q:
            n = self.df.get(t)
            if not n:
                continue
            idf = math.log(1 + (N - n + 0.5) / (n + 0.5))
            for i, cnt in enumerate(self.tf):
                f = cnt.get(t)
                if not f:
                    continue
                scores[i] += idf * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl))
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        out = []
        for i, s in ranked:
            rec = self.chunks[i]
            if not include_history and not rec.get('is_latest', 1):
                continue
            out.append(ScoredChunk(_record_to_chunk(dict(rec, location=dict(rec['location']))),
                                   float(s), 'bm25'))
            if len(out) >= k:
                break
        return out


class DenseRetriever:
    """bge + Chroma。encode_query/encode_document 分离 (D-07)。
    需要: pip install sentence-transformers chromadb;模型 BAAI/bge-large-zh-v1.5。
    换模型 = 全量重建 + 全量评测 (D-06)。"""

    QUERY_INSTRUCTION = '为这个句子生成表示以用于检索相关文章：'   # bge 中文检索指令

    def __init__(self, index_dir: str, model_name: str = 'BAAI/bge-large-zh-v1.5',
                 device: str = 'cpu'):
        self.index_dir = index_dir
        self.model_name = model_name
        self.device = device
        self._model = None
        self._col = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
        if self._col is None:
            import chromadb
            client = chromadb.PersistentClient(path=self.index_dir)
            self._col = client.get_or_create_collection(
                'lawrag', metadata={'hnsw:space': 'cosine'})

    def encode_document(self, texts: list[str]):
        self._ensure()
        return self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def encode_query(self, text: str):
        self._ensure()
        return self._model.encode([self.QUERY_INSTRUCTION + text],
                                  normalize_embeddings=True)[0]

    def build(self, chunks: list[Chunk], batch: int = 64):
        self._ensure()
        for i in range(0, len(chunks), batch):
            part = chunks[i:i + batch]
            embs = self.encode_document([c.doc_title + '\n' + c.text for c in part])
            self._col.upsert(
                ids=[c.chunk_id for c in part],
                embeddings=[e.tolist() for e in embs],
                documents=[c.text for c in part],
                metadatas=[{'record': json.dumps(_chunk_to_record(c), ensure_ascii=False),
                            'is_latest': c.is_latest, 'doc_id': c.doc_id} for c in part])

    def remove_document(self, doc_id: str):
        self._ensure()
        self._col.delete(where={'doc_id': doc_id})

    def retrieve(self, query: str, k: int = 5, include_history: bool = False) -> list[ScoredChunk]:
        self._ensure()
        where = None if include_history else {'is_latest': 1}
        res = self._col.query(query_embeddings=[self.encode_query(query).tolist()],
                              n_results=k, where=where)
        out = []
        for meta, dist in zip(res['metadatas'][0], res['distances'][0]):
            rec = json.loads(meta['record'])
            out.append(ScoredChunk(_record_to_chunk(dict(rec, location=dict(rec['location']))),
                                   1.0 - float(dist), 'dense'))
        return out
