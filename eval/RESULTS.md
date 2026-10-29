# Heard benchmark: axe-core vs Heard

- Perception mode: native_av  
- Result source: live

| Metric | Value |
|---|---|
| axe-core detected | 4/12 |
| Heard detected | 10/12 |
| Fixes verified | 10/10 |
| Rejected as unsupported | 0 |
| Model calls / cost (USD, if prices set) / latency | 17 / 0.0195 / 267.7s |

## Per bug

| Bug | Site | Category | axe | Heard | Fix verified |
|---|---|---|---|---|---|
| B01 | shop | missing_name | yes | yes | yes |
| B02 | shop | missing_alt | yes | yes | yes |
| B04 | shop | vague_link | no | yes | yes |
| B10 | shop | repeated_control | no | yes | yes |
| B03 | signup | missing_label | no | no | no |
| B06 | signup | error_not_announced | no | yes | yes |
| B09 | signup | label_in_name | yes | yes | yes |
| B11 | signup | missing_state | no | yes | yes |
| B05 | dashboard | div_button | no | yes | yes |
| B07 | dashboard | modal_dialog | no | yes | yes |
| B08 | dashboard | tab_widget | no | no | no |
| B12 | dashboard | heading_skip | yes | yes | yes |

## Per category (bugs / axe / Heard)

- div_button: 1 / 0 / 1
- error_not_announced: 1 / 0 / 1
- heading_skip: 1 / 1 / 1  ← axe >= Heard
- label_in_name: 1 / 1 / 1  ← axe >= Heard
- missing_alt: 1 / 1 / 1  ← axe >= Heard
- missing_label: 1 / 0 / 0  ← axe >= Heard
- missing_name: 1 / 1 / 1  ← axe >= Heard
- missing_state: 1 / 0 / 1
- modal_dialog: 1 / 0 / 1
- repeated_control: 1 / 0 / 1
- tab_widget: 1 / 0 / 0  ← axe >= Heard
- vague_link: 1 / 0 / 1
