#单线代码
import json
import os
import re
from typing import List, Dict
from pydantic import Field
from app.tool.base import BaseTool, ToolResult
from app.llm import LLM
from app.logger import logger

# RAG 与 Re-rank 依赖
try:
    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_core.documents import Document
    from sentence_transformers import CrossEncoder
except ImportError:
    raise ImportError("Please install dependencies: pip install langchain-huggingface faiss-cpu sentence-transformers")

# 全局模型 (单例模式)
_EMBEDDING_MODEL = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
_RERANK_MODEL = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


class StructuredRetrievalTool(BaseTool):
    name: str = "structured_retrieval"
    description: str = """
    Advanced batch-processing extraction tool. Processes multiple files,
    extracts raw structured insights, and performs re-ranking.
    Returns RAW markdown content without cleaning.
    """

    parameters: dict = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of local paths to the files (.md)."
            },
            "query": {
                "type": "string",
                "description": "The specific extraction query (e.g. 'smart home trends')."
            },
            "source_url": {
                "type": "string",
                "description": "Optional global source URL (for plain markdown files)."
            }
        },
        "required": ["file_paths", "query"]
    }

    llm: LLM = Field(default_factory=LLM, exclude=True)

    async def execute(
        self,
        query: str,
        file_paths: List[str] = None,
        source_url: str = None,
        **kwargs
    ) -> ToolResult:
        logger.info(f"🔍 Starting Raw Structured Extraction for query: '{query}'")

        session_id = os.environ.get("MANUS_SESSION_ID", "default_session")
        all_docs_pool: List[Document] = []
        execution_summary = []

        # 1) 批量加载：仅处理 Markdown 文件
        for path in file_paths:
            file_name = os.path.basename(path)
            try:
                if not os.path.exists(path):
                    continue

                # 只接受 markdown（你也可以放宽到 .md/.markdown）
                if not (path.endswith(".md") or path.endswith(".markdown")):
                    logger.warning(f"⚠️ Skip non-markdown file: {file_name}")
                    continue

                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()

                logger.info(f"📝 Processing Markdown (Raw): {file_name}")

                # 1) 优先使用参数传入的 source_url
                current_source = source_url

                # 2) 如果没传 source_url，再尝试从 HTML 注释中提取
                if not current_source:
                    source_match = re.search(r"<!--\s*Source:\s*(.*?)\s*-->", content)
                    if source_match:
                        current_source = source_match.group(1).strip()

                # 3) 如果仍然没有 source，兜底
                if not current_source:
                    current_source = "unknown_source"
                    logger.warning(f"⚠️ [Markdown] No source URL found for {file_name}, using 'unknown_source'")

                # 4) 按标题切分并入池
                sections = self._split_markdown_by_headers(
                    content,
                    min_level=1,
                    max_level=3,
                    max_chars=2000,
                    overlap=150
                )

                md_docs: List[Document] = []
                for sec in sections:
                    d = Document(page_content=sec, metadata={})
                    d.metadata["source_url"] = current_source
                    d.metadata["file_type"] = "markdown"
                    d.metadata["file_name"] = file_name
                    md_docs.append(d)

                all_docs_pool.extend(md_docs)
                execution_summary.append(f"✅ [Markdown] {file_name} ({len(md_docs)} header sections)")

            except Exception as e:
                logger.error(f"Failed to process {file_name}: {e}")

        # 2) 向量召回 + 结构化提取 (Raw Mode)
        final_data = []
        if all_docs_pool:
            logger.info(f"📊 Global Pool: {len(all_docs_pool)} chunks. Vector Search...")

            vector_store = FAISS.from_documents(all_docs_pool, _EMBEDDING_MODEL)
            retrieved_candidates = vector_store.similarity_search(query, k=200)

            docs_info = []
            for d in retrieved_candidates:
                docs_info.append({
                    "content": d.page_content,
                    "source_url": d.metadata.get("source_url"),
                    "file_type": d.metadata.get("file_type", "unknown")
                })

            structured_items = self._process_structured_content_raw(docs_info)

            structured_docs_for_rerank = [
                Document(page_content=item["text"], metadata=item)
                for item in structured_items
            ]

            reranked_docs = self._perform_rerank(query, structured_docs_for_rerank, top_k=50)

            for doc in reranked_docs:
                final_data.append({
                    "text": doc.page_content,
                    "images": doc.metadata.get("images", []),
                    "source_url": doc.metadata.get("source_url")
                })

        # 3) 保存
        if final_data:
            master_save_path = self._save_final_data(final_data, session_id)
            return ToolResult(output=f"Raw extraction complete. Saved {len(final_data)} items to: {master_save_path}")

        return ToolResult(output="Batch process finished, no items found.")

    def _process_structured_content_raw(self, docs_info: List[Dict]) -> List[Dict]:
        """
        [Raw Mode] 结构化内容提取
        - 不移除 Markdown 符号
        - 不移除图片标签 (保留在 text 中)
        - 依然提取 images 列表供下游使用
        """
        extracted_items = []

        for info in docs_info:
            raw_content = info["content"]
            source = info.get("source_url", "unknown")
            file_type = info.get("file_type", "unknown")

            primary_segments = re.split(r"(?:\n|^)#{1,6}\s+|(?:\n|^)-{3,}(?:\n|$)", raw_content)

            final_segments = []
            for seg in primary_segments:
                if len(seg) > 800:
                    final_segments.extend(seg.split("\n\n"))
                else:
                    final_segments.append(seg)

            for section in final_segments:
                section = section.strip()
                if len(section) < 10:
                    continue

                image_urls = []
                image_urls.extend(re.findall(r"!\[.*?\]\((.*?)\)", section))
                # image_urls.extend(re.findall(r"<resource_info>(.*?)</resource_info>", section))
                unique_images = list(set(image_urls))

                extracted_items.append({
                    "text": section,
                    "images": unique_images,
                    "source_url": source,
                    "file_type": file_type
                })

        return extracted_items

    def _perform_rerank(self, query: str, docs: List["Document"], top_k: int) -> List["Document"]:
        """Cross-Encoder 重排序"""
        if not docs:
            return []
        unique_docs = {d.page_content: d for d in docs}.values()
        docs = list(unique_docs)

        pairs = [[query, doc.page_content] for doc in docs]
        scores = _RERANK_MODEL.predict(pairs)
        scored_docs = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scored_docs[:top_k]]

    def _save_final_data(self, new_data: List[Dict], session_id: str) -> str:
        save_dir = f"workspace/{session_id}/structured_data"
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, f"combined_data_{session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"data": new_data}, f, ensure_ascii=False, indent=4)
        return path
    def _split_markdown_by_headers(
        self,
        content: str,
        min_level: int = 1,
        max_level: int = 3,
        max_chars: int = 2000,
        overlap: int = 150,
        ) -> List[str]:
        """
        按 Markdown ATX 标题 (#, ##, ### ...) 切分。
        - min_level/max_level 控制用哪些标题作为“切分点”
        - 每个 section 如果超过 max_chars，会再做二次切分（带 overlap）
        """
        # 匹配行首标题：# 到 ######，后面至少一个空格
        header_re = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.MULTILINE)

        matches = list(header_re.finditer(content))
        if not matches:
            # 没标题就整体返回，后面二次切分
            return self._chunk_text(content, max_chars=max_chars, overlap=overlap)

        sections: List[str] = []
        for i, m in enumerate(matches):
            level = len(m.group(1))
            # 只以指定 level 范围内的标题作为切分点
            if not (min_level <= level <= max_level):
                continue

            start = m.start()
            # 找下一个“可用标题切分点”的位置作为 end
            end = len(content)
            for j in range(i + 1, len(matches)):
                lvl2 = len(matches[j].group(1))
                if min_level <= lvl2 <= max_level:
                    end = matches[j].start()
                    break

            block = content[start:end].strip()
            if block:
                sections.append(block)

        # 如果因为 level 过滤导致 sections 为空，降级：按任意标题切
        if not sections:
            sections = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                block = content[start:end].strip()
                if block:
                    sections.append(block)

        # 二次切分：避免某个 section 太长
        final_sections: List[str] = []
        for s in sections:
            if len(s) > max_chars:
                final_sections.extend(self._chunk_text(s, max_chars=max_chars, overlap=overlap))
            else:
                final_sections.append(s)

        return final_sections


    def _chunk_text(self, text: str, max_chars: int = 2000, overlap: int = 150) -> List[str]:
        """简单按字符长度切 chunk（用于 section 太长时的二次切分）"""
        text = text.strip()
        if len(text) <= max_chars:
            return [text] if text else []

        chunks = []
        start = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(text):
                break
            start = max(0, end - overlap)
        return chunks

#双线代码
# import json
# import os
# import re
# import asyncio
# from typing import List, Optional, Dict, Any
# from pydantic import Field
# from app.schema import Message 

# # 工具类依赖
# from app.tool.base import BaseTool, ToolResult
# from app.llm import LLM
# from app.logger import logger

# # RAG 与 Re-rank 依赖
# try:
#     from langchain_text_splitters import MarkdownTextSplitter, RecursiveCharacterTextSplitter
#     from langchain_community.vectorstores import FAISS
#     from langchain_huggingface import HuggingFaceEmbeddings
#     from langchain_core.documents import Document
#     from sentence_transformers import CrossEncoder
# except ImportError:
#     raise ImportError("Please install dependencies: pip install langchain-huggingface faiss-cpu sentence-transformers")

# # 全局模型 (单例模式)
# _EMBEDDING_MODEL = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
# _RERANK_MODEL = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# class StructuredRetrievalTool(BaseTool):
#     name: str = "structured_retrieval"
#     description: str = """
#     Advanced batch-processing extraction tool. Processes multiple files, 
#     extracts raw structured insights, and performs re-ranking.
#     Returns RAW markdown content without cleaning.
#     """
    
#     parameters: dict = {
#         "type": "object",
#         "properties": {
#             "file_paths": {
#                 "type": "array",
#                 "items": {"type": "string"},
#                 "description": "List of local paths to the files (.md or extracted_context.txt)."
#             },
#             "query": {
#                 "type": "string",
#                 "description": "The specific extraction query (e.g. 'smart home trends')."
#             },
#             "source_url": {
#                 "type": "string",
#                 "description": "Optional global source URL (for plain markdown files)."
#             }
#         },
#         "required": ["file_paths", "query"]
#     }

#     llm: LLM = Field(default_factory=LLM, exclude=True)

#     async def execute(self, query: str, file_paths: List[str] = None, source_url: str = None, **kwargs) -> ToolResult:
#         logger.info(f"🔍 Starting Raw Structured Extraction for query: '{query}'")
        
#         session_id = os.environ.get("MANUS_SESSION_ID", "default_session")
#         all_docs_pool = [] 
#         execution_summary = []

#         # 1. 批量循环：加载所有文件
#         for path in file_paths:
#             file_name = os.path.basename(path)
#             try:
#                 if not os.path.exists(path):
#                     continue
                
#                 with open(path, 'r', encoding='utf-8') as f:
#                     content = f.read()

#                 # --- 分支 A: 处理 ms-agent 的 output txt ---
#                 if path.endswith('.txt') or 'extracted_context' in file_name:
        
#                     ms_docs = self._parse_ms_agent_file(content)
#                     all_docs_pool.extend(ms_docs)
#                     execution_summary.append(f"✅ [Visual] {file_name} ({len(ms_docs)} chunks)")

#                 # --- 分支 B: 处理普通 Markdown 文件 ---
#                 else:
#                     logger.info(f"📝 Processing Markdown (Raw): {file_name}")
#                     print("Processing Markdown (Raw):", file_name)
#                     # 1) 优先使用参数传入的 source_url
#                     current_source = source_url

#                     # 2) 如果没传 source_url，再尝试从 HTML 注释中提取
#                     if not current_source:
#                         source_match = re.search(r'<!--\s*Source:\s*(.*?)\s*-->', content)
#                         if source_match:
#                             current_source = source_match.group(1).strip()

#                     # 3) 如果仍然没有 source，兜底
#                     if not current_source:
#                         current_source = "unknown_source"
#                         logger.warning(f"⚠️ [Markdown] No source URL found for {file_name}, using 'unknown_source'")

#                     # 4) ✅ 无论有没有 source，都要切分并入池
#                     sections = self._split_markdown_by_headers(
#                         content,
#                         min_level=1,
#                         max_level=3,     # 常见：用到 ### 就够了；你也可以改到 6
#                         max_chars=2000,  # 每个标题块最大长度，超出会二次切分
#                         overlap=150
#                     )

#                     md_docs = []
#                     for sec in sections:
#                         d = Document(page_content=sec, metadata={})
#                         d.metadata["source_url"] = current_source
#                         d.metadata["file_type"] = "markdown"
#                         d.metadata["file_name"] = file_name
#                         md_docs.append(d)

#                     all_docs_pool.extend(md_docs)
#                     execution_summary.append(f"✅ [Markdown] {file_name} ({len(md_docs)} header sections)")
#                     # splitter = MarkdownTextSplitter(chunk_size=512, chunk_overlap=100)
#                     # md_docs = splitter.create_documents([content])

#                     # for doc in md_docs:
#                     #     doc.metadata["source_url"] = current_source
#                     #     doc.metadata["file_type"] = "markdown"
#                     #     doc.metadata["file_name"] = file_name  # 可选：方便追踪

#                     # all_docs_pool.extend(md_docs)
#                     # execution_summary.append(f"✅ [Markdown] {file_name} ({len(md_docs)} chunks)")

#             except Exception as e:
#                 logger.error(f"Failed to process {file_name}: {e}")

#         # 2. 向量召回 + 结构化提取 (Raw Mode)
#         final_data = []
#         if all_docs_pool:
#             logger.info(f"📊 Global Pool: {len(all_docs_pool)} chunks. Vector Search...")
            
#             vector_store = FAISS.from_documents(all_docs_pool, _EMBEDDING_MODEL)
#             retrieved_candidates = vector_store.similarity_search(query, k=200)
            
#             # 准备数据
#             docs_info = []
#             for d in retrieved_candidates:
#                 docs_info.append({
#                     "content": d.page_content,
#                     "source_url": d.metadata.get("source_url"),
#                     "file_type": d.metadata.get("file_type", "unknown")
#                 })
            
#             # --- 调用不做清洗的处理函数 ---
#             structured_items = self._process_structured_content_raw(docs_info)
            
#             structured_docs_for_rerank = [
#                 Document(page_content=item["text"], metadata=item) 
#                 for item in structured_items
#             ]
            
#             # Re-rank (Re-rank 模型通常能理解 Markdown 语法，所以没问题)
#             reranked_docs = self._perform_rerank(query, structured_docs_for_rerank, top_k=80)
            
#             for doc in reranked_docs:
#                 final_data.append({
#                     "text": doc.page_content, # 这里是包含 markdown 的原始内容
#                     "images": doc.metadata.get("images", []),
#                     "source_url": doc.metadata.get("source_url")
#                 })

#         # 3. 保存
#         if final_data:
#             master_save_path = self._save_final_data(final_data, session_id)
#             return ToolResult(output=f"Raw extraction complete. Saved {len(final_data)} items to: {master_save_path}")
        
#         return ToolResult(output="Batch process finished, no items found.")

#     def _parse_ms_agent_file(self, content: str) -> List[Document]:
#         """解析 ms-agent 文件 (保持原逻辑，主要是为了切分 chunk)"""
#         documents = []
#         raw_segments = re.split(r'\n={10,}\n', content)
#         splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

#         for segment in raw_segments:
#             segment = segment.strip()
#             if not segment: continue
            
#             source_url = "unknown_visual_source"
#             source_match = re.search(r'📄 \[Source\]:\s*(.*?)\n', segment)
#             if source_match:
#                 source_url = source_match.group(1).strip()
            
#             # 这里我们稍微清理一下 header，因为它是人为加的分割线，不属于内容
#             clean_content = re.sub(r'📄 \[Source\]:.*?\n-+\n', '', segment, flags=re.DOTALL)
            
#             chunks = splitter.create_documents([clean_content])
            
#             for chunk in chunks:
#                 chunk.metadata["source_url"] = source_url
#                 chunk.metadata["file_type"] = "ms_agent_txt"
#                 documents.append(chunk)
#         return documents

#     def _process_structured_content_raw(self, docs_info: List[Dict]) -> List[Dict]:
#         """
#         [Raw Mode] 结构化内容提取
#         - 不移除 Markdown 符号
#         - 不移除图片标签 (保留在 text 中)
#         - 依然提取 images 列表供下游使用
#         """
#         extracted_items = []
        
#         for info in docs_info:
#             raw_content = info["content"]
#             source = info.get("source_url", "unknown")
#             file_type = info.get("file_type", "unknown")
            
#             # 1. 依然做分段，因为我们需要以段落为单位进行 Rerank
#             # 简单的按双换行符切分，或者按 Markdown 标题切分
#             primary_segments = re.split(r'(?:\n|^)#{1,6}\s+|(?:\n|^)-{3,}(?:\n|$)', raw_content)
            
#             final_segments = []
#             for seg in primary_segments:
#                 if len(seg) > 800:
#                     sub_segs = seg.split('\n\n')
#                     final_segments.extend(sub_segs)
#                 else:
#                     final_segments.append(seg)
            
#             # 2. 逐段处理
#             for section in final_segments:
#                 section = section.strip()
#                 if len(section) < 10: continue 
                
#                 # A. 提取图片列表 (为了方便下游工具索引，提取步骤不能省)
#                 image_urls = []
#                 md_imgs = re.findall(r'!\[.*?\]\((.*?)\)', section)
#                 image_urls.extend(md_imgs)
#                 res_imgs = re.findall(r'<resource_info>(.*?)</resource_info>', section)
#                 image_urls.extend(res_imgs)
                
#                 unique_images = list(set(image_urls))
                
#                 # B. 【关键】不做清洗，直接使用原始文本
#                 # raw_text 保留了 ![img](url), [link](url), **bold**, ### header
#                 raw_text = section
#                 #B. 清洗文本
#                 # clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', section)
#                 # clean_text = re.sub(r'<resource_info>.*?</resource_info>', '', clean_text)
#                 # clean_text = re.sub(r'\[\d+\]', '', clean_text)
#                 # clean_text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', clean_text) # 移除链接保留文字
#                 # clean_text = re.sub(r'\s+', ' ', clean_text).strip()
#                 # clean_text = re.sub(r'^[#\-\*]+\s*', '', clean_text) 
                
#                 # C. 构建结果
#                 extracted_items.append({
#                     "text": raw_text,         # 原始文本
#                     "images": unique_images,  # 图片列表
#                     "source_url": source,
#                     # "metadata": {
#                     #     "file_type": file_type,
#                     #     "original_length": len(section)
#                     # }
#                 })
                
#         return extracted_items

#     def _perform_rerank(self, query: str, docs: List[Document], top_k: int) -> List[Document]:
#         """Cross-Encoder 重排序"""
#         if not docs: return []
#         unique_docs = {d.page_content: d for d in docs}.values()
#         docs = list(unique_docs)

#         pairs = [[query, doc.page_content] for doc in docs]
#         scores = _RERANK_MODEL.predict(pairs)
#         scored_docs = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
#         return [doc for score, doc in scored_docs[:top_k]]

#     def _save_final_data(self, new_data: List[Dict], session_id: str) -> str:
#         save_dir = f"workspace/{session_id}/structured_data"
#         os.makedirs(save_dir, exist_ok=True)
#         path = os.path.join(save_dir, f"combined_data_{session_id}.json")
#         with open(path, "w", encoding="utf-8") as f:
#             json.dump({"data": new_data}, f, ensure_ascii=False, indent=4)
#         return path
    # def _split_markdown_by_headers(
    # self,
    # content: str,
    # min_level: int = 1,
    # max_level: int = 3,
    # max_chars: int = 2000,
    # overlap: int = 150,
    # ) -> List[str]:
    #     """
    #     按 Markdown ATX 标题 (#, ##, ### ...) 切分。
    #     - min_level/max_level 控制用哪些标题作为“切分点”
    #     - 每个 section 如果超过 max_chars，会再做二次切分（带 overlap）
    #     """
    #     # 匹配行首标题：# 到 ######，后面至少一个空格
    #     header_re = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.MULTILINE)

    #     matches = list(header_re.finditer(content))
    #     if not matches:
    #         # 没标题就整体返回，后面二次切分
    #         return self._chunk_text(content, max_chars=max_chars, overlap=overlap)

    #     sections: List[str] = []
    #     for i, m in enumerate(matches):
    #         level = len(m.group(1))
    #         # 只以指定 level 范围内的标题作为切分点
    #         if not (min_level <= level <= max_level):
    #             continue

    #         start = m.start()
    #         # 找下一个“可用标题切分点”的位置作为 end
    #         end = len(content)
    #         for j in range(i + 1, len(matches)):
    #             lvl2 = len(matches[j].group(1))
    #             if min_level <= lvl2 <= max_level:
    #                 end = matches[j].start()
    #                 break

    #         block = content[start:end].strip()
    #         if block:
    #             sections.append(block)

    #     # 如果因为 level 过滤导致 sections 为空，降级：按任意标题切
    #     if not sections:
    #         sections = []
    #         for i, m in enumerate(matches):
    #             start = m.start()
    #             end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
    #             block = content[start:end].strip()
    #             if block:
    #                 sections.append(block)

    #     # 二次切分：避免某个 section 太长
    #     final_sections: List[str] = []
    #     for s in sections:
    #         if len(s) > max_chars:
    #             final_sections.extend(self._chunk_text(s, max_chars=max_chars, overlap=overlap))
    #         else:
    #             final_sections.append(s)

    #     return final_sections


#     def _chunk_text(self, text: str, max_chars: int = 2000, overlap: int = 150) -> List[str]:
#         """简单按字符长度切 chunk（用于 section 太长时的二次切分）"""
#         text = text.strip()
#         if len(text) <= max_chars:
#             return [text] if text else []

#         chunks = []
#         start = 0
#         while start < len(text):
#             end = min(len(text), start + max_chars)
#             chunk = text[start:end].strip()
#             if chunk:
#                 chunks.append(chunk)
#             if end == len(text):
#                 break
#             start = max(0, end - overlap)
#         return chunks
