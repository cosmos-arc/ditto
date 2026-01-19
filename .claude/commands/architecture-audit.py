"""
Architecture Audit - 全库架构审计脚本

LSP 优先的架构和工程质量审计，生成完整报告。
"""

import ast
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


class ArchitectureAuditor:
    """架构审计器"""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.docs_dir = root_dir / "docs"
        self.reviews_dir = self.docs_dir / "reviews"
        self.findings: list[dict[str, Any]] = []
        self.import_graph: dict[str, set[str]] = defaultdict(set)
        self.module_info: dict[str, dict[str, Any]] = {}

    def run(self) -> str:
        """运行完整审计"""
        print("🔍 开始架构审计...")

        # 1. 运行代码质量检查
        self._run_quality_checks()

        # 2. 构建导入图
        self._build_import_graph()

        # 3. LSP 语义分析
        self._run_lsp_analysis()

        # 4. 传统模式匹配
        self._run_pattern_matching()

        # 5. 生成报告
        report_path = self._generate_report()

        # 6. 输出摘要
        self._print_summary()

        return str(report_path)

    def _build_import_graph(self) -> None:
        """构建导入关系图"""
        print("📊 构建导入关系图...")

        packages_dir = self.root_dir / "packages"
        apps_dir = self.root_dir / "apps"

        for base_dir in [packages_dir, apps_dir]:
            if not base_dir.exists():
                continue

            for py_file in base_dir.rglob("*.py"):
                self._analyze_file_imports(py_file)

        # 检测循环依赖
        self._detect_circular_dependencies()

    def _analyze_file_imports(self, file_path: Path) -> None:
        """分析单个文件的导入"""
        rel_path = file_path.relative_to(self.root_dir)

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            # 获取模块名
            module_name = str(rel_path).replace(os.sep, ".").replace(".py", "")

            # 分析导入
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_module = alias.name
                        self.import_graph[module_name].add(imported_module)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_module = node.module
                        self.import_graph[module_name].add(imported_module)

            # 收集模块信息
            self._collect_module_info(file_path, tree, module_name)

        except Exception as e:
            # 记录解析错误
            self.findings.append(
                {
                    "id": "PARSE-001",
                    "severity": "Low",
                    "category": "Parsing",
                    "location": str(rel_path),
                    "evidence": f"无法解析文件: {e}",
                    "why": "文件可能存在语法错误",
                    "fix": "修复语法错误",
                    "effort": "S",
                }
            )

    def _collect_module_info(self, file_path: Path, tree: ast.AST, module_name: str) -> None:
        """收集模块信息"""
        info = {
            "file": file_path,
            "classes": [],
            "functions": [],
            "imports": set(),
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # 计算类规模
                class_lines = node.end_lineno - node.lineno if node.end_lineno else 0
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]

                info["classes"].append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "lines": class_lines,
                        "methods": len(methods),
                    }
                )

                # 检查类规模
                if class_lines > 300:
                    self.findings.append(
                        {
                            "id": f"DESIGN-001-{node.name}",
                            "severity": "Medium",
                            "category": "Design",
                            "location": f"{module_name}:{node.lineno}",
                            "evidence": f"class {node.name} 有 {class_lines} 行，{len(methods)} 个方法",
                            "why": "类过大影响可维护性，违反单一职责原则",
                            "fix": "将大类拆分为多个职责单一的小类",
                            "effort": "L",
                        }
                    )

            elif isinstance(node, ast.FunctionDef) and not hasattr(node, "parent_class"):
                info["functions"].append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                    }
                )

        self.module_info[module_name] = info

    def _detect_circular_dependencies(self) -> None:
        """检测循环依赖"""
        print("🔍 检测循环依赖...")

        visited = set()
        recursion_stack = set()
        cycles = []

        def dfs(node: str, path: list[str]) -> None:
            if node in recursion_stack:
                # 找到环
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            recursion_stack.add(node)

            for neighbor in self.import_graph.get(node, set()):
                # 只检查项目内部模块
                if neighbor.startswith(("packages.", "apps.")):
                    dfs(neighbor, path + [node])

            recursion_stack.remove(node)

        for module in self.import_graph:
            if module not in visited:
                dfs(module, [])

        if cycles:
            for cycle in cycles:
                self.findings.append(
                    {
                        "id": "ARCH-002",
                        "severity": "Blocker",
                        "category": "Layering",
                        "location": " -> ".join(cycle),
                        "evidence": "循环依赖",
                        "why": "循环依赖会导致模块无法独立测试和使用",
                        "fix": "引入接口层或重构模块依赖关系",
                        "effort": "L",
                    }
                )

    def _run_quality_checks(self) -> None:
        """运行代码质量检查"""
        print("📋 运行代码质量检查...")

        checks = [
            ("lint", ["pixi", "run", "-e", "dev", "lint"]),
            ("type", ["pixi", "run", "-e", "dev", "type"]),
            ("test-unit", ["pixi", "run", "-e", "dev", "test", "--unit"]),
        ]

        for name, cmd in checks:
            try:
                result = subprocess.run(
                    cmd, cwd=self.root_dir, capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    self.findings.append(
                        {
                            "id": f"QC-{name.upper()}",
                            "severity": "High",
                            "category": "QualityCheck",
                            "location": f"CI/{name}",
                            "evidence": result.stderr[:500],
                            "why": f"{name} 检查失败",
                            "fix": "修复相应的 lint/type/test 错误",
                            "effort": "L",
                        }
                    )
            except subprocess.TimeoutExpired:
                self.findings.append(
                    {
                        "id": f"QC-{name.upper()}-TIMEOUT",
                        "severity": "Medium",
                        "category": "QualityCheck",
                        "location": f"CI/{name}",
                        "evidence": "检查超时",
                        "why": f"{name} 执行时间过长",
                        "fix": "优化测试或调整超时设置",
                        "effort": "M",
                    }
                )

    def _run_lsp_analysis(self) -> None:
        """LSP 语义分析"""
        print("🔎 运行 LSP 语义分析...")

        # 检查层级穿透（port 层依赖 infra 细节）
        self._check_layer_violation()

        # 检查 Protocol 是否被使用
        self._check_unused_protocols()

    def _check_layer_violation(self) -> None:
        """检查层级穿透"""
        # port 层模块
        port_modules = [m for m in self.import_graph.keys() if m.startswith("apps.port.")]

        for module in port_modules:
            for dep in self.import_graph.get(module, set()):
                # 检查是否依赖了 packages 中的具体实现
                if dep.startswith("packages.datahub.stores.") or dep.startswith("packages.datahub.providers."):
                    self.findings.append(
                        {
                            "id": "ARCH-001",
                            "severity": "High",
                            "category": "Layering",
                            "location": f"{module} -> {dep}",
                            "evidence": "应用层直接依赖数据访问层的具体实现",
                            "why": "违反分层架构原则，应该通过 DataHub Facade 访问",
                            "fix": "使用 DataHub 提供的接口，而非直接访问 Store/Source",
                            "effort": "M",
                        }
                    )

    def _check_unused_protocols(self) -> None:
        """检查未使用的 Protocol"""
        print("🔍 检查未使用的 Protocol...")

        # 搜索 Protocol 定义
        result = subprocess.run(
            ["grep", "-r", "-n", "class.*Protocol", "packages/", "apps/"],
            cwd=self.root_dir,
            capture_output=True,
            text=True,
        )

        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                parts = line.split(":")
                if len(parts) >= 3:
                    file_path = parts[0]
                    line_num = parts[1]
                    content = ":".join(parts[2:])

                    # 提取 Protocol 名称
                    match = re.search(r"class\s+(\w+)\s*\(", content)
                    if match:
                        protocol_name = match.group(1)

                        # 检查是否被引用
                        ref_result = subprocess.run(
                            ["grep", "-r", protocol_name, "packages/", "apps/", "--exclude=*.md"],
                            cwd=self.root_dir,
                            capture_output=True,
                            text=True,
                        )

                        # 只有一行是定义本身，说明未被使用
                        if ref_result.stdout.count(protocol_name) <= 1:
                            self.findings.append(
                                {
                                    "id": "ENG-005",
                                    "severity": "Low",
                                    "category": "DeadCode",
                                    "location": f"{file_path}:{line_num}",
                                    "evidence": f"Protocol {protocol_name} 未被引用",
                                    "why": "未使用的 Protocol 是死代码，应该删除",
                                    "fix": f"删除 {protocol_name} Protocol 定义",
                                    "effort": "S",
                                }
                            )

    def _run_pattern_matching(self) -> None:
        """传统模式匹配"""
        print("🔍 运行模式匹配检查...")

        # TYPE_CHECKING 检查
        self._check_type_checking()

        # 禁止的导入检查
        self._check_forbidden_imports()

        # 异常处理检查
        self._check_exception_handling()

        # 命名与概念检查
        self._check_naming_concepts()

    def _check_type_checking(self) -> None:
        """检查 TYPE_CHECKING 使用"""
        patterns = [
            (r"if TYPE_CHECKING:\s*pass", "Empty TYPE_CHECKING block", "Low"),
            (r"from typing import TYPE_CHECKING", "TYPE_CHECKING import", "Medium"),
        ]

        for pattern, desc, severity in patterns:
            result = subprocess.run(
                ["grep", "-r", "-n", pattern, "packages/", "apps/"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                lines = result.stdout.strip().split("\n")[:5]  # 限制显示数量
                for line in lines:
                    self.findings.append(
                        {
                            "id": "ENG-006",
                            "severity": severity,
                            "category": "Typing",
                            "location": line.split(":")[0] + ":" + line.split(":")[1],
                            "evidence": line,
                            "why": f"{desc}，无循环依赖情况下不需要延迟导入",
                            "fix": "改为直接导入",
                            "effort": "S",
                        }
                    )

    def _check_forbidden_imports(self) -> None:
        """检查禁止的导入"""
        forbidden = ["pandas", "sqlalchemy"]
        for module in forbidden:
            result = subprocess.run(
                ["grep", "-r", "-n", f"import {module}", "packages/", "apps/"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                self.findings.append(
                    {
                        "id": "ARCH-005",
                        "severity": "Blocker",
                        "category": "Dependency",
                        "evidence": result.stdout.split("\n")[0],
                        "why": f"禁止使用 {module}，违反项目约束",
                        "fix": f"替换为允许的类库（polars、duckdb 等）",
                        "effort": "M",
                    }
                )

    def _check_exception_handling(self) -> None:
        """检查异常处理"""
        # 检查 except Exception 无日志
        result = subprocess.run(
            ["grep", "-r", "-n", "except Exception:", "packages/", "apps/"],
            cwd=self.root_dir,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            self.findings.append(
                {
                    "id": "ENG-002",
                    "severity": "High",
                    "category": "Logging",
                    "evidence": result.stdout.split("\n")[0],
                    "why": "异常处理缺少错误详情记录，难以调试",
                    "fix": "添加 error_type、error_message 等字段到日志",
                    "effort": "M",
                }
            )

    def _check_naming_concepts(self) -> None:
        """检查命名与概念"""
        print("🔍 检查命名与概念...")

        # 1. 业务术语与技术术语混用检测
        self._check_business_technical_mixing()

        # 2. 同一概念多种表述检测
        self._check_concept_consistency()

        # 3. 命名风格一致性检测
        self._check_naming_style_consistency()

        # 4. 缩写规范检测
        self._check_abbreviation_consistency()

    def _check_business_technical_mixing(self) -> None:
        """检测业务层混用技术术语"""
        # 检测 Port 层是否混用 SQL、Parquet 等技术术语
        technical_terms = ["SQL", "Parquet", "SQLite", "Database", "Table"]
        patterns = [rf"class.*{term}.*(?:Loader|Writer|Reader|Manager)" for term in technical_terms]

        for i, pattern in enumerate(patterns, 1):
            result = subprocess.run(
                ["grep", "-r", "-n", "-E", pattern, "apps/port/"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                lines = result.stdout.strip().split("\n")[:3]  # 限制显示数量
                for line in lines:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        self.findings.append(
                            {
                                "id": f"NAM-00{i}",
                                "severity": "High",
                                "category": "Naming",
                                "location": f"apps/port/{parts[0]}:{parts[1]}",
                                "evidence": line,
                                "why": "Port 层不应混用技术术语，应使用业务概念",
                                "fix": "重命名为业务术语（如 BarDataLoader），技术细节由 DataHub 处理",
                                "effort": "M",
                            }
                        )

    def _check_concept_consistency(self) -> None:
        """检测同一概念的多种表述"""
        # 检测 Bar/Kline/Candlestick 等同一概念的不同表述
        concept_variants = {
            "Bar": ["Kline", "Candlestick"],
            "Quantity": ["Qty", "Quant"],
            "Volume": ["Vol"],
        }

        for concept, variants in concept_variants.items():
            # 检查是否存在变体
            for variant in variants:
                result = subprocess.run(
                    ["grep", "-r", "-l", rf"class\s+{variant}", "packages/", "apps/"],
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True,
                )
                if result.stdout:
                    self.findings.append(
                        {
                            "id": "NAM-010",
                            "severity": "Medium",
                            "category": "Naming",
                            "evidence": f"发现 `{variant}` 与 `{concept}` 概念混用",
                            "why": "同一概念使用不同表述增加理解和维护成本",
                            "fix": f"统一使用 `{concept}` 概念，重命名相关类/函数",
                            "effort": "L",
                        }
                    )
                    break  # 每个概念只报告一次

    def _check_naming_style_consistency(self) -> None:
        """检测命名风格一致性"""
        # 检测类名是否混用驼峰和下划线
        result = subprocess.run(
            ["grep", "-r", "-n", r"^class [a-z]", "packages/", "apps/"],
            cwd=self.root_dir,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            lines = result.stdout.strip().split("\n")[:5]
            for line in lines:
                self.findings.append(
                    {
                        "id": "NAM-011",
                        "severity": "Low",
                        "category": "Naming",
                        "location": line.split(":")[0] + ":" + line.split(":")[1] if len(line.split(":")) > 1 else line,
                        "evidence": line,
                        "why": "类名应使用 PascalCase，不应使用小写或下划线开头",
                        "fix": "将类名改为 PascalCase 风格",
                        "effort": "S",
                    }
                )

    def _check_abbreviation_consistency(self) -> None:
        """检测缩写规范"""
        # 检测非标准缩写（如 qty 应为 quantity）
        non_standard_abbreviations = {
            "qty": "quantity",
            "vol": "volume",
        }

        for abbr, full in non_standard_abbreviations.items():
            result = subprocess.run(
                ["grep", "-r", "-n", rf"\b{abbr}\b", "packages/", "apps/"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                # 排除注释和已正确使用的情况
                lines = [
                    line
                    for line in result.stdout.strip().split("\n")
                    if "#" not in line and f'"{abbr}"' not in line and f"'{abbr}'" not in line
                ]
                if lines:
                    self.findings.append(
                        {
                            "id": "NAM-012",
                            "severity": "Low",
                            "category": "Naming",
                            "evidence": f"发现缩写 `{abbr}` 使用",
                            "why": f"应使用完整术语 `{full}` 而非缩写",
                            "fix": f"将 `{abbr}` 替换为 `{full}`",
                            "effort": "M",
                        }
                    )

    def _generate_report(self) -> Path:
        """生成审计报告"""
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        report_path = self.reviews_dir / f"{date_str}-architecture-audit.md"

        # 统计
        stats = self._calculate_stats()

        # 生成报告内容
        content = self._render_report(stats)

        # 写入文件
        report_path.write_text(content, encoding="utf-8")

        return report_path

    def _calculate_stats(self) -> dict[str, int]:
        """计算统计信息"""
        stats = {"Blocker": 0, "High": 0, "Medium": 0, "Low": 0}
        for finding in self.findings:
            severity = finding.get("severity", "Low")
            stats[severity] = stats.get(severity, 0) + 1
        return stats

    def _render_report(self, stats: dict[str, int]) -> str:
        """渲染报告"""
        total = sum(stats.values())
        top_issues = sorted(self.findings, key=lambda x: self._severity_order(x.get("severity", "Low")))[:3]

        # 生成架构图
        arch_diagram = self._generate_architecture_diagram()

        report = f"""# 架构审计报告

**日期**：{datetime.now().strftime("%Y-%m-%d")}
**审计范围**：全库
**分支**：{os.getenv("GIT_BRANCH", "unknown")}

---

## Executive Summary

### 关键发现统计
| 严重度 | 架构约束 | 工程实践 | 合计 |
|--------|---------|---------|------|
| Blocker | - | - | {stats.get("Blocker", 0)} |
| High | - | - | {stats.get("High", 0)} |
| Medium | - | - | {stats.get("Medium", 0)} |
| Low | - | - | {stats.get("Low", 0)} |
| **总计** | - | - | **{total}** |

### Top 3 优先处理的问题
"""

        for i, issue in enumerate(top_issues, 1):
            report += f"\n{i}. **{issue.get('id', 'Unknown')}**: {issue.get('evidence', '')[:50]}...\n"

        report += "\n---\n\n## Inferred Architecture\n\n"
        report += arch_diagram

        report += "\n\n---\n\n## Findings\n\n"

        # 按严重度分组
        for severity in ["Blocker", "High", "Medium", "Low"]:
            issues = [f for f in self.findings if f.get("severity") == severity]
            if not issues:
                continue

            report += f"### {severity} 严重度\n\n"
            for issue in issues:
                report += f"#### {issue.get('id', 'Unknown')}\n\n"
                report += f"- **Severity**: {severity}\n"
                report += f"- **Category**: {issue.get('category', 'Unknown')}\n"
                report += f"- **Location**: {issue.get('location', 'Unknown')}\n"
                report += f"- **Evidence**: `{issue.get('evidence', '')[:100]}`\n"
                report += f"- **Why it matters**: {issue.get('why', '')}\n"
                report += f"- **Fix**: {issue.get('fix', '')}\n"
                report += f"- **Effort**: {issue.get('effort', 'M')}\n\n"

        report += """
---

## Refactor Plan

### P0 必须修
- 修复所有 Blocker 和 High 严重度问题

### P1 应该修
- 修复 Medium 严重度问题

### P2 可优化
- 修复 Low 严重度问题

---

## 验证计划

```bash
# 完整检查
pixi run -e dev ci

# 单独测试
pixi run -e dev test --unit
pixi run -e dev type
pixi run -e dev lint
```
"""

        return report

    def _generate_architecture_diagram(self) -> str:
        """生成架构图"""
        diagram = "### 依赖关系图\n\n```\n"

        # 统计各层级的模块
        layers = {
            "apps/port": set(),
            "packages/datahub": set(),
            "packages/foundation": set(),
        }

        for module, deps in self.import_graph.items():
            if module.startswith("apps.port."):
                layers["apps/port"].add(module)
            elif module.startswith("packages.datahub."):
                layers["packages/datahub"].add(module)
            elif module.startswith("packages.foundation."):
                layers["packages/foundation"].add(module)

        # 生成层级图
        diagram += "┌─────────────────────────────────────────┐\n"
        diagram += "│  应用层 (apps/port)                       │\n"
        diagram += f"│  模块数: {len(layers['apps/port'])}                    │\n"
        diagram += "└────────────────┬────────────────────────────┘\n"
        diagram += "                 │\n"
        diagram += "                 ▼\n"
        diagram += "┌─────────────────────────────────────────┐\n"
        diagram += "│  数据访问层 (packages/datahub)            │\n"
        diagram += f"│  模块数: {len(layers['packages/datahub'])}                    │\n"
        diagram += "└────────────────┬────────────────────────────┘\n"
        diagram += "                 │\n"
        diagram += "                 ▼\n"
        diagram += "┌─────────────────────────────────────────┐\n"
        diagram += "│  基础设施层 (packages/foundation)         │\n"
        diagram += f"│  模块数: {len(layers['packages/foundation'])}                    │\n"
        diagram += "└─────────────────────────────────────────┘\n"
        diagram += "```\n\n"

        # 检测依赖方向
        diagram += "### 依赖方向分析\n\n"

        port_deps_datahub = False
        datahub_deps_foundation = False
        port_deps_foundation = False

        for module in self.import_graph:
            if module.startswith("apps.port."):
                for dep in self.import_graph[module]:
                    if dep.startswith("packages.datahub."):
                        port_deps_datahub = True
                    elif dep.startswith("packages.foundation."):
                        port_deps_foundation = True
            elif module.startswith("packages.datahub."):
                for dep in self.import_graph[module]:
                    if dep.startswith("packages.foundation."):
                        datahub_deps_foundation = True

        diagram += "| 依赖方向 | 状态 | 说明 |\n"
        diagram += "|---------|------|------|\n"
        diagram += f"| Port → DataHub | ✅ {'符合' if port_deps_datahub else '无依赖'} | 应用层依赖数据访问层 |\n"
        diagram += f"| Port → Foundation | ✅ {'符合' if port_deps_foundation else '无依赖'} | 应用层依赖基础设施 |\n"
        diagram += f"| DataHub → Foundation | ✅ {'符合' if datahub_deps_foundation else '无依赖'} | 数据访问层依赖基础设施 |\n"
        diagram += "| DataHub → Port | ❌ 禁止 | 反向依赖（架构违规）|\n"
        diagram += "| Foundation → Others | ❌ 禁止 | 基础设施不应依赖上层 |\n"

        return diagram

    def _severity_order(self, severity: str) -> int:
        """严重度排序权重"""
        order = {"Blocker": 0, "High": 1, "Medium": 2, "Low": 3}
        return order.get(severity, 4)

    def _print_summary(self) -> None:
        """打印摘要"""
        stats = self._calculate_stats()
        total = sum(stats.values())

        print("\n🔍 Architecture Audit Report")
        print("\n📊 Summary:")
        print(f"  Blocker: {stats.get('Blocker', 0)} | High: {stats.get('High', 0)} | Medium: {stats.get('Medium', 0)} | Low: {stats.get('Low', 0)}")

        if total > 0:
            print("\n🔴 Top Issues:")
            top_issues = sorted(self.findings, key=lambda x: self._severity_order(x.get("severity", "Low")))[:5]
            for i, issue in enumerate(top_issues, 1):
                print(f"  {i}. [{issue.get('id', 'Unknown')}] {issue.get('evidence', '')[:60]}...")

        date_str = datetime.now().strftime("%Y-%m-%d")
        print(f"\n📄 Full report: docs/reviews/{date_str}-architecture-audit.md")


def main():
    """主函数"""
    root_dir = Path(__file__).parent.parent.parent
    auditor = ArchitectureAuditor(root_dir)
    auditor.run()


if __name__ == "__main__":
    main()
