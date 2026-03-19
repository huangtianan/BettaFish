"""
模板设计阶段的虚拟数据构造器。

用于在“仅有模板、尚无真实业务数据”时，为布局/篇幅规划节点
提供结构化输入，便于预览模板效果。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .template_parser import TemplateSection


def build_mock_inputs_for_template(
    template_name: str,
    template_overview: Dict[str, Any],
    sections: List[TemplateSection],
    query: str = "",
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
    template_hint = f"{template_name} {template_overview.get('title', '')} {query}".lower()
    profile = _pick_profile(template_hint)
    return _build_items(profile, sections, query)


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

