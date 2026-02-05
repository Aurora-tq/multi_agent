import os
import time
import asyncio
from typing import List, Union
from urllib.parse import urlparse

# 引入 Crawl4AI
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
except ImportError:
    raise ImportError("Please install crawl4ai: pip install crawl4ai")

from app.logger import logger
from app.tool.base import BaseTool, ToolResult

class Crawl4aiTool(BaseTool):
    name: str = "crawl4ai"
    description: str = """
    High-performance web crawler that processes multiple URLs in PARALLEL.
    It saves the raw markdown content to a session-specific local folder 
    and returns the list of file paths.
    """

    parameters: dict = {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of URLs to crawl (e.g., ['http://site1.com', 'http://site2.com']).",
            }
        },
        "required": ["urls"],
    }

    async def execute(self, urls: Union[str, List[str]]) -> ToolResult:
        # 1. 参数归一化
        if isinstance(urls, str):
            url_list = [urls]
        else:
            url_list = urls

        if not url_list:
            return ToolResult(error="No URLs provided.")

        logger.info(f"🕷️ Starting parallel crawl for {len(url_list)} URLs...")

        # =================================================================
        # 2. 会话隔离：创建 Session 专属目录
        # =================================================================
        # 获取 Session ID，如果没有则放入 default_session
        session_id = os.environ.get("MANUS_SESSION_ID", "default_session")
        
        # 目录结构: workspace/{session_id}/raw_data/
        save_dir = os.path.join("workspace",session_id, "raw_data" ) #
        os.makedirs(save_dir, exist_ok=True)
        # =================================================================

        # 3. 配置 Crawl4AI
        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            java_script_enabled=True,
        )
        
        # run_config: 单次爬取任务的配置
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=5,
            excluded_tags=["script", "style", "nav", "footer"], # 排除干扰标签
            remove_overlay_elements=True,
            process_iframes=True,
        )

        results_summary = []
        
        # 4. 启动爬虫上下文
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                
                # 创建任务列表
                tasks = []
                for url in url_list:
                    tasks.append(crawler.arun(url=url, config=run_config))
                
                # 并发执行
                crawl_results = await asyncio.gather(*tasks, return_exceptions=True)

                # 5. 处理结果
                for i, result in enumerate(crawl_results):
                    url = url_list[i]

                    # 处理异常
                    if isinstance(result, Exception):
                        error_msg = f"❌ Error crawling {url}: {str(result)}"
                        logger.error(error_msg)
                        results_summary.append(error_msg)
                        continue

                    # 处理成功
                    if result.success:
                        try:
                            markdown_content = result.markdown or ""
                            
                            # =================================================================
                            # 新增逻辑：字数校验 (少于 500 字符则跳过)
                            # =================================================================
                            content_length = len(markdown_content)
                            if content_length < 500:
                                skip_msg = f"⏩ Skipped: {url} (Content too short: {content_length} chars)"
                                logger.info(skip_msg)
                                results_summary.append(skip_msg)
                                continue
                            # 生成文件名
                            parsed = urlparse(url)
                            domain = parsed.netloc.replace("www.", "").replace(".", "_")
                            # 取路径的一部分防止文件名重复，并限制长度
                            path_part = parsed.path.strip("/").replace("/", "_")[:50]
                            if not path_part:
                                path_part = "index"
                            
                            timestamp = int(time.time())
                            filename = f"{timestamp}_{domain}_{path_part}.md"
                            
                            # 完整路径包含 Session 子目录
                            filepath = os.path.join(save_dir, filename)

                            # 写入文件
                            content_to_save = f"<!-- Source: {url} -->\n<!-- Time: {time.ctime()} -->\n\n"
                            content_to_save += result.markdown or ""

                            with open(filepath, "w", encoding="utf-8") as f:
                                f.write(content_to_save)
                            
                            # ✅ 关键：返回的文件路径是包含 session_id 的路径
                            # 这样后续的 StructuredRetrievalTool 就能通过这个路径找到文件
                            success_msg = f"✅ Success: {url} -> Saved to '{filepath}'"
                            logger.info(success_msg)
                            results_summary.append(success_msg)

                        except Exception as e:
                            logger.error(f"Failed to save file for {url}: {e}")
                            results_summary.append(f"⚠️ Crawled {url} but failed to save file.")
                    else:
                        fail_msg = f"❌ Failed: {url} (Status: {getattr(result, 'status_code', 'Unknown')})"
                        logger.warning(fail_msg)
                        results_summary.append(fail_msg)

        except Exception as e:
            return ToolResult(error=f"Critical Crawler Error: {str(e)}")

        # 6. 返回摘要给 Agent
        final_output = "Batch Crawl Completed. Results:\n" + "\n".join(results_summary)
        
        return ToolResult(output=final_output)