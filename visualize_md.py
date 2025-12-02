import re
import os
from html import escape
import webbrowser
from pathlib import Path
import tempfile

class MarkdownVisualizer:
    """Markdown可视化工具，将Markdown转换为HTML并在浏览器中展示"""
    
    def __init__(self):
        # Markdown语法规则
        self.rules = [
            # 标题
            (r'^(#{1,6})\s+(.*)$', self._replace_heading),
            # 粗体
            (r'\*\*(.*?)\*\*', r'<strong>\1</strong>'),
            # 斜体
            (r'\*(.*?)\*', r'<em>\1</em>'),
            # 链接
            (r'\[(.*?)\]\((.*?)\)', r'<a href="\2" target="_blank">\1</a>'),
            # 图片
            (r'!\[(.*?)\]\((.*?)\)', r'<img src="\2" alt="\1" style="max-width:100%;height:auto;">'),
            # 代码块
            (r'```([\s\S]*?)```', r'<pre><code>\1</code></pre>'),
            # 行内代码
            (r'`(.*?)`', r'<code>\1</code>'),
            # 无序列表
            (r'^\s*[-*+]\s+(.*)$', r'<li>\1</li>'),
            # 有序列表
            (r'^\s*\d+\.\s+(.*)$', r'<li>\1</li>'),
            # 引用
            (r'^\s*>\s+(.*)$', r'<blockquote>\1</blockquote>'),
            # 水平线
            (r'^---+$', r'<hr>'),
        ]
        
        # CSS样式
        self.css = """
        <style>
            body {
                font-family: 'Segoe UI', Arial, sans-serif;
                line-height: 1.6;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                color: #333;
                background-color: #f8f9fa;
            }
            h1, h2, h3, h4, h5, h6 {
                color: #2c3e50;
                margin-top: 1.5em;
                margin-bottom: 0.5em;
            }
            h1 { border-bottom: 2px solid #eee; padding-bottom: 10px; }
            h2 { border-bottom: 1px solid #eee; padding-bottom: 8px; }
            pre {
                background-color: #f5f5f5;
                border-radius: 4px;
                padding: 15px;
                overflow-x: auto;
                border: 1px solid #ddd;
            }
            code {
                background-color: #f8f8f8;
                padding: 2px 4px;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            pre code {
                background: none;
                padding: 0;
            }
            blockquote {
                border-left: 4px solid #ddd;
                padding: 0 15px;
                color: #666;
                margin: 1em 0;
            }
            ul, ol {
                margin: 1em 0;
                padding-left: 2em;
            }
            li {
                margin: 0.5em 0;
            }
            a {
                color: #007bff;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
            img {
                border-radius: 4px;
                margin: 1em 0;
            }
            hr {
                border: none;
                border-top: 1px solid #ddd;
                margin: 2em 0;
            }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 1em 0;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px 12px;
                text-align: left;
            }
            th {
                background-color: #f2f2f2;
            }
        </style>
        """
    
    def _replace_heading(self, match):
        """处理标题替换"""
        level = len(match.group(1))
        text = match.group(2)
        return f'<h{level}>{text}</h{level}>'
    
    def _process_lists(self, html):
        """处理列表结构"""
        # 处理无序列表
        html = re.sub(r'(<li>.*?</li>\s*)+', r'<ul>\g<0></ul>', html, flags=re.DOTALL)
        # 处理有序列表
        html = re.sub(r'(<li>.*?</li>\s*)+', r'<ol>\g<0></ol>', html, flags=re.DOTALL)
        return html
    
    def markdown_to_html(self, markdown_text):
        """将Markdown文本转换为HTML"""
        # 分割成行处理
        lines = markdown_text.split('\n')
        html_lines = []
        
        in_code_block = False
        
        for line in lines:
            if line.startswith('```'):
                in_code_block = not in_code_block
            
            if not in_code_block:
                # 应用所有规则
                processed_line = line
                for pattern, replacement in self.rules:
                    if callable(replacement):
                        processed_line = re.sub(pattern, replacement, processed_line, flags=re.MULTILINE)
                    else:
                        processed_line = re.sub(pattern, replacement, processed_line, flags=re.MULTILINE)
                html_lines.append(processed_line)
            else:
                html_lines.append(line)
        
        html = '\n'.join(html_lines)
        
        # 后处理列表
        html = self._process_lists(html)
        
        # 添加段落标签
        html = re.sub(r'(?<!<[/\w])(\n|^)([^<\n]+)(?=\n|$)', r'<p>\2</p>', html)
        
        # 组合完整HTML
        full_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Markdown Preview</title>
            {self.css}
        </head>
        <body>
            {html}
        </body>
        </html>
        """
        
        return full_html
    
    def visualize_file(self, file_path):
        """可视化Markdown文件"""
        file_path = Path(file_path)
        
        if not file_path.exists():
            print(f"错误：文件 {file_path} 不存在！")
            return
        
        if file_path.suffix.lower() not in ['.md', '.markdown']:
            print("警告：文件不是Markdown格式！")
        
        # 读取Markdown文件
        with open(file_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # 转换为HTML
        html_content = self.markdown_to_html(markdown_content)
        
        # 创建临时HTML文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(html_content)
            temp_file_path = temp_file.name
        
        # 在浏览器中打开
        webbrowser.open(f'file://{os.path.abspath(temp_file_path)}')
        print(f"Markdown预览已在浏览器中打开：{temp_file_path}")
        
        return temp_file_path

    def visualize_text(self, markdown_text, title="Markdown Preview"):
        """可视化Markdown文本"""
        # 转换为HTML
        html_content = self.markdown_to_html(markdown_text)
        
        # 创建临时HTML文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(html_content.replace('Markdown Preview', title))
            temp_file_path = temp_file.name
        
        # 在浏览器中打开
        webbrowser.open(f'file://{os.path.abspath(temp_file_path)}')
        print(f"Markdown预览已在浏览器中打开：{temp_file_path}")
        
        return temp_file_path


# 示例使用
if __name__ == "__main__":
    import sys
    
    visualizer = MarkdownVisualizer()

    # 可视化指定的Markdown文件
    file_path = "/home/user/workplace/PTQ/deepseek-ocr/multi_agent/workspace/Sofa_Trend_Report.md"
    visualizer.visualize_file(file_path)
