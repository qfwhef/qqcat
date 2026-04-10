# 小喵机器人 V2 数据迁移方案

## 目标

- 将当前“Redis 风格 KV 结构”迁移为关系型表结构
- 保留现有运行能力，同时为可视化管理和热更新做准备
- 在迁移阶段不直接删除旧表，先并行保留，确保可回滚

## 当前旧结构

### 旧来源一：Redis db2

- `runtime:bot:config`
- `config:{group|private}:{id}:{config_key}`
- `chat_history:{group|private}:{id}`
- `chat_summary:{group|private}:{id}`
- `chat_history_version:{group|private}:{id}`
- `chat_summary_state:{group|private}:{id}`

### 旧来源二：当前 MySQL 中间表

- `bot_ai_config`
- `bot_chat_config`
- `bot_chat_history`
- `bot_chat_summary`

## 新结构总览

### 配置域

- `bot_ai_runtime_config`
- `bot_prompt_template`
- `bot_secret_config`
- `bot_blocked_group`
- `bot_blocked_user`
- `bot_group_config`
- `bot_private_config`

### 状态域

- `bot_group_session_state`
- `bot_private_session_state`

### 消息域

- `bot_group_message`
- `bot_private_message`

### 摘要域

- `bot_group_summary`
- `bot_private_summary`

### 观测与审计

- `bot_ai_call_log`
- `bot_config_change_log`

## 迁移原则

1. 先建新表，不删旧表。
2. 先迁配置，再迁消息，再迁摘要。
3. 迁移脚本必须幂等，允许重复执行。
4. 对无法从旧数据精确还原的字段，允许先置空，但必须在文档中明确。

## 字段映射方案

### 1. 全局 AI 配置迁移

#### 来源

- `bot_ai_config`
- `.env` / `.env.prod`

#### 目标

- `bot_ai_runtime_config`
- `bot_prompt_template`
- `bot_secret_config`

#### 映射建议

- `default_reply_rate` -> `bot_ai_runtime_config.default_reply_rate`
- `enable_tools` -> `bot_ai_runtime_config.enable_tools`
- `enable_summary_memory` -> `bot_ai_runtime_config.enable_summary_memory`
- `summary_only_group` -> `bot_ai_runtime_config.summary_only_group`
- `text_model` / `vision_model` / fallback 列表 -> `bot_ai_runtime_config`
- `prompt_base` -> `bot_prompt_template(prompt_type='base')`
- `prompt_logic_private` -> `bot_prompt_template(prompt_type='private')`
- `prompt_logic_at_me` -> `bot_prompt_template(prompt_type='at_me')`
- `prompt_logic_group` -> `bot_prompt_template(prompt_type='group')`
- `prompt_summary_system` -> `bot_prompt_template(prompt_type='summary_system')`
- `AI_API_KEY` / `AMAP_API_KEY` / `SERPER_API_KEY` / `TAVILY_API_KEY` -> `bot_secret_config`

#### 注意

- 敏感配置建议优先保留在 `.env`，后台仅展示掩码；是否完全入库可作为第二阶段。

### 2. 黑名单迁移

#### 来源

- `bot_ai_config.blocked_groups`
- `bot_ai_config.blocked_users`
- 若 `bot_ai_config` 为空，则回退读取 `.env`

#### 目标

- `bot_blocked_group`
- `bot_blocked_user`

#### 规则

- 群黑名单一条群号一行
- 用户黑名单一条用户QQ一行

### 3. 群聊/私聊配置迁移

#### 来源

- `bot_chat_config`

#### 目标

- `bot_group_config`
- `bot_private_config`

#### 映射规则

- `config_key='reply_rate'` -> `reply_rate`
- `config_key='sleeping'` -> `is_sleeping`
- 其他字段没有明确来源时保留默认值：
  - `enable_ai = 1`
  - `enable_summary = 1`

### 4. 会话状态迁移

#### 来源

- `bot_chat_config`

#### 目标

- `bot_group_session_state`
- `bot_private_session_state`

#### 映射规则

- `history_version` -> 可用于推导当前最新进度，但在 V2 中更推荐用 `last_message_id`
- `last_summary_version` -> `summary_version`
- `summary_cooldown_until` -> `summary_cooldown_until`

#### 注意

- `last_message_id` 和 `last_summary_message_id` 无法直接从旧 KV 表得到，需要在消息迁移完成后回填。

### 5. 消息迁移

#### 来源

- `bot_chat_history.history_json`

#### 目标

- `bot_group_message`
- `bot_private_message`

#### 旧数据形态

旧 `history_json` 是消息数组，每个元素类似：

```json
{"role":"user","content":"[2026-04-08 13:06:38][永远|843341710]: 今天联赛第一天啊"}
```

或：

```json
{"role":"assistant","content":"好的喵～"}
```

#### 迁移规则

- `session_type='group'` 的历史写入 `bot_group_message`
- `session_type='private'` 的历史写入 `bot_private_message`
- 每个数组元素拆成一行消息
- `role` 直接复用
- `content_text` 直接存原 `content`
- `created_at` 尽量从 `content` 中的时间前缀解析，解析失败则退回当前时间或旧表更新时间
- 群消息中：
  - 从 `[时间][昵称|QQ]: 内容` 提取 `sender_nickname`、`sender_user_id`
  - `group_id` 由原 session_id 提供
- 私聊消息中：
  - `peer_user_id` 由原 session_id 提供
  - 用户消息可将 `sender_user_id = peer_user_id`
  - assistant 消息的 `sender_user_id` 可置空或写机器人 QQ
- 包含 `[回复消息 ...]` 时：
  - `is_reply = 1`
  - `quoted_text` 尽量从文本中提取
  - 旧数据一般没有稳定的被引用 message id，`quoted_platform_message_id` 可为空
- 包含 `[图片:...]` 或 `[图片：...]` 时：
  - `message_type` 标记为 `image` 或 `mixed`
- 如消息来自工具或摘要重试，可按规则设置 `tool_name` / `model_name`，旧数据没有时允许为空

#### 注意

- 旧数据不一定包含完整群昵称、发送人 QQ、平台 message id，因此新表中部分字段可能为空。
- 这是历史存量数据的天然损失，不影响后续新消息完整落库。

### 6. 摘要迁移

#### 来源

- `bot_chat_summary`
- `bot_chat_config.last_summary_version`
- `bot_chat_config.summary_cooldown_until`

#### 目标

- `bot_group_summary`
- `bot_private_summary`
- `bot_group_session_state`
- `bot_private_session_state`

#### 迁移规则

- 群摘要写入 `bot_group_summary`
- 私聊摘要写入 `bot_private_summary`
- `summary_version` 可优先使用旧的 `last_summary_version`，没有则从 1 开始
- `summary_text` 直接迁移
- `is_active = 1`
- `source_end_message_id` 在消息迁移完成后，按照当时摘要覆盖范围回填；如果无法精确回填，可先为空

## 推荐迁移顺序

### 阶段一：建新表

1. 执行新的 `schema.sql`
2. 保留旧表不动

### 阶段二：迁配置

1. 迁 `bot_ai_config` -> `bot_ai_runtime_config` / `bot_prompt_template`
2. 迁黑名单 -> `bot_blocked_group` / `bot_blocked_user`
3. 迁 `bot_chat_config` -> `bot_group_config` / `bot_private_config`

### 阶段三：迁消息

1. 扫描 `bot_chat_history`
2. 拆 JSON 数组
3. 逐条写入 `bot_group_message` / `bot_private_message`
4. 回填 `bot_group_session_state.last_message_id` / `bot_private_session_state.last_message_id`

### 阶段四：迁摘要

1. 迁 `bot_chat_summary`
2. 建立摘要版本
3. 回填会话状态中的 `summary_version` / `summary_cooldown_until`

### 阶段五：代码切换

1. 新代码改读新表
2. 运行一段时间后确认无误
3. 再考虑下线旧表读取逻辑

## 代码改造建议

### 当前需要改的仓储层

- `RuntimeConfigStore`
- `SessionStore`
- 日志同步脚本
- 摘要逻辑
- 聊天消息保存逻辑

### 重点改造点

1. 旧版 `save_history(event, history)` 要改成逐条 `insert message`
2. 旧版 `get_history(event)` 要改成按消息表查询最近 N 条并组装上下文
3. 旧版 `save_summary()` 要改成“新增摘要版本 + 更新当前激活摘要”
4. 旧版 `history_version` 不再是核心主状态，应逐步被 `last_message_id / last_summary_message_id` 替代

## 风险点

1. 旧历史消息中的 `quoted_platform_message_id` 基本无法精确还原
2. 旧 assistant 消息不一定保存了模型名
3. 旧 private 消息通常没有显式 sender QQ，只能按 session 反推
4. 若当前 `bot_ai_config` 中没有运行时配置，需从 `.env` 补齐首版数据

## 建议的落地方式

- 第一阶段只做“新表 + 迁移脚本 + 双写兼容”
- 第二阶段再彻底移除旧表依赖

这样风险最低，也最利于你后面做后台管理界面。
