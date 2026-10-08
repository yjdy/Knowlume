# Knowlume 整体开发计划与现状审视

> 日期：2026-10-04（Asia/Shanghai）  
> 状态：独立审视报告；不是活动规范、阶段重开决定或发布授权。  
> 目标：以个人科研阅读与知识积累为主线，核对交付事实，识别日常流程障碍。  
> 配套文件：[路线调整提案](2026-10-04-roadmap-proposal.md)。

## 1. 结论

**Knowlume 已有经过验证的知识存储、引用、检索和审核基础，下一阶段最值得交付的是“科研日用闭环”。** 不建议按原阶段编号立即铺开全部演化功能，也不建议先引入语义检索、MCP 或模型调用。

- **现在能可靠做什么：** 在既定输入边界内采集 Source，创建和关联 Note，维护稳定对象与 section ID，执行冲突保护及可恢复事务，中英文全文检索，浏览本地只读 Web，并对已有 AI Artifact 进行绑定版本的人工审核和晋升。依据是本轮完整测试、安装包验证和历史远程检查，不代表所有真实资料、设备及编辑器组合都已验证。
- **日常使用卡在哪里：** 输入材料需要满足 Zotero 的既有记录条件；笔记创建后仍要查找文件并编辑结构；外部编辑会使索引陈旧；浏览页面优先展示技术元数据；AI 候选接入和审核参数传递成本高；回顾整理仍缺少专用入口。
- **原路线哪里应调整：** 保留 Contract v2、文件事实源、安全门禁及原有阶段成果。先修复机器错误输出问题，补齐写作、找回和操作指引，再提前 Phase 6A 中只读关联与回顾能力；合并、复杂历史、发布和高级搜索按实际需求后置。
- **本次确认的功能缺陷：** `kb context QUERY --json` 缺少必填 `--scope` 时，退出码为 2，stdout 为空，stderr 为普通用法提示，没有满足机器接口所声明的单 JSON 文档输出。其余主要发现属于体验、架构偏差、验证缺口或既定范围限制。

本轮没有发现新的数据丢失、越权公开或未经审核晋升的可复现缺陷。此结论限于已运行场景，不是全面安全认证。

## 2. 基线、范围与证据规则

| 项目 | 本次基线 |
|---|---|
| 仓库 | [yjdy/Knowlume](https://github.com/yjdy/Knowlume) |
| HEAD | `0c39f452004ed58b8ef3c8f11f560c09255b5494` |
| 分支 | `Phase5` |
| Dirty / Shallow | 审视开始时均为 false |
| 远端 | `git ls-remote origin refs/heads/Phase5` 返回同一 SHA |
| 本地运行环境 | Windows、Python 3.14.6；源码环境使用现有锁定依赖；隔离 wheel 环境独立解析已声明依赖 |
| 用户优先级 | 全面复盘并允许重排路线；科研阅读与知识积累；个人日常使用优先 |

当前 HEAD 的直接父提交是 Phase 5 修复提交 `1cf410cf9e7168394e907424732ed8c860964d4d`，主题为 `docs: mark phase 5 complete after review fixes`，与[完成记录定位规则](../phase5-goal.md#86-审查修复远程证据与最终完成记录)相符。正文中的代码位置均基于上述 HEAD；新增报告不改变其生产实现。

阅读覆盖活动主题文档、相关 accepted ADR、全部阶段导航、CLI 账本、契约及测试，重点追踪采集、笔记、关系、索引、AI 和 Web 的关键路径。历史 v1 仅作为兼容/迁移证据；临时克隆、缓存和生成包不作为生产实现依据。没有逐行审查全部代码，没有访问个人 vault、调用外部模型、操作真实 Zotero 资料或发布软件。

证据优先级遵循 [AGENTS.md](../../AGENTS.md)：机器契约与可执行测试优先，主题文档定义语义，路线图定义交付顺序。报告区分：**事实**（直接执行或代码证据）、**判断**（对使用价值与维护成本的解释）、**未知**（缺少运行或使用证据）。工作量 S/M/L 仅表示相对规模，不是工期承诺。

## 3. 用户任务与实际能力

| 用户任务 | 已有能力与路径 | 主要手工步骤/边界 | 本轮结论 |
|---|---|---|---|
| 收集论文并开始阅读 | `add` → Source → `source show/open` → `process` | 先有可精确匹配的 Zotero 条目；PDF 缺失允许建卡，打开需要已记录主附件 | 合成采集与重复识别通过；真实 Zotero/PDF 恢复未验证 |
| 研究论文对应的开源项目 | repo capture → 固定 commit Source → Literature Note → relation | 捕获只记录项目根与默认 HEAD；不读取代码、不解析许可证、不创建 Snippet | 可建立项目级阅读与论文关联，不能视为代码知识抽取 |
| 写阅读笔记 | `note new --type literature --source ID` → 编辑 Markdown → lint | 默认标题为 Untitled；创建只返回 ID；事实块的 locator 与角色元数据仍需编辑 | 数据模型支持闭环，写作入口成本较高 |
| 记录个人想法并综合 | Idea → Concept；Synthesis + 两条 `synthesizes` | 观点形成、正文写作和关系选择由人完成；专用回顾/合并/历史命令未交付 | 已能组织知识，持续维护工具尚不完整 |
| 找回并复用知识 | grep/get；index；search；显式 scope context | 外部编辑后必须显式刷新索引；语义近义召回不在当前范围 | literal 中英文检索与引用可追溯；研究级召回质量未知 |
| 使用 AI 辅助材料 | 手工 Artifact → list/get → review → promote | 无模型调用或候选导入命令；人工决策、对象 ID、section ID、校验值需要传递 | 审核控制有效，但不是端到端 AI 生成产品 |
| 浏览与回顾 | Dashboard、Source/Note、Search、Health | Web 只读；详情页先展示路径、checksum 和规范化字段；关联以 ID 为主 | 可检查数据，阅读优先的信息组织仍可改善 |

任务边界依据：[来源与适配器](../sources-and-adapters.md)、[数据模型](../data-model.md)、[AI 工作流](../phase5-usage.md)、[CLI 账本](../../CLI.md)。

## 4. 阶段与能力证据矩阵

| 阶段 | 文档承诺 | 代码实现 | 自动化覆盖 | 本次验证 | 使用限制/判断 |
|---|---|---|---|---|---|
| 0R | v2 契约、角色、关系、迁移基线 | v2 schemas/templates、parser、validation | phase0/phase1 contracts、正反 fixtures、迁移测试 | 全套测试通过，v1 历史与链接检查保留 | 当前契约证据充分；不推断历史独立 CI 状态 |
| 分发基础 | 纯 Python 包、资源审计、可选依赖、生命周期隔离 | resources、doctor、build 配置和验证脚本 | distribution/runtime/release tests、installed smoke | 本次构建审计和全部安装脚本通过 | 发布资格不等于已发布；本轮未核验注册表、保护规则或审批环境 |
| 1 | vault、解析、Note、关系、安全写入、迁移 | filesystem、transactions、notes、relations、migration | Phase 1 命令、冲突及恢复测试 | 全套＋installed Phase1；示例创建、演化、关联通过 | 创建与关系命令的人类界面仍需较多 ID 操作 |
| 2A | Paper/Zotero、主附件恢复、同步与状态流转 | paper_capture、sources、zotero_local | adapter、capture、sources、CLI 测试 | 全套＋core/Zotero 安装档验证；逐步推进状态通过 | 实际 Zotero 服务、真实 PDF 缺少本轮集成证据 |
| 2B | 四类统一采集、Web snapshot、Book edition、固定 OSS HEAD | capture、Git resolver、Zotero candidate lookup | 四类识别、幂等、冲突、匿名 Git 和工作流测试 | 全套＋installed Phase1/2B；合成 Paper/OSS 幂等通过 | Book/Web open/sync 未补齐；OSS 仅项目级元数据；Snippet 创建延期 |
| 3 | 确定性投影、双语 literal FTS、稳定引用、scope context | sqlite_projection、query、indexing | 重建等价、陈旧/损坏/并发、过滤、预算、安全范围测试 | 全套＋installed Phase3；中英文命中、陈旧拒绝、build/rebuild 对照通过 | 编辑器改写后需显式索引；R01 是既有 JSON 错误路径遗漏 |
| 4 | 本地只读、共享服务、安全 Markdown | web app/server、catalog、rendering、bundled templates | Web/CLI 一致、Host/Origin/XSS、方法、零写入测试 | 全套＋installed Phase4；本轮浏览器六类页面及中文搜索通过 | 没有写入、附件投递或 AI 审核 UI；正文位置与跳转体验有改进空间 |
| 5 | 绑定版本的人工审核、事务晋升、显式 probes | AIService、cli_ai、diagnostics、workflow example | AI、adversarial、workflow、doctor、三项审查回归 | 全套＋installed Phase5；修复与完成提交远程双门禁核实 | 完成条件成立；不包含生成候选或模型 transport |
| 6A | 关联、回链、历史、合并、替代、整理建议 | 已有 relation list 和 Note evolve 基础；专用命令未注册 | 不将既有基础测试当作新命令验收 | 对照 CLI 注册和账本确认 Planned | 适合拆分只读回顾与高风险多文件演化 |
| 6B | allowlist、完整闭包审计、原子 staging、Quartz | 有公共安全检查基础，无 publish 命令交付 | 已有 public-safe context 测试，不等价于 publish gate | 静态核对未交付 | 保持 Planned；不能据此公开 vault |
| 7 | 语义/MCP/图/多智能体等 | 当前没有对应生产运行闭环 | 未作为已实现能力验证 | 确认为 Deferred 范围 | 先用真实任务明确缺口，避免扩展先于使用证据 |

阶段所有权见 [roadmap](../roadmap.md)，实际命令及状态见 [CLI.md](../../CLI.md)。不得因为新增发现就改写历史远程成功，也不得把历史成功解释为所有用户流程无缺陷。

### 4.1 远程记录核验

本轮通过 GitHub REST API 读取 run 和 jobs，核对 SHA、workflow 结论及每个 job 的状态。下表每一行的两次运行各有 7 个成功 job：构建及 Windows/macOS/Linux × Python 3.13/3.14 的六种测试或安装组合。没有只依据 README 链接文字判断成功；没有重新触发远程工作流。

| 记录 | 精确提交 | CI | Package smoke |
|---|---|---|---|
| Phase 1 | `b3a0bc5292a4fdfc95dcbdbd75a1868c0f79a8ce` | [33120979913](https://github.com/yjdy/Knowlume/actions/runs/33120979913) | [33120979856](https://github.com/yjdy/Knowlume/actions/runs/33120979856) |
| Phase 2A | `7329f75e6530ecf8c8b4f0ce1d3dd3d43f515a81` | [33179444723](https://github.com/yjdy/Knowlume/actions/runs/33179444723) | [33179444644](https://github.com/yjdy/Knowlume/actions/runs/33179444644) |
| Phase 2B | `6c419fcafc2dece59db5793f6ee792e22f283625` | [33252123661](https://github.com/yjdy/Knowlume/actions/runs/33252123661) | [33252123610](https://github.com/yjdy/Knowlume/actions/runs/33252123610) |
| Phase 3 | `09c4a634a9fdf196dee0e7efe066ce3ab7eafd01` | [33300551834](https://github.com/yjdy/Knowlume/actions/runs/33300551834) | [33300551847](https://github.com/yjdy/Knowlume/actions/runs/33300551847) |
| Phase 4 | `7fdf1bb08b784ac6d5d0b3caad86ba0508cfdb38` | [33882303896](https://github.com/yjdy/Knowlume/actions/runs/33882303896) | [33882303627](https://github.com/yjdy/Knowlume/actions/runs/33882303627) |
| Phase 5 审查修复 | `1cf410cf9e7168394e907424732ed8c860964d4d` | [34797875616](https://github.com/yjdy/Knowlume/actions/runs/34797875616) | [34797875619](https://github.com/yjdy/Knowlume/actions/runs/34797875619) |
| Phase 5 最终完成记录 | `0c39f452004ed58b8ef3c8f11f560c09255b5494` | [34799997389](https://github.com/yjdy/Knowlume/actions/runs/34799997389) | [34799997386](https://github.com/yjdy/Knowlume/actions/runs/34799997386) |

**事实：** 最终完成记录满足直接后继、对应提交的两个 workflow 成功、本地/远端分支同 SHA、起始工作区干净这些条件。因此 Phase 5 的附条件完成声明在本次核验时成立。未逐份重放历史日志，也未独立审计远程 runner 或发布环境。

## 5. 本地验证记录

### 5.1 工程检查

| 执行项 | 本次结果 |
|---|---|
| `uv run --no-sync pytest -p no:cacheprovider` | 680 passed、3 skipped、1 warning，194.54 秒；这是本次基线运行记录，不是需手工维护的测试数量指标 |
| `uv run --no-sync ruff check src tests scripts` | All checks passed |
| `uv run --no-sync mypy src tests scripts` | 103 个 source files，无问题 |
| `uv build --out-dir tmp/review-20261004-dist` | wheel 与 sdist 成功 |
| `uv run --no-sync python scripts/verify_distribution.py tmp/review-20261004-dist` | distribution artifacts verified |
| `verify_installed_phase1.py WHEEL_PATH` | core 与 Zotero 档、截至 Phase 2B 的安装命令验证通过 |
| `verify_installed_phase3.py WHEEL_PATH` | 源码树外核心查询、投影与生命周期验证通过 |
| `verify_installed_phase4.py WHEEL_PATH` | core-only 和 Web loopback 验证通过 |
| `verify_installed_phase5.py WHEEL_PATH` | core/optional AI 工作流及只读 probes 通过 |
| `verify_install_lifecycle.py WHEEL_PATH` | 安装、升级、降级和卸载保持 vault 不变 |
| 新增报告后的文档链接检查 | `test_internal_documentation_links_resolve`：1 passed；所有新增文档链接可解析 |

安装脚本均以 `uv run --no-sync python scripts/<脚本> WHEEL_PATH` 启动，使用同一个本次构建 wheel；脚本内部创建系统临时目录、独立环境，并在源码目录之外执行已安装程序。没有用 editable 资源替代 wheel。生命周期脚本使用临时构造的旧版本包，不能外推为任意历史版本升级都已测试。

3 个跳过项对应 Windows 长路径、当前账户目录 symlink 能力，以及 POSIX 权限语义；依据 [vault tests](../../tests/test_phase1_vault.py) L54、L175、L228，另以 `pytest -rs` 定向复核了这三项实际跳过原因。跨平台覆盖来自上述远程记录，而非本地推断。唯一 warning 是 Starlette TestClient 使用 httpx 的弃用提示；未在本轮改动依赖。

构建发生在新增审视文档之前，代表生产基线。产物 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `knowlume-0.1.0-py3-none-any.whl` | `3b9af38282f56fc1043eee3ebf79868cb7d9c6ebf5fef7c20503dd1ed18295d6` |
| `knowlume-0.1.0.tar.gz` | `18d85de20c15932d439a1613c7e87dc5713954a8a06aff4cd97711d9d659a7b6` |

### 5.2 独立科研流程实测

另外新建源码树外的 wheel `[web]` 环境与临时 vault，运行 51 次真实 CLI 调用。仅采集边界注入合成 Zotero/Git ports，通过已安装的 `UnifiedCaptureService` 建立 Paper/OSS；不把这一部分表述为真实 API 采集。合成论文不代表真实论文事实；AI 文件明确标记 `offline-demonstration` / `synthetic-example-not-a-model-run`。

| 场景 | 实际操作与结果 |
|---|---|
| 论文与项目采集 | 建立两个 private Source，重复采集返回已有 ID；OSS commit 为明确的合成固定值。论文无附件产生 `PAPER_ATTACHMENT_UNAVAILABLE`，`source open` 以 `ZOTERO_ITEM_UNAVAILABLE` / exit 5 拒绝 |
| 阅读与记录 | Paper 经 reading → processed → integrated；创建两篇 Literature Note、一篇 Idea 和一篇 Synthesis；手工写入 human 内容和带 page locator 的合成 fact；strict lint 通过 |
| 关联与演化 | 两篇 Literature Note 建立 related_to；Synthesis 分别 synthesizes 两篇笔记；Idea → Concept 保留对象 ID；relation list 返回正反向关联 |
| 检索与索引 | 索引缺失时 search 返回 `INDEX_NOT_FOUND` / exit 5；build 后 attention 命中 3 项、知识命中 2 项；外部编辑后返回 `INDEX_SOURCE_CHANGED` / exit 4；grep/get 仍可读取；build 与 rebuild 后 attention 结果完全相同 |
| scope | trusted-local 返回合成私有 human 内容；public-safe 不纳入这些私有结果；缺 scope 以 exit 2 拒绝，但 JSON 输出遗漏见 R01 |
| AI 人工流程 | list/get → accepted review → 再 get → promote dry-run → apply；dry-run 的 vault 字节快照不变；旧 checksum 重试 exit 4；重新读取后的同目标重试 `already_promoted=true` |
| AI 与检索隔离 | 晋升后默认 search 和 context 不返回 AI proposal 内容；最终 strict lint 与 vault/sqlite doctor 通过；诊断前后 vault 字节不变 |

以上不是最低操作次数评测：51 次包含读取、断言和异常路径。没有计时推断人的阅读或写作速度，也没有把空白 Synthesis 模板与关系存在视为实际完成了学术综合。

### 5.3 浏览器验证

通过上述已安装 wheel 启动临时 loopback 服务，检查概览、笔记目录、来源目录、笔记详情、来源详情、搜索和健康页。确认对象统计为 2 Sources、4 Notes、1 Artifact，均 private；fact locator、人类内容、正反关系正常显示；中文查询与 CLI 一致返回两条 human 结果。

在临时 vault 中追加一个空行使索引陈旧，浏览器搜索显示 `INDEX_SOURCE_CHANGED` 和显式 `kb index build` 指引，健康页显示 stale，普通目录仍可浏览。随后恢复原始文件字节，比较全部 vault 文件哈希与浏览前一致。临时服务和浏览器已关闭。

视觉观察：详情首屏主要是大标题、ID、路径与 checksum，随后为全部规范化字段，正文位于更下方；搜索和关系显示 section ID 但链接没有对应 fragment。没有在本轮重跑所有窄屏、键盘、无 JavaScript、主题及 reduced-motion 场景；相关历史验收和本轮自动化测试不能替代完整人工无障碍审计。

### 5.4 高风险路径覆盖

- 并发与恢复：[Phase 1 transactions](../../tests/test_phase1_transactions.py) L73、L114、L142、L152，以及 [Phase 5 adversarial](../../tests/test_phase5_adversarial.py) L75、L107、L130 覆盖提交边界中断、回滚、锁冲突及不覆盖其他写入。
- 输入与引用：[Phase 5 review regressions](../../tests/test_phase5_review_regressions.py) L108–147 覆盖 Snippet Source 依赖与旧证据拒绝；[sources tests](../../tests/test_phase2a_sources.py) L161、L249、L280 覆盖人工修改、附件 hash 变化和 expected-checksum。
- 投影与公共范围：[Phase 3 search tests](../../tests/test_phase3_search.py) L189、L444、L522、L762、L905 覆盖重建等价、并发、版本不兼容、私有依赖和无引用 fact。
- Web：[Phase 4 web tests](../../tests/test_phase4_web.py) L596、L606 覆盖 Host/Origin、路径、方法、XSS、诊断及只读约束。

这些测试在本轮完整套件中执行；故障注入通过不代表在本机模拟了断电、文件系统损坏或全部编辑器竞争方式。

## 6. 发现、优先级与处理建议

### R01 — JSON 用法错误输出不统一（功能缺陷，P2，S）

**证据与复现：** 在有效临时 vault 上执行 `kb --vault VAULT context knowledge --json`；安装包环境和源码环境均表现为 exit 2、stdout 空、stderr 普通用法提示。依据 [interfaces](../interfaces.md) L223 的单 envelope 承诺，[CLI context](../../src/knowlume/cli.py) L848 的普通 Typer 命令注册。现有 [Phase 3 CLI test](../../tests/test_phase3_cli.py) L138–146 仅检查未带 JSON 的缺 scope 调用退出码，未锁定该错误的机器输出。AI 与 doctor 已分别有参数解析错误 envelope 处理，可作为统一策略参考。

**影响：** 脚本消费者不能仅凭 `--json` 假设 stdout 可解析，缺参数时可能先遭遇 JSON 解码错误，掩盖真正原因。不允许以隐式 scope 修复这个问题。

**建议/依赖/验收：** 先确认所有既有 JSON 命令的参数错误约定，再补集中处理及代表性命令级回归；需要接口所有者核对，不需改变 durable object。缺必填参数、非法值、未知选项仍 exit 2，同时输出符合现有 envelope 的单文档且无私人输入泄漏；全套与安装包检查通过。

### R02 — 创建到正文编辑缺少便捷交接（体验问题，P1，M）

**事实：** [NoteService](../../src/knowlume/application/notes.py) L69–94 固定生成 `Untitled <type>`；[CLI](../../src/knowlume/cli.py) L396–416 只接收 type/source 并打印 ID。科研示例必须用 get 找相对路径，再修改标题、正文、fact 注释和 locator；这不是 Note 创建失败。

**影响/判断：** 高频创作依赖用户记住结构和找到文件，最容易让“已经采集”停在空白笔记。

**建议/依赖/验收：** 优先增加可选标题和显式的文件定位结果，提供研究阅读、fact 引用及 synthesis 的一条完整操作指南。新增机器结果须先定义版本化接口；不假设需要 Web 编辑器。创建有标题笔记后能直接定位文件、填写正文、lint、检索找回，无需搜索仓库文档或猜测字段；保留既有 ID 与角色规则。

### R03 — 外部编辑到检索之间存在维护断点（体验问题，P1，S–M）

**事实：** 外部编辑后 FTS/context 按契约拒绝陈旧索引，本轮 CLI 与浏览器均复现；grep/get 保持可用。[indexing service](../../src/knowlume/application/indexing.py) L13 只为显式应用写入提供最佳努力刷新，不能观察外部编辑器的写入。

**建议/依赖/验收：** 在编辑完成的指南/显式工作流入口中安排 lint 与 index build；Web 展示清晰恢复指引，说明如何选择当前 vault。保持搜索零写入和版本不兼容时显式 rebuild，不用后台隐式重建掩盖问题。编辑后能够循指引恢复，刷新失败不丢失正文；索引删除后仍可重建。

### R04 — 浏览与跳转优先展示结构，未优先帮助阅读（体验问题，P2，S–M）

**证据：** [note-detail](../../templates/web/note-detail.html) L5–11 在正文前输出路径、checksum、全部字段；[search-results](../../templates/web/fragments/search-results.html) L5 仅使用 object_href，section ID 另作文本显示；[relations](../../templates/web/partials/relations.html) L10–13 同样不把目标 section 加入链接。本轮浏览器观察与模板一致。

**建议/依赖/验收：** 正文、角色和来源摘要前置，将审计字段折叠但保留可访问；搜索命中跳到已有稳定 section，关联显示可读标题并保留 ID。修改仅涉及只读展示，不引入正文缓存或新持久身份。长笔记点击命中能定位正确 section，缺失/不适用目标有安全退路，完整页与 HTMX 一致且零写入。

### R05 — 真实资料与长期使用证据不足（验证缺口，P1，M）

**事实：** 自动化覆盖包括 mock Zotero、合成附件和 fake Git；本轮独立流程仍使用注入 ports。新 Paper/Web/Book capture 需要 Zotero 精确候选，[capture](../../src/knowlume/application/capture.py) L179、L294；[SourceService](../../src/knowlume/application/sources.py) L210、L254 的 open/sync 仅支持 Paper。不存在“任意 DOI 自动从互联网获取资料”的已交付承诺。

**建议/依赖/验收：** 在用户指定范围的测试 library/vault 上进行真实 Zotero read-only 接入、PDF 恢复和编辑器试用；记录版本、候选歧义、缺附件、重复采集、阅读到笔记的具体结果。依赖用户准备/指定非私人或获授权的数据；未满足条件时保持“真实集成未验收”，不降低既有 capture/引用门槛。性能与长期采用率也不从 7 对象示例外推。

### R06 — AI 审核已完成，候选接入仍是手工流程（范围限制及体验问题，P2，M）

**证据：** [ADR-0018](../decisions/0018-phase5-local-revision-bound-ai-review.md) 和 [usage](../phase5-usage.md) 明确不含生成；操作要准备 Artifact、读取 candidate/target、审核后重读 checksum、显式晋升。本轮验证了这些操作及幂等保护。

**建议/依赖/验收：** 先以模板和校验辅助降低候选接入与参数传递成本，再评估受控导入；不得自动接受、伪造生成时输入版本或移除人类决策。模型 transport 属于后续独立 release-policy 决策。候选来源不明时提示缺口，修改审核内容必须重新准备候选，默认 search/context 隔离规则不变。

### R07 — 应用层依赖方向与架构声明不完全一致（架构偏差，P2，M）

**事实：** [architecture](../architecture.md) L19–29 声明 application 依赖 domain/ports；[notes](../../src/knowlume/application/notes.py) L7–13、[capture](../../src/knowlume/application/capture.py) L8–9、[ai](../../src/knowlume/application/ai.py) L10–18 直接导入 contract_v2、FilesystemVault 或 RecoverableTransactions。[VaultPort](../../src/knowlume/ports/vault.py) 已存在，但部分服务参数仍是具体适配器。诊断模块的边界回归测试只覆盖该模块，不能代表全应用层合规。

**影响/判断：** 当前行为测试良好，但后续改变存储/事务或引入新写入入口时，替换与测试成本可能增加。没有证据证明现阶段需要重写存储层。

**建议/依赖/验收：** 在新写入能力前先确定公共事务/文件写入接口与 parser 所有权；按受影响服务逐步消除反向依赖，或通过明确 ADR 修订不切实际的分层声明。依赖方向有可执行约束，原有冲突/恢复/资源读取测试不减弱；不做一次性全仓重构。

### R08 — 每次查询扫描文件的规模成本未量化（性能风险，P2，S 测量，优化待定）

**事实：** [catalog](../../src/knowlume/application/catalog.py) L125、L129、L207、L255 从 scanner 生成快照；[SQLiteProjection.status](../../src/knowlume/adapters/sqlite_projection.py) L144–148 扫描 vault，search L614 调用 status，部分路径还会重新扫描；[context](../../src/knowlume/application/query.py) L260 再构建扫描结果。

**判断/未知：** SQLite 并不意味着完整查询没有全库读取成本；但本轮没有规模延迟基准，不能称为已确认性能故障。

**建议/依赖/验收：** 在 100/1,000/10,000 个合成对象上测量扫描、搜索、Web 详情和索引，分别报告冷/热路径、文件数量、字节量、耗时与环境。只有实际超出约定使用预算才优化；优化仍必须识别外部编辑和陈旧投影。

### R09 — 后续规划应拆分只读回顾与高风险演化（路线建议，P2，分项估算）

**事实：** [CLI ledger](../../CLI.md) L153–172 将 related/backlinks/history/merge/supersede/tidy/organize/review 统列 6A。已有 relation list 包含反向关系，Web 详情也显示 incoming；专用命令未完成不等于完全不能回链。6B 的 publish 仍未实现，public-safe context 不能代替它。

**建议/依赖/验收：** 先交付复用既有关系与扫描的只读关联/回顾；合并与历史另立阶段目标，在事务、actor、Git provenance 决策充分后实施。发布、语义检索、MCP 不作为日用闭环的前置条件。以具体用户任务和退出门槛排序，见配套提案。

## 7. 未知项、复现与边界

仍未知：真实 Zotero/附件组合、用户实际 Obsidian 操作与持续使用负担、规模性能、科研相关性/近义召回质量、完整浏览器可访问性、注册表现状和远程发布保护配置。没有将“自动化绿灯”转换成这些结论。

复现工程验证：在记录的 HEAD 上运行第 5.1 节命令，将 `WHEEL_PATH` 替换为本次独立输出目录中唯一 wheel 的路径；各 installed 脚本自建临时环境。GitHub 证据可用 `GET /repos/yjdy/Knowlume/actions/runs/{id}` 与 `/jobs?per_page=100` 重新核对，避免只查看 workflow 总览的最新运行。

复现科研流程：使用独立测试 vault，按第 5.2 节依次建立两类 Source、两篇 Literature、Idea 和 Synthesis；Source 采集的合成接口形状可参照 [capture tests](../../tests/test_phase2b_capture.py) L32–115，项目到笔记流程参照 [workflow test](../../tests/test_phase2b_workflow.py) L20；fact 注释参照 [有效阅读笔记 fixture](../../tests/fixtures/v2/valid/literature-note.md)，AI 输入与命令参照 [官方离线示例](../phase5-usage.md)。所有 IDs 重新生成，不把示例事实或合成模型字段用于真实资料。

临时脚本、详细 CLI 输出、API JSON、示例 vault、环境和包均是可丢弃验证辅助；本报告保留了重要结果、复现方式、产物哈希和永久远程链接，不依赖临时文件作为唯一业务记录。本次仅新增本报告与路线提案，不改动活动计划、代码、schema 或 CLI ledger，不进行 Git 写操作。
