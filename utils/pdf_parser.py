"""
PDF 解析工具模块

使用 PyMuPDF (fitz) 库从 PDF 文件中提取纯文本内容。
用于解析用户上传的 PDF 简历，提取文本后供 AI 分析模块使用。
"""

import io
from typing import Optional

import fitz  # PyMuPDF - 高性能 PDF 处理库


def parse_resume(file_bytes: bytes) -> str:
    """
    从 PDF 文件的二进制数据中提取纯文本内容。

    逐页解析 PDF，提取排序后的文本内容，适用于文字型 PDF（如简历）。
    对于扫描件图片 PDF（无可选文字），将返回空字符串。

    Args:
        file_bytes: PDF 文件的二进制内容（由 FastAPI UploadFile.read() 返回）

    Returns:
        提取到的纯文本内容，各页之间用换行符分隔。
        如果 PDF 为空或无法提取文字，返回空字符串。
    """
    # 从内存中的二进制数据打开 PDF 文档
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text = []
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        # sort=True 确保文本按阅读顺序排列（从上到下、从左到右）
        text = page.get_text("text", sort=True)
        pages_text.append(text)
    doc.close()

    # 合并所有页面的文本，去除首尾空白
    full_text = "\n".join(pages_text).strip()
    return full_text if full_text else ""
