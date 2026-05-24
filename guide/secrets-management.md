# 敏感配置管理方案

项目通过 GitHub Secrets 管理敏感信息（API Key 等），部署时自动注入到服务器，不写入代码仓库。

## 架构

```
GitHub Secrets (配置中心)
       ↓
GitHub Actions (部署时读取)
       ↓ SSH 传输
服务器 .env 文件 (临时存储)
       ↓ docker compose env_file 加载
容器环境变量 (运行时使用)
```

## 配置步骤

### 1. 添加 GitHub Secret

进入仓库 **Settings → Secrets and variables → Actions**，点击 **New repository secret**，添加需要的 key，例如：

| Secret 名称 | 用途 |
|---|---|
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `DEPLOY_HOST` | 部署服务器地址 |
| `DEPLOY_SSH_KEY` | SSH 私钥 |

### 2. 在 Workflow 中引用

在 `.github/workflows/deploy.yml` 中通过 `${{ secrets.XXX }}` 读取，并通过 SSH 写入服务器 `.env` 文件：

```yaml
- name: Deploy via SSH
  uses: appleboy/ssh-action@v1.0.3
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  with:
    host: ${{ secrets.DEPLOY_HOST }}
    # ... 其他配置
    envs: OPENAI_API_KEY
    script: |
      cd ${{ secrets.DEPLOY_PATH || '/app/resume-gpt' }}
      echo "OPENAI_API_KEY=$OPENAI_API_KEY" > .env
      docker compose pull
      docker compose up -d --remove-orphans
```

### 3. Docker Compose 加载 .env

`docker-compose.yml` 通过 `env_file` 读取 `.env`，容器内可通过 `os.environ` 获取：

```yaml
services:
  app:
    env_file:
      - .env
    environment:
      - TZ=Asia/Shanghai
```

## 新增 Secret 的流程

1. 在 GitHub 仓库 Settings 中添加新的 Secret
2. 在 workflow 的 `env` 中添加对应的 `KEY: ${{ secrets.KEY }}`
3. 在 `envs` 字段中补充 key 名称
4. 在 `script` 的 `echo` 行中追加 `echo "KEY=$KEY" >> .env`
5. 提交代码，推送后自动生效

## 安全保障

- `.env` 已在 `.gitignore` 中，不会被提交到仓库
- GitHub Secrets 加密存储，日志中自动脱敏
- 服务器上 `.env` 文件仅在部署时生成，不纳入版本控制
