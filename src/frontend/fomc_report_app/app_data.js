window.FOMC_REPORT_DATA = {
  "metadata": {
    "title": "FOMC 多资产预测用户报告工作台",
    "model_family": "hgbdt",
    "feature_set": "fusion",
    "model_label": "hgbdt/fusion",
    "parameter_source": "baseline_tuning_20260525_221743/baseline_best_params.csv",
    "experiment_name": "experiment_20260525_230248_hgbdt",
    "experiment_created_at": "2026-05-25T23:26:44",
    "generated_from": "src/frontend/fomc_report_app/demo_data"
  },
  "default_user_question": "本次 FOMC 事件后，SPY、QQQ、GLD 和 UUP 的短期收益方向和风险如何？",
  "current_fomc_event": {
    "event_id": "FOMC_0002",
    "date": "2026-03-18",
    "meeting_type": "Statement",
    "statement_excerpt": "Available indicators suggest that economic activity has been expanding at a solid pace. Job gains have remained low, and the unemployment rate has been little changed in recent months. Inflation remains somewhat elevated. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. Uncertainty about the economic outlook remains elevated. The implications of developments in the Middle East for the U.S. economy are uncertain. The Committee is attentive to the risks to both sides of its dual mandate. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent. In considering the extent and timing of additional adjustments to the target range for the federal...",
    "statement_text": "Available indicators suggest that economic activity has been expanding at a solid pace. Job gains have remained low, and the unemployment rate has been little changed in recent months. Inflation remains somewhat elevated. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. Uncertainty about the economic outlook remains elevated. The implications of developments in the Middle East for the U.S. economy are uncertain. The Committee is attentive to the risks to both sides of its dual mandate. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent. In considering the extent and timing of additional adjustments to the target range for the federal funds rate, the Committee will carefully assess incoming data, the evolving outlook, and the balance of risks. The Committee is strongly committed to supporting maximum employment and returning inflation to its 2 percent objective. In assessing the appropriate stance of monetary policy, the Committee will continue to monitor the implications of incoming information for the economic outlook. The Committee would be prepared to adjust the stance of monetary policy as appropriate if risks emerge that could impede the attainment of the Committee's goals. The Committee's assessments will take into account a wide range of information, including readings on labor market conditions, inflation pressures and inflation expectations, and financial and international developments. Voting for the monetary policy action were Jerome H. Powell, Chair; John C. Williams, Vice Chair; Michael S. Barr; Michelle W. Bowman; Lisa D. Cook; Beth M. Hammack; Philip N. Jefferson; Neel Kashkari; Lorie K. Logan; Anna Paulson; and Christopher J. Waller. Voting against this action was Stephen I. Miran, who preferred to lower the target range for the federal funds rate by 1/4 percentage point at this meeting. For media inquiries, please email [email protected] or call 202-452-2955. Implementation Note issued March 18, 2026",
    "previous_statement_text": "Available indicators suggest that economic activity has been expanding at a solid pace. Job gains have remained low, and the unemployment rate has shown some signs of stabilization. Inflation remains somewhat elevated. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. Uncertainty about the economic outlook remains elevated. The Committee is attentive to the risks to both sides of its dual mandate. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent. In considering the extent and timing of additional adjustments to the target range for the federal funds rate, the Committee will carefully assess incoming data, the evolving outlook, and the balance of risks. The Committee is strongly committed to supporting maximum employment and returning inflation to its 2 percent objective. In assessing the appropriate stance of monetary policy, the Committee will continue to monitor the implications of incoming information for the economic outlook. The Committee would be prepared to adjust the stance of monetary policy as appropriate if risks emerge that could impede the attainment of the Committee's goals. The Committee's assessments will take into account a wide range of information, including readings on labor market conditions, inflation pressures and inflation expectations, and financial and international developments. Voting for the monetary policy action were Jerome H. Powell, Chair; John C. Williams, Vice Chair; Michael S. Barr; Michelle W. Bowman; Lisa D. Cook; Beth M. Hammack; Philip N. Jefferson; Neel Kashkari; Lorie K. Logan; and Anna Paulson. Voting against this action were Stephen I. Miran and Christopher J. Waller, who preferred to lower the target range for the federal funds rate by 1/4 percentage point at this meeting. For media inquiries, please email [email protected] or call 202-452-2955. Implementation Note issued January 28, 2026",
    "market_state": {
      "DX-Y.NYB": 112.17,
      "^VIX": 25.09,
      "DGS2": 3.76,
      "DGS10": 4.26,
      "CPIAUCSL": 330.293,
      "UNRATE": 4.3,
      "PAYEMS": 158637.0,
      "T10Y2Y": 0.5,
      "BAA10Y": 1.81,
      "UUP_volume": 4280000.0,
      "SPY_volume": 82060000.0,
      "GLD_volume": 18375600.0,
      "QQQ_volume": 56130000.0
    }
  },
  "policy_shock_vector": [
    {
      "key": "interest_rate_path",
      "label": "Interest Rate Path",
      "direction": "dovish",
      "strength": 2.0,
      "confidence": "medium",
      "evidence": "Voting against this action was Stephen I. Miran (vs. previous: Voting against this action were Stephen I. Miran and Christopher J. Waller)"
    },
    {
      "key": "inflation_concern",
      "label": "Inflation Concern",
      "direction": "neutral",
      "strength": 1.0,
      "confidence": "high",
      "evidence": "Inflation remains somewhat elevated (identical in both statements)"
    },
    {
      "key": "growth_concern",
      "label": "Growth Concern",
      "direction": "dovish",
      "strength": 2.0,
      "confidence": "medium",
      "evidence": "The implications of developments in the Middle East for the U.S. economy are uncertain (added in current statement)"
    },
    {
      "key": "labor_market",
      "label": "Labor Market",
      "direction": "dovish",
      "strength": 1.0,
      "confidence": "medium",
      "evidence": "the unemployment rate has been little changed in recent months (vs. previous: the unemployment rate has shown some signs of stabilization)"
    },
    {
      "key": "financial_stability",
      "label": "Financial Stability",
      "direction": "neutral",
      "strength": 1.0,
      "confidence": "high",
      "evidence": "No material change in financial conditions language"
    }
  ],
  "historical_similar_cases": [
    {
      "rank": 1,
      "event_id": "FOMC_0013",
      "date": "2025-06-18",
      "similarity": 0.9257,
      "shock_cosine": 0.6667,
      "evidence_cosine": 0.1172,
      "semantic_similarity": 0.9257,
      "macro_mean_abs_z_diff": 0.14,
      "statement_excerpt": "Although swings in net exports have affected the data, recent indicators suggest that economic activity has continued to expand at a solid pace. The unemployment rate remains low, and labor market conditions remain solid. Inflation remains somewhat elevated. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. Uncertainty about the economic outlook has diminished but remains elevated. The Committee is attentive to the risks to both sides of its dual mandate. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 4-1/4 to 4-1/2 percent. In considering the extent and timing of additional adjustments to the target range for the federal funds rate, the Committee will carefully assess incoming data, the evolving outlook, and the balance of risks. The Committee will continue reducing its holdings of Treasury securities and agency debt and agency mortgage-backed securities. The Committee is strongly committed to supporting maximum employment and returning inflation to its 2 percent objective. In assessing the appropriate stance of monetary policy, the Committee will continue to monitor the implications of incoming information for the economic outlook. The Committee would be prepar...",
      "previous_statement_excerpt": "Although swings in net exports have affected the data, recent indicators suggest that economic activity has continued to expand at a solid pace. The unemployment rate has stabilized at a low level in recent months, and labor market conditions remain solid. Inflation remains somewhat elevated. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. Uncertainty about the economic outlook has increased further. The Committee is attentive to the risks to both sides of its dual mandate and judges that the risks of higher unemployment and higher inflation have risen. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 4-1/4 to 4-1/2 percent. In considering the extent and timing of additional adjustments to the target range for the federal funds rate, the Committee will carefully assess i...",
      "shock_evidence": {
        "interest_rate_path": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "The Committee decided to maintain the target range for the federal funds rate at 4-1/4 to 4-1/2 percent."
        },
        "inflation_concern": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "Inflation remains somewhat elevated."
        },
        "growth_concern": {
          "direction": "dovish",
          "strength": 2.0,
          "confidence": "medium",
          "evidence": "Uncertainty about the economic outlook has diminished but remains elevated."
        },
        "labor_market": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "The unemployment rate remains low, and labor market conditions remain solid."
        },
        "financial_stability": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "medium",
          "evidence": "No material change in language regarding financial conditions or developments."
        }
      },
      "returns_pct": {
        "SPY": -0.02,
        "QQQ": -0.02,
        "GLD": -0.54,
        "UUP": 0.18
      }
    },
    {
      "rank": 2,
      "event_id": "FOMC_0027",
      "date": "2024-07-31",
      "similarity": 0.9225,
      "shock_cosine": 0.5659,
      "evidence_cosine": 0.0937,
      "semantic_similarity": 0.9225,
      "macro_mean_abs_z_diff": 0.3495,
      "statement_excerpt": "Recent indicators suggest that economic activity has continued to expand at a solid pace. Job gains have moderated, and the unemployment rate has moved up but remains low. Inflation has eased over the past year but remains somewhat elevated. In recent months, there has been some further progress toward the Committee's 2 percent inflation objective. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. The Committee judges that the risks to achieving its employment and inflation goals continue to move into better balance. The economic outlook is uncertain, and the Committee is attentive to the risks to both sides of its dual mandate. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 5-1/4 to 5-1/2 percent. In considering any adjustments to the target range for the federal funds rate, the Committee will carefully assess incoming data, the evolving outlook, and the balance of risks. The Committee does not expect it will be appropriate to reduce the target range until it has gained greater confidence that inflation is moving sustainably toward 2 percent. In addition, the Committee will continue reducing its holdings of Treasury securities and agency debt and agency mortgage...",
      "previous_statement_excerpt": "Recent indicators suggest that economic activity has continued to expand at a solid pace. Job gains have remained strong, and the unemployment rate has remained low. Inflation has eased over the past year but remains elevated. In recent months, there has been modest further progress toward the Committee's 2 percent inflation objective. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. The Committee judges that the risks to achieving its employment and inflation goals have moved toward better balance over the past year. The economic outlook is uncertain, and the Committee remains highly attentive to inflation risks. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 5-1/4 to 5-1/2 percent. In considering any adjustments to the target range for the federal funds rate, the Comm...",
      "shock_evidence": {
        "interest_rate_path": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "The Committee decided to maintain the target range for the federal funds rate at 5-1/4 to 5-1/2 percent. The Committee does not expect it will be appropriate to reduce the target range until it has gained greater confidence that inflation is moving sustainably toward 2 percent."
        },
        "inflation_concern": {
          "direction": "dovish",
          "strength": 2.0,
          "confidence": "high",
          "evidence": "Previous: 'Inflation has eased over the past year but remains elevated.' Current: 'Inflation has eased over the past year but remains somewhat elevated.'"
        },
        "growth_concern": {
          "direction": "dovish",
          "strength": 2.0,
          "confidence": "high",
          "evidence": "Previous: 'The economic outlook is uncertain, and the Committee remains highly attentive to inflation risks.' Current: 'The economic outlook is uncertain, and the Committee is attentive to the risks to both sides of its dual mandate.'"
        },
        "labor_market": {
          "direction": "dovish",
          "strength": 3.0,
          "confidence": "high",
          "evidence": "Previous: 'Job gains have remained strong, and the unemployment rate has remained low.' Current: 'Job gains have moderated, and the unemployment rate has moved up but remains low.'"
        },
        "financial_stability": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "No material change in language regarding financial conditions, credit, or banking stress. The Committee's assessments continue to take into account 'financial and international developments'."
        }
      },
      "returns_pct": {
        "SPY": 1.63,
        "QQQ": 2.96,
        "GLD": 1.81,
        "UUP": -0.55
      }
    },
    {
      "rank": 3,
      "event_id": "FOMC_0011",
      "date": "2025-07-30",
      "similarity": 0.9211,
      "shock_cosine": 0.9245,
      "evidence_cosine": 0.1076,
      "semantic_similarity": 0.9211,
      "macro_mean_abs_z_diff": 0.1921,
      "statement_excerpt": "Although swings in net exports continue to affect the data, recent indicators suggest that growth of economic activity moderated in the first half of the year. The unemployment rate remains low, and labor market conditions remain solid. Inflation remains somewhat elevated. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. Uncertainty about the economic outlook remains elevated. The Committee is attentive to the risks to both sides of its dual mandate. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 4-1/4 to 4-1/2 percent. In considering the extent and timing of additional adjustments to the target range for the federal funds rate, the Committee will carefully assess incoming data, the evolving outlook, and the balance of risks. The Committee will continue reducing its holdings of Treasury securities and agency debt and agency mortgage-backed securities. The Committee is strongly committed to supporting maximum employment and returning inflation to its 2 percent objective. In assessing the appropriate stance of monetary policy, the Committee will continue to monitor the implications of incoming information for the economic outlook. The Committee would be prepared t...",
      "previous_statement_excerpt": "Although swings in net exports have affected the data, recent indicators suggest that economic activity has continued to expand at a solid pace. The unemployment rate remains low, and labor market conditions remain solid. Inflation remains somewhat elevated. The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. Uncertainty about the economic outlook has diminished but remains elevated. The Committee is attentive to the risks to both sides of its dual mandate. In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 4-1/4 to 4-1/2 percent. In considering the extent and timing of additional adjustments to the target range for the federal funds rate, the Committee will carefully assess incoming data, the evolving outlook, and the balance of risks. The Committee will continue reducing its...",
      "shock_evidence": {
        "interest_rate_path": {
          "direction": "dovish",
          "strength": 2.0,
          "confidence": "medium",
          "evidence": "Two dissenters 'preferred to lower the target range for the federal funds rate'"
        },
        "inflation_concern": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "Inflation remains somewhat elevated (identical phrasing)"
        },
        "growth_concern": {
          "direction": "dovish",
          "strength": 3.0,
          "confidence": "high",
          "evidence": "Previous: 'economic activity has continued to expand at a solid pace'; Current: 'growth of economic activity moderated in the first half of the year'"
        },
        "labor_market": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "The unemployment rate remains low, and labor market conditions remain solid (identical phrasing)"
        },
        "financial_stability": {
          "direction": "neutral",
          "strength": 1.0,
          "confidence": "high",
          "evidence": "No change in language regarding financial conditions or developments"
        }
      },
      "returns_pct": {
        "SPY": -0.13,
        "QQQ": 0.13,
        "GLD": -1.73,
        "UUP": 0.98
      }
    }
  ],
  "rag_retrieval_logic": {
    "title": "RAG 历史案例检索逻辑链",
    "method_summary": "当前事件先被表示为政策 shock 数值向量、shock evidence 文本、声明语义向量和宏观市场状态；检索阶段在历史 FOMC 事件中寻找这些维度同时相近的案例，再将相似案例的资产收益分布转化为 case-memory 特征。",
    "retrieval_signals": [
      {
        "name": "shock_cosine",
        "meaning": "当前事件与历史事件在五类政策冲击向量上的余弦相似度。"
      },
      {
        "name": "evidence_cosine",
        "meaning": "当前 shock evidence 句与历史 evidence 文本的语义相似度。"
      },
      {
        "name": "embedding_cosine_semantic",
        "meaning": "FOMC 声明文本整体语义相似度。"
      },
      {
        "name": "macro_mean_abs_z_diff",
        "meaning": "宏观市场状态的平均标准化距离，数值越低代表宏观状态越接近。"
      },
      {
        "name": "similarity_for_baseline",
        "meaning": "综合相似度，用于排序并计算相似案例加权收益。"
      }
    ],
    "case_memory_features": [
      "case_pred_{asset}_ret：相似案例加权平均历史收益",
      "case_up_prob_{asset}：相似案例中该资产上涨的加权概率",
      "case_std_{asset}：相似案例收益离散度",
      "case_direction_agreement_{asset}：相似案例方向一致性",
      "case_avg_similarity / case_max_similarity / case_similarity_std：案例集合相似度结构"
    ],
    "fusion_usage": "hgbdt/fusion 不直接把相似案例文本写入预测结论，而是把上述 case-memory 数值特征与宏观变量、shock 主效应、shock 交互项一起输入 HistGradientBoosting 模型，生成每个资产的方向概率、收益幅度和 90% 预测区间。",
    "current_case_reading": [
      "Top 1 历史案例 FOMC_0013：综合相似度 0.9257，shock 相似度 0.6667，evidence 相似度 0.1172，宏观距离 0.14。",
      "Top 2 历史案例 FOMC_0027：综合相似度 0.9225，shock 相似度 0.5659，evidence 相似度 0.0937，宏观距离 0.3495。",
      "Top 3 历史案例 FOMC_0011：综合相似度 0.9211，shock 相似度 0.9245，evidence 相似度 0.1076，宏观距离 0.1921。"
    ],
    "interpretation_boundary": "由于检索本身已经使用 shock 信息，rag/case-memory 不是完全不含 shock 的对照；它解释的是“与当前政策冲击和宏观状态相似的历史事件，其后资产反应如何”。"
  },
  "llm_logic_chain_report": {
    "status": "generated",
    "content": "# RAG 历史案例逻辑链分析报告\n\n**当前事件**：FOMC_0002（2026-03-18 Statement）  \n**模型**：hgbdt/fusion  \n**分析日期**：2026-05-26\n\n---\n\n## 一、核心预测结果\n\n| 资产 | 预测方向 | 预测收益 (%) | 90% 预测区间 (%) |\n|------|----------|--------------|------------------|\n| SPY  | 下跌     | -0.35        | [-2.76, 2.05]    |\n| QQQ  | 上涨     | 0.09         | [-3.83, 4.02]    |\n| GLD  | 上涨     | 0.05         | [-2.60, 2.70]    |\n| UUP  | 上涨     | 0.04         | [-1.03, 1.12]    |\n\n**核心结论**：本次 FOMC 声明维持利率不变，但声明措辞调整叠加地缘不确定性上升，释放了整体偏鸽派的政策信号。历史相似案例显示资产反应存在分化：权益类（SPY）倾向小幅下跌，而 QQQ 和 GLD 录得微弱正收益，美元（UUP）小幅走强。90% 预测区间均包含零，所有方向的置信度偏低。\n\n---\n\n## 二、政策冲击与资产价格传导链\n\n### 2.1 政策冲击分解\n\n| 冲击维度 | 方向 | 强度 | 关键文本证据 |\n|----------|------|------|-------------|\n| Interest Rate Path | 鸽派 | 2.0 | 本次投票反对者仅一人（Stephen I. Miran），前期为两人，暗示分歧收窄，偏鸽 |\n| Inflation Concern | 中性 | 1.0 | “Inflation remains somewhat elevated” 措辞与前期完全相同 |\n| Growth Concern | 鸽派 | 2.0 | 新增“The implications of developments in the Middle East for the U.S. economy are uncertain”，反映增长不确定性上升 |\n| Labor Market | 鸽派 | 1.0 | 失业率描述从“some signs of stabilization”改为“little changed”，边际走弱 |\n| Financial Stability | 中性 | 1.0 | 金融条件表述无实质变化 |\n\n**综合判定**：本次政策冲击整体偏鸽，鸽派主要来自利率路径分歧收窄和增长不确定性上升；通胀和金融稳定维持中性；劳动力市场微幅转弱。\n\n### 2.2 资产价格传导逻辑\n\n1. **SPY（标普500）**：鸽派利率路径理论上利好风险资产，但增长不确定性上升（尤其是中东地缘风险）压制风险偏好，且通胀仍“somewhat elevated”限制了进一步宽松预期。历史相似案例回测显示 SPY 收益方向偏负，当前预测下跌 -0.35%，主要受增长担忧压过鸽派利率信号的传导。\n2. **QQQ（纳斯达克100）**：科技成长股对利率路径更敏感，鸽派方向形成支撑；但增长不确定性同样构成制约。预测微弱上涨 0.09%，反映鸽/鹰力量大致平衡下历史案例中 QQQ 表现分化。\n3. **GLD（黄金）**：鸽派利率路径和增长不确定性共同利好黄金（实际利率预期下降、避险需求），但通胀中性限制了黄金的进一步上行动力。预测微涨 0.05%，幅度极为有限。\n4. **UUP（美元指数）**：鸽派利率路径通常利空美元，但增长不确定性和中东地缘风险可能触发避险美元买盘，且市场未定价大幅降息。历史案例中美元录得小幅正收益，预测上涨 0.04%。\n\n**传导链总结**：鸽派利率路径 + 增长担忧 → 多资产方向分化，权益类承压而避险资产受益有限。\n\n---\n\n## 三、Top 历史案例的文本相似点、差异点与资产反应\n\n### 3.1 检索依据（RAG）\n\n当前事件被表示为五维政策冲击向量、shock evidence 文本嵌入、声明语义嵌入和宏观市场状态（VIX=25.09，收益率曲线 T10Y2Y=0.5，失业率 4.3% 等）。检索系统在历史 FOMC 事件中寻找这些维度同时相近的案例，返回 Top-3 事件。\n\n### 3.2 Top-1 案例：FOMC_0013（2025-06-18）\n\n- **综合相似度**：0.9257（最高）\n- **shock 相似度**：0.6667；**evidence 相似度**：0.1172；**宏观距离**：0.14（非常接近）\n- **声明语义相似度**：0.9257\n\n**文本相似点**：  \n- 均提到“economic activity expanding at a solid pace”  \n- “Inflation remains somewhat elevated” 完全一致  \n- “Uncertainty about the economic outlook” 表述高度一致（当前“remains elevated”，前者“has diminished but remains elevated”）  \n- 维持利率不变，且均存在内部反对票（前者无明确反对，当前一人反对）\n\n**文本差异点**：  \n- 当前事件新增“Middle East”不确定性，FOMC_0013 未提及  \n- 当前失业率“little changed” vs 前期“remains low”  \n- 前期利率区间为 4.25–4.5%，当前为 3.5–3.75%，绝对利率水平不同\n\n**历史资产反应**：SPY -0.02%，QQQ -0.02%，GLD -0.54%，UUP +0.18%  \n> 该案例资产表现总体平淡，SPY/QQQ 微跌，黄金跌幅稍大，美元微涨。当前预测与此方向基本一致（SPY 跌、UUP 涨），但 GLD 预测转为微涨，反映当前增长担忧更强（地缘风险）可能提升黄金避险价值。\n\n### 3.3 Top-2 案例：FOMC_0027（2024-07-31）\n\n- **综合相似度**：0.9225；**shock 相似度**：0.5659；**evidence 相似度**：0.0937；**宏观距离**：0.3495\n- **声明语义相似度**：0.9225\n\n**文本相似点**：  \n- 均提到“Job gains have moderated”（前者更具体：“moved up but remains low”）  \n- “Inflation has eased over the past year but remains somewhat elevated” 措辞类同  \n- 均为维持利率不变，且经济前景不确定性\n\n**文本差异点**：  \n- FOMC_0027 有更强的鸽派转向（通胀从“elevated”改“somewhat elevated”，劳动力明显走弱），而当前通胀措辞未变。  \n- 当前中东地缘风险为新增因素，前者未涉及。  \n- 宏观状态差异较大（宏观距离 0.3495），主要是利率水平不同。\n\n**历史资产反应**：SPY +1.63%，QQQ +2.96%，GLD +1.81%，UUP -0.55%  \n> 该案例为历史上一次明显的鸽派转向事件，资产大幅上涨、美元走弱。当前预测方向与之相反（SPY 跌、UUP 涨），说明当前 shock 相似度仅 0.5659，并不完全匹配。虽然语义相似度较高，但 shock 结构差异导致其资产反应在当前传导链中权重较低。\n\n### 3.4 Top-3 案例：FOMC_0011（2025-07-30）\n\n- **综合相似度**：0.9211；**shock 相似度**：0.9245（最高）；**evidence 相似度**：0.1076；**宏观距离**：0.1921\n- **声明语义相似度**：0.9211\n\n**文本相似点**：  \n- 均提及“Uncertainty about the economic outlook remains elevated”  \n- “Inflation remains somewhat elevated” 完全一致  \n- 均有两位反对者（前者两名委员“preferred to lower rates”，当前仅一人反对，但方向一致）\n\n**文本差异点**：  \n- FOMC_0011 明确提到“growth of economic activity moderated”，当前则描述为“expanding at a solid pace”，增长基调更强。  \n- 当前新增地缘不确定性，前者未涉及。  \n- 劳动力市场：前者“remains low”，当前“little changed”。\n\n**历史资产反应**：SPY -0.13%，QQQ +0.13%，GLD -1.73%，UUP +0.98%  \n> 该案例在 shock 结构上与当前最相似（shock 余弦 0.9245），资产反应也与当前预测方向高度一致：SPY 小幅下跌，QQQ 微涨，UUP 上涨，GLD 下跌。唯一差异是当前 GLD 预测由跌转涨（+0.05%），可能归因于当前中东不确定性带来的额外避险需求。该案例对预测的贡献权重最大。\n\n### 3.5 案例集合的 case-memory 特征\n\nTop-3 案例平均相似度 0.9231，数量为 3 个。  \n在 case-memory 数值特征中，各资产的加权历史收益被转化为模型输入。由于 Top-1 和 Top-3 均显示 SPY 下跌、UUP 上涨，而 Top-2 显示相反方向，因此 case-memory 对 SPY 和 UUP 的方向信号较为一致，而对 QQQ 和 GLD 则存在冲突（Top-2 大幅上涨 vs Top-1/3 微跌或下跌）。融合模型最终预测 QQQ 和 GLD 为微弱上涨，反映模型在冲突中偏向于增长担忧和鸽派利率路径的组合逻辑。\n\n---\n\n## 四、当前预测的证据强弱与不确定性\n\n### 4.1 证据较强的资产\n\n- **SPY**（下跌 -0.35%）：shock 相似度最高的 Top-3 案例显示下跌，历史方向一致性相对较高。宏观状态（VIX>25，收益率曲线平坦）支持避险情绪。\n- **UUP**（上涨 0.04%）：Top-1 和 Top-3 美元均上涨，中东不确定性可能强化避险货币需求。\n\n### 4.2 证据较弱的资产\n\n- **QQQ**（上涨 0.09%）：Top-2 大幅上涨与 Top-1/3 方向冲突，模型取折中方向，区间宽度达 [-3.83%, 4.02%]，不确定性高。\n- **GLD**（上涨 0.05%）：历史案例中仅 Top-2 大幅上涨，Top-1 和 Top-3 均下跌。当前预测转为微涨主要依赖地缘风险假设，但缺乏足够历史证据支持。\n\n### 4.3 不确定性来源\n\n1. **地缘风险未被历史案例充分覆盖**：中东不确定性是新增因素，FOMC_0011 和 FOMC_0013 均未提及，历史资产反应可能无法完全代表当前情景。\n2. **微观 shock 证据较弱**：growth_concern 的 evidence 仅为一句话的新增，且未量化冲击程度；labor_market 变化幅度微小。\n3. **宏观状态差异**：当前失业率 4.3%、VIX 25.09 与历史案例宏观距离虽低，但绝对利率水平（3.5–3.75%）显著低于 Top-2（5.25–5.5%），可能影响传导力度。\n4. **模型区间覆盖率高但幅度宽**：90% 预测区间均包含零，表明模型在概率空间中保留了较大的不确定性。\n\n---\n\n## 五、模型边界与风险提示\n\n1. **历史案例的相似性不能保证因果复制**：当前输入未提供实际事后资产表现，本报告仅基于历史统计模式做预测，实际结果可能偏离。\n2. **RAG 检索依赖历史有限样本**：Top-3 案例中两个在穿越不同利率水平时静态做了横向对比，未能完全控制绝对利率水平差异。\n3. **模型方向准确率约为 55–60%**：根据 backtest，hgbdt/fusion 的整体方向准确率为 55.94%，平衡准确率 54.21%，高于随机但仍有约 45% 的错误空间。\n4. **90% 预测区间覆盖率为 91.77%**，但逐资产看 GLD 在 2022–2026 段覆盖率仅 82.35%，当前 GLD 预测可能落在覆盖率不足的区间。\n5. **本报告不构成投资建议**，所有预测均基于历史统计和现有数据，不预示未来确定结果。\n\n---\n\n## 附录：方法说明\n\n### 附录 A：hgbdt/fusion 如何把传导链转化为预测\n\n1. **特征输入**：模型接收三组特征：\n   - 宏观市场变量：美元指数、VIX、国债收益率、CPI、失业率、非农就业等\n   - 派生市场状态：收益率曲线斜率、信用利差等\n   - 政策冲击：五维 shock 的 direction × strength 编码，以及 shock 交互项（如利率路径×增长担忧）\n   - RAG case-memory 特征：由相似案例加权收益、上涨概率、方向一致性、离散度等数值构成\n2. **模型结构**：HistGradientBoosting 回归，以方向准确率和区间校准为优化目标，boosting 轮数通过 early stopping 确定。\n3. **输出**：四个资产各自的预测收益、方向标签、90% 预测区间（基于分位数损失函数计算）。区间宽度反映了模型在相似历史模式下的预测不确定性。\n\n### 附录 B：RAG 检索历史事件的依据\n\n- **检索向量构成**：  \n  1. 政策冲击数值向量（五维方向×强度编码）  \n  2. shock evidence 文本的 Sentence-BERT 嵌入  \n  3. 完整声明的语义嵌入  \n  4. 宏观市场状态（8维 + 派生变量），标准化后计算欧氏距离\n- **相似度综合**：对各维度相似度赋予加权，形成 `similarity_for_baseline`，用于排序和 case-memory 权重的计算。\n- **检索结果**：返回 Top-3 事件，其 shock 结构、声明语调、宏观状态与当前最接近。由于检索本身已利用 shock 信息，case-memory 并非纯文本对照，而是“与当前政策冲击和宏观状态相似的历史事件，其后资产反应如何”的体现。\n- **融合使用**：hgbdt/fusion 不直接使用案例文本，而是将 case-memory 数值特征与宏观/shock 特征一起训练，因此模型可自动调整历史案例的权重，避免过拟合单一故事线。\n\n---\n\n*报告基于输入 JSON 生成，未补充任何外部信息。所有解释仅依据给定数据。*\n",
    "source_file": "src/frontend/fomc_report_app/llm_logic_chain_report.md",
    "message": "已加载 LLM 生成的 RAG 逻辑链分析报告。"
  },
  "multi_asset_predictions": [
    {
      "asset": "SPY",
      "target": "SPY_ret",
      "label": "S&P 500 ETF",
      "predicted_return": -0.003531,
      "predicted_return_pct": -0.35,
      "direction": "down",
      "direction_label": "下跌",
      "prob_up": 0.371,
      "prob_up_pct": 37.1,
      "confidence": 1.0,
      "confidence_pct": 100.0,
      "interval_90_low": -0.027583,
      "interval_90_high": 0.02052,
      "interval_90_low_pct": -2.76,
      "interval_90_high_pct": 2.05,
      "interval_width_pct": 4.81,
      "case_avg_similarity": 0.9231,
      "case_neighbor_count": 3.0
    },
    {
      "asset": "QQQ",
      "target": "QQQ_ret",
      "label": "Nasdaq 100 ETF",
      "predicted_return": 0.000927,
      "predicted_return_pct": 0.09,
      "direction": "up",
      "direction_label": "上涨",
      "prob_up": 0.4772,
      "prob_up_pct": 47.7,
      "confidence": 1.0,
      "confidence_pct": 100.0,
      "interval_90_low": -0.038321,
      "interval_90_high": 0.040175,
      "interval_90_low_pct": -3.83,
      "interval_90_high_pct": 4.02,
      "interval_width_pct": 7.85,
      "case_avg_similarity": 0.9231,
      "case_neighbor_count": 3.0
    },
    {
      "asset": "GLD",
      "target": "GLD_ret",
      "label": "Gold ETF",
      "predicted_return": 0.000526,
      "predicted_return_pct": 0.05,
      "direction": "up",
      "direction_label": "上涨",
      "prob_up": 0.3737,
      "prob_up_pct": 37.4,
      "confidence": 1.0,
      "confidence_pct": 100.0,
      "interval_90_low": -0.025968,
      "interval_90_high": 0.02702,
      "interval_90_low_pct": -2.6,
      "interval_90_high_pct": 2.7,
      "interval_width_pct": 5.3,
      "case_avg_similarity": 0.9231,
      "case_neighbor_count": 3.0
    },
    {
      "asset": "UUP",
      "target": "UUP_ret",
      "label": "US Dollar Index ETF",
      "predicted_return": 0.000441,
      "predicted_return_pct": 0.04,
      "direction": "up",
      "direction_label": "上涨",
      "prob_up": 0.6854,
      "prob_up_pct": 68.5,
      "confidence": 1.0,
      "confidence_pct": 100.0,
      "interval_90_low": -0.01033,
      "interval_90_high": 0.011212,
      "interval_90_low_pct": -1.03,
      "interval_90_high_pct": 1.12,
      "interval_width_pct": 2.15,
      "case_avg_similarity": 0.9231,
      "case_neighbor_count": 3.0
    }
  ],
  "model_evaluation": {
    "summary": {
      "model": "hgbdt/fusion",
      "direction_accuracy": 0.5594,
      "balanced_direction_accuracy": 0.5421,
      "MAE": 0.01027,
      "RMSE": 0.0151,
      "coverage_90": 0.9177,
      "avg_interval_width": 0.0558
    },
    "by_asset": [
      {
        "asset": "GLD",
        "n_test": 120,
        "direction_accuracy": 0.5333,
        "balanced_direction_accuracy": 0.5219,
        "MAE": 0.01143,
        "RMSE": 0.01485,
        "coverage_90": 0.9,
        "avg_interval_width": 0.05614
      },
      {
        "asset": "QQQ",
        "n_test": 148,
        "direction_accuracy": 0.6081,
        "balanced_direction_accuracy": 0.5705,
        "MAE": 0.01333,
        "RMSE": 0.02116,
        "coverage_90": 0.9122,
        "avg_interval_width": 0.07851
      },
      {
        "asset": "SPY",
        "n_test": 148,
        "direction_accuracy": 0.5541,
        "balanced_direction_accuracy": 0.5498,
        "MAE": 0.01109,
        "RMSE": 0.01725,
        "coverage_90": 0.9054,
        "avg_interval_width": 0.06347
      },
      {
        "asset": "UUP",
        "n_test": 107,
        "direction_accuracy": 0.5421,
        "balanced_direction_accuracy": 0.5262,
        "MAE": 0.00522,
        "RMSE": 0.00713,
        "coverage_90": 0.9533,
        "avg_interval_width": 0.02508
      }
    ],
    "segments": [
      {
        "segment": "2008_2015",
        "asset": "GLD",
        "n_test": 35,
        "direction_accuracy": 0.4857,
        "MAE": 0.0127,
        "coverage_90": 0.8857
      },
      {
        "segment": "2008_2015",
        "asset": "QQQ",
        "n_test": 63,
        "direction_accuracy": 0.619,
        "MAE": 0.01336,
        "coverage_90": 0.9524
      },
      {
        "segment": "2008_2015",
        "asset": "SPY",
        "n_test": 63,
        "direction_accuracy": 0.5397,
        "MAE": 0.01287,
        "coverage_90": 0.9048
      },
      {
        "segment": "2008_2015",
        "asset": "UUP",
        "n_test": 22,
        "direction_accuracy": 0.4091,
        "MAE": 0.00659,
        "coverage_90": 0.9091
      },
      {
        "segment": "2016_2019",
        "asset": "GLD",
        "n_test": 33,
        "direction_accuracy": 0.5455,
        "MAE": 0.00904,
        "coverage_90": 0.9697
      },
      {
        "segment": "2016_2019",
        "asset": "QQQ",
        "n_test": 33,
        "direction_accuracy": 0.5152,
        "MAE": 0.00885,
        "coverage_90": 0.9697
      },
      {
        "segment": "2016_2019",
        "asset": "SPY",
        "n_test": 33,
        "direction_accuracy": 0.5152,
        "MAE": 0.00618,
        "coverage_90": 0.9394
      },
      {
        "segment": "2016_2019",
        "asset": "UUP",
        "n_test": 33,
        "direction_accuracy": 0.7273,
        "MAE": 0.00409,
        "coverage_90": 1.0
      },
      {
        "segment": "2020_2021",
        "asset": "GLD",
        "n_test": 18,
        "direction_accuracy": 0.6667,
        "MAE": 0.01197,
        "coverage_90": 0.9444
      },
      {
        "segment": "2020_2021",
        "asset": "QQQ",
        "n_test": 18,
        "direction_accuracy": 0.8333,
        "MAE": 0.01612,
        "coverage_90": 0.8333
      },
      {
        "segment": "2020_2021",
        "asset": "SPY",
        "n_test": 18,
        "direction_accuracy": 0.6111,
        "MAE": 0.01675,
        "coverage_90": 0.8889
      },
      {
        "segment": "2020_2021",
        "asset": "UUP",
        "n_test": 18,
        "direction_accuracy": 0.6111,
        "MAE": 0.00502,
        "coverage_90": 0.9444
      },
      {
        "segment": "2022_2026",
        "asset": "GLD",
        "n_test": 34,
        "direction_accuracy": 0.5,
        "MAE": 0.01216,
        "coverage_90": 0.8235
      },
      {
        "segment": "2022_2026",
        "asset": "QQQ",
        "n_test": 34,
        "direction_accuracy": 0.5588,
        "MAE": 0.01616,
        "coverage_90": 0.8235
      },
      {
        "segment": "2022_2026",
        "asset": "SPY",
        "n_test": 34,
        "direction_accuracy": 0.5882,
        "MAE": 0.00955,
        "coverage_90": 0.8824
      },
      {
        "segment": "2022_2026",
        "asset": "UUP",
        "n_test": 34,
        "direction_accuracy": 0.4118,
        "MAE": 0.00553,
        "coverage_90": 0.9412
      }
    ]
  },
  "tuned_parameters": {},
  "risk_disclosures": [
    "本页面用于研究展示，不构成投资建议。",
    "hgbdt/fusion 是基于历史 FOMC 事件的监督学习模型，无法保证未来事件符合历史分布。",
    "90% 区间来自滚动 conformal calibration，极端市场状态下可能低估尾部风险。",
    "RAG case-memory 已包含 shock-aware 检索信息，不能解释为完全独立于 shock 的纯文本检索。"
  ],
  "report_contract": {
    "required_inputs": [
      "user_question",
      "current_fomc_event",
      "policy_shock_vector",
      "historical_similar_cases",
      "rag_retrieval_logic",
      "llm_logic_chain_report",
      "multi_asset_predictions",
      "quantitative_metrics",
      "model_evaluation",
      "risk_disclosures"
    ],
    "report_sections": [
      "问题理解",
      "核心预测结论",
      "多资产量化预测表",
      "政策冲击分解",
      "预测逻辑链",
      "历史相似案例支撑",
      "不确定性、风险因素和模型边界"
    ],
    "generation_rules": [
      "只能依据结构化输入、模型输出、相似案例原文摘录和 evidence 句生成解释。",
      "不得编造 FOMC 表述、资产收益、宏观数据、相似案例或模型指标。",
      "若证据不足，必须明确写出证据不足，而不是补充外部推测。",
      "所有方向、幅度、区间和置信度必须与 multi_asset_predictions 一致。",
      "报告必须包含模型边界说明，且不得写成投资建议。"
    ]
  },
  "materials": {
    "research_report_md": "README.md",
    "frontend_readme": "src/frontend/fomc_report_app/README.md"
  }
};
