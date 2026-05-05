#!/usr/bin/env python3
"""
save_chapters.py - 保存子Agent分析结果到章节JSON文件

用法:
    python save_chapters.py <output_dir> <chapter_json_string>

参数:
    output_dir: 输出目录路径
    chapter_json_string: 单章或多章的JSON字符串（数组或对象）

示例:
    python save_chapters.py ./book_output '{"chapter_number":1,"title":"第1章","core_question":"..."}'

注意：使用 chapter_number（书中章节编号）而非物理 index 作为文件名，如 chapter_01.json
"""

import json
import os
import sys
import re


def normalize_title(title: str) -> str:
    """
    标准化标题用于匹配比较
    去除前后空白，统一中英文标点
    """
    if not title:
        return ''
    title = title.strip()
    # 统一冒号
    title = title.replace('：', ':')
    return title


def extract_chapter_prefix(title: str) -> tuple:
    """
    从标题中提取章节前缀和核心内容
    返回: (前缀, 核心内容)
    例如: "第1章 教育心理学" -> ("第1章", "教育心理学")
    """
    if not title:
        return '', ''

    # 匹配 "第X章" 或 "第X节" 或 "Chapter X"
    patterns = [
        r'^(第[\d一二三四五六七八九十]+章)[\s:：]*(.*)$',
        r'^(第[\d一二三四五六七八九十]+节)[\s:：]*(.*)$',
        r'^(Chapter\s*\d+)[\s:：]*(.*)$',
        r'^(Part\s*[\dIVX]+)[\s:：]*(.*)$',
    ]

    for pattern in patterns:
        match = re.match(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2).strip()

    return '', title


def titles_match(title1: str, title2: str) -> bool:
    """
    判断两个标题是否匹配（支持模糊匹配）
    """
    t1 = normalize_title(title1)
    t2 = normalize_title(title2)

    # 精确匹配
    if t1 == t2:
        return True

    # 提取核心内容比较（忽略"第X章"前缀）
    prefix1, core1 = extract_chapter_prefix(t1)
    prefix2, core2 = extract_chapter_prefix(t2)

    # 如果核心内容一致，认为匹配
    if core1 and core2 and (core1 == core2 or core1 in core2 or core2 in core1):
        return True

    # 如果一个包含另一个，认为匹配
    if t1 in t2 or t2 in t1:
        return True

    return False


def save_chapters(output_dir: str, chapters_data):
    """
    保存章节分析结果到独立JSON文件，并更新 book_structure.json

    Args:
        output_dir: 输出目录
        chapters_data: 单章dict或多章list

    注意：优先使用 chapter_number 字段（书中实际章节编号），其次使用 index 字段
    """
    # 确保是列表
    if isinstance(chapters_data, dict):
        chapters = [chapters_data]
    else:
        chapters = chapters_data

    # 强制校验：每个正文章节必须有 chapter_number
    for ch in chapters:
        ch_type = ch.get('chapter_type', 'main')
        title = ch.get('title', '')
        # 判断是否为正文章节
        is_main = ch_type == 'main' or any(pattern in title for pattern in ['第', '章', 'Chapter', 'Part'])
        if is_main and not ch.get('chapter_number'):
            raise ValueError(f"正文章节缺少必需的 chapter_number 字段: {title}")

    # 加载 book_structure.json 以获取章节编号映射
    structure_path = os.path.join(output_dir, "book_structure.json")
    index_to_title = {}           # index -> 标题
    index_to_chapter_num = {}     # index -> chapter_number
    title_to_chapter_num = {}     # 标题 -> chapter_number
    structure_chapters = []       # 保存结构信息供后续使用

    if os.path.exists(structure_path):
        with open(structure_path, 'r', encoding='utf-8') as f:
            structure = json.load(f)
            structure_chapters = structure.get('chapters', [])

        # 建立索引、标题和章节编号的映射
        for s_ch in structure_chapters:
            idx = s_ch.get('index')
            title = s_ch.get('title', '')
            ch_num = s_ch.get('chapter_number')  # 逻辑章节编号（如第1章）

            # 确保 chapter_number 是整数
            if ch_num is not None:
                try:
                    ch_num = int(ch_num)
                except (ValueError, TypeError):
                    ch_num = None

            if idx:
                index_to_title[idx] = title
                if ch_num:
                    index_to_chapter_num[idx] = ch_num
            if title and ch_num:
                title_to_chapter_num[title] = ch_num

    # 保存每个章节
    for ch in chapters:
        # 优先使用 chapter_number 字段
        chapter_num = ch.get('chapter_number')
        idx = ch.get('chapter_index') or ch.get('index')
        title = ch.get('title', '')

        # 策略1: 如果有 chapter_number，直接使用（转换为整数）
        if chapter_num:
            try:
                chapter_num = int(chapter_num)
            except (ValueError, TypeError):
                chapter_num = None

        # 策略2: 通过 index 查找 chapter_number
        if not chapter_num and idx and idx in index_to_chapter_num:
            chapter_num = index_to_chapter_num[idx]

        # 策略3: 通过标题查找 chapter_number
        elif title:
            # 尝试精确匹配
            if title in title_to_chapter_num:
                chapter_num = title_to_chapter_num[title]
            else:
                # 尝试模糊匹配
                for s_title, s_ch_num in title_to_chapter_num.items():
                    if titles_match(title, s_title):
                        chapter_num = s_ch_num
                        break

        # 策略4: 还找不到，回退到使用 index
        if not chapter_num:
            chapter_num = idx if idx else 1

        # 确保标题与book_structure一致
        if idx and idx in index_to_title:
            expected_title = index_to_title[idx]
            if expected_title and title != expected_title:
                ch['title'] = expected_title

        # 使用 chapter_number 作为文件名（如 chapter_01.json）
        json_file = os.path.join(output_dir, f"chapter_{chapter_num:02d}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(ch, f, ensure_ascii=False, indent=2)
        print(f"Saved: {json_file}")

    # 更新 book_structure.json
    if os.path.exists(structure_path):
        with open(structure_path, 'r', encoding='utf-8') as f:
            structure = json.load(f)

        for ch in chapters:
            chapter_num = ch.get('chapter_number')
            idx = ch.get('chapter_index') or ch.get('index')
            title = ch.get('title', '')

            # 确保 chapter_num 是整数
            if chapter_num:
                try:
                    chapter_num = int(chapter_num)
                except (ValueError, TypeError):
                    chapter_num = None

            # 重新计算 chapter_number（确保一致性）
            if not chapter_num and idx:
                if idx in index_to_chapter_num:
                    chapter_num = index_to_chapter_num[idx]
            if not chapter_num and title:
                if title in title_to_chapter_num:
                    chapter_num = title_to_chapter_num[title]
                else:
                    for s_title, s_ch_num in title_to_chapter_num.items():
                        if titles_match(title, s_title):
                            chapter_num = s_ch_num
                            break

            if not chapter_num:
                chapter_num = idx if idx else 1

            # 更新对应章节的status和json_file（使用相对路径）
            relative_json_file = f"chapter_{chapter_num:02d}.json"
            for s_ch in structure.get('chapters', []):
                # 匹配条件：index相同 或 chapter_number相同 或 标题匹配
                if s_ch['index'] == idx:
                    s_ch['json_file'] = relative_json_file
                    s_ch['status'] = 'done'
                    s_ch['chapter_number'] = chapter_num  # 确保写回chapter_number
                    break
                elif s_ch.get('chapter_number') and s_ch.get('chapter_number') == chapter_num:
                    s_ch['json_file'] = relative_json_file
                    s_ch['status'] = 'done'
                    s_ch['chapter_number'] = chapter_num  # 确保写回
                    break
                elif s_ch.get('title') and titles_match(s_ch.get('title'), title):
                    s_ch['json_file'] = relative_json_file
                    s_ch['status'] = 'done'
                    s_ch['chapter_number'] = chapter_num  # 确保写回
                    break

        with open(structure_path, 'w', encoding='utf-8') as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
        print(f"Updated: {structure_path}")

    print(f"\nAll chapter JSON files saved and structure updated!")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    output_dir = sys.argv[1]

    # 优先从stdin读取JSON，支持大参数
    if not sys.stdin.isatty():
        json_str = sys.stdin.read()
    elif len(sys.argv) >= 3:
        json_str = sys.argv[2]
    else:
        print("Error: 请提供JSON数据（通过stdin或命令行参数）", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    try:
        data = json.loads(json_str)
        save_chapters(output_dir, data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
