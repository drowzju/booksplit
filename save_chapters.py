#!/usr/bin/env python3
"""
save_chapters.py - 保存子Agent分析结果到章节JSON文件

用法:
    python save_chapters.py <output_dir> <chapter_json_string>

参数:
    output_dir: 输出目录路径
    chapter_json_string: 单章或多章的JSON字符串（数组或对象）

示例:
    python save_chapters.py ./book_output '[{"index":1,"title":"第1章",...}]'
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

    注意：优先使用 chapter_index 字段进行匹配，标题匹配作为备用
    """
    # 确保是列表
    if isinstance(chapters_data, dict):
        chapters = [chapters_data]
    else:
        chapters = chapters_data

    # 加载 book_structure.json 以获取索引映射
    structure_path = os.path.join(output_dir, "book_structure.json")
    index_to_title = {}       # 索引 -> 标题
    title_to_index = {}       # 标题 -> 索引
    structure_chapters = []   # 保存结构信息供后续使用

    if os.path.exists(structure_path):
        with open(structure_path, 'r', encoding='utf-8') as f:
            structure = json.load(f)
            structure_chapters = structure.get('chapters', [])

        # 建立索引和标题的映射
        for s_ch in structure_chapters:
            idx = s_ch.get('index')
            title = s_ch.get('title', '')
            if idx:
                index_to_title[idx] = title
            if title:
                title_to_index[title] = idx

    # 保存每个章节
    for ch in chapters:
        # 优先使用 chapter_index 字段，其次使用 index 字段
        idx = ch.get('chapter_index') or ch.get('index')
        title = ch.get('title', '')

        # 策略1: 如果有索引，直接使用
        if idx and isinstance(idx, int):
            pass  # idx 已设置

        # 策略2: 如果提供了标题且能匹配到结构中的索引，使用结构中的索引
        elif title:
            # 尝试精确匹配
            if title in title_to_index:
                idx = title_to_index[title]
            else:
                # 尝试模糊匹配
                for s_title, s_idx in title_to_index.items():
                    if titles_match(title, s_title):
                        idx = s_idx
                        break

        # 策略3: 如果还找不到索引，尝试从文件名推断（如果有文件名信息）
        if not idx:
            # 尝试从文件名推断索引
            for filename in os.listdir(output_dir):
                if filename.startswith('chapter_') and filename.endswith('.txt'):
                    # 尝试匹配标题
                    filepath = os.path.join(output_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read(500)  # 读取前500字符
                            if title and title in content:
                                # 从文件名提取索引
                                match = re.search(r'chapter_(\d+)', filename)
                                if match:
                                    idx = int(match.group(1))
                                    break
                    except:
                        pass

        if not idx:
            idx = 1

        # 确保标题与book_structure一致（如果找到了匹配的索引）
        if idx in index_to_title:
            expected_title = index_to_title[idx]
            if expected_title and title != expected_title:
                # 标题不一致，使用book_structure中的标题
                ch['title'] = expected_title

        json_file = os.path.join(output_dir, f"chapter_{idx:02d}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(ch, f, ensure_ascii=False, indent=2)
        print(f"Saved: {json_file}")

    # 更新 book_structure.json
    if os.path.exists(structure_path):
        with open(structure_path, 'r', encoding='utf-8') as f:
            structure = json.load(f)

        for ch in chapters:
            # 同样优先使用 chapter_index 或匹配的标题索引
            idx = ch.get('chapter_index') or ch.get('index')
            title = ch.get('title', '')

            # 重新计算索引（确保一致性）
            if not idx and title:
                if title in title_to_index:
                    idx = title_to_index[title]
                else:
                    for s_title, s_idx in title_to_index.items():
                        if titles_match(title, s_title):
                            idx = s_idx
                            break

            if not idx:
                idx = ch.get('index', 1)

            # 更新对应章节的status和json_file
            for s_ch in structure.get('chapters', []):
                if s_ch['index'] == idx:
                    s_ch['json_file'] = os.path.join(output_dir, f"chapter_{idx:02d}.json")
                    s_ch['status'] = 'done'
                    break
                elif s_ch.get('title') and titles_match(s_ch.get('title'), title):
                    s_ch['json_file'] = os.path.join(output_dir, f"chapter_{idx:02d}.json")
                    s_ch['status'] = 'done'
                    idx = s_ch['index']  # 更新idx为匹配到的索引
                    break

        with open(structure_path, 'w', encoding='utf-8') as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
        print(f"Updated: {structure_path}")

    print(f"\nAll chapter JSON files saved and structure updated!")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    output_dir = sys.argv[1]
    json_str = sys.argv[2]

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    try:
        data = json.loads(json_str)
        save_chapters(output_dir, data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
