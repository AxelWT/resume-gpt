# resume-gpt

AI 驱动的面试辅助分析工具。收到面试邀请后，通过爬取网上的面经并结合 AI 分析，生成个性化的面试分析报告。

---

## 功能

- **模型无关**：支持任意 OpenAI 兼容 API（用户自行指定 base_url / api_key / model_name）
- **Premium 供应商**：内置 DeepSeek Premium 支持，无需手动填写 API Key
- **8 大面经来源**：支持牛客网、知乎、BOSS 直聘、脉脉、应届生求职网、前程无忧、智联招聘、猎聘
- **多来源并发爬取**：可同时选择多个来源，通过爬虫注册表统一调度
- **三个分析模块**：
  - **面经总结与考点分析** — 提取高频考点，按知识点分类汇总
  - **模拟面试题目预测** — 基于面经和简历生成预测面试题
  - **简历优化建议** — 对比面经考点，给出简历修改建议
- **原始题库侧边栏**：右侧展示爬取到的原始面经，点击可展开查看详情
- **进度可视化**：异步分析流程，前端实时轮询展示进度
- **亮/暗色主题**：支持亮色与暗色主题切换，自动记忆用户偏好
- **双重限流防护**：应用层 SlowAPI + Nginx 层双重限流，保障服务稳定

---

## 技术架构

### 整体架构

```
┌──────────────────────────────────────────────────┐
│                  用户浏览器                        │
│         (单页 HTML + CSS + JavaScript)            │
└──────────────┬──────────────────────────────┬────┘
               │ HTTP (REST API)              │
               ▼                              ▼
┌──────────────────────────────────┐  ┌──────────────┐
│         FastAPI 后端服务           │  │ WebSocket/轮询│
│                                  │  │ (任务进度查询) │
│  POST /api/analyze               │  │              │
│  POST /api/test-config           │  │ GET /api/status│
│  POST /api/upload-resume         │  └──────────────┘
│  GET  /api/health                │
│  GET  /api/sources               │
└──────┬───────────────┬───────────┘
       │               │
       ▼               ▼
┌──────────────┐  ┌────────────────┐
│  爬虫注册表    │  │  AI 模型客户端   │
│  (registry)  │  │  (OpenAI 兼容)  │
│              │  │                │
│ · nowcoder   │  └────────────────┘
│ · zhihu      │         │
│ · boss       │         ▼
│ · maimai     │  ┌────────────────┐
│ · yjs        │  │ 分析器模块      │
│ · job51      │  │ · 面经总结      │
│ · zhaopin    │  │ · 模拟面试      │
│ · liepin     │  │ · 简历优化      │
└──────┬───────┘  └────────────────┘
       │
       ├─ NowCrawler: 直接爬取牛客搜索页
       │
       └─ 其他 7 个爬虫: 通过 Bing site: 间接搜索
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | Python FastAPI | 异步 Web 框架，支持 async/await |
| 后端服务器 | Uvicorn | ASGI 服务器 |
| 前端 | 纯 HTML + CSS + JavaScript | 单页应用，无构建工具依赖 |
| HTTP 客户端 | httpx | 异步 HTTP 请求，用于爬虫和 AI API 调用 |
| HTML 解析 | BeautifulSoup4 + lxml | 面经页面解析 |
| PDF 解析 | PyMuPDF (fitz) | 提取简历文本 |
| 数据验证 | Pydantic | 请求/响应模型校验 |
| 限流 | SlowAPI | 应用层 API 请求频率限制 |
| 反向代理 | Nginx | 独立容器，gzip 压缩 + 限流 + 反向代理 |

### 模块说明

```
resume-gpt/
├── main.py                 # FastAPI 应用入口
│                           # - 路由定义 (7 个 API + 2 个前端路由)
│                           # - 分析流程编排 (run_analysis)
│                           # - CORS / ProxyHeaders 中间件
│                           # - 异步任务管理 (内存存储 + 过期清理)
│                           # - SlowAPI 限流配置
│                           # - Premium 供应商支持 (环境变量解析)
│
├── templates/
│   └── index.html          # 前端单页应用
│                           # - 左右分栏布局
│                           # - 配置面板 (5 种预设供应商 + 自定义)
│                           # - 多来源勾选 + 抓取数量控制
│                           # - 报告展示区 (卡片式渲染)
│                           # - 原始面经题库侧边栏
│                           # - 亮/暗色主题切换
│                           # - 进度轮询与 Toast 提示
│                           # - Help Popover 引导气泡
│
├── scraper/
│   ├── base.py             # 爬虫基类 (BaseCrawler)
│   │                       # - _search_via_bing(): Bing site: 间接搜索
│   │                       # - _parse_bing_results(): 解析搜索结果
│   ├── registry.py         # 爬虫注册表 (CRAWLERS 字典)
│   │                       # - get_crawler() / get_sources()
│   ├── nowcoder.py         # 牛客网爬虫 (直接爬取搜索页)
│   ├── zhihu.py            # 知乎爬虫 (Bing 间接搜索)
│   ├── boss.py             # BOSS 直聘爬虫 (Bing 间接搜索)
│   ├── maimai.py           # 脉脉爬虫 (Bing 间接搜索)
│   ├── yjs.py              # 应届生求职网爬虫 (Bing 间接搜索)
│   ├── job51.py            # 前程无忧爬虫 (Bing 间接搜索)
│   ├── zhaopin.py          # 智联招聘爬虫 (Bing 间接搜索)
│   └── liepin.py           # 猎聘爬虫 (Bing 间接搜索)
│
├── ai/
│   └── client.py           # AI 模型客户端
│                           # - AIClient 类
│                           # - test(): 连接测试
│                           # - chat(): 通用对话接口
│                           # - chat_json(): 结构化 JSON 输出接口
│                           # - 错误处理 (401/404/429)
│
├── analyzers/
│   ├── base.py             # BaseAnalyzer 抽象基类
│   ├── summary.py          # 面经总结与考点分析
│   ├── mock_interview.py   # 模拟面试题目预测
│   └── resume_tips.py      # 简历优化建议
│                           # 每个分析器含专用 Prompt 模板
│                           # 调用 chat_json() 获取结构化结果
│
├── utils/
│   └── pdf_parser.py       # PDF 简历文本提取
│
├── nginx/
│   ├── Dockerfile          # Nginx 容器构建 (nginx:alpine)
│   └── nginx.conf          # Nginx 配置 (gzip + 限流 + 反向代理)
│
├── guide/
│   ├── prd.md              # 产品需求文档
│   ├── deploy.md           # 服务器部署指南
│   ├── mihomo-vpn-setup.md # Mihomo 代理部署指南
│   ├── secrets-management.md # 敏感配置管理方案
│   └── prompt.md           # 初始提示词
│
├── Dockerfile              # 应用容器构建 (python:3.11-slim)
├── docker-compose.yml      # Docker Compose 编排 (app + nginx)
├── requirements.txt        # Python 依赖清单
└── .github/
    └── workflows/
        └── deploy.yml      # CI/CD 自动部署 (ACR + SSH)
```

### 数据流

```
1. 用户填写配置 → POST /api/analyze
2. 后端创建异步任务，返回 task_id
3. 前端轮询 GET /api/status/{task_id}
4. 后台任务依次执行：
   a. 测试模型连接
   b. 根据用户选择的来源，从爬虫注册表创建对应爬虫
   c. 各来源并发爬取面经列表
      - 牛客网: 直接爬取搜索页
      - 其他来源: 通过 Bing site: 间接搜索
   d. 遍历获取每篇面经详情
   e. 解析简历 PDF (base64 JSON 上传)
   f. 根据所选模块调用 AI 分析器
   g. 每个模块调用 chat_json() 获取结构化 JSON
5. 任务完成，前端拉取结果渲染报告
6. 原始面经展示在右侧题库侧边栏
```

### 关键设计

- **异步任务 + 轮询**：分析流程可能耗时较长（爬虫 + AI 调用），后端提交任务后返回 `task_id`，前端每秒轮询进度
- **结构化 Prompt**：每个分析模块的 AI Prompt 要求模型返回 JSON，前端直接渲染结构化数据，无需在后端处理文本
- **内存任务存储 + 过期清理**：使用字典存储任务状态，后台协程每 5 分钟清理已完成/失败超过 1 小时的任务，防止内存泄漏
- **模型无关性**：用户自行指定 API 地址和密钥，后端仅做透传，不存储任何凭据
- **Premium 供应商**：选择 Premium 供应商时，后端自动从环境变量 `DEEPSEEK_API_KEY` 获取 API Key，用户无需手动填写
- **爬虫注册表**：通过 `CRAWLERS` 字典统一管理 8 个爬虫，前端动态获取可用来源列表 (`GET /api/sources`)
- **Bing 间接搜索**：除牛客网外的 7 个爬虫通过 `site:` 语法在 Bing 搜索目标站点面经链接，绕过 JS 渲染和认证限制
- **双重限流**：应用层 SlowAPI（按路由差异化限流）+ Nginx 层 `limit_req_zone`，防止滥用
- **代理 IP 修复**：`ProxyHeadersMiddleware` 解析 `X-Forwarded-For` / `X-Real-IP`，确保限流器正确识别客户端 IP
- **简历 base64 上传**：简历采用 base64 编码 + JSON body 传输，规避云服务商 WAF 对 multipart 上传的拦截

---

## 部署方式

### 前置要求

- Python 3.10+
- pip

### 本地部署

```bash
# 1. 克隆或进入项目目录
cd resume-gpt

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问 `http://localhost:8000` 即可使用。

### 生产部署

使用 `nohup` 或 systemd 保持后台运行：

```bash
# nohup 方式
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 > app.log 2>&1 &

# 查看日志
tail -f app.log
```

#### systemd 服务配置

```ini
[Unit]
Description=resume-gpt
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/resume-gpt
ExecStart=/path/to/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Docker 部署

```bash
# 构建镜像
docker build -t ai-interview-coach .

# 启动容器
docker run -d -p 8000:8000 ai-interview-coach

# 或用 docker-compose (推荐，包含 Nginx 反向代理)
docker compose up -d
```

Docker Compose 部署架构：

```
用户 → :80 (Nginx 容器, nginx:alpine)
         ↓ 反向代理
       :8000 (App 容器, python:3.11-slim)
```

### GitHub Actions CI/CD

项目包含 `.github/workflows/deploy.yml`，实现 main 分支推送时的自动构建和部署。

**工作流程：**

1. 推送代码到 `main` 分支（或手动触发），触发 Action
2. 自动构建 **两个** Docker 镜像（app + nginx）
3. 推送到阿里云容器镜像服务 (ACR)
4. 通过 SCP 复制 `docker-compose.yml` 到服务器
5. SSH 登录服务器，从环境变量写入 `.env` 文件，登录 ACR 拉取新镜像并重启容器

**前置配置（仅在首次使用时需要）：**

在 GitHub 仓库 Settings → Secrets and variables → Actions 中添加：

| Secret | 说明 |
|--------|------|
| `DEPLOY_HOST` | 服务器 IP 或域名 |
| `DEPLOY_PORT` | SSH 端口（默认 22，可省略） |
| `DEPLOY_USER` | SSH 登录用户名 |
| `DEPLOY_SSH_KEY` | SSH 私钥（对应服务器的公钥） |
| `DEPLOY_PATH` | 服务器上项目路径（需包含 `docker-compose.yml`） |
| `ACR_USERNAME` | 阿里云容器镜像服务用户名 |
| `ACR_PASSWORD` | 阿里云容器镜像服务密码 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（用于 Premium 供应商） |
| `OPENAI_API_KEY` | OpenAI API Key（可选，用于默认 AI 服务） |

然后在服务器上准备好：

```bash
mkdir -p /app/ai-interview-coach
# 将 docker-compose.yml 放到该目录
# 确保 Docker 和 docker-compose 已安装
```

之后每次推送 main 分支，服务器会自动更新。

### 使用方式

1. 打开浏览器访问部署地址
2. 选择模型供应商（Premium / DeepSeek / GLM / Qwen / 自定义），填写或确认 API 配置
3. 点击「测试连接」确认配置有效
4. 输入公司+岗位搜索词
5. 选择面经来源（牛客网、知乎等，支持多选）
6. 上传 PDF 简历（可选，简历优化模块必填）
7. 选择分析模块（至少一个）
8. 点击「开始分析」，等待结果
9. 查看分析报告，可点击右侧原始面经展开详情

---

## 环境变量

### 服务器环境变量（通过 CI/CD 自动注入）

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key，用于 Premium 供应商免输入 Key 模式 |
| `OPENAI_API_KEY` | OpenAI API Key（可选） |

这些变量由 GitHub Actions 在部署时从 Secrets 写入服务器 `.env` 文件，无需手动配置。

---

## 开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 启动（热重载）
uvicorn main:app --reload --port 8000

# 验证 API
curl http://localhost:8000/
curl http://localhost:8000/api/health  # 健康检查
curl http://localhost:8000/api/sources  # 获取面经来源列表
```

### 添加新的面经来源

1. 在 `scraper/` 下创建新的爬虫文件，继承 `BaseCrawler`
2. 实现 `name` 属性、`search()` 和 `fetch_content()` 方法
3. 若目标站点搜索页需 JS 渲染，可复用 `_search_via_bing()` 间接搜索
4. 在 `scraper/registry.py` 的 `CRAWLERS` 字典中注册
5. 前端会自动通过 `GET /api/sources` 获取新来源

### 添加新的分析模块

1. 在 `analyzers/` 下创建新的模块文件，继承 `BaseAnalyzer`
2. 实现 `name` 属性和 `analyze()` 方法
3. 在 `main.py` 的 `run_analysis()` 中注册到 `analyzers` 字典
4. 在 `templates/index.html` 中添加对应的 checkbox 和渲染函数
