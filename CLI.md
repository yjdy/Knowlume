# Knowlume CLI inventory and delivery ledger

本文档记录所有已规划 `kb` 命令的用途、交付阶段、实现方案、当前状态和验证证据，用于每次 CLI 变更后的对比与验收。

> Last synchronized: 2026-09-03
> Contract baseline: Contract v2 / machine interface v1  
> Current delivery state: Phase 3 Complete and remotely verified

## Authority and update rules

- 命令语义和参数边界以 [`plan/interfaces.md`](plan/interfaces.md) 为准。
- 阶段归属和 gate 以 [`plan/roadmap.md`](plan/roadmap.md) 为准。
- JSON 输出和迁移报告以 [`schemas/interfaces/`](schemas/interfaces/README.md) 为准。
- 所有平台的 CLI stdout/stderr 均使用 UTF-8；机器输出与诊断继续严格分流。
- 本文档只负责库存、实现计划、状态和证据，不建立另一套业务规则。
- 新增、删除、重命名命令，或改变阶段、状态、JSON 支持情况时，必须在同一变更中更新本文档。
- 一个命令只有在实现完成、命令级测试通过且完整仓库测试通过后，才能标记为 `Verified`。

状态只使用以下值：

| Status | Meaning |
|---|---|
| `Planned` | 已规划，尚无可执行实现 |
| `In progress` | 已开始实现，但尚未满足阶段 gate |
| `Implemented` | 功能已实现，验证证据尚不完整 |
| `Verified` | 命令级测试和完整仓库测试均通过 |
| `Deferred` | 已明确后置，当前阶段不实现 |

## Release foundation

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `version` | `kb --version` | 显示 package、Contract、interface、projection 和 parser 版本 | `importlib.metadata` 与独立版本常量；不解析 vault | `Verified` | `tests/test_distribution_runtime.py`; isolated wheel smoke; complete suite |
| `doctor` | `kb doctor [--json]` | 检查 Python 兼容性、wheel 资源完整性和用户状态目录 | package resource checks；后续阶段扩展 vault/adapter probes | `Verified` | `tests/test_distribution_runtime.py`; isolated wheel smoke; complete suite |
| `update-check` | `kb update-check [--pre] [--json]` | 显式查询 PyPI 版本，不下载或安装更新 | stable/prerelease 选择、typed network failure、update-check-result v1 | `Verified` | `tests/test_distribution_runtime.py`; complete suite |

## Phase 1 — Vault and core

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `init` | `kb init PATH` | 初始化独立 vault、便携配置和必要目录 | Vault port、路径边界、原子配置写入 | `Verified` | `tests/test_phase1_vault.py`; complete suite |
| `scan` | `kb scan` | 扫描并解析 v2 对象、Note body 和 relation shards | Vault discovery、parser、semantic validation、scanner | `Verified` | `tests/test_phase1_scanner_cli.py`; complete suite |
| `status` | `kb status` | 汇总对象、工作流、健康和可用能力状态 | Scanner 结果上的只读 application service | `Verified` | `tests/test_phase1_scanner_cli.py`; complete suite |
| `lint` | `kb lint [--strict\|--changed]` | 报告契约、引用、provenance、关系和安全问题 | 类型化 findings；`--changed` 仅过滤完整扫描后的显示结果 | `Verified` | `tests/test_phase1_scanner_cli.py`; complete suite |
| `note.new` | `kb note new --type idea\|literature\|concept\|synthesis [--source SOURCE_ID]` | 从 v2 模板创建 Note；Literature 显式绑定 Source | Domain factory、稳定 ID/section、冲突安全写入 | `Verified` | `tests/test_phase1_notes_cli.py`; complete suite |
| `note.show` | `kb note show ID` | 按稳定 ID 显示规范化 Note | Object lookup、body parser、人类 renderer | `Verified` | `tests/test_phase1_notes_cli.py`; complete suite |
| `note.evolve` | `kb note evolve ID --to concept` | 将 Idea 原位演化为 Concept | 保留对象/section ID，追加 `type_history`，原子写入 | `Verified` | `tests/test_phase1_notes_cli.py`; complete suite |
| `relation.add` | `kb relation add FROM_ID TO_ID --type TYPE [--section SECTION_ID]` | 向来源对象分片增加关系 | 关系矩阵、canonical identity、分片所有权、冲突安全写入 | `Verified` | `tests/test_phase1_relations_cli.py`; complete suite |
| `relation.remove` | `kb relation remove FROM_ID TO_ID --type TYPE [--section SECTION_ID]` | 从来源对象分片删除关系 | 精确 canonical key 匹配、冲突检测、原子写入 | `Verified` | `tests/test_phase1_relations_cli.py`; complete suite |
| `relation.list` | `kb relation list ID` | 列出对象的正向及反向关系 | 读取所属 shard；反向关系由扫描结果派生 | `Verified` | `tests/test_phase1_relations_cli.py`; complete suite |
| `migrate` | `kb migrate --from 1 --to 2 [--dry-run\|--apply]` | 生成迁移报告并在无阻塞项时应用 v1→v2 | 默认 dry-run、版本化报告、禁止猜测、可恢复多文件事务 | `Verified` | `tests/test_phase1_migration_cli.py`; complete suite |

## Phase 2A — Paper and Zotero

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `inbox` | `kb inbox [--json]` | 列出等待处理的 Source | 按 `workflow_stage=inbox` 查询 durable files | `Verified` | `tests/test_phase2a_cli.py`; installed wheel smoke; complete suite; [CI](https://github.com/yjdy/Knowlume/actions/runs/33179444723) |
| `process` | `kb process SOURCE_ID --to STAGE [--json]` | 推进来源的阅读和整合工作流 | Source workflow service、相邻状态转换、冲突安全写入 | `Verified` | `tests/test_phase2a_sources.py`; `tests/test_phase2a_cli.py`; complete suite; [CI](https://github.com/yjdy/Knowlume/actions/runs/33179444723) |
| `source.list` | `kb source list [filters] [--json]` | 筛选和列出 Sources | Scanner-backed query 与稳定排序 | `Verified` | `tests/test_phase2a_sources.py`; `tests/test_phase2a_cli.py`; installed wheel smoke; [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33179444644) |
| `source.show` | `kb source show ID [--json]` | 显示 Source card 和恢复信息 | Source lookup、人类/JSON renderer | `Verified` | `tests/test_phase2a_cli.py`; installed wheel smoke; complete suite; [CI](https://github.com/yjdy/Knowlume/actions/runs/33179444723) |
| `source.open` | `kb source open ID` | 通过 adapter 打开原始材料 | Zotero recovery route、SHA-256 校验、typed unavailable error | `Verified` | `tests/test_phase2a_sources.py`; `tests/test_phase2a_cli.py`; complete suite; [CI](https://github.com/yjdy/Knowlume/actions/runs/33179444723) |
| `source.sync` | `kb source sync ID [--adopt-remote] [--accept-attachment-change] [--json]` | 从 Zotero 同步可更新元数据 | 字段所有权、durable baseline、身份/附件/写冲突检测 | `Verified` | `tests/test_phase2a_sources.py`; `tests/test_phase2a_cli.py`; complete suite; [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33179444644) |

## Phase 2B — Unified capture

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `add` | `kb add INPUT [--type paper\|web\|book\|repo] [--json]` | 自动识别并捕获四类 Source，显式类型只覆盖识别 | Unified router、canonical identity、duplicate check、type adapter、atomic write、add-result v1 | `Verified` | `tests/test_phase2b_cli.py`; complete suite; isolated wheel smoke; [CI](https://github.com/yjdy/Knowlume/actions/runs/33252123661); [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33252123610) |

### `kb add` type capability matrix

以下 ID 只跟踪内部 type backend，不是独立 CLI 命令。统一父命令在四条路径全部通过 Phase 2B gate 后才公开。

| Capability ID | CLI type | Durable source type | Delivery | Implementation plan | Status |
|---|---|---|---|---|---|
| `add.paper` | `paper` | `paper` | Phase 2A internal foundation; Phase 2B resolver | DOI/arXiv exact candidate search、itemType classification、Paper metadata and attachment recovery | `Verified` |
| `add.web` | `web` | `web` | Phase 2B | URL canonicalization、exact Zotero webpage and immutable HTML/XHTML snapshot evidence | `Verified` |
| `add.book` | `book` | `book` | Phase 2B | DOI/ISBN metadata、edition identity、Zotero mapping | `Verified` |
| `add.repo` | `repo` | `oss` | Phase 2B | configured Git host、isolated anonymous remote HEAD resolution、immutable commit、`license: NOASSERTION`；整体项目笔记复用 Literature Note | `Verified` |

## Deferred commands

| ID | Reserved command | Description | Reconsideration gate | Status | Verification |
|---|---|---|---|---|---|
| `snippet.add` | `kb snippet add` | Contract v2 Snippet 保持可读，但不提供创建入口 | 无期限延期且不归属任何阶段；仅在新的 accepted ADR 验证用例并冻结内容恢复、路径/行范围、许可证、发布审批、幂等和事务规则后重新规划 | `Deferred` | — |

## Phase 3 — Projection and search

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `grep` | `kb grep QUERY [--limit N] [--json]` | 不依赖索引搜索 durable files | trusted-local scanner/file search、relative path/ephemeral line、grep-result v1 | `Verified` | `tests/test_phase3_cli.py`; `tests/test_phase3_search.py`; local complete suite |
| `search` | `kb search QUERY [filters] [--scope trusted-local\|public-safe] [--limit N] [--json]` | 使用 SQLite FTS 和受控过滤搜索 | literal bilingual tokenizer、BM25、stable tie-break、search-result v1 | `Verified` | `tests/test_phase3_cli.py`; `tests/test_phase3_search.py`; isolated wheel smoke |
| `get` | `kb get ID [--json]` | 按稳定 ID 返回对象和可追溯内容 | scanner lookup、normalized body/citations/relations、get-result v1 | `Verified` | `tests/test_phase3_cli.py`; `tests/test_phase3_contracts.py`; local complete suite |
| `context` | `kb context QUERY --scope trusted-local\|public-safe [--limit N] [--max-chars N] [--json]` | 按显式 scope 组装可追溯上下文 | per-result dependency audit、grouping/budget、context-result v1 | `Verified` | `tests/test_phase3_cli.py`; `tests/test_phase3_search.py`; isolated wheel smoke |
| `index.build` | `kb index build [--json]` | 创建或增量更新 SQLite projection | checksums、change set、single transaction、index-result v1 | `Verified` | `tests/test_phase3_search.py`; `tests/test_phase3_cli.py`; local complete suite |
| `index.rebuild` | `kb index rebuild [--json]` | 从 durable files 确定性重建索引 | packaged v2 DDL、healthy snapshot、atomic database replacement | `Verified` | `tests/test_phase3_search.py`; distribution audit; Python 3.13/3.14 isolated wheel smoke |
| `index.status` | `kb index status [--json]` | 报告 projection 版本、新鲜度和错误 | missing/fresh/stale/incompatible/corrupt、index-result v1 | `Verified` | `tests/test_phase3_cli.py`; `tests/test_phase3_search.py`; local complete suite |

`search` filters are `--kind`, `--subtype`, `--visibility`, `--record-status`,
`--workflow-stage`, `--maturity`, `--review-status`, repeatable `--tag`, and `--role`. Default search
is trusted-local active Source/human/fact/snippet content with AI, archived, and superseded results
excluded. Default limit is 20 and maximum is 200. `context` requires scope, defaults to 12,000
characters, and excludes AI throughout Phase 3. Exact behavior and diagnostics are frozen by
[`ADR-0016`](plan/decisions/0016-phase3-deterministic-projection-search-context.md); every command
is registered and `Verified`. The complete Phase 3 inventory passed
[CI](https://github.com/yjdy/Knowlume/actions/runs/33300551834) and
[package smoke](https://github.com/yjdy/Knowlume/actions/runs/33300551847) on Windows, macOS, and
Linux with Python 3.13 and 3.14.

## Phase 4 — Read-only Web

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `serve` | `kb serve` | 启动 loopback 只读管理界面 | FastAPI/Jinja2/HTMX，共用 application services 和安全边界 | `Planned` | — |

## Phase 5 — Automation and AI

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `ai.list` | `kb ai list` | 列出待审核及已处理 AI Artifacts | Artifact query、默认私有过滤 | `Planned` | — |
| `ai.review` | `kb ai review ID` | 记录接受或拒绝的人工审核 | reviewer/time/action provenance、冲突安全写入 | `Planned` | — |
| `ai.promote` | `kb ai promote ID` | 将已审核 Artifact 晋升到普通 Note | promoted state、Note block、`promoted_from` 私有审计关系事务 | `Planned` | — |
`doctor` 的稳定命令入口已在 Release foundation 实现。Phase 5 只扩展 Git、SQLite、Zotero、vault 和外部 adapter probes，不新增第二个命令。

## Phase 6A — Evolution and history

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `related` | `kb related ID` | 显示规范化关联对象 | Relation scan/index、canonical symmetric relations | `Planned` | — |
| `backlinks` | `kb backlinks ID` | 显示指向对象或稳定 section 的关系 | Derived inverse relation query | `Planned` | — |
| `history` | `kb history ID` | 按稳定 ID 投影 Git 历史 | Git adapter、rename-aware object resolution、actor metadata | `Planned` | — |
| `note.merge` | `kb note merge SOURCE_ID --into TARGET_ID` | 合并重复 Note 并保留历史对象 | 多文件事务、关系重定向、source supersession | `Planned` | — |
| `note.supersede` | `kb note supersede OLD_ID --by NEW_ID` | 用新 Note 替代旧 Note | 同 kind 校验、`supersedes` relation、旧对象保留 | `Planned` | — |
| `tidy` | `kb tidy [--dry-run\|--apply]` | 规范结构，不改变知识语义 | deterministic formatter、差异预览、默认 dry-run | `Planned` | — |
| `organize` | `kb organize` | 提出重复、关系和综合建议 | suggestion-only analysis，不直接修改 durable knowledge | `Planned` | — |
| `review` | `kb review` | 报告阅读债务和维护建议 | health rules、稳定 finding codes、只读输出 | `Planned` | — |

## Phase 6B — Secure publishing

| ID | Command | Description | Implementation plan | Status | Verification |
|---|---|---|---|---|---|
| `publish.audit` | `kb publish audit` | 审计公共 allowlist 的完整依赖闭包 | dependency classification、fail-closed findings、manifest | `Planned` | — |
| `publish.build` | `kb publish build` | 构建隔离且原子的 public staging | audited manifest allowlist、atomic staging replacement | `Planned` | — |
| `publish.preview` | `kb publish preview` | 预览最近通过审计的公共构建 | staging-only publisher/preview adapter | `Planned` | — |

## Comparison and verification procedure

每次 CLI 相关变更按以下顺序更新和验证：

1. 对照 `plan/interfaces.md` 检查命令名称、参数和机器输出契约。
2. 对照 `plan/roadmap.md` 检查阶段和 gate，不在本文档独立调整阶段。
3. 更新对应行的 implementation plan、status 和 verification；保留稳定 ID，重命名时在变更记录说明。
4. 实现存在后，对比 `kb --help` 与各级 `--help`，确保没有未登记的命令或缺失的已规划命令。
5. 运行命令级测试和完整仓库测试；在 verification 中记录测试文件、CI job 或发布版本，不记录只能人工复述的成功声明。
6. 运行内部文档链接检查，确认本文档与权威文档仍可互相解析。

## Change log

| Date | Change | Comparison result |
|---|---|---|
| 2026-09-03 | 完成 Phase 3 projection/search/context | Feature commit `09c4a634a9fdf196dee0e7efe066ce3ab7eafd01` 通过跨平台 [CI](https://github.com/yjdy/Knowlume/actions/runs/33300551834) 与 [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33300551847)；release owner 已确认 PyPI Trusted Publisher 控制权，TestPyPI/PyPI prerelease gate 开放而 stable gate 保持关闭；未创建 tag、上传包或创建 GitHub Release |
| 2026-08-30 | 实现 Phase 3 projection/search/context | 七个命令、五个 result schemas、tokenizer v1、deterministic rebuild/incremental refresh、public-safe context、本地完整套件、分发审计和 Python 3.13/3.14 隔离 wheel smoke 已通过；远程完成门禁仍待执行，发布开关保持关闭 |
| 2026-08-29 | 冻结 Phase 3 projection/search/context 设计 | ADR-0016 与 `phase3-goal.md` 固定 state-directory SQLite、deterministic segments、standard-library bilingual n-gram、全部命令 JSON、trusted-local 默认和逐结果 public-safe 审计；命令仍为 `Planned` |
| 2026-08-29 | 完成 Phase 2B 统一 Source capture | `kb add` 四条 backend、Book edition/config 契约、Zotero 精确分类与 Web snapshot、匿名 Git HEAD、幂等/冲突写入和 OSS→Literature Note 已通过本地、分发、隔离安装及[跨平台 CI](https://github.com/yjdy/Knowlume/actions/runs/33252123661)；状态更新为 `Verified` |
| 2026-08-29 | 勘误 Phase 2A capture 边界并回补 CLI 验收 | Phase 2A 保持 Complete/Verified：内部 Paper capture 依赖可注入 metadata resolver，生产 DOI/arXiv Zotero 搜索归 Phase 2B；`tests/test_phase2a_cli.py` 直接覆盖 Source filters、open 成功、sync 审批参数、warnings 和主要 human/JSON 输出；ADR-0014 冻结完整公开诊断 |
| 2026-08-29 | 收紧 Phase 2B OSS 范围并无期限延期 Snippet 创建 | `add.repo` 仅捕获仓库根和远端 HEAD 的项目级 OSS Source；整体项目笔记复用已验证的 Literature Note；`snippet.add` 改为未分配阶段的 `Deferred`，现有 Contract v2 Snippet 仍可读 |
| 2026-08-28 | Phase 2A 跨平台最终门禁完成 | [CI](https://github.com/yjdy/Knowlume/actions/runs/33179444723) 与 [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33179444644) 覆盖 Windows/Linux/macOS × Python 3.13/3.14，Phase 2A 命令与内部 Paper capture 标记为 `Verified` |
| 2026-08-28 | 实现 Phase 2A Paper/Zotero vertical slice | 内部 capture、Source 查询/同步/工作流、JSON schema、wheel 审计和隔离安装通过；公共 `kb add` 保持未注册，跨平台 CI 待确认 |
| 2026-08-28 | Phase 1 跨平台最终门禁完成 | [CI](https://github.com/yjdy/Knowlume/actions/runs/33120979913) 与 [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33120979856) 覆盖 Windows/Linux/macOS × Python 3.13/3.14，所有 Phase 1 命令保持 `Verified` |
| 2026-08-27 | 建立跨平台 package 与 release foundation，新增 `--version`、`doctor --json`、`update-check` | 三个入口已实现；Phase 1–6 业务命令状态不变 |
| 2026-08-27 | 实现 `kb init PATH` 与根级 `--vault PATH` 契约 | `init` 命令级测试、Vault 边界测试与完整套件通过 |
| 2026-08-27 | 实现确定性 `scan`、scanner-backed `status` 与 `lint` | v2 正反 fixtures、关系/基数/引用、CLI 行为与完整套件通过 |
| 2026-08-27 | 实现 Note 创建、显示与 Idea→Concept 原位演化 | Literature 使用显式 `--source`；身份/section/body、冲突与完整套件通过 |
| 2026-08-28 | 实现 relation 操作与显式 v1→v2 迁移 | canonical shard、反向派生、dry-run/apply、崩溃恢复、安装包 CLI 冒烟与完整套件通过 |
| 2026-08-27 | 将四类 capture 入口统一为 `kb add INPUT [--type ...] [--json]` | 公共命令归属 Phase 2B；四类 backend 独立跟踪且保持 `Planned` |
| 2026-08-27 | 建立 Contract v2 CLI 全量库存与交付状态账本 | 与 active interfaces/roadmap 对齐；所有命令尚为 `Planned` |
