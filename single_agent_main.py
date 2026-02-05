import asyncio
import os
import time
import uuid
import nest_asyncio
from agents.manus_agent import Manus  # 导入你刚刚重新定义的 Manus 类
from app.logger import logger

# 应用 nest_asyncio patch (保留它以防 BrowserUseTool 需要嵌套循环)
nest_asyncio.apply()

# 设置代理 (如果需要爬取国外网站，保持开启)
os.environ["http_proxy"] = "http://127.0.0.1:7897"
os.environ["https_proxy"] = "http://127.0.0.1:7897"
os.environ["all_proxy"] = "http://127.0.0.1:7897"

# ==========================================
# 🔥 生成本次运行的唯一会话 ID
# 这样每次运行脚本，都会产生一个新的 ID，数据文件也会是新的
# ==========================================
session_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:4]}"
os.environ["MANUS_SESSION_ID"] = session_id
print(f"🚀 Current Session ID: {session_id}")
# ==========================================
async def main():
    print("==========================================================")
    print("   OpenManus-RAG Autonomous Agent (All-in-One)   ")
    print("==========================================================")

    user_query = """
    I want to design a mid-range sofa. Which models have been selling well recently?
    """
  
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
