# Phase 4 execution goal: Local read-only Web management

> **Status:** Complete — M0–M8 gates passed
> **Target branch:** `Phase4`
> **Implementation baseline commit:** `ab22542316788fc0924a672d4c70dd923b878394`
> **Baseline state:** Phase 3 已合并到 `main`；本地实现从该提交开始；P4-C1～P4-C8 位于 `Phase4`
> **Feature evidence:** [CI](https://github.com/yjdy/Knowlume/actions/runs/33882303896) and [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33882303627) passed for `7fdf1bb08b784ac6d5d0b3caad86ba0508cfdb38`

## 1. 当前基础与权威来源

Phase 0R、Phase 1、Phase 2A、Phase 2B 和 Phase 3 已完成。Phase 4 直接复用：

- Contract v2 对象、稳定 ID、Note section、Fact citation、AI provenance 和 relation shard；
- Vault 发现、解析、扫描、typed findings、路径边界和冲突安全读取；
- Source、Note、关系和工作流的既有 application services；
- Phase 3 的 SQLite projection、索引状态、双语 FTS、过滤器、稳定排序和对象追溯；
- CLI envelope、可选依赖、`importlib.resources`、wheel 审计、隔离安装和跨平台 CI；
- 当前已开放的 TestPyPI/PyPI prerelease 门禁；Phase 4 不执行发布。

本目标从属于机器契约，并遵循：

- [`roadmap.md`](roadmap.md)
- [`architecture.md`](architecture.md)
- [`interfaces.md`](interfaces.md)
- [`security-publishing.md`](security-publishing.md)
- [`distribution.md`](distribution.md)
- [`ADR-0001`](decisions/0001-files-as-source-of-truth.md)
- [`ADR-0010`](decisions/0010-python-package-distribution.md)
- [`ADR-0016`](decisions/0016-phase3-deterministic-projection-search-context.md)
- M0 新增并接受的 `ADR-0017`

Phase 4 只能增加一个复用现有应用层的只读 Web 接口，不得建立第二套解析器、搜索实现、对象模型或持久化层。

## 2. 最终可以得到什么

Phase 4 完成后，安装 Web extra 的用户可以运行：

```text
kb serve
  [--host 127.0.0.1|localhost|::1]
  [--port PORT]
  [--open-browser]
```

默认行为：

- 监听 `127.0.0.1:8765`；
- 只允许 loopback 地址，不允许局域网或公网监听；
- 默认不自动打开浏览器；
- `--open-browser` 显式要求在服务成功启动后打开一次浏览器；
- 通过 Ctrl+C 正常退出，不产生 traceback；
- 不要求 Zotero 正在运行；
- 不创建、重建或修复索引；
- 不修改 Vault、SQLite、缓存、配置或附件。

用户获得一个中文优先、响应式、可键盘操作的本地管理界面：

| 路由 | 页面 | 数据来源 |
|---|---|---|
| `/` | Dashboard | scanner、对象统计、Source 工作流、AI 审核计数、index status |
| `/sources` | Source 列表 | 共享只读 catalog service |
| `/sources/{source_id}` | Source 详情 | `get_object` 和规范化 Source 数据 |
| `/notes` | Note 列表 | 共享只读 catalog service |
| `/notes/{note_id}` | Note 详情 | `get_object`、稳定 section、citation 和 relations |
| `/search` | FTS 搜索 | Phase 3 `QueryService.search` |
| `/health` | Knowledge Health | scanner findings 和 index status |
| `/assets/app.css` | 本地样式 | wheel 内置资源 |
| `/assets/htmx.min.js` | HTMX | wheel 内置且固定版本的资源 |

Phase 4 只提供 HTML 页面和 HTMX HTML 片段。程序调用继续使用现有 `kb ... --json`；不新增 HTTP JSON API、OpenAPI 或接口 schema。

## 3. 冻结的接口与行为

### 3.1 页面数据和导航

Dashboard 显示：

- Source、Note、Snippet、AI Artifact 数量；
- private/public 数量；
- Paper、Web、Book、OSS 数量；
- Idea、Literature、Concept、Synthesis 数量；
- Inbox、Reading、Processed、Integrated 数量；
- unreviewed/accepted/rejected/promoted AI Artifact 数量；
- scanner error/warning 数量；
- SQLite index 的 `missing/fresh/stale/incompatible/corrupt` 状态和对象/segment 数量；
- 最近更新的 5 个 Source 和 5 个 Note。

Dashboard 和 Knowledge Health 只展示已有 scanner/index 事实，不在 Phase 4 发明新的健康规则。诸如“建议整理”“阅读债务”和自动修复继续属于 Phase 6A。

Source 列表支持：

- `source_type`
- `workflow_stage`
- `record_status`
- `visibility`
- 可重复 `tag`，采用 AND 语义
- `page`

Note 列表支持：

- `note_type`
- `maturity`
- `record_status`
- `visibility`
- 可重复 `tag`，采用 AND 语义
- `page`

列表固定每页 50 项，不提供可变 page size。排序为 `updated` 降序，再按稳定对象 ID 升序。无效过滤器或页码返回安全的 HTTP 400 页面。

详情页显示：

- 规范化对象字段；
- Vault 相对路径和 checksum；
- Source 附件是否存在、文件名、MIME、大小和哈希；
- Note 的稳定 section、role、正文块及 Fact citations；
- incoming/outgoing relations；
- 指向本界面已有 Source/Note 页面的内部链接。

不得显示机器绝对路径、Zotero storage 路径、附件正文、网页 snapshot 正文或私有 adapter 错误细节。Source 的 HTTP(S) canonical URL 可以作为外部链接显示，并强制 `rel="noopener noreferrer"`。

### 3.2 搜索行为

搜索页面完整复用 Phase 3：

- 查询参数 `q`；
- `trusted-local` 和 `public-safe` scope；
- kind、subtype、visibility、record status、workflow stage、maturity、review status、tag 和 role 过滤器；
- 默认 `trusted-local`，默认 limit 20，最大 200；
- BM25 和稳定 tie-break；
- object ID、section ID、role、snippet、tags、status 和 citations；
- public-safe exclusion 继续由 Phase 3 规则决定。

空查询只显示表单，不调用后端。无效查询或过滤器返回 HTTP 400。

只有 fresh compatible index 可以执行搜索：

- `missing`：提示运行 `kb index build`；
- `stale`：提示运行 `kb index build`；
- `incompatible` 或 `corrupt`：提示运行 `kb index rebuild`；
- 页面返回 HTTP 503，并保留对应 `INDEX_*` 诊断代码；
- Web 页面不得提供构建、重建或修复按钮。

显式 trusted-local AI 搜索保持 Phase 3 行为，但 Phase 4 不提供 AI Artifact 详情、审核或晋升页面。默认搜索仍排除 AI。

### 3.3 读取一致性

新增 UI-neutral 的 `CatalogQueryService`，负责 Dashboard、Source/Note catalog、过滤、统计和分页。它：

- 每次请求使用一个 scanner snapshot；
- 复用现有 domain values、`scan_vault`、`get_object`、`QueryService` 和 `ProjectionStore.status`；
- 不调用 CLI callback，不解析 CLI JSON，不启动子进程；
- 不缓存 durable object body；
- 不要求索引存在即可浏览 Dashboard、Sources、Notes 和 Health；
- 在 Vault 不健康时仍展示成功解析的对象和完整 findings，不隐藏问题或尝试修复。

### 3.4 Markdown 与前端资源

Note/Source 正文使用安全 Markdown 子集：

- Web extra 增加直接依赖 `markdown-it-py>=4.2,<5`，精确版本由 `uv.lock` 固定；
- 禁止 raw HTML、外部图片、`file:`、`data:`、`javascript:` 和未知 URL scheme；
- 支持标题、段落、列表、引用、强调、行内代码、代码块和安全 HTTP(S) 链接；
- Jinja2 全局启用 autoescape；
- 只有经过安全 renderer 生成的结果可以进入模板的 HTML-safe 边界；
- 用户正文、标题、标签、诊断 message 和 query 不得直接标记为 safe。

HTMX 固定使用 2.0.10，按[官方本地复制方式](https://github.com/bigskysoftware/htmx/blob/master/www/content/docs.md?plain=1)放入权威资源目录，同时保存上游许可证和完整性记录。不得从 CDN、npm 服务或运行时网络加载脚本、字体、样式或图片。

HTML 在禁用 JavaScript 时仍可通过普通 GET 表单完成列表过滤、分页和搜索。HTMX 仅用于渐进增强；同一路由根据 `HX-Request` 返回完整页面或受控片段，不改变数据权限和错误语义。

界面采用：

- 中文页面文案；
- 英文原值保留用于对象类型、role、状态、诊断代码和稳定 ID；
- semantic HTML、可见焦点、键盘导航、足够色彩对比；
- `prefers-color-scheme` 自动适配明暗主题；
- `prefers-reduced-motion`；
- 无前端构建链、无遥测、无外部资源。

### 3.5 本地服务安全

网络边界固定为：

- `--host` 只接受 `127.0.0.1`、`localhost`、`::1`；
- `--port` 只接受 1–65535，默认 8765；
- 不信任 `X-Forwarded-*` 或代理头；
- 不启用 permissive CORS，也不返回 `Access-Control-Allow-Origin: *`；
- Host 必须匹配允许的 loopback host；
- Origin 缺失时允许普通浏览器 GET；存在时必须与当前 loopback origin 完全同源；
- 不使用 cookie、session、认证 token 或本地 secret；
- `/docs`、`/redoc` 和 `/openapi.json` 禁用；
- 仅注册 GET/HEAD；POST、PUT、PATCH、DELETE 返回 405；
- 不提供文件系统路径路由、通配附件路由或 Zotero 打开动作；
- Uvicorn access log 默认关闭，错误日志不得记录 query、正文、附件或绝对路径。

所有 HTML、错误和静态资源响应都设置：

```text
Content-Security-Policy:
  default-src 'self';
  base-uri 'none';
  object-src 'none';
  frame-ancestors 'none';
  form-action 'self';
  script-src 'self';
  style-src 'self';
  img-src 'self';
  connect-src 'self'

X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Cache-Control: no-store
```

### 3.6 CLI 和 HTTP 诊断

新增 CLI 诊断：

| Code | Exit | 含义 |
|---|---:|---|
| `WEB_ARGUMENT_INVALID` | 2 | host 或 port 不符合 Phase 4 边界 |
| `WEB_CAPABILITY_UNAVAILABLE` | 5 | 未安装 `knowlume[web]` 或 Web runtime 不可导入 |
| `WEB_SERVER_UNAVAILABLE` | 5 | loopback 绑定或服务启动失败 |
| `WEB_BROWSER_OPEN_FAILED` | warning | 服务已启动，但显式浏览器打开失败 |

`kb serve --help` 必须在没有 Web extra 时正常工作。Web 依赖只在实际执行 `kb serve` 时延迟导入。

HTTP 错误行为：

- 400：无效查询、过滤器、分页参数；
- 403：Host 或 Origin 被拒绝；
- 404：对象不存在、ID 类型与路由不匹配、资源不存在；
- 405：不允许的方法；
- 503：搜索索引不可用；
- 500：未预期错误，只显示通用错误页和关联 ID，不显示 traceback、正文或本地路径。

### 3.7 打包边界

- `templates/web/` 是 Web HTML、CSS、JS 和 vendor license 的权威目录；
- wheel 中的副本位于 `knowlume/_assets/templates/web/`；
- 运行时只通过 `importlib.resources` 获取模板和静态资源；
- `scripts/verify_distribution.py` 比较所有 Web 资源的源字节和 wheel 字节；
- `web` 和 `all` extras 增加 `markdown-it-py`，core 和 `zotero` extra 不增加 Web 依赖；
- core wheel 保持 `py3-none-any`；
- 安装、升级、降级和卸载不得创建、修改或删除 Vault、索引或用户配置；
- Phase 4 不修改 package version、Contract version、parser、projection、tokenizer、segment algorithm、配置 schema 或 SQLite DDL。

## 4. 不能遗漏的要求

- Web 必须是严格只读界面；包括 disposable SQLite 在内也不得由 Web 自动修改。
- Markdown/YAML 和 relation shards 仍是唯一 durable authority。
- Web 和 CLI 必须调用相同应用服务和规则，不能复制搜索、过滤、引用或 public-safe 逻辑。
- Dashboard、Sources、Notes 和 Health 必须在索引缺失时可用。
- Search 必须拒绝 missing、stale、incompatible 和 corrupt index。
- 完整本地界面可以显示 private 内容，但只能通过 loopback 提供。
- raw AI Artifact 默认不可见；显式 AI 搜索只能保持现有 trusted-local 行为。
- Fact citations、稳定 object/section ID 和 provenance role 不能在 HTML 转换中丢失。
- 所有用户内容都必须经过转义或安全 Markdown renderer。
- 页面不得提供 PDF、网页 snapshot、Zotero storage 或任意 Vault 文件下载。
- 页面和资源不得依赖 CDN、外部字体、分析服务、遥测或运行时网络。
- 任何 Host、Origin、路径、HTML、URL scheme 或模板注入测试都必须 fail closed。
- 缺少 Web extra 不能破坏 core CLI 的 import、help、version、doctor 或 Phase 0R–3 功能。
- HTML 模板和前端资源必须随 wheel 安装，并通过字节一致性审计。
- Phase 4 完成不能绕过完整测试、隔离安装和跨平台远程门禁。

## 5. 里程碑和工作步骤

Git checkpoint 表示需要形成独立、可回滚的提交，不代表已经授权 stage、commit、push、merge、tag 或发布。

### M0 — 冻结 Phase 4 设计

**要求**

- 新增并接受 `ADR-0017: Keep Phase 4 Web local, read-only, and application-backed`。
- 新增本目标文档。
- 同步 interfaces、security、distribution、roadmap、plan README、chapter map 和 CLI ledger。
- 冻结 CLI 参数、路由、页面范围、安全头、Markdown 规则、诊断和打包边界。
- `kb serve` 保持 `Planned`，不得提前标记 Implemented/Verified。

**限制**

- 仅修改设计和导航文档。
- 不修改 production code、schema、template、fixture、依赖、lockfile、CI 或版本。
- 不把历史 archive 重新设为权威来源。

**完成条件**

- 每项 Phase 4 行为只有一个明确 owner。
- 活动文档之间无冲突。
- 文档链接检查通过。
- ADR 和本目标经人工审阅接受后，才能开始 M1。

**Git commit:** Yes — P4-C1

```text
docs: freeze phase 4 read-only web design
```

### M1 — 建立共享只读查询模型和安全渲染器

**要求**

- 实现 UI-neutral 的 `CatalogQueryService`。
- 实现 Dashboard、Source/Note 列表、稳定排序、过滤、统计和固定分页。
- 复用 scanner、`get_object`、QueryService 和 ProjectionStore。
- 实现安全 Markdown renderer 和安全外部链接策略。
- 增加 `markdown-it-py>=4.2,<5` 到 `web`/`all` extra 并更新 lockfile。
- 为正常、空 Vault、不健康 Vault、边界分页和非法过滤器添加 focused tests。

**限制**

- 不导入 FastAPI、Jinja2 或 Uvicorn 到 domain/application。
- 不修改 Vault、索引、配置或 durable contract。
- 不添加 Web-only 搜索、citation、relation 或 public-safe 语义。
- 不读取附件正文或任意 Vault 文件路径。

**完成条件**

- Catalog 结果确定性稳定。
- 列表过滤和排序与现有 domain values 一致。
- 同一个请求只使用一个 scanner snapshot。
- 注入型 Markdown、URL 和模板输入均输出为无执行能力的安全 HTML。
- focused tests、Ruff 和 mypy 通过。

**Git commit:** Yes — P4-C2

```text
feat(web): add read-only catalog models and safe rendering
```

### M2 — 实现安全 Web runtime 和 `kb serve`

**要求**

- 新建 Web app factory，并通过依赖注入接收 Vault、catalog、query 和 projection services。
- 实现模板资源 loader、精确静态资源路由、基础布局和导航。
- 实现 Host/Origin 校验、安全响应头、HTML error handler 和 method boundary。
- 注册 `kb serve --host --port --open-browser`。
- 延迟导入全部 Web 可选依赖。
- 实现 capability、参数、server 和 browser warning 诊断。
- 禁用 OpenAPI/docs、proxy headers 和 access log。

**限制**

- 不实现业务页面写操作。
- 不在模块 import、`--help` 或 app factory 创建时访问网络或修改 Vault。
- 不允许非 loopback 监听。
- 不增加认证、session、cookie、TLS 或 LAN 模式。

**完成条件**

- core-only 环境中 `kb serve --help` 成功，实际启动给出 typed capability error。
- Web 环境能在三个允许的 loopback host 上启动。
- 非 loopback host、非法 port、端口占用和浏览器打开失败均有稳定行为。
- Ctrl+C 正常退出。
- route/middleware/CLI focused tests 通过。

**Git commit:** Yes — P4-C3

```text
feat(web): add secure loopback server and serve command
```

### M3 — 实现 Dashboard 和 Knowledge Health

**要求**

- 实现 `/` 与 `/health`。
- 展示冻结的对象、类型、visibility、workflow、AI review、finding 和 index 指标。
- 显示最近更新 Source/Note。
- 显示完整 scanner findings 和 index status。
- 对 findings 使用稳定排序和分页。
- 在 Vault 不健康时仍安全展示可读取信息和问题。

**限制**

- 不新增健康 finding code 或建议系统。
- 不自动运行 lint、index build/rebuild、Zotero probe 或 doctor。
- 不把 Phase 3 public-safe 检查描述为发布审计。
- 不隐藏 error findings 来制造健康状态。

**完成条件**

- Dashboard 数字与相同 snapshot 的 scanner/index 结果一致。
- missing/stale/incompatible/corrupt index 都能正常展示。
- 空 Vault 和包含无效文件的 Vault 有直接 route evidence。
- 所有页面保持只读且无绝对路径泄漏。

**Git commit:** Yes — P4-C4

```text
feat(web): add dashboard and knowledge health views
```

### M4 — 实现 Sources 和 Notes 浏览

**要求**

- 实现 Source/Note 列表、过滤、分页和详情页。
- 展示规范化字段、稳定 section、role、citations 和 relations。
- Source 页面只展示附件元数据和哈希。
- Note 页面区分 human、fact、ai、evolution 内容。
- 内部 Source/Note 链接使用稳定 ID，不使用文件名或 heading 作为身份。
- 错误 ID、错误 kind 和缺失对象返回安全 404。

**限制**

- 不提供 add、edit、delete、process、sync、open、relation mutation 或 index mutation。
- 不提供 PDF、snapshot、AI Artifact 或任意 Vault 文件下载。
- 不通过 Zotero 私有数据库或 attachment path 读取内容。
- 不将 AI 内容重新标记为 human/fact。

**完成条件**

- 所有 Source 和 Note 类型都有页面测试。
- Fact 的每条 citation 和 locator 可见且顺序保持不变。
- incoming/outgoing relations 与 `get_object` 一致。
- 列表无索引时仍可使用。
- 页面渲染不改变任何 Vault/state 文件字节或时间戳。

**Git commit:** Yes — P4-C5

```text
feat(web): add source and note browsing views
```

### M5 — 实现 FTS Search 和 HTMX 渐进增强

**要求**

- 实现 `/search` 的完整页面和 HTMX fragment。
- 暴露 Phase 3 全部 search filters 和两个 scope。
- 保持默认 trusted-local、limit、AI 排除、BM25 和稳定 tie-break。
- 显示可追溯 object/section/role/citation 信息。
- 为四种不可用 index 状态提供对应 503 页面和 CLI 恢复说明。
- 将固定的 HTMX 2.0.10、许可证和完整性记录加入权威 Web 资源。

**限制**

- 不新增 JSON API、raw FTS syntax、regex、semantic search 或 context 页面。
- HTMX header 不得放宽 Host、Origin、scope 或内容策略。
- 不自动刷新、构建或修复索引。
- 不依赖 JavaScript 才能执行搜索。

**完成条件**

- 普通 GET 和 HTMX GET 返回语义相同的结果。
- 禁用 JavaScript时搜索和过滤仍完整工作。
- 中英文、所有过滤器、AI scope、public-safe、空查询和非法查询均有 route tests。
- 搜索结果与直接调用 QueryService 的结果一致。
- 浏览器不发起任何外部资源请求。

**Git commit:** Yes — P4-C6

```text
feat(web): add traceable htmx search interface
```

### M6 — 完成安全、隐私和只读对抗测试

**要求**

- 覆盖 Host header、Origin、CORS、proxy header、method 和路径遍历攻击。
- 覆盖 raw HTML、script、事件属性、危险 URL、SVG/image、模板表达式和畸形 Markdown。
- 检查正常、错误、HTMX 和静态资源响应的全部安全头。
- 在遍历所有页面前后比较 Vault、relations、config、index 和 state 的文件集合与 checksum。
- 检查日志不包含 query、正文、附件、绝对路径或 adapter stderr。
- 覆盖并发读取和请求中 Vault 变化，确保不混合两个 snapshot。
- 对中文、键盘、focus、窄屏和明暗主题进行浏览器验收。

**限制**

- 不以“本机服务”为理由跳过 Web 安全测试。
- 不通过关闭 autoescape、CSP 或 Origin 检查解决兼容问题。
- 不把测试 Vault、截图、日志或浏览器 profile 提交到仓库。
- 不引入浏览器插件、遥测或公网测试服务。

**完成条件**

- 所有攻击输入 fail closed。
- 所有只读 route 都有“零写入”可执行证据。
- 1440×900 和 390×844 视口无阻断性布局问题。
- 核心流程仅使用键盘可完成。
- 安全 focused suite、Ruff 和 mypy 通过。

**Git commit:** Yes — P4-C7

```text
test(web): harden the local read-only boundary
```

### M7 — 通过本地、打包和隔离安装门禁

**要求**

- 将 `templates/web` 加入 wheel/sdist 和字节一致性审计。
- 将 Web 资源加入 required asset 和 distribution tests。
- 新增 installed-wheel Phase 4 smoke script。
- core-only 安装验证 help 和 typed missing-extra 诊断。
- `[web]` 安装验证实际 loopback server、主要页面、安全头、搜索和正常终止。
- 验证安装生命周期不改变既有 Vault。
- 更新 CI/package-smoke 的 Phase4 分支和脚本触发路径。
- 更新 CLI inventory；远程门禁前 `serve` 最多标记为 `Implemented`。

**限制**

- 不从源码 checkout 加载模板或静态资源。
- 不把 tests、plans、Vault、数据库、缓存、日志或截图打入 wheel。
- 不修改 package version、release gate、tag 或 registry 状态。
- 不要求 core 用户安装 FastAPI/Jinja2/Uvicorn/Markdown renderer。

**完成条件**

- 完整测试、Ruff、mypy、build 和 distribution audit 全绿。
- Python 3.13 和 3.14 的隔离 core/Web 安装通过。
- wheel 仍为 `py3-none-any`。
- Phase 0R–3 的全部行为保持通过。
- CLI help、实现表面和 CLI ledger 一致。

**Git commit:** Yes — P4-C8

```text
test: pass phase 4 local and distribution gates
```

### M8 — 通过远程门禁并标记 Phase 4 完成

**要求**

- 仅在获得显式授权后 push。
- 等待 Windows、macOS、Linux × Python 3.13/3.14 CI。
- 等待 core 和 `[web]` package smoke。
- 把真实 workflow 链接写入 README、roadmap、plan README、本目标和 CLI ledger。
- 将 `kb serve` 标记为 `Verified`，将 Phase 4 标记为 Complete。
- 让 status-only completion commit 再次通过相同门禁。

**限制**

- 未通过 feature CI 前不得声称 Complete。
- 不创建 tag、GitHub Release 或 package upload。
- 不打开 stable release gate。
- push、PR、merge 和发布仍分别授权。

**完成条件**

- feature commit 和 completion commit 的 required checks 全绿。
- `kb serve` 有命令级、route、安全、完整套件和 installed-wheel 证据。
- 最终分支干净并与远端同步。
- 文档与实际命令、依赖、页面和安全行为完全一致。

**Git commit:** Yes — P4-C9，仅在 feature remote gate 通过后

```text
docs: mark phase 4 complete
```

## 6. 明确不在 Phase 4 范围内

- Web 中任何 durable 或 disposable mutation；
- Note/Source/Relation 创建、编辑、删除、同步或工作流推进；
- index build、rebuild、repair 或后台 watcher；
- PDF/EPUB/网页 snapshot 预览、下载、流式传输或 Range；
- Zotero 打开、写入、OAuth、Cloud API 或私有 SQLite；
- HTTP JSON API、OpenAPI、GraphQL、WebSocket 或 SSE；
- LAN/public binding、认证、账户、TLS、反向代理部署；
- AI Artifact 详情、生成、审核、接受、拒绝或晋升；
- 外部模型调用、论文解析、OCR 或自动写笔记；
- publish audit/build/preview；
- semantic/vector/hybrid search、MCP、graph 和 multi-agent；
- Snippet 创建；
- Git history、backlinks、merge、supersede、tidy、organize、review；
- PWA、service worker、离线缓存、前端构建链或外部 CDN；
- Contract v2、config v1、transaction v1、projection DDL v2 或现有 JSON schema 变更；
- package version、tag、TestPyPI、PyPI 或 GitHub Release。

## 7. 完成前必须检查什么

### 功能与一致性

- 七个用户页面和两个精确静态资源路由均存在。
- Dashboard、列表、详情、搜索和 Health 使用共享 application/domain 逻辑。
- Source/Note 过滤、分页、排序和计数确定性稳定。
- 对象详情保留稳定 ID、section、citations、locators 和 relations。
- 页面在空 Vault、不健康 Vault和索引缺失时具有明确行为。
- Web 搜索与同参数 QueryService 结果一致。
- 无 JavaScript时全部核心只读功能可用。

### 只读、隐私与安全

- 所有 route 和启动流程均不修改 Vault、配置、relations、index 或 state。
- 非 GET/HEAD 方法全部拒绝。
- 非 loopback host、恶意 Host/Origin、proxy spoofing 和路径逃逸全部拒绝。
- 页面、错误和日志不泄漏绝对路径、正文、附件或私有 adapter 信息。
- Markdown、标题、标签、query、finding 和 URL 的 XSS 组合全部覆盖。
- 所有响应具有冻结的 CSP 和安全头。
- 没有外部脚本、样式、字体、图片、遥测或网络请求。
- private 内容只能通过 loopback trusted-local 页面显示。
- public-safe 仍不等于 Phase 6B 发布认证。

### 包和兼容性

- core import/help/version/doctor 不导入 Web extra。
- 缺失 Web extra 返回 `WEB_CAPABILITY_UNAVAILABLE`。
- `[web]` 和 `[all]` 安装依赖完整，`[zotero]` 不被扩大。
- Web 模板、CSS、HTMX 和许可证在 wheel 中存在且字节一致。
- wheel/sdist 不含 Vault、SQLite、缓存、日志、测试数据或截图。
- 安装、升级、降级和卸载不修改 Vault。
- Windows、macOS、Linux × Python 3.13/3.14 通过。
- 所有 Phase 0R–3 测试继续通过。

### 必需的本地命令

```powershell
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests scripts
uv run --no-sync mypy src tests scripts
uv build
uv run --no-sync python scripts/verify_distribution.py dist
```

还必须执行仓库提供的：

- Phase 1/2B installed-wheel smoke；
- Phase 3 installed projection/search smoke；
- 新增的 Phase 4 core-only 与 `[web]` installed-wheel smoke；
- install/upgrade/downgrade/uninstall lifecycle 检查；
- 实际浏览器桌面与窄屏验收。

## 8. Git 执行规则

- P4-C1～P4-C9 是必需的回滚边界，但任何 Git mutation 仍需用户显式授权。
- 每个提交只包含对应里程碑，不能混入生成数据库、构建产物、Vault、缓存、日志或无关修改。
- M0 未接受前不得开始 production 实现。
- 安全测试失败时不得提交后续里程碑。
- 本地完整门禁未通过前不得 push feature branch。
- 远程 feature gate 未通过前不得提交完成状态。
- push、PR、merge、tag、版本变化、TestPyPI、PyPI 和 GitHub Release 是独立权限。
- Phase 4 完成不会自动授权 Phase 5，也不会授权任何包发布。
