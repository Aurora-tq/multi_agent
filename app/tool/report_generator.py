#单线代码
import os
import json
import re

from pydantic import Field
from app.tool.base import BaseTool, ToolResult
from app.llm import LLM
from app.logger import logger
from app.schema import Message


class ReportGeneratorTool(BaseTool):
    name: str = "report_generator"
    description: str = """
    Generates a final, visually rich market report.
    It combines data analysis with automatic local image embedding.
    No separate post-processing tool is needed.
    """

    parameters: dict = {
        "type": "object",
        "properties": {
            "report_topic": {
                "type": "string",
                "description": "The main topic of the report (e.g., '2025 Sofa Design Trends')."
            },
            "language": {
                "type": "string",
                "description": "The output language (default: English).",
                "default": "English"
            }
        },
        "required": ["report_topic"]
    }

    llm: LLM = Field(default_factory=LLM, exclude=True)

    async def execute(self, report_topic: str, language: str = "English") -> ToolResult:
        logger.info(f"📝 Generating final report for: {report_topic}")

        # =================================================================
        # 1. 加载数据
        # =================================================================
        session_id = os.environ.get("MANUS_SESSION_ID", "default_session")

        data_dir = f"workspace/{session_id}/structured_data"
        candidates = [
            f"{data_dir}/combined_data_{session_id}.json",
            # f"{data_dir}/data_{session_id}.json"
        ]

        data_list = []

        for path in candidates:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                        data_list = raw.get("data", raw) if isinstance(raw, dict) else raw
                        break
                except Exception:
                    continue

        if not data_list:
            return ToolResult(error=f"No structured data found for session '{session_id}'. Run extraction first.")

        collected_data_str = json.dumps(data_list, ensure_ascii=False, indent=2)  # [:60000]

        # =================================================================
        # 2. 生成报告 (LLM 阶段)
        # =================================================================
        system_prompt = f"""
You are a professional design trend analyst. Generate a Markdown report based on the user's topic and the provided input data.

**Requirements:**
1. **MECE Principle**: Content must be mutually exclusive and collectively exhaustive, with clear structure and logic.

2. **Visual-Rich (Strict image rules)**:
   - Treat an image as a “web URL image” **ONLY if it starts with `https://`**. In that case, you MUST embed it using Markdown image syntax: `![alt](url)`, placed adjacent to the most relevant paragraph.
   - Do NOT group all images at the end; insert them inline where they are most relevant.

3. **Must Cite Sources**: Every key insight must end with a citation `[Website Name](url)`. e.g. "[Homes & Gardens](https://www.homesandgardens.com/interior-design/living-rooms/sofa-trends-for-2026)"

4. **Formatting**: Use Markdown headings; LaTeX formulas allowed; preserve tables.

5. **Start Directly**: Begin with the report title. No greetings or introductory filler.

6. **Length**: Write a **long, detailed report** with as much depth as the input supports (prioritize completeness over brevity; avoid fluff).

**Output Language**: {language}
"""

        user_prompt = f"""
**Topic**: {report_topic}

**Input Data**:
{collected_data_str}
"""

        try:
            report_content = await self.llm.ask([
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt)
            ])

            # 简单清洗
            if report_content:
                report_content = report_content.replace("```markdown", "").replace("```", "").strip()

            # =================================================================
            # 3. 保存最终文件（不再做 resource_map 注入/替换）
            # =================================================================
            output_dir = f"workspace/{session_id}/reports"
            if not os.path.exists(f"workspace/{session_id}"):
                output_dir = "reports"

            os.makedirs(output_dir, exist_ok=True)

            safe_topic = re.sub(r'[\\/*?:"<>|]', "", report_topic.replace(" ", "_"))
            filename = f"{output_dir}/{safe_topic}.md"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(report_content)

            logger.info(f"💾 Final report saved to: {filename}")
            return ToolResult(output=f"✅ Report generated. Saved to: {filename}")

        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            import traceback
            traceback.print_exc()
            return ToolResult(error=str(e))
##双线代码
# import os
# import json
# import re
# from typing import Dict, List, Optional

# from pydantic import Field
# from app.tool.base import BaseTool, ToolResult
# from app.llm import LLM
# from app.logger import logger
# from app.schema import Message 

# class ReportGeneratorTool(BaseTool):
#     name: str = "report_generator"
#     description: str = """
#     Generates a final, visually rich market report. 
#     It combines data analysis with automatic local image embedding.
#     No separate post-processing tool is needed.
#     """
    
#     parameters: dict = {
#         "type": "object",
#         "properties": {
#             "report_topic": {
#                 "type": "string",
#                 "description": "The main topic of the report (e.g., '2025 Sofa Design Trends')."
#             },
#             "language": {
#                 "type": "string",
#                 "description": "The output language (default: English).",
#                 "default": "English"
#             }
#         },
#         "required": ["report_topic"]
#     }

#     llm: LLM = Field(default_factory=LLM, exclude=True)

#     def _parse_resource_map(self, session_id: str) -> Dict[str, str]:
#         """
#         读取并解析 resource_map.txt
#         返回: { 'image_id_string': 'local/path/to/image.png' }
#         """
#         map_path = f"workspace/{session_id}/extracted_data/resource_map.txt"
#         # map_path = "/home/user/workplace/PTQ/deepseek-ocr/multi_agent/workspace/extracted_data/test_design_trends_1768896730/resource_map.txt"
#         resource_map = {}
        
#         if not os.path.exists(map_path):
#             logger.warning(f"⚠️ Resource map not found at {map_path}. Images cannot be embedded.")
#             return {}

#         try:
#             with open(map_path, 'r', encoding='utf-8') as f:
#                 content = f.read()
            
#             # 解析格式: "ItemName\n  -> Path\n\n"
#             entries = re.split(r'\n\n', content)
#             for entry in entries:
#                 if '->' in entry:
#                     lines = entry.strip().split('\n')
#                     split_idx = -1
#                     for i, line in enumerate(lines):
#                         if line.strip().startswith('->'):
#                             split_idx = i
#                             break
                    
#                     if split_idx >= 0:
#                         item_name = "".join(lines[:split_idx]).strip()
#                         path_line = lines[split_idx].strip()
#                         # 去掉 "-> "
#                         file_path = path_line[2:].strip()
                        
#                         # 转为绝对路径，确保在 reports/ 目录下也能访问
#                         if not os.path.isabs(file_path):
#                             file_path = os.path.abspath(file_path)
                            
#                         if item_name and file_path:
#                             resource_map[item_name] = file_path
                            
#             logger.info(f"🗺️ Loaded {len(resource_map)} resource mappings.")
#             return resource_map
            
#         except Exception as e:
#             logger.error(f"❌ Failed to parse resource map: {e}")
#             return {}

#     def _inject_images_into_report(self, report_content: str, resource_map: Dict[str, str], session_id: str) -> str:
#             """
#             将报告中的 <resource_info>id</resource_info> 替换为 ![id](/workspace/{session_id}/extracted_data/resources/filename)
#             """
#             if not resource_map:
#                 return report_content

#             # 1. 预处理：修复可能错误的 Markdown 语法 (防止双重包裹)
#             replace_pattern = r'!\[[^\]]*\]\(<resource_info>(.*?)</resource_info>\)'
#             report_content = re.sub(replace_pattern, r'<resource_info>\1</resource_info>', report_content)

#             replaced_count = 0
            
#             # 2. 遍历替换 (按 Key 长度降序，防止部分匹配)
#             sorted_keys = sorted(resource_map.keys(), key=len, reverse=True)

#             for item_name in sorted_keys:
#                 # 原始路径 (可能是相对的也可能是绝对的)
#                 raw_path = resource_map[item_name]
                
#                 # 提取文件名 (例如 8beabc31.png)
#                 filename = os.path.basename(raw_path)
                
#                 # 构造你要求的标准路径格式
#                 # 注意：这假设所有资源最终都位于这个标准目录下
#                 final_path = f"/workspace/{session_id}/extracted_data/resources/{filename}"
                
#                 tag = f'<resource_info>{item_name}</resource_info>'
                
#                 if tag in report_content:
#                     # 构造 Markdown 图片语法
#                     # 使用文件名作为 alt 文本
#                     markdown_img = f'\n\n![{filename}]({final_path})\n\n'
                    
#                     report_content = report_content.replace(tag, markdown_img)
#                     replaced_count += 1

#             logger.info(f"🖼️ Injected {replaced_count} images into the report.")
            
#             # 3. 清理未匹配的标签
#             report_content = re.sub(r'<resource_info>.*?</resource_info>', '', report_content, flags=re.DOTALL)
            
#             return report_content
#     async def execute(self, report_topic: str, language: str = "English") -> ToolResult:
#         logger.info(f"📝 Generating final report for: {report_topic}")

#         # =================================================================
#         # 1. 加载数据
#         # =================================================================
#         session_id = os.environ.get("MANUS_SESSION_ID", "default_session")
        
#         # 尝试加载 combined 数据或普通数据
#         data_dir = f"workspace/{session_id}/structured_data"
#         candidates = [
#             f"{data_dir}/combined_data_{session_id}.json",
#             # f"{data_dir}/data_{session_id}.json"
#         ]
        
#         data_list = []
#         # loaded_path = ""
        
#         for path in candidates:
#             if os.path.exists(path):
#                 try:
#                     with open(path, "r", encoding="utf-8") as f:
#                         raw = json.load(f)
#                         data_list = raw.get("data", raw) if isinstance(raw, dict) else raw
#                         # loaded_path = path
#                         break
#                 except Exception:
#                     continue
        
#         if not data_list:
#             return ToolResult(error=f"No structured data found for session '{session_id}'. Run extraction first.")

#         # 转换为字符串供 Prompt 使用 (截断保护)
#         collected_data_str = json.dumps(data_list, ensure_ascii=False, indent=2)#[:60000]

#         # =================================================================
#         # 2. 生成报告 (LLM 阶段)
#         # =================================================================
#         system_prompt = f"""
# You are a professional design trend analyst. Generate a Markdown report based on the user's topic and the provided input data.

# **Requirements:**
# 1. **MECE Principle**: Content must be mutually exclusive and collectively exhaustive, with clear structure and logic.
# 2. **Visual-Rich (Strict image rules)**:
#    - Treat an image as a “web URL image” **ONLY if it starts with `https://`**. In that case, you MUST embed it using Markdown image syntax: `![alt](url)`, placed adjacent to the most relevant paragraph.
#    - Treat **all other image identifiers as local/resource placeholders** (including `http://`, relative paths, local file paths, resource keys, resource ids, etc.). In that case, you MUST use: `<resource_info>placeholder_string</resource_info>`, placed near the relevant text.
#    - Do NOT group all images at the end; insert them inline where they are most relevant.
# 3. **Must Cite Sources**: Every key insight must end with a citation `[Website Name](url)`.e.g."[Homes & Gardens](https://www.homesandgardens.com/interior-design/living-rooms/sofa-trends-for-2026)"
# 4. **Formatting**: Use Markdown headings; LaTeX formulas allowed; preserve tables.
# 5. **Start Directly**: Begin with the report title. No greetings or introductory filler.
# 6. **Length**: Write a **long, detailed report** with as much depth as the input supports (prioritize completeness over brevity; avoid fluff).
# **Output Language**: {language}
# """


#         user_prompt = f"""
# **Topic**: {report_topic}

# **Input Data**:
# {collected_data_str}
# """

#         try:
#             # 调用 LLM
#             report_content = await self.llm.ask([
#                 Message(role="system", content=system_prompt),
#                 Message(role="user", content=user_prompt)
#             ])
            
#             # 简单清洗
#             if report_content:
#                 report_content = report_content.replace("```markdown", "").replace("```", "").strip()

#             # =================================================================
#             # 3. 资源替换 (Resource Injection 阶段)
#             # =================================================================
#             logger.info("🔄 Processing image tags...")
            
#             # 加载映射表
#             resource_map = self._parse_resource_map(session_id)
            
#             # 执行替换
#             final_content = self._inject_images_into_report(report_content, resource_map,session_id)

#             # =================================================================
#             # 4. 保存最终文件
#             # =================================================================
#             output_dir = f"workspace/{session_id}/reports"
#             # 兼容：如果 session 目录不存在，回退到根目录 reports
#             if not os.path.exists(f"workspace/{session_id}"):
#                 output_dir = "reports"
                
#             os.makedirs(output_dir, exist_ok=True)
            
#             safe_topic = re.sub(r'[\\/*?:"<>|]', "", report_topic.replace(" ", "_"))
#             filename = f"{output_dir}/{safe_topic}.md"
            
#             with open(filename, "w", encoding="utf-8") as f:
#                 f.write(final_content)
                
#             logger.info(f"💾 Final report saved to: {filename}")
            
#             return ToolResult(output=f"✅ Report generated with images embedded. Saved to: {filename}")

#         except Exception as e:
#             logger.error(f"Failed to generate report: {e}")
#             import traceback
#             traceback.print_exc()
#             return ToolResult(error=str(e))