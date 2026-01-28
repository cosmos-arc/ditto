#!/usr/bin/env python3
"""LSP 辅助脚本 - 使用 Pyright LSP (替代 Jedi)

支持的功能:
    goto       - 跳转到定义
    refs       - 查找所有引用
    symbols    - 获取文档符号（类、函数、变量）
    hover      - 获取类型和文档信息（类似鼠标悬停）
    complete   - 代码补全建议
    diagnose   - Pyright 类型诊断
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def create_lsp_server(project_root: Path):
    """创建 LSP 服务器连接"""
    try:
        from multilspy import SyncLanguageServer
        from multilspy.multilspy_config import MultilspyConfig
        from multilspy.multilspy_logger import MultilspyLogger
    except ImportError:
        raise RuntimeError(
            "multilspy 未安装。运行: pixi run -e dev pip install multilspy"
        )

    # 配置使用 Pyright
    config_dict = {
        "code_language": "python",
        # BasedPyright 配置（Pyright fork，更严格的类型检查）
        "lsp_server": {
            "command": "basedpyright-langserver",
            "args": ["--stdio"],
            "initializationOptions": {},
        },
    }

    config = MultilspyConfig.from_dict(config_dict)
    logger = MultilspyLogger()

    # 注意：每次操作都需要启动/停止服务器
    # 在生产环境中可以保持长连接
    lsp = SyncLanguageServer.create(config, logger, str(project_root))
    return lsp


def goto_definition(file_path: str, line: int, column: int) -> dict:
    """跳转到定义"""
    project_root = Path.cwd()
    lsp = create_lsp_server(project_root)

    try:
        with lsp.start_server():
            # Pyright 使用 0-based 行号
            result = lsp.request_definition(file_path, line - 1, column)
            if not result:
                return {"error": "未找到定义"}

            results = []
            for r in result:
                results.append({
                    "file": r["uri"],
                    "line": r["range"]["start"]["line"] + 1,  # 转换回 1-based
                    "column": r["range"]["start"]["character"],
                })
            return {"results": results}
    except Exception as e:
        return {"error": f"goto 失败: {e}"}


def find_references(file_path: str, line: int, column: int) -> dict:
    """查找引用"""
    project_root = Path.cwd()
    lsp = create_lsp_server(project_root)

    try:
        with lsp.start_server():
            result = lsp.request_references(file_path, line - 1, column)
            if not result:
                return {"error": "未找到引用"}

            results = []
            for r in result:
                results.append({
                    "file": r["uri"],
                    "line": r["range"]["start"]["line"] + 1,
                    "column": r["range"]["start"]["character"],
                })
            return {"results": results}
    except Exception as e:
        return {"error": f"refs 失败: {e}"}


def document_symbols(file_path: str) -> dict:
    """获取文档符号"""
    project_root = Path.cwd()
    lsp = create_lsp_server(project_root)

    try:
        with lsp.start_server():
            result = lsp.request_document_symbols(file_path)
            if not result or not result[0]:
                return {"class": [], "function": [], "variable": []}

            # multilspy 返回 tuple: (symbols_list, None)
            symbols = result[0] if isinstance(result, tuple) else result

            # 按类型分组
            by_type = {"class": [], "function": [], "variable": [], "module": []}
            for symbol in symbols:
                kind = symbol.get("kind", 0)
                name = symbol.get("name", "")
                range_info = symbol.get("range", {})
                location = symbol.get("location", {})
                detail = symbol.get("detail", "")

                # LSP SymbolKind 映射
                kind_map = {
                    1: "file",
                    2: "module",
                    3: "namespace",
                    4: "package",
                    5: "class",
                    6: "method",
                    7: "property",
                    8: "field",
                    9: "constructor",
                    10: "enum",
                    11: "interface",
                    12: "function",
                    13: "variable",
                    14: "constant",
                    15: "string",
                    16: "number",
                    17: "boolean",
                    18: "array",
                    19: "object",
                    20: "key",
                    21: "null",
                    22: "enum_member",
                    23: "struct",
                    24: "event",
                    25: "operator",
                    26: "type_parameter",
                }

                symbol_type = kind_map.get(kind, "unknown")

                item = {
                    "name": name,
                    "detail": detail,
                    "kind": kind,
                    "kind_name": symbol_type,
                }

                if location:
                    item["line"] = location["range"]["start"]["line"] + 1
                elif range_info:
                    item["line"] = range_info["start"]["line"] + 1

                # 分类
                if symbol_type in by_type:
                    by_type[symbol_type].append(item)
                elif kind == 6:  # method
                    by_type["class"].append(item)
                elif kind == 12:  # function
                    by_type["function"].append(item)

            return by_type
    except Exception as e:
        return {"error": f"symbols 失败: {e}"}


def hover(file_path: str, line: int, column: int) -> dict:
    """获取悬停信息"""
    project_root = Path.cwd()
    lsp = create_lsp_server(project_root)

    try:
        with lsp.start_server():
            result = lsp.request_hover(file_path, line - 1, column)
            if not result or not result.get("contents"):
                return {"error": "无悬停信息"}

            contents = result["contents"]
            if isinstance(contents, str):
                return {"text": contents}
            elif isinstance(contents, list):
                return {"text": "\n".join(c.get("value", "") for c in contents)}
            elif isinstance(contents, dict):
                return {"text": contents.get("value", str(contents))}

            return {"text": str(contents)}
    except Exception as e:
        return {"error": f"hover 失败: {e}"}


def complete(file_path: str, line: int, column: int) -> dict:
    """代码补全"""
    project_root = Path.cwd()
    lsp = create_lsp_server(project_root)

    try:
        with lsp.start_server():
            result = lsp.request_completions(file_path, line - 1, column)
            if not result or not result.get("items"):
                return {"count": 0, "results": []}

            items = result["items"][:50]  # 限制数量
            results = []
            for item in items:
                results.append({
                    "label": item.get("label", ""),
                    "kind": item.get("kind", 0),
                    "detail": item.get("detail", ""),
                    "documentation": item.get("documentation", ""),
                })
            return {"count": len(result.get("items", [])), "results": results}
    except Exception as e:
        return {"error": f"complete 失败: {e}"}


def run_diagnostics(file_path: str = None) -> dict:
    """Pyright 类型诊断"""
    import subprocess

    project_root = Path.cwd()
    cmd = ["pixi", "run", "-e", "dev", "pyright", "--outputjson"]

    if file_path:
        cmd.append(file_path)
    else:
        cmd.append(str(project_root / "packages"))

    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    try:
        output = json.loads(result.stdout)
        diagnostics = []
        for file_diag in output.get("diagnostics", []):
            diagnostics.append({
                "file": file_diag.get("file"),
                "severity": file_diag.get("severity"),
                "message": file_diag.get("message"),
                "line": file_diag.get("line"),
                "column": file_diag.get("column"),
                "rule": file_diag.get("rule"),
            })
        return {
            "summary": output.get("summary", {}),
            "diagnostics": diagnostics,
        }
    except Exception as e:
        return {"error": f"解析输出失败: {e}\nstdout: {result.stdout}"}


def main():
    parser = argparse.ArgumentParser(
        description="LSP 辅助工具 (Pyright) - 为 Claude Code 提供代码导航能力",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # goto
    goto_parser = subparsers.add_parser("goto", help="跳转到定义")
    goto_parser.add_argument("file", help="文件路径")
    goto_parser.add_argument("line", type=int, help="行号 (从1开始)")
    goto_parser.add_argument("column", type=int, help="列号 (从0开始)")

    # refs
    refs_parser = subparsers.add_parser("refs", help="查找引用")
    refs_parser.add_argument("file", help="文件路径")
    refs_parser.add_argument("line", type=int, help="行号")
    refs_parser.add_argument("column", type=int, help="列号")

    # symbols
    symbols_parser = subparsers.add_parser("symbols", help="文档符号")
    symbols_parser.add_argument("file", help="文件路径")

    # hover
    hover_parser = subparsers.add_parser("hover", help="获取类型和文档信息")
    hover_parser.add_argument("file", help="文件路径")
    hover_parser.add_argument("line", type=int, help="行号")
    hover_parser.add_argument("column", type=int, help="列号")

    # complete
    complete_parser = subparsers.add_parser("complete", help="代码补全建议")
    complete_parser.add_argument("file", help="文件路径")
    complete_parser.add_argument("line", type=int, help="行号")
    complete_parser.add_argument("column", type=int, help="列号")

    # diagnose
    diagnose_parser = subparsers.add_parser("diagnose", help="Pyright 类型诊断")
    diagnose_parser.add_argument("file", nargs="?", help="文件路径 (可选)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    result = {}
    if args.command == "goto":
        result = goto_definition(args.file, args.line, args.column)
    elif args.command == "refs":
        result = find_references(args.file, args.line, args.column)
    elif args.command == "symbols":
        result = document_symbols(args.file)
    elif args.command == "hover":
        result = hover(args.file, args.line, args.column)
    elif args.command == "complete":
        result = complete(args.file, args.line, args.column)
    elif args.command == "diagnose":
        result = run_diagnostics(args.file)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
