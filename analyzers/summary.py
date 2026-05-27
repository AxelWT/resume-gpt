"""
面经与岗位总结分析器

对爬取的面经和岗位描述进行汇总分析，提取高频考点、技能要求和知识点分类。
如果用户提供了简历，还会分析简历与岗位要求的匹配度。
"""

from analyzers.base import BaseAnalyzer

SUMMARY_PROMPT = """你是一个资深面试辅导与职业规划专家。请根据以下数据内容，进行总结与考点分析。

数据中包含两种类型：
- **面经**：面试经验分享，包含面试问题、面试流程、面试感受等
- **岗位描述**：招聘信息，包含职位要求、工作职责、技能要求等

请综合分析两类数据，面经用于提取面试考点和常见问题，岗位描述用于提取技能要求和职位核心能力。

要求输出 JSON 格式（不要 markdown 包裹），结构如下：
{{
  "summary": "整体趋势总结（2-3句话，综合面经和岗位描述的发现）",
  "total_experiences": 数据总条数,
  "key_points": [
    {{"name": "考点/技能名称", "frequency": "高频/中频/低频", "count": 出现次数, "description": "详细说明（来源：面经/岗位描述/两者均有）"}}
  ],
  "categories": [
    {{"name": "知识点分类名", "items": ["具体知识点1", "知识点2"]}}
  ]
}}

数据内容：
{experiences}

{resume_section}"""


class SummaryAnalyzer(BaseAnalyzer):
    """面经与岗位总结分析器，提取面经考点和岗位技能要求"""

    @property
    def name(self) -> str:
        return "面经总结与考点分析"

    async def analyze(self, experiences: list[dict], resume_text: str = "") -> dict:
        """
        执行总结分析。

        Args:
            experiences: 数据列表（面经 + 岗位描述）
            resume_text: 用户简历文本（可选，提供时会追加匹配度分析）

        Returns:
            包含 summary、total_experiences、key_points、categories 的字典
        """
        exp_text = self._format_experiences(experiences)
        resume_section = ""
        if resume_text:
            resume_section = f"\n用户简历：\n{resume_text}\n请结合简历背景，分析考点和技能要求与简历的匹配度。"

        prompt = SUMMARY_PROMPT.format(
            experiences=exp_text,
            resume_section=resume_section,
        )

        return await self.ai_client.chat_json(
            [
                {
                    "role": "system",
                    "content": "你是一个专业的面试辅导与职业规划AI助手，输出必须是合法JSON。",
                },
                {"role": "user", "content": prompt},
            ]
        )
