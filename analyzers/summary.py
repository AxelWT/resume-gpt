from analyzers.base import BaseAnalyzer


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
    @property
    def name(self) -> str:
        return "面经总结与考点分析"

    async def analyze(
        self, experiences: list[dict], resume_text: str = ""
    ) -> dict:
        exp_text = self._format_experiences(experiences)
        resume_section = ""
        if resume_text:
            resume_section = f"\n用户简历：\n{resume_text}\n请结合简历背景，分析面经考点与简历的匹配度。"

        prompt = SUMMARY_PROMPT.format(
            experiences=exp_text,
            resume_section=resume_section,
        )

        return await self.ai_client.chat_json([
            {"role": "system", "content": "你是一个专业的面试辅导AI助手，输出必须是合法JSON。"},
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
