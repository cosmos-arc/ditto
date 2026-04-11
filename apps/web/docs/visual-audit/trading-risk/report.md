# Visual Audit: trading-risk

- Route: `/trading/risk`
- React URL: http://localhost:5173/trading/risk
- Prototype URL: http://localhost:8889/page-risk-center.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:22:19.156Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x803 | 0, 0, 56x900 | 0 | 0 | 0 | 97 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | 0, 876, 1536x24 | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| tabs | 56, 104, 1480x37 | missing | n/a | n/a | n/a | n/a |
| strip | 56, 68, 1480x36 | 56, 68, 1480x36 | 0 | 0 | 0 | 0 |
| main | missing | 56, 104, 1180x796 | n/a | n/a | n/a | n/a |
| alerts | missing | missing | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| banner | missing | missing | n/a | n/a | n/a | n/a |
| activity | missing | 1236, 104, 300x796 | n/a | n/a | n/a | n/a |
| analysis | missing | missing | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "tabs" has no matching react target
- targets: prototype target "alerts" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "banner" has no matching prototype target
- targets: react target "activity" has no matching prototype target
- targets: react target "analysis" has no matching prototype target
- prototype: Missing selector "main": .risk-main, .main-grid
- prototype: Missing selector "alerts": .risk-alerts, .breach-list
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "status": [data-slot='status-bar']
- react: Missing selector "banner": [data-slot='banner']
- react: Missing selector "analysis": [data-slot='analysis']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
