"""Localized names and descriptions for common MCP tools."""

from __future__ import annotations


MCP_TOOL_TEXT: dict[str, dict[str, dict[str, str]]] = {
    "thinking": {
        "sequentialthinking": {
            "display_name": "步骤思考",
            "description": (
                "把复杂问题拆成多步思考，支持修正、分支、继续补充和不确定性记录；"
                "适合规划、排查、分析方案和需要多轮推理的任务。"
            ),
        },
    },
    "memory": {
        "create_entities": {
            "display_name": "创建记忆实体",
            "description": "在长期记忆图谱中创建人物、项目、概念等实体，并记录实体类型和基础信息。",
        },
        "create_relations": {
            "display_name": "创建记忆关系",
            "description": "在两个记忆实体之间创建有向关系，用来表达归属、偏好、负责、关联等联系。",
        },
        "add_observations": {
            "display_name": "追加记忆观察",
            "description": "给已有实体追加新的事实、偏好、事件或备注，作为长期记忆的一部分。",
        },
        "delete_entities": {
            "display_name": "删除记忆实体",
            "description": "从长期记忆图谱中删除指定实体，并清理与这些实体相关的关系。",
        },
        "delete_observations": {
            "display_name": "删除记忆观察",
            "description": "删除指定实体下不再需要或不准确的观察记录。",
        },
        "delete_relations": {
            "display_name": "删除记忆关系",
            "description": "删除两个实体之间指定的关系，不删除实体本身。",
        },
        "read_graph": {
            "display_name": "读取记忆图谱",
            "description": "读取当前长期记忆图谱中的实体、关系和观察记录。",
        },
        "search_nodes": {
            "display_name": "搜索记忆节点",
            "description": "按关键词搜索长期记忆中的实体和观察记录，用于查找相关上下文。",
        },
        "open_nodes": {
            "display_name": "打开记忆节点",
            "description": "按实体名称读取指定记忆节点的详细内容和相关关系。",
        },
    },
    "filesystem": {
        "read_file": {"display_name": "读取文件", "description": "读取允许目录内指定文件的文本内容。"},
        "read_text_file": {"display_name": "读取文本文件", "description": "读取允许目录内指定文本文件的内容。"},
        "read_media_file": {"display_name": "读取媒体文件", "description": "读取允许目录内图片、音频等媒体文件的内容或元信息。"},
        "read_multiple_files": {"display_name": "批量读取文件", "description": "一次读取多个允许目录内文件的内容。"},
        "write_file": {"display_name": "写入文件", "description": "向允许目录内的指定文件写入内容，会覆盖原有文件。"},
        "edit_file": {"display_name": "编辑文件", "description": "按差异或片段修改允许目录内的指定文件。"},
        "create_directory": {"display_name": "创建目录", "description": "在允许目录内创建新的文件夹，必要时会创建上级目录。"},
        "list_directory": {"display_name": "列出目录", "description": "列出允许目录内指定文件夹的文件和子目录。"},
        "list_directory_with_sizes": {
            "display_name": "目录大小列表",
            "description": "列出允许目录内指定文件夹的文件、子目录和对应大小。",
        },
        "directory_tree": {"display_name": "目录树", "description": "以树形结构查看允许目录内指定文件夹的层级内容。"},
        "move_file": {"display_name": "移动文件", "description": "在允许目录内移动或重命名文件、文件夹。"},
        "search_files": {"display_name": "搜索文件", "description": "在允许目录内按名称或模式搜索文件。"},
        "get_file_info": {"display_name": "文件信息", "description": "查看允许目录内文件或目录的大小、时间、类型等元信息。"},
        "list_allowed_directories": {"display_name": "允许目录", "description": "查看当前文件系统 MCP 被允许访问的目录列表。"},
    },
    "git": {
        "git_status": {"display_name": "Git 状态", "description": "查看仓库当前分支、暂存区和工作区改动状态。"},
        "git_diff_unstaged": {"display_name": "未暂存差异", "description": "查看工作区尚未暂存的代码差异。"},
        "git_diff_staged": {"display_name": "已暂存差异", "description": "查看已经加入暂存区、准备提交的代码差异。"},
        "git_diff": {"display_name": "Git 差异", "description": "查看指定文件、提交或分支之间的代码差异。"},
        "git_commit": {"display_name": "提交代码", "description": "使用指定提交信息创建一次 Git commit。"},
        "git_add": {"display_name": "加入暂存区", "description": "把指定文件加入 Git 暂存区。"},
        "git_reset": {"display_name": "取消暂存", "description": "把指定文件从暂存区移回工作区，不删除文件内容。"},
        "git_log": {"display_name": "提交历史", "description": "查看仓库最近的提交记录。"},
        "git_create_branch": {"display_name": "创建分支", "description": "基于当前提交创建新的 Git 分支。"},
        "git_checkout": {"display_name": "切换分支", "description": "切换到指定分支或提交。"},
        "git_show": {"display_name": "查看提交", "description": "查看指定提交、标签或对象的详细内容。"},
        "git_init": {"display_name": "初始化仓库", "description": "在指定目录初始化 Git 仓库。"},
    },
}


def localize_mcp_tool(server_name: str, original_tool_name: str, description: str = "") -> dict[str, str]:
    """Return a Chinese display name and description when the MCP tool is known."""
    server = str(server_name or "").strip()
    tool = str(original_tool_name or "").strip()
    localized = MCP_TOOL_TEXT.get(server, {}).get(tool)
    if localized:
        return {
            "display_name": localized["display_name"],
            "description": localized["description"],
        }
    return {
        "display_name": tool,
        "description": f"第三方 MCP 工具，来自 {server or '未知'} 服务；可在后台工具缓存中补充更准确的中文说明。",
    }
