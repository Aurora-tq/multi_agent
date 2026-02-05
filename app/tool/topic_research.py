import asyncio
import json
import os
from datetime import datetime, timezone
import time
from typing import List, Set,Dict
from pydantic import Field
from tavily import TavilyClient
from urllib.parse import urlparse
from app.logger import logger

# 引入你的项目依赖
from app.tool.base import BaseTool, ToolResult
from app.llm import LLM
from app.schema import Message  # 确保引入 Message 以防报错

class TopicResearchTool(BaseTool):
    name: str = "topic_research"
    description: str = """
    Deep research tool using Tavily API.
    1. Analyzes user topic and generates 3-5 professional search queries using LLM.
    2. Executes these searches in parallel via Tavily to get high-quality results.
    3. Returns a deduplicated list of relevant URLs.
    """
    
    parameters: dict = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The user's research topic (e.g., '2025 sofa design trends')."
            },
            "max_urls": {
                "type": "integer",
                "description": "Max number of unique URLs to return.",
                "default": 15
            }
        },
        "required": ["topic"]
    }

    llm: LLM = Field(default_factory=LLM, exclude=True)
    
    _tavily_client: TavilyClient = None

    def __init__(self, **data):
        super().__init__(**data)
        api_key = os.getenv("TAVILY_API_KEY") 
        self._tavily_client = TavilyClient(api_key=api_key)

    async def execute(self, topic: str, max_urls: int = 20) -> ToolResult:
        logger.info(f"🧠 Brainstorming search queries for: '{topic}'")

        # 1. 使用 LLM 生成 3-5 个多维度搜索词
        queries = await self._generate_smart_queries(topic)
        
        if not queries:
            logger.warning("LLM failed to generate queries, falling back to simple search.")
            queries = [topic, f"{topic} trends 2025"]

        logger.info(f"🔎 Executing Tavily searches for: {queries}")

        # 2. 并行执行搜索 (Tavily Search)
        # Tavily SDK 是同步的，我们需要用 asyncio.to_thread 把它变成异步非阻塞，否则会卡住 Agent
        search_tasks = []
        for q in queries:
            search_tasks.append(self._perform_tavily_search(q))
        

        # 等待所有搜索完成
        search_results_list = await asyncio.gather(*search_tasks, return_exceptions=True)
       
        # 3. 结果聚合与去重
        seen_urls: Set[str] = set()
        final_results = []
        
        for batch_results in search_results_list:
            if isinstance(batch_results, Exception):
                logger.error(f"A search task failed: {batch_results}")
                continue
            
            # batch_results 是 Tavily 返回的 'results' 列表
            for item in batch_results:
                url = item.get('url')
                title = item.get('title', 'No Title')
                
                if url and url not in seen_urls:
                    if self._is_valid_url(url):
                        seen_urls.add(url)
                        # 暂时只存 URL，如果 Agent 需要 Title 可以把这里改成 dict
                        final_results.append(url)

        # 4. 截断结果
        selected_urls = final_results[:max_urls]
        logger.info(f"total length:{len(final_results)} ✅ Found {len(selected_urls)} unique high-quality URLs.")

        # 返回 JSON 格式的 URL 列表
        return ToolResult(output=json.dumps(selected_urls))

    async def _perform_tavily_search(self, query: str) -> List[dict]:
        """
        在线程池中运行 Tavily 搜索，避免阻塞异步循环
        每个关键词固定返回5个高质量URL，保证结果数量且后续易去重
        """
        def search_sync():
            try:
                response = self._tavily_client.search(
                    query=query,
                    search_depth="advanced",  # 使用高级搜索深度
                    max_results=5,            # 每个query仅取前5个（精准控制数量）
                    include_answer=False,
                    include_raw_content=False,
                    include_images=False,
                    # 可选：添加时间范围，匹配你之前的时间戳需求
                    # start_date=self.search_start_date,
                    # end_date=self.search_end_date,
                    # include_domains=[
                    #     "taobao.com", "tmall.com", "ikea.com",
                    #     "wgsn.com", "minotti.com", "xiaohongshu.com", "tiktok.com"
                    # ],
                )
                # 对单query的3个结果做基础清洗（过滤无效URL）
                raw_results = response.get('results', [])
                cleaned_results = []
                for res in raw_results:
                    url = res.get('url', '').strip()
                    if url and url.startswith(('http://', 'https://')):  # 过滤无效URL
                        cleaned_results.append(res)
                # 不足3个时补充空结果（保证数量，后续汇总时自动过滤）
                return cleaned_results[:3]
            except Exception as e:
                logger.error(f"Tavily search error for query '{query}': {e}")
                return []

        # 使用 asyncio.to_thread (Python 3.9+)
        return await asyncio.to_thread(search_sync)
    async def _generate_smart_queries(self, topic: str, timestamp: float = None) -> List[str]:
        """
        让 LLM 生成 3-5 个高质量搜索词（带时间戳，确保搜索词时效性）
        :param topic: 核心调研主题
        :param timestamp: 时间戳（秒级），若不传则使用当前时间
        :return: 3-5个时效性搜索词列表
        """
        # 处理时间戳：默认用当前时间，转换为易读的年份/年月格式
        if timestamp is None:
            timestamp = time.time()
        # 转换时间戳为 "YYYY" 和 "YYYY-MM" 格式（适配搜索词场景）
        search_year = datetime.fromtimestamp(timestamp).strftime("%Y")
        search_month = datetime.fromtimestamp(timestamp).strftime("%Y-%m")

        prompt = f"""
        You are an expert Market Researcher and SEO Specialist.
        Your goal is to generate **3 to 5 highly distinct** search queries to maximize information coverage for the topic: "{topic}".
        
        **Time Context:**
        - Research Target Time: {search_month} (Year: {search_year})
        - Timestamp: {int(timestamp)}
        - **Constraint:** ALL queries must explicitly include time markers like "{search_year}", "{search_month}", or "Q{int((datetime.now().month-1)/3)+1} {search_year}".

        **Strategic Dimensions (Generate distinct queries for each dimension):**
        1.  **Quantitative/Sales Data:** Bestseller lists, market share statistics, sales volume rankings (e.g., "top selling mid-range sofas {search_year} statistics").
        2.  **Qualitative/Design Trends:** Aesthetic evolution, colors, materials, shapes (e.g., "trending sofa fabric types {search_year}", "living room furniture color trends {search_year}").
        3.  **Industry Authority:** Professional forecasts, trade shows (e.g., Milan Design Week), wgsn reports (e.g., "furniture industry market analysis report {search_year}").
        4.  **Platform/Competitor Specific:** Specific retailer data (e.g., "IKEA vs Wayfair sofa sales {search_year}", "Amazon furniture best sellers {search_month}").

        **Strict Requirements:**
        - **Maximize Semantic Distance:** Do NOT generate synonymous queries (e.g., do not output both "best sofas" and "top rated sofas").
        - **Focus on Diversity:** Ensure the list covers at least 4 of the 5 dimensions above.
        - Return ONLY a raw JSON list of strings. No markdown formatting.
        - Example Output: ["{search_year} mid-range sofa market share", "trending velvet sofa colors {search_year}", "best sofa for back pain reviews {search_year}", "IKEA 2025 catalog living room", "sofa industry supply chain trends {search_year}"]
        """
        
        try:
            # 构造 Message 对象
            messages = [
                Message(role="user", content=prompt)
            ]
            response = await self.llm.ask(messages)
            
            # 清洗响应内容
            cleaned_response = response.replace("```json", "").replace("```", "").strip()
            queries = json.loads(cleaned_response)
            
            return queries
        except Exception as e:
            logger.error(f"Error generating queries with LLM: {e}")
            # 异常时返回带时间的兜底搜索词
            return [f"{search_year} {topic}"]

    def _is_valid_url(self, url: str) -> bool:
        """简单的 URL 过滤器"""
        # 排除文件类型
        skip_extensions = ('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xml', '.json', '.jpg', '.png')
       
        url_lower = url.lower()
        if url_lower.endswith(skip_extensions):
            return False
        return True
    