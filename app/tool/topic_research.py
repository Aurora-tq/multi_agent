import json
import re
from typing import List, Dict
from pydantic import Field

from app.tool.base import BaseTool, ToolResult
from app.llm import LLM
from app.logger import logger
from app.tool.web_search import WebSearch

class TopicResearchTool(BaseTool):
    name: str = "topic_research"
    description: str = """
    Uses an LLM with search capabilities to generate an initial research summary and, most importantly, 
    generate a list of high-quality reference URLs for further deep scraping.
    """
    parameters: dict = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The research topic or user query."
            }
        },
        "required": ["topic"]
    }

    llm: LLM = Field(default_factory=LLM, exclude=True)
    # 我们依然需要给 LLM 一个搜索工具，让它能联网查到链接
    search_tool: WebSearch = Field(default_factory=WebSearch, exclude=True)

    async def execute(self, topic: str) -> ToolResult:
        logger.info(f"🧠 Researching topic: {topic}")

        # 1. 先让搜索工具跑一次，获取原始素材给 LLM
        # 注意：如果你的 LLM (如 Gemini Pro) 原生自带联网，可以跳过这一步直接问。
        # 但为了通用性，我们这里先手动搜一下，把上下文喂给 LLM。
        search_result = await self.search_tool.execute(query=topic, num_results=10)
        
        # 2. 构建 Prompt，强制 LLM 输出 JSON 格式的链接列表
        prompt = f"""
        You are an expert researcher.
        I have a topic: "{topic}".
        
        Here are some search results I found:
        {search_result.output}

        **YOUR TASKS:**
        1. Analyze the search results and identify the 10-15 BEST articles that contain rich details (images, trends, data).
        2. Briefly explain why these articles are relevant.
        3. **CRITICAL**: Output the exact URLs of these best articles in a strict JSON list format at the very end.

        **OUTPUT FORMAT:**
        [Analysis text...]

        URL_LIST_START
        ["https://best-site.com/article1", "https://another-site.com/article2"]
        URL_LIST_END
        """

        # 3. 询问 LLM
        messages = [
            {"role": "user", "content": prompt}
        ]
        response = await self.llm.ask(messages)
        
        # 4. 提取链接 (Regex)
        urls = []
        try:
            # 匹配 URL_LIST_START 和 URL_LIST_END 中间的内容
            match = re.search(r'URL_LIST_START(.*?)URL_LIST_END', response, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                # 清理可能的 markdown 代码块标记
                json_str = json_str.replace("```json", "").replace("```", "")
                urls = json.loads(json_str)
            else:
                # 备用方案：尝试找任何看起来像 JSON 列表的东西
                match = re.search(r'\[\s*".*?"\s*\]', response, re.DOTALL)
                if match:
                    urls = json.loads(match.group(0))
        except Exception as e:
            logger.error(f"Failed to parse URLs from LLM response: {e}")
            logger.debug(f"LLM Response was: {response}")

        if not urls:
            return ToolResult(error="LLM analyzed the topic but failed to return a valid JSON list of URLs.")

        logger.info(f"✅ LLM generated {len(urls)} target URLs: {urls}")
        
        # 直接返回 URL 列表的 JSON 字符串，方便 SmartScraper 读取
        return ToolResult(output=json.dumps(urls))
    
