# github actions工作流说明

```bash
# 工作流名称，显示在 GitHub Actions 页面上
name: Deploy

# 触发条件定义
on:
  # 当代码推送到 main 分支时自动触发
  push:
    branches: [main]
  # 允许在 GitHub Actions 页面手动触发（方便紧急部署或重试）
  workflow_dispatch:

# 全局环境变量，所有 Job 中的步骤都可以引用
env:
  # 阿里云容器镜像服务 (ACR) 的注册表地址（个人版，上海区域）
  REGISTRY: crpi-fmn9v2rn38d84ou1.cn-shanghai.personal.cr.aliyuncs.com
  # 镜像名称，最终镜像地址格式为：{REGISTRY}/{IMAGE_NAME}:{tag}
  IMAGE_NAME: axelwt/resume-gpt

# 工作流包含的作业列表
jobs:
  # 第一个 Job：构建 Docker 镜像并推送到 ACR
  build-and-push:
    # 运行环境：GitHub 提供的 Ubuntu 最新版虚拟机
    runs-on: ubuntu-latest
    # 超时时间：15 分钟（防止构建卡住占用资源）
    timeout-minutes: 15
    # 权限声明：仅需读取仓库内容的权限（最小权限原则）
    permissions:
      contents: read

    # Job 包含的步骤列表
    steps:
      # 检出代码：将仓库代码拉取到 Runner 的工作目录中，后续构建才能访问 Dockerfile 等文件
      - uses: actions/checkout@v4.2.2

      # 登录阿里云 ACR：推送镜像前必须先认证
      - name: Log in to Alibaba Cloud ACR
        # 使用 Docker 官方的 login-action，封装了 docker login 命令
        uses: docker/login-action@v3.4.0
        with:
          # ACR 注册表地址，引用全局环境变量
          registry: ${{ env.REGISTRY }}
          # ACR 用户名，从 GitHub Secrets 中读取（避免明文暴露）
          username: ${{ secrets.ACR_USERNAME }}
          # ACR 密码，从 GitHub Secrets 中读取
          password: ${{ secrets.ACR_PASSWORD }}

      # 构建并推送应用镜像（FastAPI 后端）
      - name: Build and push app image
        # 使用 Docker 官方的 build-push-action，封装了 docker build + docker push
        uses: docker/build-push-action@v6.18.0
        with:
          # 构建上下文：项目根目录（包含根目录的 Dockerfile）
          context: .
          # 构建完成后推送到 ACR
          push: true
          # 镜像标签：同时打两个 tag
          tags: |
            # latest 标签：始终指向最新构建，docker compose pull 默认拉取此标签
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
            # commit SHA 标签：用 git commit 的完整哈希值标记，便于回溯和回滚到特定版本
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

      # 构建并推送 Nginx 镜像（反向代理层）
      - name: Build and push nginx image
        # 同样使用 build-push-action
        uses: docker/build-push-action@v6.18.0
        with:
          # 构建上下文仍为项目根目录（因为 nginx/Dockerfile 中需要复制 templates/index.html）
          context: .
          # 指定非默认位置的 Dockerfile（根目录下的是 app 的，nginx 的在子目录中）
          file: nginx/Dockerfile
          # 构建完成后推送到 ACR
          push: true
          # Nginx 镜像标签：使用 -nginx 后缀区分，同样打 latest 和 commit SHA 两个标签
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-nginx:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-nginx:${{ github.sha }}

  # 第二个 Job：SSH 登录服务器执行部署
  deploy:
    # 依赖关系：必须等 build-and-push Job 成功完成后才执行
    needs: build-and-push
    # 运行环境：GitHub 提供的 Ubuntu 最新版虚拟机
    runs-on: ubuntu-latest
    # 超时时间：60 分钟（SSH 部署可能涉及大镜像拉取，需要更长超时）
    timeout-minutes: 60
    # 条件判断：仅当触发分支为 main 时才部署（workflow_dispatch 从其他分支触发时跳过）
    if: github.ref == 'refs/heads/main'

    # Job 包含的步骤列表
    steps:
      # 检出代码：需要读取 docker-compose.yml 文件用于 SCP 传输
      - uses: actions/checkout@v4.2.2

      # 通过 SCP 将 docker-compose.yml 复制到服务器
      - name: Copy config files to server
        # 使用 appleboy/scp-action，基于 SSH 的文件传输
        uses: appleboy/scp-action@v0.1.7
        with:
          # 服务器 IP 或域名，从 GitHub Secrets 中读取
          host: ${{ secrets.DEPLOY_HOST }}
          # SSH 端口，从 GitHub Secrets 中读取，未配置则默认 22
          port: ${{ secrets.DEPLOY_PORT || '22' }}
          # SSH 登录用户名，从 GitHub Secrets 中读取
          username: ${{ secrets.DEPLOY_USER }}
          # SSH 私钥，从 GitHub Secrets 中读取（对应服务器上的公钥）
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          # 要传输的文件：仅传输 docker-compose.yml
          source: "docker-compose.yml"
          # 服务器上的目标路径，未配置则默认 /app/resume-gpt
          target: ${{ secrets.DEPLOY_PATH || '/app/resume-gpt' }}

      # 通过 SSH 登录服务器执行部署命令
      - name: Deploy via SSH
        # 使用 appleboy/ssh-action，基于 SSH 执行远程命令
        uses: appleboy/ssh-action@v1.0.3
        # 定义要传递给远程脚本的环境变量（从 GitHub Secrets 映射而来）
        env:
          # OpenAI API Key，应用运行时可能使用的 AI 服务密钥
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          # DeepSeek API Key，Premium 供应商模式使用，后端从 .env 中读取
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          # Docker 拉取镜像时的 HTTP 代理地址（服务器在国内可能需要代理才能拉取 ACR 镜像）
          DOCKER_HTTP_PROXY: ${{ secrets.DOCKER_HTTP_PROXY }}
          # Docker 拉取镜像时的 HTTPS 代理地址
          DOCKER_HTTPS_PROXY: ${{ secrets.DOCKER_HTTPS_PROXY }}
          # ACR 注册表地址，传递给远程脚本用于 docker login
          ACR_REGISTRY: ${{ env.REGISTRY }}
          # ACR 用户名，传递给远程脚本用于 docker login
          ACR_USERNAME: ${{ secrets.ACR_USERNAME }}
          # ACR 密码，传递给远程脚本用于 docker login
          ACR_PASSWORD: ${{ secrets.ACR_PASSWORD }}
        with:
          # 服务器 IP 或域名，从 GitHub Secrets 中读取
          host: ${{ secrets.DEPLOY_HOST }}
          # SSH 端口，未配置则默认 22
          port: ${{ secrets.DEPLOY_PORT || '22' }}
          # SSH 登录用户名
          username: ${{ secrets.DEPLOY_USER }}
          # SSH 私钥
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          # 远程命令超时时间：60 分钟（与 Job 超时一致）
          command_timeout: 60m
          # 声明要传递到远程脚本的环境变量名列表（只有列出的变量才会被传递）
          envs: OPENAI_API_KEY,DEEPSEEK_API_KEY,DOCKER_HTTP_PROXY,DOCKER_HTTPS_PROXY,ACR_REGISTRY,ACR_USERNAME,ACR_PASSWORD
          # 远程执行的脚本内容
          script: |
            # 进入项目部署目录
            cd ${{ secrets.DEPLOY_PATH || '/app/resume-gpt' }}
            # 将 API Key 写入 .env 文件（> 覆盖写入，确保每次部署都是最新的）
            echo "OPENAI_API_KEY=$OPENAI_API_KEY" > .env
            # 追加 DEEPSEEK_API_KEY 到 .env 文件（>> 追加写入）
            echo "DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY" >> .env

            # 登录阿里云 ACR：通过 stdin 传递密码（比命令行参数更安全，不会出现在进程列表中）
            echo "$ACR_PASSWORD" | docker login --username "$ACR_USERNAME" --password-stdin "$ACR_REGISTRY"

            # 拉取最新镜像：如果配置了代理则通过代理拉取，否则直连
            if [ -n "$DOCKER_HTTPS_PROXY" ] || [ -n "$DOCKER_HTTP_PROXY" ]; then
              # 通过代理拉取镜像（临时设置环境变量，仅对当前命令生效）
              HTTPS_PROXY="$DOCKER_HTTPS_PROXY" HTTP_PROXY="$DOCKER_HTTP_PROXY" docker compose pull
            else
              # 直连拉取镜像
              docker compose pull
            fi
            # 以守护进程模式启动容器，--remove-orphans 清除 docker-compose.yml 中已不存在的旧容器
            docker compose up -d --remove-orphans
            # 清理不再使用的 Docker 镜像（释放磁盘空间），-f 表示强制执行不需要确认
            docker image prune -f
```