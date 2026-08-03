# Hermes Skill Router — Hermes 技能路由插件

在模型调用前把大量技能收窄到相关的几个。**零核心改动**：仅用户插件 + `pre_llm_call`。

## 流程

- **L1 硬触发**：命中后注入强提示，并通过标准 `skill_view()` 加载技能
- **L2–5**：BM25 + 同义词 + HTTP 向量 + RRF → 只注入名称/描述提示
- 置信度低则静默；嵌入服务挂了仍可用 L1–L3

## 安装

```bash
python scripts/build_config.py
bash scripts/install.sh
hermes gateway restart
```

关闭：`HERMES_DISABLE_SKILL_RETRIEVAL=1`

嵌入地址写在 `~/.hermes/.env`，例如：

```
HERMES_EMBEDDING_BASE_URL=http://localhost:3001/v1
```

详见 [docs/embedding-server.md](docs/embedding-server.md) 与 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 依赖

`jieba` `numpy` `requests`

## 许可

MIT
