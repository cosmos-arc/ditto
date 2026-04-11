# Visual Audit: trading-signals

- Route: `/trading/signals`
- React URL: http://localhost:5173/trading/signals
- Prototype URL: http://localhost:8889/page-signals-inbox.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:21:45.918Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | 0, 876, 1536x24 | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| toolbar | 56, 68, 1480x36 | missing | n/a | n/a | n/a | n/a |
| main | 56, 104, 1100x796 | 56, 101.14, 1140x798.86 | 0 | -2.86 | 40 | 2.86 |
| detail | 1156, 104, 380x796 | 1196, 101.14, 340x798.86 | 40 | -2.86 | -40 | 2.86 |
| table | missing | missing | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| filter | missing | missing | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "table" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "filter" has no matching prototype target
- prototype: Missing selector "table": .signals-table, .signals-list
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "status": [data-slot='status-bar']
- react: Missing selector "toolbar": [data-slot='toolbar']
- react: Missing selector "filter": [data-slot='filter-toolbar']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
