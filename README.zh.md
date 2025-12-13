<div align="center">

> ⚠️ **重要提示:** 该项目目前处于 **Alpha 测试阶段**。
> 功能可能会发生变化，可能出现错误和不稳定的情况。
> 请谨慎使用并报告任何问题。

</div>

---

# GraceHub Platform

<div align="right">
  <a href="README.md">🇷🇺 Русский</a> •
  <a href="README.en.md">🇬🇧 English</a> •
  <a href="README.es.md">🇪🇸 Español</a> •
  <a href="README.hi.md">🇮🇳 हिन्दी</a> •
  <a href="README.zh.md">🇨🇳 简体中文</a>
</div>

GraceHub 是一个 SaaS 平台，使您能够直接在 Telegram 中部署支持，同时成为为小型和中型企业提供反馈机器人和技术支持服务的提供商。

**🌐 网站:** [gracehub.ru](https://gracehub.ru)  
**📢 Telegram 频道:** [@gracehubru](https://t.me/gracehubru)  
**👨‍💻 开发者:** [@Gribson_Micro](https://t.me/Gribson_Micro)

## 主要功能

- **主机器人** — 用于绑定所有反馈机器人的控制中心
- **Mini App 个人柜台** — 用于管理机器人和客户的直观界面
- **统计和分析** — 跟踪每个机器人的指标
- **计费系统** — 自动计算和支付管理

## 🌍 支持的语言

- 🇷🇺 Русский
- 🇬🇧 English
- 🇪🇸 Español
- 🇮🇳 हिन्दी
- 🇨🇳 简体中文

## 🛠 技术栈

| 组件 | 技术 |
|-----------|-----------|
| 后端 | Python (FastAPI, Hypercorn) |
| 前端 | React 19 + TypeScript + Vite |
| 机器人管理 | Telegram Bot API |
| 数据库 | PostgreSQL 15+ |
| 代理 | Nginx |
| Python 版本 | 3.11+ |

## 📁 项目结构

```
gracehub/
├── src/
│   └── master_bot/
│       ├── main.py                 # 主机器人入口点
│       ├── api_server.py           # REST API 服务器
│       └── worker/                 # 实例工作程序
├── frontend/miniapp_frontend/      # React 应用程序
├── config/                         # 配置文件
├── scripts/
│   └── launch.sh                   # 启动脚本
├── logs/                           # 应用日志
└── .env                            # 环境变量
```

## 📋 要求

- Python 3.11+
- Node.js 20+
- PostgreSQL 15+
- Nginx（可选）

## ⚙️ 环境设置

1. 导航到项目目录：

```bash
cd /root/gracehub
```

2. 创建并配置环境文件：

```bash
cp .env-example .env
nano .env
```

3. 加载环境变量：

```bash
source .env
```

4. 如果需要，创建虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate
```

## 🚀 开发运行

### 普通模式（带终端日志）

```bash
./scripts/launch.sh dev
```

### 后台模式

```bash
./scripts/launch.sh dev --detach
```

启动包括三个进程：
- 主机器人
- REST API 服务器
- 前端应用程序

### 个人使用运行

如果您想为自己和您的团队运行项目并限制外部访问，请在 `.env` 中指定 2 个参数：

```bash
export GRACEHUB_SINGLE_TENANT_OWNER_ONLY=1
export GRACEHUB_OWNER_TELEGRAM_ID=YOUR_ID
```

将 `YOUR_ID` 替换为您的 Telegram ID。

## 🔧 通过 systemd 生产部署

### 初始设置和部署

```bash
./scripts/launch.sh prod
```

### 服务管理

部署后，通过 systemd 管理服务：

```bash
# 检查状态
systemctl status gracehub-master gracehub-api gracehub-frontend

# 重启服务
systemctl restart gracehub-master gracehub-api gracehub-frontend

# 停止服务
systemctl stop gracehub-frontend
```

## 📊 日志和监控

### 开发模式

日志位于 `logs/` 目录中：

```bash
tail -f logs/masterbot.log
tail -f logs/api_server.log
tail -f logs/frontend-dev.log
```

### 生产环境

查看 systemd 日志：

```bash
journalctl -u gracehub-master -n 50 --no-pager
journalctl -u gracehub-api -n 50 --no-pager
journalctl -u gracehub-frontend -n 50 --no-pager
```

## 🎯 使用说明

成功部署后，按照以下步骤设置您的支持：

### 第 1 步：连接主 GraceHub 机器人

1. 在 Telegram 中找到主 GraceHub Platform 机器人（您在前面步骤中部署的）
2. 点击 **Start** 或输入 `/start`
3. 机器人将为您提供个人柜台和管理说明

### 第 2 步：注册您的支持机器人

1. 在主机器人中，选择添加新机器人的选项
2. 通过 [@BotFather](https://t.me/botfather) 获取您的 Telegram 机器人令牌
3. 将令牌发送到 GraceHub Platform 机器人
4. 您的支持机器人将在系统中被激活

### 第 3 步：初始化管理员

1. 在您的新支持机器人中输入 `/start` 命令
2. 机器人将记住您是管理员并授予管理权限

### 第 4 步：创建带主题的超级聊天

1. 在 Telegram 中创建新群组
2. 在群组设置中，启用 **"讨论"** (Topics) 模式
3. 将您的支持机器人添加到此群组，具有管理员权限
4. 确保机器人有权管理消息和主题

### 第 5 步：将机器人绑定到常规主题

1. 在您的超级聊天中打开 **常规** 主题
2. 输入绑定命令：

```
/bind @your_bot_username
```

将 `@your_bot_username` 替换为您的支持机器人的用户名。

3. 成功绑定后，机器人将开始在此主题中接受客户请求
4. 所有客户消息将自动分配到超级聊天中的主题

### ✅ 完成！

您的 Telegram 支持系统已完全配置。您业务的客户可以写信给机器人，您将在便捷的超级聊天界面中看到所有请求，并按主题分离。

## 📄 许可证

MIT

