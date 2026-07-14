# -*- coding: utf-8 -*-
"""Retriever 层 (§4, D-17)。BM25(纯Python) / Dense(bge+Chroma) 可插拔。
默认检索 = 非重复+最新版;历史版本显式放开 (D-21)。
2026-07-13: 表内行级下钻(M05/X03)——全局命中表格文档时行内二次打分,治「文件命中,行不命中」。"""
import json
import math
import os
import pickle
import re
from collections import Counter, defaultdict
from .schema import Chunk, Location, ScoredChunk


def _tokenize_zh(text):
    try:
        import jieba
        return [t for t in jieba.lcut(text) if t.strip()]
    except ImportError:
        text = re.sub(r'\s+', '', text)
        toks = re.findall(r'[A-Za-z0-9〔〕\[\]第条章节%．.-]+', text)
        han = re.sub(r'[^一-鿿]', '', text)
        toks += [han[i:i + 2] for i in range(len(han) - 1)]
        return toks


def _chunk_to_record(c):
    return c.to_dict()


def _record_to_chunk(d):
    loc = Location(**d.pop('location'))
    return Chunk(location=loc, **d)


class BM25Retriever:
    """D-17 混合检索插槽的 BM25 分支;无GPU环境的基线检索器。"""

    def __init__(self, index_dir, k1=1.6, b=0.75, title_weight=3):
        self.index_dir = index_dir
        self.k1, self.b = k1, b
        self.title_weight = title_weight   # BM25F-lite:标题词权重(2026-07-13,M05 修复)
        self.chunks = []
        self.df = Counter()
        self.tf = []
        self.dl = []
        self.avgdl = 1.0
        self.doc_rows = defaultdict(list)

    def build(self, chunks):
        self.chunks = [_chunk_to_record(c) for c in chunks]
        self.tf, self.dl = [], []
        self.df = Counter()
        self.doc_rows = defaultdict(list)
        for i, c in enumerate(chunks):
            cnt = Counter(_tokenize_zh(c.text))
            for t in _tokenize_zh(c.doc_title):
                cnt[t] += self.title_weight      # 标题字段加权,压制行内长表头稀释
            cnt = Counter({t: n for t, n in cnt.items()})
            self.tf.append(cnt)
            self.dl.append(sum(cnt.values()))
            for t in cnt:
                self.df[t] += 1
            if c.location.row_range:
                self.doc_rows[c.doc_id].append(i)
        self.avgdl = (sum(self.dl) / len(self.dl)) if self.dl else 1.0

    def save(self):
        os.makedirs(self.index_dir, exist_ok=True)
        with open(os.path.join(self.index_dir, 'bm25.pkl'), 'wb') as f:
            pickle.dump({'chunks': self.chunks, 'df': self.df, 'tf': self.tf,
                         'dl': self.dl, 'avgdl': self.avgdl,
                         'doc_rows': dict(self.doc_rows)}, f)

    def load(self):
        with open(os.path.join(self.index_dir, 'bm25.pkl'), 'rb') as f:
            d = pickle.load(f)
        for k in ('chunks', 'df', 'tf', 'dl', 'avgdl'):
            setattr(self, k, d[k])
        self.doc_rows = defaultdict(list, d.get('doc_rows', {}))
        return self

    def _score(self, q_tokens, indices=None):
        """BM25 打分;indices 限定候选(表内下钻用)。"""
        N = len(self.chunks)
        scores = defaultdict(float)
        for t in q_tokens:
            n = self.df.get(t)
            if not n:
                continue
            idf = math.log(1 + (N - n + 0.5) / (n + 0.5))
            pool = indices if indices is not None else range(N)
            for i in pool:
                f = self.tf[i].get(t)
                if not f:
                    continue
                scores[i] += idf * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl))
        return scores

    def retrieve(self, query, k=5, include_history=False, drilldown=True):
        q = _tokenize_zh(query)
        scores = self._score(q)
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        picked = []
        for i, s in ranked:
            rec = self.chunks[i]
            if not include_history and not rec.get('is_latest', 1):
                continue
            picked.append(i)
            if len(picked) >= k:
                break
        # 表内行级下钻(2026-07-13, M05/X03)
        if drilldown and picked:
            picked_set = set(picked)
            for doc_id in {self.chunks[i]['doc_id'] for i in picked}:
                rows = self.doc_rows.get(doc_id)
                if not rows or len(rows) < 3:
                    continue
                row_scores = self._score(q, indices=rows)
                if not row_scores:
                    continue
                best = max(row_scores, key=row_scores.get)
                if best in picked_set:
                    continue
                same_doc = [i for i in picked if self.chunks[i]['doc_id'] == doc_id]
                victim = min(same_doc, key=lambda i: scores.get(i, 0)) if same_doc \
                    else min(picked, key=lambda i: scores.get(i, 0))
                picked[picked.index(victim)] = best
                picked_set = set(picked)
                scores[best] = max(scores.get(best, 0.0), row_scores[best])
        picked.sort(key=lambda i: -scores.get(i, 0))
        out = []
        for i in picked:
            rec = dict(self.chunks[i], location=dict(self.chunks[i]['location']))
            out.append(ScoredChunk(_record_to_chunk(rec), float(scores.get(i, 0)), 'bm25'))
        return out


class DenseRetriever:
    """bge + Chroma。encode_query/encode_document 分离 (D-07)。换模型=全量重建+全量评测 (D-06)。"""

    QUERY_INSTRUCTION = '为这个句子生成表示以用于检索相关文章：'

    def __init__(self, index_dir, model_name='BAAI/bge-large-zh-v1.5', device='cpu'):
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

    def encode_document(self, texts):
        self._ensure()
        return self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def encode_query(self, text):
        self._ensure()
        return self._model.encode([self.QUERY_INSTRUCTION + text], normalize_embeddings=True)[0]

    def build(self, chunks, batch=64):
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

    def remove_document(self, doc_id):
        self._ensure()
        self._col.delete(where={'doc_id': doc_id})

    def retrieve(self, query, k=5, include_history=False, drilldown=True):
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
