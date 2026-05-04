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


def save_chapters(output_dir: str, chapters_data):
    """
    保存章节分析结果到独立JSON文件，并更新 book_structure.json

    Args:
        output_dir: 输出目录
        chapters_data: 单章dict或多章list

    注意：使用物理索引（index）保存文件，而非章节编号（chapter_number）
    """
    # 确保是列表
    if isinstance(chapters_data, dict):
        chapters = [chapters_data]
    else:
        chapters = chapters_data

    # 加载 book_structure.json 以获取索引映射
    structure_path = os.path.join(output_dir, "book_structure.json")
    index_to_chapter = {}
    if os.path.exists(structure_path):
        with open(structure_path, 'r', encoding='utf-8') as f:
            structure = json.load(f)
        # 建立标题到索引的映射
        for s_ch in structure.get('chapters', []):
            index_to_chapter[s_ch['title']] = s_ch['index']

    # 保存每个章节
    for ch in chapters:
        # 优先使用 chapter_index 字段，其次使用 index 字段
        idx = ch.get('chapter_index') or ch.get('index')

        # 如果提供了标题且能匹配到结构中的索引，使用结构中的索引
        title = ch.get('title', '')
        if title and title in index_to_chapter:
            idx = index_to_chapter[title]

        if not idx:
            idx = 1

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
            if title and title in index_to_chapter:
                idx = index_to_chapter[title]
            if not idx:
                idx = ch.get('index', 1)

            for s_ch in structure.get('chapters', []):
                if s_ch['index'] == idx or s_ch.get('title') == title:
                    s_ch['json_file'] = os.path.join(output_dir, f"chapter_{idx:02d}.json")
                    s_ch['status'] = 'done'
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
