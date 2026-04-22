#!/usr/bin/env python3
"""
generate_report.py - 从章节分析结果生成HTML报告

用法:
    python generate_report.py <output_dir> [template_path]

参数:
    output_dir:    包含 book_structure.json 和 chapter_XX.json 的目录
    template_path: HTML模板路径（可选，默认使用内置模板）

示例:
    python generate_report.py ./book_output
"""

import json
import os
import sys
from datetime import datetime


def load_chapters(output_dir: str, use_level1_only: bool = False):
    """
    加载所有章节JSON文件

    Args:
        output_dir: 输出目录
        use_level1_only: 是否只使用一级章节（过滤掉二级及以下小节）
    """
    structure_path = os.path.join(output_dir, "book_structure.json")

    if not os.path.exists(structure_path):
        raise FileNotFoundError(f"book_structure.json not found in {output_dir}")

    with open(structure_path, 'r', encoding='utf-8') as f:
        structure = json.load(f)

    # 尝试加载每个章节的分析结果
    chapters = []
    for s_ch in structure.get('chapters', []):
        # 如果指定只使用一级章节，跳过 level > 1 的
        if use_level1_only and s_ch.get('level', 1) > 1:
            continue

        idx = s_ch['index']
        ch_file = os.path.join(output_dir, f"chapter_{idx:02d}.json")

        if os.path.exists(ch_file):
            with open(ch_file, 'r', encoding='utf-8') as f:
                ch = json.load(f)
                # 合并结构信息
                ch['start_page'] = s_ch.get('start_page', 0)
                ch['end_page'] = s_ch.get('end_page', 0)
                ch['index'] = idx
                ch['level'] = s_ch.get('level', 1)  # 保留层级信息
                chapters.append(ch)
        else:
            # 章节分析结果不存在，使用结构信息创建占位
            chapters.append({
                'index': idx,
                'title': s_ch.get('title', f'Chapter {idx}'),
                'start_page': s_ch.get('start_page', 0),
                'end_page': s_ch.get('end_page', 0),
                'level': s_ch.get('level', 1),
                'status': 'pending',
                'core_question': '待分析',
                'key_points': [],
                'key_cases': [],
                'key_quotes': [],
                'argument_logic': '',
                'relation_to_book': ''
            })

    return structure, chapters


def escape_html(text):
    """转义HTML特殊字符"""
    if not isinstance(text, str):
        text = str(text)
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def truncate(text, max_len=60):
    """截断文本"""
    if not text:
        return ''
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text


def generate_mindmap(chapters, book_title="Book"):
    """生成思维导图 - 使用层级结构展示，包含关键内容摘要"""
    lines = ["mindmap"]
    # 根节点
    root_title = book_title[:10] + "..." if len(book_title) > 12 else book_title
    lines.append(f'  root(({escape_html(root_title)}))')

    import re

    # 按一级部分分组
    current_part = None
    part_nodes = []
    current_part_chapters = []

    for ch in chapters:
        if ch.get('level', 1) == 1:
            # 保存上一个部分
            if current_part and current_part_chapters:
                part_nodes.append((current_part, current_part_chapters))
            # 开始新部分
            current_part = ch
            current_part_chapters = []
        elif current_part:
            current_part_chapters.append(ch)

    # 处理最后一部分
    if current_part and current_part_chapters:
        part_nodes.append((current_part, current_part_chapters))

    # 如果没有分组（只有一级章节），直接使用章节列表
    if not part_nodes:
        part_nodes = [(ch, []) for ch in chapters if ch.get('level', 1) == 1][:8]

    # 生成思维导图节点
    for part, sub_chapters in part_nodes[:8]:  # 最多8个主要部分
        title = part.get('title', 'Part')
        # 提取简短标题 - 使用更大的长度保留完整语义
        short_title = extract_chapter_short_name(title, max_len=25)

        lines.append(f"    {escape_html(short_title)}")

        # 如果有子章节，添加子节点（最多4个）
        for sub in sub_chapters[:4]:
            sub_short = extract_chapter_short_name(sub.get('title', ''), max_len=20)
            lines.append(f"      {escape_html(sub_short)}")

        # 如果没有子章节，添加核心问题和关键论点作为子节点
        if not sub_chapters:
            core_q = part.get('core_question', '')
            if core_q:
                q_short = truncate(core_q, 18)
                lines.append(f"      {escape_html(q_short)}")

            key_points = part.get('key_points', [])
            for kp in key_points[:2]:
                kp_short = truncate(kp, 15)
                lines.append(f"      {escape_html(kp_short)}")

    return "\n".join(lines)


def is_chapter_title(title):
    """判断是否为有效章节标题（排除时间、前言、附录等非主线内容）"""
    if not title:
        return False
    # 排除纯数字（年份、页码等）
    if title.isdigit():
        return False
    # 排除明显的时间标记
    time_patterns = ['年', '月', '日', '202', '201', '200']
    if any(p in title for p in time_patterns) and len(title) <= 6:
        return False
    # 排除非章节标记
    exclude_keywords = [
        '前言', '目录', '附录', '索引', '参考文献', '致谢', '总结',
        '其它', '其他', '系列文章', '技术资料', '关于作者'
    ]
    if any(kw in title for kw in exclude_keywords):
        return False
    return True


def extract_chapter_short_name(title, max_len=20):
    """智能提取章节短名称 - 保留更多语义内容"""
    if not title:
        return "未知"

    # 优先匹配 "第X章" 或 "Chapter X" 模式
    import re

    # 中文模式：第1章、第一章、第1节等
    cn_match = re.search(r'第[\d一二三四五六七八九十]+[章节部]', title)
    if cn_match:
        chapter_part = cn_match.group(0)  # "第1章"
        # 提取后续关键词（最多10字，保留完整语义）
        rest = title[cn_match.end():].strip()
        rest = re.sub(r'^[:：\s]+', '', rest)  # 移除冒号
        if rest:
            # 尝试提取前两个词或前10个字符
            words = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]+', rest)
            if len(words) >= 2 and len(words[0]) + len(words[1]) <= 10:
                keyword = f"{words[0]}{words[1]}"
            else:
                keyword = rest[:10] if len(rest) > 10 else rest
            result = f"{chapter_part} {keyword}"
        else:
            result = chapter_part
        return result[:max_len]

    # 英文模式：Chapter 1、Part I 等
    en_match = re.search(r'(Chapter|Part|Section)\s*[\dIVX]+', title, re.I)
    if en_match:
        en_part = en_match.group(0)
        rest = title[en_match.end():].strip()
        rest = re.sub(r'^[:：\s]+', '', rest)
        if rest:
            words = rest.split()[:3]  # 取前3个单词
            keyword = ' '.join(words)
            result = f"{en_part} {keyword}"
            return result[:max_len]
        return en_part[:max_len]

    # 回退：取前max_len字
    return title[:max_len-3] + "..." if len(title) > max_len else title


def generate_argument_chain(chapters):
    """生成论证链 - 显示章节级别的详细脉络"""
    lines = ["flowchart LR"]

    # 收集所有非辅助内容的章节
    valid_chapters = []
    for ch in chapters:
        title = ch.get('title', '')
        ch_type = ch.get('chapter_type', 'unknown')
        # 跳过明显的辅助内容
        if ch_type == 'aux' or not is_chapter_title(title):
            continue
        valid_chapters.append(ch)

    if not valid_chapters:
        valid_chapters = [ch for ch in chapters if is_chapter_title(ch.get('title', ''))]

    # 按部分分组显示
    prev_node = "Start"
    for i, ch in enumerate(valid_chapters[:15], 1):  # 最多15个节点
        level = ch.get('level', 1)
        title = ch.get('title', '')

        # 根据层级决定节点样式
        if level == 1:
            # 一级部分显示完整标题
            short_title = extract_chapter_short_name(title, max_len=15)
            node_style = f'Ch{i}["{escape_html(short_title)}"]'
        else:
            # 二级章节显示简短标题
            short_title = extract_chapter_short_name(title, max_len=12)
            node_style = f'Ch{i}(("{escape_html(short_title)}"))'

        lines.append(f'    {prev_node} --> {node_style}')

        # 添加论证逻辑说明
        argument = ch.get('argument_logic', '')
        if argument:
            arg_short = truncate(argument, 20)
            lines.append(f'    Ch{i} -.->|"{escape_html(arg_short)}"| Ch{i}Desc')

        prev_node = f"Ch{i}"

    lines.append(f'    {prev_node} --> End["总结"]')
    return "\n".join(lines)


def generate_report_html(structure, chapters):
    """生成完整HTML报告"""
    book_title = structure.get('pdf_name', '书籍分析报告')
    total_pages = structure.get('total_pages', 0)
    chapter_count = len(chapters)

    # 收集全书关键信息
    all_key_points = []
    all_cases = []
    all_quotes = []
    all_entities = {'people': set(), 'companies': set(), 'events': set()}

    for ch in chapters:
        all_key_points.extend(ch.get('key_points', []))
        all_cases.extend(ch.get('key_cases', []))
        all_quotes.extend(ch.get('key_quotes', []))
        entities = ch.get('entities', {})
        all_entities['people'].update(entities.get('people', []))
        all_entities['companies'].update(entities.get('companies', []))
        all_entities['events'].update(entities.get('events', []))

    # 取前3个关键论点
    top_points = all_key_points[:3] if all_key_points else ['待补充关键论点']

    # 生成关键论点HTML
    key_points_html = ""
    for i, point in enumerate(top_points, 1):
        num = ["①", "②", "③"][i-1]
        key_points_html += f'<div class="key-point"><span class="key-point-number">{num}</span>{escape_html(point)}</div>\n'

    # 章节导航
    chapter_nav_html = ""
    for ch in chapters:
        idx = ch['index']
        title = truncate(ch.get('title', f'第{idx}章'), 20)
        chapter_nav_html += f'<a href="#ch-{idx}" class="nav-item chapter-link">第{idx}章 {title}</a>\n'

    # 章节摘要
    chapter_summaries_html = ""
    for ch in chapters:
        idx = ch['index']
        sampled = ch.get('sampled', False)
        sampled_tag = ' <small style="color:var(--text-secondary)">[采样]</small>' if sampled else ''

        # 关键论点
        kp_list = ""
        for kp in ch.get('key_points', [])[:5]:
            kp_list += f"<li>{escape_html(truncate(kp, 80))}</li>\n"

        # 案例
        cases_html = ""
        for case in ch.get('key_cases', [])[:3]:
            case_text = case['case'] if isinstance(case, dict) else case
            page = case.get('page', '') if isinstance(case, dict) else ''
            cases_html += f'<div class="quote"><p>{escape_html(case_text)}</p><div class="quote-source">p.{page}</div></div>\n'

        # 引用
        quotes_html = ""
        for quote in ch.get('key_quotes', [])[:3]:
            quote_text = quote['quote'] if isinstance(quote, dict) else quote
            page = quote.get('page', '') if isinstance(quote, dict) else ''
            quotes_html += f'<div class="quote"><p>{escape_html(quote_text)}</p><div class="quote-source">p.{page}</div></div>\n'

        chapter_summaries_html += f'''
<div class="chapter-summary" id="ch-{idx}">
    <div class="chapter-header">
        <h4>第{idx}章 · {escape_html(ch.get('title', '未知章节'))}{sampled_tag}</h4>
        <span class="chapter-pages">P{ch['start_page']}-{ch['end_page']}</span>
    </div>
    <div class="chapter-content">
        <div class="chapter-section">
            <div class="chapter-section-title">核心问题</div>
            <p>{escape_html(ch.get('core_question', 'N/A'))}</p>
        </div>
        <div class="chapter-section">
            <div class="chapter-section-title">关键论点</div>
            <ul>{kp_list if kp_list else '<li>暂无</li>'}</ul>
        </div>
        <div class="chapter-section">
            <div class="chapter-section-title">典型案例</div>
            {cases_html if cases_html else '<p>无详细案例</p>'}
        </div>
        <div class="chapter-section">
            <div class="chapter-section-title">原文引用</div>
            {quotes_html if quotes_html else '<p>无引用</p>'}
        </div>
        <div class="chapter-section">
            <div class="chapter-section-title">论证逻辑</div>
            <p>{escape_html(ch.get('argument_logic', 'N/A'))}</p>
        </div>
        <div class="chapter-section">
            <div class="chapter-section-title">章节定位</div>
            <p>{escape_html(ch.get('relation_to_book', 'N/A'))}</p>
        </div>
    </div>
</div>
'''

    # 生成HTML
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape_html(book_title)} - 拆书分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        :root {{
            --bg-primary: #ffffff;
            --bg-secondary: #f5f5f5;
            --bg-sidebar: #fafafa;
            --text-primary: #333333;
            --text-secondary: #666666;
            --accent: #2563eb;
            --accent-light: #dbeafe;
            --border: #e5e5e5;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-primary: #1a1a2e;
                --bg-secondary: #16213e;
                --bg-sidebar: #0f0f23;
                --text-primary: #eaeaea;
                --text-secondary: #a0a0a0;
                --accent: #60a5fa;
                --accent-light: #1e3a5f;
                --border: #333344;
            }}
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
        }}
        .container {{ display: flex; min-height: 100vh; }}
        .sidebar {{
            width: 280px;
            background: var(--bg-sidebar);
            border-right: 1px solid var(--border);
            position: fixed;
            height: 100vh;
            overflow-y: auto;
            padding: 20px;
            z-index: 100;
        }}
        .sidebar h1 {{ font-size: 1.2rem; margin-bottom: 10px; color: var(--accent); }}
        .sidebar .book-meta {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--border);
        }}
        .nav-section {{ margin-bottom: 15px; }}
        .nav-section-title {{
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        .nav-item {{
            display: block;
            padding: 8px 12px;
            color: var(--text-primary);
            text-decoration: none;
            border-radius: 6px;
            font-size: 0.9rem;
            transition: all 0.2s;
        }}
        .nav-item:hover {{ background: var(--accent-light); color: var(--accent); }}
        .nav-item.active {{ background: var(--accent); color: white; }}
        .nav-item.chapter-link {{ padding-left: 20px; font-size: 0.85rem; }}
        .main-content {{
            flex: 1;
            margin-left: 280px;
            padding: 40px;
            max-width: 900px;
        }}
        .section {{ margin-bottom: 50px; scroll-margin-top: 20px; }}
        .section h2 {{
            font-size: 1.8rem;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--accent);
            display: inline-block;
        }}
        .section h3 {{
            font-size: 1.3rem;
            margin: 25px 0 15px;
            color: var(--accent);
        }}
        .card {{
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            border: 1px solid var(--border);
        }}
        .key-points {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .key-point {{
            background: var(--bg-primary);
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid var(--accent);
        }}
        .key-point-number {{
            font-weight: bold;
            color: var(--accent);
            margin-right: 8px;
        }}
        .chapter-summary {{
            margin: 30px 0;
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
        }}
        .chapter-header {{
            background: var(--bg-secondary);
            padding: 15px 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }}
        .chapter-header:hover {{ background: var(--accent-light); }}
        .chapter-header h4 {{ margin: 0; color: var(--text-primary); }}
        .chapter-pages {{
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
        .chapter-content {{ padding: 20px; display: none; }}
        .chapter-content.active {{ display: block; }}
        .chapter-section {{ margin: 15px 0; }}
        .chapter-section-title {{
            font-weight: 600;
            color: var(--accent);
            margin-bottom: 8px;
        }}
        .quote {{
            border-left: 4px solid var(--accent);
            padding: 15px 20px;
            margin: 15px 0;
            background: var(--bg-secondary);
            font-style: italic;
            border-radius: 0 8px 8px 0;
        }}
        .quote-source {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 8px;
            font-style: normal;
        }}
        .mermaid-container {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
            overflow-x: auto;
        }}
        .tag {{
            display: inline-block;
            background: var(--accent-light);
            color: var(--accent);
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 0.8rem;
            margin: 3px;
        }}
        ul, ol {{ margin: 10px 0 10px 20px; }}
        li {{ margin: 5px 0; }}
        @media (max-width: 768px) {{
            .sidebar {{ display: none; }}
            .main-content {{ margin-left: 0; padding: 20px; }}
            .key-points {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <aside class="sidebar">
            <h1>{escape_html(book_title)}</h1>
            <div class="book-meta">
                共{total_pages}页 · {chapter_count}章<br>
                生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
            </div>
            <div class="nav-section">
                <div class="nav-section-title">导航</div>
                <a href="#overview" class="nav-item active">概览</a>
                <a href="#mindmap" class="nav-item">全书导图</a>
                <a href="#chapters" class="nav-item">章节详情</a>
            </div>
            <div class="nav-section">
                <div class="nav-section-title">章节索引</div>
                {chapter_nav_html}
            </div>
        </aside>
        <main class="main-content">
            <section id="overview" class="section">
                <h2>书籍概览</h2>
                <div class="card">
                    <h3>核心要点</h3>
                    <div class="key-points">
                        {key_points_html}
                    </div>
                </div>
            </section>
            <section id="mindmap" class="section">
                <h2>全书思维导图</h2>
                <div class="mermaid-container">
                    <pre class="mermaid">
{generate_mindmap(chapters, book_title)}
                    </pre>
                </div>
                <h3>论证脉络</h3>
                <div class="mermaid-container">
                    <pre class="mermaid">
{generate_argument_chain(chapters)}
                    </pre>
                </div>
            </section>
            <section id="chapters" class="section">
                <h2>章节详情</h2>
                {chapter_summaries_html}
            </section>
        </main>
    </div>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose'
        }});
        document.querySelectorAll('.chapter-header').forEach(header => {{
            header.addEventListener('click', () => {{
                const content = header.nextElementSibling;
                content.classList.toggle('active');
            }});
        }});
    </script>
</body>
</html>
'''
    return html


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    output_dir = sys.argv[1]

    if not os.path.exists(output_dir):
        print(f"Error: Directory not found: {output_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        structure, chapters = load_chapters(output_dir)
        html = generate_report_html(structure, chapters)

        output_path = os.path.join(output_dir, "book_analysis_report.html")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"Generated report: {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error generating report: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
