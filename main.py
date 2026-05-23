import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from scraper.nowcoder import NowCrawler
from ai.client import AIClient
from utils.pdf_parser import parse_resume
from analyzers.summary import SummaryAnalyzer
from analyzers.mock_interview import MockInterviewAnalyzer
from analyzers.resume_tips import ResumeTipsAnalyzer

app = FastAPI(title="resume-gpt")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent

# 任务存储
tasks: dict[str, dict] = {}


class TestConfigRequest(BaseModel):
    base_url: str
    api_key: str
    model_name: str


class AnalyzeRequest(BaseModel):
    base_url: str
    api_key: str
    model_name: str
    query: str
    modules: list[str]
    max_count: int = 10
    resume_text: str = ""


@app.post("/api/test-config")
async def test_config(req: TestConfigRequest):
    try:
        client = AIClient(req.base_url, req.api_key, req.model_name)
        await client.test()
        return {"status": "ok", "message": "连接成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze")
async def start_analyze(req: AnalyzeRequest):
    task_id = uuid.uuid4().hex[:12]
    tasks[task_id] = {"status": "pending", "progress": 0, "result": None, "error": None}

    asyncio.create_task(run_analysis(task_id, req))
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "status": task["status"],
        "progress": task["progress"],
        "result": task["result"],
        "error": task["error"],
    }


async def run_analysis(task_id: str, req: AnalyzeRequest):
    task = tasks[task_id]
    try:
        task["status"] = "running"
        task["progress"] = 5

        # Step 1: 初始化客户端
        ai_client = AIClient(req.base_url, req.api_key, req.model_name)
        await ai_client.test()
        task["progress"] = 10

        # Step 2: 爬取面经
        task["message"] = "正在爬取牛客网面经..."
        crawler = NowCrawler()
        experiences = await crawler.search(req.query, req.max_count)
        task["progress"] = 30

        if not experiences:
            task["status"] = "completed"
            task["progress"] = 100
            task["result"] = {"error": "未找到相关面经，请尝试其他搜索词"}
            return

        # Step 3: 获取面经详情
        task["message"] = f"已找到 {len(experiences)} 条面经，正在获取详情..."
        for exp in experiences:
            try:
                detail = await crawler.fetch_content(exp["url"])
                exp.update(detail)
            except Exception:
                exp["content"] = ""
        task["progress"] = 50

        # Step 4: 获取简历文本
        resume_text = req.resume_text
        task["progress"] = 55

        # Step 5: 执行分析模块
        result = {"modules": {}, "experiences": experiences}

        analyzers = {
            "summary": SummaryAnalyzer(ai_client),
            "mock_interview": MockInterviewAnalyzer(ai_client),
            "resume_tips": ResumeTipsAnalyzer(ai_client),
        }

        step_progress = 0
        selected = [m for m in req.modules if m in analyzers]
        progress_per_module = 35 // max(len(selected), 1)

        for module_key in selected:
            analyzer = analyzers[module_key]
            task["message"] = f"正在执行: {analyzer.name}"
            result["modules"][module_key] = await analyzer.analyze(
                experiences, resume_text
            )
            step_progress += progress_per_module
            task["progress"] = 55 + step_progress

        task["progress"] = 90
        task["message"] = "正在整理报告..."

        task["result"] = result
        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "分析完成"

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)


@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件")

    content = await file.read()
    text = parse_resume(content)
    if not text.strip():
        raise HTTPException(status_code=400, detail="无法从 PDF 中提取文本，请确认文件内容为可识别文本")
    return {"text": text}


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = BASE_DIR / "templates" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
