# ragflow — 中文金融法规 RAG 问答系统

> Citation-first RAG for Chinese financial laws & regulations. 引用可信优先：每个答案可溯源到法规名与条款，宁可不答，不可乱答。

面向中小微企业财务与合规查询场景，语料为金融/银行/税法领域的公开法律、规章、规范性文件（约 1100 份，docx/doc/txt/xlsx）。

## 核心设计

- **法律结构解析**：正则识别「编/章/节/条」，按条分块，引用输出行业原生格式——《增值税法》第十二条（含版本号与历史版本标注）
- **三级引用框架**：A/B/C 级自动判级 + 降级规则；top-k 全为低可信来源时拒答
- **版本控制**：同名法规按标题归组，检索默认只出现行版，引用废止条文视为最高级事故
- **五阶段可插拔架构**：Parser → Chunker → Indexer → Retriever → Generator，各阶段独立接口；BM25 与 Dense(bge+Chroma) 检索器即插即换，未来混合检索/reranker 有预留插槽
- **评测先行**：60 题测试集（55 正题 + 5 拒答题）先于 pipeline 代码存在，引用错 = 判负

## 当前状态（MVP，spec v0.2）

- 全语料 55,728 chunks，A 级引用占比 93.4%，C 级为零
- BM25 检索基线：file_hit@5 = 90.9%，条号级 loc_hit@5 = 89.1%，单查 0.2-0.3s
- Dense（bge-large-zh-v1.5）与 LLM 端到端评测待执行（验收线：准确率 >80%，引用命中 >90%，响应 <5s）

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
