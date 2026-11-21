"""docx 提取与报告生成。

体量小、逻辑确定：python-docx 读段落 → 拼成按行排列的纯文本，
行号与 checker 的 `\n` 切分一致；报告复用 checker.to_markdown，不在本模块重写规则。
"""

from io import BytesIO
from pathlib import Path

from docx import Document

import checker


def extract_text(data: bytes) -> str:
    """从 docx 字节流提取纯文本，按段落/表格行保留换行与行号。

    空段落也保留为占位行——引擎按 `\n` 切分行号，丢空行会让后续行号错位。
    表格单元格内容按「行内单元格以空格连接」提取，避免表格文字被整体丢弃。
    """
    try:
        doc = Document(BytesIO(data))
    except Exception as exc:  # python-docx 对损坏文件抛多种异常
        raise ValueError("无法解析 docx 文件，请确认文件未损坏") from exc

    lines: list[str] = []
    for block in doc.iter_inner_content():
        if hasattr(block, "text"):  # Paragraph
            lines.append(block.text)
        else:  # Table：逐行拼接单元格
            for row in getattr(block, "rows", []):
                cells = [cell.text.strip() for cell in row.cells]
                lines.append(" ".join(c for c in cells if c))

    text = "\n".join(lines)
    if not text.strip():
        raise ValueError("docx 中没有可提取的文字内容")
    return text


def build_report(filename: str, findings: list[dict], rule_count: int) -> str:
    """生成 Markdown 报告，复用引擎已有的 to_markdown（含规范来源清单）。"""
    return checker.to_markdown(Path(filename), findings, rule_count)
