"""
面经总结与考点分析器

对爬取的多条面经进行汇总分析，提取高频考点和知识点分类。
如果用户提供了简历，还会分析简历与面经考点的匹配度。
"""

from analyzers.base import BaseAnalyzer

# AI 提示词模板：要求 AI 对面经进行总结，提取考点频率和知识分类
SUMMARY_PROMPT = """你是一个资深面试辅导专家。请根据以下面经内容，进行面经总结与考点分析。

要求输出 JSON 格式（不要 markdown 包裹），结构如下：
{{
  "summary": "整体面经趋势总结（2-3句话）",
  "total_experiences": 面经总数,
  "key_points": [
    {{"name": "考点名称", "frequency": "高频/中频/低频", "count": 出现次数, "description": "该考点的详细说明"}}
  ],
  "categories": [
    {{"name": "知识点分类名", "items": ["具体知识点1", "知识点2"]}}
  ]
}}

面经内容：
{experiences}

{resume_section}"""


class SummaryAnalyzer(BaseAnalyzer):
    """面经总结与考点分析器，提取面经中的高频考点和知识分类"""

    @property
    def name(self) -> str:
        """分析器显示名称"""
        return "面经总结与考点分析"

    async def analyze(
        self, experiences: list[dict], resume_text: str = ""
    ) -> dict:
        """
        执行面经总结分析。

        Args:
            experiences: 面经列表
            resume_text: 用户简历文本（可选，提供时会追加匹配度分析）

        Returns:
            包含 summary、total_experiences、key_points、categories 的字典
        """
        # 将面经列表格式化为文本
        exp_text = self._format_experiences(experiences)
        # 如果用户提供了简历，追加到 prompt 中让 AI 分析匹配度
        resume_section = ""
        if resume_text:
            resume_section = f"\n用户简历：\n{resume_text}\n请结合简历背景，分析面经考点与简历的匹配度。"

        # 组装完整的 prompt
        prompt = SUMMARY_PROMPT.format(
            experiences=exp_text,
            resume_section=resume_section,
        )

        # 调用 AI 接口，要求返回 JSON 格式的分析结果
        return await self.ai_client.chat_json([
            {"role": "system", "content": "你是一个专业的面试辅导AI助手，输出必须是合法JSON。"},
            {"role": "user", "content": prompt},
        ])

    def _format_experiences(self, experiences: list[dict]) -> str:
        """
        将面经列表格式化为 AI 可读的文本。

        Args:
            experiences: 面经列表，每条包含 title、tags、content

        Returns:
            格式化后的文本字符串，每条面经截取前 2000 字符
        """
        lines = []
        for i, exp in enumerate(experiences, 1):
            lines.append(f"--- 面经 {i} ---")
            lines.append(f"标题: {exp.get('title', '')}")
            lines.append(f"标签: {', '.join(exp.get('tags', []))}")
            # 截取前 2000 字符，控制 prompt 长度
            lines.append(f"内容:\n{exp.get('content', '')[:2000]}")
        return "\n".join(lines)
