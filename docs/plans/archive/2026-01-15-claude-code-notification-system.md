# Claude Code 强提示通知系统设计

## 需求概述

设计一个基于 Claude Code Hook 机制的多渠道通知系统，在 AI 需要用户介入时提供强提示。

### 核心需求
- **场景全覆盖**：权限确认、错误中断、关键决策
- **智能通知**：VSCode 内 → 编辑器提示；VSCode 外 → Windows Toast
- **多渠道推送**：优先国内方案，备用国际方案
- **中国大陆环境**：考虑网络访问的可行性

### 通知渠道
1. **VSCode 内置通知**（编辑器内）
2. **Windows Toast 通知**（系统级）
3. **Bark 推送**（iOS - 主力方案）
4. **Telegram Bot**（国际备用）

---

## 方案详细评估

### 1. PushPlus（推送加）- 微信推送

| 维度 | 评估 |
|------|------|
| **稳定性** | ⭐⭐⭐⭐ 商业化服务，SLA 保障 |
| **成本** | 免费版 200 条/日，付费版 5 元/月起（5000 条/日） |
| **优势** | API 简单、支持多渠道（微信/企业微信/邮件/钉钉/飞书）、免费额度充足 |
| **缺点** | 需要微信扫码绑定、免费版有推送延迟（1-5秒） |
| **限制** | 单条消息最大 2KB、频率限制（免费版 1 条/秒） |
| **适用场景** | **日常主力推送方案** |

### 2. WxPusher - 微信推送

| 维度 | 评估 |
|------|------|
| **稳定性** | ⭐⭐⭐ 开源项目，社区维护 |
| **成本** | 完全免费 |
| **优势** | 无需注册账号、微信扫码即用、支持多应用、开源可自建 |
| **缺点** | 单作者维护、SLA 无保障、可能出现服务中断 |
| **限制** | 单日 1000 条、需关注公众号 |
| **适用场景** | **备用/测试环境** |

### 3. Bark - iOS 推送

| 维度 | 评估 |
|------|------|
| **稳定性** | ⭐⭐⭐⭐⭐ 基于 APNs，苹果官方保障 |
| **成本** | 完全免费（自建服务器需承担服务器成本） |
| **优势** | 极其稳定、瞬间推送、支持自定义铃声/图标、可自建 |
| **缺点** | 仅限 iOS、Android 需配合 Gotify |
| **限制** | 需要安装 App |
| **适用场景** | **iOS 用户首选** |

### 4. ntfy.sh - 开源推送

| 维度 | 评估 |
|------|------|
| **稳定性** | ⭐⭐⭐⭐ 开源项目，活跃维护 |
| **成本** | 公共服务免费，自建仅需服务器成本 |
| **优势** | 完全开源、支持多平台、离线消息存储、可自建 |
| **缺点** | 国内访问公共服务器可能不稳定 |
| **限制** | 公共服务器有速率限制 |
| **适用场景** | **自建服务的最佳选择** |

### 5. 钉钉/飞书机器人

| 维度 | 评估 |
|------|------|
| **稳定性** | ⭐⭐⭐⭐⭐ 企业级服务，SLA 保障 |
| **成本** | 完全免费 |
| **优势** | 极其稳定、企业级保障、支持富文本、无频率限制 |
| **缺点** | 需要创建群、需要对应账号 |
| **限制** | 仅限群聊推送、需要公司/团队账号 |
| **适用场景** | **工作环境首选** |

### 6. Telegram Bot

| 维度 | 评估 |
|------|------|
| **稳定性** | ⭐⭐⭐⭐⭐ 全球服务，极其稳定 |
| **成本** | 完全免费 |
| **优势** | API 简单、实时性最好、支持富媒体 |
| **缺点** | 国内需要特殊网络环境 |
| **限制** | 需要科学上网 |
| **适用场景** | **国际环境/技术用户备用** |

---

## 推荐组合方案

### 🎯 最佳实践组合（推荐）

```
主力方案：
├── Bark 推送（iOS - APNs 极致稳定）
└── Telegram Bot（国际环境备用）

本地方案：
├── VSCode 内置通知（编辑器内）
└── Windows Toast（系统级）
```

### 方案选择决策树

```
使用 iOS 设备？
├── 是 → Bark（首选，基于 APNs 最稳定）
└── 否 → Telegram Bot（需要科学上网）
```

---

## 技术实现方案

### Hook 机制集成

Claude Code 支持以下 Hook 事件：

| Hook 类型 | 说明 | 通知优先级 |
|-----------|------|-----------|
| `SessionStart:startup` | 会话开始 | 低 |
| `pre-command` | 命令执行前 | 中 |
| `post-command` | 命令执行后 | 中 |
| `command-error` | 命令执行失败 | **高** |
| `user-prompt-submit` | 用户提交提示 | 低 |
| `tool-use` | 工具调用 | 中 |
| `permission-blocked` | 权限被拒绝 | **高** |

### 通知优先级设计

```javascript
const NOTIFICATION_LEVELS = {
  CRITICAL: {  // 需要立即介入
    channels: ['bark', 'telegram'],
    sound: 'alarm',
    retry: 3
  },
  HIGH: {  // 错误/失败
    channels: ['bark', 'telegram'],
    sound: 'default',
    retry: 2
  },
  NORMAL: {  // 关键节点
    channels: ['bark'],
    sound: 'none',
    retry: 1
  },
  INFO: {  // 一般信息
    channels: ['bark'],
    sound: 'none',
    retry: 1
  }
};
```

---

## Windows 环境特殊处理

### VSCode 焦点检测

```javascript
// 检测 VSCode 是否为前台窗口
const isVSCodeActive = () => {
  const activeWindow = getActiveWindow();
  return activeWindow.includes('Visual Studio Code');
};

// 智能通知路由
const routeNotification = async (message) => {
  if (isVSCodeActive()) {
    // VSCode 内置通知
    vscode.showInformationMessage(message);
  } else {
    // Windows Toast + 远程推送
    showWindowsToast(message);
    await sendToPushService(message);
  }
};
```

### Windows Toast 通知实现

使用 PowerShell + BurntToast 模块：

```powershell
# 安装 BurntToast
Install-Module -Name BurntToast

# 发送 Toast 通知
New-BurntToastNotification -Text "Claude Code", "需要您的介入"
```

---

## 完整实施计划

### 阶段 0：环境准备（一次性）

#### 0.1 获取 Bark 推送凭证（主力方案）

1. 在 iOS App Store 下载 **Bark** App
2. 打开 Bark，复制推送地址
3. 记录：`BARK_PUSH_URL`（格式：`https://api.day.app/YOUR_KEY`）

**可选：使用自建 Bark 服务器**
```bash
# Docker 部署自建服务器
docker run -d -p 8080:8080 finab/bark-server
# 推送地址变为：http://your-server:8080/YOUR_KEY
```

#### 0.2 获取 Telegram Bot 凭证（备用方案）

1. 在 Telegram 中搜索 **@BotFather**
2. 发送 `/newbot` 创建机器人，按提示操作
3. 获取 Bot Token（格式：`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`）
4. 记录：`TELEGRAM_BOT_TOKEN`

5. 获取 Chat ID：
   - 给你的 Bot 发送一条消息
   - 访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - 找到 `chat.id` 字段
   - 记录：`TELEGRAM_CHAT_ID`

#### 0.3 创建配置文件

在 `C:\Users\36486\.claude\notification-config.json`：

```json
{
  "enabled": true,
  "channels": {
    "bark": {
      "enabled": true,
      "url": "YOUR_BARK_URL"
    },
    "telegram": {
      "enabled": true,
      "bot_token": "YOUR_BOT_TOKEN",
      "chat_id": "YOUR_CHAT_ID"
    }
  },
  "priority": {
    "critical": ["bark", "telegram"],
    "high": ["bark", "telegram"],
    "normal": ["bark"],
    "info": ["bark"]
  },
  "windows": {
    "toast_enabled": true,
    "sound_enabled": true
  }
}
```

---

### 阶段 1：核心通知服务实现

#### 1.1 创建通知服务模块

**文件：** `C:\Users\36486\.claude\notification-service.js`

```javascript
const fs = require('fs');
const path = require('path');
const http = require('http');

// 加载配置
const configPath = path.join(process.env.USERPROFILE, '.claude', 'notification-config.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));

// 通知级别
const Level = {
  CRITICAL: 'critical',  // 需要立即介入
  HIGH: 'high',          // 错误/失败
  NORMAL: 'normal',      // 关键节点
  INFO: 'info'           // 一般信息
};

// Bark 推送
async function sendBark(title, content, level = Level.NORMAL) {
  if (!config.channels.bark.enabled) return;

  const sound = level === Level.CRITICAL ? 'alarm' : 'default';
  const url = `${config.channels.bark.url}/${encodeURIComponent(title)}/${encodeURIComponent(content)}?sound=${sound}`;

  await httpGet(url);
}

// Telegram 推送
async function sendTelegram(title, content, level = Level.NORMAL) {
  if (!config.channels.telegram.enabled) return;

  const url = `https://api.telegram.org/bot${config.channels.telegram.bot_token}/sendMessage`;
  const data = JSON.stringify({
    chat_id: config.channels.telegram.chat_id,
    text: `*${title}*\n${content}`,
    parse_mode: 'Markdown'
  });

  await httpPost(url, data);
}

// 通用 HTTP POST
function httpPost(url, data, headers = {}) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 443,
      path: urlObj.pathname + urlObj.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
        ...headers
      }
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => resolve(body));
    });

    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

// 通用 HTTP GET
function httpGet(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => resolve(body));
    }).on('error', reject);
  });
}

// 主通知函数
async function notify(title, content, level = Level.NORMAL) {
  const channels = config.priority[level] || config.priority.normal;

  for (const channel of channels) {
    try {
      switch (channel) {
        case 'bark':
          await sendBark(title, content, level);
          break;
        case 'telegram':
          await sendTelegram(title, content, level);
          break;
      }
    } catch (error) {
      console.error(`[${channel}] 通知失败:`, error.message);
    }
  }
}

// 导出
module.exports = { notify, Level };
```

---

### 阶段 2：Claude Code Hook 集成

#### 2.1 创建权限拦截 Hook

**文件：** `C:\Users\36486\.claude\hooks\permission-blocked.js`

```javascript
const { notify, Level } = require('../notification-service');

module.exports = async function(context) {
  const { tool, prompt } = context;

  // 权限被拒绝时发送高优先级通知
  await notify(
    '🚫 Claude Code 权限请求被拒绝',
    `工具: ${tool}\n提示: ${prompt}`,
    Level.HIGH
  );

  return context;
};
```

#### 2.2 创建命令错误 Hook

**文件：** `C:\Users\36486\.claude\hooks\command-error.js`

```javascript
const { notify, Level } = require('../notification-service');

module.exports = async function(context) {
  const { command, error } = context;

  await notify(
    '❌ Claude Code 命令执行失败',
    `命令: ${command}\n错误: ${error}`,
    Level.HIGH
  );

  return context;
};
```

#### 2.3 创建用户提示提交 Hook

**文件：** `C:\Users\36486\.claude\hooks\user-prompt-submit.js`

```javascript
const { notify, Level } = require('../notification-service');

module.exports = async function(context) {
  const { prompt } = context;

  // 可以选择性通知，避免过于频繁
  if (prompt.includes('/help') || prompt.includes('/commit')) {
    await notify(
      '💬 Claude Code 新对话',
      prompt.substring(0, 100) + (prompt.length > 100 ? '...' : ''),
      Level.INFO
    );
  }

  return context;
};
```

#### 2.4 更新 settings.json

在你的 `C:\Users\36486\.claude\settings.json` 中添加 hooks 配置：

```json
{
  "hooks": {
    "permission-blocked": "./hooks/permission-blocked.js",
    "command-error": "./hooks/command-error.js",
    "user-prompt-submit": "./hooks/user-prompt-submit.js"
  }
}
```

---

### 阶段 3：Windows Toast 通知集成

#### 3.1 创建 PowerShell 通知脚本

**文件：** `C:\Users\36486\.claude\show-toast.ps1`

```powershell
param(
    [Parameter(Mandatory=$true)]
    [string]$Title,

    [Parameter(Mandatory=$true)]
    [string]$Message,

    [string]$Sound = "default"
)

# 检查是否安装了 BurntToast
if (-not (Get-Module -ListAvailable -Name BurntToast)) {
    Install-Module -Name BurntToast -Scope CurrentUser -Force
}

# 发送 Toast 通知
New-BurntToastNotification -Text $Title, $Message
```

#### 3.2 在 Node.js 中调用 PowerShell

修改 `notification-service.js`，添加 Windows Toast 支持：

```javascript
const { execSync } = require('child_process');

// Windows Toast 通知
function showWindowsToast(title, content) {
  if (process.platform !== 'win32' || !config.windows.toast_enabled) return;

  try {
    const psScript = path.join(process.env.USERPROFILE, '.claude', 'show-toast.ps1');
    execSync(`powershell -ExecutionPolicy Bypass -File "${psScript}" -Title "${title}" -Message "${content}"`, {
      stdio: 'ignore'
    });
  } catch (error) {
    console.error('Windows Toast 通知失败:', error.message);
  }
}

// 更新主通知函数
async function notify(title, content, level = Level.NORMAL) {
  // 先显示 Windows Toast
  showWindowsToast(title, content);

  // 再发送远程推送
  const channels = config.priority[level] || config.priority.normal;

  for (const channel of channels) {
    try {
      // ... 原有推送逻辑
    } catch (error) {
      console.error(`[${channel}] 通知失败:`, error.message);
    }
  }
}
```

---

### 阶段 4：VSCode 焦点检测（可选）

#### 4.1 创建焦点检测模块

**文件：** `C:\Users\36486\.claude\vscode-focus.js`

```javascript
const { execSync } = require('child_process');

function isVSCodeFocused() {
  if (process.platform !== 'win32') return false;

  try {
    // 使用 PowerShell 获取当前活动窗口
    const result = execSync('powershell -Command "(Get-Process | Where-Object { $_.MainWindowTitle -ne \"\" } | Select-Object -First 1 ProcessName, MainWindowTitle | ConvertTo-Json)"', {
      encoding: 'utf-8'
    });

    const activeWindow = JSON.parse(result);
    return activeWindow.ProcessName && (
      activeWindow.ProcessName.toLowerCase().includes('code') ||
      activeWindow.MainWindowTitle.includes('Visual Studio Code')
    );
  } catch (error) {
    return false;
  }
}

module.exports = { isVSCodeFocused };
```

#### 4.2 更新通知路由

在 `notification-service.js` 中集成焦点检测：

```javascript
const { isVSCodeFocused } = require('./vscode-focus');

// 智能通知路由
async function notify(title, content, level = Level.NORMAL) {
  const inVSCode = isVSCodeFocused();

  if (!inVSCode) {
    // VSCode 无焦点时，使用 Toast + 远程推送
    showWindowsToast(title, content);
  }

  // 根据 VSCode 状态决定推送策略
  if (level === Level.CRITICAL || !inVSCode) {
    const channels = config.priority[level] || config.priority.normal;
    for (const channel of channels) {
      try {
        // ... 推送逻辑
      } catch (error) {
        console.error(`[${channel}] 通知失败:`, error.message);
      }
    }
  }
}
```

---

### 阶段 5：测试与验证

#### 5.1 单元测试

创建测试脚本 `C:\Users\36486\.claude\test-notification.js`：

```javascript
const { notify, Level } = require('./notification-service');

async function runTests() {
  console.log('开始测试通知系统...\n');

  // 测试 1：Bark 普通通知
  console.log('测试 Bark 普通通知...');
  await notify('测试通知', '这是一条测试消息', Level.NORMAL);
  await sleep(2000);

  // 测试 2：Bark 高优先级
  console.log('测试 Bark 高优先级通知...');
  await notify('🚨 重要通知', '需要您的注意！', Level.HIGH);
  await sleep(2000);

  // 测试 3：Bark + Telegram 紧急通知
  console.log('测试 Bark + Telegram 紧急通知...');
  await notify('⚠️ 紧急介入', 'AI 等待您的决策', Level.CRITICAL);

  console.log('\n测试完成！请检查您的 iOS 设备和 Telegram。');
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

runTests().catch(console.error);
```

运行测试：
```bash
node C:\Users\36486\.claude\test-notification.js
```

#### 5.2 Hook 测试

1. **测试权限拦截**：在 Claude Code 中尝试一个被拒绝的命令
2. **测试命令错误**：故意执行一个会失败的命令
3. **测试用户提示**：发送包含 `/help` 的消息

#### 5.3 端到端验证清单

- [ ] Bark iOS 通知收到
- [ ] Telegram 通知收到
- [ ] Windows Toast 通知显示
- [ ] 权限拦截触发通知
- [ ] 命令错误触发通知
- [ ] 不同优先级正确路由
- [ ] VSCode 焦点检测工作正常

---

## 文件结构总览

```
C:\Users\36486\.claude\
├── notification-config.json      # 配置文件
├── notification-service.js       # 核心通知服务
├── vscode-focus.js               # VSCode 焦点检测
├── show-toast.ps1                # PowerShell Toast 脚本
├── test-notification.js          # 测试脚本
├── hooks\
│   ├── permission-blocked.js     # 权限拦截 Hook
│   ├── command-error.js          # 命令错误 Hook
│   └── user-prompt-submit.js     # 用户提示 Hook
└── settings.json                 # Claude Code 配置（需更新）
```

---

## 验收标准

1. **功能完整性**
   - [ ] 权限被拒绝时发送通知
   - [ ] 命令执行失败时发送通知
   - [ ] 支持多个推送渠道
   - [ ] Windows Toast 通知正常工作

2. **可靠性**
   - [ ] 通知发送失败不影响主流程
   - [ ] 支持重试机制
   - [ ] 错误日志清晰

3. **可用性**
   - [ ] 配置简单清晰
   - [ ] 支持多种推送服务
   - [ ] 通知优先级合理

---

## 业界最佳实践总结

### 1. 通知渠道选择策略

```
iOS 用户：
├── 主力：Bark（基于 APNs，最稳定）
└── 备用：Telegram Bot（需要科学上网）

非 iOS 用户：
└── 使用：Telegram Bot（需要科学上网）
```

### 2. Bark vs Telegram 对比

| 维度 | Bark | Telegram |
|------|------|----------|
| **稳定性** | ⭐⭐⭐⭐⭐ APNs 保障 | ⭐⭐⭐⭐⭐ 全球服务 |
| **实时性** | 秒级推送 | 秒级推送 |
| **成本** | 完全免费 | 完全免费 |
| **网络要求** | 国内直连 | 需要科学上网 |
| **设备要求** | 仅限 iOS | 全平台 |
| **推荐优先级** | **主力** | 备用 |

### 3. Hook 设计原则

- **非侵入式**：Hook 失败不应影响主流程
- **异步处理**：通知发送应为异步，不阻塞操作
- **错误隔离**：每个渠道独立 try-catch
- **降级策略**：主要渠道失败时自动降级

### 4. Windows 环境特殊考虑

- **权限问题**：PowerShell 脚本需要 ExecutionPolicy 绕过
- **路径问题**：Windows 路径使用反斜杠，需注意转义
- **编码问题**：中文字符需使用 UTF-8 编码
- **焦点检测**：使用 PowerShell 获取活动窗口信息

### 5. 成本优化

| 方案 | 月成本 | 适用场景 |
|------|--------|----------|
| Bark | ¥0 | iOS 用户（推荐） |
| Telegram | ¥0 | 需要科学上网 |
| 自建 Bark 服务器 | 服务器成本 | 隐私要求高 |

### 6. 安全建议

- Token 和 Webhook URL 存储在本地配置文件
- 不要将敏感凭证提交到版本控制
- 生产环境考虑使用环境变量
- 定期轮换 API Token

---

**参考来源：**
- [Bark GitHub](https://github.com/Finb/Bark)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Claude Code Hooks 文档](https://docs.anthropic.com/en/docs/build-with-claude/claude-for-developers)
