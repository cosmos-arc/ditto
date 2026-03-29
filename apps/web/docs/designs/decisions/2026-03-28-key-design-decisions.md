# Ditto App — Key Design Decisions

> 决策时间：2026-03-28
> 状态：Style B 已定稿，密度档位待最终选定

## 1. 视觉风格 → Style B: Graphite Studio

- **选择**：Style B (Graphite Studio)，Linear/Vercel/Raycast 风格
- **淘汰**：Style A (Obsidian Terminal), C (Slate Observatory), D (Warm Carbon), E (Deep Navy), F (Zenith)
- **Why:** 现代 Sans 主导，信息密度与可读性平衡，适合日常量化工作台。非 Mono 极密风格，减少长时间使用疲劳
- **How to apply:** 所有原型和 Token 以 `docs/designs/specs/prototypes/style-b-graphite-studio/` 为基准

## 2. UI 字体 → Inter + Noto Sans SC

- **选择**：`'Inter', 'Noto Sans SC', system-ui, -apple-system, sans-serif`
- **Why:** 中文内容为主，Inter 搭配 Noto Sans SC 覆盖中英文，Google Fonts 免费，渲染质量优秀，广泛用于 Linear/Vercel/Raycast
- **How to apply:** `--font-family-ui` token，全局 UI 文本

## 3. 数据/代码字体 → JetBrains Mono

- **选择**：`'JetBrains Mono', monospace`
- **Why:** 等宽字体，数字列对齐优秀，代码高亮 ligature 支持，量化平台标配
- **How to apply:** `--font-family-numeric` + `--font-family-code` token

## 4. 密度系统 → 3 级 (Dense / Compact / Comfortable)

- **选择**：以行高为基准的 3 级密度
  - Dense: 34px rows, 48px rail, 12px body font
  - Compact: 36px rows, 56px rail, 13px body font (当前默认)
  - Comfortable: 42px rows, 60px rail, 15px body font
- **Why:** 不同使用场景需求不同（多屏工作台 vs 日常监控 vs 长时间分析）
- **How to apply:** `--density-row-height` 为核心变量，配合 `--shell-rail-width`、`--font-size-XX`、`--space-XX` 联动
- **待定:** 用户尚未最终选定默认密度档位

## 5. 色彩空间 → OKLCH

- **选择**：所有色值使用 OKLCH 格式
- **Why:** Perceptually uniform，前向兼容 Tailwind CSS v4，支持 alpha 通道 (`oklch(0.7 0.1 260 / 0.5)`)
- **How to apply:** `tokens-base.css` 中所有 neutral/brand/functional primitives 均为 OKLCH

## 6. 涨跌色 → 可切换，默认红涨绿跌（中国大陆习惯）

- **选择**：涨跌色必须支持切换，**默认为红涨绿跌**（中国大陆/A股习惯）
- **两套配色方案**：
  - 中国大陆模式（默认）：涨 = 红色 `oklch(0.670 0.170 20)`，跌 = 绿色 `oklch(0.680 0.120 175)`
  - 国际模式（可切换）：涨 = 绿色 `oklch(0.680 0.120 175)`，跌 = 红色 `oklch(0.670 0.170 20)`
- **Why:** 用户主要面向中国大陆市场，红涨绿跌是本地习惯。同时需要支持国际市场绿涨红跌
- **How to apply:** `--market-up-fg` / `--market-down-fg` token 值根据用户设置切换，所有行情/信号/PnL 组件统一引用这两个 token，不做硬编码
- **实现要求**：需要在用户设置（Settings）中提供涨跌色切换开关，切换后全局实时生效
- **注意**：当前原型 tokens-style.css 中 `--market-up-fg` 使用 Teal（绿）、`--market-down-fg` 使用 Coral（红），需要调整为默认红涨绿跌

## 7. CSS 架构 → html 16px 根 + rem 间距

- **选择**：`html` 保持浏览器默认 16px，`body` 设 `font-size: var(--font-size-13)`，所有间距/密度用 `rem`
- **Why:** 修复了 `html { font-size: var(--font-size-13) }` 导致所有 rem 值基于 13px 计算的 bug（缩水 19%）。html 16px 确保 rem 值符合设计预期
- **How to apply:** `layout-base.css` 中 `html` 不设 font-size，`body` 设内容字号。Shell/组件尺寸用 CSS 变量 (`--shell-rail-width` 等)

## 8. Shell 布局 → Rail + Header + CSS Grid

- **选择**：左侧 Rail (56px) + 顶部 Header (68px) + CSS Grid 内容区
- **Why:** 图标导航节省水平空间，全局操作在顶部，内容区自适应
- **How to apply:** `--shell-rail-width` + `--shell-header-height` 变量控制，5 个页面 shell 共享 grid 结构

## 9. Token 层级 → 9 层命名体系

- **选择**：Foundation → Semantic Surface → Shell → Data View → Component → Interaction → Domain Semantic → Density → Module Pattern
- **Why:** 清晰的关注点分离，每层可独立演进，密度层可在不改变业务语义的情况下调整视觉密度
- **How to apply:** 参见 `docs/designs/specs/14_ditto_token_naming_layering_spec.md`
