# 构建文件说明

## Dockerfile文件命令说明

```bash
# 基础镜像：Python 3.11 精简版（基于 Debian slim）
# 相比完整版 python:3.11 约 900MB，slim 版仅约 150MB，去除不必要的系统包
# 3.11 版本性能比 3.10 提升约 10-25%，且兼容本项目所有依赖
FROM python:3.11-slim

# 设置容器内的工作目录为 /app
# 后续的 COPY、RUN、CMD 等指令都基于此目录执行
# 如果 /app 不存在会自动创建
WORKDIR /app

# 仅复制依赖清单文件到容器中
# 关键优化：先单独复制 requirements.txt 并安装依赖，再复制源代码
# 这样当源代码变更但依赖不变时，Docker 可复用缓存的依赖安装层
# 如果直接 COPY . . 再 pip install，每次代码变更都会重新安装所有依赖
COPY requirements.txt .

# 安装 Python 依赖
# --no-cache-dir：不保留 pip 下载缓存（默认缓存在 ~/.cache/pip）
# 容器构建是一次性的，缓存留在镜像中只会增大体积（约可节省数十MB）
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目所有源代码到容器的 /app 目录
# 受 .dockerignore 控制，.git、__pycache__、.env、guide/ 等文件不会被复制
# 放在 pip install 之后，确保代码变更不会触发依赖重新安装
COPY . .

# 声明容器运行时监听的端口
# 注意：EXPOSE 仅是文档声明，不会实际发布端口
# 端口映射需要在 docker run -p 或 docker-compose.yml 中配置
EXPOSE 8000

# 容器启动命令：使用 uvicorn 启动 FastAPI 应用
# uvicorn：ASGI 服务器，负责接收 HTTP 请求并转发给 FastAPI 应用
# main:app：表示 main.py 文件中的 app 变量（FastAPI 实例）
# --host 0.0.0.0：监听所有网络接口（默认仅监听 127.0.0.1，容器内需监听所有接口才能被外部访问）
# --port 8000：监听端口号，与 EXPOSE 声明一致
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


```

---

## docker-compose.yml说明
```bash
# Docker Compose 编排配置文件
# 定义了两个服务：app（FastAPI 后端）和 nginx（反向代理）
# 部署架构：用户 → Nginx(:80) → App(:8000)

services:
  # FastAPI 后端应用服务
  app:
    # 镜像地址：阿里云 ACR 个人版（上海区域）中的最新镜像
    # CI/CD 构建后会推送 latest 和 commit SHA 两个标签到此地址
    image: crpi-fmn9v2rn38d84ou1.cn-shanghai.personal.cr.aliyuncs.com/axelwt/resume-gpt:latest
    # 仅向同一 Docker 网络内的其他容器暴露端口，不对宿主机映射
    # 与 ports 不同，expose 不会在宿主机上发布端口，外部无法直接访问
    # 只有同在 backend 网络的 nginx 容器可以通过 app:8000 访问
    expose:
      - "8000"
    # 重启策略：除非手动停止（docker stop），否则总是重启
    # 包括容器崩溃、Docker 守护进程重启、服务器重启等情况
    restart: unless-stopped
    # 从 .env 文件加载环境变量到容器中
    # CI/CD 部署时会自动写入 DEEPSEEK_API_KEY 和 OPENAI_API_KEY 到此文件
    env_file:
      - .env
    # 额外的环境变量（直接在配置中指定，不通过 .env 文件）
    environment:
      # 设置容器时区为中国上海（UTC+8），确保日志时间戳正确
      - TZ=Asia/Shanghai
    # 连接到 backend 自定义网络
    networks:
      - backend

  # Nginx 反向代理服务
  # 作为唯一的对外入口，将请求转发给后端 app 服务
  nginx:
    # Nginx 镜像地址：同样托管在阿里云 ACR
    # 镜像基于 nginx:alpine，包含自定义的 nginx.conf 配置
    image: crpi-fmn9v2rn38d84ou1.cn-shanghai.personal.cr.aliyuncs.com/axelwt/resume-gpt-nginx:latest
    # 端口映射：将宿主机的 80 端口映射到容器的 80 端口
    # 格式为 "宿主机端口:容器端口"，用户通过访问服务器 80 端口即可使用应用
    ports:
      - "80:80"
    # 服务依赖：nginx 必须等 app 服务启动后才启动
    # 确保 Nginx 启动时后端已经就绪，避免反向代理到未启动的服务
    depends_on:
      - app
    # 重启策略：同 app 服务，除非手动停止否则总是重启
    restart: unless-stopped
    # 连接到同一个 backend 网络，这样才能通过服务名 "app" 访问后端
    networks:
      - backend

# 自定义网络定义
networks:
  # 创建名为 backend 的桥接网络（默认驱动为 bridge）
  # 同一网络内的容器可以通过服务名互相访问（如 nginx 中 proxy_pass http://app:8000）
  # 不同网络内的容器相互隔离，提高安全性
  backend:

```

---

## nginx 配置文件说明
```bash
# ============================================================
# Nginx 反向代理配置 — resume-gpt
# 部署架构：用户 → Nginx(:80) → FastAPI App(:8000)
# Nginx 职责：静态文件服务 + 反向代理 + 限流 + gzip 压缩
# ============================================================

# -----------------------------------------------------------
# 限流区域定义（在 http 块级别声明，供 server 块中的 location 引用）
# 语法：limit_req_zone key zone=名称:内存大小 rate=速率
# -----------------------------------------------------------

# 分析接口限流区域：每个 IP 每分钟最多 10 次请求
# $binary_remote_addr：以二进制格式存储客户端 IP（比字符串格式节省内存，每个 IP 占 4/16 字节）
# zone=analyze:10m：分配 10MB 内存存储该限流区域的会话状态（约可记录 16 万个 IP）
# rate=10r/m：每分钟 10 次请求（平均每 6 秒允许 1 次）
limit_req_zone $binary_remote_addr zone=analyze:10m rate=10r/m;

# 简历上传接口限流区域：每个 IP 每分钟最多 10 次请求
# 上传接口消耗服务器资源较多（PDF 解析 + base64 编解码），需要严格限流
limit_req_zone $binary_remote_addr zone=upload:10m rate=10r/m;

# 通用 API 接口限流区域：每个 IP 每分钟最多 30 次请求
# 适用于健康检查、来源列表等轻量级接口
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;

# 1. 上方 limit_req_zone：定义证的名字（zone=analyze）和规则（rate=10r/m）
# 2. 下方 limit_req zone=analyze：哪个接口领哪张证
# 名字对名字，zone=analyze 定义的证，zone=analyze 领走。就像办证处窗口写着"过山车通行证"，下面过山车检票口写着"需出示过山车通行证"。

# -----------------------------------------------------------
# 服务器配置块
# -----------------------------------------------------------
server {
    # 监听 80 端口（HTTP），对外提供服务的唯一入口
    listen 80;

    # server_name：匹配请求的 Host 头
    # 下划线 _ 是通配写法，表示匹配任何域名/IP 访问（即不限制域名）
    server_name _;

    # -------------------------------------------------------
    # Gzip 压缩配置
    # 开启后可显著减小传输体积，加快前端加载速度
    # -------------------------------------------------------

    # 启用 gzip 压缩
    gzip on;

    # 需要压缩的 MIME 类型列表：
    # text/plain        — 纯文本（如 API 返回的文本）
    # text/css          — CSS 样式表
    # application/json  — JSON API 响应（本项目主要数据格式）
    # application/javascript — JavaScript 文件
    # text/xml          — XML 数据
    gzip_types text/plain text/css application/json application/javascript text/xml;

    # 最小压缩阈值：仅当响应体 >= 1024 字节时才压缩
    # 小于阈值的响应压缩收益不大，反而增加 CPU 开销
    gzip_min_length 1024;

    # 客户端请求体最大大小：10MB
    # 限制上传文件大小，防止恶意上传大文件耗尽服务器资源
    # 本项目简历上传采用 base64 JSON 传输，需确保此值大于 base64 编码后的简历大小
    client_max_body_size 10m;

    # -------------------------------------------------------
    # 路由规则（location 块）
    # Nginx 按照特定优先级匹配 location：
    #   精确匹配 (=) > 前缀匹配 (^~) > 正则匹配 (~) > 普通前缀匹配
    # -------------------------------------------------------

    # 首页：精确匹配根路径 "/"
    location = / {
        # 静态文件根目录：Nginx 容器内的 HTML 文件路径
        # nginx/Dockerfile 中将 templates/index.html 复制到此目录
        root /usr/share/nginx/html;
        # 尝试读取 /usr/share/nginx/html/index.html，不存在则返回 404
        try_files /index.html =404;
        # 浏览器缓存时间：1 小时
        # 前端单页应用不频繁变更，缓存可减少重复请求
        expires 1h;
    }

    # Favicon：精确匹配 /favicon.ico
    location = /favicon.ico {
        # 静态文件根目录
        root /usr/share/nginx/html;
        # 尝试读取请求的文件，不存在则返回 204 No Content（而非 404）
        # 204 表示"成功但无内容"，浏览器不会报错，也不会重复请求
        try_files $uri =204;
        # 浏览器缓存时间：7 天（favicon 很少变化，可长期缓存）
        expires 7d;
    }

    # 分析接口：精确匹配 /api/analyze
    location = /api/analyze {
        # 应用限流规则：
        # zone=analyze：引用上方定义的 analyze 限流区域（10r/m）
        # burst=5：允许突发 5 个额外请求（超出速率的请求排队等待，而非立即拒绝）
        # nodelay：突发请求不延迟处理，而是立即处理 burst 数量内的请求
        # 超出 burst+rate 的请求直接返回 503 Service Unavailable
        limit_req zone=analyze burst=5 nodelay;

        # 反向代理目标：将请求转发到 app 服务的 8000 端口
        # "app" 是 docker-compose.yml 中定义的服务名，Docker 内部 DNS 自动解析
        proxy_pass http://app:8000;

        # 以下四行为标准的反向代理头设置，确保后端能获取真实的客户端信息
        
        # 用户通过 Nginx 访问后端，后端拿到的请求信息全是 Nginx 的，不是用户的。这四行就是把用户的真实信息补回去：                                                                     █  
                                                                                                                                             ▼ Modified Files                     █  
        # Host $host：告诉后端，用户原来访问的是哪个域名                                                                                        .dockerignore                  +1 -1 █  
        # X-Real-IP $remote_addr：告诉后端，用户的真实 IP 是什么（不然后端看到的 IP 全是 Nginx 的内网 IP）                                      README.md                   +132 -59 █  
        # X-Forwarded-For：IP 传递链，记录请求经过了哪些代理（比如：用户IP → CDN → Nginx）                                                      guide-docs/deploy.md            +179 █  
        # X-Forwarded-Proto：告诉后端，用户原来用的是 HTTP 还是 HTTPS

        # 传递原始请求的 Host 头（域名/端口），后端可能用于生成回调 URL 等
        proxy_set_header Host $host;

        # 传递客户端真实 IP（取自 TCP 连接的远端地址）
        # 后端 SlowAPI 限流器依赖此头识别客户端（配合 ProxyHeadersMiddleware）
        proxy_set_header X-Real-IP $remote_addr;

        # 追加客户端 IP 到 X-Forwarded-For 链（支持多层代理场景）
        # 如果请求已存在 X-Forwarded-For，则追加；否则等于 $remote_addr
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # 传递原始请求的协议（http 或 https）
        # 后端可根据此头判断客户端是否使用 HTTPS
        proxy_set_header X-Forwarded-Proto $scheme;

        # 代理读取超时：300 秒（5 分钟）
        # 分析流程涉及爬虫 + AI 调用，可能耗时较长，默认 60s 不够用
        # 此值需小于后端 uvicorn 的超时和 main.py 的 ANALYSIS_TIMEOUT_SECONDS(600s)
        proxy_read_timeout 300s;
    }

    # 简历上传接口：精确匹配 /api/upload-resume
    location = /api/upload-resume {
        # 应用限流规则：upload 区域（10r/m），允许突发 5 个请求
        limit_req zone=upload burst=5 nodelay;

        # 反向代理到后端
        proxy_pass http://app:8000;

        # 标准反向代理头（同上）
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 任务状态查询接口：前缀匹配 /api/status/
    location /api/status/ {
        # 注意：此接口不限流
        # 前端每秒轮询此接口获取分析进度，限流会导致正常用户体验受损
        # 且 status 查询是轻量只读操作，服务器压力很小

        # 反向代理到后端
        proxy_pass http://app:8000;

        # 标准反向代理头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 其他 API 接口：前缀匹配 /api/
    # 匹配所有未被上方更具体 location 捕获的 /api/* 请求
    # 如 /api/health、/api/sources、/api/test-config 等
    location /api/ {
        # 应用限流规则：api 区域（30r/m），允许突发 10 个请求
        limit_req zone=api burst=10 nodelay;

        # 反向代理到后端
        proxy_pass http://app:8000;

        # 标准反向代理头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 兜底规则：匹配所有未被上方规则捕获的请求
    # 作为最后的 fallback，将剩余请求全部转发给后端处理
    location / {
        # 反向代理到后端
        proxy_pass http://app:8000;

        # 标准反向代理头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

```

---