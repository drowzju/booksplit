#!/usr/bin/env python3
"""
PDF书籍分析工具 - 支持拆书技能
用于提取目录、章节信息、文本内容，以及页码校准
"""

import fitz  # PyMuPDF
import os
import sys
import json
import re
import io
from typing import List, Dict, Optional

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

    # ------------------------------------------------------------------ #
    # 目录提取
    # ------------------------------------------------------------------ #

    def get_toc(self) -> List[Dict]:
        """
        提取PDF内置目录结构。
        返回: [{"level": int, "title": str, "page": int, "pdf_page": int}, ...]
        page     = 目录中标注的页码（人类可读，未校准）
        pdf_page = 对应的PDF内部0-indexed页码（未校准）
        """
        toc = self.doc.get_toc()
        result = []
        for level, title, page in toc:
            result.append({
                "level": level,
                "title": title.strip(),
                "page": int(page),
                "pdf_page": int(page) - 1,
            })
        return result

    # ------------------------------------------------------------------ #
    # 页码校准
    # ------------------------------------------------------------------ #

    def calibrate_page_offset(self) -> Dict:
        """
        自动校准TOC页码与PDF实际页码的偏移量。

        策略：取TOC前三条level-1条目，在各自标注页码的 ±10 页范围内
        搜索标题关键词，投票决定最可信的偏移值。

        返回:
          {
            "offset": int,          # 需要加到 toc.page 上得到正确pdf_page的值
            "confidence": "high" | "medium" | "low",
            "verified_by": str,     # 用于验证的章节标题
            "toc_page": int,
            "actual_page": int
          }
        """
        toc = self.get_toc()
        if not toc:
            return {"offset": 0, "confidence": "low", "verified_by": None,
                    "toc_page": None, "actual_page": None}

        # 只取 level==1 的条目，最多取前3条
        candidates = [t for t in toc if t["level"] == 1][:3]
        if not candidates:
            candidates = toc[:3]

        offsets = []
        for entry in candidates:
            toc_page = entry["page"]       # 1-indexed，目录标注值
            keywords = self._title_keywords(entry["title"])
            if not keywords:
                continue

            search_start = max(0, toc_page - 11)          # ±10页，0-indexed
            search_end   = min(self.total_pages - 1, toc_page + 9)

            for p in range(search_start, search_end + 1):
                text = self.doc[p].get_text().replace('\n', ' ')
                if all(kw in text for kw in keywords):
                    # p 是 0-indexed，toc_page 是 1-indexed
                    offsets.append({
                        "offset": p - (toc_page - 1),
                        "verified_by": entry["title"],
                        "toc_page": toc_page,
                        "actual_page": p + 1,   # 返回给人类看，1-indexed
                    })
                    break   # 本条目找到即停

        if not offsets:
            return {"offset": 0, "confidence": "low", "verified_by": None,
                    "toc_page": None, "actual_page": None}

        # 多数投票
        from collections import Counter
        offset_votes = Counter(o["offset"] for o in offsets)
        best_offset, votes = offset_votes.most_common(1)[0]
        confidence = "high" if votes >= 2 else "medium" if len(offsets) >= 1 else "low"
        best = next(o for o in offsets if o["offset"] == best_offset)

        return {
            "offset": best_offset,
            "confidence": confidence,
            "verified_by": best["verified_by"],
            "toc_page": best["toc_page"],
            "actual_page": best["actual_page"],
        }

    def _title_keywords(self, title: str) -> List[str]:
        """从标题中提取2-3个有辨识度的关键词（去掉纯数字和常见前缀）"""
        # 去掉"第X章"、"Chapter N"等前缀
        clean = re.sub(r'^(第\s*\d+\s*[章节部]|Chapter\s*\d+|Part\s*\d+)\s*', '',
                       title, flags=re.IGNORECASE).strip()
        if not clean:
            clean = title
        # 取前15个字符里有意义的词
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}', clean)
        return words[:2] if words else [clean[:6]] if clean else []

    # ------------------------------------------------------------------ #
    # 文本提取（含采样模式）
    # ------------------------------------------------------------------ #

    def extract_text_from_pages(self, start_page: int, end_page: int,
                                 sample: bool = False) -> str:
        """
        从指定页面范围（0-indexed）提取文本。

        sample=True 时启用按比例采样，适用于超长章节（>50页），
        策略：前20% + 中间40%中心区域 + 后20%，其余页只保留各段落首句。
        采样时在文本开头附加 [SAMPLED] 标记供调用方识别。
        """
        end_page = min(end_page, self.total_pages - 1)
        page_count = end_page - start_page + 1

        if not sample or page_count <= 50:
            parts = []
            for p in range(start_page, end_page + 1):
                text = self.doc[p].get_text()
                parts.append(f"--- Page {p + 1} ---\n{text}")
            return "\n\n".join(parts)

        # 采样模式：按比例划分区段
        front_end   = start_page + max(1, int(page_count * 0.20))
        mid_start   = start_page + int(page_count * 0.40)
        mid_end     = start_page + int(page_count * 0.60)
        back_start  = end_page  - max(1, int(page_count * 0.20)) + 1

        def full_pages(a, b):
            parts = []
            for p in range(a, min(b + 1, self.total_pages)):
                parts.append(f"--- Page {p + 1} ---\n{self.doc[p].get_text()}")
            return parts

        def first_sentences(a, b):
            """只取每页的段落首句（粗略：每段第一行）"""
            parts = []
            for p in range(a, min(b + 1, self.total_pages)):
                lines = [l.strip() for l in self.doc[p].get_text().split('\n')
                         if l.strip()]
                summary = '\n'.join(lines[:3])   # 每页取前3行
                parts.append(f"--- Page {p + 1} [summary only] ---\n{summary}")
            return parts

        sections = []
        sections += full_pages(start_page, front_end - 1)
        if front_end < mid_start:
            sections += first_sentences(front_end, mid_start - 1)
        sections += full_pages(mid_start, mid_end)
        if mid_end + 1 < back_start:
            sections += first_sentences(mid_end + 1, back_start - 1)
        sections += full_pages(back_start, end_page)

        return "[SAMPLED]\n\n" + "\n\n".join(sections)

    def extract_chapter_to_file(self, start_page: int, end_page: int,
                                 output_path: str, sample: bool = False):
        """
        将指定页面范围的文本提取并写入 .txt 文件。
        start_page / end_page 均为 0-indexed。
        """
        text = self.extract_text_from_pages(start_page, end_page, sample=sample)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        return output_path

    # ------------------------------------------------------------------ #
    # 书籍结构分析
    # ------------------------------------------------------------------ #

    def analyze_book_structure(self, page_offset: int = 0) -> Dict:
        """
        分析整本书结构，返回章节列表。
        page_offset: calibrate_page_offset() 返回的 offset 值。
        """
        toc = self.get_toc()
        if not toc:
            return self._auto_detect_chapters()

        chapters = []
        for i, item in enumerate(toc):
            corrected_pdf_page = item["pdf_page"] + page_offset
            corrected_pdf_page = max(0, min(corrected_pdf_page, self.total_pages - 1))

            if i < len(toc) - 1:
                next_pdf_page = toc[i + 1]["pdf_page"] + page_offset
                end_page = max(corrected_pdf_page, next_pdf_page - 1)
            else:
                end_page = self.total_pages - 1

            page_count = end_page - corrected_pdf_page + 1
            chapters.append({
                "index": i + 1,
                "level": item["level"],
                "title": item["title"],
                "start_page": corrected_pdf_page + 1,   # 1-indexed，人类可读
                "end_page": end_page + 1,
                "page_count": page_count,
                "status": "pending",
                "json_file": None,
                "txt_file": None,
            })

        return {
            "pdf_name": self.pdf_name,
            "total_pages": self.total_pages,
            "has_toc": True,
            "page_offset": page_offset,
            "chapter_count": len(chapters),
            "chapters": chapters,
        }

    def _auto_detect_chapters(self) -> Dict:
        """无TOC时启发式检测章节边界（大字体+粗体文本）"""
        chapters = []
        current_start = 0

        for page_num in range(self.total_pages):
            page = self.doc[page_num]
            for block in page.get_text("dict")["blocks"]:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        if span["size"] > 16 and (span["flags"] & 2):
                            if page_num > current_start:
                                chapters.append({
                                    "index": len(chapters) + 1,
                                    "level": 1,
                                    "title": f"Section {len(chapters) + 1}",
                                    "start_page": current_start + 1,
                                    "end_page": page_num,
                                    "page_count": page_num - current_start,
                                    "status": "pending",
                                    "json_file": None,
                                    "txt_file": None,
                                })
                                current_start = page_num
                            break

        # 最后一章
        chapters.append({
            "index": len(chapters) + 1,
            "level": 1,
            "title": f"Section {len(chapters) + 1}",
            "start_page": current_start + 1,
            "end_page": self.total_pages,
            "page_count": self.total_pages - current_start,
            "status": "pending",
            "json_file": None,
            "txt_file": None,
        })

        return {
            "pdf_name": self.pdf_name,
            "total_pages": self.total_pages,
            "has_toc": False,
            "page_offset": 0,
            "chapter_count": len(chapters),
            "chapters": chapters,
        }

    # ------------------------------------------------------------------ #
    # PDF拆分
    # ------------------------------------------------------------------ #

    def split_by_chapters(self, output_dir: str = "./",
                           page_offset: int = 0) -> List[str]:
        """按章节拆分PDF，返回生成的文件路径列表"""
        structure = self.analyze_book_structure(page_offset=page_offset)
        os.makedirs(output_dir, exist_ok=True)
        output_files = []

        for ch in structure["chapters"]:
            doc_part = fitz.open()
            start = ch["start_page"] - 1   # 转为0-indexed
            end   = ch["end_page"] - 1
            doc_part.insert_pdf(self.doc, from_page=start, to_page=end)

            safe_title = re.sub(r'[^\w\s-]', '', ch["title"]).strip()
            safe_title = re.sub(r'[-\s]+', '-', safe_title)
            out_path = os.path.join(
                output_dir,
                f"{self.pdf_name}_ch{ch['index']:02d}_{safe_title[:30]}.pdf"
            )
            doc_part.save(out_path)
            doc_part.close()
            output_files.append(out_path)

        return output_files

    # ------------------------------------------------------------------ #
    # 导出
    # ------------------------------------------------------------------ #

    def export_structure_json(self, output_path: str,
                               page_offset: int = 0) -> Dict:
        """导出书籍结构为 book_structure.json（不含正文文本）"""
        structure = self.analyze_book_structure(page_offset=page_offset)
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
        return structure

    def close(self):
        self.doc.close()


# ------------------------------------------------------------------ #
# 命令行入口
# ------------------------------------------------------------------ #

def main():
    usage = """Usage: python pdf_analyzer.py <command> <pdf_path> [options]

Commands:
  toc      <pdf_path>                     提取目录（stdout JSON）
  calibrate <pdf_path>                    自动校准页码偏移（stdout JSON）
  structure <pdf_path> [--offset N]       分析书籍结构（stdout JSON）
  export   <pdf_path> <out_json> [--offset N]   导出 book_structure.json
  split    <pdf_path> <out_dir> [--offset N]    按章节拆分PDF
  extract_text <pdf_path> <out_dir> [--offset N] [--sample]
                                          提取各章节文本到 .txt 文件
"""
    if len(sys.argv) < 3:
        print(usage)
        sys.exit(1)

    command  = sys.argv[1]
    pdf_path = sys.argv[2]

    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # 解析公共参数
    args = sys.argv[3:]
    offset = 0
    use_sample = False
    positional = []
    i = 0
    while i < len(args):
        if args[i] == '--offset' and i + 1 < len(args):
            offset = int(args[i + 1]); i += 2
        elif args[i] == '--sample':
            use_sample = True; i += 1
        else:
            positional.append(args[i]); i += 1

    analyzer = PDFBookAnalyzer(pdf_path)

    try:
        if command == "toc":
            toc = analyzer.get_toc()
            print(json.dumps(toc, ensure_ascii=False, indent=2))

        elif command == "calibrate":
            result = analyzer.calibrate_page_offset()
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif command == "structure":
            structure = analyzer.analyze_book_structure(page_offset=offset)
            # 不含正文
            print(json.dumps(structure, ensure_ascii=False, indent=2))

        elif command == "export":
            out_json = positional[0] if positional else f"{analyzer.pdf_name}_structure.json"
            structure = analyzer.export_structure_json(out_json, page_offset=offset)
            print(f"Exported to: {out_json}  ({structure['chapter_count']} chapters)")

        elif command == "split":
            out_dir = positional[0] if positional else "./book_chapters"
            files = analyzer.split_by_chapters(out_dir, page_offset=offset)
            print(f"Split into {len(files)} chapters:")
            for f in files:
                print(f"  {f}")

        elif command == "extract_text":
            out_dir = positional[0] if positional else f"./{analyzer.pdf_name}_txt"
            os.makedirs(out_dir, exist_ok=True)
            structure = analyzer.analyze_book_structure(page_offset=offset)
            created = []
            for ch in structure["chapters"]:
                start = ch["start_page"] - 1   # 0-indexed
                end   = ch["end_page"] - 1
                do_sample = use_sample or ch["page_count"] > 50
                safe_title = re.sub(r'[^\w\s-]', '', ch["title"]).strip()
                safe_title = re.sub(r'[-\s]+', '-', safe_title)
                out_path = os.path.join(
                    out_dir,
                    f"{analyzer.pdf_name}_ch{ch['index']:02d}_{safe_title[:30]}.txt"
                )
                analyzer.extract_chapter_to_file(start, end, out_path, sample=do_sample)
                sampled_flag = " [sampled]" if do_sample else ""
                print(f"  ch{ch['index']:02d} ({ch['page_count']}p{sampled_flag}) -> {out_path}")
                created.append(out_path)
            print(f"Done. {len(created)} text files written to {out_dir}/")

        else:
            print(f"Unknown command: {command}", file=sys.stderr)
            print(usage)
            sys.exit(1)

    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
