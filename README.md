# QQ猫娘

这是一个基于 `NoneBot2 + OneBot V11 + MySQL` 的 QQ 机器人项目。

你现在这套项目的实际部署方式是：

```text
NapCat(Docker) -> OneBot WebSocket -> NoneBot(Python虚拟环境) -> 管理后台
```

如果你是第一次接触这个项目，直接按下面步骤做，不用自己猜。

## 这个项目现在能做什么

- QQ 群聊 / 私聊 AI 对话
- 聊天记忆和摘要压缩
- 图片识别与图片描述
- 工具调用
  - 内置工具
  - 后台新增 HTTP 工具
  - 单工具启停
- 管理后台
  - 运行配置热更新
  - 提示词管理
  - 会话配置
  - 消息查询
  - 摘要查询
  - AI 调用日志
  - 工具管理
  - 定时任务
- Minecraft 重启通知接口
- 拍一拍事件入聊天记忆
- 用户拍小喵时强制触发回复

## 你需要准备什么

你至少需要有下面这些：

1. 一台 Linux 服务器
2. Docker
3. MySQL
4. Python 3.10+
5. `screen`
6. `pnpm`
7. 一个已经登录好的 NapCat 容器

## 目录说明

```text
xiaomiao_refactor/
├── admin_web/                 # 管理后台前端
├── scripts/                   # 迁移脚本
├── sql/                       # 建表 SQL
├── src/
│   ├── plugins/               # NoneBot 插件入口
│   └── xiaomiao_bot/          # 机器人主代码
├── .env.example               # 示例配置
├── pyproject.toml
└── README.md
```

## 第一步：确认 NapCat 正常运行

如果你和当前线上一样使用 Docker 运行 NapCat，先检查容器：

```bash
docker ps
```

你应该能看到类似：

```text
napcat    mlikiowa/napcat-docker:latest
```

再检查 OneBot WebSocket 端口：

```bash
ss -ltnp | grep 3001
```

如果这里没有 `3001`，后面的机器人一定连不上。

## 第二步：准备项目代码

假设你的项目目录是：

```bash
/root/mybot/xiaomiao_v2
```

进入目录后创建虚拟环境：

```bash
cd /root/mybot/xiaomiao_v2
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
pip install nb-cli
```

说明：

- `pip install -e .` 会安装项目依赖
- 现在项目里已经包含 `apscheduler`，所以定时任务功能也会一起安装
- 如果你更新了代码，记得重新执行一次：

```bash
pip install -e .
```

## 第三步：初始化数据库

先执行 [schema.sql](sql/schema.sql)。

如果你是全新部署，直接把整个 SQL 跑一遍。

如果你是老库升级，至少要保证这些表存在：

- `bot_ai_runtime_config`
- `bot_prompt_template`
- `bot_secret_config`
- `bot_group_config`
- `bot_private_config`
- `bot_group_summary`
- `bot_private_summary`
- `bot_ai_call_log`
- `bot_tool_config`
- `bot_scheduled_task`
- `bot_message_session_registry`

说明：

- `bot_tool_config`
- `bot_scheduled_task`
- `bot_minecraft_runtime_config`

这几个表有些代码会自动创建，但不要依赖“运行时碰运气”，最好还是先把主 schema 跑好。

## 第四步：准备配置文件

复制示例配置：

```bash
cp .env.example .env
cp .env.example .env.prod
```

然后编辑 `.env.prod`。

示例文件在 [`.env.example`](.env.example)。

你至少要改这些：

### 1. OneBot / NoneBot 相关

```env
DRIVER=~fastapi+~httpx+~websockets
ONEBOT_WS_URLS=["ws://127.0.0.1:3001/onebot/v11/ws"]
HOST=0.0.0.0
PORT=8080
```

注意：

- `DRIVER` 必须带 `~websockets`
- `ONEBOT_WS_URLS` 必须是 JSON 数组格式
- 不能写成普通字符串

### 2. 模型相关

```env
AI_API_KEY=你的key
AI_BASE_URL=http://127.0.0.1:8317/v1
TEXT_MODEL=你的文本模型
VISION_MODEL=你的视觉模型
TEXT_MODEL_FALLBACK=备用模型1,备用模型2
VISION_MODEL_FALLBACK=备用模型1,备用模型2
```

### 3. MySQL 相关

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_DB=xiaomiao
```

### 4. 后台登录相关

```env
ADMIN_UID=你的QQ号
ADMIN_API_TOKEN=你自定义的后台token
```

### 5. Minecraft 通知相关

```env
MINECRAFT_API_SECRET=你自定义的通知密钥
```

说明：

- Minecraft 通知群现在也支持后台配置，不再只靠 `.env`
- 但 `MINECRAFT_API_SECRET` 仍建议放环境变量或后台密钥配置里

## 第五步：构建管理后台

进入前端目录：

```bash
cd /root/mybot/xiaomiao_v2/admin_web
pnpm install
pnpm build
```

构建完成后，后端会直接托管前端产物。

访问地址：

```text
http://你的服务器IP:8080/admin-ui/login
```

## 第六步：启动机器人

先回到项目根目录：

```bash
cd /root/mybot/xiaomiao_v2
source .venv/bin/activate
export PYTHONPATH=/root/mybot/xiaomiao_v2/src
nb run
```

如果 `nb` 命令不可用，也可以：

```bash
python -m nonebot
```

## 第七步：用 screen 挂后台

建议这样启动：

```bash
screen -dmS mcbot bash -lc 'cd /root/mybot/xiaomiao_v2 && source .venv/bin/activate && export PYTHONPATH=/root/mybot/xiaomiao_v2/src && nb run'
```

查看会话：

```bash
screen -ls
```

进入会话：

```bash
screen -r mcbot
```

退出但不关闭：

- 先按 `Ctrl + A`
- 再按 `D`

## 第八步：登录后台

访问：

```text
http://你的服务器IP:8080/admin-ui/login
```

登录需要：

1. 管理员 QQ
2. `ADMIN_API_TOKEN`

说明：

- QQ 必须在管理员白名单里
- 如果管理员白名单为空，系统会尝试自动写入 `ADMIN_UID`

## 后台都能配什么

### 1. AI 运行配置

可以改：

- 主模型
- 备用模型
- 默认回复率
- 工具总开关
- 摘要总开关
- 摘要只在群聊启用
- 摘要触发条数
- 摘要保留最近消息数
- 摘要冷却秒数
- 摘要最少新增消息数
- 最大历史条数
- 日志级别

### 2. 提示词

现在支持这些提示词：

- 基础人格
- 私聊逻辑
- @机器人逻辑
- 用户拍了一下你
- 群聊逻辑
- 摘要系统提示词

### 3. 工具管理

当前支持：

- 内置工具启停
- 新增 HTTP 工具
- 编辑 HTTP 工具
- 删除 HTTP 工具

当前还不支持：

- 后台直接写 Python 代码工具

### 4. 定时任务

支持：

- 新增 / 编辑 / 删除 / 查询
- 状态
- 描述
- 上次运行时间 / 下次运行时间
- 投递到多个群号 / 多个 QQ
- 立即运行

调度类型支持：

- `once`
- `interval`
- `cron`

注意：

- 定时任务现在不是“直接发一段固定文本”
- 而是把 `message_content` 当成一条用户消息交给 AI
- 再由 AI 生成回复后投递到群/私聊

### 5. 消息查询

支持：

- 查看
- 编辑
- 删除
- 批量删除
- 清空当前会话全部消息

### 6. 摘要查询

支持查看：

- 当前摘要
- 摘要版本
- 起始消息 ID / 结束消息 ID
- 创建时间

### 7. Minecraft 通知

现在支持：

- 后台配置通知群白名单
- 运行时热生效
- 接口按白名单投递指定群

接口：

```text
POST /minecraft/restart
```

请求体示例：

```json
{
  "message": "服务器即将重启",
  "secret": "你的密钥",
  "group_ids": [123456789, 987654321]
}
```

## 常用迁移脚本

### Redis -> MySQL

```bash
python scripts/sync_redis_to_mysql.py ...
```

脚本位置：

- [sync_redis_to_mysql.py](scripts/sync_redis_to_mysql.py)

### 共享消息表 -> 动态分表

```bash
python scripts/migrate_shared_messages_to_partitioned_tables.py
```

脚本位置：

- [migrate_shared_messages_to_partitioned_tables.py](scripts/migrate_shared_messages_to_partitioned_tables.py)

## 你最容易踩的坑

### 1. 后台打开是 404

先检查：

```bash
curl http://127.0.0.1:8080/admin/auth/me
curl http://127.0.0.1:8080/admin-ui/login
```

如果两个都是 404，一般不是前端问题，而是 `admin_api` 插件导入失败。

最常见原因：

- 新增依赖没安装
- 代码同步了，但 `pip install -e .` 没重新执行

### 2. 机器人收不到消息

先看：

```bash
ss -ltnp | grep 3001
ss -ltnp | grep 8080
```

还要确认 `.env.prod`：

- `DRIVER` 包含 `~websockets`
- `ONEBOT_WS_URLS` 是 JSON 数组

### 3. MySQL 明明配了密码，却提示 `using password: NO`

说明不是密码错，而是程序没读到环境变量。  
通常是：

- `.env.prod` 没生效
- 启动方式不对
- 代码没重启

### 4. 定时任务新增成功但不执行

先看：

- `apscheduler` 是否安装
- 代码是否同步了带调度器启动钩子的 `src/plugins/admin_api.py`

然后看任务表里的：

- `status`
- `next_run_at`

### 5. 选择 `200/page` 报错

现在代码已经支持 `200/page`。  
如果你还看到这个错误，说明服务器后端代码没同步或没重启。

## Git 忽略建议

这些不要提交：

- `.env`
- `.env.prod`
- `admin_web/dist`
- `admin_web/node_modules`
- `__pycache__`
- 本地数据库
- 备份文件
- 第三方参考项目源码目录

## 最后一句

如果你只是想让机器人先跑起来，最短路径就是：

1. NapCat 容器正常运行
2. `.env.prod` 配对
3. 跑 `schema.sql`
4. `pip install -e .`
5. `pnpm build`
6. `screen` 启动 `nb run`

只要这 6 步都对，项目基本就能起来。  
剩下的问题一般都是“代码没同步”或者“改完没重启”。  
