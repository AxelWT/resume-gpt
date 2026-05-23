from analyzers.base import BaseAnalyzer


MOCK_INTERVIEW_PROMPT = """你是一个资深面试官。请根据以下面经内容和用户简历，生成模拟面试题目预测。

要求输出 JSON 格式（不要 markdown 包裹），结构如下：
{{
  "total_questions": 题目总数,
  "categories": [
    {{
      "type": "技术题 / 项目经验 / 行为面试 / 其他",
      "questions": [
        {{
          "question": "具体的面试题目",
          "reason": "为什么可能会问这道题（结合面经和简历）",
          "difficulty": "简单/中等/困难",
          "suggested_answer": "回答思路或要点"
        }}
      ]
    }}
  ]
}}

面经内容：
{experiences}

{resume_section}"""


class MockInterviewAnalyzer(BaseAnalyzer):
    @property
    def name(self) -> str:
        return "模拟面试题目预测"

    async def analyze(
        self, experiences: list[dict], resume_text: str = ""
    ) -> dict:
        exp_text = self._format_experiences(experiences)
        resume_section = ""
        if resume_text:
            resume_section = f"\n用户简历：\n{resume_text}\n请结合简历中的项目经历和技术栈，个性化预测题目。"

        prompt = MOCK_INTERVIEW_PROMPT.format(
            experiences=exp_text,
            resume_section=resume_section,
        )

        return await self.ai_client.chat_json([
            {"role": "system", "content": "你是一个资深面试官AI助手，输出必须是合法JSON。"},
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
