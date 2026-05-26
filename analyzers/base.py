"""
分析器基类模块

定义了所有分析器的统一接口规范。
每个具体的分析器（面经总结、模拟面试、简历优化）都必须继承此基类，
实现 name 属性和 analyze 方法，确保主流程可以统一调用。
"""

from abc import ABC, abstractmethod


class BaseAnalyzer(ABC):
    """
    分析器抽象基类。

    所有分析器共享同一个 AI 客户端实例，通过实现 analyze() 方法
    来定义各自的分析逻辑和 prompt 策略。
    """

    def __init__(self, ai_client):
        """
        Args:
            ai_client: AIClient 实例，用于调用 AI 接口
        """
        self.ai_client = ai_client

    @property
    @abstractmethod
    def name(self) -> str:
        """
        分析器的中文显示名称。
        在前端进度提示中展示，如 "面经总结与考点分析"、"模拟面试题目预测"。
        """
        ...

    @abstractmethod
    async def analyze(self, experiences: list[dict], resume_text: str = "") -> dict:
        """
        执行分析逻辑。

        Args:
            experiences: 面经列表，每条包含 title、url、content、tags 等字段
            resume_text: 用户上传的简历文本，可能为空字符串

        Returns:
            分析结果字典，结构由各分析器自行定义
        """
        ...

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
            lines.append(f"内容:\n{exp.get('content', '')[:2000]}")
        return "\n".join(lines)
