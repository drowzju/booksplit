---
name: splitbook
description: 智能拆解和分析PDF书籍，生成多维度结构化知识输出，包括超短摘要、分章节摘要、知识导图、作者论证链、Deep Research扩展和可问答知识库。
---

# 拆书技能 (Split Book Skill)

智能拆解PDF书籍，生成包含超短摘要、章节分析、知识导图、论证链、Deep Research扩展等多维度结构化报告。

---

## 使用方法

```
/splitbook <PDF文件路径>
```

输出目录自动创建在PDF同级，命名为 `{pdf文件名}_output/`。

---

## 架构概述：主Agent + 子Agent

```
主Agent（Orchestrator）
├── 步骤1：页码校准 + 导出 book_structure.json
├── 步骤2：拆分PDF为章节文件 + 提取章节文本为 .txt
├── 步骤3：派发子Agent（每章一个），各自输出 chapter_XX.json
└── 步骤4：汇总所有 chapter_XX.json → 填充模板 → 生成报告
```

**子Agent触发条件**：章节数 ≥ 3，或总页数 > 80。否则主Agent直接处理。

子Agent只读取 `.txt` 文件（纯文本），不直接操作PDF。这是架构的关键约束——
子Agent无法通过文件路径打开PDF，必须由主Agent预先提取好文本再传递。

---

## 工具说明：两个脚本的分工

| 脚本 | 适用场景 |
|------|----------|
| `pdf_analyzer.py` | PDF有内置TOC；主力工具，负责校准、提取、拆分 |
| `pdf_split_part.py` | PDF无TOC，或需要手动指定章节起始页时的备选 |

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
  "chapter_count": 8,
  "page_offset": 3,
  "chapters": [
    {
      "index": 1,
      "level": 1,
      "title": "第一章 XXX",
      "start_page": 18,
      "end_page": 42,
      "page_count": 25,
      "status": "pending",
      "json_file": null,
      "txt_file": null
    }
  ]
}
```

`status` 字段用于主Agent追踪进度，取值：`pending` / `done` / `failed`。

---

### 步骤2：拆分PDF + 提取章节文本

```bash
# 按章节拆分PDF
python pdf_analyzer.py split <pdf_path> <output_dir> --offset <N>

# 提取各章节文本为 .txt（单章>50页自动采样）
python pdf_analyzer.py extract_text <pdf_path> <output_dir> --offset <N>
```

`extract_text` 命令：
- 单章 ≤ 50页：全文提取
- 单章 > 50页：自动按比例采样（前20% + 中间40%中心区 + 后20%，其余页只保留段落首行）
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

### 步骤3：派发子Agent并行分析章节

对每个章节启动独立子Agent，传入其 `.txt` 文件路径和元数据。

**子Agent Prompt模板**：

```
你是一个书籍章节分析助手。请读取以下路径的文本文件，提取结构化信息。
仅输出合法JSON，不要包含任何其他文字、注释或markdown代码块。

文件路径：{{txt_file}}
章节信息：第{{index}}章《{{title}}》，原书第{{start_page}}-{{end_page}}页
{{#if sampled}}注意：此章文本为采样提取，非全文，分析时请注明"采样分析"。{{/if}}

输出格式：
{
  "chapter_index": {{index}},
  "title": "{{title}}",
  "sampled": {{true|false}},
  "core_question": "本章试图回答的核心问题（1句话）",
  "key_points": [
    "论点1（必填，3-5条）",
    "论点2"
  ],
  "key_cases": [
    { "case": "案例描述（必填）", "page": 23 }
  ],
  "key_quotes": [
    { "quote": "原文（选填，仅在表述不可替代时填写）", "page": 25 }
  ],
  "entities": {
    "people": [],
    "companies": [],
    "events": []
  },
  "argument_logic": "本章论证逻辑一句话概括，用因→果结构（必填）",
  "counter_arguments": ["选填，作者提及的反对观点"],
  "relation_to_book": "本章在全书中的角色：承接/转折/总结/独立（必填）"
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

读取所有 `status == "done"` 的 `chapter_XX.json`，主Agent执行全书级分析，
填充 `report_template.html` 模板变量，生成 `book_analysis_report.html`。

**模板变量对照表**：

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
| `{{CHAPTER_RELATIONSHIPS}}` | 各章 `relation_to_book` 串联 | 1段话 |
| `{{CHAPTER_NAV}}` | `chapters` 列表 | `<a href="#ch-N" class="nav-item chapter-link">第N章 标题</a>` |
| `{{MERMAID_MINDMAP}}` | 主Agent基于全书结构生成 | mindmap语法，节点≤15字 |
| `{{CHAPTER_SUMMARIES}}` | 各章JSON → HTML卡片 | 见章节卡片模板 |
| `{{MERMAID_ARGUMENT_CHAIN}}` | 各章 `argument_logic` 串联 | `flowchart LR` 语法，节点≤15字 |
| `{{ARGUMENT_STEPS_DETAIL}}` | 各章 `argument_logic` 展开 | `<div class="card">` |
| `{{DEEP_RESEARCH_CONTENT}}` | 主Agent针对各核心论点生成扩展建议 | `<div class="research-item">` |
| `{{TOPIC_1}}` | 全书最核心概念 | 纯文本 |
| `{{KB_INDEX}}` | 各章 `entities` 合并去重 | `<div class="kb-item">` |

**章节卡片HTML模板**（填充 `{{CHAPTER_SUMMARIES}}`，注意：无 `onclick`，由模板JS统一处理）：

```html
<div class="chapter-summary" id="ch-{{INDEX}}">
  <div class="chapter-header">
    <h4>第{{INDEX}}章 · {{TITLE}}{{#if SAMPLED}} <small style="color:var(--text-secondary)">[采样]</small>{{/if}}</h4>
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

**1. 页码偏移必须执行**
校准结果 `confidence == "low"` 时不可跳过人工验证。偏移错误会导致章节切割错位，
且错误会传递到所有后续步骤，难以事后修复。

**2. 子Agent只读 .txt，不读 .pdf**
这是执行层的硬约束。步骤2的 `extract_text` 命令必须在步骤3之前完成。

**3. 采样章节的分析局限**
`[SAMPLED]` 章节的分析结果可靠性低于全文章节，报告卡片中会显示"[采样]"标记。
如需更精确分析，可对该章单独运行子Agent并传入 `--sample` 关闭的全文版本。

**4. Mermaid节点长度**
mindmap 和 flowchart 节点文字不超过15字，超出截断加省略号，防止渲染溢出。

**5. 章节卡片不写 onclick**
`report_template.html` 已通过事件委托统一处理折叠逻辑，章节卡片中不要添加内联
`onclick` 属性，否则会触发两次导致展开后立即收起。
