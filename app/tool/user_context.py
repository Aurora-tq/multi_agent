# tool/user_context.py
from typing import Dict, List, Literal, Optional, Any

from app.exceptions import ToolError
from app.tool.base import BaseTool, ToolResult

_USER_CONTEXT_DESCRIPTION = """
一个用户初始化与偏好管理工具。
用于设定和管理设计任务的初始参数，包括设计类型、风格、价格区间、颜色倾向等个性化模板。
这些信息将作为后续设计趋势分析和报告生成的上下文基础。
"""

class UserContextTool(BaseTool):
    """
    用户初始化与偏好管理工具。
    支持创建、更新、获取和清除用户的设计偏好模板。
    """

    name: str = "user_context"
    description: str = _USER_CONTEXT_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "description": "执行的命令。可用命令：set (设置/初始化), update (更新部分参数), get (获取当前配置), clear (重置)。",
                "enum": ["set", "update", "get", "clear"],
                "type": "string",
            },
            "design_type": {
                "description": "设计类型，例如：平面设计、UI/UX、室内设计、工业产品等。",
                "type": "string",
            },
            "style_preference": {
                "description": "设计风格倾向，例如：极简主义、赛博朋克、孟菲斯风格、包豪斯等。",
                "type": "string",
            },
            "budget_range": {
                "description": "价格/预算区间（字符串描述）。",
                "type": "string",
            },
            "color_palette": {
                "description": "颜色倾向或色系要求。",
                "type": "array",
                "items": {"type": "string"},
            },
            "target_audience": {
                "description": "目标受众群体描述。",
                "type": "string",
            },
            "extra_requirements": {
                "description": "其他补充的个性化要求。",
                "type": "string",
            }
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    # 用于存储当前的上下文信息
    _context: Dict[str, Any] = {}

    async def execute(
        self,
        *,
        command: Literal["set", "update", "get", "clear"],
        design_type: Optional[str] = None,
        style_preference: Optional[str] = None,
        budget_range: Optional[str] = None,
        color_palette: Optional[List[str]] = None,
        target_audience: Optional[str] = None,
        extra_requirements: Optional[str] = None,
        **kwargs,
    ):
        if command == "set":
            return self._set_context(
                design_type, style_preference, budget_range, color_palette, target_audience, extra_requirements
            )
        elif command == "update":
            return self._update_context(
                design_type, style_preference, budget_range, color_palette, target_audience, extra_requirements
            )
        elif command == "get":
            return self._get_context()
        elif command == "clear":
            return self._clear_context()
        else:
            raise ToolError(f"不支持的命令: {command}")

    def _set_context(self, d_type, style, budget, colors, audience, extra) -> ToolResult:
        """完全初始化上下文"""
        # 校验必要参数（可根据实际需求调整哪些是必填的）
        if not d_type:
            raise ToolError("命令 'set' 需要提供 'design_type' 参数。")

        self._context = {
            "design_type": d_type,
            "style_preference": style or "未设定",
            "budget_range": budget or "未设定",
            "color_palette": colors or [],
            "target_audience": audience or "通用",
            "extra_requirements": extra or "无",
        }
        return ToolResult(output=f"用户初始化模板设置成功：\n{self._format_context()}")

    def _update_context(self, d_type, style, budget, colors, audience, extra) -> ToolResult:
        """增量更新上下文"""
        if not self._context:
            raise ToolError("尚未初始化模板，请先使用 'set' 命令。")

        if d_type: self._context["design_type"] = d_type
        if style: self._context["style_preference"] = style
        if budget: self._context["budget_range"] = budget
        if colors: self._context["color_palette"] = colors
        if audience: self._context["target_audience"] = audience
        if extra: self._context["extra_requirements"] = extra

        return ToolResult(output=f"用户偏好已更新：\n{self._format_context()}")

    # def _get_context(self) -> ToolResult:
    #     """查看当前配置"""
    #     if not self._context:
    #         return ToolResult(output="当前没有已配置的个性化模板。")
    #     return ToolResult(output=self._format_context())

    def _clear_context(self) -> ToolResult:
        """清空配置"""
        self._context = {}
        return ToolResult(output="用户个性化模板已清空。")


    def _get_context(self) -> ToolResult:
        """查看当前配置，并识别缺失的必要项"""
        if not self._context:
            return ToolResult(output="[Missing Info] 您尚未设置个性化模板。请提供：设计类型、风格偏好、颜色倾向等。")
        
        # 定义核心必要字段
        required_fields = {
            "design_type": "设计类型",
            "style_preference": "风格偏好"
        }
        missing = [v for k, v in required_fields.items() if not self._context.get(k) or self._context.get(k) == "未设定"]
        
        formatted = self._format_context()
        if missing:
            return ToolResult(output=f"{formatted}\n\n⚠️ 尚缺关键信息: {', '.join(missing)}。请补充这些信息以获得更精准的分析。")
        return ToolResult(output=formatted)
    def _format_context(self) -> str:
        """格式化输出内容"""
        ctx = self._context
        palette = ", ".join(ctx.get("color_palette", [])) or "未指定"
        
        output = [
            f"--- 👤 DesignAgent 用户个性化配置 ---",
            f"🎯 设计类型: {ctx.get('design_type')}",
            f"🎨 风格偏好: {ctx.get('style_preference')}",
            f"💰 价格区间: {ctx.get('budget_range')}",
            f"🌈 颜色倾向: {palette}",
            f"👥 目标受众: {ctx.get('target_audience')}",
            f"📝 额外需求: {ctx.get('extra_requirements')}",
            f"------------------------------------"
        ]
        return "\n".join(output)