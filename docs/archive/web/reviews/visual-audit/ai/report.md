# Visual Audit: ai

- Route: `/ai`
- React URL: http://localhost:5173/ai
- Prototype URL: http://localhost:8888/page-ai-overview.html
- Viewport: 1536x900
- Captured: 2026-04-12T16:26:42.361Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x876 | 0, 0, 56x900 | 0 | 0 | 0 | 24 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | 56, 852, 1480x24 | 56, 876, 1480x24 | 0 | 24 | 0 | 0 |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| strip | 56, 68, 1480x32 | 56, 68, 1480x32 | 0 | 0 | 0 | 0 |
| main | 56, 100, 1160x752 | 56, 100, 1160x776 | 0 | 0 | 0 | 24 |
| queue | missing | missing | n/a | n/a | n/a | n/a |
| inspector | missing | missing | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| sidebar | missing | 1216, 100, 320x776 | n/a | n/a | n/a | n/a |
| statusSlot | missing | missing | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "queue" has no matching react target
- targets: prototype target "inspector" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "sidebar" has no matching prototype target
- targets: react target "statusSlot" has no matching prototype target
- prototype: Missing selector "queue": .queue-panel, .agent-queue
- prototype: Missing selector "inspector": .ai-inspector, .inspector-panel
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "statusSlot": [data-slot='status']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
