#!/usr/bin/env python3
"""拆书报告质量验证脚本"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class CheckResult:
    status: str  # PASS, WARN, FAIL
    message: str


class SplitbookValidator:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.checks: List[CheckResult] = []
        self.structure_data = None

    def add(self, status: str, message: str) -> None:
        self.checks.append(CheckResult(status, message))

    def run(self) -> int:
        """运行全部验证"""
        print(f"验证目录: {self.output_dir}\n")

        if not self.output_dir.exists():
            self.add("FAIL", f"输出目录不存在: {self.output_dir}")
            return self.finish()

        self.validate_structure()
        self.validate_chapters()
        self.validate_report()
        self.validate_quality_gates()

        return self.finish()

    def validate_structure(self) -> None:
        """验证 book_structure.json"""
        structure_file = self.output_dir / "book_structure.json"

        if not structure_file.exists():
            self.add("FAIL", "缺少 book_structure.json")
            return

        try:
            with open(structure_file, 'r', encoding='utf-8') as f:
                self.structure_data = json.load(f)
        except json.JSONDecodeError as e:
            self.add("FAIL", f"book_structure.json 格式错误: {e}")
            return

        # 检查关键字段
        required = ['pdf_name', 'total_pages', 'chapters', 'page_offset']
        for field in required:
            if field not in self.structure_data:
                self.add("FAIL", f"book_structure.json 缺少字段: {field}")

        # 检查页码偏移
        offset = self.structure_data.get('page_offset')
        if offset is None:
            self.add("FAIL", "未设置 page_offset")
        elif not isinstance(offset, int):
            self.add("FAIL", f"page_offset 应为整数: {offset}")

        # 检查章节数组
        chapters = self.structure_data.get('chapters', [])
        if not chapters:
            self.add("FAIL", "chapters 数组为空")
        else:
            self.add("PASS", f"共 {len(chapters)} 个章节条目")

            # 检查章节类型分布
            main_count = sum(1 for c in chapters if c.get('chapter_type') == 'main')
            aux_count = sum(1 for c in chapters if c.get('chapter_type') == 'aux')
            self.add("PASS", f"正文章节: {main_count}, 辅助章节: {aux_count}")

    def validate_chapters(self) -> None:
        """验证章节分析结果"""
        if not self.structure_data:
            return

        chapters = self.structure_data.get('chapters', [])
        main_chapters = [c for c in chapters if c.get('chapter_type') == 'main']

        if not main_chapters:
            return

        # 检查完成状态
        completed = [c for c in main_chapters if c.get('status') == 'done']
        failed = [c for c in main_chapters if c.get('status') == 'failed']

        completion_rate = len(completed) / len(main_chapters) if main_chapters else 0

        if completion_rate >= 0.9:
            self.add("PASS", f"章节完成率 {len(completed)}/{len(main_chapters)} (90%+)")
        elif completion_rate >= 0.7:
            self.add("WARN", f"章节完成率 {len(completed)}/{len(main_chapters)} (70-90%)")
        else:
            self.add("FAIL", f"章节完成率过低 {len(completed)}/{len(main_chapters)} (<70%)")

        if failed:
            self.add("WARN", f"有 {len(failed)} 个章节分析失败: {', '.join(c['title'] for c in failed[:3])}")

        # 检查JSON文件存在性（支持相对路径和绝对路径）
        missing_json = []
        for ch in main_chapters:
            json_file = ch.get('json_file')
            if json_file:
                # 优先作为相对路径处理
                json_path = self.output_dir / json_file
                if not json_path.exists():
                    # 回退：作为绝对路径检查
                    json_path = Path(json_file)
                    if not json_path.exists():
                        missing_json.append(ch['title'])

        if missing_json:
            self.add("WARN", f"缺少章节JSON文件: {', '.join(missing_json[:3])}")

    def validate_report(self) -> None:
        """验证HTML报告"""
        report_file = self.output_dir / "book_analysis_report.html"

        if not report_file.exists():
            self.add("FAIL", "缺少 HTML 报告")
            return

        try:
            content = report_file.read_text(encoding='utf-8')
        except Exception as e:
            self.add("FAIL", f"无法读取报告: {e}")
            return

        # 检查模板变量是否替换
        template_vars = re.findall(r'\{\{([A-Z_]+)\}\}', content)
        if template_vars:
            unique_vars = set(template_vars)
            self.add("FAIL", f"报告包含未替换的模板变量: {', '.join(unique_vars)}")
        else:
            self.add("PASS", "所有模板变量已替换")

        # 检查本地路径泄露
        local_patterns = [
            r'[A-Z]:\\\S+',  # Windows路径
            r'/Users/\S+',    # macOS路径
            r'/home/\S+',     # Linux路径
        ]
        leaked_paths = []
        for pattern in local_patterns:
            matches = re.findall(pattern, content)
            leaked_paths.extend(matches[:3])

        if leaked_paths:
            self.add("WARN", f"报告可能包含本地路径: {leaked_paths[0]}...")
        else:
            self.add("PASS", "无本地路径泄露")

        # 检查关键内容区域
        required_sections = ['核心洞察', '思维导图', '章节详情']
        for section in required_sections:
            if section in content:
                self.add("PASS", f"包含'{section}'区域")
            else:
                self.add("WARN", f"缺少'{section}'区域")

    def validate_quality_gates(self) -> None:
        """验证特定质量门禁"""
        if not self.structure_data:
            return

        # 门禁1: 采样章节比例
        chapters = self.structure_data.get('chapters', [])
        txt_files = list(self.output_dir.glob("*.txt"))

        sampled_count = 0
        for txt_file in txt_files:
            try:
                content = txt_file.read_text(encoding='utf-8', errors='ignore')
                if '[SAMPLED]' in content[:500]:
                    sampled_count += 1
            except:
                pass

        total_txt = len(txt_files)
        if total_txt > 0 and sampled_count / total_txt > 0.5:
            self.add("WARN", f"采样章节比例高 ({sampled_count}/{total_txt})，可能影响分析深度")

        # 门禁2: 关键字段完整性
        if self.structure_data:
            for ch in self.structure_data.get('chapters', [])[:5]:
                if ch.get('status') == 'done' and ch.get('json_file'):
                    json_path = self.output_dir / ch['json_file']
                    if not json_path.exists():
                        # 回退：作为绝对路径检查
                        json_path = Path(ch['json_file'])
                    if json_path.exists():
                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            if not data.get('key_points'):
                                self.add("WARN", f"章节 '{ch['title']}' 缺少 key_points")
                        except:
                            pass

    def finish(self) -> int:
        """输出结果并返回状态码"""
        failures = [c for c in self.checks if c.status == "FAIL"]
        warnings = [c for c in self.checks if c.status == "WARN"]
        passes = [c for c in self.checks if c.status == "PASS"]

        # 按状态分组输出
        for check in self.checks:
            print(f"[{check.status:4}] {check.message}")

        print(f"\n{'='*50}")
        print(f"总计: {len(passes)} 通过, {len(warnings)} 警告, {len(failures)} 失败")

        if failures:
            print("\n建议: 修复失败项后重新生成")
            return 1
        elif warnings:
            print("\n建议: 查看警告项，确认是否影响使用")
            return 0
        else:
            print("\n报告质量检查通过")
            return 0


def main():
    parser = argparse.ArgumentParser(
        description="验证拆书输出质量",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python validate_splitbook.py ./book_output/
        """
    )
    parser.add_argument("output_dir", help="拆书输出目录路径")
    args = parser.parse_args()

    validator = SplitbookValidator(Path(args.output_dir))
    sys.exit(validator.run())


if __name__ == "__main__":
    main()
