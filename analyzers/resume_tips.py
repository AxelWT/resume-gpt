"""
简历优化建议分析器

将用户上传的简历与面经考点和岗位要求进行对比分析，
给出简历匹配度评分、具体修改建议、需要补充的关键词等优化方案。
"""

from analyzers.base import BaseAnalyzer

RESUME_TIPS_PROMPT = """你是一个资深简历优化专家。请根据以下数据内容和用户简历，给出简历优化建议。

数据中包含两种类型：
- **面经**：面试经验分享，反映面试官关注的考点和考察方向
- **岗位描述**：招聘信息，明确列出了技能要求和职位职责

请综合两类数据与用户简历进行对比：
- 从岗位描述中提取核心技能要求，检查简历是否覆盖
- 从面经中提取高频考点，评估简历是否体现相关经验
- 给出具体的优化建议和关键词补充

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

数据内容：
{experiences}

用户简历：
{resume_text}

请对比分析哪些方面可以优化。"""


class ResumeTipsAnalyzer(BaseAnalyzer):
    """简历优化建议分析器，对比面经考点和岗位要求给出简历改进方案"""

    @property
    def name(self) -> str:
        return "简历优化建议"

    async def analyze(self, experiences: list[dict], resume_text: str = "") -> dict:
        """
        执行简历优化分析。

        Args:
            experiences: 数据列表（面经 + 岗位描述）
            resume_text: 用户简历文本（必须提供，否则无法分析）

        Returns:
            包含 match_score、suggestions、keywords_to_add 等字段的字典。
            如果未提供简历，返回包含 error 提示的默认结果。
        """
        if not resume_text:
            return {
                "error": "未上传简历，无法提供简历优化建议",
                "match_score": 0,
                "suggestions": [],
            }

        exp_text = self._format_experiences(experiences)

        prompt = RESUME_TIPS_PROMPT.format(
            experiences=exp_text,
            resume_text=resume_text,
        )

        return await self.ai_client.chat_json(
            [
                {
                    "role": "system",
                    "content": "你是一个简历优化专家AI助手，输出必须是合法JSON。",
                },
                {"role": "user", "content": prompt},
            ]
        )
