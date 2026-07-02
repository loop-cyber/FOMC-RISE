# FOMC 文本分析与 RAG 多资产预测项目

本项目实现了一套 FOMC 声明文本分析与多资产收益预测流程，覆盖事件抽取、政策冲击识别、RAG 历史案例检索、资产收益建模，以及本地交互式前端展示。

## 项目结构

```text
.
├── data/
│   ├── raw/                 # 原始 Excel 数据
│   ├── interim/             # 中间事件表
│   ├── processed/           # 政策冲击抽取结果
│   └── rag_corpus/          # RAG 元数据、向量矩阵和 SVD 模型
├── outputs/
│   ├── retrieval/           # RAG 检索结果、基准预测和 prompt 输出
│   └── modeling/            # 建模实验结果、预测表、评估表和图表
├── src/
│   ├── app/                 # 前端数据生成、在线推理和本地服务
│   ├── frontend/            # 本地交互式前端页面
│   ├── modeling/            # 多资产收益预测建模脚本
│   └── rag/                 # 文本差分、冲击抽取、RAG 构建与检索脚本
├── requirements.txt
└── README.md
```

## 环境准备

建议使用 Python 3.10 及以上版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如需运行 `--model-family xgboost` 分支，可额外安装：

```bash
pip install xgboost
```

`xgboost` 不是默认前端展示和 `hgbdt` 建模分支的必需依赖。

## 快速运行前端

如果只查看已有静态展示结果，可以直接启动本地服务：

```bash
python src/app/serve_frontend.py --port 8010
```

然后打开：

```text
http://127.0.0.1:8010/src/frontend/fomc_report_app/
```

如果要使用页面中的“RAG 检索 + 模型预测 + 生成逻辑链报告”按钮，需要先配置 API Key：

```bash
export SJTU_API_KEY="你的 API Key"
python src/app/serve_frontend.py --port 8010
```

端口被占用时可以更换端口，例如：

```bash
python src/app/serve_frontend.py --port 8012
```

## 运行流程

### 1. 生成 FOMC 事件表

输入文件：

```text
data/raw/data_for_text_diff.xlsx
```

运行：

```bash
python src/rag/extract_fomc_events.py
```

输出：

```text
data/interim/fomc_events.csv
```

### 2. 抽取五类政策冲击

默认使用 OpenAI 兼容 Chat Completions 接口。需要设置 API Key：

```bash
export SJTU_API_KEY="你的 API Key"
python src/rag/run_batch.py
```

输出：

```text
data/processed/fomc_policy_shocks.csv
```

本地调试且不调用 API：

```bash
python src/rag/run_batch.py --dry-run
```

### 3. 构建 RAG 语料和向量

默认读取原始文本数据和政策冲击文件：

```bash
export DASHSCOPE_API_KEY="你的百炼 API Key"
python src/rag/build_rag_corpus.py
```

只生成 TF-IDF/SVD 本地向量、不调用 Embedding API：

```bash
python src/rag/build_rag_corpus.py --skip-api
```

输出目录：

```text
data/rag_corpus/
```

### 4. RAG 检索与基准预测

```bash
python src/rag/retrieve_fomc_neighbors.py
```

主要输出：

```text
outputs/retrieval/fomc_retrieval_pipeline_topk.csv
outputs/retrieval/fomc_baseline_predictions.csv
outputs/retrieval/fomc_cot_prompts.jsonl
```

生成单个会议的 CoT prompt：

```bash
python src/rag/retrieve_fomc_neighbors.py --query-event-id FOMC_0002
```

调用百炼 Chat 生成解释文本：

```bash
export DASHSCOPE_API_KEY="你的百炼 API Key"
python src/rag/retrieve_fomc_neighbors.py --query-event-id FOMC_0002 --generate-llm
```

### 5. 运行收益预测建模

默认运行建模脚本：

```bash
python src/modeling/modeling.py
```

可以用 `--model-family` 指定 baseline、shock、fusion 三组监督模型使用同一类算法：

```bash
python src/modeling/modeling.py --model-family ridge
python src/modeling/modeling.py --model-family lasso
python src/modeling/modeling.py --model-family elasticnet
python src/modeling/modeling.py --model-family hgbdt
python src/modeling/modeling.py --model-family xgboost
```

可选值说明：

- `current`：旧混合设置，baseline 用 Ridge，shock 和 fusion 用 XGBoost 或 HGBDT。
- `ridge`：三组特征都用 Ridge 回归。
- `lasso`：三组特征都用 Lasso 回归。
- `elasticnet`：三组特征都用 ElasticNet 回归。
- `hgbdt`：三组特征都用 sklearn HistGradientBoosting。
- `xgboost`：三组特征都用 XGBoost，需要额外安装 `xgboost`。

默认读取：

```text
data/raw/data_for_text_diff.xlsx
data/processed/fomc_policy_shocks.csv
outputs/retrieval/fomc_retrieval_pipeline_topk.csv
```

默认输出：

```text
outputs/modeling/experiments/experiment_YYYYMMDD_HHMMSS/
```

### 6. 更新前端静态数据

如果更新了前端演示数据、检索结果或 LLM 报告，需要重新生成：

```bash
python src/app/build_frontend_data.py
```

输出：

```text
src/frontend/fomc_report_app/app_data.js
```

该命令只更新静态前端数据，不启动网页服务，也不会调用 LLM。

## 关键脚本

| 脚本 | 作用 |
| --- | --- |
| `src/rag/extract_fomc_events.py` | 从原始 Excel 抽取 FOMC 事件表 |
| `src/rag/run_batch.py` | 调用 LLM，根据声明差分抽取五类政策冲击 |
| `src/rag/sentence_align.py` | 关键词筛选与 TF-IDF 句级余弦对齐 |
| `src/rag/build_rag_corpus.py` | 构建 RAG 元数据、文本向量和宏观/市场状态 |
| `src/rag/retrieve_fomc_neighbors.py` | 历史案例检索、基准预测与 CoT prompt 生成 |
| `src/modeling/modeling.py` | 多资产收益预测建模 |
| `src/modeling/tune_baseline.py` | 模型调参脚本 |
| `src/app/build_frontend_data.py` | 生成前端静态数据 |
| `src/app/online_inference.py` | 前端交互后的在线检索与预测 |
| `src/app/generate_logic_chain_report.py` | 生成 LLM 逻辑链报告 |
| `src/app/serve_frontend.py` | 启动本地前端服务 |


