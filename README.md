# xiaomiao_refactor

基于 NoneBot2 + OneBot V11 的小喵机器人重构版。

## 目标

- 保留原项目全部核心能力
- 去掉 Redis，改为 MySQL 直存
- 重组项目结构，降低模块耦合

## 功能

- QQ 群聊 / 私聊 AI 对话
- `/sleep` `/wakeup` `/rate` `/srate` `/clean` 命令
- 运行时配置管理 API
- Minecraft 重启通知 API
- 工具调用：时间、联网搜索、网页抓取、天气
- 会话摘要压缩
- 图片消息与引用图片描述

## 目录

```text
xiaomiao_refactor/
├── admin_web/
├── pyproject.toml
├── README.md
├── .env
├── sql/
│   └── schema.sql
└── src/
    ├── plugins/
    └── xiaomiao_bot/
```

## 环境变量

直接编辑项目根目录的 `.env`。

其中：
- `TEXT_MODEL` / `VISION_MODEL` 配置主模型
- `TEXT_MODEL_FALLBACK` / `VISION_MODEL_FALLBACK` 配置逗号分隔的回滚模型列表

## 启动

```bash
cd /root/mybot/xiaomiao_refactor
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
export PYTHONPATH=/root/mybot/xiaomiao_refactor/src
nb run
```

## Screen 运行

```bash
screen -dmS bot_refactor bash -lc 'cd /root/mybot/xiaomiao_refactor && source .venv/bin/activate && export PYTHONPATH=/root/mybot/xiaomiao_refactor/src && nb run'
```

## 数据库

先执行 [sql/schema.sql](/C:/Users/84334/Desktop/fsdownload/src/xiaomiao_refactor/sql/schema.sql) 建表。

## 管理后台

前端工程在 `admin_web/`，构建后由 NoneBot/FastAPI 同服务托管到 `/admin-ui/`。

```bash
cd /root/mybot/xiaomiao_refactor/admin_web
pnpm install
pnpm run build
```

构建完成后直接访问：

- `http://你的服务器地址:8080/admin-ui/login`

登录方式：

- 输入管理员 QQ 号
- 输入 `ADMIN_API_TOKEN`
- QQ 号必须在 `bot_admin_user` 白名单中

当前后台支持：

- 系统概览
- AI 运行配置热更新
- 提示词管理
- 管理员与密钥管理
- 黑名单、群聊、私聊配置
- 群聊/私聊消息查询
- 群聊/私聊摘要查询
- AI 调用日志查询
