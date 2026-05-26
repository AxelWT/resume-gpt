"""
模拟面试题目预测分析器

根据爬取的面经内容和用户简历，利用 AI 生成针对性的模拟面试题目。
题目按类型分类（技术题、项目经验、行为面试等），并附带难度和回答思路。
"""

from analyzers.base import BaseAnalyzer

# AI 提示词模板：要求 AI 扮演资深面试官，根据面经和简历生成面试题目预测
# 使用 {{ }} 转义 JSON 中的花括号，因为外层使用 .format() 格式化
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
    """模拟面试题目预测分析器，生成基于面经的个性化面试题目"""

    @property
    def name(self) -> str:
        """分析器显示名称"""
        return "模拟面试题目预测"

    async def analyze(self, experiences: list[dict], resume_text: str = "") -> dict:
        """
        执行模拟面试题目预测分析。

        Args:
            experiences: 面经列表
            resume_text: 用户简历文本（可选）

        Returns:
            包含 total_questions 和 categories 的字典
        """
        # 将面经列表格式化为文本
        exp_text = self._format_experiences(experiences)
        # 如果用户提供了简历，在 prompt 中追加简历内容，要求 AI 结合简历个性化出题
        resume_section = ""
        if resume_text:
            resume_section = f"\n用户简历：\n{resume_text}\n请结合简历中的项目经历和技术栈，个性化预测题目。"

        # 组装完整的 prompt
        prompt = MOCK_INTERVIEW_PROMPT.format(
            experiences=exp_text,
            resume_section=resume_section,
        )

        # 调用 AI 接口，要求返回 JSON 格式
        return await self.ai_client.chat_json(
            [
                {
                    "role": "system",
                    "content": "你是一个资深面试官AI助手，输出必须是合法JSON。",
                },
                {"role": "user", "content": prompt},
            ]
        )
