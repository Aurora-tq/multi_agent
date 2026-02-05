from app.tool import BaseTool


class AskHuman(BaseTool):
    """Add a tool to ask human for help."""

    name: str = "ask_human"
    description: str = "Use this tool to ask human for help."
    parameters: str = {
        "type": "object",
        "properties": {
            "inquire": {
                "type": "string",
                "description": "The question you want to ask human.",
            }
        },
        "required": ["inquire"],
    }

    async def execute(self, inquire: str) -> str:
        return input(f"""Bot: {inquire}\n\nYou: """).strip()


# from app.tool import BaseTool
# from app.logger import logger  # 建议引入 logger 以便记录 Agent 问了什么

# class AskHuman(BaseTool):
#     """Add a tool to ask human for help."""

#     name: str = "ask_human"
#     description: str = "Use this tool to ask human for help."
#     parameters: dict = {  # 注意：这里类型应该是 dict
#         "type": "object",
#         "properties": {
#             "inquire": {
#                 "type": "string",
#                 "description": "The question you want to ask human.",
#             }
#         },
#         "required": ["inquire"],
#     }

#     async def execute(self, inquire: str) -> str:
#         # ✅ Benchmark 专用修改版（自动回复）：
        
#         # 1. 在后台记录 Agent 想问什么，方便后续分析它的决策路径
#         logger.warning(f"🤖 [Auto-Reply Triggered] Agent asked: {inquire}")
        
#         # 2. 返回一个“万能”的授权指令，迫使 Agent 自行决策
#         # 这个回复的核心目的是告诉 Agent：“我不提供额外信息，你按你的判断继续。”
#         mock_response = (
#             "User is currently unavailable. "
#             "Please proceed based on your own professional judgment. "
#             "You may assume a common or popular context (e.g., Modern style, Standard size) if specific details are missing."
#         )
        
#         print(f"Bot: {inquire}\n(Auto-System): {mock_response}")
#         return mock_response
