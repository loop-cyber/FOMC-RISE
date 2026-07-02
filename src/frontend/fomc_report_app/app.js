const data = window.FOMC_REPORT_DATA;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const formatPct = (value, signed = false) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "NA";
  const sign = signed && Number(value) > 0 ? "+" : "";
  return `${sign}${Number(value).toFixed(2)}%`;
};

const formatNum = (value, digits = 4) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "NA";
  return Number(value).toFixed(digits);
};

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const activeInput = () => ({
  user_question: $("#question-input").value.trim(),
  current_fomc_event: {
    ...data.current_fomc_event,
    statement_text: $("#current-statement-input").value.trim(),
    previous_statement_text: $("#previous-statement-input").value.trim(),
    market_state: collectMarketState(),
  },
  policy_shock_vector: data.policy_shock_vector,
  historical_similar_cases: data.historical_similar_cases,
  rag_retrieval_logic: data.rag_retrieval_logic,
  llm_logic_chain_report: data.llm_logic_chain_report,
  multi_asset_predictions: data.multi_asset_predictions,
  quantitative_metrics: data.multi_asset_predictions.map((item) => ({
    asset: item.asset,
    predicted_return_pct: item.predicted_return_pct,
    interval_90_pct: [item.interval_90_low_pct, item.interval_90_high_pct],
  })),
  model_evaluation: data.model_evaluation,
  risk_disclosures: data.risk_disclosures,
});

function collectMarketState() {
  const currentState = data.current_fomc_event?.market_state || {};
  const out = {};
  Object.keys(currentState).forEach((key) => {
    const input = document.querySelector(`[data-market-key="${key}"]`);
    const raw = input ? input.value.trim() : "";
    out[key] = raw === "" ? currentState[key] : Number(raw);
  });
  return out;
}

function markdownLite(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let list = [];

  const inline = (text) =>
    escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${inline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!list.length) return;
    html.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`);
    list = [];
  };

  const isTableSeparator = (line) => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
  const isTableRow = (line) => /^\s*\|.+\|\s*$/.test(line);

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i];
    const line = raw.trim();

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    if (line === "---" || line === "***") {
      flushParagraph();
      flushList();
      html.push("<hr>");
      continue;
    }

    if (line.startsWith("### ")) {
      flushParagraph();
      flushList();
      html.push(`<h4>${inline(line.slice(4))}</h4>`);
      continue;
    }

    if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      html.push(`<h3>${inline(line.slice(3))}</h3>`);
      continue;
    }

    if (line.startsWith("# ")) {
      flushParagraph();
      flushList();
      html.push(`<h2>${inline(line.slice(2))}</h2>`);
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      flushParagraph();
      list.push(line.replace(/^[-*]\s+/, ""));
      continue;
    }

    if (isTableRow(line)) {
      flushParagraph();
      flushList();
      const tableRows = [];

      while (i < lines.length && isTableRow(lines[i].trim())) {
        tableRows.push(lines[i].trim());
        i += 1;
      }
      i -= 1;

      const normalizedRows = tableRows.filter((row) => !isTableSeparator(row));
      const cells = normalizedRows.map((row) =>
        row
          .replace(/^\|/, "")
          .replace(/\|$/, "")
          .split("|")
          .map((cell) => cell.trim())
      );

      if (cells.length) {
        const [head, ...body] = cells;
        html.push(`
          <div class="markdown-table-wrap">
            <table class="markdown-table">
              <thead><tr>${head.map((cell) => `<th>${inline(cell)}</th>`).join("")}</tr></thead>
              <tbody>${body
                .map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join("")}</tr>`)
                .join("")}</tbody>
            </table>
          </div>
        `);
      }
      continue;
    }

    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  return html.join("");
}

function exportLlmReportPdf() {
  const reportHtml = $("#llm-report").innerHTML;
  if (!reportHtml.trim()) {
    showToast("暂无可导出的报告");
    return;
  }

  const title = `${data.current_fomc_event?.event_id || "FOMC"}_logic_chain_report`;
  const printWindow = window.open("", "_blank", "noopener,noreferrer,width=980,height=800");
  if (!printWindow) {
    showToast("浏览器阻止了弹窗，无法导出 PDF");
    return;
  }

  printWindow.document.write(`<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <title>${escapeHtml(title)}</title>
    <style>
      body { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17201b; line-height: 1.65; }
      h1,h2,h3,h4 { margin-top: 0; }
      h2 { font-size: 26px; margin-bottom: 18px; }
      h3 { font-size: 20px; margin: 24px 0 10px; }
      h4 { font-size: 16px; margin: 18px 0 8px; }
      p, li { font-size: 14px; }
      table { width: 100%; border-collapse: collapse; margin: 12px 0 20px; }
      th, td { border: 1px solid #d7d7d7; padding: 8px 10px; text-align: left; vertical-align: top; font-size: 13px; }
      th { background: #f5f5f5; }
      code { background: #f3f3f3; padding: 1px 4px; border-radius: 4px; }
      hr { border: none; border-top: 1px solid #ddd; margin: 22px 0; }
      .meta { color: #5f6b65; font-size: 12px; margin-bottom: 18px; }
      @page { size: A4; margin: 14mm; }
    </style>
  </head>
  <body>
    <h2>RAG 历史案例逻辑链分析报告</h2>
    <div class="meta">${escapeHtml(data.current_fomc_event?.date || "")} ${escapeHtml(data.current_fomc_event?.event_id || "")}</div>
    ${reportHtml}
  </body>
</html>`);
  printWindow.document.close();
  printWindow.focus();
  printWindow.onload = () => {
    printWindow.print();
  };
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 1700);
}

async function copyText(text, message) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(message);
  } catch {
    showToast("当前浏览器不支持直接复制");
  }
}

function renderOverview() {
  const event = data.current_fomc_event;
  $("#question-input").value = data.default_user_question;
  $("#current-statement-input").value = event.statement_text || event.statement_excerpt || "";
  $("#previous-statement-input").value = event.previous_statement_text || "";
  $("#event-title").textContent = `${event.date} ${event.event_id}`;
  $("#model-chip").textContent = data.metadata.model_label;
  $("#experiment-chip").textContent = data.metadata.experiment_name;

  $("#event-list").innerHTML = `
    <dt>事件 ID</dt><dd>${escapeHtml(event.event_id)}</dd>
    <dt>日期</dt><dd>${escapeHtml(event.date)}</dd>
    <dt>会议类型</dt><dd>${escapeHtml(event.meeting_type)}</dd>
    <dt>参数来源</dt><dd>${escapeHtml(data.metadata.parameter_source)}</dd>
  `;
  $("#statement-excerpt").textContent = event.statement_excerpt;

  $("#market-state").innerHTML = Object.entries(event.market_state)
    .map(([key, value]) => `
      <div class="state-item">
        <span>${escapeHtml(key)}</span>
        <input
          class="state-input"
          type="number"
          step="0.001"
          data-market-key="${escapeHtml(key)}"
          value="${value ?? ""}"
        >
      </div>
    `)
    .join("");

  const evalSummary = data.model_evaluation.summary;
  const metrics = [
    ["方向准确率", `${formatNum(evalSummary.direction_accuracy * 100, 2)}%`],
    ["平衡方向准确率", `${formatNum(evalSummary.balanced_direction_accuracy * 100, 2)}%`],
    ["MAE", formatNum(evalSummary.MAE, 5)],
    ["RMSE", formatNum(evalSummary.RMSE, 5)],
    ["90% 覆盖率", `${formatNum(evalSummary.coverage_90 * 100, 2)}%`],
    ["平均区间宽度", `${formatNum(evalSummary.avg_interval_width * 100, 2)}%`],
  ];

  $("#metric-grid").innerHTML = metrics
    .map(([label, value]) => `
      <div class="metric">
        <span>${label}</span>
        <strong>${value}</strong>
      </div>
    `)
    .join("");
}

function replaceData(nextData) {
  Object.keys(data).forEach((key) => {
    delete data[key];
  });
  Object.assign(data, nextData);
}

function renderPredictions() {
  $("#asset-grid").innerHTML = data.multi_asset_predictions
    .map((item) => {
      const barWidth = Math.max(6, Math.min(100, Math.abs(item.predicted_return_pct) * 18));
      return `
        <article class="asset-card">
          <header>
            <div>
              <h3>${escapeHtml(item.asset)}</h3>
              <span>${escapeHtml(item.label)}</span>
            </div>
            <em class="direction ${item.direction}">${item.direction_label}</em>
          </header>
          <div class="return-value">${formatPct(item.predicted_return_pct, true)}</div>
          <div class="spark"><i style="width:${barWidth}%"></i></div>
          <span>90% 区间 ${formatPct(item.interval_90_low_pct, true)} 至 ${formatPct(item.interval_90_high_pct, true)}</span>
        </article>
      `;
    })
    .join("");

  $("#prediction-table").innerHTML = data.multi_asset_predictions
    .map((item) => `
      <tr>
        <td><strong>${escapeHtml(item.asset)}</strong><br><span>${escapeHtml(item.label)}</span></td>
        <td><em class="direction ${item.direction}">${item.direction_label}</em></td>
        <td>${formatPct(item.predicted_return_pct, true)}</td>
        <td>${formatPct(item.interval_90_low_pct, true)} 至 ${formatPct(item.interval_90_high_pct, true)}</td>
      </tr>
    `)
    .join("");

  const fields = [
    ["模型", data.model_evaluation.summary.model],
    ["方向准确率", `${formatNum(data.model_evaluation.summary.direction_accuracy * 100, 2)}%`],
    ["MAE", formatNum(data.model_evaluation.summary.MAE, 5)],
    ["RMSE", formatNum(data.model_evaluation.summary.RMSE, 5)],
    ["90% 覆盖率", `${formatNum(data.model_evaluation.summary.coverage_90 * 100, 2)}%`],
    ["平均区间宽度", `${formatNum(data.model_evaluation.summary.avg_interval_width * 100, 2)}%`],
  ];

  $("#evaluation-grid").innerHTML = fields
    .map(([label, value]) => `
      <div class="eval-item">
        <span>${label}</span>
        <strong>${value}</strong>
      </div>
    `)
    .join("");
}

function renderEvidence() {
  $("#shock-list").innerHTML = data.policy_shock_vector
    .map((item) => `
      <article class="shock-item">
        <div class="shock-top">
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <p class="evidence">${escapeHtml(item.evidence)}</p>
          </div>
          <span class="badge">${escapeHtml(item.direction)} · ${escapeHtml(item.confidence)}</span>
        </div>
        <span>Strength ${formatNum(item.strength, 1)}</span>
      </article>
    `)
    .join("");

  $("#case-list").innerHTML = data.historical_similar_cases
    .map((item) => `
      <article class="case-item">
        <div class="case-top">
          <div>
            <strong>#${item.rank} ${escapeHtml(item.event_id)}</strong>
            <p class="evidence">${escapeHtml(item.date)}</p>
          </div>
          <span class="badge">sim ${formatNum(item.similarity, 3)}</span>
        </div>
        <div class="case-metrics">
          <span>shock cosine ${formatNum(item.shock_cosine, 3)}</span>
          <span>evidence cosine ${formatNum(item.evidence_cosine, 3)}</span>
          <span>SPY ${formatPct(item.returns_pct.SPY, true)}</span>
          <span>QQQ ${formatPct(item.returns_pct.QQQ, true)}</span>
          <span>GLD ${formatPct(item.returns_pct.GLD, true)}</span>
          <span>UUP ${formatPct(item.returns_pct.UUP, true)}</span>
        </div>
      </article>
    `)
    .join("");

  const llm = data.llm_logic_chain_report;

  if (llm?.status === "generated" && llm.content) {
    $("#llm-report").innerHTML = `<div class="markdown-report">${markdownLite(llm.content)}</div>`;
  } else {
    $("#llm-report").innerHTML = `
      <div class="empty-report">
        <strong>尚未生成 LLM 逻辑链分析报告</strong>
        <p>${escapeHtml(llm?.message || "请先运行 LLM 生成脚本。")}</p>
        <pre>export SJTU_API_KEY="你的 API Key"
python src/app/generate_logic_chain_report.py --model &lt;MODEL_NAME&gt;
python src/app/build_frontend_data.py</pre>
      </div>
    `;
  }

}

function renderLlmReport(content, status = "generated") {
  data.llm_logic_chain_report = {
    status,
    content,
    source_file: "src/frontend/fomc_report_app/llm_logic_chain_report.md",
    message: status === "generated" ? "由前端请求触发 LLM 生成。" : "",
  };
  $("#llm-report").innerHTML = `<div class="markdown-report">${markdownLite(content)}</div>`;
}

async function generateLlmReport() {
  const button = $("#generate-llm-report");
  const status = $("#generation-status");
  const userQuestion = $("#question-input").value.trim();
  const currentStatement = $("#current-statement-input").value.trim();
  const previousStatement = $("#previous-statement-input").value.trim();
  const marketState = collectMarketState();

  if (!userQuestion) {
    showToast("请先输入用户问题");
    return;
  }

  if (!currentStatement) {
    showToast("请先提供当前声明文本");
    return;
  }

  button.disabled = true;
  button.textContent = "正在生成...";
  status.textContent = "正在执行在线 RAG 检索、hgbdt/fusion 预测，并调用 LLM...";

  try {
    const response = await fetch("/api/generate-logic-chain", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        user_question: userQuestion,
        current_statement_text: currentStatement,
        previous_statement_text: previousStatement,
        market_state: marketState,
        base_event_id: data.current_fomc_event.event_id,
        top_k_cases: 3,
        timeout: 600,
        retries: 1,
        max_tokens: 5000,
        model_family: "hgbdt",
      }),
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }

    if (result.frontend_data) {
      replaceData(result.frontend_data);
      renderOverview();
      renderPredictions();
      renderEvidence();
    }
    renderLlmReport(result.report);
    status.textContent = `生成完成：${result.model}，prompt ${result.prompt_chars} 字符`;
    showToast("LLM 逻辑链报告已生成");
  } catch (error) {
    status.textContent = `生成失败：${error.message}`;
    showToast("生成失败，请检查服务端和 API key");
  } finally {
    button.disabled = false;
    button.textContent = "RAG 检索 + 模型预测 + 生成逻辑链报告";
  }
}

function reportTemplate() {
  const input = activeInput();

  if (input.llm_logic_chain_report?.status === "generated" && input.llm_logic_chain_report.content) {
    return input.llm_logic_chain_report.content;
  }

  const strongest = [...input.multi_asset_predictions].sort(
    (a, b) => Math.abs(b.predicted_return_pct) - Math.abs(a.predicted_return_pct)
  )[0];
  const rows = input.multi_asset_predictions
    .map(
      (item) =>
        `| ${item.asset} | ${item.direction_label} | ${formatPct(item.predicted_return_pct, true)} | ${formatPct(item.interval_90_low_pct, true)} 至 ${formatPct(item.interval_90_high_pct, true)} |`
    )
    .join("\n");

  const shockRows = input.policy_shock_vector
    .map(
      (item) =>
        `| ${item.label} | ${item.direction} | ${formatNum(item.strength, 1)} | ${item.confidence} | ${item.evidence} | 基于该 evidence 句，该维度为 ${item.direction}，强度为 ${formatNum(item.strength, 1)}。 |`
    )
    .join("\n");

  const caseRows = input.historical_similar_cases
    .map(
      (item) =>
        `- ${item.event_id} (${item.date})：综合相似度 ${formatNum(item.similarity, 3)}，shock cosine ${formatNum(item.shock_cosine, 3)}，历史收益 SPY ${formatPct(item.returns_pct.SPY, true)}、QQQ ${formatPct(item.returns_pct.QQQ, true)}、GLD ${formatPct(item.returns_pct.GLD, true)}、UUP ${formatPct(item.returns_pct.UUP, true)}。`
    )
    .join("\n");
  const ragLogic = input.rag_retrieval_logic;
  const ragSignals = ragLogic.retrieval_signals
    .map((item) => `- ${item.name}：${item.meaning}`)
    .join("\n");
  const ragCaseReading = ragLogic.current_case_reading
    .map((item) => `- ${item}`)
    .join("\n");
  const caseFeatureList = ragLogic.case_memory_features
    .map((item) => `- ${item}`)
    .join("\n");

  return `# FOMC 多资产预测用户报告

## 1. 问题理解

用户关注的问题是：${input.user_question}

本报告基于 ${input.current_fomc_event.date} 的 ${input.current_fomc_event.event_id}，使用 hgbdt/fusion 模型对 SPY、QQQ、GLD 和 UUP 的短期事件收益进行解释。

## 2. 核心预测结论

- 当前绝对预测幅度最大的资产是 ${strongest.asset}，预测收益为 ${formatPct(strongest.predicted_return_pct, true)}，90% 区间为 ${formatPct(strongest.interval_90_low_pct, true)} 至 ${formatPct(strongest.interval_90_high_pct, true)}。
- hgbdt/fusion 的跨资产历史方向准确率为 ${formatNum(input.model_evaluation.summary.direction_accuracy * 100, 2)}%，MAE 为 ${formatNum(input.model_evaluation.summary.MAE, 5)}。
- 90% 区间平均覆盖率为 ${formatNum(input.model_evaluation.summary.coverage_90 * 100, 2)}%，用于衡量历史回测中实际收益落入预测区间的比例。

## 3. 多资产量化预测表

| 资产 | 预测方向 | 预测收益 | 90% 区间 |
| --- | --- | ---: | ---: |
${rows}

## 4. 政策冲击分解

| 冲击维度 | 方向 | 强度 | 置信度 | 证据句 | 对预测解释的含义 |
| --- | --- | ---: | --- | --- | --- |
${shockRows}

## 5. 预测逻辑链

当前 FOMC 文本先被分解为五类政策冲击向量。hgbdt/fusion 模型随后同时使用宏观市场变量、派生市场状态、shock 主效应、shock 与市场状态交互项，以及 RAG case-memory 特征生成多资产预测。报告中的方向、幅度、区间和置信度均直接来自模型输出。

### RAG 历史案例检索逻辑

${ragLogic.method_summary}

检索排序使用的关键信号包括：

${ragSignals}

相似案例进入 fusion 模型时不是作为长文本直接参与预测，而是转换为以下 case-memory 特征：

${caseFeatureList}

${ragLogic.fusion_usage}

${ragLogic.interpretation_boundary}

## 6. 历史相似案例支撑

${caseRows}

当前 Top 历史案例链读法：

${ragCaseReading}

## 7. 不确定性、风险因素和模型边界

90% 预测区间表示按历史滚动残差校准后，模型期望约 90% 的同类回测结果落入该区间。该区间不是收益上下限，也不能保证未来事件必然落入区间。

${input.risk_disclosures.map((item) => `- ${item}`).join("\n")}
`;
}

function bindInteractions() {
  $("#question-input").addEventListener("input", () => {
  });
  $("#current-statement-input").addEventListener("input", () => {
  });
  $("#previous-statement-input").addEventListener("input", () => {
  });
  $("#market-state").addEventListener("input", (event) => {
    if (!event.target.matches(".state-input")) return;
  });
  $("#copy-report").addEventListener("click", () =>
    copyText(reportTemplate(), "已复制用户报告")
  );
  $("#copy-llm-report").addEventListener("click", () =>
    copyText(
      data.llm_logic_chain_report?.content || reportTemplate(),
      "已复制 LLM 逻辑链报告"
    )
  );
  $("#export-llm-pdf").addEventListener("click", exportLlmReportPdf);
  $("#generate-llm-report").addEventListener("click", generateLlmReport);

  const sections = $$(".section");
  const navItems = $$(".side-nav a");
  window.addEventListener("scroll", () => {
    const current = sections
      .map((section) => [section.id, section.getBoundingClientRect().top])
      .filter(([, top]) => top < 140)
      .pop();
    if (!current) return;
    navItems.forEach((item) => item.classList.toggle("active", item.hash === `#${current[0]}`));
  });
}

function init() {
  renderOverview();
  renderPredictions();
  renderEvidence();
  bindInteractions();
}

init();
