"""
Resume-GPT 主应用入口

基于 FastAPI 构建的 Web 应用，提供面经分析、岗位信息分析、模拟面试、简历优化等 AI 驱动的求职辅助功能。

架构概览：
    用户浏览器
        │
        ├── GET /                  → 返回前端单页 HTML
        ├── GET /favicon.ico       → 返回 204（避免 404 报错）
        ├── POST /api/test-config  → 测试 AI 模型连接是否可用
        ├── POST /api/analyze      → 提交异步分析任务，返回 task_id
        ├── GET  /api/status/{id}  → 前端轮询任务进度与结果
        ├── POST /api/upload-resume → 上传 PDF 简历，解析返回文本
        ├── GET  /api/health       → 健康检查（供监控使用）
        └── GET  /api/sources      → 获取所有可用的数据来源列表

异步任务模型：
    前端提交分析请求 → 后端创建后台协程 → 立即返回 task_id
    → 前端每秒轮询 /api/status/{task_id} → 后端返回进度百分比和结果

中间件栈（按注册顺序，请求从外到内依次经过）：
    1. CORSMiddleware          — 处理跨域请求
    2. ProxyHeadersMiddleware  — 从 X-Forwarded-For / X-Real-IP 还原真实客户端 IP
    3. SlowAPI Limiter         — 按路由差异化限流

限流策略（应用层 SlowAPI + Nginx 层双重限流）：
    /api/analyze       — 10 次/分钟/IP（分析接口，消耗 AI 调用额度，严格限流）
    /api/upload-resume — 10 次/分钟/IP（上传接口，消耗 PDF 解析资源，严格限流）
    /api/test-config   — 30 次/分钟/IP（测试连接，轻量操作，适度限流）
    /api/status/{id}   — 60 次/分钟/IP（轮询接口，前端每秒调用，宽松限流）
"""

import asyncio
import base64
import logging
import os
import time
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from typing import Optional

from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from scraper.registry import get_crawler, get_sources
from ai.client import AIClient
from utils.pdf_parser import parse_resume
from analyzers.summary import SummaryAnalyzer
from analyzers.mock_interview import MockInterviewAnalyzer
from analyzers.resume_tips import ResumeTipsAnalyzer

# ==================== 任务存储 ====================
# 使用内存字典存储异步任务的进度和结果
# key: task_id (12位随机hex), value: 任务状态字典
# 任务状态字典结构:
#   {
#       "status": "pending" | "running" | "completed" | "failed",  # 任务生命周期状态
#       "progress": 0-100,        # 进度百分比，前端据此渲染进度条
#       "result": dict | None,    # 分析完成后的结构化结果（含 modules 和 experiences）
#       "error": str | None,      # 失败时的错误信息，前端展示给用户
#       "message": str,           # 当前步骤描述，如"正在从牛客网爬取面经..."
#       "finished_at": float,     # 任务完成/失败的时间戳（UNIX 秒），用于过期清理
#   }
tasks: dict[str, dict] = {}

# 任务过期时间：已完成/失败的任务在内存中保留 1 小时后自动清理
# 超过此时间后，前端再次轮询会收到 404（任务不存在）
TASK_TTL_SECONDS = 3600


async def cleanup_expired_tasks():
    """
    后台协程：每 5 分钟清理一次超过 TTL 的已完成/已失败任务，防止内存泄漏。

    运行机制：
        1. 应用启动时通过 lifespan 创建为后台协程，持续运行
        2. 每隔 300 秒（5 分钟）扫描一次 tasks 字典
        3. 找出 status 为 completed/failed 且 finished_at 超过 TASK_TTL_SECONDS 的任务
        4. 从字典中删除这些过期任务
        5. 应用关闭时（lifespan 的 yield 之后），取消此协程

    为什么需要清理：
        如果用户持续提交分析请求但从不重启服务，tasks 字典会无限增长，
        每个任务的结果数据（含完整面经文本）可能达数百 KB，
        长时间运行后可能导致内存占用过高。
    """
    while True:
        await asyncio.sleep(300)
        now = time.time()
        expired = [
            tid
            for tid, t in tasks.items()
            if t["status"] in ("completed", "failed")
            and now - t.get("finished_at", 0) > TASK_TTL_SECONDS
        ]
        for tid in expired:
            del tasks[tid]


@asynccontextmanager
async def lifespan(app):
    """
    FastAPI 应用生命周期管理器。

    使用 asynccontextmanager 实现应用启动/关闭时的资源管理：
        yield 之前：应用启动阶段，创建后台清理协程
        yield 之后：应用关闭阶段，取消后台协程

    参考：https://fastapi.tiangolo.com/advanced/events/#lifespan
    """
    task = asyncio.create_task(cleanup_expired_tasks())
    yield
    task.cancel()


# ==================== FastAPI 应用实例 ====================

# SlowAPI 限流器实例
# key_func=get_remote_address：使用客户端 IP 作为限流的 key
# 注意：当应用部署在 Nginx 反向代理之后时，直接获取的 IP 是 Nginx 的内网 IP，
# 需要配合 ProxyHeadersMiddleware 从 X-Forwarded-For / X-Real-IP 头中还原真实客户端 IP
limiter = Limiter(key_func=get_remote_address)

# 创建 FastAPI 应用实例
# title 参数会显示在自动生成的 OpenAPI 文档页面（/docs）
# lifespan 参数注册应用生命周期管理器
app = FastAPI(title="resume-gpt", lifespan=lifespan)

# 将限流器实例挂载到 app.state，使 @limiter.limit 装饰器能正确工作
# SlowAPI 要求 limiter 实例可通过 request.app.state.limiter 访问
app.state.limiter = limiter

# 注册限流异常处理器：当请求超过限流阈值时，返回 429 Too Many Requests
# 而非默认的 500 Internal Server Error
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ==================== 中间件配置 ====================

# CORS（跨域资源共享）中间件
# 允许所有来源的跨域请求，方便本地开发和前后端分离部署
# 生产环境中建议将 allow_origins 限制为具体的前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发环境友好，生产环境应收紧）
    allow_credentials=False,  # 不允许携带 Cookie 等凭据（本应用使用 API Key 认证，不需要 Cookie）
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头（包括 Authorization 等）
)


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """
    代理头还原中间件。

    问题背景：
        当应用部署在 Nginx 等反向代理之后时，FastAPI 接收到的请求的客户端 IP
        是代理服务器的内网 IP（如 172.18.0.1），而非真实用户的公网 IP。
        这导致 SlowAPI 限流器无法正确识别不同用户，所有请求被视为同一 IP。

    解决方案：
        Nginx 通过 proxy_set_header 将用户真实 IP 写入以下 HTTP 头：
        - X-Forwarded-For: 客户端 IP 链（格式：客户端IP, 代理1 IP, 代理2 IP, ...）
        - X-Real-IP: 客户端真实 IP（由 Nginx 直接设置）

        本中间件从这些头中提取真实客户端 IP，覆盖 request.scope["client"]，
        使后续的 SlowAPI 限流器（基于 get_remote_address）能获取到真实 IP。

    优先级：
        X-Forwarded-For > X-Real-IP（前者支持多级代理链，优先使用）
        对于 X-Forwarded-For，取第一个 IP（最左边的，即原始客户端 IP）

    参考：
        https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Forwarded-For
    """

    def __init__(self, app: ASGIApp, trusted_hosts: str = "*"):
        """
        Args:
            app: ASGI 应用实例（中间件链中的下一个应用）
            trusted_hosts: 信任的代理主机（预留参数，当前未实现校验逻辑）
        """
        super().__init__(app)
        self.trusted_hosts = trusted_hosts

    async def dispatch(self, request: Request, call_next):
        # 尝试从 X-Forwarded-For 头获取真实客户端 IP
        # 格式示例：X-Forwarded-For: 203.0.113.50, 70.41.3.18
        # 取第一个（最左侧的）IP，即原始客户端 IP
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        x_real_ip = request.headers.get("X-Real-IP")

        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()
            # 覆盖 request.scope["client"] 元组
            # client 元组格式：(host: str, port: int)
            # 保留原始端口号（对限流无影响，但保持数据一致性）
            request.scope["client"] = (
                client_ip,
                request.scope.get("client", ("", 0))[1],
            )
        elif x_real_ip:
            # X-Real-IP 是 Nginx 直接设置的，不需要解析逗号分隔链
            request.scope["client"] = (
                x_real_ip,
                request.scope.get("client", ("", 0))[1],
            )

        # 继续执行后续中间件和路由处理函数
        return await call_next(request)


# 注册代理头还原中间件（必须在 SlowAPI 限流器之前注册，确保限流器能获取真实 IP）
app.add_middleware(ProxyHeadersMiddleware)

# 项目根目录，用于定位模板等静态资源
# Path(__file__) 拿到的是当前这个 Python 文件自身的路径，.parent 取它的上一级目录，也就是这个文件所在的文件夹
BASE_DIR = Path(__file__).parent


# ==================== 请求模型定义 ====================
# 使用 Pydantic BaseModel 定义请求体的数据结构，FastAPI 会自动：
# 1. 解析 JSON 请求体并填充模型字段
# 2. 进行类型校验（如字段类型不匹配则返回 422 错误）
# 3. 生成 OpenAPI 文档中的请求体 Schema


class TestConfigRequest(BaseModel):
    """
    测试 AI 模型连接请求体。

    前端在用户点击「测试连接」按钮时发送此请求，
    后端尝试用提供的配置连接 AI API，验证是否可用。

    Attributes:
        base_url: OpenAI 兼容 API 的基础地址，如 https://api.deepseek.com/v1
        api_key: API 密钥，Premium 模式下可为空（由后端自动填充）
        model_name: 模型名称，如 deepseek-chat、gpt-4o 等
    """

    base_url: str
    api_key: Optional[str] = None
    model_name: str


class AnalyzeRequest(BaseModel):
    """
    启动分析任务请求体。

    前端在用户点击「开始分析」按钮时发送此请求，
    后端创建异步分析任务并立即返回 task_id。

    Attributes:
        base_url: OpenAI 兼容 API 的基础地址
        api_key: API 密钥，Premium 模式下可为空
        model_name: 模型名称（Premium 模型为 deepseek-v4-flash）
        query: 搜索关键词，格式为"公司+岗位"，如"字节跳动 Java后端"
        modules: 用户选择的分析模块列表，可选值: ["summary", "mock_interview", "resume_tips"]
        sources: 面经来源列表，默认 ["nowcoder"]，可选值通过 /api/sources 获取
        max_count: 每个来源爬取的最大面经条数，默认 10
        resume_text: 简历文本内容（由 /api/upload-resume 解析后传入，简历优化模块必填）
    """

    base_url: str
    api_key: Optional[str] = None
    model_name: str
    query: str
    modules: list[str]
    sources: list[str] = ["nowcoder"]
    max_count: int = 10
    resume_text: str = ""


class UploadResumeRequest(BaseModel):
    """
    上传简历请求体。

    前端将 PDF 文件读取为 base64 编码字符串后发送此请求，
    后端解码并解析 PDF 文本内容返回给前端，前端再将其填入 AnalyzeRequest.resume_text。

    为什么使用 base64 + JSON 而非 multipart/form-data：
        部分云服务商的 WAF（Web 应用防火墙）会拦截 multipart 文件上传请求，
        改用 base64 编码放入 JSON body 可绕过此限制。

    Attributes:
        filename: 原始文件名，用于校验文件扩展名（仅接受 .pdf）
        file_base64: PDF 文件的 base64 编码字符串
    """

    filename: str
    file_base64: str


# ==================== Premium 供应商支持 ====================

# Premium 模型的标识名称
# 当用户选择 Premium 供应商时，前端将 model_name 设为此值
# 后端检测到此值后，自动从环境变量 DEEPSEEK_API_KEY 获取 API Key，
# 用户无需手动填写，降低使用门槛
PREMIUM_MODEL = "deepseek-v4-flash"


def resolve_api_key(api_key: Optional[str], model_name: str) -> str:
    """
    解析并验证 API Key。

    逻辑：
        1. 如果用户提供了 api_key → 直接使用
        2. 如果未提供 api_key 且为 Premium 模型 → 从环境变量 DEEPSEEK_API_KEY 获取
        3. 如果未提供 api_key 且非 Premium 模型 → 报错提示用户填写

    Args:
        api_key: 用户在前端输入的 API Key，可为 None
        model_name: 模型名称，用于判断是否为 Premium 模型

    Returns:
        解析后的有效 API Key 字符串

    Raises:
        HTTPException 400: Premium 模型但环境变量未配置，或非 Premium 但未填写 Key
    """
    if not api_key:
        if model_name == PREMIUM_MODEL:
            key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not key:
                raise HTTPException(
                    status_code=400, detail="Premium 模型暂不可用，请选择其他供应商"
                )
            return key
        raise HTTPException(status_code=400, detail="请填写 API Key")
    return api_key


# ==================== API 路由 ====================


@app.post("/api/test-config")
@limiter.limit("30/minute")
async def test_config(request: Request, req: TestConfigRequest):
    """
    测试 AI 模型连接是否可用。

    流程：
        1. 解析 API Key（支持 Premium 模式自动填充）
        2. 创建 AIClient 实例
        3. 调用 ai_client.test() 发送一个简单请求验证连接
        4. 成功返回 {"status": "ok"}，失败返回 400 错误

    限流：30 次/分钟/IP（轻量操作，适度限流即可）
    """
    client = None
    try:
        api_key = resolve_api_key(req.api_key, req.model_name)
        client = AIClient(req.base_url, api_key, req.model_name)
        await client.test()
        return {"status": "ok", "message": "连接成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        # 确保关闭 AI 客户端的 HTTP 连接，释放资源
        if client:
            try:
                await client.close()
            except Exception:
                pass


@app.get("/api/health")
async def health():
    """
    健康检查接口。

    用于监控系统和负载均衡器检测服务是否存活。
    如果此接口返回 200，说明 FastAPI 进程正常运行。
    不检查 AI 连接、数据库等外部依赖（那是 /api/test-config 的职责）。
    """
    return {"status": "ok"}


@app.get("/api/sources")
async def list_sources():
    """
    返回所有可用的面经来源列表。

    前端在页面加载时调用此接口，动态渲染来源多选组件。
    来源列表由 scraper/registry.py 中的 CRAWLERS 字典统一管理，
    新增来源只需在 registry 中注册，前端会自动获取。

    返回格式示例：
        [
            {"key": "nowcoder", "name": "牛客网"},
            {"key": "zhihu",    "name": "知乎"},
            ...
        ]
    """
    return get_sources()


@app.post("/api/analyze")
@limiter.limit("10/minute")
async def start_analyze(request: Request, req: AnalyzeRequest):
    """
    启动异步分析任务。

    流程：
        1. 预验证 API Key 是否有效（避免无效任务占用后台资源）
        2. 生成唯一的 12 位 task_id
        3. 在 tasks 字典中创建初始任务状态
        4. 将分析任务提交到事件循环中异步执行（asyncio.create_task）
        5. 立即返回 task_id，前端开始轮询 /api/status/{task_id}

    设计说明：
        分析流程可能耗时数分钟（爬虫 + AI 调用），使用异步任务模型
        避免请求超时，同时前端可以通过轮询展示实时进度。

    限流：10 次/分钟/IP（分析接口消耗 AI 调用额度和爬虫资源，严格限流）
    """
    resolve_api_key(req.api_key, req.model_name)

    # 生成唯一的任务 ID（取 UUID 的 hex 形式前 12 位，如 "a3f1b2c4d5e6"）
    task_id = uuid.uuid4().hex[:12]
    tasks[task_id] = {
        "status": "pending",  # 初始状态为等待中，run_analysis 开始后变为 running
        "progress": 0,  # 进度从 0 开始
        "result": None,  # 结果为空，分析完成后填充
        "error": None,  # 错误为空，失败时填充
        "finished_at": 0,  # 完成时间戳为 0，完成/失败时更新
    }

    # 将分析任务提交到事件循环中异步执行，不阻塞当前请求
    # asyncio.create_task 返回 Task 对象，但此处不需要追踪它
    # （任务状态通过 tasks 字典管理，不需要 await）
    asyncio.create_task(run_analysis(task_id, req))
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
@limiter.limit("60/minute")
async def get_status(request: Request, task_id: str):
    """
    查询指定任务的当前状态和进度。

    前端每隔约 1 秒调用此接口轮询任务进度，直到任务完成或失败。

    返回字段说明：
        status:   "pending"（等待中）→ "running"（执行中）→ "completed"（已完成）/ "failed"（失败）
        progress: 0-100 的进度百分比，前端据此渲染进度条
        result:   分析完成后的结构化数据，包含 modules（各模块分析结果）和 experiences（原始面经）
        error:    失败时的错误信息字符串

    限流：60 次/分钟/IP（轮询接口，前端每秒调用，宽松限流）
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "status": task["status"],
        "progress": task["progress"],
        "result": task["result"],
        "error": task["error"],
    }


# ==================== 核心分析流程 ====================

# 分析任务超时时间：10 分钟
# 如果爬虫或 AI 调用卡住，超时后任务状态设为 failed
# 此值需大于 Nginx 的 proxy_read_timeout（300s），否则 Nginx 会先断开连接
ANALYSIS_TIMEOUT_SECONDS = 600


async def run_analysis(task_id: str, req: AnalyzeRequest):
    """
    分析任务入口函数，包装超时控制。

    使用 asyncio.wait_for 为整个分析流程设置超时上限，
    超时后任务状态标记为 failed，错误信息提示用户减少数据量。

    Args:
        task_id: 任务 ID，用于更新 tasks 字典中的状态
        req: 分析请求参数
    """
    task = tasks[task_id]
    try:
        await asyncio.wait_for(
            _run_analysis_inner(task_id, req), timeout=ANALYSIS_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        task["status"] = "failed"
        task["error"] = "分析任务超时（超过10分钟），请减少数据量或来源后重试"
        task["finished_at"] = time.time()
        logger.error(f"[{task_id}] 分析任务超时")


async def _run_analysis_inner(task_id: str, req: AnalyzeRequest):
    """
    异步执行完整的分析流程。

    完整流程：
        Step 1: 初始化 AI 客户端并验证连接（progress 5% → 10%）
        Step 2: 根据用户选择的来源，逐个爬取数据（progress 10% → 50%）
        Step 3: 按用户选择的分析模块逐个执行 AI 分析（progress 55% → 90%）
        Step 4: 汇总结果，标记任务完成（progress 90% → 100%）

    进度分配策略：
        5%   → 启动任务
        10%  → AI 连接测试完成
        10-50% → 爬取数据（按来源数量平均分配 40% 的进度）
        55%  → 爬取完成，开始分析
        55-90% → 执行分析模块（按模块数量平均分配 35% 的进度）
        100% → 全部完成

    错误处理：
        - 爬取阶段：单个来源失败不影响其他来源，静默跳过
        - 单条数据详情获取失败：标记 content 为空，不中断整体流程
        - AI 分析阶段：任何异常都会导致整个任务失败

    Args:
        task_id: 任务 ID
        req: 分析请求参数
    """
    task = tasks[task_id]
    ai_client = None
    try:
        task["status"] = "running"
        task["progress"] = 5

        # Step 1: 初始化 AI 客户端并验证连接
        ai_client = AIClient(
            req.base_url, resolve_api_key(req.api_key, req.model_name), req.model_name
        )
        await ai_client.test()
        task["progress"] = 10

        # Step 2: 从多个来源爬取数据
        sources = req.sources or ["nowcoder"]
        crawl_start = time.time()
        logger.info(f"[{task_id}] 开始爬取数据，来源: {sources}")
        all_experiences = []
        total_sources = len(sources)
        # 将 10% → 50% 的进度（共 40%）按来源数量平均分配
        progress_per_source = 40 // max(total_sources, 1)

        # 招聘网站爬虫关键字，用于区分数据类型
        JOB_DESCRIPTION_SOURCES = {"job51", "liepin", "zhaopin"}

        for idx, source_key in enumerate(sources):
            crawler = None
            try:
                # 通过注册表获取对应来源的爬虫实例
                crawler = get_crawler(source_key)
                is_job_site = source_key in JOB_DESCRIPTION_SOURCES
                data_type_label = "岗位描述" if is_job_site else "面经"
                task["message"] = f"正在从{crawler.name}爬取{data_type_label}..."

                # 搜索列表（返回标题、URL 等摘要信息）
                exps = await crawler.search(req.query, req.max_count)
                # 为每条数据标记来源名称和数据类型
                for exp in exps:
                    exp["source"] = crawler.name
                    exp["type"] = "job_description" if is_job_site else "interview"

                # 逐条获取详情内容
                # 失败的数据保留摘要信息，content 设为空字符串
                for exp in exps:
                    if exp.get("content"):
                        continue
                    try:
                        detail = await crawler.fetch_content(exp["url"])
                        exp.update(detail)
                    except Exception:
                        exp["content"] = ""

                all_experiences.extend(exps)
                logger.info(
                    f"[{task_id}] {crawler.name} 爬取完成，获取 {len(exps)} 条{data_type_label}"
                )
            except Exception:
                logger.warning(f"[{task_id}] {source_key} 爬取失败", exc_info=True)
            finally:
                # 确保关闭爬虫的 HTTP 客户端，释放连接池资源
                if crawler:
                    try:
                        await crawler.close()
                    except Exception:
                        pass

            task["progress"] = 10 + (idx + 1) * progress_per_source

        crawl_elapsed = time.time() - crawl_start
        logger.info(
            f"[{task_id}] 数据爬取全部完成，共获取 {len(all_experiences)} 条，耗时 {crawl_elapsed:.1f}s"
        )

        if not all_experiences:
            logger.warning(f"[{task_id}] 所有来源均未爬取到数据")
            task["status"] = "completed"
            task["progress"] = 100
            task["result"] = {
                "error": "未找到相关面经或岗位信息，请尝试其他搜索词或来源"
            }
            task["finished_at"] = time.time()
            return

        task["message"] = f"共获取 {len(all_experiences)} 条数据，正在分析..."
        task["progress"] = 55

        # Step 3: 执行用户选择的分析模块
        # result 结构：{ "modules": {模块key: 分析结果}, "experiences": [原始面经列表] }
        result = {"modules": {}, "experiences": all_experiences}

        # 初始化所有可用的分析器
        # 每个分析器接收同一个 AI 客户端实例，内部调用不同的 Prompt 模板
        analyzers = {
            "summary": SummaryAnalyzer(ai_client),  # 面经总结与考点分析
            "mock_interview": MockInterviewAnalyzer(ai_client),  # 模拟面试题目预测
            "resume_tips": ResumeTipsAnalyzer(ai_client),  # 简历优化建议
        }

        # 只执行用户选择的分析模块，过滤掉无效的模块名
        selected = [m for m in req.modules if m in analyzers]
        analysis_start = time.time()
        logger.info(f"[{task_id}] 开始执行分析模块: {selected}")
        # 将 55% → 90% 的进度（共 35%）按模块数量平均分配
        progress_per_module = 35 // max(len(selected), 1)
        step_progress = 0

        for module_key in selected:
            analyzer = analyzers[module_key]
            task["message"] = f"正在执行: {analyzer.name}"
            result["modules"][module_key] = await analyzer.analyze(
                all_experiences, req.resume_text
            )
            logger.info(f"[{task_id}] {analyzer.name} 分析完成")
            step_progress += progress_per_module
            task["progress"] = 55 + step_progress

        analysis_elapsed = time.time() - analysis_start
        logger.info(f"[{task_id}] 分析模块全部完成，耗时 {analysis_elapsed:.1f}s")

        task["progress"] = 90
        task["message"] = "正在整理报告..."

        # Step 4: 汇总结果，标记任务完成
        task["result"] = result
        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "分析完成"
        task["finished_at"] = time.time()

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["finished_at"] = time.time()
        logger.error(f"[{task_id}] 分析任务异常: {e}", exc_info=True)
    finally:
        # 确保关闭 AI 客户端的 HTTP 连接，无论成功或失败
        if ai_client:
            try:
                await ai_client.close()
            except Exception:
                pass


# ==================== 简历上传 ====================

# 上传文件大小上限：5MB
# base64 编码会使数据膨胀约 33%，因此原始 PDF 需小于约 3.75MB 才能确保编码后不超过此限制
# 实际校验的是解码后的原始文件大小
MAX_FILE_SIZE = 5 * 1024 * 1024


@app.post("/api/upload-resume")
@limiter.limit("10/minute")
async def upload_resume(request: Request, req: UploadResumeRequest):
    """
    上传并解析 PDF 简历。

    流程：
        1. 校验文件扩展名（仅接受 .pdf）
        2. 解码 base64 字符串为原始 PDF 字节
        3. 校验文件大小（不超过 5MB）
        4. 调用 PyMuPDF 解析 PDF 文本内容
        5. 返回提取的文本内容

    前端使用方式：
        1. 用户选择 PDF 文件
        2. 前端使用 FileReader.readAsDataURL() 读取为 base64
        3. 发送此接口解析
        4. 将返回的 text 存入 AnalyzeRequest.resume_text 字段
        5. 提交分析时一并传给后端

    限流：10 次/分钟/IP（PDF 解析消耗 CPU 和内存资源，严格限流）
    """
    # 校验文件扩展名
    if not req.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件")

    # 将 base64 编码的文件内容解码为原始字节
    content = base64.b64decode(req.file_base64)

    # 校验文件大小
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 5MB")

    # 使用 PyMuPDF 解析 PDF 文本
    text = parse_resume(content)

    # 检查是否成功提取到文本（扫描件 PDF 无法提取文本）
    if not text.strip():
        raise HTTPException(
            status_code=400, detail="无法从 PDF 中提取文本，请确认文件内容为可识别文本"
        )
    return {"text": text}


# ==================== 前端页面路由 ====================


@app.get("/", response_class=HTMLResponse)
async def index():
    """
    返回前端单页面应用的 HTML。

    前端代码位于 templates/index.html，是一个自包含的单文件 SPA，
    包含 HTML 结构、CSS 样式和 JavaScript 逻辑。
    不使用前端构建工具（如 Vite/Webpack），直接返回原始 HTML 文件。

    注意：生产环境中，Nginx 会拦截 / 请求直接返回静态文件，
    不会走到此路由（Nginx 的 try_files 优先级更高）。
    此路由主要用于本地开发（uvicorn 直接启动）时的页面访问。
    """
    html_path = BASE_DIR / "templates" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/favicon.ico")
async def favicon():
    """
    返回 SVG 格式的 favicon。

    浏览器会自动请求 /favicon.ico，此处返回 SVG 内容并设置正确的 Content-Type，
    确保本地开发模式下标签页图标正常显示。
    生产环境中，Nginx 直接服务 /favicon.svg，此路由作为兜底。
    """
    svg_path = BASE_DIR / "static" / "favicon.svg"
    if svg_path.exists():
        return Response(
            content=svg_path.read_bytes(),
            media_type="image/svg+xml",
        )
    return Response(status_code=204)


# ==================== 开发模式启动入口 ====================

if __name__ == "__main__":
    import uvicorn

    # 开发模式启动，启用热重载
    # --reload: 监听文件变更，自动重启服务
    # 生产环境使用 Docker 容器中的 CMD 指令启动，不走此处
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
