# ADR-0019: 科研日用闭环

> Status: Accepted
> Date: 2026-10-08
> Decision: 用户批准完整日用闭环的实施计划

## Context

审视提案见 [roadmap proposal](../reviews/2026-10-04-roadmap-proposal.md)。现有创建、
编辑、校验、索引和阅读能力需要连成可操作的日常流程。实施基线为
`13d24131874dd694e6a2124bcde9a7d4eea6ab0a`，工作区干净；JSON 参数错误修复的
准确提交及跨平台证据保留在 [CLI 账本](../../CLI.md)。

## Decision

在 Phase 5 与 6A 之间增加命名里程碑“科研日用闭环”，不重新分配命令阶段。
[执行目标](../daily-workflow-goal.md)定义范围与门禁。

- `note new` 增加可选标题与 JSON。标题先校验，去除首尾空白，拒绝空白、换行和
  控制字符，固定安全诊断 `NOTE_TITLE_INVALID`，退出 2；扫描和写入前完成校验。
  用户标题只赋给已解析的 Note，再由现有序列化器渲染，文件名仍由 ID 决定。
- 保留 `NoteService.create()` 返回 ObjectId；`create_with_result()` 返回 ID 和实际写入
  相对路径，两者共用创建实现。Literature 沿用 Source 要求及可恢复事务。
- [interfaces](../interfaces.md)拥有参数与输出规则；新机器结果的字段只由
  [note-create-result v1](../../schemas/interfaces/note-create-result-v1.schema.json)拥有。
  这是新增结果与可选参数，envelope/interface v1、durable Contract v2 不变，无迁移。
  模板结构、对象 schema 和模板字段不变。
- Note Web 正文优先，审计详情使用原生 details。搜索链接使用已有 section ID。
  关系标题及 section 存在性取自 catalog 同次快照；反向关系的目标 section 属于当前对象。
  不修改 CLI get 的机器结果。缺失/陈旧索引显式 build，不兼容/损坏显式 rebuild，
  来源无效先 lint 和修正文件。恢复指令用 `<VAULT_ROOT>`，页面始终只读。
- 中文指南与离线样例全部是合成资料，包括 human 演示文本。模拟采集证据与真实
  Zotero、PDF 恢复、编辑器往返证据分开。真实条件未提供不阻塞工程交付，必须明确未完成。

## Consequences and boundaries

默认标题、非 JSON 的 ID stdout、业务错误码、警告、已有 AI/doctor 版本保持兼容。
新 JSON 命令复用既有参数错误处理；发现 vault 的错误也必须输出 envelope。
不新增默认 scope，不改变数据所有权、访问范围或事实/AI 要求。
不交付 history、merge、supersede、发布、模型调用、语义检索、MCP 或 Web 写入。
本次不提交、推送、发布或启动远程工作流；新实现的远程门禁只能绑定实际实现提交。
