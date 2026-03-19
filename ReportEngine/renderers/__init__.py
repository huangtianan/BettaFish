"""
Report Engine渲染器集合。

提供 HTMLRenderer 和 PDFRenderer，支持HTML和PDF输出。
"""

from .html_renderer import HTMLRenderer
from .markdown_renderer import MarkdownRenderer

# PDF 渲染依赖（WeasyPrint/pango）在部分环境中可能不可用。
# 为了支持 `--skip-pdf` 仍能顺利生成 HTML/IR，这里对 PDFRenderer 做可选导入。
try:
    from .pdf_renderer import PDFRenderer
    from .pdf_layout_optimizer import (
        PDFLayoutOptimizer,
        PDFLayoutConfig,
        PageLayout,
        KPICardLayout,
        CalloutLayout,
        TableLayout,
        ChartLayout,
        GridLayout,
    )
except Exception:  # pragma: no cover
    PDFRenderer = None  # type: ignore
    PDFLayoutOptimizer = None  # type: ignore
    PDFLayoutConfig = None  # type: ignore
    PageLayout = None  # type: ignore
    KPICardLayout = None  # type: ignore
    CalloutLayout = None  # type: ignore
    TableLayout = None  # type: ignore
    ChartLayout = None  # type: ignore
    GridLayout = None  # type: ignore

__all__ = [
    "HTMLRenderer",
    "MarkdownRenderer",
    "PDFRenderer",
    "PDFLayoutOptimizer",
    "PDFLayoutConfig",
    "PageLayout",
    "KPICardLayout",
    "CalloutLayout",
    "TableLayout",
    "ChartLayout",
    "GridLayout",
]
