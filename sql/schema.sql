-- 小喵机器人 V2 数据库结构
-- 目标：
-- 1. 用结构化字段替代 Redis 风格 KV 表
-- 2. 为运行时配置、可视化管理、热更新、消息审计、摘要增量压缩提供支撑
-- 3. 群聊与私聊分表，便于索引优化与后续归档

CREATE TABLE IF NOT EXISTS bot_ai_runtime_config (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    config_scope VARCHAR(32) NOT NULL DEFAULT 'global' COMMENT '配置作用域：global/group/private',
    scope_ref VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '作用域标识，global 默认 default',
    ai_base_url VARCHAR(255) NULL COMMENT '模型服务基础地址',
    text_model VARCHAR(128) NOT NULL COMMENT '主文本模型',
    vision_model VARCHAR(128) NOT NULL COMMENT '主视觉模型',
    text_model_fallback_json JSON NULL COMMENT '文本模型回滚列表',
    vision_model_fallback_json JSON NULL COMMENT '视觉模型回滚列表',
    enable_tools TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用工具调用',
    enable_summary_memory TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用摘要记忆',
    summary_only_group TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否只在群聊启用摘要',
    summary_trigger_rounds INT UNSIGNED NOT NULL DEFAULT 150 COMMENT '摘要触发所需历史消息条数',
    summary_keep_recent_messages INT UNSIGNED NOT NULL DEFAULT 16 COMMENT '摘要后保留的最近消息数',
    summary_cooldown_seconds INT UNSIGNED NOT NULL DEFAULT 90 COMMENT '摘要冷却秒数',
    summary_min_new_messages INT UNSIGNED NOT NULL DEFAULT 12 COMMENT '触发摘要所需最少新增消息数',
    default_reply_rate TINYINT UNSIGNED NOT NULL DEFAULT 100 COMMENT '默认回复率 0-100',
    max_history INT UNSIGNED NOT NULL DEFAULT 100 COMMENT '会话窗口最大消息条数',
    log_level VARCHAR(16) NULL COMMENT '日志级别',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否为当前生效版本',
    version INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '配置版本号',
    updated_by VARCHAR(64) NULL COMMENT '最后更新人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_runtime_scope_version (config_scope, scope_ref, version),
    KEY idx_ai_runtime_scope_active (config_scope, scope_ref, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 运行时配置表';

CREATE TABLE IF NOT EXISTS bot_prompt_template (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    prompt_type VARCHAR(32) NOT NULL COMMENT '提示词类型：base/private/at_me/group/summary_system',
    scope_type VARCHAR(16) NOT NULL DEFAULT 'global' COMMENT '提示词作用域：global/group/private',
    scope_id BIGINT NULL COMMENT '群号或用户号，global 时为空',
    title VARCHAR(128) NOT NULL COMMENT '提示词标题',
    content LONGTEXT NOT NULL COMMENT '提示词正文',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否生效',
    version INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '版本号',
    updated_by VARCHAR(64) NULL COMMENT '最后更新人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_prompt_scope_version (prompt_type, scope_type, scope_id, version),
    KEY idx_prompt_active (prompt_type, scope_type, scope_id, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='提示词模板表';

CREATE TABLE IF NOT EXISTS bot_secret_config (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    secret_key VARCHAR(64) NOT NULL COMMENT '密钥名称',
    secret_value TEXT NOT NULL COMMENT '密钥值',
    value_hint VARCHAR(255) NULL COMMENT '展示提示，不存明文时可显示掩码描述',
    is_encrypted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否加密存储',
    updated_by VARCHAR(64) NULL COMMENT '最后更新人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_secret_key (secret_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='敏感配置表';

CREATE TABLE IF NOT EXISTS bot_tool_config (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    tool_name VARCHAR(64) NOT NULL COMMENT '工具唯一标识',
    display_name VARCHAR(128) NULL COMMENT '工具显示名称',
    description TEXT NOT NULL COMMENT '工具说明',
    parameters_json JSON NULL COMMENT '工具参数 schema',
    tool_type VARCHAR(16) NOT NULL DEFAULT 'builtin' COMMENT '工具类型：builtin/http',
    method VARCHAR(16) NULL COMMENT 'HTTP 请求方法',
    url TEXT NULL COMMENT 'HTTP 工具请求地址',
    headers_json JSON NULL COMMENT 'HTTP 请求头',
    body_template TEXT NULL COMMENT 'HTTP Body 模板',
    timeout_seconds INT UNSIGNED NOT NULL DEFAULT 15 COMMENT 'HTTP 超时秒数',
    is_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_tool_name (tool_name),
    KEY idx_tool_type_enabled (tool_type, is_enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工具配置表';

CREATE TABLE IF NOT EXISTS bot_scheduled_task (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    name VARCHAR(128) NOT NULL COMMENT '任务名称',
    description TEXT NULL COMMENT '任务描述',
    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT '状态：active/paused/completed',
    schedule_type VARCHAR(16) NOT NULL COMMENT '调度类型：once/interval/cron',
    cron_expression VARCHAR(64) NULL COMMENT 'Cron 表达式',
    run_at DATETIME NULL COMMENT '一次性运行时间',
    interval_seconds INT UNSIGNED NULL COMMENT '间隔秒数',
    target_type VARCHAR(16) NOT NULL COMMENT '投递类型：group/private',
    target_ids_json JSON NOT NULL COMMENT '投递群号或QQ号列表',
    message_content TEXT NOT NULL COMMENT '投递消息内容',
    last_run_at DATETIME NULL COMMENT '上次运行时间',
    next_run_at DATETIME NULL COMMENT '下次运行时间',
    last_run_status VARCHAR(16) NULL COMMENT '上次运行结果：success/failed',
    last_error TEXT NULL COMMENT '最近一次错误信息',
    run_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计运行次数',
    created_by VARCHAR(64) NULL COMMENT '创建人',
    updated_by VARCHAR(64) NULL COMMENT '更新人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_scheduled_task_status_next (status, next_run_at),
    KEY idx_scheduled_task_target_type (target_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务表';

CREATE TABLE IF NOT EXISTS bot_admin_user (
    user_id BIGINT NOT NULL COMMENT '管理员QQ',
    nickname VARCHAR(255) NULL COMMENT '管理员昵称',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='后台管理员用户表';

CREATE TABLE IF NOT EXISTS bot_blocked_group (
    group_id BIGINT NOT NULL COMMENT '群号',
    group_name VARCHAR(255) NULL COMMENT '群名称',
    block_reason VARCHAR(255) NULL COMMENT '拉黑原因',
    created_by VARCHAR(64) NULL COMMENT '操作人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='黑名单群配置表';

CREATE TABLE IF NOT EXISTS bot_blocked_user (
    user_id BIGINT NOT NULL COMMENT '用户QQ',
    user_nickname VARCHAR(255) NULL COMMENT '用户昵称',
    block_reason VARCHAR(255) NULL COMMENT '拉黑原因',
    created_by VARCHAR(64) NULL COMMENT '操作人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='黑名单用户配置表';

CREATE TABLE IF NOT EXISTS bot_group_config (
    group_id BIGINT NOT NULL COMMENT '群号',
    group_name VARCHAR(255) NULL COMMENT '群名称',
    reply_rate TINYINT UNSIGNED NOT NULL DEFAULT 100 COMMENT '回复率 0-100',
    is_sleeping TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否睡眠',
    enable_ai TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用 AI',
    enable_summary TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用摘要',
    updated_by VARCHAR(64) NULL COMMENT '最后更新人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群聊配置表';

CREATE TABLE IF NOT EXISTS bot_private_config (
    user_id BIGINT NOT NULL COMMENT '用户QQ',
    user_nickname VARCHAR(255) NULL COMMENT '用户昵称',
    reply_rate TINYINT UNSIGNED NOT NULL DEFAULT 100 COMMENT '回复率 0-100',
    is_sleeping TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否睡眠',
    enable_ai TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用 AI',
    enable_summary TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用摘要',
    updated_by VARCHAR(64) NULL COMMENT '最后更新人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='私聊配置表';

CREATE TABLE IF NOT EXISTS bot_group_session_state (
    group_id BIGINT NOT NULL COMMENT '群号',
    last_message_id BIGINT NULL COMMENT '当前已落库的最后一条消息主键',
    last_summary_message_id BIGINT NULL COMMENT '最近一次摘要覆盖到的消息主键',
    summary_version INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '当前摘要版本',
    summary_cooldown_until DATETIME NULL COMMENT '摘要冷却截止时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群聊会话状态表';

CREATE TABLE IF NOT EXISTS bot_private_session_state (
    user_id BIGINT NOT NULL COMMENT '用户QQ',
    last_message_id BIGINT NULL COMMENT '当前已落库的最后一条消息主键',
    last_summary_message_id BIGINT NULL COMMENT '最近一次摘要覆盖到的消息主键',
    summary_version INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '当前摘要版本',
    summary_cooldown_until DATETIME NULL COMMENT '摘要冷却截止时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='私聊会话状态表';

CREATE TABLE IF NOT EXISTS bot_message_session_registry (
    session_type VARCHAR(16) NOT NULL COMMENT '会话类型：group/private',
    session_id BIGINT NOT NULL COMMENT '群号或QQ号',
    table_name VARCHAR(64) NOT NULL COMMENT '动态消息表名',
    display_name VARCHAR(255) NULL COMMENT '会话展示名',
    total_messages BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计消息数',
    last_message_id BIGINT NULL COMMENT '最新消息主键',
    last_message_at DATETIME NULL COMMENT '最新消息时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (session_type, session_id),
    UNIQUE KEY uk_message_session_table (table_name),
    KEY idx_message_session_last_time (session_type, last_message_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息分表注册表';

-- 消息表改为按会话动态创建，不再预置 bot_group_message / bot_private_message。
-- 运行时表名规则：
-- 1. 群聊：bot_group_message_<group_id>
-- 2. 私聊：bot_private_message_<user_id>
-- 表结构由应用首次写入消息时自动创建，并登记到 bot_message_session_registry。

CREATE TABLE IF NOT EXISTS bot_group_summary (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    group_id BIGINT NOT NULL COMMENT '群号',
    group_name VARCHAR(255) NULL COMMENT '群名称',
    summary_version INT UNSIGNED NOT NULL COMMENT '摘要版本',
    summary_text LONGTEXT NOT NULL COMMENT '摘要正文',
    summary_json JSON NULL COMMENT '结构化摘要，可选',
    source_start_message_id BIGINT NULL COMMENT '摘要覆盖起始消息ID',
    source_end_message_id BIGINT NULL COMMENT '摘要覆盖结束消息ID',
    source_message_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '本次摘要覆盖的消息数',
    created_by_model VARCHAR(128) NULL COMMENT '生成摘要的模型',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否为当前生效摘要',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_group_summary_version (group_id, summary_version),
    KEY idx_group_summary_active (group_id, is_active, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群聊摘要表';

CREATE TABLE IF NOT EXISTS bot_private_summary (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    peer_user_id BIGINT NOT NULL COMMENT '私聊对端用户QQ',
    peer_nickname VARCHAR(255) NULL COMMENT '私聊对端昵称',
    summary_version INT UNSIGNED NOT NULL COMMENT '摘要版本',
    summary_text LONGTEXT NOT NULL COMMENT '摘要正文',
    summary_json JSON NULL COMMENT '结构化摘要，可选',
    source_start_message_id BIGINT NULL COMMENT '摘要覆盖起始消息ID',
    source_end_message_id BIGINT NULL COMMENT '摘要覆盖结束消息ID',
    source_message_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '本次摘要覆盖的消息数',
    created_by_model VARCHAR(128) NULL COMMENT '生成摘要的模型',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否为当前生效摘要',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_private_summary_version (peer_user_id, summary_version),
    KEY idx_private_summary_active (peer_user_id, is_active, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='私聊摘要表';

CREATE TABLE IF NOT EXISTS bot_ai_call_log (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    session_type VARCHAR(16) NOT NULL COMMENT '会话类型：group/private',
    session_id BIGINT NOT NULL COMMENT '群号或用户QQ',
    message_table VARCHAR(64) NULL COMMENT '消息来源表：动态消息表名',
    message_row_id BIGINT NULL COMMENT '关联消息主键',
    stage VARCHAR(32) NOT NULL COMMENT '阶段：chat/summary/chat-tool-round/chat-fallback',
    model_name VARCHAR(128) NOT NULL COMMENT '模型名称',
    fallback_index INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '回滚层级，主模型为 0',
    allow_tools TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否启用 tools',
    failure_reason VARCHAR(32) NULL COMMENT '失败原因：rate_limit/empty_response/image_unsupported/tools_unsupported/other',
    is_success TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否成功',
    latency_ms INT UNSIGNED NULL COMMENT '耗时毫秒',
    request_excerpt VARCHAR(500) NULL COMMENT '请求摘要片段',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_ai_call_session_time (session_type, session_id, created_at),
    KEY idx_ai_call_reason_time (failure_reason, created_at),
    KEY idx_ai_call_stage_time (stage, created_at),
    KEY idx_ai_call_model_time (model_name, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 调用与回滚日志表';

CREATE TABLE IF NOT EXISTS bot_config_change_log (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    config_domain VARCHAR(32) NOT NULL COMMENT '配置域：ai_runtime/prompt/group_config/private_config/blocked_group/blocked_user/secret',
    scope_ref VARCHAR(64) NULL COMMENT '作用域标识，如 group:123 或 user:456',
    change_type VARCHAR(16) NOT NULL COMMENT '变更类型：create/update/delete',
    before_json JSON NULL COMMENT '变更前快照',
    after_json JSON NULL COMMENT '变更后快照',
    changed_by VARCHAR(64) NULL COMMENT '操作人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_config_change_domain_time (config_domain, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配置变更审计日志表';
