# Visual Audit: markets-screener

- Route: `/markets/screener`
- React URL: http://localhost:5173/markets/screener
- Prototype URL: http://localhost:8889/page-markets-screener.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:22:37.270Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x283.50 | 0, 0, 56x900 | 0 | 0 | 0 | 616.50 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | missing | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| toolbar | 56, 68, 1480x32 | 56, 68, 1480x36.14 | 0 | 0 | 0 | 4.14 |
| main | missing | 56, 104.14, 1160x795.86 | n/a | n/a | n/a | n/a |
| detail | 1216, 100, 320x183.50 | 1216, 104.14, 320x795.86 | 0 | 4.14 | 0 | 612.36 |
| table | missing | missing | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| filter | missing | 56, 68, 1480x36.14 | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "table" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- targets: react target "filter" has no matching prototype target
- prototype: Missing selector "status": .status-bar
- prototype: Missing selector "main": .catalog-main, .screener-main
- prototype: Missing selector "table": .screener-table, .results-table
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "status": [data-slot='status-bar']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
