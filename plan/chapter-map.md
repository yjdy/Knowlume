# DESIGN_PLAN.md chapter migration map

本清单用于确保 `DESIGN_PLAN.md` 的内容在拆解过程中没有遗漏。`Pending` 表示目标文档尚未创建或该章节尚未迁移；`Complete` 只能在内容迁移、交叉引用和验收检查全部完成后设置。

2026-08-26 第二轮审计已按规范性要点逐章核对：18/18 章节覆盖完整，未发现未记录的语义冲突。状态维度拆分、v1 不支持 Claim 级关系、Phase 1 拆分和显式 context scope 均为已接受的细化，不计为迁移冲突；关键决策理由由 ADR-0001 至 ADR-0004 保存。

| 原章节 | 主要目标 | README/AGENTS 摘要 | 状态 |
|---|---|---|---|
| 1. 项目定位 | `architecture.md` | README 项目简介 | Complete |
| 2. 设计原则 | `architecture.md`、`decisions/0001-files-as-source-of-truth.md` | README 核心原则；AGENTS 操作边界 | Complete |
| 3. 总体架构 | `architecture.md` | README 简化架构图 | Complete |
| 4. 仓库和目录布局 | `architecture.md` | README 入口；AGENTS 目录规则 | Complete |
| 5. 统一数据模型 | `data-model.md` | AGENTS 核心字段规则 | Complete |
| 6. 来源类型和保存策略 | `sources-and-adapters.md` | README 支持的来源类型 | Complete |
| 7. 关系模型和知识演化 | `data-model.md`、`decisions/0003-locator-and-stable-sections.md`、`decisions/0004-no-claim-relations-in-v1.md` | AGENTS 关系目标规则 | Complete |
| 8. SQLite 可重建索引 | `storage-index-search.md` | README 核心架构原则 | Complete |
| 9. 三层搜索和 Codex 接入 | `storage-index-search.md`、`interfaces.md` | README 能力摘要 | Complete |
| 10. `kb` CLI 设计 | `interfaces.md` | README 快速开始；AGENTS 验证命令 | Complete |
| 11. Adapter 和外部软件边界 | `sources-and-adapters.md`、`architecture.md` | README 集成摘要 | Complete |
| 12. 管理页面 | `interfaces.md` | README 能力摘要 | Complete |
| 13. 安全、隐私和合规边界 | `security-publishing.md` | AGENTS 强制安全规则 | Complete |
| 14. 阶段化实施计划 | `roadmap.md` | README 当前阶段 | Complete |
| 15. 第一版明确不做 | `roadmap.md` | README 非目标摘要 | Complete |
| 16. 第一版核心命令范围 | `roadmap.md`、`interfaces.md` | README 快速开始 | Complete |
| 17. 验收清单 | `roadmap.md` 与可执行测试 | AGENTS 必跑验证 | Complete |
| 18. 最终目标 | `architecture.md` | README 长期愿景 | Complete |

## Completion checks

- [x] 18 个章节均有唯一的主要目标文档。
- [x] README 只保留项目入口和必要摘要。
- [x] AGENTS 只保留长期有效的操作规则。
- [x] 字段和枚举不在计划文档中复制定义，而是链接到 `schemas/`。
- [x] 所有内部链接有效。
- [x] Phase 0 契约测试通过。
- [ ] 根目录活动版 `DESIGN_PLAN.md` 完成退役。
