# resume-gpt

AI 驱动的面试辅助分析工具。收到面试邀请后，通过爬取牛客网面经并结合 AI 分析，生成个性化的面试分析报告。

---

## 功能

- **模型无关**：支持任意 OpenAI 兼容 API（用户自行指定 base_url / api_key / model_name）
- **面经爬取**：根据公司+岗位搜索词爬取牛客网面经
- **三个分析模块**：
  - **面经总结与考点分析** — 提取高频考点，按知识点分类汇总
  - **模拟面试题目预测** — 基于面经和简历生成预测面试题
  - **简历优化建议** — 对比面经考点，给出简历修改建议
- **原始题库侧边栏**：右侧展示爬取到的原始面经，点击可展开查看详情
- **进度可视化**：异步分析流程，前端实时轮询展示进度

---

## 技术架构

### 整体架构

```
┌──────────────────────────────────────────────────┐
│                  用户浏览器                         │
│         (单页 HTML + CSS + JavaScript)              │
└──────────────┬──────────────────────────────┬─────┘
               │ HTTP (REST API)              │
               ▼                              ▼
┌──────────────────────────────┐  ┌──────────────────┐
│      FastAPI 后端服务          │  │  WebSocket/轮询   │
│                              │  │  (任务进度查询)    │
│  POST /api/analyze           │  │                  │
│  POST /api/test-config       │  │  GET /api/status  │
│  POST /api/upload-resume     │  │                  │
└──────┬───────────────┬───────┘  └──────────────────┘
       │               │
       ▼               ▼
┌──────────┐  ┌────────────────┐
│ 牛客网爬虫│  │  AI 模型客户端   │
│ (httpx +  │  │  (OpenAI 兼容)  │
│  BS4)    │  │                │
└──────────┘  └────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │ 分析器模块      │
            │ · 面经总结      │
            │ · 模拟面试      │
            │ · 简历优化      │
            └────────────────┘
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
| 文件上传 | python-multipart | PDF 文件上传支持 |

### 模块说明

```
my-project/
├── main.py                 # FastAPI 应用入口
│                           # - 路由定义 (4个 API + 前端路由)
│                           # - 分析流程编排 (run_analysis)
│                           # - CORS 中间件配置
│                           # - 异步任务管理 (内存存储)
│
├── templates/
│   └── index.html          # 前端单页应用
│                           # - 左右分栏布局
│                           # - 配置面板 (模型/搜索/简历/模块选择)
│                           # - 报告展示区 (卡片式渲染)
│                           # - 原始面经题库侧边栏
│                           # - 进度轮询与 Toast 提示
│
├── scraper/
│   └── nowcoder.py         # 牛客网面经爬虫
│                           # - NowCrawler 类
│                           # - search(): 搜索面经列表
│                           # - fetch_content(): 获取单篇面经详情
│                           # - 反爬防护 (UA、延迟)
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
├── prd.md                  # 产品需求文档
└── requirements.txt        # Python 依赖清单
```

### 数据流

```
1. 用户填写配置 → POST /api/analyze
2. 后端创建异步任务，返回 task_id
3. 前端轮询 GET /api/status/{task_id}
4. 后台任务依次执行：
   a. 测试模型连接
   b. 爬取牛客网面经列表
   c. 遍历获取每篇面经详情
   d. 解析简历 PDF
   e. 根据所选模块调用 AI 分析器
   f. 每个模块调用 chat_json() 获取结构化 JSON
5. 任务完成，前端拉取结果渲染报告
6. 原始面经展示在右侧题库侧边栏
```

### 关键设计

- **异步任务 + 轮询**：分析流程可能耗时较长（爬虫 + AI 调用），后端提交任务后返回 `task_id`，前端每秒轮询进度
- **结构化 Prompt**：每个分析模块的 AI Prompt 要求模型返回 JSON，前端直接渲染结构化数据，无需在后端处理文本
- **内存任务存储**：当前使用字典存储任务状态，服务重启后任务丢失（适用于 MVP）
- **模型无关性**：用户自行指定 API 地址和密钥，后端仅做透传，不存储任何凭据

---

## 部署方式

### 前置要求

- Python 3.10+
- pip

### 本地部署

```bash
# 1. 克隆或进入项目目录
cd my-project

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
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 > app.log 2>&1 &

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
WorkingDirectory=/path/to/my-project
ExecStart=/path/to/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
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

# 或用 docker-compose
docker compose up -d
```

### GitHub Actions CI/CD

项目包含 `.github/workflows/deploy.yml`，实现 main 分支推送时的自动构建和部署。

**工作流程：**

1. 推送代码到 `main` 分支，触发 Action
2. 自动构建 Docker 镜像
3. 推送到 GitHub Container Registry (GHCR)
4. SSH 登录服务器，拉取新镜像并重启容器

**前置配置（仅在首次使用时需要）：**

在 GitHub 仓库 Settings → Secrets and variables → Actions 中添加：

| Secret | 说明 |
|--------|------|
| `DEPLOY_HOST` | 服务器 IP 或域名 |
| `DEPLOY_PORT` | SSH 端口（默认 22，可省略） |
| `DEPLOY_USER` | SSH 登录用户名 |
| `DEPLOY_SSH_KEY` | SSH 私钥（对应服务器的公钥） |
| `DEPLOY_PATH` | 服务器上项目路径（需包含 `docker-compose.yml`） |

然后在服务器上准备好：

```bash
mkdir -p /app/ai-interview-coach
# 将 docker-compose.yml 放到该目录
# 确保 Docker 和 docker-compose 已安装
```

之后每次推送 main 分支，服务器会自动更新。

### 使用方式

1. 打开浏览器访问部署地址
2. 填写模型供应商配置（base_url / api_key / model_name）
3. 点击「测试连接」确认配置有效
4. 输入公司+岗位搜索词
5. 上传 PDF 简历（可选，简历优化模块必填）
6. 选择分析模块（至少一个）
7. 点击「开始分析」，等待结果
8. 查看分析报告，可点击右侧原始面经展开详情

---

## 环境变量（可选）

可通过环境变量覆盖默认开发配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8000` | 监听端口 |

---

## 开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 启动（热重载）
uvicorn main:app --reload --port 8000

# 验证 API
curl http://localhost:8000/
curl http://localhost:8000/favicon.ico  # 应返回 204
```

### 添加新的分析模块

1. 在 `analyzers/` 下创建新的模块文件，继承 `BaseAnalyzer`
2. 实现 `name` 属性和 `analyze()` 方法
3. 在 `main.py` 的 `run_analysis()` 中注册到 `analyzers` 字典
4. 在 `templates/index.html` 中添加对应的 checkbox 和渲染函数
