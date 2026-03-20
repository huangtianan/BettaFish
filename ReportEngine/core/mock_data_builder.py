"""
模板设计阶段的虚拟数据构造器。

用于在“仅有模板、尚无真实业务数据”时，为布局/篇幅规划节点
提供结构化输入，便于预览模板效果。
"""

from __future__ import annotations

import json
import asyncio
import threading
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .template_parser import TemplateSection


def build_mock_inputs_for_template(
    template_name: str,
    template_overview: Dict[str, Any],
    sections: List[TemplateSection],
    query: str = "",
    llm_client: Optional[Any] = None,
    code_executor: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    根据模板语义生成虚拟输入（与正式流程 inputs 格式一致）。

    参数:
        template_name: 模板名称（可用于判断报告类型）。
        template_overview: 模板概览结构。
        sections: 模板切片后的章节列表。
        query: 可选主题词，作为模拟语境补充。

    返回:
        list[dict]: 与正式 generate_report(inputs) 一致的输入条目列表。
    """
    # 优先使用 LLM 生成更“像真数据”的 mock（根据模板骨架动态生成）
    if llm_client is not None and code_executor is not None:
        try:
            llm_items = _build_items_via_llm_and_python(
                llm_client=llm_client,
                code_executor=code_executor,
                template_name=template_name,
                template_overview=template_overview,
                sections=sections,
                query=query,
            )
            if llm_items:
                return llm_items
        except Exception as e:
            # LLM mock 失败则回退到内置规则
            print(f"LLM mock 失败: {e}")
            return []

    template_hint = f"{template_name} {template_overview.get('title', '')} {query}".lower()
    profile = _pick_profile(template_hint)
    return _build_items(profile, sections, query)


@dataclass
class _MockAttachment:
    type: Any
    content: str
    extra: Any


class _LightPostProxy:
    """仅用于 CodeExecutor.process_code_output 抽取附件 url 的轻量代理。"""

    def __init__(self) -> None:
        self.attachments: List[_MockAttachment] = []

    def update_attachment(self, message: str, type=None, extra: Any = None, **kwargs):  # noqa: A002
        self.attachments.append(_MockAttachment(type=type, content=message, extra=extra))
        return self.attachments[-1]


def _build_items_via_llm_and_python(
    *,
    llm_client: Any,
    code_executor: Any,
    template_name: str,
    template_overview: Dict[str, Any],
    sections: List[TemplateSection],
    query: str,
) -> List[Dict[str, Any]]:
    """
    使用注入的 LLM 为不同模板生成不同的 mock inputs。

    产出要求：
    - 至少包含 1 个 summary
    - 至少包含 1 个 table（content 为 list[dict] 的 JSON 字符串）
    - 至少包含 1 个 plotly（content 为 plotly JSON 字符串）
    """
    items: List[Dict[str, Any]] = []
    topic = query or template_overview.get("title") or template_name or "示例主题"

    system_prompt = (
        "你是一个 Python 数据分析工程师，只做一件事："
        "为给定的一组章节生成一段完整可执行的 Python 代码，模拟表格数据并调用 plotly_visualization 生成图表。"
        "严格要求："
        "1. 只输出一个 JSON 对象，格式必须是：{\"code\": \"<python源码>\"}。"
        "2. 不要输出 markdown，不要输出解释文字，不要输出其它字段。"
        "3. code 字段中的 Python 源码必须可以直接执行，第一行从 import 开始，最后一行必须是："
        "   print(json.dumps(outputs, ensure_ascii=False))。"
        "4. 代码结构固定为："
        "   - import 部分（至少 import json, import pandas as pd）"
        "   - 代码内部必须先定义 CHAPTERS = [...]（将所有章节信息内嵌到代码里；每项含 chapter_index/chapter_title/chapter_outline）"
        "   - 遍历 CHAPTERS：对每个章节按章节类型决定输出"
        "   - 若 chapter_title/outline 包含纯文本关键词（行动/计划/举措/步骤/流程/机制/复盘/监控/执行/建议）：跳过该章节（continue），不生成 table_rows、不生成 chart、不追加任何 outputs 元素。"
        "   - 否则（非纯文本章节）：必须追加 1 条 type='json' 输出（先生成 table_rows，再 json.dumps 成字符串作为 output）。"
        "   - chart 是可选的：仅当章节更像需要可视化（趋势/分布/对比/偏差/矩阵/图/曲线/柱状/热力/概率/风险/机会/驱动/阻力）时追加 type='plotly'；追加 chart 时才把 table_rows 转成 df 并调用 plotly_visualization。"
        "   - 生成 chart 时必须按插件参数名用关键字参数调用："
        "     `fig = plotly_visualization(data=df, plot_type=<...>, x_cols=[...], y_cols=[...], title=<str>)`；"
        "     禁止使用 `chart_type=`、`x=`、`y=`，禁止位置参数调用。"
        "   - plotly_visualization目前支持Literal[\"line\", \"bar\", \"pie\", \"double_y\", \"histogram\", \"scatter\", \"area\", \"box\", \"candlestick\", \"funnel\", \"radar\", \"heatmap\"]。"
        "   - 构造 outputs：纯文本章节跳过；非纯文本章节至少输出 json，chart 可选，所以 outputs 数量不固定，允许 outputs 为空列表。"
        "   - outputs 的元素格式必须严格是："
        "       {'name': <str>, 'type': 'json'|'plotly', 'desc': <str>, 'output': <str>}"
        "     其中："
        "       - json 的 output 必须是 table_rows 的 JSON 字符串（list[dict] 的 json.dumps 结果，确保 output 为 str）"
        "       - plotly 的 output 必须是 fig.to_json() 的 JSON 字符串"
        "       - name/desc 必须包含 chapter_index 和 chapter_title，保证后续可追溯到章节"
        "   - print(json.dumps(outputs, ensure_ascii=False))"
        "5. 不要使用随机数种子，不要使用 MQL，不要访问网络和文件。"
        "6. 严格禁止在代码中自定义plotly_visualization 必须只调用运行环境注入的 plotly_visualization 插件函数。"
        "7. 严格禁止在代码中 import plotly.express/plotly.graph_objects/px/go；也不要生成 def plotly_visualization(...)。"
    )

    sections_payload: List[Dict[str, Any]] = []
    for idx, section in enumerate(sections, start=1):
        sections_payload.append(
            {
                "chapter_index": idx,
                "chapter_title": section.title,
                "chapter_outline": list(section.outline or [])[:8],
            }
        )

    user_payload = {
        "topic": topic,
        "templateName": template_name,
        "sections": sections_payload,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False)

    raw = llm_client.invoke(system_prompt, user_prompt)
    if not raw:
        return items

    try:
        obj = json.loads(raw)
        code = obj.get("code", "") if isinstance(obj, dict) else ""
    except Exception:
        return items
    code = str(code or "").strip()
    if not code:
        return items

    # 执行一次代码，outputs 中包含所有章节的数据；url 由 CodeExecutor 负责生成
    proxy = _LightPostProxy()
    exec_id = "mock_design_all"
    result = _run_coro_sync(code_executor.execute_code(exec_id=exec_id, code=code))
    proxy, _ = code_executor.process_code_output(
        result,
        proxy,
        only_output_type="any",
        is_mask=False,
        is_show_full_data=False,
    )

    extracted = _extract_items_from_proxy(proxy)
    items.extend(extracted)

    

    return items


def _run_coro_sync(coro):
    """
    在同步上下文运行协程：
    - 如果当前线程没有 running loop：直接 asyncio.run
    - 如果已有 running loop（常见于 FastAPI/async 环境）：新线程中 asyncio.run
    """
    try:
        loop = asyncio.get_running_loop()
        if loop and loop.is_running():
            box: Dict[str, Any] = {}

            def _runner():
                box["result"] = asyncio.run(coro)

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join()
            return box["result"]
    except RuntimeError:
        pass
    return asyncio.run(coro)


def _extract_urls_from_proxy(proxy: _LightPostProxy) -> Tuple[str, str, str, str]:
    try:
        from nextagent.memory.attachment import AttachmentType as _AttachmentType  # type: ignore
    except Exception:  # pragma: no cover
        _AttachmentType = None

    table_url = ""
    chart_url = ""
    table_content = ""
    chart_content = ""
    for att in proxy.attachments:
        extra = att.extra or {}
        if isinstance(extra, dict) and extra.get("url"):
            url = str(extra.get("url") or "")
            if not url:
                continue
            if (_AttachmentType is not None and att.type == _AttachmentType.table) or str(att.type).endswith("AttachmentType.table"):
                table_url = url
                table_content = att.content or table_content
            if (_AttachmentType is not None and att.type == _AttachmentType.plotly) or str(att.type).endswith("AttachmentType.plotly"):
                chart_url = url
                chart_content = att.content or chart_content
    return table_url, chart_url, table_content, chart_content


def _extract_items_from_proxy(proxy: _LightPostProxy) -> List[Dict[str, Any]]:
    """
    从 CodeExecutor.process_code_output 生成的附件中提取所有 table/plotly url，
    每个 url 都对应一个 mock input item。
    """
    try:
        from nextagent.memory.attachment import AttachmentType as _AttachmentType  # type: ignore
    except Exception:  # pragma: no cover
        _AttachmentType = None

    extracted: List[Dict[str, Any]] = []
    for att in proxy.attachments:
        extra = att.extra or {}
        url = str(extra.get("url") or "")
        if not url:
            continue

        # table
        if (_AttachmentType is not None and att.type == _AttachmentType.table) or str(att.type).endswith(
            "AttachmentType.table"
        ):
            extracted.append(
                {
                    "outputType": "table",
                    "query": str(extra.get("query") or ""),
                    "content": att.content or "",
                    "url": url,
                }
            )
            continue

        # plotly
        if (_AttachmentType is not None and att.type == _AttachmentType.plotly) or str(att.type).endswith(
            "AttachmentType.plotly"
        ):
            extracted.append(
                {
                    "outputType": "plotly",
                    "query": str(extra.get("query") or ""),
                    "content": att.content or "",
                    "url": url,
                }
            )
            continue

    return extracted


def _pick_profile(template_hint: str) -> str:
    """按模板关键词粗分虚拟数据画像。"""
    if any(token in template_hint for token in ("品牌", "声誉", "公关", "危机")):
        return "brand_reputation"
    if any(token in template_hint for token in ("竞争", "市场", "份额")):
        return "market_competition"
    if any(token in template_hint for token in ("政策", "行业", "监管")):
        return "policy_industry"
    return "generic_business"


def _build_items(profile: str, sections: List[TemplateSection], query: str) -> List[Dict[str, Any]]:
    """构造轻量可读的模拟条目，覆盖 summary/text/widget 三类输入。"""
    topic = query or "示例主题"
    section_titles = [section.title for section in sections[:5]]
    section_brief = "；".join(section_titles) if section_titles else "章节结构待补充"

    if profile == "brand_reputation":
        return [
            {
                "outputType": "summary",
                "query": f"{topic} 舆情总览",
                "content": (
                    "近30天全网相关讨论热度上升，正负面分化明显。"
                    "品牌口碑在服务体验与售后环节出现争议。"
                ),
            },
            {
                "outputType": "text",
                "query": f"{topic} 章节骨架",
                "content": f"模板关注章节：{section_brief}",
            },
            {
                "outputType": "plotly",
                "query": f"{topic} 热度趋势图",
                "url": "https://example.com/widgets/mock-brand-trend",
            },
        ]

    if profile == "market_competition":
        return [
            {
                "outputType": "summary",
                "query": f"{topic} 竞争格局",
                "content": "头部企业竞争激烈，中腰部企业通过细分场景实现差异化增长。",
            },
            {
                "outputType": "text",
                "query": f"{topic} 用户需求变化",
                "content": "用户关注点从价格转向综合体验与交付效率。",
            },
            {
                "outputType": "plotly",
                "query": f"{topic} 份额变化图",
                "url": "https://example.com/widgets/mock-market-share",
            },
        ]

    if profile == "policy_industry":
        return [
            {
                "outputType": "summary",
                "query": f"{topic} 政策动态",
                "content": "监管导向趋严，合规与数据治理要求提升，行业进入结构性调整阶段。",
            },
            {
                "outputType": "text",
                "query": f"{topic} 行业影响",
                "content": "短期成本上升，中长期有利于头部企业规范化扩张。",
            },
            {
                "outputType": "plotly",
                "query": f"{topic} 政策影响路径图",
                "url": "https://example.com/widgets/mock-policy-impact",
            },
        ]

    return [
        {
            "outputType": "summary",
            "query": f"{topic} 总览",
            "content": "整体趋势稳中有变，建议围绕增长、风险与执行三条主线组织报告。",
        },
        {
            "outputType": "text",
            "query": f"{topic} 模板结构",
            "content": f"建议按以下章节铺陈：{section_brief}",
        },
        {
            "outputType": "plotly",
            "query": f"{topic} 指标趋势图",
            "url": "https://example.com/widgets/mock-generic-kpi",
        },
    ]

