"""
Resume-GPT 主应用入口

基于 FastAPI 构建的 Web 应用，提供面经分析、模拟面试、简历优化等 AI 驱动的求职辅助功能。
前端通过轮询 /api/status/{task_id} 获取异步任务的实时进度和结果。
"""

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

# ==================== FastAPI 应用实例 ====================

app = FastAPI(title="resume-gpt")

# 允许所有来源的跨域请求，方便本地开发和前后端分离部署
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 项目根目录，用于定位模板等静态资源
BASE_DIR = Path(__file__).parent

# ==================== 任务存储 ====================
# 使用内存字典存储异步任务的进度和结果
# key: task_id (12位随机hex), value: 任务状态字典
# 注意: 仅适用于单 worker 部署，多 worker 下各进程内存不共享
tasks: dict[str, dict] = {}


# ==================== 请求模型定义 ====================

class TestConfigRequest(BaseModel):
    """测试 AI 模型配置是否有效的请求体"""
    base_url: str       # OpenAI 兼容 API 的基础地址，如 https://api.openai.com/v1
    api_key: str        # API 密钥
    model_name: str     # 模型名称，如 gpt-4o、deepseek-chat 等


class AnalyzeRequest(BaseModel):
    """启动分析任务的请求体"""
    base_url: str               # AI API 基础地址
    api_key: str                # API 密钥
    model_name: str             # 模型名称
    query: str                  # 搜索关键词，用于在牛客网搜索相关面经
    modules: list[str]          # 要执行的分析模块列表，可选值: summary, mock_interview, resume_tips
    max_count: int = 10         # 最多爬取多少条面经，默认 10 条
    resume_text: str = ""       # 用户上传的简历文本（可选），用于结合简历做个性化分析


# ==================== API 路由 ====================

@app.post("/api/test-config")
async def test_config(req: TestConfigRequest):
    """
    测试 AI 模型配置是否可用。
    发送一条简短消息验证 API 地址、密钥和模型名是否正确。
    """
    try:
        client = AIClient(req.base_url, req.api_key, req.model_name)
        await client.test()
        return {"status": "ok", "message": "连接成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze")
async def start_analyze(req: AnalyzeRequest):
    """
    启动异步分析任务。
    创建一个后台任务来执行面经爬取和 AI 分析，
    立即返回 task_id 供前端轮询进度。
    """
    # 生成唯一的任务 ID（取 UUID 前 12 位）
    task_id = uuid.uuid4().hex[:12]
    tasks[task_id] = {"status": "pending", "progress": 0, "result": None, "error": None}

    # 将分析任务提交到事件循环中异步执行，不阻塞当前请求
    asyncio.create_task(run_analysis(task_id, req))
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """
    查询指定任务的当前状态和进度。
    前端每隔约 1 秒调用此接口轮询任务进度。
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "status": task["status"],      # pending | running | completed | failed
        "progress": task["progress"],  # 0-100 的进度百分比
        "result": task["result"],      # 分析完成后的结果数据
        "error": task["error"],        # 失败时的错误信息
    }


# ==================== 核心分析流程 ====================

async def run_analysis(task_id: str, req: AnalyzeRequest):
    """
    异步执行完整的分析流程，包括：
    1. 初始化并测试 AI 客户端连接
    2. 根据关键词爬取牛客网面经
    3. 获取每条面经的详细内容
    4. 按用户选择的分析模块逐个执行 AI 分析
    5. 汇总结果并更新任务状态
    """
    task = tasks[task_id]
    try:
        task["status"] = "running"
        task["progress"] = 5

        # Step 1: 初始化 AI 客户端并验证连接
        ai_client = AIClient(req.base_url, req.api_key, req.model_name)
        await ai_client.test()
        task["progress"] = 10

        # Step 2: 爬取牛客网面经列表
        task["message"] = "正在爬取牛客网面经..."
        crawler = NowCrawler()
        experiences = await crawler.search(req.query, req.max_count)
        task["progress"] = 30

        # 如果没搜到任何面经，直接返回提示
        if not experiences:
            task["status"] = "completed"
            task["progress"] = 100
            task["result"] = {"error": "未找到相关面经，请尝试其他搜索词"}
            return

        # Step 3: 逐条获取面经的正文详情和标签
        task["message"] = f"已找到 {len(experiences)} 条面经，正在获取详情..."
        for exp in experiences:
            try:
                detail = await crawler.fetch_content(exp["url"])
                exp.update(detail)  # 将 content 和 tags 合并到该条面经中
            except Exception:
                # 单条面经获取失败不影响整体流程，置空即可
                exp["content"] = ""
        task["progress"] = 50

        # Step 4: 准备简历文本
        resume_text = req.resume_text
        task["progress"] = 55

        # Step 5: 执行用户选择的分析模块
        result = {"modules": {}, "experiences": experiences}

        # 可用的分析器映射表
        analyzers = {
            "summary": SummaryAnalyzer(ai_client),           # 面经总结与考点分析
            "mock_interview": MockInterviewAnalyzer(ai_client),  # 模拟面试题目预测
            "resume_tips": ResumeTipsAnalyzer(ai_client),    # 简历优化建议
        }

        # 过滤出用户实际选择的分析模块
        step_progress = 0
        selected = [m for m in req.modules if m in analyzers]
        # 将 35% 的进度平均分配给各模块（55% → 90%）
        progress_per_module = 35 // max(len(selected), 1)

        for module_key in selected:
            analyzer = analyzers[module_key]
            task["message"] = f"正在执行: {analyzer.name}"
            # 调用分析器执行分析，将结果存入对应模块
            result["modules"][module_key] = await analyzer.analyze(
                experiences, resume_text
            )
            # 每完成一个模块，更新一次进度
            step_progress += progress_per_module
            task["progress"] = 55 + step_progress

        task["progress"] = 90
        task["message"] = "正在整理报告..."

        # 将最终结果写入任务
        task["result"] = result
        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "分析完成"

    except Exception as e:
        # 任何步骤出错都标记任务为失败，记录错误信息
        task["status"] = "failed"
        task["error"] = str(e)


@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    上传 PDF 简历文件，提取其中的文本内容。
    返回纯文本供后续分析模块使用。
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件")

    # 读取文件二进制内容，在内存中解析 PDF 提取文本
    content = await file.read()
    text = parse_resume(content)
    if not text.strip():
        raise HTTPException(status_code=400, detail="无法从 PDF 中提取文本，请确认文件内容为可识别文本")
    return {"text": text}


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端单页面应用的 HTML"""
    html_path = BASE_DIR / "templates" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/favicon.ico")
async def favicon():
    """浏览器自动请求的图标文件，返回 204 No Content 避免报错"""
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn
    # 开发模式启动，启用热重载
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
