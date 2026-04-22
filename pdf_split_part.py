import fitz  # PyMuPDF
import os
import sys

if len(sys.argv) < 3:
    print('Usage: python pdf_split_part.py <input_pdf> "<page_numbers>" [output_dir]')
    print('  page_numbers: comma-separated first-page of each part, 1-indexed')
    print('  Example: python pdf_split_part.py book.pdf "1,50,100" ./output/')
    sys.exit(1)

input_pdf = sys.argv[1]
pdf_name = os.path.splitext(os.path.basename(input_pdf))[0]
doc = fitz.open(input_pdf)
total_pages = len(doc)

# 解析章节起始页码（1-indexed，与PDF阅读器显示一致）
page_numbers_str = sys.argv[2].strip('"')
input_page_start_num = [int(x) for x in page_numbers_str.split(',')]

# 输出目录处理
output_dir = sys.argv[3] if len(sys.argv) >= 4 else os.path.dirname(input_pdf) or '.'
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)

for i in range(len(input_page_start_num)):
    doc_part = fitz.open()
    from_page = input_page_start_num[i] - 1  # 转为0-indexed
    if i < len(input_page_start_num) - 1:
        to_page = input_page_start_num[i + 1] - 2  # 下一章起始页的前一页
    else:
        to_page = total_pages - 1  # 末章到文档结尾
    print(f"Part {i+1}: pages {from_page+1}-{to_page+1}")
    output_path = os.path.join(output_dir, f"{pdf_name}_part_{i+1}.pdf")
    doc_part.insert_pdf(doc, from_page=from_page, to_page=to_page)
    doc_part.save(output_path)
    doc_part.close()
    print(f"  -> {output_path}")

doc.close()
print(f"Done. Split into {len(input_page_start_num)} parts.")
