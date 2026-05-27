"""
模拟面试题目预测分析器

根据爬取的面经内容和岗位描述，利用 AI 生成针对性的模拟面试题目。
面经用于提取面试常见问题，岗位描述用于提取技能考察方向，
综合两类数据生成更精准的面试题目预测。
"""

from analyzers.base import BaseAnalyzer

MOCK_INTERVIEW_PROMPT = """你是一个资深面试官。请根据以下数据内容，生成模拟面试题目预测。

数据中包含两种类型：
- **面经**：面试经验分享，包含面试问题、面试流程等
- **岗位描述**：招聘信息，包含职位要求、技能要求等

请综合两类数据生成面试题目：
- 从面经中提取真实出现过的面试问题
- 从岗位描述中推断可能会被考察的技能方向和项目经验
- 题目应兼顾技术深度和实际岗位需求

要求输出 JSON 格式（不要 markdown 包裹），结构如下：
{{
  "total_questions": 题目总数,
  "categories": [
    {{
      "type": "技术题 / 项目经验 / 行为面试 / 其他",
      "questions": [
        {{
          "question": "具体的面试题目",
          "reason": "为什么可能会问这道题（结合面经和岗位描述）",
          "difficulty": "简单/中等/困难",
          "suggested_answer": "回答思路或要点"
        }}
      ]
    }}
  ]
}}

数据内容：
{experiences}

{resume_section}"""


class MockInterviewAnalyzer(BaseAnalyzer):
    """模拟面试题目预测分析器，综合面经和岗位描述生成个性化面试题目"""

    @property
    def name(self) -> str:
        return "模拟面试题目预测"

    async def analyze(self, experiences: list[dict], resume_text: str = "") -> dict:
        """
        执行模拟面试题目预测分析。

        Args:
            experiences: 数据列表（面经 + 岗位描述）
            resume_text: 用户简历文本（可选）

        Returns:
            包含 total_questions 和 categories 的字典
        """
        exp_text = self._format_experiences(experiences)
        resume_section = ""
        if resume_text:
            resume_section = f"\n用户简历：\n{resume_text}\n请结合简历中的项目经历和技术栈，个性化预测题目。"

        prompt = MOCK_INTERVIEW_PROMPT.format(
            experiences=exp_text,
            resume_section=resume_section,
        )

        return await self.ai_client.chat_json(
            [
                {
                    "role": "system",
                    "content": "你是一个资深面试官AI助手，输出必须是合法JSON。",
                },
                {"role": "user", "content": prompt},
            ]
        )
