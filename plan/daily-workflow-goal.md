# 科研日用闭环执行目标

> Status: Implemented — local engineering verified; exact-commit remote gate pending
> Baseline: `13d24131874dd694e6a2124bcde9a7d4eea6ab0a`, clean workspace
> Decision: [ADR-0019](decisions/0019-research-daily-workflow.md)

## 目标与范围

连续完成创建笔记、定位文件、编辑正文与引用、校验、刷新索引、检索与阅读。
在 Phase 5 与 6A 之间交付；命令归属仍由 [roadmap](roadmap.md)管理。
Note 字段与引用由 [data-model](data-model.md)、[v2 schemas](../schemas/v2/README.md)拥有；
参数与机器结果由 [interfaces](interfaces.md)及 [interface schemas](../schemas/interfaces/README.md)拥有。
Web 安全边界沿用 [ADR-0017](decisions/0017-phase4-local-read-only-application-backed-web.md)。

## 交付与退出条件

1. 四种 Note 创建支持安全标题与实际相对路径 JSON，默认文字输出兼容。
   19 个 JSON 命令的参数终止符、误消费标志及错误无副作用回归通过。
2. Note 正文和引用在审计字段之前；原生 details 无需 JavaScript。搜索命中直达稳定
   section，关系标题可读，正反向 section 所属正确，catalog 不逐条扫描。
3. 一份 [中文指南](daily-workflow-usage.md)走通两个 Literature、Idea 演化、Synthesis、
   有效 fact locator、关系、中英文检索及合成 Artifact 审核/预览/冲突拒绝。
   缺失、陈旧、不兼容、损坏、来源无效的索引恢复步骤清楚，Web 阅读零写入。
4. 完整 pytest、Ruff、mypy、文档链接、wheel/sdist 审计、源码目录外安装和既有生命周期
   检查通过；Windows/macOS/Linux × Python 3.13/3.14 CI 与 Package smoke 对应实际提交。
5. 真实试用另记两篇精确匹配 Zotero Paper、至少一份可恢复 PDF、重复采集、不可用路径
   和编辑器往返。只记录版本、结果与必要指纹，不记录私人正文或凭据。

## 非目标与依赖

依赖现有 Phase 1–5 服务、稳定 ID、事务、只读 Web 和 JSON 参数错误前置成果。
不实现 history、merge、supersede、发布、模型调用、语义检索、MCP、Web 写入。
不改变 Contract v2、envelope v1 或模板结构，无数据迁移；保留两份既有审视报告。

## 验收记录

- 本地工程：2026-10-08，Windows / Python 3.14.6 通过；证据如下。
- 远程平台：待用户提交并推送实际实现；不以旧提交成功替代。
- 真实 Zotero/PDF/编辑器试用：未完成，未提供测试条件；不等同于模拟适配器验证。

### 本地证据矩阵

| 交付/边界 | 执行证据 | 结果 |
|---|---|---|
| Note 创建结果与兼容性 | [Note 回归](../tests/test_daily_workflow_notes.py)、既有 [Phase 1](../tests/test_phase1_notes_cli.py) | 四类型、默认/中文/引号冒号标题、typed 序列化、实际路径、自定义 notes 布局、旧 create 返回 ID、文字 stdout 兼容 |
| 错误与副作用 | 同上及 [共享 JSON 参数回归](../tests/test_cli_json_arguments.py) | 19 命令库存；83 项共享回归通过；终止符/误消费/显式值/帮助兼容；标题在扫描前失败；缺 Source、无效引用零写入；事务冲突保留 Note/shard；刷新失败保留创建并仅报告 warning |
| 阅读与关系 | [Web 回归](../tests/test_daily_workflow_web.py)、[既有 Web 检查](../tests/test_phase4_web.py) | 正文→关系→details；原生 details 无 JS 依赖；搜索/正反向 section 链接；Artifact 审计标题；catalog 同次快照；CLI get 无新字段；浏览前后配置/vault/索引字节及 mtime 不变 |
| 恢复指引 | 同上与 [指南](daily-workflow-usage.md) | missing/stale build、incompatible/corrupt rebuild、source invalid 先 lint；同 vault 占位符，不显示绝对路径 |
| 单一离线闭环 | [注册 CLI 流程测试](../tests/test_daily_workflow_demo.py)及 [安装检查](../scripts/verify_installed_phase1.py)运行 [演示脚本](../scripts/daily_workflow_demo.py) | 新 vault，2 Paper/1 固定 commit 项目 Source，2 Literature、Idea→Concept、Synthesis≥2 关系；human/fact 编辑、校验、中英文检索、稳定 section；AI 查看/审核/预览/冲突拒绝、陈旧索引恢复实际完成 |
| 工程静态/完整检查 | pytest、Ruff `src tests scripts`、mypy `src tests scripts`、[内部链接测试](../tests/test_phase0_contracts.py) | 最终完整套件 809 passed / 3 skipped（平台条件跳过），另有既有 Starlette/httpx 弃用提示；38 项 Note 回归、7 项 Web 回归及单一离线闭环均包含在完整复验中 |
| 分发 | wheel/sdist 构建及 [verify_distribution](../scripts/verify_distribution.py) | 纯 Python wheel，资源与源文件字节相同；sdist 包含并核对指南、脚本、合成样例；输出位于 ignored `tmp/daily-workflow-20261008-dist/` |
| 源码目录外安装 | [Phase 1（含 2A/2B）](../scripts/verify_installed_phase1.py)、[Phase 3](../scripts/verify_installed_phase3.py)、[Phase 4](../scripts/verify_installed_phase4.py)、[Phase 5](../scripts/verify_installed_phase5.py) | 全部通过；core-only 标题/JSON/19 命令参数错误、离线演示、可选依赖、真实 HTTP Web section 跳转与正文优先；模拟集成不视为真实 Zotero |
| 生命周期 | [verify_install_lifecycle](../scripts/verify_install_lifecycle.py) | 安装、升级、降级、卸载保持 vault 不变 |

### 范围与剩余门禁

durable schemas/v2、templates/v2、公共业务规则、CLI get 结果、包版本/依赖及远程工作流配置
均未改变。两份历史审视报告未修改；没有操作个人 vault、调用模型或发布。
开发及本地验收期间未提交、推送；2026-10-08 用户明确授权提交本轮改动至 `origin/Phase5`
并核对远程 CI 与 Package smoke。远程结果尚待实际执行。
更改只补标题和创建定位、只读阅读、使用说明及其验收，既有命令阶段归属保留。

当前实现等待提交后的远程验收，**不宣告整个里程碑远程完成**。
提交并推送后，应在这里记录实际完整 SHA、CI 与 Package smoke 链接及
Windows/macOS/Linux × Python 3.13/3.14 六组合结果；不可沿用前置 JSON 修复的旧 SHA。
真实试用按 [指南第 7 节](daily-workflow-usage.md#7-真实试用清单当前未完成)另记。
