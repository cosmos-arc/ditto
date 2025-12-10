# 测试覆盖率指南

本文档说明如何查看和提高项目的测试覆盖率。

## 快速开始

### 运行测试并生成覆盖率报告

```bash
# 使用提供的脚本（推荐）
./scripts/run_coverage.sh              # Linux/Mac
scripts\run_coverage.ps1               # Windows PowerShell

# 或直接使用 pytest
pixi run pytest --cov=packages/ --cov-report=html
```

### 查看覆盖率报告

```bash
# 打开 HTML 报告（推荐）
python scripts/view_coverage.py --open

# 查看摘要信息
python scripts/view_coverage.py --summary

# 生成报告并立即查看
python scripts/view_coverage.py --all
```

## 覆盖率报告格式

项目支持多种覆盖率报告格式：

1. **HTML 报告** (`htmlcov/index.html`)
   - 交互式，可逐文件查看
   - 显示每行代码的覆盖情况

2. **终端报告**
   - 显示未覆盖的行号
   - 适合快速查看

3. **XML 报告** (`coverage.xml`)
   - 机器可读格式
   - 用于 CI/CD 集成

## 覆盖率配置

### pytest 配置 (pyproject.toml)

```toml
[tool.pytest.ini_options]
addopts = [
    "--cov=packages/",
    "--cov-report=html:htmlcov",
    "--cov-report=term-missing:skip-covered",
    "--cov-report=xml:coverage.xml",
    "--cov-branch",
    "--cov-fail-under=80"  # 要求至少 80% 覆盖率
]
```

### 覆盖率阈值

- **当前要求**: 80% (在 CI 中强制执行)
- **目标**: 核心模块达到 90%+

## 提高覆盖率的技巧

### 1. 识别未测试的代码

```bash
# 查看具体文件的覆盖情况
python scripts/view_coverage.py --check path/to/file.py

# 在终端报告中查看未覆盖的行
pixi run pytest --cov-report=term-missing
```

### 2. 编写测试用例

优先覆盖以下场景：
- 正常流程
- 边界条件
- 异常处理
- 错误分支

### 3. 使用覆盖率工具

```bash
# 安装 coverage 工具（如果需要）
pip install coverage

# 运行覆盖率分析
coverage run -m pytest
coverage html
```

## 常见问题

### Q: 为什么某些文件不显示在覆盖率报告中？

A: 检查 `pyproject.toml` 中的 `--cov` 配置，确保包含了正确的路径。

### Q: 如何排除特定文件或目录？

A: 在 pytest 配置中添加：

```toml
[tool.coverage.run]
omit = [
    "*/tests/*",
    "*/migrations/*",
    "*/__pycache__/*",
    "*/conftest.py"
]
```

### Q: 如何处理条件分支覆盖？

A: 使用 `--cov-branch` 参数启用分支覆盖率，确保所有条件分支都被测试。

## CI/CD 集成

覆盖率报告会在 CI/CD 中自动生成和检查：

1. **Pull Request**: 显示覆盖率变化
2. **Merge**: 必须达到最低覆盖率阈值
3. **报告**: 上传到覆盖率服务（可选）

## 最佳实践

1. **持续关注**: 每次提交都检查覆盖率
2. **目标明确**: 新功能必须包含测试
3. **重构安全**: 在重构前确保高覆盖率
4. **团队协作**: 代码审查时关注测试覆盖

## 相关文档

- [pytest 文档](https://docs.pytest.org/)
- [coverage.py 文档](https://coverage.readthedocs.io/)
- [项目测试规范](TESTING.md)
