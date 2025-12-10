# GitHub Actions Workflows

本目录包含Ditto量化系统的GitHub Actions CI/CD工作流配置。

## 工作流说明

### 1. `test.yml` - 主测试工作流

**触发条件：**
- 推送到 master/main/develop 分支
- 创建/更新针对 master/main 的 Pull Request

**功能：**
- 在 Windows 和 Ubuntu 环境下运行测试
- 支持 Python 3.11 和 3.12（Ubuntu只测试3.11以节省时间）
- 使用 pixi 作为包管理器
- 运行 pytest 测试套件
- 生成测试覆盖率报告（XML和HTML）
- 上传覆盖率到 Codecov
- 验证Python文件语法和导入

**关键特性：**
- 矩阵构建：支持多OS和多Python版本
- 快速失败：语法错误立即失败
- 缓存优化：使用pixi缓存加速依赖安装
- 测试结果上传：保存测试报告供下载

### 2. `lint.yml` - 代码质量检查工作流

**触发条件：**
- 推送到 master/main/develop 分支
- 创建/更新针对 master/main 的 Pull Request

**功能：**
- **Lint检查**：运行 ruff 检查代码质量问题
- **格式化检查**：验证代码格式是否符合标准
- **类型检查**：运行 mypy 进行静态类型检查
- **安全扫描**：使用 bandit 扫描安全漏洞
- **Pre-commit检查**：运行所有pre-commit hooks

**作业说明：**
- `lint`：ruff检查（Ubuntu和Windows并行运行）
- `type-check`：mypy类型检查（仅在Ubuntu）
- `security`：bandit安全扫描（仅在Ubuntu）
- `pre-commit`：完整的pre-commit检查（仅在Ubuntu）

### 3. `coverage.yml` - 覆盖率检查工作流

**触发条件：**
- 仅在 Pull Request 时运行

**功能：**
- 生成详细的覆盖率报告
- 与基础分支比较覆盖率差异
- 在PR中添加覆盖率评论
- 检查覆盖率是否达到阈值（80%）
- 上传HTML覆盖率报告

**特性：**
- 自动评论：在PR中自动添加覆盖率报告
- 阈值检查：覆盖率低于80%时PR无法合并
- 可视化报告：生成HTML报告供下载

## 环境变量

工作流使用以下环境变量：

- `PYTHON_DEFAULT_VERSION`: "3.11" - 默认Python版本
- `CODECOV_TOKEN`: 存储在GitHub Secrets中，用于上传覆盖率

## 缓存策略

1. **Pixi缓存**：缓存依赖包，加速后续构建
2. **Pre-commit缓存**：缓存pre-commit环境

## 产物（Artifacts）

工作流会生成以下产物供下载：

- `coverage-report-{os}`: HTML覆盖率报告
- `test-results-{os}-py{version}`: 测试结果文件
- `bandit-security-report`: 安全扫描报告（JSON格式）
- `coverage-html-report`: PR的HTML覆盖率报告

## 故障排除

### 常见问题

1. **pixi安装失败**
   - 检查 pixi.toml 格式是否正确
   - 确认所有依赖都可用的版本

2. **测试失败**
   - 查看测试日志确定具体失败原因
   - 检查是否是环境特定的失败（如Windows路径问题）

3. **覆盖率不足**
   - 运行 `pixi run pytest --cov-report=term-missing` 查看未覆盖的行
   - 添加相应的测试用例

4. **mypy类型错误**
   - 使用 `pixi run mypy packages/` 查看详细错误
   - 添加缺失的类型注解

### 调试技巧

1. **本地运行相同的检查**
   ```bash
   # 运行所有检查
   pre-commit run --all-files

   # 运行测试
   pixi run python -m pytest --cov=packages --cov-report=html

   # 类型检查
   pixi run mypy packages/ apps/
   ```

2. **查看详细日志**
   - 在GitHub Actions页面点击对应的工作流
   - 展开失败的步骤查看详细输出

## 最佳实践

1. **提交前检查**
   - 总是在本地运行 pre-commit
   - 确保所有测试通过

2. **PR管理**
   - 保持PR较小，便于审查
   - 确保PR标题和描述清晰

3. **性能优化**
   - 利用缓存减少构建时间
   - 避免不必要的工作流触发

## 扩展指南

如需添加新的检查或修改现有工作流：

1. **添加新的质量检查**
   - 在 `lint.yml` 中添加新的作业
   - 或在现有作业中添加新的步骤

2. **修改测试矩阵**
   - 在 `test.yml` 中修改 `strategy.matrix`
   - 添加或删除Python版本/操作系统组合

3. **调整覆盖率阈值**
   - 在相应工作流中修改 `--cov-fail-under` 参数
   - 更新文档中的阈值说明
