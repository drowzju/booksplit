---
name: splitbook
description: 智能拆解和分析PDF书籍，生成多维度结构化知识输出，包括超短摘要、分章节摘要、知识导图、作者论证链、Deep Research扩展和可问答知识库。
---

# 拆书技能 (Split Book Skill)

智能拆解PDF书籍，生成包含超短摘要、章节分析、知识导图、论证链、Deep Research扩展等多维度结构化报告。

---

## 何时使用此技能

当用户需要：
- 快速理解一本书的核心内容（1分钟速览）
- 深入分析书籍结构和论证逻辑
- 提取关键观点、案例和引用
- 生成可视化的知识导图
- 建立可查询的书籍知识库

---

## 使用方法

```
/splitbook <PDF文件路径>
```

---

## 架构概述：主Agent + 子Agent

本技能采用**主Agent协调、子Agent并行**的架构，原因如下：

- 一本普通书籍（200页）提取的文本约为15万字，远超单次上下文处理能力
- 各章节分析相互独立，天然适合并行
- 主Agent负责调度和汇总，子Agent只处理单章内容，保持上下文干净

```
主Agent（Orchestrator）
├── 步骤1：提取结构 & 页码校准
├── 步骤2：拆分PDF为章节文件
├── 步骤3：并行派发子Agent分析各章
│   ├── 子Agent-1 → 第1章分析 → chapter_01.json
│   ├── 子Agent-2 → 第2章分析 → chapter_02.json
│   └── 子Agent-N → 第N章分析 → chapter_0N.json
└── 步骤4：汇总所有 chapter_XX.json → 生成最终报告
```

**子Agent触发条件**：章节数 ≥ 5，或总页数 > 120页时，强制使用子Agent模式。  
章节数 ≤ 4 且总页数 ≤ 120 时，主Agent可直接处理。

---

## 工具说明：两个脚本的分工

| 脚本 | 适用场景 | 核心能力 |
|------|----------|----------|
| `pdf_analyzer.py` | PDF内置TOC完整 | 自动提取目录、按TOC拆分 |
| `pdf_split_part.py` | 无TOC或需手动指定页码 | 按手动页码列表拆分 |

优先使用 `pdf_analyzer.py`；若提取的TOC为空或条目少于3个，改用 `pdf_split_part.py` 并手动探测章节边界（见步骤1）。

---

## 主Agent工作流程

### 步骤1：提取结构 & 页码校准

```bash
python pdf_analyzer.py toc <pdf_path>
```

拿到TOC后，**必须执行页码校准**，否则后续拆分会错位：

```bash
# 取目录第一条entry，提取该页文本
python pdf_analyzer.py structure <pdf_path>
# 查看第一章 start_page 处的实际文本，与目录标题比对
```

**校准算法**：

1. 取TOC第一条：`{ title: "第一章 XXX", page: 15 }`
2. 提取PDF第15页文本，检查是否包含该标题关键词
3. 若不匹配，在 ±10页范围内搜索，找到匹配页后计算偏移量 `offset = actual_page - toc_page`
4. 将偏移量应用到所有TOC条目：`corrected_page = toc_page + offset`
5. 若偏移为0则直接继续

**若TOC为空**，使用启发式探测：取全书前30%页面，查找字体大小 > 16 且独占一行的文本，作为章节起始候选。

---

### 步骤2：拆分PDF为章节文件

```bash
# 有完整TOC时
python pdf_analyzer.py split <pdf_path> <output_dir>

# 无TOC或需手动指定时（页码为校准后的PDF实际页码）
python pdf_split_part.py <pdf_path> "<p1,p2,p3,...>" <output_dir>
```

拆分完成后，在 `output_dir` 中会生成：
```
chapter_01_xxx.pdf
chapter_02_xxx.pdf
...
book_structure.json   ← 记录章节元数据，供后续汇总使用
```

同时生成 `book_structure.json`（若 pdf_analyzer 未自动生成，则手动创建）：

```json
{
  "pdf_name": "书名",
  "total_pages": 220,
  "chapter_count": 8,
  "page_offset": 3,
  "chapters": [
    { "index": 1, "title": "第一章 XXX", "start_page": 18, "end_page": 42, "file": "chapter_01_xxx.pdf" }
  ]
}
```

---

### 步骤3：派发子Agent并行分析章节

对 `book_structure.json` 中每个章节，启动独立子Agent，传入：
- 章节PDF文件路径
- 章节元数据（标题、页码范围）
- 子Agent提示词（见下方）

**子Agent Prompt模板**：

```
你是一个书籍章节分析助手。请分析以下章节PDF，提取结构化信息，以JSON格式输出，不要包含任何其他文字。

章节信息：
- 标题：{{chapter_title}}
- 页码范围：第{{start_page}}页 - 第{{end_page}}页

输出格式：
{
  "chapter_index": 1,
  "title": "章节标题",
  "core_question": "本章试图回答的核心问题（1句话）",
  "key_points": [           // 必填，3-5条最重要论点
    "论点1",
    "论点2"
  ],
  "key_cases": [            // 必填，书中具体举的例子
    { "case": "案例描述", "page": 23 }
  ],
  "key_quotes": [           // 选填，仅在原文表述不可替代时填写
    { "quote": "原文", "page": 25 }
  ],
  "entities": {             // 选填，提到的具体实体
    "people": [],
    "companies": [],
    "events": []
  },
  "argument_logic": "本章论证逻辑的一句话概括（因→果结构）",
  "counter_arguments": [],  // 选填，作者提及的反对观点
  "relation_to_book": "本章在全书论证中的角色（承接/转折/总结等）"
}
```

**错误处理**：若某章节子Agent返回格式错误或超时，主Agent记录失败章节，继续处理其余章节，最终报告中该章节显示"分析失败，请单独重试"，不阻断整体流程。

---

### 步骤4：汇总生成报告

所有子Agent完成后，主Agent读取全部 `chapter_XX.json`，执行全书级别分析并填充报告模板。

**模板变量对照表**（`report_template.html` 中的占位符 → 数据来源）：

| 占位符 | 数据来源 | 格式说明 |
|--------|----------|----------|
| `{{BOOK_TITLE}}` | `book_structure.json` → `pdf_name` | 纯文本 |
| `{{TOTAL_PAGES}}` | `book_structure.json` → `total_pages` | 数字 |
| `{{CHAPTER_COUNT}}` | `book_structure.json` → `chapter_count` | 数字 |
| `{{GENERATE_TIME}}` | 当前时间 | `YYYY-MM-DD HH:mm` |
| `{{BOOK_WHAT_ABOUT}}` | 主Agent综合所有章节 `key_points` 生成 | 1-2句话 |
| `{{KEY_POINTS}}` | 各章节 `key_points` 中挑选全书最重要3条 | `<div class="key-point">` × 3 |
| `{{KEY_CONCLUSIONS}}` | 主Agent提炼 | `<li>` × 5 |
| `{{CORE_CONCEPTS}}` | 各章节 `entities` + 高频术语 | `<span class="tag">` |
| `{{CHAPTER_RELATIONSHIPS}}` | 各章节 `relation_to_book` 串联 | 1段话 |
| `{{CHAPTER_NAV}}` | `book_structure.json` → chapters | `<a class="nav-item chapter-link">` |
| `{{MERMAID_MINDMAP}}` | 主Agent基于全书结构生成 | mindmap语法 |
| `{{CHAPTER_SUMMARIES}}` | 各 `chapter_XX.json` | 见章节HTML模板 |
| `{{MERMAID_ARGUMENT_CHAIN}}` | 各章节 `argument_logic` 串联 | flowchart LR语法 |
| `{{ARGUMENT_STEPS_DETAIL}}` | 各章节 `argument_logic` 展开 | `<div class="card">` |
| `{{DEEP_RESEARCH_CONTENT}}` | 主Agent针对每条 `key_points` 生成扩展建议 | `<div class="research-item">` |
| `{{TOPIC_1}}` | 全书最核心概念 | 纯文本 |
| `{{KB_INDEX}}` | 各章节 `entities` 合并去重 | `<div class="kb-item">` |

**章节摘要HTML模板**（填充 `{{CHAPTER_SUMMARIES}}`）：

```html
<div class="chapter-summary">
  <div class="chapter-header" onclick="this.nextElementSibling.classList.toggle('active')">
    <h4>第{{INDEX}}章 · {{TITLE}}</h4>
    <span class="chapter-pages">P{{START_PAGE}}-{{END_PAGE}}</span>
  </div>
  <div class="chapter-content">
    <div class="chapter-section">
      <div class="chapter-section-title">核心问题</div>
      <p>{{CORE_QUESTION}}</p>
    </div>
    <div class="chapter-section">
      <div class="chapter-section-title">关键论点</div>
      <ul>{{KEY_POINTS_LI}}</ul>
    </div>
    <div class="chapter-section">
      <div class="chapter-section-title">典型案例</div>
      {{CASES}}
    </div>
    <!-- 若有引用 -->
    {{QUOTES_BLOCK}}
    <!-- 若有反对观点 -->
    {{COUNTER_BLOCK}}
  </div>
</div>
```

---

## 输出目录结构

```
<output_dir>/
├── book_analysis_report.html    # 最终报告（直接在浏览器打开）
├── book_structure.json          # 书籍结构元数据
├── chapter_01_xxx.json          # 子Agent分析结果（中间产物）
├── chapter_02_xxx.json
├── ...
├── chapter_01_xxx.pdf           # 拆分后章节PDF
├── chapter_02_xxx.pdf
└── ...
```

---

## 注意事项

**1. 页码偏移**  
目录页码与PDF实际页码常有差异（通常3-20页的偏移）。步骤1的校准是必须执行的，不可省略。偏移量需记录在 `book_structure.json` 的 `page_offset` 字段中。

**2. 章节过长**  
单章超过50页时，子Agent在提取文本时应只取前10页、中间5页、后10页作为采样，避免文本塞满上下文。在输出的JSON中注明"采样分析"。

**3. 两个拆分脚本的Bug修复**  
`pdf_split_part.py` 中最后一章的 `to_page` 硬编码为100000，实际运行时 PyMuPDF 会自动截断到文档末尾，功能上无问题，但建议在调用时传入实际总页数替换该值以避免警告。

**4. 子Agent失败容错**  
记录失败章节索引，在报告中该章节卡片显示降级内容，不影响其他章节展示。

**5. Mermaid节点长度**  
mindmap和flowchart中，每个节点文字不超过15个字，超出则截断并加省略号，避免图表渲染溢出。

**6.输出位置**
输出到pdf所在位置，建立目录名为{pdf文件名_output}。所有材料包括中间产物都放在这个目录下。