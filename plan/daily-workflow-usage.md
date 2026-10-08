# 科研日用闭环使用指南（中文）

本指南按“创建 → 定位 → 编辑 → 校验 → 索引 → 检索 → 阅读”操作。
验收状态见 [执行目标](daily-workflow-goal.md)，接口决定见 [ADR-0019](decisions/0019-research-daily-workflow.md)。
以下资料、论文名、项目 commit、fact 内容和 human 文本全部是演示数据，不是真实研究结论。
样例未访问 Zotero、Git 远程或模型，没有 PDF；不能据此声称真实集成通过。

## 1. 准备独立测试 vault

先安装 core 包；Web 阅读另需 `knowlume[web]`。程序仓库与 vault 保持分离。
源码及 sdist 带有 [合成样例](../tests/fixtures/daily-workflow/sources/paper-a.md)和
[可运行演示](../scripts/daily_workflow_demo.py)，core wheel 仅安装命令，不安装演示脚本。
在已解压的源码目录，选择一个**尚不存在**的 vault 路径执行：

```text
python scripts/daily_workflow_demo.py --vault NEW_TEST_VAULT
```

脚本创建两个 Literature、一个无 Source 的 Idea 并演化为 Concept、一个关联两个对象的
Synthesis；写入明确标为演示的 human/fact 文本，建立项目引用和 section 关系。
随后实际执行校验、索引、中英文检索、显式 scope context、AI 审核/预览/冲突拒绝、
陈旧索引恢复。输出四个 ID、相对路径和 section URL。重复运行拒绝覆盖已有目录。
`real_trial: not_run` 明确表示真实试用未进行。以下步骤可在另一个新 vault 手工复现。

PowerShell 示例（将路径改为自己的独立测试位置；不要选择个人 vault）：

```powershell
$demoVault = 'NEW_TEST_VAULT'
kb init $demoVault
Copy-Item tests/fixtures/daily-workflow/sources/paper-a.md "$demoVault/sources/papers/"
Copy-Item tests/fixtures/daily-workflow/sources/paper-b.md "$demoVault/sources/papers/"
Copy-Item tests/fixtures/daily-workflow/sources/project.md "$demoVault/sources/oss/"
kb --vault $demoVault lint
```

上面的目录是默认配置；自定义布局以 `knowlume.toml` 为准。样例的 Zotero key 是合成占位，
不要对它们执行 sync/open 并将结果当真实恢复证据。实际资料可用 `kb add INPUT --type paper --json`
采集；[sources and adapters](sources-and-adapters.md)拥有精确匹配和 PDF 恢复规则。
重复采集由 [模拟适配器测试](../tests/test_phase2b_capture.py)验证，真实试用单列在第 7 节。

## 2. 创建并立即定位文件

```powershell
$paperA = 'src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0'
$paperB = 'src_01JSTAG7N9Q3V5X8Y2Z4A6B8C4'
$project = 'src_01JSTAG7N9Q3V5X8Y2Z4A6B8C3'
$readingA = kb --vault $demoVault note new --type literature --source $paperA --title '演示：论文 A 阅读' --json | ConvertFrom-Json
$readingB = kb --vault $demoVault note new --type literature --source $paperB --title '演示：论文 B 阅读' --json | ConvertFrom-Json
$idea = kb --vault $demoVault note new --type idea --title '演示：知识回顾想法' --json | ConvertFrom-Json
$synthesis = kb --vault $demoVault note new --type synthesis --title '演示：跨来源综合' --json | ConvertFrom-Json
$readingA.data.object_id
Join-Path $demoVault $readingA.data.path
```

先确认 `success` 为 true 再使用 `data`。JSON 路径是实际写入的 vault 相对路径；
自定义 notes 目录也适用。非 JSON 模式只输出 ID。省略标题保留 `Untitled TYPE`；
标题可有中文、引号、冒号，不能为空或含换行、控制字符。
Literature 需要已有 Source，其 summarizing 关系随 Note 事务创建；其他类型可无 Source。

## 3. 用编辑器写 human 内容和 fact 引用

在编辑器或 Obsidian 中打开上一步的实际文件。保留 frontmatter 中的 ID 和原有 section
标记；修改 human section 的提示文本，例如：

```markdown
演示 human 文本（非用户观点）：知识积累需要定期回顾。Knowledge review demo.
```

给 Literature 在文件末尾追加以下**合成事实演示**。第二篇替换 source_id 为 `$paperB` 的值。
真实事实必须根据已核验原文填写定位；完整语义由 [data-model](data-model.md)及
[locator schema](../schemas/v2/locator.schema.json)拥有，样例 page 不证明存在真实 PDF。

```markdown
<!-- knowlume:section id=sec_demo_facts role=fact -->
## 合成来源事实演示

<!-- knowlume:fact
citations:
  - source_id: src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0
    locator:
      locator_version: 2
      source_type: paper
      page: 1
      section: "demo"
-->
演示 fact 文本（非真实论文结论）：合成资料展示知识回顾。
```

Synthesis 的 human section 由你填写综合认识，不由创建命令自动生成。
保持稳定 section ID；改标题、heading、类型时都不要用行号或标题替换身份。
保存后先执行下一节的 lint；失败时修正文档，再建立关系和刷新索引。

```powershell
kb --vault $demoVault lint
kb --vault $demoVault note evolve $idea.data.object_id --to concept
kb --vault $demoVault relation add $synthesis.data.object_id $readingA.data.object_id --type synthesizes
kb --vault $demoVault relation add $synthesis.data.object_id $readingB.data.object_id --type synthesizes
kb --vault $demoVault relation add $idea.data.object_id $project --type cites
kb --vault $demoVault relation add $readingB.data.object_id $readingA.data.object_id --type supports --section sec_demo_facts
kb --vault $demoVault process $paperA --to reading --json
kb --vault $demoVault process $paperB --to reading --json
```

Idea 演化为 Concept 保留对象 ID、文件路径和 section 身份。关系类型的合法端点及
cardinality 由现有契约负责；例如 related_to 连接两个 Note，不能用于 Note→Source。

## 4. 固定编辑后步骤与恢复

每次外部编辑后执行：

```powershell
kb --vault $demoVault lint
kb --vault $demoVault index build --json
kb --vault $demoVault search '知识' --json
kb --vault $demoVault search 'Knowledge' --json
kb --vault $demoVault context '知识' --scope trusted-local --json
```

lint 成功之后再 build。命令写入会尝试刷新已有索引，但编辑器保存不会自动刷新。
`trusted-local` 可包含私人资料；JSON 输出不等于外部模型授权。scope 必须显式选择。

| 状态/诊断 | 操作 |
|---|---|
| missing / INDEX_NOT_FOUND | `kb --vault VAULT index build` |
| stale / INDEX_SOURCE_CHANGED | 先 lint，再 `index build`；页面不会自动修复 |
| incompatible / INDEX_INCOMPATIBLE | `kb --vault VAULT index rebuild` |
| corrupt / INDEX_CORRUPT | `kb --vault VAULT index rebuild`；SQLite 可重建，durable 文件仍是事实来源 |
| INDEX_SOURCE_INVALID | `kb --vault VAULT lint`，修正来源或引用错误，再 build；反复 rebuild 不能修复源文件 |

索引不可用时，`kb --vault VAULT grep QUERY --json` 直接查 durable 文件；
`kb --vault VAULT get ID --json` 返回对象、相对路径、校验值、引用和关系，适合定位与排查。
这两个只读命令不替代 lint，也不生成索引。详细语义见 [storage/index/search](storage-index-search.md)。

## 5. 检索并阅读 section

```text
kb --vault VAULT serve
```

使用启动输出中的本机地址打开搜索页。Note section 命中链接直达
`/notes/NOTE_ID#sec_demo_facts` 等稳定位置。Note 页先显示类型、标题、正文、角色和
引用，然后关系，最后原生可展开的“可追溯信息与规范化字段”；禁用 JavaScript 仍可阅读。
正向关系可直达目标 section；反向关系分别链接来源对象和当前页的目标 section。
搜索和目录页面只读，不会在后台补索引。
错误页面中的 `<VAULT_ROOT>` 要替换成启动 serve 时的同一 vault，路径有空格时加引号。
CLI 和 Web 使用同一批文件和服务；在多个 vault 间切换时每条命令都显式 `--vault`。

## 6. 合成 Artifact：看清、审核、预览、拒绝过期修改

只在本测试 vault 中复制 [合成 Artifact](../tests/fixtures/daily-workflow/artifact.md)至
配置的 AI 目录（默认 `ai/artifacts/demo.md`）。其工具/模型名明确表示离线演示。
用 get 阅读候选正文，用 list 查看队列；真实使用须阅读所有 input_refs。

```powershell
Copy-Item tests/fixtures/daily-workflow/artifact.md "$demoVault/ai/artifacts/demo.md"
$artifactId = 'ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E1'
kb --vault $demoVault ai list --json
$inspected = kb --vault $demoVault get $artifactId --json | ConvertFrom-Json
kb --vault $demoVault ai review $artifactId --decision accepted --reviewer demo-human --expect-checksum $inspected.data.checksum --json
$accepted = kb --vault $demoVault get $artifactId --json | ConvertFrom-Json
$target = kb --vault $demoVault get $idea.data.object_id --json | ConvertFrom-Json
kb --vault $demoVault ai promote $artifactId --into $idea.data.object_id --section sec_demo_ai --actor demo-human --expect-artifact-checksum $accepted.data.checksum --expect-note-checksum $target.data.checksum --dry-run --json
```

`demo-human` 仅演示身份。真实审核填写自己的真实 reviewer/actor；不要直接改 review_status。
预览不会写入。现在编辑目标 human section，保留旧 `$target.data.checksum`，执行同一 promote
命令但把 `--dry-run` 改为 `--apply`：应退出 4、返回 `VAULT_WRITE_CONFLICT`，候选和 Note 都不变。
这一步只用于证明过期写入被拒绝。再次 lint → build → search；如真正决定晋升，应重新阅读
当前文件并获取新校验值，再明确 apply。输入材料或候选变动还需遵守现有审查证据规则。
完整晋升和幂等重试步骤见 [Phase 5 指南](phase5-usage.md)，本教程不调用外部模型。

## 7. 真实试用清单（当前未完成）

真实 Zotero 与编辑器试用和工程交付分开记录。条件未提供，当前不能声称真实接入通过。
在用户指定的测试资料中执行下列项目；记录应用/包版本、平台和结果，不记录私人正文、路径或凭据。

| 项目 | 通过条件 | 当前状态 |
|---|---|---|
| 两篇 Paper | 支持的 Zotero API 精确匹配两篇 DOI/arXiv，记录匿名化对象指纹 | 未提供测试条件 |
| PDF 恢复 | 至少一篇具有可恢复 PDF，校验通过；不可用路径给 typed 诊断 | 未试用 |
| 重复采集 | 同一资料重复 add 返回原 ID，不重复写入 | 仅模拟适配器有证据 |
| 编辑器往返 | 创建后按返回路径打开、写 human/fact、保存、lint/build/search、section 阅读 | 自动化演示通过后仍需真实编辑器试用 |
| 版本记录 | 包版本、Zotero 版本、编辑器版本、操作系统及试用日期 | 待填写 |

本地工程和远程平台证据统一维护在 [执行目标](daily-workflow-goal.md)，本指南不取代契约。
