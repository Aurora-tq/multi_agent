"""File and directory manipulation tool with sandbox support."""
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, List, Literal, Optional, get_args
from typing import Union
from app.config import config
from app.exceptions import ToolError
from app.tool import BaseTool
from app.tool.base import CLIResult, ToolResult
from app.tool.file_operators import (
    FileOperator,
    LocalFileOperator,
    PathLike,
    SandboxFileOperator,
)


Command = Literal[
    "view",
    "create",
    "str_replace",
    "insert",
    "undo_edit",
]

# Constants
SNIPPET_LINES: int = 4
MAX_RESPONSE_LEN: int = 16000
TRUNCATED_MESSAGE: str = (
    "<response clipped><NOTE>To save on context only part of this file has been shown to you. "
    "You should retry this tool after you have searched inside the file with `grep -n` "
    "in order to find the line numbers of what you are looking for.</NOTE>"
)

# Tool description
_STR_REPLACE_EDITOR_DESCRIPTION = """Custom editing tool for viewing, creating and editing files
* State is persistent across command calls and discussions with the user
* If `path` is a file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep
* The `create` command cannot be used if the specified `path` already exists as a file
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>`
* The `undo_edit` command will revert the last edit made to the file at `path`

Notes for using the `str_replace` command:
* The `old_str` parameter should match EXACTLY one or more consecutive lines from the original file. Be mindful of whitespaces!
* If the `old_str` parameter is not unique in the file, the replacement will not be performed. Make sure to include enough context in `old_str` to make it unique
* The `new_str` parameter should contain the edited lines that should replace the `old_str`
"""


def maybe_truncate(
    content: str, truncate_after: Optional[int] = MAX_RESPONSE_LEN
) -> str:
    """Truncate content and append a notice if content exceeds the specified length."""
    if not truncate_after or len(content) <= truncate_after:
        return content
    return content[:truncate_after] + TRUNCATED_MESSAGE


class StrReplaceEditor(BaseTool):
    """A tool for viewing, creating, and editing files with sandbox support."""

    name: str = "str_replace_editor"
    description: str = _STR_REPLACE_EDITOR_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "description": "The commands to run. Allowed options are: `view`, `create`, `str_replace`, `insert`, `undo_edit`.",
                "enum": ["view", "create", "str_replace", "insert", "undo_edit"],
                "type": "string",
            },
            "path": {
                "description": "Absolute or relative path to file or directory.",
                "type": "string",
            },
            "file_text": {
                "description": "Required parameter of `create` command, with the content of the file to be created.",
                "type": "string",
            },
            "old_str": {
                "description": "Required parameter of `str_replace` command containing the string in `path` to replace.",
                "type": "string",
            },
            "new_str": {
                "description": "Optional parameter of `str_replace` command containing the new string (if not given, no string will be added). Required parameter of `insert` command containing the string to insert.",
                "type": "string",
            },
            "insert_line": {
                "description": "Required parameter of `insert` command. The `new_str` will be inserted AFTER the line `insert_line` of `path`.",
                "type": "integer",
            },
            "view_range": {
                "description": "Optional parameter of `view` command when `path` points to a file. If none is given, the full file is shown. If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. Indexing at 1 to start. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file.",
                "items": {"type": "integer"},
                "type": "array",
            },
        },
        "required": ["command", "path"],
    }
    _file_history: DefaultDict[PathLike, List[str]] = defaultdict(list)
    _local_operator: LocalFileOperator = LocalFileOperator()
    _sandbox_operator: SandboxFileOperator = SandboxFileOperator()

    # def _get_operator(self, use_sandbox: bool) -> FileOperator:
    def _get_operator(self) -> FileOperator:
        """Get the appropriate file operator based on execution mode."""
        return (
            self._sandbox_operator
            if config.sandbox.use_sandbox
            else self._local_operator
        )

    async def execute(
        self,
        *,
        command: Command,
        path: str,
        file_text: str | None = None,
        view_range: list[int] | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
        insert_line: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute a file operation command."""
        # Get the appropriate file operator
        operator = self._get_operator()

        # Validate path and command combination
        await self.validate_path(command, Path(path), operator)

        # --- 新增代码开始 ---
        # [核心修复]：如果是相对路径，自动拼接到 workspace_root
        if not os.path.isabs(path):
            # 优先使用 config 中定义的 workspace，如果没有则用当前目录
            base_dir = getattr(config, "workspace", os.getcwd())
            path = os.path.join(base_dir, path)
            
        # [核心修复]：确保目录存在，不存在则创建
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                return ToolResult(error=f"Failed to create directory {directory}: {e}")
            
        # Execute the appropriate command
        if command == "view":
            result = await self.view(path, view_range, operator)
        # elif command == "create":
        #     # 3. 强制覆盖模式 (解决 "File already exists" 错误)
        #     try:
        #         # 使用 'w' 模式，如果文件存在直接覆盖
        #         async with aiofiles.open(path, 'w', encoding='utf-8') as f:
        #             await f.write(file_text)
        #         return ToolResult(output=f"File successfully saved to {path}")
        #     except Exception as e:
        #         return ToolResult(error=f"Write failed: {e}")
            
        elif command == "create":
            if file_text is None:
                raise ToolError("Parameter `file_text` is required for command: create")
            await operator.write_file(path, file_text)
            self._file_history[path].append(file_text)
            result = ToolResult(output=f"File created successfully at: {path}")
        elif command == "str_replace":
            if old_str is None:
                raise ToolError(
                    "Parameter `old_str` is required for command: str_replace"
                )
            result = await self.str_replace(path, old_str, new_str, operator)
        elif command == "insert":
            if insert_line is None:
                raise ToolError(
                    "Parameter `insert_line` is required for command: insert"
                )
            if new_str is None:
                raise ToolError("Parameter `new_str` is required for command: insert")
            result = await self.insert(path, insert_line, new_str, operator)
        elif command == "undo_edit":
            result = await self.undo_edit(path, operator)
        else:
            # This should be caught by type checking, but we include it for safety
            raise ToolError(
                f'Unrecognized command {command}. The allowed commands for the {self.name} tool are: {", ".join(get_args(Command))}'
            )

        return str(result)

    async def validate_path(
        self, command: str, path: Path, operator: FileOperator
    ) -> None:
        """Validate path and command combination based on execution environment."""
        # Check if path is absolute
        if not path.is_absolute():
            raise ToolError(f"The path {path} is not an absolute path")

        # Only check if path exists for non-create commands
        if command != "create":
            if not await operator.exists(path):
                raise ToolError(
                    f"The path {path} does not exist. Please provide a valid path."
                )

            # Check if path is a directory
            is_dir = await operator.is_directory(path)
            if is_dir and command != "view":
                raise ToolError(
                    f"The path {path} is a directory and only the `view` command can be used on directories"
                )

        # Check if file exists for create command
        elif command == "create":
            exists = await operator.exists(path)
            if exists:
                raise ToolError(
                    f"File already exists at: {path}. Cannot overwrite files using command `create`."
                )

    async def view(
        self,
        path: PathLike,
        view_range: Optional[List[int]] = None,
        operator: FileOperator = None,
    ) -> CLIResult:
        """Display file or directory content."""
        # Determine if path is a directory
        is_dir = await operator.is_directory(path)

        if is_dir:
            # Directory handling
            if view_range:
                raise ToolError(
                    "The `view_range` parameter is not allowed when `path` points to a directory."
                )

            return await self._view_directory(path, operator)
        else:
            # File handling
            return await self._view_file(path, operator, view_range)

    @staticmethod
    async def _view_directory(path: PathLike, operator: FileOperator) -> CLIResult:
        """Display directory contents."""
        find_cmd = f"find {path} -maxdepth 2 -not -path '*/\\.*'"

        # Execute command using the operator
        returncode, stdout, stderr = await operator.run_command(find_cmd)

        if not stderr:
            stdout = (
                f"Here's the files and directories up to 2 levels deep in {path}, "
                f"excluding hidden items:\n{stdout}\n"
            )

        return CLIResult(output=stdout, error=stderr)

    async def _view_file(
        self,
        path: PathLike,
        operator: FileOperator,
        view_range: Optional[List[int]] = None,
    ) -> CLIResult:
        """Display file content, optionally within a specified line range."""
        # Read file content
        file_content = await operator.read_file(path)
        init_line = 1

        # Apply view range if specified
        if view_range:
            if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
                raise ToolError(
                    "Invalid `view_range`. It should be a list of two integers."
                )

            file_lines = file_content.split("\n")
            n_lines_file = len(file_lines)
            init_line, final_line = view_range

            # Validate view range
            if init_line < 1 or init_line > n_lines_file:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its first element `{init_line}` should be "
                    f"within the range of lines of the file: {[1, n_lines_file]}"
                )
            if final_line > n_lines_file:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be "
                    f"smaller than the number of lines in the file: `{n_lines_file}`"
                )
            if final_line != -1 and final_line < init_line:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be "
                    f"larger or equal than its first `{init_line}`"
                )

            # Apply range
            if final_line == -1:
                file_content = "\n".join(file_lines[init_line - 1 :])
            else:
                file_content = "\n".join(file_lines[init_line - 1 : final_line])

        # Format and return result
        return CLIResult(
            output=self._make_output(file_content, str(path), init_line=init_line)
        )

    async def str_replace(
        self,
        path: PathLike,
        old_str: str,
        new_str: Optional[str] = None,
        operator: FileOperator = None,
    ) -> CLIResult:
        """Replace a unique string in a file with a new string."""
        # Read file content and expand tabs
        file_content = (await operator.read_file(path)).expandtabs()
        old_str = old_str.expandtabs()
        new_str = new_str.expandtabs() if new_str is not None else ""

        # Check if old_str is unique in the file
        occurrences = file_content.count(old_str)
        if occurrences == 0:
            raise ToolError(
                f"No replacement was performed, old_str `{old_str}` did not appear verbatim in {path}."
            )
        elif occurrences > 1:
            # Find line numbers of occurrences
            file_content_lines = file_content.split("\n")
            lines = [
                idx + 1
                for idx, line in enumerate(file_content_lines)
                if old_str in line
            ]
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str `{old_str}` "
                f"in lines {lines}. Please ensure it is unique"
            )

        # Replace old_str with new_str
        new_file_content = file_content.replace(old_str, new_str)

        # Write the new content to the file
        await operator.write_file(path, new_file_content)

        # Save the original content to history
        self._file_history[path].append(file_content)

        # Create a snippet of the edited section
        replacement_line = file_content.split(old_str)[0].count("\n")
        start_line = max(0, replacement_line - SNIPPET_LINES)
        end_line = replacement_line + SNIPPET_LINES + new_str.count("\n")
        snippet = "\n".join(new_file_content.split("\n")[start_line : end_line + 1])

        # Prepare the success message
        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(
            snippet, f"a snippet of {path}", start_line + 1
        )
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

        return CLIResult(output=success_msg)


    # async def insert(
    #     self,
    #     path: PathLike,
    #     insert_line: int,
    #     new_str: str,
    #     operator: FileOperator = None,
    # ) -> CLIResult:
    #     """Insert text at a specific line in a file."""
    #     # Read and prepare content
    #     file_text = (await operator.read_file(path)).expandtabs()
    #     new_str = new_str.expandtabs()
    #     file_text_lines = file_text.split("\n")
    #     n_lines_file = len(file_text_lines)

    #     # Validate insert_line
    #     if insert_line < 0 or insert_line > n_lines_file:
    #         raise ToolError(
    #             f"Invalid `insert_line` parameter: {insert_line}. It should be within "
    #             f"the range of lines of the file: {[0, n_lines_file]}"
    #         )

    #     # Perform insertion
    #     new_str_lines = new_str.split("\n")
    #     new_file_text_lines = (
    #         file_text_lines[:insert_line]
    #         + new_str_lines
    #         + file_text_lines[insert_line:]
    #     )

    #     # Create a snippet for preview
    #     snippet_lines = (
    #         file_text_lines[max(0, insert_line - SNIPPET_LINES) : insert_line]
    #         + new_str_lines
    #         + file_text_lines[insert_line : insert_line + SNIPPET_LINES]
    #     )

    #     # Join lines and write to file
    #     new_file_text = "\n".join(new_file_text_lines)
    #     snippet = "\n".join(snippet_lines)

    #     await operator.write_file(path, new_file_text)
    #     self._file_history[path].append(file_text)

    #     # Prepare success message
    #     success_msg = f"The file {path} has been edited. "
    #     success_msg += self._make_output(
    #         snippet,
    #         "a snippet of the edited file",
    #         max(1, insert_line - SNIPPET_LINES + 1),
    #     )
    #     success_msg += "Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."

    #     return CLIResult(output=success_msg)
    async def insert(
        self,
        path: str,
        insert_line: Union[int, str],  # ← 改为 Union 类型
        new_str: str,
        operator: FileOperator,
    ) -> str:
        """
        Insert new_str at the specified line in the file.
        
        Args:
            path: File path
            insert_line: Line number (int) or special value ("start", "end")
            new_str: Content to insert
            operator: File operator
        """
        # 1. 读取文件
        content = await operator.read_file(path)
        lines = content.split("\n")
        n_lines_file = len(lines)
        
        # 🔥 2. 处理特殊字符串值
        if isinstance(insert_line, str):
            insert_line_lower = insert_line.lower().strip()
            if insert_line_lower == "end":
                insert_line = n_lines_file
            elif insert_line_lower == "start" or insert_line_lower == "beginning":
                insert_line = 0
            else:
                # 尝试转换为整数
                try:
                    insert_line = int(insert_line)
                except ValueError:
                    raise ValueError(
                        f"Invalid insert_line value: '{insert_line}'. "
                        f"Expected: integer, 'start', or 'end'"
                    )
        
        # 3. 确保是整数
        insert_line = int(insert_line)
        
        # 4. 验证范围
        if insert_line < 0 or insert_line > n_lines_file:
            raise ValueError(
                f"insert_line must be between 0 and {n_lines_file}, got {insert_line}"
            )
        
        # 5. 插入新内容
        new_lines = lines[:insert_line] + [new_str] + lines[insert_line:]
        new_content = "\n".join(new_lines)
        
        # 6. 写回文件
        await operator.write_file(path, new_content)
        
        # 7. 生成预览
        start_line = max(0, insert_line - 3)
        end_line = min(len(new_lines), insert_line + 5)
        preview_lines = []
        for i in range(start_line, end_line):
            preview_lines.append(f"{i+1:6d}\t{new_lines[i]}")
        preview = "\n".join(preview_lines)
        
        return (
            f"The file {path} has been edited. Here's the result of running `cat -n` "
            f"on a snippet of the edited file:\n{preview}\n\n"
            f"Review the changes and make sure they are as expected "
            f"(correct indentation, no duplicate lines, etc). Edit the file again if necessary."
        )

    async def undo_edit(
        self, path: PathLike, operator: FileOperator = None
    ) -> CLIResult:
        """Revert the last edit made to a file."""
        if not self._file_history[path]:
            raise ToolError(f"No edit history found for {path}.")

        old_text = self._file_history[path].pop()
        await operator.write_file(path, old_text)

        return CLIResult(
            output=f"Last edit to {path} undone successfully. {self._make_output(old_text, str(path))}"
        )

    def _make_output(
        self,
        file_content: str,
        file_descriptor: str,
        init_line: int = 1,
        expand_tabs: bool = True,
    ) -> str:
        """Format file content for display with line numbers."""
        file_content = maybe_truncate(file_content)
        if expand_tabs:
            file_content = file_content.expandtabs()

        # Add line numbers to each line
        file_content = "\n".join(
            [
                f"{i + init_line:6}\t{line}"
                for i, line in enumerate(file_content.split("\n"))
            ]
        )

        return (
            f"Here's the result of running `cat -n` on {file_descriptor}:\n"
            + file_content
            + "\n"
        )
