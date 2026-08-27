# Knowlume

> Knowledge + lume/light — 照亮知识。

Knowlume 是一个 local-first 的个人知识系统：以可读、可迁移的 Markdown/YAML 保存长期知识，用稳定引用连接论文、网页、书籍和开源项目，并明确区分人的想法、可验证事实、AI 推论与观点演化。

## Current status

Phase 0R（Contract v2）已完成，Phase 1 是下一阶段。跨平台 Python package 与发布工程骨架已经建立，目前 `kb` 只提供版本、安装健康检查和显式更新检查；vault、笔记、迁移、capture、search 和 Web 功能仍按路线图逐阶段实现。

```text
Phase 0R  Contract v2                         Complete
Release   Python package foundation           Implemented
Phase 1   Vault, domain, parser, safe writes  Next
Phase 2A  Paper + Zotero                      Planned
Phase 2B  Web, Book, OSS                      Planned
Phase 3   SQLite projection and search        Planned
Phase 4   Read-only Web                       Planned
Phase 5   Automation and AI promotion         Planned
Phase 6A  Evolution and history               Planned
Phase 6B  Secure publishing                   Planned
Phase 7   Semantic, MCP, graph, multi-agent   Deferred
```

详细阶段门见 [roadmap](plan/roadmap.md)。

## Contract v2 in brief

- 程序仓库与个人 vault 分离；Markdown/YAML 是长期事实源，SQLite、缓存和 staging 可重建。
- Note 使用按需、带稳定 ID 的 `human | fact | ai | evolution` section，不再强制固定四章节。
- 无原始出处的个人笔记是一等场景：`role=human` 内容可以创建、搜索和公开，但必须表示为观点、想法或解释，不能冒充事实。
- Fact 逐块绑定一个或多个 Source 与类型匹配的 locator。
- AI 内容先进入私有 Artifact，经人工审核晋升后才能进入普通 Note。
- Relation 以 `relations/<from_id>.yaml` 独立分片保存。
- Contract v1 只读保留，用于历史验证和 v1→v2 迁移；后续 production 只创建和修改 v2。

语义从 [data model](plan/data-model.md) 开始阅读；机器约束以 [v2 schemas](schemas/v2/README.md) 和验收测试为准。

## Repository guide

| Path | Purpose |
|---|---|
| [schemas/v2/](schemas/v2/README.md) | 当前生产目标的对象、body、locator、relation 与 SQLite 契约 |
| [schemas/v1/](schemas/v1/README.md) | 只读历史契约 |
| [schemas/interfaces/](schemas/interfaces/README.md) | CLI envelope 与 migration report 契约 |
| [src/knowlume/](src/knowlume/) | 可安装 Python package 与当前已实现命令 |
| [templates/v2/](templates/v2/README.md) | 新内容模板 |
| [tests/fixtures/](tests/fixtures/) | v1 历史、v2 正反和迁移样本 |
| [plan/](plan/README.md) | 活动设计、ADR、迁移规范、路线图与历史归档 |
| [CLI.md](CLI.md) | 全部规划命令、实现方案、交付状态和验证证据 |
| [AGENTS.md](AGENTS.md) | 仓库工作与安全规则 |

根目录旧 `DESIGN_PLAN.md` 已退役；历史副本保存在 [plan/archive/design-baseline-v0.1.md](plan/archive/design-baseline-v0.1.md)。

## Local development

需要 Git、[uv](https://docs.astral.sh/uv/) 和 Python 3.13–3.14：

```powershell
uv python install 3.14
uv venv --python 3.14 .venv
uv sync --all-extras
```

当前可执行的发布诊断：

```powershell
uv run --no-sync kb --version
uv run --no-sync kb update-check
```

`doctor` 检查的是安装产物中的资源完整性，应在构建并隔离安装 wheel 后运行；editable 源码环境不会回退读取仓库资源。`update-check` 只有在显式调用时联网，并且不会安装更新。正式 PyPI 发布要等 Phase 3 gate；当前不要把本地构建误认为公开版本。

运行完整契约与文档链接检查：

```powershell
uv run --no-sync pytest -p no:cacheprovider
```

不在文档中手工维护测试数量；实际测试输出和 CI 是验收依据。

## Design navigation

- [Architecture](plan/architecture.md)
- [Data model](plan/data-model.md)
- [Sources and adapters](plan/sources-and-adapters.md)
- [Storage, index, and search](plan/storage-index-search.md)
- [Interfaces](plan/interfaces.md)
- [Security and publishing](plan/security-publishing.md)
- [Distribution and releases](plan/distribution.md)
- [Roadmap](plan/roadmap.md)
- [Accepted decisions](plan/decisions/)
- [v1→v2 migration](plan/migrations/v1-to-v2.md)

## License

Knowlume 使用仓库中的 [LICENSE](LICENSE)。
