# Visual Audit: instrument-hub

- Route: `/instruments/$id`
- React URL: http://localhost:5173/instruments/600519
- Prototype URL: http://localhost:8889/page-instrument-hub.html
- Viewport: 1536x900
- Captured: 2026-04-11T15:24:20.818Z

## Target Rect Deltas

| Target | Prototype | React | Δx | Δy | Δw | Δh |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| rail | 0, 0, 56x876 | 0, 0, 56x900 | 0 | 0 | 0 | 24 |
| header | 72, 6.09, 1448x55.80 | 56, 0, 1480x68 | -16 | -6.09 | 32 | 12.20 |
| status | 0, 876, 1536x24 | missing | n/a | n/a | n/a | n/a |
| shell | 0, 0, 1536x900 | 0, 0, 1536x900 | 0 | 0 | 0 | 0 |
| meta | 56, 68, 1480x36 | 56, 68, 1480x62.20 | 0 | 0 | 0 | 26.20 |
| tabs | 56, 0, 1480x68 | 56, 68, 1480x531.89 | 0 | 68 | 0 | 463.89 |
| main | 56, 149, 1480x533 | 56, 159.34, 1480x440.55 | 0 | 10.34 | 0 | -92.45 |
| bottom | 56, 682, 1480x194 | missing | n/a | n/a | n/a | n/a |
| content | missing | 56, 68, 1480x832 | n/a | n/a | n/a | n/a |
| layout | missing | 56, 68, 1480x531.89 | n/a | n/a | n/a | n/a |

## Warnings

- targets: react target "content" has no matching prototype target
- targets: react target "layout" has no matching prototype target
- prototype: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- prototype: requestfailed script https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js: net::ERR_TIMED_OUT
- prototype: console error: Failed to load resource: net::ERR_TIMED_OUT
- prototype: pageerror: LightweightCharts is not defined
- react: Missing selector "status": [data-slot='status-bar']
- react: Missing selector "bottom": [data-slot='bottom']
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
- react: requestfailed stylesheet https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap: net::ERR_TIMED_OUT
- react: console error: Failed to load resource: net::ERR_TIMED_OUT
