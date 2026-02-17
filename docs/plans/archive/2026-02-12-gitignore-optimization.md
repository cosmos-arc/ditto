# .gitignore 优化设计

## 背景

当前项目的 `.gitignore` 存在以下问题：
1. 拼写错误：`/.temp` 实际目录是 `.tmp/`
2. 缺少缓存目录：`.grimp_cache/`、`.import_linter_cache/`、`.benchmarks/`
3. 过度宽泛的全局规则：`*.json`、`*.html`、`*.csv` 可能忽略需要的文件

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 数据文件策略 | 混合策略 | 忽略根目录和特定子目录，源码目录不忽略 |
| IDE 配置 | 完全忽略 | 每个开发者自己配置 |

## 优化内容

### 1. 核心修复

```gitignore
# 修复拼写错误
/.tmp/                    # 原来是 /.temp

# 添加缺失的缓存目录
.grimp_cache/
.import_linter_cache/
.benchmarks/
.mypy_cache/              # 预留，以防未来使用 mypy
```

### 2. 精简过度宽泛规则

**删除：**
- `*.json` - 太宽泛
- `*.html` - 太宽泛
- `*.csv` - 太宽泛

**替换为精确规则：**
```gitignore
# CSV/JSON 精确忽略
/*.csv
/*.json
config/**/*.json
!config/**/*.example.json
!.factory/settings.json
```

### 3. 完整优化后的配置

见下方实施部分。

## 变更总结

| 变更类型 | 内容 |
|---------|------|
| 修复 | `/.temp` → `/.tmp/` |
| 新增 | `.grimp_cache/`、`.import_linter_cache/`、`.benchmarks/`、`.mypy_cache/` |
| 删除 | `*.json`、`*.html`、`*.csv` 全局规则 |
| 优化 | CSV/JSON 改为精确路径忽略 |
| 精简 | 移除冗余注释 |

## 实施计划

1. 备份当前 `.gitignore`
2. 替换为优化后的配置
3. 验证 `git status` 无异常
