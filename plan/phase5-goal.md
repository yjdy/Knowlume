# Phase 5 execution goal: Local automation and auditable AI review/promotion

> **Status:** In progress — 三项审查问题已修复并完成本地验收；修复与完成记录的 Git 已授权，远程门禁待完成
> **Target branch:** `Phase5`（用户已在本地创建，继续使用该分支）
> **Inspected baseline commit:** `0961d17baee690170d749ddfc8c073f29ec2dfca`
> **Baseline state:** Phase 5 实施从上述提交开始；P5-C1～C9 已提交、推送并通过 feature 远程门禁
> **Feature evidence:** `3c03ccf8b13d2e484635ffa5cd4a02e9820f2f8a` — [CI](https://github.com/yjdy/Knowlume/actions/runs/34683929401) / [Package smoke](https://github.com/yjdy/Knowlume/actions/runs/34683929402)
> **Updated:** 2026-09-14
> **Execution boundary:** 已授权提交、推送本次修复；修复精确 SHA 远程全绿后，再提交、推送并验证完成记录；不创建 PR、不合并、不打 tag、不发布

## 1. 目标、基础与权威来源

Phase 5 将现有本地知识库推进到“脚本可调用、人工可审核、AI 内容可追溯晋升”的状态。
它复用 Phase 0R–4 的 Contract v2、parser/scanner、Note/Relation 写入、可恢复事务、
SQLite projection、显式作用域 context、CLI envelope、安装包资源与只读 Web。

本文拥有 Phase 5 的工作拆分、实施顺序与验收清单；阶段归属仍由
[`roadmap.md`](roadmap.md) 决定。现有机器契约和已接受 ADR 优先于本文中的候选设计。
正式实施时，M0 将候选设计落实为已接受决策和主题文档，M1 再落实机器契约。
不要把本文中提出的参数、诊断码、schema 名称误认为已发布接口。

实施前必须阅读：

- [`architecture.md`](architecture.md)：应用层复用、依赖方向、程序与 Vault 分离。
- [`data-model.md`](data-model.md)：AI Artifact、Note role、稳定 ID、input references、关系。
- [`security-publishing.md`](security-publishing.md)：人工审核、私有审计、scope、外发政策。
- [`interfaces.md`](interfaces.md)、[`CLI.md`](../CLI.md)：命令语义、机器接口、交付状态。
- [`storage-index-search.md`](storage-index-search.md)：事务、投影、默认检索和 context 排除规则。
- [`sources-and-adapters.md`](sources-and-adapters.md)：支持的外部接口与附件访问边界。
- [`distribution.md`](distribution.md)：wheel 资源、可选依赖、兼容性和远程门禁。
- [`ADR-0008`](decisions/0008-ai-promotion-and-publish-dependencies.md)：晋升与私有审计关系。
- [`ADR-0011`](decisions/0011-phase1-vault-and-transaction-contracts.md)：冲突与事务恢复。
- [`ADR-0016`](decisions/0016-phase3-deterministic-projection-search-context.md)：既有 context 与索引。
- [`ADR-0017`](decisions/0017-phase4-local-read-only-application-backed-web.md)：Web 保持只读。
- [`objects schema`](../schemas/v2/objects.schema.json)、
  [`Note body schema`](../schemas/v2/note-body.schema.json)、
  [`relation schema`](../schemas/v2/relations.schema.json)、
  [`interface schemas`](../schemas/interfaces/README.md)：字段与输出的机器权威。

工作区已有标为 Accepted 的 [ADR-0018](decisions/0018-phase5-local-revision-bound-ai-review.md)
及实现。规划交付后，当前开发目标已明确要求继续实施；现已另获阶段提交/推送授权，发布仍未授权。
执行时先核对现有改动与本目标的差距，复用正确成果，不从零重写；
本文的里程碑是完整验收范围，不表示每一项当前都尚未编码或已经完成。

## 2. 最终可以得到什么

### 2.1 用户交付结果

1. **本地 AI 工作队列。** 可列出、筛选和查看四种现有 Artifact，知道哪些未审核、已接受、
   已拒绝、已晋升，以及它们对应的模型、输入引用和人工审核记录。
2. **与内容版本绑定的审核。** 人工明确接受或拒绝某个已查看版本；内容或输入在审核后变化，
   旧决定不能继续授权新内容晋升。
3. **可恢复的晋升。** 将已接受的 Artifact 内容追加到明确指定 Note 的新 AI section，
   同一事务更新 Artifact、Note 和 Note 所有的 `promoted_from` 审计关系。
   重试不会重复插入，失败不会留下半个晋升结果。
4. **可用于脚本的本地工作流。** 新 AI 命令提供版本化 JSON；已有 `get`、`search`、`context`
   可直接组合，保留显式 scope、稳定引用、输出界限与 typed errors。
5. **更完整的诊断。** 保留安装级 `doctor`，按显式选择检查 Vault、SQLite、Git 和 Zotero，
   区分未选择、能力未安装、未运行、检查失败和健康。
6. **可安装的跨平台交付。** core-only 即可审核和晋升；可选能力缺失有明确诊断；
   Windows/macOS/Linux × Python 3.13/3.14 的完整测试和隔离安装验证通过。

### 2.2 一条完整的使用流程

本阶段的入口是已经存在于 Vault 的合法 Contract v2 Artifact。用户或外部工具依据
[`AI Artifact 模板`](../templates/v2/ai-artifact.md) 在配置的 AI 目录中准备私有、未审核文件，
保留真实模型、生成工具、输入对象/section 引用，随后执行扫描校验。
接入说明必须提供可以完整复现的样例，不能只让开发者手改 `review_status` 演示晋升。
程序内不新增 Artifact 生成、导入或模型调用命令；这也不授权任何外部工具读取或发送私有数据。

下列调用形式已实现并通过 feature 阶段门禁；大写变量需替换为实际值。
可复现的合成样例与脚本说明见 [phase5-usage](phase5-usage.md)：

```text
kb --vault VAULT ai list --review-status unreviewed --json
kb --vault VAULT get ARTIFACT_ID --json
kb --vault VAULT ai review ARTIFACT_ID --decision accepted --reviewer HUMAN_ID --expect-checksum ARTIFACT_CHECKSUM --json
kb --vault VAULT get ARTIFACT_ID --json
kb --vault VAULT get NOTE_ID --json
kb --vault VAULT ai promote ARTIFACT_ID --into NOTE_ID --section SECTION_ID --actor HUMAN_ID --expect-artifact-checksum ACCEPTED_CHECKSUM --expect-note-checksum NOTE_CHECKSUM --dry-run --json
kb --vault VAULT ai promote ARTIFACT_ID --into NOTE_ID --section SECTION_ID --actor HUMAN_ID --expect-artifact-checksum ACCEPTED_CHECKSUM --expect-note-checksum NOTE_CHECKSUM --apply --json
kb --vault VAULT doctor --probe vault --probe sqlite --json
```

用户通过已有 `note new` 与编辑器准备包含 human section 的目标 Note；Phase 5 不自动替用户写
“人工结论”。审核后重新读取 Artifact，是因为审核会改变文件 checksum。
`--dry-run` 与 `--apply` 互斥；晋升未指定二者时默认 dry-run。预览只产生结果，不创建计划文件、
锁、事务或索引；apply 重新读取、检查并构造事务，不能盲目重放旧预览。

### 2.3 范围与非目标

| 范围内 | 不在本阶段内 |
|---|---|
| `ai list/review/promote` 与既有 `get` 的组合 | `ai generate/import`、模型供应商 SDK、自动写笔记 |
| 本地 JSON、已有显式 scope context 的组合与回归 | 模型网关、私有内容外发、release-policy 执行器、HTTP JSON API、MCP |
| 已接受内容作为 `role=ai` 晋升 | 自动变成 Fact/human，自动执行 relation candidate |
| 安装级与显式 Vault/adapter `doctor` probes | 自动修复、数据库重建、Zotero 写入、下载附件 |
| 既有只读 Web 对新数据的兼容性 | Web 审核按钮、POST 写入、登录、CSRF、Artifact 详情路由 |
| 同步分发与跨平台验收 | 版本发布、tag、TestPyPI/PyPI 上传、GitHub Release |

定时调度、后台 watcher、PDF/OCR/论文解析、语义/vector/hybrid search、图谱、Snippet 创建、
Phase 6A 演化工具与 Phase 6B 发布也不属于 Phase 5。
`relation_candidate` 可被查看和人工审核；若晋升，仅将其候选文字保留为 AI 内容，
不得解析并执行其中的命令或直接创建其提议的可信关系。

## 3. 不能漏掉的设计要求

### 3.1 Artifact 查询与现有数据入口

- 复用 scanner 和 `get_object`；列表、详情、审核与晋升不依赖 SQLite。
- `ai list` 默认 active + unreviewed，提供 `--review-status`、`--type`、`--status`、
  `--limit`、`--offset` 与 `--json`。全状态选择使用明确的 `all`；不增加新的 durable enum。
- 排序按 created 升序、ID 升序；默认 limit 50、范围 1–200，offset 为非负整数。
  JSON 返回总数和有效过滤条件；空列表成功，非法参数失败，损坏文件不伪装成空队列。
- 列表只输出审核所需摘要和相对位置，不输出正文、prompt 内容、附件、凭据或绝对路径；
  正文由显式 `get ID` 读取。两者都是 trusted-local 操作，不表示可发送给外部模型。
- 读取所有既有 Artifact 类型与审核状态；遇到缺少新证据的旧对象，应准确显示兼容性状态，
  不能仅因缺少 Phase 5 扩展字段就使整个旧 Vault 不可读取。

### 3.2 审核状态机与人工归因

| 当前状态 | 操作 | 结果 |
|---|---|---|
| unreviewed | 人工 review accepted / rejected | 写入决定、审核人、带时区时间及审核证据 |
| accepted | 同决定、同审核人、内容与证据一致的 review | 幂等成功，保留原时间与字节 |
| rejected | 同决定、同审核人、内容与证据一致的 review | 幂等成功，保留原时间与字节 |
| accepted | 显式 promote，全部前置条件满足 | Artifact、Note、审计关系一起提交，状态 promoted |
| promoted | 同一目标/section、结果完整的 promote 重试 | 返回既有结果，不插入第二份内容 |
| 其他转换或证据不一致 | review / promote | typed refusal，零 durable 写入 |

- 不允许 unreviewed/rejected 直接晋升，也不允许 promoted 回退、改审核人或原地改写来源。
- 需要修改已审核候选时，准备一个新 ID 的 unreviewed Artifact，保留旧 Artifact；
  本阶段不提供撤销、重开审核或批量自动接受。
- `--reviewer`、`--actor` 必须显式且非空，写入 human 归因；不使用模型名称、Git 用户或系统默认
  偷填人工身份。二者可以不同，保留“谁审核”和“谁执行晋升”两条记录。
- 本地调用者提供的身份是审计声明，不是身份认证或签名；文档不得声称能够证明真人身份。
- 用户给出的 expected checksum 对应已查看的完整 Artifact/Note 版本，写入前再次比较。
  网络或进程中断后的旧 checksum 重试可以返回冲突；调用者读取当前结果后判断是否已成功，
  不得通过忽略旧 checksum 来实现所谓幂等。

### 3.3 审核内容、输入版本与兼容性

现有 Artifact 字段能表达审核人和时间，但不足以检测“审核后正文被编辑”或记录晋升目标。
M0/M1 必须补足**持久的、带版本的审核快照与晋升记录**，不能只存 SQLite、日志或事务目录。
精确字段由 schema 拥有，本文不复制字段表。

建议采用 Contract v2 的可选 provenance 扩展：旧文件继续可读，新 review/promote 操作必须写入
完整证据。扩展需要显式兼容性决策，不能把“新程序可读旧文件”宣称为“旧程序可读新文件”。
旧 schema 使用 `additionalProperties: false`；旧程序可能拒绝扩展后的对象。
M0 必须记录该影响，明确新增证据的独立版本、parser 版本与索引失效策略；
M1 提供旧数据、新数据和不支持版本的可执行用例。对象主版本仍按仓库生产规则保留 v2；
若最终设计需要不同主版本，须先修订本目标及版本决策，不能在实施中静默变更。

审核快照至少覆盖：

- Artifact ID、正文、类型、生成工具、模型、prompt 引用与 input references；
- 明确版本的规范化与 SHA-256 算法，排除审核快照自身与后写入的晋升字段，避免自引用 hash；
- 审核时每个实际输入对象的完整文件 checksum，以及被引用稳定 section 的存在性；
- 参与输入验证的关系 shard/依赖读取版本，足以在提交前发现相关变化。
- Snippet 的 `source_id` 即使没有可选 `snippet_from` shard，也必须展开并纳入上述版本与活动状态校验。

具体规范化算法、空输入、重复引用、引用循环、已归档/被 supersede 输入和语义等价换行的行为
在 M0 冻结、M1 用 fixtures 固定。建议新审核允许合法的空 `input_refs`，但不得据此生成 Facts；
有输入时只接受可解析、active、未 supersede 的引用，循环和缺失引用拒绝。
审核时采集的输入版本只证明本次审核绑定的本地版本，不证明模型生成时使用了相同版本；
缺少生成时版本证据时必须保留这个事实，不能根据当前文件反推历史。
prompt_ref 仅作安全相对引用，不跟随它读取任意文件；禁止 traversal、绝对路径和链接逃逸。

兼容性流程：

- 旧 unreviewed Artifact：正常人工审核后获得新证据。
- 旧 accepted Artifact：保持可读，但不能直接晋升；显式重新 review accepted 当前版本，
  原审核人/时间保存在新增的历史证据中，本次审核使用当前人工声明与时间。
- 旧 rejected/promoted Artifact：保持读取和现有检索语义，不自动补造内容 hash、输入历史或目标。
  缺少足够映射的旧 promoted 对象不能借此命令再晋升或被当成已完成的同目标重试。
- 已有 public AI Note 及其私有 audit edge 继续按已接受契约读取；新写入的增强要求不追溯破坏旧 fixtures。
- 新证据版本未知或证据损坏：保留文件，阻止受影响写入并报告可操作诊断。
- 安装、升级、降级、卸载和只读命令均不迁移对象；不宣称包降级可消除已写入的扩展字段。

### 3.4 晋升对象、内容与事务

- `--into` 必须指定现有、active、private Note；本阶段拒绝直接写 public Note，
  不更改目标 visibility。以后显式公开的资格仍归既有 public-safe/Phase 6B 规则判断。
- `--section` 指定一个全新的稳定 AI section ID。已有 section 冲突时拒绝；
  唯一例外是已经完成且证据完全匹配的同次晋升重试。
- 保留 Note ID、类型、maturity、全部已有 section ID、human/fact/evolution 正文与既有关系；
  只追加本次 AI section，按既有写入规则更新必要 metadata。Note 必须保有 human section。
- 晋升全份已审核 Artifact 正文，不暗中摘要、改写、选段、推断引用或改变 role。
  引用 Artifact 的 metadata 必须邻接每个生成的 AI block，并通过现有 Note parser 验证。
- 嵌入的 `knowlume` 结构标记、伪造 metadata、frontmatter、特殊 Markdown 与代码围栏必须有
  明确拒绝或无歧义序列化规则；不能让 Artifact 文本伪造 human/fact section。
  完成条件是内容忠实且 round-trip 后每块仍为 AI，不是“字符串拼接看起来正确”。
- 多文件提交包含 Artifact 的 promoted 状态与晋升记录、目标 Note、
  `relations/<note_id>.yaml` 中唯一的 `promoted_from` 关系。
  审核人/时间保留，晋升 actor/time 与目标 Note/section 单独持久记录。
- 保存输入引用、模型和生成工具；Artifact 始终 private 且不删除。审计关系不自动复制其正文、
  prompt 或附件到 public 输出。
- 提交前验证完整候选对象图，并重新确认 Artifact、Note、relation shard 与所有已读取依赖。
  对只读依赖的校验必须覆盖至提交边界；若既有事务能力不足，在 M0/M1 冻结必要扩展，
  不得把依赖伪装成需要重写的对象。
- 使用既有可恢复事务设施；在任一替换阶段失败均能恢复到原状态，恢复再次中断也可重试。
  重试所需业务证据来自 durable 数据，不依赖被清理的 transaction ID 或 SQLite。
- 已完成重试校验本次晋升记录及提交后结果，不机械重用提交前输入 checksum；
  特别覆盖目标 Note 本身也是 input_ref 的场景，区分本次合法追加与后续人工编辑。
  后续编辑造成结果不一致时明确报冲突，不覆盖编辑或重新追加。
- mutation 成功后使用现有 best-effort index refresh；刷新失败保留成功写入及明确警告，
  后续搜索按既有 stale 规则拒绝服务，不回报假失败诱发重复晋升。

### 3.5 自动化、JSON 与作用域

- 新 AI 命令使用既有 envelope v1，成功、空结果、dry-run、幂等、拒绝、冲突均有版本化 data
  和 golden output；stdout 只输出一个 UTF-8 JSON 文档，诊断不混入 stdout。
- 为 AI list/review/promote 增加各自 result schema；不得把任意 dict 当成稳定接口。
- 参数错误在 `--json` 模式下也应具有机器可解析诊断；进程退出码与 envelope 一致。
  AI 新错误覆盖参数、对象缺失/类型、状态、审核证据、目标冲突、输入变化与 capability，
  复用已有 Vault/索引错误，不重复发明第二套同义码。M0 冻结名称与 0–6 退出语义。
- 自动化交付是一条经过测试的“context/get → 人工 review → dry-run → apply → get 验证”流程，
  包含拒绝、冲突重读与幂等分支；脚本不能自行填写 accepted 或绕过人工决定。
- `context --scope trusted-local|public-safe` 的必填规则、预算、引用和类型不变；
  context 继续不输出 AI 内容，包括 promoted AI。默认 search 继续排除 AI；显式本地 AI 查询
  不绕过 Note block 的晋升要求。这里是复用和回归，不重复实现 Phase 3。
- scope 是内容访问范围，不是外发许可；trusted-local JSON 可能含私有正文，调用者不能因
  `--json`、工具名称或输出到管道就扩大权限。本阶段不发送内容到模型、不读附件正文，
  不把 public-safe context 称为发布认证或外发 release policy。

### 3.6 扩展 doctor，同时保留旧入口

候选参数为 `kb [--vault VAULT] doctor [--probe vault|sqlite|git|zotero]... [--json]`。
可重复选择，去重后按固定次序输出；不加入含义不清的自动 all-probes 模式。

- 不传 `--probe` 时维持既有安装级行为及 report v1，包括不解析 Vault、不联网、不创建用户目录。
  旧报告中的 `user_paths` 是已有本地诊断字段；不能在同一版本下静默删除。
- 显式 probe 使用新 report v2，独立结果 schema；维持 envelope v1 与命令名 doctor。
  v2 输出不回显绝对路径、凭据、私有正文、完整远端响应或环境值。
- vault：配置/可读性、扫描 findings 与待恢复事务检查；只报告，不创建、不修复、不恢复。
- sqlite：标准库 SQLite/FTS 能力与已选 Vault 索引状态；能力试验只在内存中进行，
  缺少索引时报告缺失，绝不创建文件、WAL、journal 或执行 rebuild。
- git：本地可执行文件可用性/版本与必要只读环境信息；有超时，不联网、不调用 credential helper、
  不 commit/pull/push，不将 Git 设为 AI review/promote 的运行前提。
- zotero：仅在显式选择时通过现有支持的 loopback Local API 作最小只读探测；
  懒加载可选依赖，超时且不下载附件、不读取私有 SQLite，不要求用户打开 Zotero 才能审核 AI。
- 必须区分 skipped、unavailable、failed 与 passed，不把“未选择”显示为成功检查；
  缺少可选依赖仅在显式请求对应能力时使该 probe 不通过。
- v2 聚合完整检查结果，明确“报告成功生成”与“所有检查健康”的不同含义；
  M0 冻结失败严重级别、退出码优先级与 envelope/data 对应关系，并保持默认 v1 兼容。
- 仅覆盖当前已有外部 adapter，预留可测试扩展位置，不创建模型供应商、Quartz 或云端探测器。

## 4. 里程碑与工作步骤

顺序执行 M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9。
下列 Git checkpoint 是独立回滚边界。用户已明确授权 P5-C1～C9 提交/推送，
并授权在 feature 远程检查通过后提交、推送和验证 P5-C10；不重复索要同一授权。

### 里程碑总览

| 步骤 | 主要交付 | 核心限制 | 进入下一步的完成条件 | 计划 Git 提交 |
|---|---|---|---|---|
| M0 | 基线核对、范围与兼容性决策、主题文档 | 不把计划当成开发或 Git 授权 | 接口、版本、状态机无关键未决项 | P5-C1，已授权 |
| M1 | schema、模板、正反样例、契约测试 | 先契约后实现；不改历史 v1 | 新旧样例与版本拒绝测试通过 | P5-C2，已授权 |
| M2 | Artifact 列表、读取、接入说明 | 无模型调用、无 SQLite 依赖；读取零写入 | 模板到 scan/list/get 流程与查询边界通过 | P5-C3，已授权 |
| M3 | 人工接受/拒绝与版本绑定证据 | 不自动接受、不伪造身份或历史 | 状态机、旧数据重审、冲突和幂等通过 | P5-C4，已授权 |
| M4 | 晋升预览、应用、多文件恢复 | 私有 Note、新 AI section；不得改成 human/fact | 三文件一致、故障恢复、正文保留、重试通过 | P5-C5，已授权 |
| M5 | JSON 与可复现脚本工作流 | 显式人工决定与 scope；不外发内容 | 成功、拒绝、冲突、重试及作用域回归通过 | P5-C6，已授权 |
| M6 | vault/sqlite/git/zotero 只读诊断 | 未选择不探测；不自动修复 | 默认兼容、错误分类、超时与零写入通过 | P5-C7，已授权 |
| M7 | 安全与 Phase 0R–4 集成验收 | 不放宽旧门禁、不使用私人测试数据 | 完整测试、静态检查和对抗用例通过 | P5-C8，已授权 |
| M8 | 包资源审计、隔离安装、CI 接入 | 不发布；源码运行不能代替安装测试 | 本地完整门禁和新旧安装验收通过 | P5-C9，已授权 |
| M9 | 精确提交的远程门禁与完成记录 | 必须有推送授权；不自动合并或发布 | feature/completion 两次矩阵通过、远端一致 | P5-C10，已授权，先通过 feature 门禁 |

每一步的详细要求、限制、完成条件和建议 commit message 见下文。
本次规划交付本身**无需 Git 提交**。执行时未获 Git 授权，可继续完成 M0–M8 的本地工作，
将提交节点记为待办；不能因此跳过 M9 后声称阶段完成。

### M0 — 冻结范围、行为和版本决策

**要求**

- 核对实际 Phase5 基线、工作区与 Phase 4 完成证据；保留无关用户工作。
- 审阅本目标并核对现有 ADR-0018；缺失时先形成决策：固定审核状态机、内容快照、旧 Artifact 兼容处理、
  目标 Note 约束、事务读集合校验、JSON/doctor 版本和诊断规则。
- 把第 3 节候选参数和算法落实到 interfaces、data-model、security、storage、distribution
  等各自 owner；同步 roadmap、plan README、chapter-map 和 CLI ledger。
- 写清 Artifact 模板入口、无模型调用范围、人工声明边界，以及失败/重试的使用流程。

**限制**

- 仅设计和导航文档；不写 production code、schema、fixtures、lockfile 或 CI 实现。
- 不把计划文档或先前 Phase 4 的授权视为 Phase 5 ADR 已接受或 Git 已授权。
- 不保留会影响机器接口或 durable 写入的未决设计后进入 M1。

**完成条件**

- 设计得到明确接受；每项行为有唯一 owner，无契约冲突，兼容性影响和非目标清楚。
- 文档链接检查通过；AI 命令保持 Planned，旧 doctor 的 Verified 状态不冒充新 probes 已验证。

**Git commit:** Yes — P5-C1 `docs: freeze phase 5 automation and ai review design`

### M1 — 先落实契约、模板、正反样例与验收测试

**要求**

- 按已接受版本决策扩展 v2 Artifact provenance；必要时对事务读集合能力作独立版本决策。
- 按“决策与迁移影响 → schema → 当前模板 → valid/invalid fixtures → 可执行契约测试”实施。
- 增加拟定的 `ai-list-result-v1`、`ai-review-result-v1`、`ai-promote-result-v1`、
  `doctor-result-v1`、`doctor-result-v2` schema；v1 doctor 准确描述已有报告，不能借此重定义它。
- 覆盖四种 Artifact 类型、四种审核状态、新旧对象、合法空输入、引用异常、快照损坏、
  不支持证据版本、非法状态转换、输出失败分支，以及旧 promoted public Note 的兼容案例。
- 固定哈希规范化、输入版本、身份/时间、目标映射和幂等结果的测试向量。

**限制**

- 不修改 v1 历史资产，不新建 Claim 或其他领域对象，不独立修改 parser 规避 schema。
- 此里程碑不注册未完成命令；契约测试必须可运行，不以全体 skip 作为通过。
- 不把旧 reviewed 对象缺少的新证据自动补写成已验证事实。

**完成条件**

- 新旧正样例通过，反样例按预期拒绝；机器输出版本与文档一致。
- 当前模板符合扩展契约，既有 v2 样例仍可读，所有迁移/兼容分支有验收用例。

**Git commit:** Yes — P5-C2 `feat(contracts): define phase 5 review provenance and machine results`

### M2 — Artifact 读取、列表与接入流程

**要求**

- 同步 domain/parser/serializer 支持 M1 的可选新证据且保留旧文件行为。
- 建立共享 AI 应用模块，提供 scanner-backed 查询，复用已有 get，不增加第二套文件解析。
- 实现 `ai list` 与 JSON、过滤、排序、分页、兼容性提示和 typed input failures。
- 提供模板接入教程和合法私有样例，演示准备 Artifact → scan → list → get。

**限制**

- 无外部模型、无网络、无 SQLite 依赖、无静默写入或目录创建。
- 不实现 review/promote 的假成功占位，不自动接受外部工具写入的状态声明。

**完成条件**

- 空/正常/不健康 Vault、四种状态/类型、分页边界、新旧对象均有命令级证据。
- get 可查看审核所需正文、引用和 checksum；读操作的 Vault/state 零写入验证通过。
- focused tests、Ruff、mypy 通过，CLI ledger 与实际实现一致。

**Git commit:** Yes — P5-C3 `feat(ai): add local artifact queries and intake guidance`

### M3 — 与已查看版本绑定的人工审核

**要求**

- 实现 `ai review` accepted/rejected、显式 reviewer、expected checksum、快照与输入版本验证。
- 原子保存人工决定和审核证据，保留 Artifact 内容、模型、生成工具和私有属性。
- 实现兼容旧 accepted 的显式重新审核流程，并保存旧审核归因。
- 输出成功、no-op、状态拒绝、证据损坏、内容冲突和输入失效的版本化结果。

**限制**

- 不晋升、不创建 Note、不执行候选关系；不得自动生成 reviewer 或回填未知历史。
- 内容、输入、锁或路径冲突时不能有 partial write；审阅后变更不能沿用旧证据。

**完成条件**

- 所有状态转换正反例、原 checksum 失效、输入变化、并发编辑、同决定幂等与旧数据重审通过。
- 拒绝路径保持 durable 字节不变；同决定 no-op 保留原时间；新决定能从文件重新读取验证。
- focused tests、Ruff、mypy 与命令 ledger 更新完成。

**Git commit:** Yes — P5-C4 `feat(ai): bind human review to artifact and input revisions`

### M4 — 预览、晋升与多文件恢复

**要求**

- 实现 promote 默认 dry-run 和显式 apply，显示目标、计划追加 section、影响文件与前置条件。
- 通过应用模块构造候选对象图，验证 Section/AI block、input references、关系 cardinality。
- 一次事务提交 Artifact、Note、relation shard；持久记录晋升 actor/time、目标映射与结果证据。
- 覆盖同目标幂等、不同目标拒绝、现有 section 冲突、旧 promoted 证据不足和索引刷新警告。

**限制**

- 只写明确指定的 private Note 和其 shard；不改变既有知识角色、不重写其他 Note、不外发。
- accepted 检查不能仅看 enum；必须验证快照和输入版本。
- dry-run 不能创建锁/事务/索引；apply 不能执行旧预览中未经重验的写入。

**完成条件**

- 每个多文件替换阶段的故障注入、进程中断、恢复再中断和恢复后重试均通过。
- 成功后 Artifact/Note/relation 三方一致；失败恢复原字节；重复 apply 不重复 section/关系。
- Markdown round-trip 不能伪造 human/fact；既有 Note 正文和稳定 ID 保留。
- 删除 SQLite 后仍能读取晋升证据；索引失效不破坏 durable 成功结果。

**Git commit:** Yes — P5-C5 `feat(ai): promote reviewed artifacts with recoverable transactions`

### M5 — 自动化组合与 scope 回归

**要求**

- 完成新命令全部 JSON 分支与 golden fixtures，使用既有 envelope 和退出码约定。
- 编写并自动验证本地端到端脚本示例：取得 context/get、接收明确人工决定、审核、预览、晋升、
  检查输出；附拒绝、冲突重读和已完成重试示例。
- 验证 Phase 3 context/search/get 与新审核状态和 provenance 的兼容性。
- 明确 trusted-local 数据不能由自动化隐式外发，public-safe 不代表发布许可。

**限制**

- 不重建 context/search 引擎，不扩大 context 的内容类型，不新增 schedule/MCP/模型客户端。
- 不把 pipeline 默认值或 AI 自己的输出作为人工接受动作。

**完成条件**

- 缺 scope、私有依赖、未晋升 AI、promoted AI、超预算、陈旧索引等用例保持既有契约。
- stdout/stderr、UTF-8、非交互错误、JSON schema 和退出码在命令级验证。
- 本地示例无需网络、凭据、个人 Vault 或手动改 promoted 字段即可复现完整工作流。

**Git commit:** Yes — P5-C6 `feat(automation): compose scoped context and ai review workflows`

### M6 — 显式、只读的 doctor probes

**要求**

- 扩展既有 doctor，落实默认 v1/显式 probes v2、固定检查顺序、健康汇总和退出码。
- 实现 vault、sqlite、git、zotero 检查，复用现有能力，设置超时并清理子进程。
- 使用可替换的检查入口注入时钟、进程或 Zotero 响应；不得使 domain 导入可选包。

**限制**

- 默认命令无新增网络/Vault 扫描；未请求的探测不能自行执行。
- 所有 probe 只读，不修复事务、不触发 index refresh、不安装依赖、不启动 Zotero、不读附件。
- 不要求 Git 或 Zotero 可用才能运行本地 AI 工作流。

**完成条件**

- 原 doctor 回归通过；每个 probe 的正常、缺失、拒绝、超时、失败和 skipped 语义可验证。
- core-only 缺少 Zotero extra 返回 typed capability，而 import/help/其他命令正常。
- 默认与 probes 执行的 Vault/state/cache/config 字节和目录清单无非预期变化。

**Git commit:** Yes — P5-C7 `feat(doctor): add explicit read-only vault and adapter probes`

### M7 — 对抗性与跨阶段集成验收

**要求**

- 覆盖第 5 节检查表；重点验证伪造审核、缺失输入、复用旧 checksum、已接受正文替换、
  输入/关系并发变化、目录/链接逃逸、恶意 Markdown 和被篡改事务。
- 生成工具归因、审核与晋升记录在 parser、scan/lint、get、index rebuild、显式 AI search 和
  Phase 4 Dashboard/Note 页面中保持一致；Web 沿用既有允许显示的字段，不为此暴露私有审核细节。
- 回归默认检索/context 排除规则、private audit edge 例外与 Source/locator 完整性。
- 对新增数据执行既有安全渲染检查；保持 Web 无写入、无新路由、无外部资源。

**限制**

- 不降低既有 contract、security、migration、publish 检查以使新测试通过。
- 测试使用合成内容和离线替身，不访问个人 Vault、真实附件、外部模型或公网 Git。

**完成条件**

- 对抗性测试全部通过；失败没有内容泄漏和 partial durable state。
- 完整 repository suite、Ruff、mypy 通过，Phase 0R–4 回归无失败。
- documented behavior、fixtures、机器 schema 与实现一致，未实现能力仍标 Planned/Deferred。

**Git commit:** Yes — P5-C8 `test(ai): harden review promotion and cross-phase boundaries`

### M8 — 分发、隔离安装与本地完整门禁

**要求**

- 构建 wheel/sdist 并审计新增 schema/template 资源；运行 installed code 时使用 importlib.resources。
- 新增 `scripts/verify_installed_phase5.py`，覆盖 core-only AI 全流程、旧数据兼容、JSON、
  默认 doctor 和所选 probes，并对可选 Zotero 能力分别测试缺失与离线替身。
- 保留既有 Phase 1/2B、Phase 3、Phase 4、package lifecycle smokes，并纳入新旧 Artifact 状态。
- 更新 CI 与 Package smoke：显式加入 `Phase5` push 分支及新脚本，确保 completion docs-only
  提交也会触发相同门禁。基线的 CI push 未包含 Phase5，不可遗漏该变更。
- 在支持的本地 Python 版本执行完整检查，记录执行环境、命令、退出结果和实际跳过原因。

**限制**

- 不提交生成包、SQLite、日志、临时 Vault、私人路径、凭据；core wheel 保持 pure Python。
- 不以源码 checkout 内运行代替隔离 wheel 安装，不增加未使用的 model extra。
- 无包版本/tag/release/upload 操作；远程未绿前 Phase 5 不标 Complete。

**完成条件**

- 第 5 节本地检查全部通过，安装/升级/降级/卸载未修改任何 Vault 文件。
- 新旧 schema/template 在 wheel 中正确且源字节一致；旧程序遇新扩展的行为符合版本决策。
- Phase 5 feature commits 已形成可审阅结果，可在获得 push 授权后运行远程门禁。

**Git commit:** Yes — P5-C9 `test: pass phase 5 local and distribution gates`

### M9 — 远程门禁与状态收口

**要求**

- 确认存在针对 Phase 5 的有效提交/推送授权后推送 Phase5，等待该精确 feature SHA 的 CI 与
  Package smoke 全部通过；没有授权则停在本地交付，明确列出待提交与远程验收项。
- 失败时保留诊断证据，修复实际问题并重新验证；必要修复用独立 fix commit，不能伪造绿灯。
- 仅在 feature SHA 全绿后，同步目标文档、README、plan README、roadmap、interfaces、
  chapter-map、CLI ledger；AI 命令及 doctor 扩展有命令级与完整套件证据后标 Verified。
- completion commit 只更新状态和证据，再通过相同远程矩阵。

**限制**

- workflow 未触发、被取消、跳过必要检查或仅其他 SHA 成功，均不算本阶段通过。
- 不以手工维护的测试数量代替真实检查结果；不将远程等待作为已完成状态。
- PR、merge、tag、版本和发布仍是独立动作；已有授权在其范围内持续有效。

**完成条件**

- feature 与 completion SHA 均有 Windows/macOS/Linux × Python 3.13/3.14 成功证据。
- CI/Package smoke 链接与实际 SHA 对应，工作区干净，Phase5 与远端一致。
- 文档、已发布命令和数据行为一致；无尚未落实的必需项，才能宣布 Phase 5 Complete。

**Git commit:** Yes — P5-C10 `docs: mark phase 5 complete`

## 5. 完成前必须检查什么

以下勾选表示 2026-09-12 的历史验证结论（见第 8 节）；后续审查使其不足以证明当前阶段完成。
当前修复验收及重新收口条件见第 8.5 节，旧 completion 门禁不能替代新代码的远程验证。

### 5.1 功能、知识完整性与兼容性

- [x] Artifact 模板入口、scan、list、get、review、dry-run、apply 的用户流程可完整复现。
- [x] 四种 Artifact 类型/状态可读；默认列表、过滤、分页和空结果语义确定。
- [x] accepted 不等于 promoted；拒绝/未审核内容不能进入普通 Note。
- [x] 审核快照覆盖正文、模型、输入和版本；内容变化及输入变化使旧授权失效。
- [x] reviewer、review time、promotion actor/time、input references、目标与审计关系持久可查。
- [x] 新 AI section 全部为 AI block，不能伪造 human/fact；Note 原有 section/ID/正文保留。
- [x] Artifact 始终 private，目标不会被自动公开，候选关系未被自动执行。
- [x] 旧 v2 Artifact/public AI Note 可读；旧 accepted 的显式重审保留旧归因；无自动补造历史。
- [x] 兼容性/证据版本/parser 变化的决策与实际拒绝行为一致，v1 历史资产未改变。

### 5.2 冲突、事务与派生状态

- [x] 读取后 Artifact、目标 Note、relation shard 和相关输入变化均能检测。
- [x] 目标不存在、已公开、归档、superseded、section 冲突和非法路径全部拒绝。
- [x] dry-run 零写入，apply 重验快照；受控失败和中断恢复无 partial durable state。
- [x] 完成晋升后重试无重复 section/关系；请求不同目标/内容时不误判为幂等成功。
- [x] 删除 SQLite/日志/已完成事务目录不损失审核事实，也不破坏幂等判定。
- [x] 索引刷新失败不回滚已成功知识写入；read/context/search 不隐式修复 stale index。

### 5.3 自动化、隐私与诊断

- [x] 全部新 JSON 分支匹配 schema，UTF-8 stdout 单文档、错误流和退出码一致。
- [x] context 必填 scope，保留预算和稳定引用；默认 search/context 的 AI 排除规则未放宽。
- [x] source-free human 内容仍是 human；Facts 必须有合法 Source/locator，不能由晋升绕过。
- [x] 没有模型网络请求、隐式外发、prompt/附件跟随读取或执行 AI 文本的路径。
- [x] 私有 Artifact audit edge 不被当作 public 内容依赖复制；不声称完成 Phase 6B 发布认证。
- [x] 默认 doctor 保持原报告兼容；新 probes 显式、只读、超时、区分 skipped/unavailable/failed。
- [x] 缺少 Git/Zotero/Web extra 不破坏 core AI 功能，错误不泄漏正文、凭据和机器路径。
- [x] Phase 4 Web 路由与只读安全头保持，新增 AI 内容能安全渲染且保留归因。

### 5.4 分发与交付证据

- [x] 完整测试、Ruff、mypy、wheel/sdist 构建与 distribution audit 通过。
- [x] core-only 与可选依赖环境完成隔离 wheel 验收，执行位置不依赖源码树。
- [x] Phase 1/2B、3、4、5 installed smoke 与生命周期测试通过；Vault 字节未被安装操作改变。
- [x] CI 和 Package smoke 覆盖 Phase5；feature 精确 SHA 的六种平台/Python 组合全部成功。
- 最终 Complete 必须另满足 completion 精确 SHA 的同矩阵门禁；其定位与回执要求见第 8.4 节。
- [x] CLI ledger、目标状态、文档链接和证据一致；未提交私有或生成文件。

### 5.5 必需检查命令

开发时运行最小相关测试；M7/M8 与最终交付必须包含：

```powershell
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests scripts
uv run --no-sync mypy src tests scripts
uv build
uv run --no-sync python scripts/verify_distribution.py dist
```

构建后，以**本次构建的唯一 wheel 文件**作为参数，在隔离环境执行：

```text
python scripts/verify_installed_phase1.py WHEEL_PATH
python scripts/verify_installed_phase3.py WHEEL_PATH
python scripts/verify_installed_phase4.py WHEEL_PATH
python scripts/verify_installed_phase5.py WHEEL_PATH
python scripts/verify_install_lifecycle.py WHEEL_PATH
```

Phase 5 脚本由 M8 新增，其余脚本沿用并扩展；验证结论以第 8 节对应构建的记录为准。
源码环境 doctor 不能替代安装包验证；不要把平台真实不支持的检查强行改成通过。
平台跳过项需有明确原因和等价覆盖，必需安全/契约检查不允许以 skip 消除失败。

## 6. Git 与状态规则

- 使用用户已有 `Phase5` 分支；执行时再核对基线，不自动重建分支或改写用户历史。
- P5-C1～P5-C10 是建议的独立提交边界；每步只纳入对应文件，阶段性修复另作清晰提交。
- 最初目标文档整理不提交、不推送；当前用户已另行明确授权 P5-C1～C9 提交/推送，
  以及 feature 全绿后的 P5-C10 提交/推送/验证。此权限来自 Phase 5 本次授权，不沿用 Phase 4。
- 若后续只授权本地实施，则先完成全部可审阅本地工作，Git/远端门禁作为剩余步骤明确列出，
  不声称整个阶段 Complete；已经授权的步骤无需重复确认。
- 规划交付时保持 Planning handoff；明确执行后按证据更新 In progress / Implemented；
  feature 与 completion 远程门禁全部通过后才是 Complete。
- Phase 5 完成不自动启动 Phase 6A/6B 或软件包发布。

## 7. 后续可直接使用的执行指令

以下内容供用户准备好后作为新的开发请求使用；写入本文件不代表当前已发出执行授权：

```text
按照 plan/phase5-goal.md 完成 Phase 5 的本地开发与验收。
继续使用已有 Phase5 分支；先核对工作区及已有实现，不覆盖无关改动、不重新创建分支。
按 M0–M8 推进，每一步满足要求、限制和完成条件后再继续，并记录实际验收证据。
必须交付第 2 节的用户结果，完整遵守第 3 节要求，逐项验证第 5 节检查表。
无另行明确授权时，不 stage、commit、push、创建 PR、合并、打 tag 或发布。
完成全部可行本地工作后，说明完成内容、验证结果、遗留问题，以及待授权的 Git/M9 步骤；
远程门禁未完成时不得将 Phase 5 标为 Complete。
```

如用户还希望同一次开发包含 Git 与远程验收，可另行明确授权：

```text
授权在已有 Phase5 分支提交 P5-C1～P5-C9 及必要的验收修复，并推送 origin。
feature SHA 的 CI 和 Package smoke 全绿后，授权提交并推送
P5-C10 docs: mark phase 5 complete，并验证该 completion SHA 的相同远程门禁。
本授权不包含 PR 创建、合并、分支删除、tag 或软件包发布。
```

## 8. 执行证据与最终交接

本地实施已恢复，不将已有代码或历史测试结果直接转换为本阶段验收结论。
执行时每个 M0–M9 均补充以下记录，未实测项保持待验收，不预先勾选：

| 记录项 | 必须包含 |
|---|---|
| 范围 | 里程碑、具体交付、修改文件及对应要求 |
| 验证 | 执行日期、环境/Python、命令、退出结果、跳过原因 |
| 风险 | 未通过项、兼容性影响、剩余限制与需要用户决定的事项 |
| Git | 未授权/待提交，或实际提交 SHA；不凭计划编号声称已提交 |
| 远程 | 精确 SHA 对应的 CI 与 Package smoke 链接及必需矩阵结果 |

最终交接应回答：现在能做什么、如何运行完整流程、哪些边界仍不支持、
第 5 节各项有什么证据、有哪些待授权动作。仅完成本地实现时明确写“本地验收完成，
Git/远程门禁待完成”；只有 M9 全部满足才写“Phase 5 Complete”。

### 8.1 本地实施记录（2026-09-12）

当前工作分支为 `Phase5`，P5-C1～C9 已提交并推送，完整 feature 远程门禁已通过。
以下本地记录不是远程 feature/completion SHA 的替代证据；M9 将分别验证两次精确提交。

| 里程碑 | 已交付内容与可执行证据 | 当前边界 |
|---|---|---|
| M0 | ADR-0018、主题文档与本目标；版本、人工归因、只读诊断和非目标已明确 | 阶段 Git 已授权；发布未授权 |
| M1 | v2 可选审核/晋升证据、模板、5 个机器结果 schema；`test_phase5_contracts.py` 固定新旧样例、路径、身份和版本边界 | 旧 strict schema 的前向可读性不作保证 |
| M2 | scanner-backed 队列、过滤/分页/排序、get 复用；`test_phase5_ai.py` 覆盖全部类型/状态；`phase5-usage.md` 提供合成接入样例 | 无模型生成、导入或网络传输 |
| M3 | 人工接受/拒绝、版本快照、旧 accepted 重审、同决定幂等；`test_phase5_ai.py` 与 `test_phase5_adversarial.py` | 审核归因是调用者声明，不是认证 |
| M4 | 默认预览、三文件事务、持久晋升映射；故障/中断/再次恢复、并发依赖与配置变化、四类 Note 内容和关系保留均有测试 | 只追加到明确的 private Note；冲突不覆盖人工编辑 |
| M5 | `scripts/phase5_workflow.py`、真实 CLI golden 对照、写入后 Note/AI block/审计边验证；`test_phase5_workflow.py` 回归 scope、索引警告和只读 Web | context 仍排除全部 AI；脚本不自动作人工决定 |
| M6 | doctor 默认 v1 与显式 probes v2；`test_phase5_doctor.py` 覆盖聚合、只读、能力缺失、超时和输出脱敏 | 未选择的 probe 不执行，不自动修复 |
| M7 | Windows Python 3.13.14/3.14.6 完整套件各 668 passed、3 skipped；Ruff 与 mypy（100 个源文件）均通过 | 平台跳过不能当成跨平台通过 |
| M8 | wheel/sdist 构建与审计、两版本 Phase 1/2B、3、4、5 core/optional 安装验收与生命周期检查均通过；CI/Package smoke 已接入 Phase5 | 六种平台/Python 组合的远程安装与生命周期检查均通过 |
| M9 | P5-C1～C9 已推送；feature 的 CI 及 Package smoke 共 14 个 job 全部成功 | P5-C10 仅含完成文档；自身同矩阵全绿后本完成记录生效 |

兼容性核对使用基线提交中的真实 `schemas/v2/objects.schema.json`：16 个旧 Artifact
样例全部通过，4 个带新证据的样例全部被旧 strict schema 拒绝，与 ADR-0018 的降级限制一致。
当前 parser 的新旧样例往返和未知证据版本拒绝另由契约/对抗测试执行验证。

Windows 本地既有 3 个平台跳过项为：长路径未启用、当前账户不能创建目录 symlink、
POSIX 权限语义。已有 Windows junction 安全测试及 Phase 5 的内外部路径别名测试实际通过；
M9 的 Linux/macOS feature CI 已实际通过 POSIX 和链接安全覆盖，未用 Windows 结果推定。
Linux/macOS 唯一平台 skip 是 Windows junction 专属用例；Phase 5 用例不含 skip。

### 8.2 构建与验证记录

- Windows Python 3.13.14 与 3.14.6：执行第 5.5 节完整 pytest、Ruff、mypy，退出码均为 0。
  完整 pytest 各为 668 passed、3 skipped；唯一 warning 为既有 Starlette/httpx TestClient 弃用提示，
  不影响真实安装后的 loopback 验收。
- 两版本均在源码树外安装同一 core wheel，并执行 Phase 1/2B、3、4、5 installed smoke
  及 `verify_install_lifecycle.py`，全部退出 0；Zotero 采用离线替身，不连接真实库或附件。
- 构建 wheel/sdist 并运行 `verify_distribution.py dist` 通过；新增机器资源与源码字节一致，
  源码包包含工作流示例与安装验收脚本。包版本、发布资格和 v1 历史资产未改变。
- 本地验收 wheel：`knowlume-0.1.0-py3-none-any.whl`，SHA-256 为
  `b0a0d6757595bab1a6113db6766d4b4cd286ea5a603616b0f5a572b6bdbd1674`。
  此为同步 README 后重新构建并在两版本重新通过全部 installed smoke/lifecycle 的交付包。
  生成包和临时测试环境均不纳入 Git。
- 阶段提交按本次明确授权进行；feature 精确 SHA 与链接见第 8.4 节。
  completion 采用该节的自指提交定位与最终回执规则；两次门禁通过前，不宣布 Phase 5 Complete。

### 8.3 Git checkpoint 验证（2026-09-12）

提交拆分使用完整已测试工作区的独立暂存快照，不覆盖工作区文件；在临时目录检出各快照后验证。
P5-C2 契约快照 64 passed；P5-C3 查询快照 60 passed；P5-C4 审核快照 63 passed；
P5-C5 晋升快照 106 passed；P5-C6 自动化快照 14 passed；P5-C7 诊断快照 23 passed；
P5-C8 对抗与跨阶段快照 132 passed。C3/C4/C5/C7 的 Ruff 和完整类型检查均通过。
这些 focused checks 不替代第 8.2 节完整本地门禁或 M9 精确 SHA 的远程矩阵。
所有临时检出、类型检查缓存和提交拆分辅助脚本均位于已忽略的 `tmp/`，未纳入 Git。

| Checkpoint | Commit | 交付 |
|---|---|---|
| P5-C1 | `637dd20` | 冻结设计与兼容性决策 |
| P5-C2 | `bee0596` | schema、模板与契约样例 |
| P5-C3 | `6f9bef5` | Artifact 查询、解析与接入 |
| P5-C4 | `cfa0c52` | 人工审核与版本绑定 |
| P5-C5 | `dbecab8` | 事务晋升、恢复与幂等 |
| P5-C6 | `52695f4` | 显式 scope/人工决定的本地工作流 |
| P5-C7 | `dba4f39` | 显式只读 doctor probes |
| P5-C8 | `15067ec` | 对抗性与跨阶段验收 |
| P5-C9 | `3c03ccf` | 完整本地和分发门禁、CI 接入 |

### 8.4 远程精确提交证据与完成记录生效条件

Feature SHA 为 `3c03ccf8b13d2e484635ffa5cd4a02e9820f2f8a`：

- [CI run 34683929401](https://github.com/yjdy/Knowlume/actions/runs/34683929401)：
  Windows/macOS/Linux × Python 3.13/3.14 六个测试 job 与 build job 全部 `success`。
  每个测试 job 的完整 pytest、Ruff、mypy 均成功，构建与分发审计成功。
  六个 job 的 pytest 日志均为 670 passed、1 skipped；Windows 跳过 POSIX 专属权限检查，
  Linux/macOS 跳过 Windows 专属 junction 检查。无 Phase 5 用例被跳过。
- [Package smoke run 34683929402](https://github.com/yjdy/Knowlume/actions/runs/34683929402)：
  build 与六个 install job 全部 `success`；每个环境的 uv tool、pipx、Phase 1/2B、3、4、5
  installed smoke 和 Vault-preserving lifecycle 步骤均成功，没有跳过必需步骤。
- 两个 workflow 的 `head_sha` 均已核对为上述 feature SHA，不使用其他分支或旧提交的绿灯。

P5-C10 是紧接此 feature 的 `docs: mark phase 5 complete` 提交，只更新状态、使用说明和证据，
不改变源码、契约、模板、测试、工作流或发布配置。README 作为包 metadata 会重新构建并由
completion 的 Package smoke 重新验证；本地第 8.2 节 wheel hash 是 feature 包的历史证据。

Git 提交无法在自己的文件中嵌入自身 SHA 或提交之后才产生的运行 ID，因此本文件不伪造这些值。
实际 completion SHA、对应 CI/Package smoke 两条永久链接与最终远端一致性由本次执行最终回执给出。
复查时可定位父提交为上述 feature SHA、主题为 `docs: mark phase 5 complete` 的直接后继提交，
核对其 GitHub Actions `head_sha`；不得只查看分支最近的任意成功运行。

**生效条款：** 只有该 completion SHA 的 CI 和 Package smoke 均为 completed/success，
六种矩阵组合及全部必需步骤成功，且本地 `Phase5` 与 `origin/Phase5` 指向该 SHA、工作区干净时，
本文及导航中的 Complete 状态才生效。等待、取消、失败、跳过必要检查均不满足此条件。
这不授权创建 PR、合并、分支删除、tag、版本发布或启动 Phase 6。

### 8.5 审查后本地修复

2026-09-13：P5-C10 `aca4de01ea4a4e9ef8ac04d57dc80f4b0ed0398d` 已通过
[CI](https://github.com/yjdy/Knowlume/actions/runs/34684713600) 和
[Package smoke](https://github.com/yjdy/Knowlume/actions/runs/34684713613)，两个 workflow
各 7 个 job 及必需步骤全部成功。此证据只证明该提交，不证明本节未提交的后续修复。

分支相对 main 的双轴审查发现三个 P2 问题，阶段重新进入 In progress：

- Snippet 的必需 `source_id` 未纳入审核依赖。现按既有闭包规则遍历 Source，绑定内容与
  relation shard 的存在/缺失；归档或 superseded 来源不得通过审核/晋升。
- 非 UTF-8 Vault 配置绕过 doctor 聚合。现将发现过程纳入每个已选 probe 的错误边界，
  保留单一脱敏 JSON 和后续 probe 结果，不修改 Vault。
- application diagnostics 直接实现具体探测。现由 CLI 注入 `DiagnosticProbePort`，
  具体 Git/SQLite/Zotero/Vault 操作位于 adapter，应用层保留选择、聚合和退出策略。
  既有 scanner 的健康检查由 CLI 注入，诊断 adapter 不反向导入应用服务。

这是一项依赖完整性和实现边界修复，不改变 durable schema、review evidence 版本、CLI
参数或 JSON 版本。旧不完整 evidence 保持可读，但不能静默补填或授权晋升，须准备新候选；
既有已完成晋升的幂等重试规则保持不变。决策与兼容性说明见 ADR-0018 和 data-model。

回归记录：修复前 5 个用例全部失败；修复后新增回归与 doctor 定向套件 33 passed，
Ruff 和 mypy（103 个源文件）在两个环境均通过。最终代码在 Windows Python 3.13.14 与
3.14.6 的完整套件各为 680 passed、3 skipped，退出 0。跳过仍仅为长路径、账户 symlink
权限及 POSIX 权限语义；Phase 5 无跳过，既有 Starlette/httpx 弃用 warning 未新增。
wheel/sdist 已重新构建并通过分发审计。两版 Python 均使用最终同一 wheel，在源码树外
完成 Phase 1/2B、3、4、5 的 core/optional 安装验收，以及安装、升级、降级、卸载保持
Vault 字节不变的生命周期检查；全部退出 0。最终 wheel SHA-256 为
`9f688c66107f10c2615bb75ac9a74ebf3bbc0ce374fa9ca5f51e54dc241c02ff`。
收口文档更新后另跑内部链接检查与 diff whitespace 检查，均通过。
全部测试使用合成数据，临时重现脚本、环境和生成包保持忽略，未使用个人知识库。

Git 边界：2026-09-14 用户已明确授权提交、推送本次修复；远程检查通过后，再提交、推送
并验证完成记录。先验证本次修复精确 SHA 的完整 CI 与 Package smoke，再更新并验证完成记录。
本修复提交的 SHA、远程链接及随后完成记录的定位规则将在通过门禁后的文档中记录；
未获得两次精确提交的成功证据前，不宣布 Phase 5 Complete。
