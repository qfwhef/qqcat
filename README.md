# xiaomiao_refactor

基于 `NoneBot2 + OneBot V11 + MySQL` 的小喵机器人重构版。

这个版本的目标不是只“能跑”，而是把原项目里聊天、记忆、工具、配置管理、后台管理这些能力整理成更清晰的结构，同时去掉 Redis，统一走 MySQL。

## 特性

- QQ 群聊 / 私聊 AI 对话
- `/sleep` `/wakeup` `/rate` `/srate` `/clean` 命令
- MySQL 直存，不依赖 Redis
- 会话摘要压缩与长期记忆
- 图片消息识别与引用图片补充描述
- 模型回滚、失败原因区分、AI 调用日志
- Web 管理后台
- 运行时热更新配置
- 工具管理
  - 全局工具开关
  - 单工具启停
  - 后台新增 / 编辑 / 删除 HTTP 工具
- Minecraft 重启通知接口

## 技术栈

- Python 3.10+
- NoneBot2
- OneBot V11 Adapter
- FastAPI / Uvicorn
- MySQL
- Vue 3 + Vite + Element Plus

## 项目结构

```text
xiaomiao_refactor/
├── admin_web/                 # 管理后台前端
├── scripts/                   # 迁移 / 同步脚本
├── sql/                       # 建表 SQL 与迁移文档
├── src/
│   ├── plugins/               # NoneBot 插件入口
│   └── xiaomiao_bot/
│       ├── adapters/          # OneBot 适配
│       ├── application/       # 应用服务
│       ├── bootstrap/         # 依赖注入容器
│       ├── core/              # 配置、常量、日志
│       ├── domain/            # 领域模型
│       ├── infrastructure/    # 数据库 / 存储
│       ├── presentation/      # HTTP API / 权限
│       └── tools/             # 工具注册与执行
├── .env.example               # 示例配置
├── pyproject.toml
└── README.md
```

## 环境准备

### 1. 创建虚拟环境并安装依赖

```bash
cd /root/mybot/xiaomiao_refactor
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
pip install nb-cli
```

### 2. 初始化数据库

先执行 [schema.sql](C:/Users/84334/Desktop/fsdownload/src/xiaomiao_refactor/sql/schema.sql)。

如果你已经在旧版本基础上升级，除了完整建表外，还要确认 `bot_ai_runtime_config` 里已经包含这些摘要配置列：

- `summary_trigger_rounds`
- `summary_keep_recent_messages`
- `summary_cooldown_seconds`
- `summary_min_new_messages`

### 3. 准备环境变量

复制示例配置：

```bash
cp .env.example .env
cp .env.example .env.prod
```

然后按实际环境填写。

## 配置说明

示例文件见 [`.env.example`](C:/Users/84334/Desktop/fsdownload/src/xiaomiao_refactor/.env.example)。

重点字段：

- `DRIVER`
  - 必须包含 `~websockets`
- `ONEBOT_WS_URLS`
  - 必须是 JSON 数组格式
- `AI_API_KEY`
  - 模型服务密钥
- `AI_BASE_URL`
  - OpenAI 兼容接口地址
- `TEXT_MODEL` / `VISION_MODEL`
  - 主模型
- `TEXT_MODEL_FALLBACK` / `VISION_MODEL_FALLBACK`
  - 逗号分隔的回滚模型列表
- `MYSQL_*`
  - MySQL 连接配置
- `ADMIN_UID`
  - 默认后台管理员 QQ
- `ADMIN_API_TOKEN`
  - 后台登录 token
- `MINECRAFT_API_SECRET`
  - Minecraft 通知接口校验密钥

## 启动机器人

```bash
cd /root/mybot/xiaomiao_refactor
source .venv/bin/activate
export PYTHONPATH=/root/mybot/xiaomiao_refactor/src
nb run
```

如果没有 `nb`，可以直接：

```bash
python -m nonebot
```

## 使用 Screen 后台运行

```bash
screen -dmS xiaomiao bash -lc 'cd /root/mybot/xiaomiao_refactor && source .venv/bin/activate && export PYTHONPATH=/root/mybot/xiaomiao_refactor/src && nb run'
```

查看：

```bash
screen -ls
```

进入：

```bash
screen -r xiaomiao
```

## 构建管理后台

```bash
cd /root/mybot/xiaomiao_refactor/admin_web
pnpm install
pnpm build
```

构建完成后由后端同服务托管，访问：

- `http://你的服务器地址:8080/admin-ui/login`

## 后台能力

当前后台支持：

- 概览
- AI 运行配置
- 工具管理
- 提示词管理
- 访问控制
- 会话配置
- 消息查询
- 摘要查询
- AI 调用日志

### 工具管理

当前支持两类工具：

1. 内置工具
- `get_current_time`
- `web_search`
- `web_fetch`
- `get_weather`

2. 数据库 HTTP 工具
- 后台新增
- 单工具启停
- 编辑请求方法 / URL / Headers / Body 模板 / 参数 Schema
- 删除 HTTP 工具

说明：

- 内置工具允许启停，但不允许删除
- HTTP 工具修改后立即生效，不需要重启
- 当前还没有开放“后台直接写 Python 脚本工具”

## 运行时热更新

这些配置现在可以在后台实时修改：

- 模型与回滚模型
- 默认回复率
- 工具总开关
- 摘要总开关
- 摘要仅群聊开关
- 摘要阈值配置
  - `摘要触发条数`
  - `摘要保留最近消息数`
  - `摘要冷却秒数`
  - `摘要最少新增消息数`
- 最大历史条数
- 日志级别
- 提示词
- 黑名单
- 群聊 / 私聊配置

## 迁移脚本

### Redis -> MySQL

[sync_redis_to_mysql.py](C:/Users/84334/Desktop/fsdownload/src/xiaomiao_refactor/scripts/sync_redis_to_mysql.py)

### 共享消息表 -> 动态分表

[migrate_shared_messages_to_partitioned_tables.py](C:/Users/84334/Desktop/fsdownload/src/xiaomiao_refactor/scripts/migrate_shared_messages_to_partitioned_tables.py)

## 注意事项

- `.env` / `.env.prod` 不要提交到 Git
- `ONEBOT_WS_URLS` 必须是 JSON 数组，不能写成普通字符串
- 机器人使用动态消息分表：
  - 群聊：`bot_group_message_<group_id>`
  - 私聊：`bot_private_message_<user_id>`
- 如果后台页面访问异常，优先检查：
  - `DRIVER` 是否包含 `~websockets`
  - `PYTHONPATH` 是否指向 `src`
  - MySQL 表结构是否与当前代码一致

## Git

当前仓库建议忽略：

- `.env`
- `.env.prod`
- `admin_web/dist`
- `node_modules`
- `LittleMeowBot-main`
- 本地数据库 / 备份文件 / 缓存
