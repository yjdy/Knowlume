
# Knowlume 本地知识库设计计划

> 版本：v0.1
>
> 状态：实施基线设计
>
> 目标目录：`D:\project\Knowlume`

## 1. 项目定位

Knowlume 是一个以个人长期学习和知识演化为中心的本地 Knowledge Operating System，而不是单纯的资料收藏器、Obsidian 插件集合或 AI 聊天界面。

系统要解决四个核心问题：

1. 长期保存论文、网页、书籍和开源项目的可追溯来源。
2. 让人类笔记能够快速回到原始材料，并在不同笔记之间形成可解释的关系。
3. 让 Codex 等 harness 通过稳定的 CLI 使用知识库，同时防止 AI 生成内容反向污染事实层。
4. 将经过人工审核的私有知识安全地演化为可发布的公共知识。

核心判断：

> Markdown/YAML 和原始附件是长期事实源；SQLite 只是可重建索引；Git 保存知识演化历史；`kb` CLI 是统一控制面；Obsidian、Zotero、Quartz 和未来自研组件都是可替换 adapter。

## 2. 设计原则

### 2.1 长期事实源优先

- Markdown、YAML frontmatter、source cards、笔记、snippet 和必要的本地原始资料构成长期数据层。
- SQLite 不承载唯一知识，不保存不可从文件恢复的业务事实。
- 删除 SQLite 后，`kb index rebuild` 必须能够从文件重新生成等价索引。
- 不依赖 Obsidian 私有数据库、Zotero 内部 SQLite schema 或 Quartz 内部实现。

### 2.2 关系和出处显式化

- Source 与 Note 是多对多关系。
- Note 与 Note 也是多对多关系。
- 关系必须能从 Markdown/YAML、正文链接和引用标记中重建。
- 知识主张尽量定位到来源的 locator，例如页码、章节、网页标题或仓库 commit/代码行。

### 2.3 原始资料、人类知识、AI 产物严格分离

- 原始资料：来源、附件、网页快照、书籍文件、仓库元数据。
- 人类知识：人类阅读笔记、概念笔记、综合笔记、可发布 evergreen 笔记。
- AI 产物：摘要、提取结果、候选关系、草稿和其他未审核内容。
- AI 默认只能产生 `ai_artifact`，不能直接把内容写入事实区或公共发布区。

### 2.4 当前状态和历史分离

- 当前知识状态由当前 Markdown/YAML 表示。
- 历史由 Git 表示，不通过 `note-v1.md`、`note-v2.md` 等复制文件制造版本。
- 重要的认识转变可在笔记中增加“观点演化”段落；普通文字修改留给 Git diff。

### 2.5 先可靠，再智能

- 第一层搜索是文件搜索。
- 第二层搜索是 SQLite FTS5。
- 第三层 semantic search 只预留接口，后期再实现。
- 第一阶段不引入复杂 RAG、向量数据库、reranker、MCP server 或 agent memory。

### 2.6 默认私有，公共发布采用 allowlist 和物理隔离

- 所有新对象默认 `visibility: private`。
- 发布只能从明确允许的公共对象构建 public staging。
- 不把整个私有 vault 交给 Quartz 再依赖过滤，避免配置错误导致泄露。

## 3. 总体架构

```text
                         Human
              Obsidian / Web Dashboard
                              |
                              v
                        kb-core (Python)
                              |
              +---------------+----------------+
              |               |                |
              v               v                v
          kb CLI          File Store       SQLite Projection
              |           Markdown/YAML          FTS5
              |
       Codex / Other Harnesses
       kb search / get / context

      +----------------------------------------------+
      |                 Adapters                     |
      | Zotero | Obsidian | Git | Quartz | Filesystem|
      +----------------------------------------------+
```

逻辑分层：

1. `domain`：Source、Note、Snippet、AI Artifact、Relation、Provenance 等稳定模型。
2. `application`：capture、process、search、index、lint、review、publish 等用例。
3. `ports`：文件存储、参考文献管理、版本控制、搜索、发布和外部仓库访问接口。
4. `adapters`：Filesystem、Zotero Local API、Git、Obsidian、Quartz、未来 native 实现。
5. `cli`：Typer 命令行入口。
6. `web`：FastAPI + Jinja2 + HTMX 管理页面。

CLI、Web 和 Codex 都只能通过 `kb-core` 的应用服务访问数据，避免三套业务逻辑分叉。

## 4. 仓库和目录布局

建议 `D:\project\Knowlume` 作为 Git 仓库，并把知识数据、程序代码和生成物按边界分开：

```text
Knowlume/
├── AGENTS.md                    # 给 Codex/harness 的工作规则
├── README.md
├── LICENSE
├── pyproject.toml
├── src/kb/
│   ├── domain/
│   ├── application/
│   ├── ports/
│   ├── adapters/
│   │   ├── filesystem.py
│   │   ├── zotero.py
│   │   ├── obsidian.py
│   │   ├── git.py
│   │   ├── github.py
│   │   └── quartz.py
│   ├── index/
│   │   ├── sqlite.py
│   │   ├── fts.py
│   │   └── tokenizer.py
│   ├── cli/
│   └── web/
├── knowledge/
│   ├── sources/
│   │   ├── papers/
│   │   ├── web/
│   │   ├── books/
│   │   └── oss/
│   ├── notes/
│   │   ├── literature/
│   │   ├── concept/
│   │   ├── synthesis/
│   │   └── evergreen/
│   ├── snippets/
│   └── ai/
│       ├── artifacts/
│       └── tmp/
├── schemas/
├── templates/
├── migrations/
├── tests/
├── .cache/                       # 临时仓库克隆、解析缓存，不进 Git
├── derived/                      # 可重新生成内容，不进 Git
├── public-staging/               # 发布临时目录，不作为事实源
└── kb.sqlite                     # 可选本地索引，不进 Git
```

说明：

- 论文、网页和书籍的 PDF/EPUB/快照默认由 Zotero 管理；Knowlume 保存稳定的 source card 和 Zotero key。
- 如需在仓库内保存附件，应放在明确的附件策略目录并单独处理版权、体积和备份；第一版不把大型原始附件默认提交到 Git。
- `ai/tmp` 是 disposable；`ai/artifacts` 只有在明确保存后才进入版本管理。
- `.obsidian/workspace*`、`.obsidian/cache/`、SQLite、日志、临时 clone 和生成目录默认忽略。

## 5. 统一数据模型

### 5.1 对象类型

```text
source       原始资料的 source card
note         人类知识笔记
snippet      从 OSS 固定 commit 提取的少量重要代码
ai_artifact  AI 生成或 AI 辅助但尚未晋升为人类知识的内容
```

### 5.2 Note 类型和演化

| `note_type` | 作用 | 典型生命周期 |
|---|---|---|
| `literature` | 针对单个论文、网页或书籍的阅读笔记 | 随阅读补充 |
| `concept` | 对一个概念的长期理解 | 反复修改 |
| `synthesis` | 综合多个来源或多个笔记的结论 | 持续吸收证据 |
| `evergreen` | 较稳定、可复用和可发布的知识 | 低频演化 |

Note 的成熟度：

```text
seed -> developing -> mature -> evergreen
```

对象记录状态、工作流阶段和知识成熟度不能混用：

```text
record_status: active | archived | superseded
maturity: seed | developing | mature | evergreen
```

`record_status` 适用于所有对象，表示对象当前是否有效、归档或已被替代。Note 使用 `maturity` 表示知识成熟度；Source 另外使用 `workflow_stage` 表示处理进度：

```text
workflow_stage: inbox | reading | processed | integrated
```

其中 `integrated` 表示来源已经融入 concept 或 synthesis，而不只是收藏或处理过。Source 归档时设置 `record_status: archived`，而不是把 `archived` 作为工作流阶段。

### 5.3 基础 frontmatter

Source、Note、Snippet 和 AI Artifact 共享稳定字段；不同对象可增加专属字段：

```yaml
---
id: note_01KXXXX
kind: note
note_type: synthesis
title: Scaling Laws for LLMs
visibility: private
record_status: active
maturity: developing
created: 2026-08-20
updated: 2026-08-26
source_ids:
  - src_01KXXXX
  - src_01KYYYY
related_notes:
  - note_01KZZZZ
tags:
  - llm
  - scaling
supersedes: []
superseded_by: null
ai_assisted: true
review_status: reviewed
---
```

字段规则：

- `id` 是永久身份，创建后不因文件重命名而改变。
- `kind`、`note_type`、`visibility`、`record_status`、`workflow_stage`、`maturity` 使用受控词表。
- `record_status` 适用于所有对象；`workflow_stage` 只用于 Source；`maturity` 只用于 Note。
- `created` 和 `updated` 使用 ISO 日期或 ISO 8601 时间。
- `source_ids`、`related_notes` 是便于人类阅读的声明；索引器同时扫描正文链接。
- `supersedes` / `superseded_by` 用于替代关系，旧对象不删除，默认搜索降低优先级并提示新对象。
- `ai_assisted` 只表示是否使用过 AI，不能代替 `ai_artifact` 的审核状态。

### 5.4 Source card

Source card 不是论文正文，而是原始资料的稳定索引和访问入口：

```yaml
---
id: src_01KXXXX
kind: source
source_type: paper
title: Attention Is All You Need
visibility: private
record_status: active
workflow_stage: processed
canonical_url: https://arxiv.org/abs/1706.03762
zotero_key: ABCD1234
year: 2017
authors:
  - Vaswani et al.
captured_at: 2026-08-26
tags:
  - transformer
---
```

不得把机器相关的绝对路径写入 source card，例如 `D:\Zotero\storage\...`。通过 `zotero_key` 交给 Zotero adapter 解析附件。

### 5.5 Locator 和稳定 section

Phase 0 必须按 `source_type` 冻结 locator schema。Locator 必须同时满足人类可读、机器可解析和可校验，不能使用无法规范化的自由文本作为唯一定位信息：

```text
paper: page/page_label, section, figure, table
web: captured_at, heading_path, paragraph, content_hash
book: edition/isbn, chapter, page/location
oss: commit, path, start_line, end_line, symbol
```

- 每种来源只允许使用其 schema 定义的字段，并规定必填字段、规范化规则和 `locator_version`。
- 网页 locator 必须绑定抓取时间或快照内容哈希，避免页面变化后仍把旧位置解释为当前内容。
- OSS locator 必须固定 commit；只有分支名而没有 commit 的定位不视为可追溯。
- 无法精确定位时可以记录部分 locator，但必须由 `kb lint` 给出 warning；公共发布采用更严格规则。
- Note 内允许被关系引用的 section 必须具有永久 `section_id`。标题可以修改，`section_id` 不随标题和文件名变化。
- 第一版关系目标使用 `to_id + to_section_id` 表示稳定 section；对象级关系的 `to_section_id` 统一投影为空字符串。
- `section_id` 的字符集、唯一性、Markdown 表示和重命名规则在 Phase 0 与 locator schema 一起冻结。

### 5.6 笔记的 provenance 分区

每篇人类笔记固定区分三类内容：

```markdown
# Transformer Attention

## 原文事实

- Transformer 使用 multi-head attention。
  - source: src_01KXXXX
  - locator: { page: 4, section: "3.2" }

## 我的理解

- Multi-head 的价值不仅是增加容量，也提供了多个关系子空间。

## AI 推论

- AI 推测这种设计可能有助于……

## 观点演化

### 2026-08

最初的理解是……

### 2026-11

加入新证据后，修正为……
```

内部统一标记：

```text
fact
interpretation
ai_inference
```

事实单元必须能绑定 `source_id + locator`。解释和 AI 推论可以没有原文 locator，但必须保持明确分区。

### 5.7 AI Artifact

AI 生成内容默认单独存放：

```yaml
---
id: ai_01KXXXX
kind: ai_artifact
artifact_type: summary
title: Candidate summary for Attention Is All You Need
visibility: private
record_status: active
review_status: unreviewed
created: 2026-08-26
source_ids:
  - src_01KXXXX
generated_by: codex
prompt_ref: null
---
```

晋升流程：

```text
AI Artifact -> Human Review -> Accept/Reject -> Promote -> Note
```

未经人工晋升的 AI artifact：

- 不进入默认 `kb search`。
- 不进入默认 `kb context`。
- 不得出现在事实区。
- 不得参与 public publish。
- 只有 `--include-ai` 或明确 review 流程才可读取。

## 6. 来源类型和保存策略

### 6.1 论文

- Zotero 保存 metadata 和 PDF/附件。
- Knowlume 保存 `source_type: paper` 的 source card、canonical URL、Zotero key、标签和阅读状态。
- 阅读内容进入 literature note，事实使用页码、章节、图表等 locator。
- 不把 Zotero storage 的绝对路径提交到 Git。

### 6.2 网页

- 保存 canonical URL、抓取时间和必要的标题/作者信息。
- 网页快照或 PDF 由 Zotero 保存；网页可能变化，因此 `captured_at` 必须保留。
- 笔记中的网页事实尽量使用标题、heading、段落或快照页码定位。
- 入库时进行 URL 规范化和重复检查。

### 6.3 书籍

- 通过 ISBN、DOI、Zotero key 或用户提供的本地文件定位。
- PDF/EPUB 等原始资料优先由 Zotero 管理。
- Knowlume 保存 source card、章节笔记、页码定位和 concept/synthesis 关系。
- 不在第一版自研电子书阅读器。

### 6.4 开源项目

不长期本地保存完整仓库。Source card 保存：

```yaml
id: src_01KOSS
kind: source
source_type: oss
title: Example Project
canonical_url: https://github.com/org/repo
repo: org/repo
default_branch: main
commit: abc123...
license: Apache-2.0
visibility: private
record_status: active
workflow_stage: processed
```

- 默认只保存 URL、默认分支、固定 commit/tag、license、description 和 tags。
- 临时阅读使用 shallow/partial clone、sparse checkout 或其他可丢弃缓存，放在 `.cache/repos/`。
- 只把极重要代码保存为 snippet。
- snippet 必须记录 repo、commit、path、line range、license 和必要的改动说明。

```yaml
---
id: snip_01KXXXX
kind: snippet
source_type: oss
source_id: src_01KOSS
repo: org/repo
commit: abc123...
path: src/core.py
lines: 120-165
license: Apache-2.0
visibility: private
---
```

“合法性检查”只提供事实和风险提示，不把自动检查当作法律意见；无法确认的版权、许可证、转载或发布问题必须转人工确认。

## 7. 关系模型和知识演化

### 7.1 一等关系类型

```text
cites          Note -> Source 或 Source -> Source
derived_from   Note -> Source/Note
summarizes     Note -> Source
synthesizes    Note -> Source/Note
supports       Source/Note -> Source/Note/Section
contradicts    Source/Note -> Source/Note/Section
related_to     Note <-> Note 或 Source <-> Source
snippet_from   Snippet -> Source
supersedes     新对象 -> 旧对象
```

第一版不定义 Claim 对象，也不支持 Claim 级关系。关系默认指向完整对象；需要更细粒度时，只能指向带永久 `section_id` 的稳定 section。不得使用可变标题或索引重建时临时生成的 segment ID 作为长期关系目标。

关系必须有来源时，允许附加 `locator`、`reason` 和 `created_by`。正文中的 Wikilink/Markdown link 负责导航，frontmatter 和显式 relation block 负责语义，SQLite 只保存它们的 projection。

### 7.2 Merge、summary 和 supersede

- `summarizes` 表示一个笔记概括一个来源，不等于两个笔记合并。
- `synthesizes` 表示跨多个来源或笔记形成综合结论。
- `merge` 将重复或高度重叠的对象合并到一个目标对象；源对象保留并标记 `superseded`，历史和旧链接不丢。
- `supersede` 表示新对象取代旧对象，但不一定复制旧正文。
- 旧笔记默认保留，搜索结果显示替代提示；公共发布审计应阻止或提示指向已替代对象的链接。

示例：

```bash
kb note merge note_old --into note_new
kb note supersede note_old --by note_new
```

### 7.3 Git 的职责

Git 版本管理：

```text
Markdown / YAML
source cards
notes / snippets
schemas / templates
configuration
kb-core source code
```

默认不提交：

```text
大型 PDF / EPUB
Zotero storage
kb.sqlite
.cache/
derived/
logs/
temporary clones
ai/tmp/
```

`kb history <id>` 对 Git history 做友好投影，帮助回答观点何时出现、何时修改、哪些 commit 由人或 agent 产生。

## 8. SQLite 可重建索引

### 8.1 索引原则

```text
Markdown/YAML -> parser -> normalized projection -> SQLite
```

- SQLite 任何时候都可以删除。
- `index build` 增量更新，`index rebuild` 删除并完整重建。
- 索引记录 checksum、源文件路径和最后扫描时间，用于发现陈旧对象。
- 关系、标签和 provenance 都由文件重新投影。

### 8.2 第一版表

```text
objects(
  id primary key,
  kind,
  subtype,
  path,
  title,
  visibility,
  record_status,
  workflow_stage,
  created_at,
  updated_at,
  checksum
)

relations(
  from_id,
  to_id,
  to_section_id,
  relation_type,
  locator,
  reason,
  primary key(from_id, to_id, to_section_id, relation_type, locator)
)

segments(
  segment_id primary key,
  object_id,
  section_id,
  segment_type,
  heading,
  text,
  source_id,
  locator
)

tags(tag primary key)
object_tags(object_id, tag, primary key(object_id, tag))

fts_segments using FTS5(
  title, text, tags, object_id UNINDEXED,
  segment_type UNINDEXED, visibility UNINDEXED
)
```

实现时可增加 schema/version、parse errors、index metadata 等技术表，但不能让它们成为唯一事实源。

### 8.3 中文和英文搜索

- SQLite 默认 tokenizer 对连续中文文本不等价于中文分词。
- 第一版由 Python 做轻量中英文预处理，把中文词或可检索片段规范化后写入 FTS5。
- 不先开发 SQLite C tokenizer。
- 后续如需求明确，再评估 trigram、专业分词器或混合索引。

## 9. 三层搜索和 Codex 接入

### 9.1 L1 文件搜索

```bash
kb grep transformer
```

直接扫描原始文件，优点是永远可靠、无需索引，适合调试和确认事实源。

### 9.2 L2 SQLite FTS5

```bash
kb search "multi head attention"
kb search transformer --type note
kb search transformer --source paper
kb search transformer --visibility public
kb search transformer --section fact
```

返回标题、对象 ID、命中分段、highlight/snippet、匹配分数和 superseded 提示。支持 `--json`，便于 Codex 解析。

### 9.3 L3 Semantic Search 预留

先定义接口，不实现 embedding/vector DB：

```python
class SearchBackend(Protocol):
    def search(self, query: str, filters: SearchFilters) -> list[SearchResult]: ...

class FileSearchBackend(SearchBackend): ...
class FTSBackend(SearchBackend): ...
class SemanticSearchBackend(SearchBackend):  # later
    ...
```

未来可以增加：

```bash
kb semantic "attention 为什么有效"
```

### 9.4 Context Engineering 接口

```bash
kb get note_01KXXXX
kb context "transformer architecture"
kb search "scaling laws" --json
```

`kb context` 输出按 Sources、Facts、My Notes、Relevant Snippets 分组的可读上下文；默认排除未审核 AI 内容和私有对象泄漏。第一版通过 shell/CLI 接入 Codex，不需要 MCP。

根目录 `AGENTS.md` 应明确：目录边界、写入规则、`kb` 命令、fact/interpretation/ai_inference 规则、不能修改的原始资料位置和发布要求。

## 10. `kb` CLI 设计

### 10.1 五类能力

```text
Capture   快速入库
Organize  结构整理与关系发现
Inspect   查看、搜索、历史
Maintain  lint、doctor、review、索引维护
Publish   审计、构建、预览
```

### 10.2 命令总览

```text
kb init
kb status
kb scan

kb add [paper|web|book|repo] URL
kb inbox
kb process SOURCE_ID

kb source [list|show|open|sync]
kb note [new|show|link|merge|supersede]
kb snippet add

kb grep QUERY
kb search QUERY
kb get ID
kb context QUERY
kb related ID
kb backlinks ID
kb history ID

kb tidy [--dry-run|--apply]
kb organize
kb review

kb index [build|rebuild|status]
kb lint [--strict|--changed]
kb doctor

kb ai [list|review|promote]
kb publish [audit|build|preview]

kb serve
```

### 10.3 Capture：快速入库

支持显式类型：

```bash
kb add paper https://arxiv.org/abs/1706.03762
kb add web https://example.com/article
kb add book --isbn 978...
kb add repo https://github.com/org/repo
```

也支持自动识别：

```bash
kb add https://arxiv.org/...
kb add https://github.com/org/repo
kb add https://some-web-page
```

识别规则：arXiv/DOI -> paper，GitHub/GitLab repository -> oss，ISBN -> book，普通 URL -> web；`--type` 可覆盖识别结果。

入库流程：

```text
normalize -> duplicate check -> metadata -> adapter sync -> source card -> inbox -> index
```

快速入库默认设置 `record_status: active` 和 `workflow_stage: inbox`，不要求用户当场完成整理；以后通过 `kb inbox` 和 `kb process` 处理。

### 10.4 Organize：安全整理和结构发现

`kb tidy` 只改结构，不改知识含义：

- 规范 frontmatter 字段顺序和格式。
- 规范标签。
- 检查或建议文件名。
- 修复可确定的生成链接。
- 移除陈旧 cache 引用。
- 更新时间字段。

默认 `--dry-run`，只有 `--apply` 才写文件。

`kb organize` 只提出建议，不直接修改：

- 标题、标签、关键词和共同来源相似的潜在重复笔记。
- 缺少 synthesis 的 processed source。
- 可能应 `related_to`、`merge` 或 `supersede` 的对象。
- 未来可接入 semantic search，但第一版只使用字符串、标签和链接。

### 10.5 Inspect：快速理解知识库

```bash
kb status
kb source show src_01KXXXX
kb note show note_01KXXXX
kb backlinks note_01KXXXX
kb related note_01KXXXX
kb history note_01KXXXX
```

`kb status` 至少显示 Sources、Notes、Snippets、Paper/Web/Book/OSS 数量、Private/Public 数量、待审核 AI、Inbox、Indexed objects、最后索引时间和健康问题。

### 10.6 Maintain：lint、doctor、review

`kb lint` 检查知识和结构：

- schema、ID 唯一性、受控字段值。
- source/note ID 是否存在。
- 关系目标对象和 `section_id` 是否存在；第一版不得出现 Claim 级关系。
- broken links、public -> private 引用。
- fact 是否具有 source locator。
- AI artifact 是否拥有审核状态。
- snippet 是否有 repo、commit、path、lines、license。
- SQLite 是否与事实源一致。

```bash
kb lint
kb lint --strict
kb lint --changed
```

普通模式区分 `ERROR`、`WARN`、`INFO`；`--strict` 将 warning 按 error 处理，可用于 publish、CI 和 pre-commit。第一版允许部分事实 locator 缺失为 warning，但公共发布必须更严格。

`kb doctor` 检查运行环境而不是知识内容：

```text
Python / Git / SQLite FTS5 / Zotero Local API /
Obsidian vault / Quartz / Git repository
```

`kb review` 输出阅读债务和维护建议：

- 长期未处理 inbox。
- processed 但无 literature note 或 synthesis 的来源。
- 长期未更新的 developing note。
- 潜在重复概念。
- 待审核 AI artifact。
- 引用 superseded note 的公共笔记。

### 10.7 Publish：受控发布

```bash
kb publish audit
kb publish preview
kb publish build
```

发布审计必须检查：

- public note 是否依赖 private note/source/image。
- 是否存在 broken link、未解析引用或 superseded link。
- 是否包含未审核 AI artifact。
- 是否误带原始 PDF、EPUB、私有路径或临时文件。
- OSS snippet 的 license 和发布状态。
- copyright-sensitive 内容是否需要人工确认。

只有通过 audit 的 allowlist 对象才能复制到 `public-staging/`，再交给 Quartz adapter。发布不直接从整个私有 vault 过滤。

## 11. Adapter 和外部软件边界

### 11.1 Zotero adapter

- 通过 Zotero Local API（例如本地服务）访问数据。
- 不直接读取 `zotero.sqlite`。
- 通过 Zotero key 找到 item、metadata 和 attachment。
- 为 `kb source open` 返回可打开的本地附件。
- 将外部 metadata 映射成 source card，不把 Zotero schema 泄漏到 domain。

### 11.2 Obsidian adapter

- Obsidian 是人类 Markdown 编辑器，不是核心数据库。
- 支持普通 Markdown link 和 Wikilink 作为导航层。
- ID 负责身份，文件名负责可读性；重命名不能破坏 ID。
- 不依赖 `.obsidian` 私有状态。

### 11.3 Git adapter

- 提供 status、diff、history、commit hook 等能力。
- 支持 `kb history` 和 `kb lint --changed`。
- pre-commit 可阻止 duplicate ID、公共笔记依赖私有对象等严重错误。

### 11.4 Quartz adapter

- 只接收 `kb publish build` 生成的 public staging。
- 不直接把私有 vault 当站点源。
- 保留 Markdown/Wikilinks 兼容性，但发布边界由 Knowlume 决定。

### 11.5 未来 native adapter

领域层只依赖 `SourceStore`、`NoteStore`、`ReferenceManager`、`SearchBackend`、`Publisher` 等 port。未来替代 Obsidian、Zotero 或 Quartz 时，只替换 adapter，不迁移核心数据模型。

## 12. 管理页面

技术选型：

```text
FastAPI + Jinja2 + HTMX
Browser -> FastAPI -> kb-core
Typer   -> kb-core
```

第一版做 6 个页面：

1. Dashboard：来源、笔记、私有/公共、待审核 AI、Inbox 和索引状态。
2. Sources：按类型、record_status、workflow_stage、标签、更新时间和关联笔记查看来源。
3. Notes：按 note_type、maturity、visibility、record_status 和来源筛选。
4. Search：统一调用 `kb search` 的 FTS 结果和分段预览。
5. AI Review：查看、接受、拒绝、晋升 AI artifact。
6. Publish：显示公共对象、就绪状态、失败审计项和预览入口。

“Knowledge Health”是 Dashboard 的重点区域：

```text
Sources without notes
Notes without sources
Facts without source locator
Broken links
Unreviewed AI artifacts
Public -> Private links
Sources not indexed
Stale SQLite entries
```

第一版不做知识图谱可视化；先把健康指标和可操作错误做可靠。

## 13. 安全、隐私和合规边界

- 默认 private，任何新对象必须显式晋升为 public。
- AI 默认不可写事实区；写入事实区必须有 source ID 和 locator，并经过人类审核。
- `kb context` 默认不混入未审核 AI，不跨越 public/private 边界。
- public -> private link、private image、绝对本地路径和原始附件必须阻止发布。
- 许可证、版权和转载检查输出风险清单与证据，不替代法律判断。
- 日志不得默认记录完整私有正文或敏感附件内容。
- 未来如引入外部 LLM，必须增加显式“允许发送哪些对象”的策略；第一版优先本地文件和用户主动传递的上下文。

## 14. 阶段化实施计划

### Phase 0：冻结协议和边界

交付：

- `schemas/`：对象、frontmatter、relation、provenance、visibility schema。
- `templates/`：source card、四类 note、snippet、AI artifact 模板。
- `AGENTS.md`：Codex 工作规则。
- 目录布局、ID 规范、各 `source_type` 的 locator schema、稳定 `section_id` 语法、Git ignore 规则。
- 最小 fixtures 和 schema/lint 测试。

完成标准：任何工具都能读懂同一组 Markdown/YAML；事实、理解、AI 推论和发布状态有明确规则。

### Phase 1：kb-core、文件扫描和 Dashboard

交付：

- Python 包和 Ports & Adapters 骨架。
- Markdown/frontmatter parser。
- filesystem scanner、Source/Note domain model。
- `kb init`、`kb scan`、`kb status`、`kb serve`。
- Dashboard、Sources、Notes、Knowledge Health 页面。

完成标准：仅使用 Markdown/YAML 就能扫描、统计和展示知识库；删除空 SQLite 不影响事实文件。

### Phase 2：Zotero 和 Capture

交付：

- Zotero Local API adapter。
- `kb add` 自动识别和显式类型。
- `kb inbox`、`kb process`。
- `kb source list/show/open/sync`。
- 去重、canonical URL、Zotero key 和 source card 生成。

完成标准：论文、网页、书籍可以快速入库并回到 Zotero 原始资料；OSS 不会默认 clone 并保存完整仓库。

### Phase 3：SQLite FTS5 搜索

交付：

- SQLite schema、migration 和 indexer。
- `kb index build/rebuild/status`。
- L1 `kb grep`。
- L2 `kb search`，包含类型、来源、标签、可见性和 section 过滤。
- 中文轻量预处理、highlight/snippet、`--json` 输出。

完成标准：删除 `kb.sqlite` 后能够重建；文件搜索和 FTS 搜索结果可以互相解释。

### Phase 4：Codex 接入和 AI 边界

交付：

- `kb get`、`kb context`、`kb search --json`。
- `AGENTS.md` 和 harness 使用示例。
- AI artifact 存储、review_status、默认排除规则。
- `kb ai list/review/promote`。
- `kb lint`、`kb doctor`、`kb lint --changed`。

完成标准：Codex 可以通过 CLI 获得可追溯上下文；AI 不能静默进入事实层或公共站点。

### Phase 5：知识演化和发布

交付：

- 关系解析、backlinks、related、history。
- `kb note link/merge/supersede`。
- `kb tidy`、`kb organize`、`kb review`。
- public/private allowlist、publish audit/build/preview。
- public staging 和 Quartz adapter。
- Git pre-commit 集成。

完成标准：知识可总结、关联、合并和替代而不丢历史；公共发布能阻止私有依赖和未审核 AI 内容。

### Phase 6：高级能力（后置）

只有前述基础稳定后再评估：

- semantic/hybrid search、embedding、reranker。
- MCP adapter（作为 CLI API 的 facade）。
- native editor、native reference manager、browser extension。
- knowledge graph、图可视化、多 agent 阅读流程。
- 更丰富的自动化和外部模型路由。

## 15. 第一版明确不做

第一版不做以下内容：

```text
不做视频资料管理
不做 vector database
不做 RAG pipeline
不做 semantic search 实现
不做 MCP server
不做 graph database / knowledge graph visualization
不做 multi-agent 和 agent memory
不做自研 PDF/EPUB 阅读器
不做自研文献管理器
不做浏览器插件
不做云同步服务
不长期保存完整 OSS repository
不把 PDF/EPUB/Zotero storage 默认放进 Git
不让 AI 直接修改 fact 区
不把整个私有 vault 直接交给 Quartz
不把业务逻辑分别实现于 CLI 和 Web
```

## 16. 第一版核心命令范围

为了可控交付，第一批只实现：

```text
kb init
kb add
kb inbox
kb source show
kb source open
kb note new
kb grep
kb search
kb index rebuild
kb status
kb lint
kb doctor
kb serve
```

第二批实现：

```text
kb tidy
kb related
kb backlinks
kb history
kb review
kb context
kb publish
```

第三批实现：

```text
kb organize
kb note merge
kb note supersede
kb ai promote
semantic search
```

## 17. 验收清单

### 数据可靠性

- [ ] 所有对象有唯一稳定 ID。
- [ ] Markdown/YAML 是可读、可迁移、可版本管理的事实源。
- [ ] 删除 SQLite 后能够完整 rebuild。
- [ ] Git diff 能看出知识演化，历史对象不因 merge/supersede 被删除。

### provenance 和 AI 隔离

- [ ] Fact、Interpretation、AI Inference 有固定分区和内部类型。
- [ ] Fact 能关联 source 和 locator，缺失时被 lint 发现。
- [ ] paper/web/book/oss locator 符合各自冻结的 schema，且能够稳定回到原始位置或固定快照。
- [ ] 第一版关系只指向对象或永久 `section_id`，不支持 Claim 级关系。
- [ ] AI artifact 默认 private/unreviewed，默认搜索和发布排除。
- [ ] 晋升流程有明确的人类审核动作。

### 来源和适配器

- [ ] paper/web/book/oss 都有 source card。
- [ ] Zotero key 可打开原始资料，source card 不含绝对路径。
- [ ] OSS 默认只保存 metadata、commit 和必要 snippet。
- [ ] Obsidian、Zotero、Quartz 可以被替换而不改变 domain model。

### CLI、搜索和管理页

- [ ] 支持快速 `kb add` 和 inbox 延后整理。
- [ ] `grep` 不依赖索引，`search` 使用 SQLite FTS5。
- [ ] Codex 能通过 `get/search/context --json` 获得受控上下文。
- [ ] `lint` 和 `doctor` 分工清晰，`review` 能显示阅读债务。
- [ ] Dashboard 能显示数量、状态、健康问题和索引状态。

### 发布

- [ ] 新对象默认 private。
- [ ] 只有 allowlist 对象进入 public staging。
- [ ] public -> private、未审核 AI、私有附件和敏感路径会阻止发布。
- [ ] 发布前有可审计的结果和可预览产物。

## 18. 最终目标

Knowlume 的稳定内核可以概括为：

```text
Markdown/YAML + 原始资料引用
        +
明确 provenance
        +
Git 历史
        +
可重建 SQLite FTS 索引
        +
kb CLI control plane
        +
FastAPI 管理页
        +
可替换的 Zotero/Obsidian/Quartz adapters
        +
严格的 AI 和 public/private 边界
```

它不是“收藏了多少资料”的统计系统，而是一个能回答以下问题的长期知识系统：

```text
这个结论来自哪里？
我什么时候这样理解？
后来为什么改变？
哪些来源支持或反驳它？
这个资料是否已经融入长期知识？
哪些内容可以安全公开？
AI 生成的内容是否经过人工确认？
```

实施顺序必须坚持：先冻结模型和边界，再做可靠的文件层、CLI、FTS 和 Dashboard，最后才增加 semantic search、MCP 和更复杂的 AI 能力。
