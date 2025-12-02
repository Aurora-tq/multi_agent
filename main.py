import asyncio
import os
import nest_asyncio
from agents.manus_agent import Manus  # 导入你刚刚重新定义的 Manus 类
from app.logger import logger

# 应用 nest_asyncio patch (保留它以防 BrowserUseTool 需要嵌套循环)
nest_asyncio.apply()

# 设置代理 (如果需要爬取国外网站，保持开启)
os.environ["http_proxy"] = "http://127.0.0.1:7897"
os.environ["https_proxy"] = "http://127.0.0.1:7897"
os.environ["all_proxy"] = "http://127.0.0.1:7897"

async def main():
    print("==========================================================")
    print("   OpenManus-RAG Autonomous Agent (All-in-One)   ")
    print("==========================================================")

    user_query = """
    我想设计一款沙发，请帮我调研现在最火的款式是什么？
    """
    #  请按照以下步骤执行：
    # 1. 使用 Planning 工具制定一个调研计划。
    # 2. 使用 Crawl4AI 或 Browser 工具广泛搜集。
    # 3. 整理收集到的数据。
    # 4. 最后，请撰写一份详细的 Markdown 报告，保存为文件 "Sofa_Design_Trend_Report.md"。
    
    print(f"\n[Task] 用户指令: {user_query}")
    print("\n--- Manus Agent 启动中 (初始化工具与 MCP) ---")

    # 2. 初始化 Manus 智能体
    # 使用 create 工厂方法，确保 MCP 和工具正确连接
    agent = await Manus.create()

    try:
        print("\n--- Agent 开始自主思考与执行 ---")
        await agent.run(user_query)
        
        print("\n[Success] Manus 任务执行完毕！请检查生成的报告文件。")

    except Exception as e:
        logger.error(f"任务执行过程中发生错误: {e}")
    finally:
        # 4. 清理资源 (关闭浏览器、断开 MCP 连接)
        await agent.cleanup()

if __name__ == "__main__":
    asyncio.run(main())