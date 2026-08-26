# Knowlume design and implementation plans

`plan/` 保存 Knowlume 的详细设计、决策记录和阶段实施计划。这里的文档用于解释系统为什么这样设计，以及后续应按什么顺序实现。

## Document authority

文档和契约的权威顺序如下：

1. `schemas/` 与验收测试：字段、枚举和边界的可执行契约。
2. `AGENTS.md`：开发者和自动化代理必须遵守的操作规则。
3. `plan/`：详细设计、设计理由、ADR 和路线图。
4. `README.md`：项目入口、快速开始和文档导航。
5. `plan/archive/`：历史基线，只用于追溯，不作为现行规范。

## Current documents

| Document | Status | Purpose |
|---|---|---|
| [`chapter-map.md`](chapter-map.md) | Active | 跟踪原始设计章节的目标文档与迁移状态。 |
| [`architecture.md`](architecture.md) | Active | 系统边界、依赖方向、逻辑分层和仓库布局。 |
| [`data-model.md`](data-model.md) | Active | 对象语义、身份、生命周期、provenance、section 和关系。 |
| [`sources-and-adapters.md`](sources-and-adapters.md) | Active | 来源保存、locator 语义和外部软件边界。 |
| [`storage-index-search.md`](storage-index-search.md) | Active | 持久化、Git、SQLite projection、索引和搜索。 |
| [`interfaces.md`](interfaces.md) | Active | CLI、机器输出、工作流和管理页面。 |
| [`security-publishing.md`](security-publishing.md) | Active | 信任边界、AI 隔离、隐私和公共发布。 |
| [`roadmap.md`](roadmap.md) | Active | 阶段、范围、非目标和验收门。 |
| [`decisions/0001-files-as-source-of-truth.md`](decisions/0001-files-as-source-of-truth.md) | Accepted ADR | 文件作为长期事实源。 |
| [`decisions/0002-record-status-and-workflow-stage.md`](decisions/0002-record-status-and-workflow-stage.md) | Accepted ADR | 对象状态与来源工作流分离。 |
| [`decisions/0003-locator-and-stable-sections.md`](decisions/0003-locator-and-stable-sections.md) | Accepted ADR | 来源专属 locator 与稳定 section。 |
| [`decisions/0004-no-claim-relations-in-v1.md`](decisions/0004-no-claim-relations-in-v1.md) | Accepted ADR | 第一版不引入 Claim 级关系。 |
| [`archive/design-baseline-v0.1.md`](archive/design-baseline-v0.1.md) | Frozen | `DESIGN_PLAN.md` v0.1 的逐字节历史副本。 |

## Planned active documents

活动设计文档已经按主题拆分完成，四个初始关键决策已记录为 Accepted ADR。

拆解期间，任何现行规则只能有一个权威位置；其他文档应通过链接引用，避免复制后产生分歧。
