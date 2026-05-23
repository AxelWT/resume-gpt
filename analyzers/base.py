from abc import ABC, abstractmethod


class BaseAnalyzer(ABC):
    def __init__(self, ai_client):
        self.ai_client = ai_client

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def analyze(
        self, experiences: list[dict], resume_text: str = ""
    ) -> dict:
        ...
