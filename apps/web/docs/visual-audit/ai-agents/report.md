# Visual Audit: ai-agents

- Route: `/ai/agents`
- React URL: http://localhost:5173/ai/agents
- Prototype URL: http://localhost:8889/page-agent-console.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:24:02.370Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | 0, 876, 1536x24 | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| tabs | 56, 68, 1480x36 | missing | n/a | n/a | n/a | n/a |
| main | 56, 104, 1140x796 | 296, 68, 940x412.78 | 240 | -36 | -200 | -383.22 |
| plans | 72, 164, 1108x167 | missing | n/a | n/a | n/a | n/a |
| inspector | missing | 1236, 68, 300x412.78 | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| source | missing | 56, 68, 240x412.78 | n/a | n/a | n/a | n/a |
| logs | missing | missing | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "tabs" has no matching react target
- targets: prototype target "plans" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "source" has no matching prototype target
- targets: react target "logs" has no matching prototype target
- prototype: Missing selector "inspector": .agent-inspector, .detail-panel
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "status": [data-slot='status-bar']
- react: Missing selector "logs": [data-slot='logs']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
