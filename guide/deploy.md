# 服务器部署指南

## 架构概览

```
代码推送到 main → GitHub Actions 构建镜像 → 推送到 GHCR → SSH 到服务器拉取新镜像并重启容器
```

## 前置条件

- 一台有公网 IP 的 Linux 服务器（阿里云、腾讯云、AWS 等）
- 服务器开放 22（SSH）和 8000（应用）端口

## 一、服务器环境准备

### 1. 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

### 2. 登录 GHCR

私有仓库的镜像拉取需要认证。前往 GitHub → Settings → Developer settings → Personal access tokens 创建一个 Token，勾选 `read:packages` 权限。

```bash
echo "你的PAT" | docker login ghcr.io -u AxelWT --password-stdin
```

### 3. 创建项目目录并上传 docker-compose.yml

```bash
mkdir -p /app/resume-gpt
```

在本地执行：

```bash
scp docker-compose.yml 用户名@服务器IP:/app/resume-gpt/
```

## 二、配置 GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加以下 secrets：

| Secret | 说明 |
|--------|------|
| `DEPLOY_HOST` | 服务器公网 IP |
| `DEPLOY_PORT` | SSH 端口（可选，默认 22） |
| `DEPLOY_USER` | SSH 登录用户名 |
| `DEPLOY_SSH_KEY` | SSH 私钥内容（`cat ~/.ssh/id_rsa` 的完整输出） |
| `DEPLOY_PATH` | 服务器上的项目路径（可选，默认 `/app/resume-gpt`） |

### 生成 SSH 密钥对（如果没有）

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy"
```

将公钥（`~/.ssh/id_ed25519.pub`）添加到服务器的 `~/.ssh/authorized_keys` 中，私钥内容填入 `DEPLOY_SSH_KEY`。

## 三、部署流程

配置完成后，每次推送到 `main` 分支，GitHub Actions 会自动执行：

1. **构建镜像** — 基于 Dockerfile 构建 Docker 镜像
2. **推送镜像** — 推送到 `ghcr.io/axelwt/resume-gpt`
3. **SSH 部署** — 连接服务器执行以下命令：
   ```bash
   docker compose pull
   docker compose up -d --remove-orphans
   docker image prune -f
   ```

也可以在 GitHub Actions 页面手动触发（`workflow_dispatch`）。

## 四、手动操作

### 在服务器上手动部署

```bash
cd /app/resume-gpt
docker compose pull
docker compose up -d --remove-orphans
docker image prune -f
```

### 查看应用日志

```bash
docker compose logs -f
```

### 重启应用

```bash
docker compose restart
```

## 五、故障排查

| 问题 | 排查方式 |
|------|----------|
| 容器未启动 | `docker compose ps` 查看状态 |
| 应用报错 | `docker compose logs -f` 查看日志 |
| 拉取镜像失败 | 检查 GHCR 登录状态：`docker login ghcr.io` |
| SSH 连接失败 | 检查 secrets 配置和服务器公钥 |
| 端口不通 | 检查服务器安全组和防火墙是否放通 8000 端口 |
