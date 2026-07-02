# FOMC 用户报告前端

这是一个本地前端工作台，用于展示 `hgbdt / fusion` 的默认演示结果，并支持用户输入问题后触发一次在线链路：

```text
用户问题 + 当前/上一期声明文本 + 可编辑宏观变量
-> RAG 检索
-> 单事件模型预测
-> 调用 LLM 生成逻辑链分析报告
```

## 当前数据来源

首次加载页面时，静态展示数据来自：

```text
src/frontend/fomc_report_app/demo_data
```

对应的静态前端数据文件由下面脚本生成：

```text
src/app/build_frontend_data.py
-> src/frontend/fomc_report_app/app_data.js
```

当前默认模型设定：

```text
model_family = hgbdt
feature_set = fusion
```

调参结果读取自：

```text
outputs/modeling/tuning/baseline_tuning_20260525_221743/baseline_best_params.csv
```

## 页面功能

当前页面包含：

1. 当前 FOMC 事件信息。
2. 用户问题输入框。
3. 当前声明文本、上一期声明文本输入框。
4. 可编辑的宏观/市场状态变量输入框。
5. 多资产预测卡片与量化预测表。
6. `hgbdt/fusion` 评估摘要。
7. 政策冲击分解。
8. 历史相似案例。
9. LLM 逻辑链分析报告。

当前页面不展示：

1. Prompt 章节。
2. 材料章节。
3. 上涨概率。
4. 置信度。

## 启动方式

先启动本地服务：

```bash
export SJTU_API_KEY="你的 API Key"
python src/app/serve_frontend.py --port 8010
```

然后打开：

```text
http://127.0.0.1:8010/src/frontend/fomc_report_app/
```

服务根路径 `/` 会自动跳转到前端页面。

如果端口被占用，可以换端口：

```bash
python src/app/serve_frontend.py --port 8012
```
```text
http://127.0.0.1:8012/src/frontend/fomc_report_app/
```


## 首次加载和交互生成的区别

首次加载页面时：

- 直接读取 `app_data.js`
- 展示 `demo_data` 对应的固定事件、固定预测结果和已有 LLM 报告

点击“RAG 检索 + 模型预测 + 生成逻辑链报告”后：

- 后端读取前端输入的用户问题、当前声明文本、上一期声明文本和宏观变量
- 重新构造当前事件的 shock
- 重新做 RAG 检索
- 重新做单事件 `hgbdt/fusion` 预测
- 调用 LLM 生成新的逻辑链报告
- 结果直接返回前端刷新展示

注意：

- 点击按钮时不会重跑整套 `src/modeling/modeling.py` 回测实验
- 它做的是在线单事件推理，不是重新训练一轮完整实验

## 后端接口

前端按钮调用的本地接口是：

```text
POST /api/generate-logic-chain
```

本地服务入口：

```text
src/app/serve_frontend.py
```

在线推理逻辑入口：

```text
src/app/online_inference.py
```

LLM 报告生成入口：

```text
src/app/generate_logic_chain_report.py
```

默认 LLM 配置：

```text
Base URL: https://models.sjtu.edu.cn/api/v1/chat/completions
Model: deepseek-reasoner
```

## 静态数据更新

如果你修改了默认演示数据目录 `src/frontend/fomc_report_app/demo_data`，或者更新了静态展示要读取的报告内容，需要重新生成：

```bash
python src/app/build_frontend_data.py
```

这个脚本只会更新：

```text
src/frontend/fomc_report_app/app_data.js
```

它不会打开网页，也不会调用 LLM。

## 单独生成 LLM 报告

如果你想不经过前端，直接用 Python 覆盖当前 LLM 报告文件：

```bash
export SJTU_API_KEY="你的 API Key"
python src/app/generate_logic_chain_report.py
```

生成结果会写入：

```text
src/frontend/fomc_report_app/llm_logic_chain_report.md
src/frontend/fomc_report_app/llm_logic_chain_payload.json
```

如果只想检查即将发送给 LLM 的 payload：

```bash
python src/app/generate_logic_chain_report.py --dry-run
```

## 当前说明入口

页面顶部“项目说明”链接当前指向：

```text
README.md
```
