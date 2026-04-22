import fitz  # PyMuPDF
import os
import sys

if len(sys.argv) < 3:
    print('Usage: python pdf_split_part.py <input_pdf> "<page_numbers>" [output_dir]')
    sys.exit(1)

input_pdf = sys.argv[1]
pdf_name = os.path.splitext(os.path.basename(input_pdf))[0]
doc = fitz.open(input_pdf)

# 解析页码起始数字
page_numbers_str = sys.argv[2].strip('"')
input_page_start_num = [int(x) for x in page_numbers_str.split(',')]

# 输出目录处理
output_dir = sys.argv[3] if len(sys.argv) >= 4 else os.path.dirname(input_pdf)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)

#0 - 28(1-29)
#29 - 50(30-51)
#51 - 82(52-83)
start = 0
for i  in range(len(input_page_start_num)):
    doc_part = fitz.open()
    from_page = start + input_page_start_num[i] - 1
    if (i < len(input_page_start_num) - 1):
        to_page = start + input_page_start_num[i + 1] - 2
    else:
        # 到末尾。随便写了
        to_page = 100000
    print(from_page, to_page)
    output_path = os.path.join(output_dir, f"{pdf_name}_part_{i+1}.pdf")
    doc_part.insert_pdf(doc, from_page=from_page, to_page=to_page)
    doc_part.save(output_path)
    doc_part.close()

doc.close()


# 1-29
# chap 1: 1-22
# chap 2: 23-54
# chap 3: 55-86
# chap 4: 87-122

# like:   python3 .\pdf_split_part.py .\高并发的哲学原理.pdf "1,200,225" ./
