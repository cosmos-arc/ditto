"""分析代码复杂度的脚本。"""

import ast
import subprocess
import sys
from pathlib import Path


def get_changed_files(base: str, head: str) -> list[Path]:
    """获取改动的 Python 文件列表。"""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line) for line in result.stdout.strip().splitlines() if line]


def analyze_file(path: Path) -> dict:
    """分析单个文件的复杂度指标。"""
    if not path.exists():
        return {}

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return {"error": "Failed to parse"}

    issues = {
        "deep_nesting": [],  # 4层以上嵌套
        "long_functions": [],  # 超过50行
        "many_params": [],  # 超过5个参数
        "many_locals": [],  # 超过10个局部变量
        "high_cyclomatic": [],  # 圈复杂度高
    }

    for node in ast.walk(tree):
        # 检查函数和方法
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 获取函数行数
            if hasattr(node, "end_lineno") and node.end_lineno:
                func_lines = node.end_lineno - node.lineno
            else:
                func_lines = 0

            # 参数数量（不包括self/cls）
            params = [
                a
                for a in node.args.args
                if a.arg not in ("self", "cls")
            ]
            param_count = len(params) + len(node.args.kwonlyargs) + len(node.args.posonlyargs)

            # 局部变量数量
            local_vars = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    local_vars.add(child.id)
            local_count = len(local_vars)

            # 圈复杂度（简化版：决策点数量 + 1）
            complexity = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                    complexity += 1
                elif isinstance(child, ast.ExceptHandler):
                    complexity += 1
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1

            # 记录问题
            if func_lines > 50:
                issues["long_functions"].append(
                    {"name": node.name, "line": node.lineno, "lines": func_lines}
                )

            if param_count > 5:
                issues["many_params"].append(
                    {"name": node.name, "line": node.lineno, "params": param_count}
                )

            if local_count > 10:
                issues["many_locals"].append(
                    {"name": node.name, "line": node.lineno, "locals": local_count}
                )

            if complexity > 10:
                issues["high_cyclomatic"].append(
                    {"name": node.name, "line": node.lineno, "complexity": complexity}
                )

            # 检查嵌套深度（只在当前函数范围内）
            def check_nesting(
                func_node: ast.FunctionDef | ast.AsyncFunctionDef,
                node: ast.AST,
                depth: int = 0,
            ) -> None:
                # 检查是否超过嵌套深度
                if depth > 3:
                    # 只记录在函数范围内的深层嵌套
                    if hasattr(node, "lineno"):
                        issues["deep_nesting"].append(
                            {
                                "name": func_node.name,
                                "line": node.lineno,
                                "depth": depth,
                                "type": node.__class__.__name__,
                            }
                        )
                    return

                for child in ast.iter_child_nodes(node):
                    if isinstance(
                        child,
                        (
                            ast.If,
                            ast.While,
                            ast.For,
                            ast.AsyncFor,
                            ast.With,
                            ast.AsyncWith,
                            ast.Try,
                        ),
                    ):
                        check_nesting(func_node, child, depth + 1)
                    elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                        # 遇到嵌套函数，不增加深度计数
                        pass
                    else:
                        check_nesting(func_node, child, depth)

            check_nesting(node, node)

    return issues


def main() -> None:
    """主函数。"""
    base = "dd60280226b68f34f65068b20e904ea004aeb13d"
    head = "61434c1adb8c9009d5bde1b3d62339741223278d"

    print("正在获取改动的文件列表...")
    files = get_changed_files(base, head)
    print(f"找到 {len(files)} 个改动的 Python 文件\n")

    # 项目根目录
    project_root = Path.cwd()

    all_issues = {
        "deep_nesting": [],
        "long_functions": [],
        "many_params": [],
        "many_locals": [],
        "high_cyclomatic": [],
    }

    for i, file_path in enumerate(files, 1):
        # 转换为绝对路径
        abs_path = file_path if file_path.is_absolute() else project_root / file_path

        if not abs_path.exists():
            continue

        # 获取相对路径用于显示
        try:
            rel_path = abs_path.relative_to(project_root)
        except ValueError:
            rel_path = file_path

        print(f"[{i}/{len(files)}] 分析 {rel_path}...")
        issues = analyze_file(abs_path)

        for category, items in issues.items():
            if items:
                for item in items:
                    item["file"] = str(rel_path)
                    all_issues[category].append(item)

    print("\n" + "=" * 80)
    print("Code Complexity Analysis Results")
    print("=" * 80)

    if not any(all_issues.values()):
        print("\n[PASS] No significant complexity issues found!")
        return

    if all_issues["deep_nesting"]:
        print(f"\n[ISSUE] Deep nesting (>3 levels): {len(all_issues['deep_nesting'])} occurrences")
        for item in all_issues["deep_nesting"][:10]:  # Only show first 10
            type_str = item.get("type", "block")
            print(f"  - {item['file']}:{item['line']} - in {item['name']}() (depth={item['depth']}, {type_str})")

    if all_issues["long_functions"]:
        print(f"\n[WARN] Long functions (>50 lines): {len(all_issues['long_functions'])} occurrences")
        for item in all_issues["long_functions"][:10]:
            print(f"  - {item['file']}:{item['line']} - {item['name']}() ({item['lines']} lines)")

    if all_issues["many_params"]:
        print(f"\n[WARN] Too many parameters (>5): {len(all_issues['many_params'])} occurrences")
        for item in all_issues["many_params"][:10]:
            print(f"  - {item['file']}:{item['line']} - {item['name']}() ({item['params']} params)")

    if all_issues["many_locals"]:
        print(f"\n[WARN] Too many local variables (>10): {len(all_issues['many_locals'])} occurrences")
        for item in all_issues["many_locals"][:10]:
            print(f"  - {item['file']}:{item['line']} - {item['name']}() ({item['locals']} vars)")

    if all_issues["high_cyclomatic"]:
        print(f"\n[WARN] High cyclomatic complexity (>10): {len(all_issues['high_cyclomatic'])} occurrences")
        for item in all_issues["high_cyclomatic"][:10]:
            print(f"  - {item['file']}:{item['line']} - {item['name']}() (complexity={item['complexity']})")


if __name__ == "__main__":
    main()
