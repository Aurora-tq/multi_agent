import os
import yaml
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI, ChatOpenAI
# 引入 Google GenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# 加载环境变量
load_dotenv()

CONFIG_FILE = "gpt_config.yaml"

def load_config(path: str = CONFIG_FILE) -> dict:
    """加载 YAML 配置文件"""
    if not os.path.exists(path):
        # print(f"警告: 配置文件 {path} 未找到，将仅依赖环境变量。")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_llm_instance(config_path: str = CONFIG_FILE):
    """根据配置文件或环境变量工厂模式生产 LLM 实例"""
    config = load_config(config_path)
    
    # 获取 agent_type，默认为 'openai'
    agent_type = config.get("agent_type", "gemini") 
    agent_config = config.get(agent_type, {}) if agent_type else {}

    # --- 分支 1: Google Gemini ---
    if agent_type == "gemini":
        google_api_key = os.environ.get("GOOGLE_API_KEY", agent_config.get("api_key"))
        model_name = os.environ.get("MODEL_NAME", agent_config.get("model_name", "gemini-2.0-flash"))
        
        if not google_api_key:
            raise ValueError("使用 Gemini 需要设置 GOOGLE_API_KEY 环境变量")

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=google_api_key,
            temperature=0.1,
            convert_system_message_to_human=True, # 有助于兼容性
            # 注意：千万不要在这里全局强制 response_mime_type="application/json"
            # 否则 Reporter Agent 无法生成 Markdown 报告
        )
        return llm

    # --- 分支 2: OpenAI / Azure (保留原有逻辑) ---
    else:
        endpoint = os.environ.get("ENDPOINT", agent_config.get("endpoint"))
        api_key = os.environ.get("API_KEY", agent_config.get("api_key"))
        api_version = os.environ.get("API_VERSION", agent_config.get("api_version"))
        model_name = os.environ.get("MODEL_NAME", agent_config.get("model_name"))

        if not api_key:
            raise ValueError(f"未找到 API_KEY，请检查环境变量 .env 或 {config_path}")

        print(f"--- Loading: {agent_type} ({model_name}) ---")

        if api_version:
            return AzureChatOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
                azure_deployment=model_name,
                temperature=0.1,
                max_tokens=4000
            )
        else:
            return ChatOpenAI(
                base_url=endpoint,
                api_key=api_key,
                model=model_name,
                temperature=0.1,
                max_tokens=4000
            )