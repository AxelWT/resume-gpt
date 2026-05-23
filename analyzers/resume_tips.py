from analyzers.base import BaseAnalyzer


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
    @property
    def name(self) -> str:
        return "简历优化建议"

    async def analyze(
        self, experiences: list[dict], resume_text: str = ""
    ) -> dict:
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

        return await self.ai_client.chat_json([
            {"role": "system", "content": "你是一个简历优化专家AI助手，输出必须是合法JSON。"},
            {"role": "user", "content": prompt},
        ])

    def _format_experiences(self, experiences: list[dict]) -> str:
        lines = []
        for i, exp in enumerate(experiences, 1):
            lines.append(f"--- 面经 {i} ---")
            lines.append(f"标题: {exp.get('title', '')}")
            lines.append(f"标签: {', '.join(exp.get('tags', []))}")
            lines.append(f"内容:\n{exp.get('content', '')[:2000]}")
        return "\n".join(lines)
