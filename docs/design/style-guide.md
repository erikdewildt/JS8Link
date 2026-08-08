# JS8Link Station Console style guide

This guide is the visual and interaction baseline for JS8Link. New screens and extensions must
build on it. The target is a professional amateur-radio console: compact, information-rich and
operational, without looking like a generic website.

## Design principles

1. **Radio instrument, not website.** Fill the viewport with fixed work panels and thin dividers;
   avoid a centered page made from detached cards.
2. **Telemetry must be scannable.** Frequency, band, mode, offset, RX/TX, connection and UTC belong
   together in the station bar and use tabular figures.
3. **Dense but calm.** Use compact controls, clear hierarchy and color only for meaning.
4. **Responsive by default.** On smaller screens move secondary information to a detail sheet; never
   remove functionality.
5. **Dark and light are equal.** Both themes keep the same hierarchy, dimensions and semantic colors.

## Visual references

These images are normative visual references. Use the reference for the screen being changed first,
then this written guide, then the other images for component details. Callsigns and measurements in
the images are sample data only.

### Chat — primary station console

![JS8Link Station Console — chat](references/station-console-chat.png)

### Chat — operator workbench detail

![JS8Link Operator Workbench — chat](references/operator-workbench-chat.png)

### Band monitor — station console

![JS8Link Station Console — band monitor](references/station-console-band-monitor.png)

## Design tokens

Use the CSS custom properties in `frontend/src/index.css` and `frontend/src/precision.css`. Add a
shared token when a new meaning is needed; do not add component-specific hex colors.

| Meaning | Dark | Light |
|---|---:|---:|
| App background | `#090c10` | `#edf1f5` |
| Panel | `#0f1318` | `#ffffff` |
| Raised panel / input | `#151a20` | `#f7f9fb` |
| Hover / selection | `#1b2430` | `#e7eef6` |
| Divider | `#27313b` | `#cbd3dc` |
| Primary text | `#e6ebf1` | `#17202a` |
| Secondary text | `#8f9aa7` | `#596573` |
| RX / interactive blue | `#4b9eff` | `#1269c7` |
| TX / warning amber | `#f3a11a` | `#a95a00` |
| Connected green | `#62c277` | `#247b3c` |
| Error red | `#f06464` | `#b4232c` |

The `forest` theme is the earthy dark variant: near-black green surfaces, lichen green for RX and
connection, clay orange for TX, and warm sand text. `field-light` is its light counterpart: warm
ivory surfaces, olive green RX/connection and terracotta TX. All themes keep the same layout and
responsive behavior. Use no gradients or decorative glass effects. Standard radius is 3px; large
panels may use 6px. Shadows are reserved for modals, popovers and floating map information.

## Typography

- Use locally bundled IBM Plex Sans for interface text and IBM Plex Mono for frequencies, offsets,
  times, callsigns, radio logs and measurements.
- Base text is 13px. Panel titles are 12px, semibold, uppercase and lightly letter-spaced.
- VFO is 22–30px on desktop and at least 17px on mobile, weight 400 with slight positive tracking.
- Do not use decorative display fonts or CDN-hosted fonts.

## Application shell and station bar

The flat station bar runs across the top with a bottom divider. From left to right it contains the
JS8Link mark and station, primary navigation, VFO and band, mode and speed, offset and Auto/Fixed
state, RX/TX activity, JS8Call status, time, settings and help.

Instrument groups use vertical dividers rather than rounded capsules. RX is blue, TX amber and
connection green. Every color status also has a text or accessible label. VFO is the visual focus and
uses `14.074.000`, never a small form-like number. The bandscope below the bar is a real recent-data
visualization covering at least 500–2500 Hz: heartbeat 500–1000 Hz, JS8 passband 1000–2500 Hz, blue
received signals, amber local TX and a thin dotted amber offset marker.

## Work panels

- Panels touch and use 1px dividers; headers are 40–56px with title, context and local actions.
- Tables use sticky headers, compact rows and monospaced measurements.
- Chat uses three columns on wide screens: conversations, transcript and station inspector.
- Chat messages are full-width radio log rows with RX/TX badges, callsign, text and metadata; do not
  use oversized rounded chat bubbles.
- Forms use section headings and responsive grids rather than one large stack of floating cards.
- ShadCN/UI primitives remain the basis for Button, Input, Select, Switch, Tabs, Dialog and Textarea.

## Band monitor

The command bar contains traffic, station and relationship counts plus shared band/history filters.
The map and lower table touch; only the 12px horizontal resize bar separates them. Show the SNR scale
from red (`-20`) through amber (`-7`) and green (`0`) to blue (`+10 dB`). Each connection half uses the
color of the receive SNR at that endpoint. An unknown endpoint remains visible as a subtle, clearly
contrasting dotted line. This also applies to grouped connections.

Use OpenStreetMap tiles. Dim and desaturate them in dark themes; keep normal brightness in light
themes. Keep markers and controls unaffected. The lower panel shares one header for `Traffic`, `By
offset` and `Last heard`; use compact uppercase headers and monospaced data. RX is blue, TX amber,
derived callsigns amber and errors red.

## Settings, dialogs and setup

Settings use a title header, connection status and tabs for Application and JS8Call. Use numbered
console panels, full-width switch rows, a responsive two-column desktop grid and one column on mobile.
Keep Save in a sticky bottom bar. Dialogs are normally 620px wide (760px for changelog), use a 3px
blue left accent and a fixed action bar. On mobile they become bottom sheets with internal scrolling.
Setup and login share the console background and compact brand bar; wizard steps form one instrument
strip with a blue active state.

## Color and iconography

RX blue marks navigation selection, received traffic and active data. TX amber is reserved for
transmission, queues and airtime-impacting actions. Green means confirmed connection, confirmation or
good SNR. Red means error, block, poor SNR or destructive action. Use locally bundled Tabler Icons
for navigation and the station console; existing Lucide/ShadCN icons may remain inside form controls.
Use a consistent 1.6–1.8px stroke, 16–20px sizes, and never use emoji or hand-drawn SVG icons.

## Responsive behavior

- At 1200px and above, keep the full station bar and three-column chat layout.
- Between 768px and 1199px, compress instrument cells and allow the inspector to collapse.
- Below 768px, stack panels, make the station bar horizontally scrollable, and use sheets for the
  inspector and help. Keep the composer and primary actions visible without page-level scrolling.
- Use dynamic viewport units and keep every scrollable region inside its panel.

## Maintenance checklist

Before merging a UI change, compare it with the relevant reference image, test dark/light and narrow
viewports, keep semantic colors consistent, verify keyboard focus and tooltips, and update the
matching local help topic and screenshot when the change is substantial.
