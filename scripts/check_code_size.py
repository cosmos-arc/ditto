#!/usr/bin/env python3
"""
代码规模检查脚本

检查项：
- 单文件行数 ≤ 800
- 类 public 方法数 ≤ 20

使用方式：
    uv run --no-sync python scripts/check_code_size.py
    uv run --no-sync python scripts/check_code_size.py --verbose
"""

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClassInfo:
    """类信息"""

    name: str
    line: int
    public_methods: int
    total_methods: int


@dataclass
class FileInfo:
    """文件信息"""

    path: Path
    lines: int
    classes: list[ClassInfo]


class CodeSizeChecker:
    """代码规模检查器"""

    def __init__(
        self,
        max_file_lines: int = 800,
        max_public_methods: int = 20,
        exclude_patterns: list[str] | None = None,
    ):
        self.max_file_lines = max_file_lines
        self.max_public_methods = max_public_methods
        self.exclude_patterns = exclude_patterns or ["*Provider*"]
        self.issues: list[dict] = []

    def is_excluded_class(self, class_name: str) -> bool:
        """判断类是否应被排除"""
        for pattern in self.exclude_patterns:
            if pattern.replace("*", "") in class_name:
                return True
        return False

    def is_public_method(self, name: str) -> bool:
        """判断是否为 public 方法"""
        return not name.startswith("_")

    def count_class_methods(self, node: ast.ClassDef) -> tuple[int, int]:
        """
        统计类的方法数

        Returns:
            (public_methods, total_methods)
        """
        public = 0
        total = 0

        for item in node.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                total += 1
                if self.is_public_method(item.name):
                    public += 1

        return public, total

    def check_file(self, path: Path) -> FileInfo | None:
        """检查单个文件"""
        try:
            source = path.read_text(encoding="utf-8")

            # 统计物理行数
            lines = len(source.splitlines())

            # 解析 AST
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError:
                return None

            # 提取类信息
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    public_methods, total_methods = self.count_class_methods(node)
                    classes.append(
                        ClassInfo(
                            name=node.name,
                            line=node.lineno,
                            public_methods=public_methods,
                            total_methods=total_methods,
                        )
                    )

            return FileInfo(path=path, lines=lines, classes=classes)

        except Exception:
            return None

    def check_directory(self, root: Path) -> list[FileInfo]:
        """检查目录下的所有 Python 文件"""
        results = []

        for py_file in root.rglob("*.py"):
            # 跳过测试文件和 __pycache__
            if (
                "test" in py_file.parts
                or "__pycache__" in py_file.parts
                or ".venv" in py_file.parts
                or ".pixi" in py_file.parts
            ):
                continue

            info = self.check_file(py_file)
            if info:
                results.append(info)

        return results

    def check(self) -> int:
        """执行检查并返回退出码"""
        # 扫描目录
        src_dirs = [
            Path.cwd() / "packages" / "foundation" / "src",
            Path.cwd() / "packages" / "data" / "src",
            Path.cwd() / "packages" / "core" / "src",
            Path.cwd() / "apps" / "port" / "src",
        ]

        all_files = []
        for src_dir in src_dirs:
            if src_dir.exists():
                all_files.extend(self.check_directory(src_dir))

        # 收集问题
        file_issues = []
        class_issues = []

        for info in all_files:
            # 检查文件行数
            if info.lines > self.max_file_lines:
                file_issues.append(info)

            # 检查类 public 方法数（排除特定模式的类）
            for cls in info.classes:
                if (
                    not self.is_excluded_class(cls.name)
                    and cls.public_methods > self.max_public_methods
                ):
                    class_issues.append((info, cls))

        # 输出报告
        self._print_report(file_issues, class_issues)

        # 返回退出码
        return 1 if (file_issues or class_issues) else 0

    def _print_report(
        self,
        file_issues: list[FileInfo],
        class_issues: list[tuple[FileInfo, ClassInfo]],
    ) -> None:
        """打印检查报告"""
        # Windows 兼容：使用 ASCII 字符
        print("Code Size Check Report")
        print()

        # 文件行数问题
        if file_issues:
            print(f"Files exceeding {self.max_file_lines} lines: {len(file_issues)}")
            for info in sorted(file_issues, key=lambda x: x.lines, reverse=True):
                rel_path = info.path.relative_to(Path.cwd())
                print(f"  [X] {rel_path}: {info.lines} lines")
        else:
            print(f"Files exceeding {self.max_file_lines} lines: 0")

        print()

        # 类方法数问题
        if class_issues:
            msg = f"Classes with >{self.max_public_methods} public methods: {len(class_issues)}"  # noqa: E501
            print(msg)
            for info, cls in sorted(
                class_issues, key=lambda x: x[1].public_methods, reverse=True
            ):
                rel_path = info.path.relative_to(Path.cwd())
                msg = f"  [!] {cls.name}: {cls.public_methods} public methods ({rel_path}:{cls.line})"  # noqa: E501
                print(msg)
        else:
            print(f"Classes with >{self.max_public_methods} public methods: 0")

        print()

        # 总结
        if file_issues or class_issues:
            print("[X] Issues found, please review and refactor")
        else:
            print("[OK] All checks passed!")


def main() -> int:
    """主函数"""
    parser = argparse.ArgumentParser(description="代码规模检查脚本")
    parser.add_argument(
        "--max-file-lines",
        type=int,
        default=800,
        help="单文件最大行数 (默认: 800)",
    )
    parser.add_argument(
        "--max-public-methods",
        type=int,
        default=20,
        help="类 public 方法最大数量 (默认: 20)",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        default=["*Provider*"],
        help="排除的类名模式 (可多次使用, 默认: *Provider*)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="详细输出模式",
    )

    args = parser.parse_args()

    checker = CodeSizeChecker(
        max_file_lines=args.max_file_lines,
        max_public_methods=args.max_public_methods,
        exclude_patterns=args.exclude,
    )

    return checker.check()


if __name__ == "__main__":
    sys.exit(main())
