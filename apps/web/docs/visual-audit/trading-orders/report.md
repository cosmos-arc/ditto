# Visual Audit: trading-orders

- Route: `/trading/orders`
- React URL: http://localhost:5173/trading/orders
- Prototype URL: http://localhost:8889/page-orders-ledger.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:22:03.985Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x900 | 0, 0, 56x900 | 0 | 0 | 0 | 0 |
| header | 56, 0, 1480x68 | 56, 0, 1480x68 | 0 | 0 | 0 | 0 |
| status | 0, 876, 1536x24 | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| health | 56, 68, 1480x36 | 56, 68, 1480x33.14 | 0 | 0 | 0 | -2.86 |
| main | missing | 56, 101.14, 1140x798.86 | n/a | n/a | n/a | n/a |
| detail | missing | 1196, 101.14, 340x798.86 | n/a | n/a | n/a | n/a |
| table | 56, 152, 1140x387.50 | missing | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |

## Warnings

- targets: prototype target "table" has no matching react target
- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- prototype: Missing selector "main": .orders-main, .ledger-main
- prototype: Missing selector "detail": .order-detail, .detail-panel
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: Missing selector "status": [data-slot='status-bar']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
