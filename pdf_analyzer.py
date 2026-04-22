#!/usr/bin/env python3
"""
PDF书籍分析工具 - 支持拆书技能
用于提取目录、章节信息和文本内容
"""

import fitz  # PyMuPDF
import os
import sys
import json
import re
import io
from typing import List, Dict, Tuple, Optional

# 修复 Windows 终端 Unicode 编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class PDFBookAnalyzer:
    """PDF书籍分析器"""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.total_pages = len(self.doc)
        self.pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]

    def get_toc(self) -> List[Dict]:
        """
        提取PDF目录结构
        返回: [{"level": int, "title": str, "page": int}, ...]
        """
        toc = self.doc.get_toc()
        result = []
        for item in toc:
            level, title, page = item
            result.append({
                "level": level,
                "title": title.strip(),
                "page": int(page),
                "pdf_page": int(page) - 1  # PDF内部页码从0开始
            })
        return result

    def extract_text_from_pages(self, start_page: int, end_page: int) -> str:
        """从指定页面范围提取文本"""
        text_parts = []
        for page_num in range(start_page, min(end_page + 1, self.total_pages)):
            page = self.doc[page_num]
            text = page.get_text()
            text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
        return "\n\n".join(text_parts)

    def extract_text_from_chapter(self, chapter_start_page: int, chapter_end_page: int) -> Dict:
        """提取章节文本并返回结构化数据"""
        text = self.extract_text_from_pages(chapter_start_page, chapter_end_page)

        # 尝试提取章节标题（通常在前几页）
        first_page = self.doc[chapter_start_page]
        first_page_text = first_page.get_text()

        # 简单启发式：找第一行非空文本作为标题
        lines = [l.strip() for l in first_page_text.split('\n') if l.strip()]
        chapter_title = lines[0] if lines else f"Chapter {chapter_start_page}"

        return {
            "title": chapter_title,
            "start_page": chapter_start_page + 1,  # 转换为人类可读页码
            "end_page": chapter_end_page + 1,
            "text": text,
            "page_count": chapter_end_page - chapter_start_page + 1
        }

    def analyze_book_structure(self) -> Dict:
        """分析整本书的结构"""
        toc = self.get_toc()

        if not toc:
            # 如果没有目录，尝试自动检测章节
            return self._auto_detect_chapters()

        chapters = []
        for i, item in enumerate(toc):
            if i < len(toc) - 1:
                end_page = toc[i + 1]["pdf_page"] - 1
            else:
                end_page = self.total_pages - 1

            chapter_info = self.extract_text_from_chapter(item["pdf_page"], end_page)
            chapter_info["level"] = item["level"]
            chapters.append(chapter_info)

        return {
            "pdf_name": self.pdf_name,
            "total_pages": self.total_pages,
            "has_toc": True,
            "chapters": chapters
        }

    def _auto_detect_chapters(self) -> Dict:
        """当PDF没有目录时，尝试自动检测章节边界"""
        # 简单策略：找大字体文本作为章节标题
        chapters = []
        current_chapter_start = 0

        for page_num in range(self.total_pages):
            page = self.doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            # 启发式：大字体可能是章节标题
                            if span["size"] > 16 and span["flags"] & 2:  # 粗体且字体大
                                if page_num > current_chapter_start:
                                    chapter_text = self.extract_text_from_pages(
                                        current_chapter_start, page_num - 1
                                    )
                                    chapters.append({
                                        "title": f"Section {len(chapters) + 1}",
                                        "start_page": current_chapter_start + 1,
                                        "end_page": page_num,
                                        "text": chapter_text[:1000] + "...",
                                        "level": 1
                                    })
                                    current_chapter_start = page_num
                                break

        # 添加最后一个章节
        if current_chapter_start < self.total_pages - 1:
            chapter_text = self.extract_text_from_pages(
                current_chapter_start, self.total_pages - 1
            )
            chapters.append({
                "title": f"Section {len(chapters) + 1}",
                "start_page": current_chapter_start + 1,
                "end_page": self.total_pages,
                "text": chapter_text[:1000] + "...",
                "level": 1
            })

        return {
            "pdf_name": self.pdf_name,
            "total_pages": self.total_pages,
            "has_toc": False,
            "chapters": chapters if chapters else [{
                "title": "Full Book",
                "start_page": 1,
                "end_page": self.total_pages,
                "text": self.extract_text_from_pages(0, self.total_pages - 1)[:2000] + "...",
                "level": 1
            }]
        }

    def split_by_chapters(self, output_dir: str = "./") -> List[str]:
        """
        按章节拆分PDF
        返回拆分的PDF文件路径列表
        """
        structure = self.analyze_book_structure()
        output_files = []

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        for i, chapter in enumerate(structure["chapters"]):
            doc_part = fitz.open()
            start = chapter["start_page"] - 1  # 转换为0索引
            end = chapter["end_page"] - 1

            doc_part.insert_pdf(self.doc, from_page=start, to_page=end)

            # 清理标题作为文件名
            safe_title = re.sub(r'[^\w\s-]', '', chapter["title"]).strip()
            safe_title = re.sub(r'[-\s]+', '-', safe_title)

            output_path = os.path.join(
                output_dir,
                f"{self.pdf_name}_ch{i+1:02d}_{safe_title[:30]}.pdf"
            )
            doc_part.save(output_path)
            doc_part.close()
            output_files.append(output_path)

        return output_files

    def export_structure_json(self, output_path: str):
        """导出书籍结构为JSON"""
        structure = self.analyze_book_structure()

        # 简化文本内容，避免JSON过大
        for ch in structure["chapters"]:
            if "text" in ch:
                del ch["text"]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)

        return structure

    def close(self):
        """关闭PDF文档"""
        self.doc.close()


def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print("Usage: python pdf_analyzer.py <command> <pdf_path> [options]")
        print("\nCommands:")
        print("  toc <pdf_path>              - 提取目录")
        print("  structure <pdf_path>        - 分析书籍结构")
        print("  split <pdf_path> <out_dir>  - 按章节拆分")
        print("  export <pdf_path> <out_json>- 导出结构为JSON")
        sys.exit(1)

    command = sys.argv[1]
    pdf_path = sys.argv[2]

    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    analyzer = PDFBookAnalyzer(pdf_path)

    try:
        if command == "toc":
            toc = analyzer.get_toc()
            print(json.dumps(toc, ensure_ascii=False, indent=2))

        elif command == "structure":
            structure = analyzer.analyze_book_structure()
            # 简化输出
            for ch in structure["chapters"]:
                if "text" in ch:
                    ch["text_preview"] = ch["text"][:200] + "..."
                    del ch["text"]
            print(json.dumps(structure, ensure_ascii=False, indent=2))

        elif command == "split":
            output_dir = sys.argv[3] if len(sys.argv) > 3 else "./book_chapters"
            files = analyzer.split_by_chapters(output_dir)
            print(f"Split into {len(files)} chapters:")
            for f in files:
                print(f"  - {f}")

        elif command == "export":
            output_json = sys.argv[3] if len(sys.argv) > 3 else f"{analyzer.pdf_name}_structure.json"
            analyzer.export_structure_json(output_json)
            print(f"Structure exported to: {output_json}")

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
