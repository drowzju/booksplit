---
name: splitbook
description: 智能拆解和分析PDF书籍，生成多维度结构化知识输出，包括超短摘要、分章节摘要、知识导图、作者论证链、Deep Research扩展和可问答知识库。
---

# 拆书技能 (Split Book Skill)

智能拆解PDF书籍，生成包含超短摘要、章节分析、知识导图、论证链、Deep Research扩展等多维度结构化报告。

---

## 使用方法

```
/splitbook @<PDF文件路径>
```

输出目录自动创建在PDF文件同级，命名为 `{pdf文件名}_output/`。

---

## 核心原则：必须使用提供的脚本

**严格禁止自行创建脚本**。本技能目录下已提供完整的工具脚本（`pdf_analyzer.py`、`pdf_split_part.py`、`save_chapters.py`、`generate_report.py`），Agent 必须直接调用这些脚本，而不是自行编写替代脚本。

- 所有 PDF 操作（校准、拆分、文本提取）必须通过 `pdf_analyzer.py` 完成
- 章节分析结果保存必须通过 `save_chapters.py` 完成
- 报告生成必须通过 `generate_report.py` 完成
- 仅在 `pdf_analyzer.py` 无法提取 TOC 时，才使用 `pdf_split_part.py`

---

## 架构概述：主Agent + 子Agent

```
主Agent（Orchestrator）
├── 步骤1：页码校准 + 导出 book_structure.json
├── 步骤2：拆分PDF为章节文件 + 提取章节文本为 .txt
├── 步骤3：派发子Agent（每章一个），各自输出 chapter_XX.json
└── 步骤4：汇总所有 chapter_XX.json → 填充模板 → 生成报告
```

**子Agent触发条件**：总页数 > 100。否则主Agent直接处理。

**子Agent批处理策略**：
- 短章节（<=20页）：主Agent可一次性合并 2-3 个相邻章节传给单个子Agent
- 标准章节（>20页）：单章一个子Agent


子Agent只读取 `.txt` 文件（纯文本），不直接操作PDF。

---

## 工具说明：两个脚本的分工

| 脚本 | 适用场景 |
|------|----------|
| `pdf_analyzer.py` | PDF有内置TOC；主力工具，负责校准、提取、拆分 |
| `pdf_split_part.py` | PDF无TOC，或需要手动指定章节起始页时的备选 |

**章节拆分策略**：
- **两级目录分析**：先分析两级目录结构，优先使用一级目录（Part/部分）作为切分单位
- **智能细分**：仅当某个一级部分页数 > 100页时，才使用其下的二级章节进行细分
- **保留原书自然结构**：直接使用PDF内置的完整TOC，保持章节完整性，不进行强制合并
- **章节类型识别**：自动识别章节类型（main/aux），供主Agent参考处理策略

**主Agent vs 子Agent 分工**：

| 内容类型 | 章节特征 | 处理方式 | 说明 |
|---------|---------|---------|------|
| **正文章节** | 第X章、Chapter X、Part X | **子Agent处理** | 每个正文章节独立分析，确保内容完整性 |
| **辅助内容** | 前言、目录、附录、后记、参考文献 | **主Agent处理** | 内容较短，主Agent直接分析或合并处理 |



优先使用 `pdf_analyzer.py`。TOC条目为空或少于3条时，改用 `pdf_split_part.py`，
并在步骤1末尾手动编写 `book_structure.json`（格式见下）。

---

## 主Agent工作流程

### 步骤1：页码校准 + 导出结构

#### 1a. 运行校准

```bash
python pdf_analyzer.py calibrate <pdf_path>
```

输出示例：
```json
{
  "offset": 3,
  "confidence": "high",
  "verified_by": "第一章 并发的本质",
  "toc_page": 15,
  "actual_page": 18
}
```

- `offset` 即后续所有命令的 `--offset N` 参数值
- `confidence` 为 `low` 时，需人工确认：提取 `toc_page` 和 `actual_page` 两页的文本，
  目测哪一页包含章节标题，手动确定 offset

#### 1b. 导出 book_structure.json

```bash
python pdf_analyzer.py export <pdf_path> <output_dir>/book_structure.json --offset <N>
```

`book_structure.json` 结构：
```json
{
  "pdf_name": "书名",
  "total_pages": 220,
  "chapter_count": 12,
  "page_offset": 3,
  "chapters": [
    {
      "index": 1,
      "level": 1,
      "title": "第一部分 XXX",
      "chapter_type": "main",
      "suggested_handler": "sub_agent",
      "start_page": 18,
      "end_page": 150,
      "page_count": 132,
      "is_part_header": true,      // 一级部分标记（页数>100时会细分）
      "sub_chapters": [],          // 包含的二级章节索引
      "status": "pending",
      "json_file": null,
      "txt_file": null
    },
    {
      "index": 2,
      "level": 2,                // 二级章节（当一级部分>100页时出现）
      "title": "第一章 YYY",
      "parent_title": "第一部分 XXX",  // 所属一级部分
      "chapter_type": "main",
      "suggested_handler": "sub_agent",
      "start_page": 18,
      "end_page": 45,
      "page_count": 27,
      "status": "pending",
      "json_file": null,
      "txt_file": null
    }
  ]
}
```

**字段说明**：
- `chapter_type`: 章节类型
  - `"main"`: 正文章节（第X章、Chapter X），**子Agent处理**
  - `"aux"`: 辅助内容（前言、附录等），**主Agent处理**
  - `"unknown"`: 无法识别，由主Agent判断
- `suggested_handler`: 建议的处理者
  - `"sub_agent"`: 派发子Agent处理
  - `"main_agent"`: 主Agent直接处理
- `status`: 处理状态，`pending` / `done` / `failed`

---

### 步骤2：拆分PDF + 提取章节文本

```bash
# 按章节拆分PDF
python pdf_analyzer.py split <pdf_path> <output_dir> --offset <N>

# 提取各章节文本为 .txt（单章>100页自动采样）
python pdf_analyzer.py extract_text <pdf_path> <output_dir> --offset <N>
```

`extract_text` 命令：
- 单章 ≤ 100页：全文提取
- 单章 > 100页：自动按比例采样（前20% + 中间40%中心区 + 后20%，其余页只保留段落首行）
  输出文本开头会有 `[SAMPLED]` 标记，需在子Agent prompt中告知此章为采样分析

完成后 `output_dir` 内容：
```
book_structure.json
{书名}_ch01_{标题}.pdf
{书名}_ch01_{标题}.txt      ← 子Agent读取这个
{书名}_ch02_{标题}.pdf
{书名}_ch02_{标题}.txt
...
```

更新 `book_structure.json` 中每章的 `txt_file` 字段为对应 `.txt` 路径。



---

### 步骤3：章节分析与派发

**主Agent预处理**：

在派发子Agent之前，主Agent根据 `book_structure.json` 的 `chapter_type` 和 `suggested_handler` 字段进行分流：

```python
main_chapters = [ch for ch in chapters if ch['chapter_type'] == 'main']
aux_chapters = [ch for ch in chapters if ch['chapter_type'] == 'aux']

# 正文章节 → 子Agent处理
for ch in main_chapters:
    dispatch_subagent(ch)

# 辅助内容 → 主Agent直接处理
for ch in aux_chapters:
    analyze_by_main_agent(ch)
```

**辅助内容处理策略**（主Agent直接处理）：

| 辅助类型 | 处理方式 | 说明 |
|---------|---------|------|
| 前言/简介 | 主Agent读取txt，提取1-2个key_points | 作为全书背景介绍 |
| 附录 | 可选处理，内容多则采样 | 技术书籍附录可能有价值 |
| 参考文献/索引 | 可跳过分析 | 通常无需深入分析 |
| 后记/致谢 | 可跳过分析 | 除非包含重要总结内容 |

辅助内容分析结果直接写入 `chapter_XX.json`，无需启动子Agent。

---

**子Agent并行策略**（仅处理正文章节）：

| 策略 | 适用场景 | 并行数建议 |
|------|----------|-----------|
| 顺序执行 | 正文章节 ≤ 5，或总页数 < 100 | 1 |
| 低并行 | 正文章节 5-12，有依赖关系（前后章关联强） | 3-5 |
| 高并行 | 正文章节 > 12，章节独立性强 | 8-10 |
| 批量合并 | 多短正文章节（每章 < 10页） | 合并后 3-5 |

**子Agent超时设置**：
- 短章（<20页）：120秒
- 标准章（20-50页）：180秒
- 长章（>100页，采样）：240秒

**失败重试策略**：
1. 首次失败：记录错误，继续下一章
2. 所有章节尝试完成后：汇总失败列表
3. 对失败章节重试一次（可调整Prompt要求简化输出）
4. 二次失败：标记 `status: "failed"`，报告中显示降级提示

---

**子Agent Prompt模板**（仅用于正文章节）：

```
你是一个书籍章节分析助手。请读取以下路径的文本文件，提取结构化信息。
仅输出合法JSON，不要包含任何其他文字、注释或markdown代码块。

文件路径：{{txt_file}}
章节信息：第{{index}}章《{{title}}》，原书第{{start_page}}-{{end_page}}页，共{{page_count}}页
{{#if sampled}}注意：此章文本为采样提取（前20%+中间40%+后20%），非全文，分析时请注明"采样分析"。{{/if}}
{{#if multi_chapter}}注意：此文本包含多个短章节，请分别分析每个子章节的核心内容。{{/if}}

根据内容长度调整提取要求：
- 极短章（<5页）：提取 1-2 个 key_points，core_question 可简写
- 短章（5-15页）：提取 2-3 个 key_points
- 标准章（15-50页）：提取 3-5 个 key_points
- 长章（>50页）：提取 4-6 个 key_points，重点关注章节首尾和中间核心段落

输出格式：
{
  "chapter_index": {{index}},
  "title": "{{title}}",
  "sampled": {{true|false}},
  "page_count": {{page_count}},
  "core_question": "本章试图回答的核心问题（1句话，极短章可省略）",
  "key_points": [
    "论点1（按内容长度提取2-6条）",
    "论点2"
  ],
  "key_cases": [
    { "case": "案例描述（如有）", "page": 23 }
  ],
  "key_quotes": [
    { "quote": "原文（仅保留不可替代的表述）", "page": 25 }
  ],
  "entities": {
    "people": [],
    "companies": [],
    "events": []
  },
  "argument_logic": "本章论证逻辑一句话概括，因→果结构",
  "counter_arguments": ["作者提及的反对观点（如有）"]
}
```

**错误处理**：
- 子Agent返回格式错误：主Agent尝试从输出中提取JSON，失败则将该章 `status` 置为 `failed`
- 失败章节自动重试一次，仍失败则跳过，继续后续章节
- 最终报告中失败章节卡片显示降级提示："此章分析失败，可单独重新运行"
- 不因单章失败阻断整体流程

完成后将各章 `status` 更新为 `done` 或 `failed`，`json_file` 填入输出路径，
并将更新后的 `book_structure.json` 写回磁盘。

---

### 步骤4：汇总生成报告

**4a. 收集子Agent分析结果**

子Agent完成章节分析后，主Agent使用 `save_chapters.py` 保存结果：

```bash
python save_chapters.py <output_dir> '<chapter_json_string>'
```

示例（单章）：
```bash
python save_chapters.py ./book_output '{"index":1,"title":"第1章","core_question":"..."}'
```

示例（多章）：
```bash
python save_chapters.py ./book_output '[{"index":1,...},{"index":2,...}]'
```

此脚本会：
- 保存每个章节为 `chapter_XX.json`
- 自动更新 `book_structure.json` 的 `status` 和 `json_file` 字段

**4b. 生成HTML报告**

所有章节分析完成后，生成包含丰富可视化图表的最终报告：

```bash
python generate_report.py <output_dir>
```

报告包含：
- **思维导图**：使用矩形树状结构（xmind风格）展示书籍层级结构，无节点数量限制
  - 根节点：书名
  - 一级节点：主要部分（Part）标题，可折叠/展开
  - 二级节点：子章节标题，悬停显示完整core_question
  - 无子章节时：显示core_question和关键论点
- **章节详情**：完整的章节分析卡片（含"论证逻辑"section）

输出：`book_output/book_analysis_report.html`（浏览器直接打开）

**报告生成优化**：

`generate_report.py` 生成可视化图表时，根据两级目录结构智能展示：

**思维导图**（HTML嵌套树状结构）：
- 根节点：书名（accent色矩形）
- 一级节点：主要部分（Part）标题，不限制数量，支持折叠/展开
- 二级节点：子章节标题，无数量限制，悬停显示core_question
- 无子章节时：自动显示该章节的core_question和key_points作为子节点
- 过滤辅助内容（chapter_type == 'aux'的一级章节）

**标题智能提取策略**：
1. 中文书籍：提取"第X章" + 前10字关键词（保留完整语义）
2. 英文书籍：提取"Chapter X/Part X" + 前3个单词
3. 超长标题智能截断

**非章节内容自动过滤**：
- 纯数字（年份、页码）
- 时间标记（"2018年"、"2023年"等）
- 非主线内容（"前言"、"附录"等辅助内容）

**报告模板变量**（供主Agent参考）：

| 占位符 | 数据来源 | HTML格式 |
|--------|----------|----------|
| `{{BOOK_TITLE}}` | `book_structure.json` → `pdf_name` | 纯文本 |
| `{{TOTAL_PAGES}}` | `book_structure.json` → `total_pages` | 数字 |
| `{{CHAPTER_COUNT}}` | `book_structure.json` → `chapter_count` | 数字 |
| `{{GENERATE_TIME}}` | 当前时间 | `YYYY-MM-DD HH:mm` |
| `{{BOOK_WHAT_ABOUT}}` | 主Agent综合各章 `key_points` 生成 | 1-2句话 |
| `{{KEY_POINTS}}` | 全书最重要3条论点 | `<div class="key-point"><span class="key-point-number">①</span>内容</div>` × 3 |
| `{{KEY_CONCLUSIONS}}` | 主Agent提炼5条结论 | `<li>` × 5 |
| `{{CORE_CONCEPTS}}` | 各章 `entities` 合并 + 高频术语 | `<span class="tag">词</span>` |
| `{{CHAPTER_NAV}}` | `chapters` 列表 | `<a href="#ch-N" class="nav-item chapter-link">第N章 标题</a>` |
| `{{MERMAID_MINDMAP}}` | 主Agent基于全书结构生成 | HTML嵌套树状结构（ul/li/details） |
| `{{CHAPTER_SUMMARIES}}` | 各章JSON → HTML卡片 | 见章节卡片模板 |
| `{{ARGUMENT_STEPS_DETAIL}}` | 各章 `argument_logic` 展开 | `<div class="card">` |
| `{{DEEP_RESEARCH_CONTENT}}` | 主Agent针对各核心论点生成扩展建议 | `<div class="research-item">` |
| `{{TOPIC_1}}` | 全书最核心概念 | 纯文本 |
| `{{KB_INDEX}}` | 各章 `entities` 合并去重 | `<div class="kb-item">` |

**章节卡片HTML模板**（填充 `{{CHAPTER_SUMMARIES}}`，注意：无 `onclick`，由模板JS统一处理）：

```html
<div class="chapter-summary" id="ch-{{INDEX}}">
  <div class="chapter-header">
    <h4>{{TITLE}}{{#if SAMPLED}} <small style="color:var(--text-secondary)">[采样]</small>{{/if}}</h4>
    <span class="chapter-pages">P{{START_PAGE}}–{{END_PAGE}}</span>
  </div>
  <div class="chapter-content">
    <div class="chapter-section">
      <div class="chapter-section-title">核心问题</div>
      <p>{{CORE_QUESTION}}</p>
    </div>
    <div class="chapter-section">
      <div class="chapter-section-title">关键论点</div>
      <ul>
        <li>论点1</li>
        <!-- 每条 key_points 一个 <li> -->
      </ul>
    </div>
    <div class="chapter-section">
      <div class="chapter-section-title">典型案例</div>
      <!-- 每条 key_cases 一个 <div class="quote"> -->
      <div class="quote">案例描述<span class="quote-source">p.23</span></div>
    </div>
    <!-- 若 key_quotes 非空 -->
    <div class="chapter-section">
      <div class="chapter-section-title">原文引用</div>
      <div class="quote">引用文字<span class="quote-source">p.25</span></div>
    </div>
    <!-- 若 counter_arguments 非空 -->
    <div class="chapter-section">
      <div class="chapter-section-title">反对观点</div>
      <ul><li>反对观点1</li></ul>
    </div>
    <!-- 若 status == "failed" -->
    <div class="chapter-section" style="color:var(--text-secondary)">
      ⚠️ 此章分析失败，可单独重新运行子Agent处理。
    </div>
  </div>
</div>
```

---

## 工具脚本说明

| 脚本 | 功能 | 主Agent/子Agent |
|------|------|----------------|
| `pdf_analyzer.py` | 提取目录、页码校准、PDF拆分、文本提取 | 主Agent |
| `pdf_split_part.py` | 按手动指定页码拆分PDF（无TOC时用） | 主Agent |
| `save_chapters.py` | 保存子Agent分析结果，更新 `book_structure.json` | 主Agent |
| `generate_report.py` | 从分析结果生成可视化HTML报告 | 主Agent |

---

## 输出目录结构

```
{pdf文件名}_output/
├── book_analysis_report.html   ← 最终报告，浏览器直接打开
├── book_structure.json         ← 结构元数据（含各章 status）
├── {书名}_ch01_{标题}.pdf      ← 拆分后章节PDF
├── {书名}_ch01_{标题}.txt      ← 章节纯文本（子Agent读取）
├── {书名}_ch01_{标题}.json     ← 子Agent分析结果（中间产物）
├── {书名}_ch02_{标题}.pdf
├── {书名}_ch02_{标题}.txt
├── {书名}_ch02_{标题}.json
└── ...
```

---

## 注意事项

**1. 章节结构保护原则**
- **20章是上限而非目标**：原书有12章就保持12章，不要强行拆成20章
- **正文章节不得切割**：第X章、Chapter X等正文章节必须保持完整
- **辅助内容可合并**：前言、附录等可与相邻章节合并处理
- **合并优先级**：辅助内容 > 短正文章节，尽量避免合并正文章节
- **合并标识**：合并后的章节标题用 " + " 连接，如 `前言 + 第1章 概述`

**2. 主Agent vs 子Agent 分工**
- **子Agent只处理正文章节**：确保每个正文章节被完整分析
- **主Agent处理辅助内容**：前言、附录、后记等由主Agent直接处理或跳过
- **章节类型识别**：`book_structure.json` 中的 `chapter_type` 和 `suggested_handler` 字段供参考

**3. 子Agent效率优化**

为提升子Agent处理效率，建议主Agent采用以下策略：

| 场景 | 处理建议 |
|------|----------|
| **单章 < 10页** | 主Agent可直接将相邻短章合并，一次性传入多个章节的 `.txt` 内容 |
| **单章 10-50页** | 标准模式，单章一个子Agent |
| **单章 > 100页** | 自动启用采样模式（前20% + 中间40% + 后20%），子Agent收到 `[SAMPLED]` 标记 |
| **超长章节 > 100页** | 考虑按子标题手动拆分后再分析 |

**批量子Agent调用建议**：
```
# 低并行度（推荐）：每次同时运行 3-5 个子Agent
# 高并行度：章节独立性强时，可同时运行 8-10 个
# 避免：同时启动 >10 个子Agent，可能造成系统资源竞争
```

**子Agent输出优化**：
- 要求子Agent严格输出JSON，不输出解释性文字
- 若章节内容极少（<5页），可减少 `key_points` 数量要求（3条→2条）
- 对于纯案例/附录章节，可跳过 `core_question` 提取

**4. 页码偏移必须执行**
校准结果 `confidence == "low"` 时不可跳过人工验证。偏移错误会导致章节切割错位，
且错误会传递到所有后续步骤，难以事后修复。

**5. 子Agent只读 .txt，不读 .pdf**
这是执行层的硬约束。步骤2的 `extract_text` 命令必须在步骤3之前完成。

**6. 采样章节的分析局限**
`[SAMPLED]` 章节的分析结果可靠性低于全文章节，报告卡片中会显示"[采样]"标记。
如需更精确分析，可对该章单独运行子Agent并传入 `--sample` 关闭的全文版本。

**7. 章节卡片不写 onclick**
`report_template.html` 已通过事件委托统一处理折叠逻辑，章节卡片中不要添加内联
`onclick` 属性，否则会触发两次导致展开后立即收起。

**8. 输出语言与原书一致**
- 生成的所有分析内容（core_question、key_points、argument_logic、章节摘要等）
  必须使用**与原书相同的语言**。
- 原书为英文 → 报告用英文；原书为中文 → 报告用中文；混合语言则正文用原书主体语言。
- HTML模板中的固定标签（如"核心问题"、"关键论点"等section标题）可保持中文，
  但章节内容的提取、总结、分析文字必须与原书语言一致。
- 子Agent Prompt中应明确告知此规则，避免默认输出中文。

**8. 必须使用提供的脚本，禁止自行创建**
- 所有 PDF 操作必须通过 `pdf_analyzer.py`，结果保存通过 `save_chapters.py`，
  报告生成通过 `generate_report.py`。
- Agent 不得自行编写 Python 脚本替代上述工具。
- 无 TOC 时才使用 `pdf_split_part.py`。
