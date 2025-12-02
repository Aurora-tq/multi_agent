import asyncio
from typing import List, Dict, Any, Union
from app.tool.base import BaseTool, ToolResult
from app.tool.crawl4ai import Crawl4aiTool
from app.tool.browser_use_tool import BrowserUseTool
from app.logger import logger

class SmartScraperTool(BaseTool):
    """
    A smart scraper that attempts to fetch content using a waterfall strategy:
    1. Try Crawl4AI (Fast, Headerless)
    2. If failed/empty, fallback to BrowserUse (Full Browser, Slow, Anti-detection)
    """
    name: str = "smart_scraper"
    description: str = """
    Intelligently scrapes content from a list of URLs.
    It first tries a fast crawler. If the website blocks it or returns empty content, 
    it automatically falls back to a full browser simulation to extract the data.
    Use this for reading blog posts, news articles, or documentation.
    """
    
    parameters: dict = {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of URLs to scrape.",
            },
            "instruction": {
                "type": "string",
                "description": "Specific instruction for what to extract (used if fallback to browser is needed).",
                "default": "Extract the main content, including title, body text, and key images."
            }
        },
        "required": ["urls"]
    }

    # 内部持有两个工具
    crawler: Crawl4aiTool = Crawl4aiTool()
    browser_tool: BrowserUseTool = BrowserUseTool()

    async def execute(self, urls: List[str], instruction: str = "Extract main content") -> ToolResult:
        results = []
        
        for url in urls:
            logger.info(f"🚀 SmartScraper processing: {url}")
            
            # --- 阶段 1: 尝试 Crawl4AI (快) ---
            scrape_success = False
            content_data = None
            
            try:
                # 使用 bypass_cache=True 确保拿到最新数据
                crawl_result = await self.crawler.execute(urls=[url], bypass_cache=True)
                
                # 检查爬取结果是否有效
                # Crawl4AI 返回的是格式化后的字符串，我们需要判断里面是否包含有效信息
                # 这里做一个简单的启发式判断：如果没有 Markdown 内容或者内容太短，视为失败
                if "Markdown: None" not in crawl_result.output and "Success (HTTP 200)" in crawl_result.output:
                    # 进一步检查内容长度
                    # 这是一个简化的检查，实际可以解析 output 字符串
                    if len(crawl_result.output) > 500: 
                        logger.info(f"✅ Crawl4AI success for {url}")
                        results.append(f"Source: {url} (via Crawler)\n{crawl_result.output}")
                        scrape_success = True
                    else:
                        logger.warning(f"⚠️ Crawl4AI returned too little data for {url}")
                else:
                    logger.warning(f"⚠️ Crawl4AI failed status check for {url}")
                    
            except Exception as e:
                logger.error(f"❌ Crawl4AI error for {url}: {e}")

            # --- 阶段 2: 降级到 BrowserUse (慢但稳) ---
            if not scrape_success:
                logger.info(f"🔄 Falling back to BrowserUse for {url}")
                try:
                    # 1. 导航
                    await self.browser_tool.execute(action="go_to_url", url=url)
                    
                    # 2. 提取 (使用我们优化过的支持多模态的提取逻辑)
                    extract_result = await self.browser_tool.execute(
                        action="extract_content", 
                        goal=instruction
                    )
                    
                    if not extract_result.error:
                        results.append(f"Source: {url} (via Browser)\n{extract_result.output}")
                        logger.info(f"✅ BrowserUse success for {url}")
                    else:
                        results.append(f"❌ Failed to scrape {url}: {extract_result.error}")
                        
                except Exception as e:
                    logger.error(f"❌ BrowserUse error for {url}: {e}")
                    results.append(f"❌ Critical error scraping {url}: {str(e)}")

        return ToolResult(output="\n\n".join(results))