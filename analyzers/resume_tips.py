"""
简历优化建议分析器

将用户上传的简历与面经中的考点进行对比分析，
给出简历匹配度评分、具体修改建议、需要补充的关键词等优化方案。
"""

from analyzers.base import BaseAnalyzer

# AI 提示词模板：要求 AI 扮演简历优化专家，对比面经考点和用户简历给出优化建议
RESUME_TIPS_PROMPT = """你是一个资深简历优化专家。请根据以下面经考点和用户简历，给出简历优化建议。

要求输出 JSON 格式（不要 markdown 包裹），结构如下：
{{
  "match_analysis": "简历与岗位的匹配度整体评价（2-3句话）",
  "match_score": 匹配度分数(0-100),
  "suggestions": [
    {{
      "category": "项目描述 / 技能关键词 / 经历补充 / 排版格式",
      "title": "建议标题",
      "detail": "具体修改建议",
      "priority": "高/中/低"
    }}
  ],
  "keywords_to_add": ["建议补充的技能词1", "技能词2"],
  "keywords_to_highlight": ["简历中已有的亮点技能"]
}}

面经考点摘要：
{experiences}

用户简历：
{resume_text}

请对比分析哪些方面可以优化。"""


class ResumeTipsAnalyzer(BaseAnalyzer):
    """简历优化建议分析器，对比面经考点给出简历改进方案"""

    @property
    def name(self) -> str:
        """分析器显示名称"""
        return "简历优化建议"

    async def analyze(self, experiences: list[dict], resume_text: str = "") -> dict:
        """
        执行简历优化分析。

        Args:
            experiences: 面经列表
            resume_text: 用户简历文本（必须提供，否则无法分析）

        Returns:
            包含 match_score、suggestions、keywords_to_add 等字段的字典。
            如果未提供简历，返回包含 error 提示的默认结果。
        """
        # 简历优化必须提供简历文本，否则直接返回提示
        if not resume_text:
            return {
                "error": "未上传简历，无法提供简历优化建议",
                "match_score": 0,
                "suggestions": [],
            }

        # 将面经格式化为摘要文本
        exp_text = self._format_experiences(experiences)

        # 组装 prompt，将面经和简历内容都传给 AI
        prompt = RESUME_TIPS_PROMPT.format(
            experiences=exp_text,
            resume_text=resume_text,
        )

        # 调用 AI 接口获取 JSON 格式的优化建议
        return await self.ai_client.chat_json(
            [
                {
                    "role": "system",
                    "content": "你是一个简历优化专家AI助手，输出必须是合法JSON。",
                },
                {"role": "user", "content": prompt},
            ]
        )
