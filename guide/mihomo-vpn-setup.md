# 云服务器部署 Mihomo（Clash Meta 内核）代理指南

> 本文档介绍如何在云服务器上通过 Docker 部署 Mihomo 代理，并配置 Web UI 面板进行可视化管理。

## 环境要求

- 云服务器（Linux，推荐 Ubuntu 20.04+ / Debian 11+ / CentOS 8+）
- 已安装 Docker 及 Docker Compose
- 拥有可用的代理订阅链接

---

## 第一步：拉取 Mihomo Docker 镜像

```bash
docker pull metacubex/mihomo
```

> Mihomo 是 Clash Meta 的继任项目，镜像地址为 `metacubex/mihomo`。

拉取完成后验证：

```bash
docker images | grep mihomo
```

---

## 第二步：配置 config.yml 文件

创建配置目录并编写核心配置文件：

```bash
mkdir -p /opt/mihomo
```

创建 `/opt/mihomo/config.yaml`，内容如下：

```yaml
mixed-port: 7890
allow-lan: true
bind-address: "*"
mode: rule
log-level: info
ipv6: false
external-controller: 0.0.0.0:9090
external-ui: ui
secret: "your-secret-password"

dns:
  enable: true
  listen: 0.0.0.0:1053
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - https://dns.alidns.com/dns-query
    - https://doh.pub/dns-query
  fallback:
    - https://dns.google/dns-query
    - https://cloudflare-dns.com/dns-query
  fallback-filter:
    geoip: true
    geoip-code: CN

proxy-providers:
  my-subscription:
    type: http
    url: "你的订阅链接"          # <-- 替换为你的订阅链接
    interval: 3600
    path: ./proxies/my-sub.yaml
    health-check:
      enable: true
      url: https://www.gstatic.com/generate_204
      interval: 300

proxy-groups:
  - name: "🚀 节点选择"
    type: select
    use:
      - my-subscription

  - name: "♻️ 自动选择"
    type: url-test
    use:
      - my-subscription
    url: https://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50

  - name: "🎯 全球直连"
    type: select
    proxies:
      - DIRECT

rules:
  - GEOIP,CN,🎯 全球直连
  - MATCH,🚀 节点选择
```

### 关键配置说明

| 配置项 | 说明 |
|---|---|
| `mixed-port: 7890` | HTTP/SOCKS5 混合代理端口 |
| `allow-lan: true` | 允许局域网连接 |
| `external-controller` | RESTful API 地址，Web UI 依赖此端口 |
| `external-ui` | Web UI 静态文件路径 |
| `secret` | API 访问密钥，**请务必修改** |
| `proxy-providers` | 通过订阅链接自动拉取节点 |
| `url` | **替换为你的实际订阅链接** |

---

## 第三步：拉取 Mihomo Web UI

Mihomo 推荐使用 **MetaCubeXD** 作为 Web 管理面板（Yacd 亦可）。

```bash
mkdir -p /opt/mihomo/ui
```

下载 MetaCubeXD 最新发行版并解压到 UI 目录：

```bash
# 下载最新版 MetaCubeXD
curl -sL https://github.com/MetaCubeX/metacubexd/releases/latest/download/compressed-dist.tgz -o /tmp/metacubexd.tgz

# 解压到 UI 目录
tar -xzf /tmp/metacubexd.tgz -C /opt/mihomo/ui

# 清理临时文件
rm -f /tmp/metacubexd.tgz
```

> 如果 GitHub 访问缓慢，可使用镜像：
> ```bash
> curl -sL https://mirror.ghproxy.com/https://github.com/MetaCubeX/metacubexd/releases/latest/download/compressed-dist.tgz -o /tmp/metacubexd.tgz
> ```

验证 UI 文件是否就位：

```bash
ls /opt/mihomo/ui/
```

---

## 第四步：修改 config.yml 以支持 Web UI

确保 `config.yaml` 中以下配置项已正确设置（第二步中已包含，此处确认）：

```yaml
external-controller: 0.0.0.0:9090   # 监听所有网卡，端口 9090
external-ui: ui                      # 容器内 UI 文件挂载路径
secret: "your-secret-password"        # API 密钥（登录 Web UI 时需要）
```

> **注意：** `external-ui` 的值 `/ui` 对应容器内的路径，需要在启动容器时将宿主机的 `/opt/mihomo/ui` 挂载到容器的 `/ui` 目录。

---

## 第五步：上线容器

### 方式一：Docker Run

```bash
docker run -d \
  --name mihomo \
  --restart always \
  -p 7890:7890 \
  -p 9090:9090 \
  -v /opt/mihomo/config.yaml:/root/.config/mihomo/config.yaml \
  -v /opt/mihomo/ui:/ui \
  metacubex/mihomo
```

### 方式二：Docker Compose（推荐）

创建 `/opt/mihomo/docker-compose.yml`：

```yaml
services:
  mihomo:
    image: metacubex/mihomo
    container_name: mihomo
    restart: always
    ports:
      - "7890:7890"
      - "9090:9090"
    volumes:
      - ./config.yaml:/root/.config/mihomo/config.yaml
      - ./ui:/ui
```

启动：

```bash
cd /opt/mihomo && docker compose up -d
```

### 验证运行状态

```bash
# 查看容器状态
docker ps | grep mihomo

# 查看实时日志
docker logs -f mihomo
```

### 访问 Web UI

浏览器打开：

```
http://你的服务器IP:9090/ui
```

- **主机（Host）：** 填写 `你的服务器IP:9090`
- **密钥（Secret）：** 填写 `config.yaml` 中 `secret` 的值

### 代理使用

在其他设备上配置 HTTP/SOCKS5 代理：

- **地址：** 你的服务器 IP
- **端口：** `7890`

---

## 目录结构总览

```
/opt/mihomo/
├── config.yaml          # Mihomo 核心配置文件
├── docker-compose.yml   # Docker Compose 编排文件
└── ui/                  # Web UI 静态文件
    ├── index.html
    └── ...
```

---

## 常见问题

**Q: Web UI 无法访问？**

检查防火墙是否放行 9090 端口：

```bash
# Ubuntu / Debian
sudo ufw allow 9090

# CentOS
sudo firewall-cmd --permanent --add-port=9090/tcp
sudo firewall-cmd --reload
```

同时确认云服务器安全组规则中已放行 9090 和 7890 端口。

**Q: 订阅节点未加载？**

检查订阅链接是否有效，查看容器日志排查：

```bash
docker logs mihomo 2>&1 | grep -i error
```

**Q: 如何更新 Mihomo？**

```bash
docker pull metacubex/mihomo
cd /opt/mihomo && docker compose up -d
```

---

## 参考资料

- [Mihomo 官方仓库](https://github.com/MetaCubeX/mihomo)
- [Mihomo Wiki](https://wiki.metacubex.one/)
- [MetaCubeXD Web UI](https://github.com/MetaCubeX/metacubexd)
- [Clash Meta 配置文档](https://wiki.metacubex.one/config/)
- [Docker 官方文档](https://docs.docker.com/)
