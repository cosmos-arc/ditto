# P2: DTCG Token 格式标准化 + Style Dictionary 集成

## Context

Ditto 有 516 个 CSS 自定义属性设计 token（9 层架构），但没有机器可读的标准化格式输出。W3C DTCG (Design Tokens Community Group) 格式是业界标准，Style Dictionary v4 是最成熟的 DTCG 消费工具。本方案构建 CSS → DTCG → 多平台输出的完整 pipeline，为未来 Figma/iOS/Android 等多平台消费做准备。

**SSOT 不变**：`src/styles/design-tokens/*.css` 仍然是唯一真理源。导出 pipeline 是只读消费。

---

## 文件结构

```
scripts/
  export-tokens/
    types.ts                    # 共享类型定义
    css-parser.ts               # CSS 解析 → RawCssToken[]
    oklch-converter.ts          # OKLCH ↔ hex 转换（culori）
    reference-resolver.ts       # var() → DTCG {path} 引用
    composite-builder.ts        # shadow/border/transition → DTCG 复合类型
    atmosphere-handler.ts       # runtime-dynamic calc() token 特殊处理
    dtcg-writer.ts              # 写 DTCG JSON 文件（分 layer + 分 theme）
    sd-oklch-transform.ts       # Style Dictionary OKLCH 自定义 transform
    index.ts                    # Pipeline 编排
  export-tokens.ts              # CLI 入口
sd.config.ts                    # Style Dictionary v4 配置
dist/tokens/                    # DTCG JSON 输出（gitignored）
  tokens/  {base,semantic,atmosphere,shell,data-viz,component,interaction,domain,density}.json
  themes/   {dark,light,domain-signatures,market-intl,density-comfortable,density-dense}.json
dist/sd/                        # Style Dictionary 输出
  css/variables.css
  scss/_variables.scss
  json/tokens.json
```

---

## Tasks

### Task 1: 安装依赖 + 基础配置

- `bun add -d culori style-dictionary`
- 在 `package.json` 中添加 scripts：
  - `"build:tokens"`: `bun scripts/export-tokens.ts`
  - `"build:tokens:check"`: `bun scripts/export-tokens.ts --check`
- `.gitignore` 已有 `dist/`，无需改动

### Task 2: `types.ts` — 类型定义

关键类型：
- `RawCssToken` — CSS 解析原始数据（name, value, source file, selector, layer）
- `TokenLayer` — 9 层枚举：base | semantic | atmosphere | shell | data-viz | component | interaction | domain | density
- `ThemeContext` — 选择器分类：default | light | domain | density | intl | lightDomain
- `ParsedValue` — 联合类型覆盖所有值模式：color/dimension/number/fontFamily/fontWeight/cubicBezier/duration/reference/referenceWithFallback/relativeOklch/composite-*/string/runtimeDynamic/transparent/unknown
- `DtcgToken` — DTCG 输出结构（$value, $type, $description?, $extensions?）
- `DittoExtension` — 项目自定义扩展（oklch原始值, source, layer, dynamic标记, rawCss）

### Task 3: `oklch-converter.ts` — OKLCH ↔ Hex 转换

使用 `culori` 库（替代 `token-utils.mjs` 中的手动实现）：
- `oklchToHex(l, c, h, alpha?)` → hex string
- `hexToOklch(hex)` → {l, c, h} 用于 roundtrip 验证
- `resolveRelativeOklch(baseOklch, alpha)` — 解析 `oklch(from var(--x) l c h / 0.10)`

### Task 4: `css-parser.ts` — CSS Token 解析器

**输入**：9 个 `tokens-*.css` 文件 + 3 个 theme 文件
**输出**：`Map<string, RawCssToken[]>`（按选择器分组）

解析逻辑：
1. 用正则提取 selector block（`:root`, `[data-theme="light"]`, `[data-domain="trading"]` 等）
2. 从每个 block 中提取 `--name: value` 声明
3. 文件名 → layer 映射（`tokens-base.css` → `base`）
4. 选择器 → `ThemeContext` 分类

**关键复用**：`token-utils.mjs` 中的 `OKLCH_RE`、`RELATIVE_OKLCH_RE`、`VAR_RE` 正则模式

### Task 5: `reference-resolver.ts` — 引用解析

**两阶段**：

Phase A — 构建引用映射表：
```
token-name → DTCG path
e.g., "brand-500" → "{base.brand.500}"
```

Phase B — 逐 token 解析值：
- `var(--xxx)` → `{path.to.xxx}`
- `var(--xxx, var(--yyy))` → 主引用 + fallback 存入 `$extensions`
- `oklch(from var(--xxx) l c h / alpha)` → 先解析 base 的 OKLCH，计算 alpha 变体，转 hex
- 纯值（无引用）→ 直接解析

**处理顺序**：L1 base 先处理（因为 L2-L8 引用 L1）

### Task 6: `composite-builder.ts` — 复合 Token 构建

4 种复合模式：
- **Shadow**：`0 8px 24px oklch(0 0 0 / 0.4)` → `{$type: "shadow", $value: {offsetX, offsetY, blur, color}}`
- **Border**：`1px solid var(--border-subtle)` → `{$type: "border", $value: {width, style, color}}`
- **Transition**：`var(--motion-duration-slow) var(--motion-easing-standard)` → `{$type: "transition", $value: {duration, timingFunction}}`
- **Padding shorthand**：`var(--space-10) var(--space-12)` → `{$type: "string"}` + extension 标记

### Task 7: `atmosphere-handler.ts` — Runtime Dynamic Token

6 个 atmosphere token 的特殊处理：
- 3 个运行时参数（`--atmosphere-hue-shift` 等）→ `$type: "number"` + `$extensions.dynamic = true`
- 2 个 calc 组合（`--surface-app-atmosphere`）→ `$value` = fallback hex + `$extensions.runtimeDynamic = true` + `$extensions.rawCss` = 原始 calc 表达式
- 1 个 duration（`--atmosphere-breathe-duration`）→ 正常处理

### Task 8: `dtcg-writer.ts` — DTCG JSON 写入

按 layer + theme 分文件写入：

**Token 文件**（9 个）：每层一个，包含 `:root` 默认值
- `tokens/base.json`, `tokens/semantic.json`, ... `tokens/density.json`

**Theme 文件**（6 个）：
- `themes/dark.json` — 空文件（`:root` 即 dark 默认值）
- `themes/light.json` — 所有 `[data-theme="light"]` 覆盖
- `themes/domain-signatures.json` — 6 个 `[data-domain]` 块
- `themes/market-intl.json` — `[data-market-region="intl"]` 块
- `themes/density-comfortable.json`, `themes/density-dense.json`

**DTCG 路径构建**：layer-aware prefix 剥离策略
- `--neutral-0` → `neutral.0`
- `--brand-500` → `brand.500`
- `--surface-panel-base` → `surface.panel-base`
- `--btn-sm-padding-y` → `btn.sm.padding-y`

### Task 9: `index.ts` — Pipeline 编排

```
parseAllTokenFiles()
  → buildReferenceMap()
  → resolveTokens()（按 L1→L8 顺序）
  → groupByLayerAndContext()
  → writeDtcgFiles()
  → [可选] runStyleDictionary()
  → [可选] validateDtcg()
```

### Task 10: `export-tokens.ts` — CLI 入口

薄 CLI 层，解析 `--check` 和 `--schema-only` 参数。

### Task 11: `sd-oklch-transform.ts` + `sd.config.ts` — Style Dictionary 集成

**自定义 OKLCH transform**：
- `transitive: true`
- filter: `$type === "color"` 且有 `com.ditto-app.oklch` extension
- transform: 读 `$extensions["com.ditto-app"].oklch` 输出 `oklch(...)` CSS
- runtime-dynamic token: 输出原始 calc 表达式

**sd.config.ts** 平台：
- `css` — `css/variables` 格式，输出 `dist/sd/css/variables.css`
- `scss` — `scss/variables` 格式，输出 `dist/sd/scss/_variables.scss`
- `json` — `json` 格式，输出 `dist/sd/json/tokens.json`

### Task 12: 测试

在 `scripts/export-tokens/` 下为每个模块写 `.test.ts`：
- OKLCH 转换精度（与 token-utils.mjs 已知值对比）
- 引用解析（简单引用 / fallback / relative oklch）
- 复合 token 解析
- 选择器分类
- DTCG 输出结构验证
- Roundtrip 验证（OKLCH → hex → OKLCH 误差 < 0.001）

### Task 13: 集成验证

- `bun run build:tokens` 成功导出所有 DTCG JSON
- `bun run build:tokens:check` 通过 DTCG 验证
- Style Dictionary 输出 CSS 变量文件语法正确
- `bun run check`（lint + type + test）通过

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| DTCG color 格式 | hex $value + oklch in $extensions | DTCG spec 只支持 hex，OKLCH 保留在 extensions 供自定义 transform 消费 |
| Theme 处理 | 分文件（dark/light/domain/...） | DTCG 无官方 theme 规范，Style Dictionary 推荐分文件 |
| Atmosphere tokens | runtimeDynamic 标记 + fallback hex | calc() 无法静态解析，保留原始表达式供 SD transform |
| @theme inline | 不导出 | 非 SSOT，仅 Tailwind 桥接层 |
| Token 命名路径 | layer-aware prefix 剥离 | 保留语义分组，避免 DTCG 路径层级过深 |
| SSOT 地位 | CSS 文件不变 | Pipeline 是只读消费，不反向生成 CSS |

## 验证方式

```bash
# 完整 pipeline
bun run build:tokens

# 验证 + 审计
bun run build:tokens:check

# 工程检查
bun run check

# 手动检查输出
cat dist/tokens/tokens/base.json | head -50
cat dist/sd/css/variables.css | head -30
```
