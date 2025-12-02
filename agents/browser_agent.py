from typing import Optional
from app.agent.toolcall import ToolCallAgent
from app.prompt.browser import SYSTEM_PROMPT as BROWSER_SYSTEM_PROMPT
# 假设你上面的 BrowserAgent 定义在 agents/browser_agent.py 或类似位置
from app.agent.browser import BrowserAgent 

# 定义专属的 Research System Prompt
# 让 Agent 知道它的任务是去访问给定的 URL 并提取信息，而不是发散搜索
MANUS_SYSTEM_PROMPT = """
You are Manus, an advanced visual research agent capable of browsing the web to extract detailed information and identify visual trends.

Your goal is to visit the URLs provided in the user's task, analyze the page content (text and visuals), and answer the user's research questions.

INSTRUCTIONS:
1. **Navigate**: Use the browser tool to visit the specific URLs provided in the task context. Do not search for new URLs unless the provided ones are broken.
2. **Analyze**: Once on a page, read the text content and look at the visual layout (the screenshots provided in the context).
3. **Extract**: Look for specific details requested by the user (e.g., "design styles", "materials", "colors").
4. **Scroll**: If the page is long, use scroll actions to see more content.
5. **Finish**: Once you have gathered enough information from the URLs, call the 'terminate' tool. Your final output must be a comprehensive summary of what you found.

IMPORTANT:
- You have vision capabilities. When you see a sofa, describe its shape, color, and material based on the screenshot.
- Focus on FACTS and VISUAL DETAILS.
"""

class _BrowerAgent(BrowserAgent):
    """
    Manus Agent: 专用于深度网页阅读和视觉分析的代理。
    它是 BrowserAgent 的特化版本。
    """
    name: str = "manus_researcher"
    description: str = "Visits specific URLs to extract textual and visual insights."
    
    # 覆盖默认的 System Prompt
    system_prompt: str = MANUS_SYSTEM_PROMPT

    # 可以适当增加步数，因为加载页面和滚动需要步骤
    max_steps: int = 30 

    async def run(self, task: str) -> str:
        """
        执行研究任务。
        :param task: 包含 URL 和具体问题的 Prompt 字符串
        :return: 研究结果总结
        """
        # 调用父类 (ToolCallAgent/BrowserAgent) 的 run 方法
        # 这会启动 think -> act -> observe 循环
        # BrowserContextHelper 会自动把截图注入到 Memory 中
        result = await super().run(task)
        
        # 任务结束后，确保浏览器资源释放（虽然 BrowserAgent.cleanup 会做，但显式确保是个好习惯）
        await self.cleanup()
        
        return result