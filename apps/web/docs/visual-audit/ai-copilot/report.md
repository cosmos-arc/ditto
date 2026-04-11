# Visual Audit: ai-copilot

- Route: `/ai/copilot`
- React URL: http://localhost:5173/ai/copilot
- Prototype URL: http://localhost:8889/page-ai-copilot.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:23:46.624Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | 0, 876, 1536x24 | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| modes | 56, 68, 1480x32 | missing | n/a | n/a | n/a | n/a |
| source | 56, 100, 220x800 | 56, 68, 240x586.19 | 0 | -32 | 20 | -213.81 |
| main | missing | 296, 68, 940x586.19 | n/a | n/a | n/a | n/a |
| inspector | missing | 1236, 68, 300x586.19 | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| logs | missing | missing | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "modes" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "logs" has no matching prototype target
- prototype: Missing selector "main": .copilot-main, .chat-panel
- prototype: Missing selector "inspector": .copilot-inspector
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "status": [data-slot='status-bar']
- react: Missing selector "logs": [data-slot='logs']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
