# 🦅 鹰眼 — Hermes Agent 5层智能技能检索引擎

> **从100+技能中精准匹配Top-5 —— 硬检测词、模糊匹配、语义搜索、排名融合。零核心修改。**

[English](README.md)

---

## 问题

[Hermes Agent](https://github.com/nousresearch/hermes-agent) 将所有已安装技能以平铺列表形式加载到系统提示词中。当技能数量超过50个时：

- **LLM选错技能** —— 描述重叠导致选择混乱
- **浪费token** —— 每轮对话仅技能列表就消耗5,000–10,000 token
- **低频技能被埋没** —— 沉在长列表底部，永远不被选中

## 解决方案

鹰眼是一个**零侵入插件**，在每次API调用前充当智能预过滤器，将技能列表缩小到最相关的Top-5候选，以轻量提示注入用户消息。

```
用户查询
    │
    ▼
┌─────────────────────────────────────────────┐
│  L1: 硬检测词                                │
│  确定性关键词匹配（三层匹配算法）             │
│  命中 → 直接注入完整SKILL.md                 │
│  未命中 ↓                                   │
├─────────────────────────────────────────────┤
│  L2: FTS5 BM25      （文本相似度）           │
│  L3: 同义词词典      （领域知识编码）         │
│  L4: 稠密嵌入        （语义相似度）           │
│  L5: RRF融合         （排名组合）            │
│                                             │
│  分数 ≥ 阈值 → 注入技能提示                 │
│  分数 < 阈值 → 静默（LLM自主回答）           │
└─────────────────────────────────────────────┘
    │
    ▼
LLM最终决策
```

## 核心设计决策

### 1. "不匹配"本身也是正确的匹配结果

不是每个查询都需要技能。"晚饭吃什么？"最好由LLM用通用知识回答——而不是加载美食搜索技能。鹰眼的置信度门槛防止强制匹配。

### 2. 确定性优先，概率性兜底

L1（硬检测词）是100%精确的——用户输入"debug"，调试技能立即加载，没有任何概率成分。L2–L5处理长尾场景，模糊/语义匹配在此发挥作用。

### 3. 提示，而非决策

L2–L5返回候选，而非结论。LLM保留最终决定权：加载技能、组合多个技能、或完全忽略提示。检索系统不覆盖LLM的判断。

### 4. 每层独立可失败

如果`sentence-transformers`未安装，L4优雅降级——L1+L2+L3仍然工作。如果`jieba`缺失，L1+L4仍然工作。系统永不崩溃，始终回退到可用子集。

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/willingning-coder/eagle-eye.git
cd eagle-eye

# 2. 从本地技能库生成配置
python scripts/build_config.py

# 3. 审查并自定义
#    - 编辑 src/skill_retriever.py 中的 _HARD_TRIGGERS
#    - 编辑 src/skill_synonyms.yaml
#    
# 4. 安装
bash scripts/install.sh

# 5. 重启Hermes
hermes gateway restart
```

## 自定义

鹰眼自带**最小示例数据**。真正的价值在于根据你安装的技能生成专属配置。

### 自动生成（推荐）

```bash
# 扫描本地技能并生成模板配置
python scripts/build_config.py

# 或仅列出发现的技能
python scripts/build_config.py --scan-only
```

### 手动自定义

| 组件 | 文件 | 操作 |
|------|------|------|
| **硬检测词** | `src/skill_retriever.py` → `_HARD_TRIGGERS` | 添加`(关键词, 技能名)`元组，更具体的放前面 |
| **同义词词典** | `src/skill_synonyms.yaml` | 将自然语言术语映射到技能，每个技能5–15个 |
| **嵌入模型** | 环境变量`HERMES_EMBEDDING_MODEL` | 替换为不同的sentence-transformers模型 |

## 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `HERMES_DISABLE_SKILL_RETRIEVAL` | *（未设置）* | 设为`1`完全禁用 |
| `HERMES_SKILL_RETRIEVAL_TOP_K` | `5` | 返回的技能数量 |
| `HERMES_EMBEDDING_MODEL` | `shibing624/text2vec-base-chinese-paraphrase` | L4使用的嵌入模型 |

## 性能

| 指标 | 数值 |
|------|------|
| L1真实对话准确率 | ~90% |
| 功能测试准确率 | 100% |
| 查询延迟（缓存后） | ~20ms |
| 首次调用延迟 | ~11s（模型加载） |
| 内存占用 | ~403MB（含嵌入模型） |

## 技术文档

参见 [`ARCHITECTURE.md`](ARCHITECTURE.md)，涵盖：

- 逐层算法分析（含代码）
- RRF融合数学原理及其优于分数归一化的原因
- 置信度门槛设计哲学
- 故障模式矩阵与降级层级
- 延迟与内存剖析

## 文件结构

```
eagle-eye/
├── src/
│   ├── skill_retriever.py      # 核心5层检索引擎
│   ├── skill_synonyms.yaml     # 同义词词典（模板）
│   ├── plugin.py               # Hermes插件（pre_llm_call钩子）
│   └── plugin.yaml             # 插件清单
├── scripts/
│   ├── build_config.py      # 从本地技能自动生成配置
│   └── install.sh              # 一键安装脚本
├── templates/
│   └── hard_triggers.example.py  # 硬检测词格式参考
├── README.md                   # English文档
├── README_CN.md                # 本文件（中文）
├── ARCHITECTURE.md             # 技术深潜文档
├── CHANGELOG.md                # 版本历史
└── LICENSE                     # MIT
```

## 依赖

| 包 | 是否必需 | 用途 |
|----|----------|------|
| `jieba` | 是 | L2–L3中文分词 |
| `sentence-transformers` | 可选 | L4稠密嵌入（缺失时优雅降级） |
| `numpy` | 可选 | L4数值计算 |

## 贡献

欢迎贡献！特别需要帮助的领域：

- **触发词/同义词质量**：分享你的`_HARD_TRIGGERS`和`skill_synonyms.yaml`配置
- **嵌入模型基准测试**：测试替代模型并报告准确率
- **多语言支持**：扩展中英文之外的触发词和同义词
- **Bug报告**：模糊匹配中的边界情况、假阳性/假阴性

## 许可证

[MIT](LICENSE)
