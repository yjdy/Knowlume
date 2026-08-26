# Knowlume

> Knowledge + lume/light — 照亮知识。

Knowlume 是一个面向个人长期学习和知识演化的 local-first Knowledge Operating System。它以可读、可迁移的 Markdown/YAML 保存知识，用稳定引用连接论文、网页、书籍和开源项目，并通过统一的 `kb` 控制面服务人类、Web 界面和自动化工具。

Knowlume 关注的不是“收藏了多少资料”，而是持续回答：结论来自哪里、理解如何变化、哪些证据支持或反驳它、AI 内容是否经过确认，以及哪些知识可以安全公开。

## Current status

项目处于早期实施阶段：Phase 0 的数据契约、模板、正反 fixtures 和可执行验收测试已经完成；下一阶段是 production parser、不可变 domain model 和 filesystem scanner。

```text
Phase 0  Contracts and boundaries        Complete
Phase 1A Parser, domain, file scanner     Next
Phase 1B Read-only management UI          Planned
Phase 2  Capture and Zotero               Planned
Phase 3  SQLite FTS5 search               Planned
Phase 4  Controlled automation and AI     Planned
Phase 5  Evolution and publishing         Planned
Phase 6  Optional advanced capabilities   Deferred
```

详细阶段门和验收要求见 [`plan/roadmap.md`](plan/roadmap.md)。当前尚未提供可运行的 `kb` CLI 或 Web 服务。

## Core architecture

```text
Markdown/YAML + stable source references
                    |
                    v
               kb-core (Python)
          +---------+---------+
          |         |         |
          v         v         v
        CLI       Web UI   SQLite FTS5
          |
          v
   Codex / other harnesses

Adapters: Filesystem | Zotero | Obsidian | Git | Quartz
```

核心边界：

- Markdown/YAML 和稳定的原始资料引用是长期事实源。
- SQLite、缓存、派生内容和 public staging 都可重建或丢弃。
- CLI、Web 和自动化调用同一组应用服务。
- AI 产物与人类知识分离，所有新对象默认私有。
- 公共发布从显式 allowlist 构建隔离 staging，不直接过滤整个私有知识库。
- 先完成可靠文件层和 FTS，再评估 semantic search、MCP 与复杂 Agent 能力。

完整架构见 [`plan/architecture.md`](plan/architecture.md)。

## Local development

### Requirements

- [uv](https://docs.astral.sh/uv/)
- Git
- CPython 3.14 为主要开发版本
- CPython 3.13 为兼容目标
- CPython 3.14t 为测试目标；在测试矩阵落地前不宣称已经验证

项目元数据声明 Python `>=3.13,<3.15`。

### Prepare the environment

在仓库根目录执行：

```powershell
uv python install 3.14
uv venv --python 3.14 .venv
uv sync --no-install-project
```

当前生产包尚未建立，因此使用 `--no-install-project` 同步依赖。进入 Phase 1A 并创建 `src/kb` 后再切换为普通 `uv sync`。

激活环境（可选）：

```powershell
.venv\Scripts\Activate.ps1
```

### Run the contract tests

```powershell
uv run --no-sync pytest -p no:cacheprovider
```

当前基线：12 项 Phase 0 测试通过。测试覆盖 schema、状态拆分、来源 locator、稳定 section、关系目标、AI 默认边界和 public-to-private 依赖。

## Repository guide

| Path | Purpose |
|---|---|
| [`schemas/`](schemas/README.md) | 对象、locator 和关系的可执行 JSON Schema |
| [`templates/`](templates/) | Source、Note、Snippet 和 AI Artifact 模板 |
| [`tests/fixtures/`](tests/fixtures/) | 有效和无效契约样本 |
| [`tests/test_phase0_contracts.py`](tests/test_phase0_contracts.py) | Phase 0 可执行验收测试 |
| [`plan/`](plan/README.md) | 活动设计、路线图、ADR 和历史基线 |
| [`AGENTS.md`](AGENTS.md) | 开发者与自动化代理必须遵守的工作规则 |
| `src/kb/` | 计划中的 production Python 包；尚未创建 |

## Design documentation

| Topic | Document |
|---|---|
| 系统边界与分层 | [`plan/architecture.md`](plan/architecture.md) |
| 对象、状态、provenance 与关系 | [`plan/data-model.md`](plan/data-model.md) |
| 来源保存与外部适配器 | [`plan/sources-and-adapters.md`](plan/sources-and-adapters.md) |
| Git、SQLite、索引与搜索 | [`plan/storage-index-search.md`](plan/storage-index-search.md) |
| CLI、JSON 输出与 Web | [`plan/interfaces.md`](plan/interfaces.md) |
| AI、隐私和公共发布 | [`plan/security-publishing.md`](plan/security-publishing.md) |
| 阶段、非目标和验收 | [`plan/roadmap.md`](plan/roadmap.md) |
| 已接受的架构决策 | [`plan/decisions/`](plan/decisions/) |
| 原始设计迁移状态 | [`plan/chapter-map.md`](plan/chapter-map.md) |

字段、枚举和约束以 `schemas/` 与验收测试为准；设计文档负责解释语义和理由。历史原稿位于 `plan/archive/`，不作为现行规范。

## V1 scope

第一版聚焦文件事实源、来源捕获、CLI、SQLite FTS5、只读管理页面、AI 审核边界和受控发布。以下能力明确后置：vector database、RAG、semantic search 实现、MCP server、知识图谱、multi-agent memory、自研阅读器、浏览器插件和云同步服务。

完整范围与非目标见 [`plan/roadmap.md`](plan/roadmap.md)。

## Contributing

开始修改前请阅读 [`AGENTS.md`](AGENTS.md)。涉及 durable contracts 的变更必须同步更新 schema、模板、fixtures、测试和对应 ADR/设计文档。Phase 0 验收测试必须保持通过。

## License

Knowlume 使用仓库中的 [`LICENSE`](LICENSE)。
