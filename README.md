# ragflow — 中文金融法规 RAG 问答系统

> Citation-first RAG for Chinese financial laws & regulations. 引用可信优先：每个答案可溯源到法规名与条款，宁可不答，不可乱答。

面向中小微企业财务与合规查询场景，语料为金融/银行/税法领域的公开法律、规章、规范性文件（约 1100 份，docx/doc/txt/xlsx）。

## 核心设计

- **法律结构解析**：正则识别「编/章/节/条」，按条分块，引用输出行业原生格式——《增值税法》第十二条（含版本号与历史版本标注）
- **三级引用框架**：A/B/C 级自动判级 + 降级规则；top-k 全为低可信来源时拒答
- **版本控制**：同名法规按标题归组，检索默认只出现行版，引用废止条文视为最高级事故
- **五阶段可插拔架构**：Parser → Chunker → Indexer → Retriever → Generator，各阶段独立接口；BM25 与 Dense(bge+Chroma) 检索器即插即换，未来混合检索/reranker 有预留插槽
- **评测先行**：60 题测试集（55 正题 + 5 拒答题）先于 pipeline 代码存在，引用错 = 判负

## 当前状态（MVP，spec v0.2，2026-07-12 评测后）

- 全语料 59,097 chunks，A 级引用占比 94%，C 级为零
- BM25 检索基线：file_hit@5 = 94.5%，条号级 loc_hit@5 = 92.7%，单查 0.2-0.3s
- 端到端（BM25 + DeepSeek-chat）：60 题延迟全部 <5s；人工复核修正三类评测误判后估计准确率 ≥81.7%（详见 spec_dev.md 评测记录），待修复版 eval 重跑确认
- 已修复：拒答标志漏标（拒答语挂无关引用）、cite_ok 结构化比对、判分归一化与数值容差、doc_title 跨段截断
- Dense（bge-large-zh-v1.5）与混合检索为下一优化项

## 目录

```
lawrag/       核心包（含运行手册 lawrag/README.md）
scripts/      语料预处理:登记表构建 / 去重 / 版本归组
testset/      冻结测试集 testset_v1.jsonl
spec_dev.md   唯一事实来源:全部决议(D-01~D-26)、接口定义、引用规则、评测协议、已知风险
```

## 快速开始

```bash
pip install python-docx openpyxl jieba
export LAWRAG_ROOT=/path/to/corpus LAWRAG_META=/path/to/metadata
python -m lawrag.cli index --retriever bm25
python -m lawrag.cli search "外资银行被取缔后几年内不受理设立申请？"
python -m lawrag.cli eval --mode retrieval
```

详见 `lawrag/README.md`。开发原则见 `spec_dev.md`——决议只追加不改写，任何与 spec 冲突的代码以 spec 为准。

## License

MIT
