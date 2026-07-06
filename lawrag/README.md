# lawrag — 中文金融法规 RAG 问答系统（MVP）

spec_dev.md 是唯一事实来源；本 README 只讲怎么跑。

## 安装

```bash
pip install python-docx openpyxl jieba          # 基础(BM25 链路)
pip install sentence-transformers chromadb      # 可选(Dense 链路,首次运行自动下载 bge-large-zh-v1.5 约1.3GB)
```

## 环境变量

```
LAWRAG_ROOT      语料根目录(默认指向开发沙盒,本机运行必须设置,如 C:\Users\wxt20\Documents\rag sys)
LAWRAG_META      metadata_output 目录(registry.jsonl / testset / 索引所在)
LAWRAG_LLM_API_KEY / LAWRAG_LLM_MODEL / LAWRAG_LLM_BASE_URL   OpenAI 兼容 API(默认 deepseek-chat)
```

## 命令

```bash
python -m lawrag.cli index  --retriever bm25      # 建索引(全语料约2分钟)
python -m lawrag.cli search "外资银行被取缔后几年内不受理申请？"      # 只检索,看引用
python -m lawrag.cli ask    "……"                  # 检索+LLM,需 API key
python -m lawrag.cli eval   --mode retrieval      # testset 检索基线(不调LLM)
python -m lawrag.cli eval   --mode full           # 完整评测(准确率/引用/拒答/延迟)
```

## 架构（spec §4 五阶段,全部可插拔）

```
registry.jsonl ─► pipeline ─► parsers(law_regex 结构探测路由) ─► chunker(按条/款) 
              ─► retriever(BM25 | Dense bge+Chroma,D-17 混合插槽) ─► generator(R1 降级/拒答)
eval.py: 检索基线 与 完整评测 双模式,引用错=判负(D-05)
```

## 基线记录（2026-07-05,BM25/jieba/k=5,55 道正题）

file_hit@5 = 90.9%，loc_hit@5(条号级) = 89.1%，单查延迟 0.2-0.3s。
分格式:doc 100/100,docx 95/95,xlsx 100/100,txt 85/77,md 60/60。
5 个未命中中 3 个为跨格式孪生文档判分伪失误(见 spec 已知限制),1 个跨文档题部分命中,1 个疑似多源题。
Dense/混合检索、LLM 端到端评测待本机环境执行(沙盒无法下载模型)。

## 已知事项

- 挂载盘会向文件注入 null 字节(同步盘所致):执行前用 VM 本地副本;本机运行无此问题。
- 索引不入库 git/网盘,重建只需 2 分钟。
- 换 embedding 模型 = 全量重建+全量评测(D-06)。
