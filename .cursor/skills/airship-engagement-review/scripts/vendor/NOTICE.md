# Vendored third-party assets

## chart.umd.min.js — Chart.js v4.4.4
- Source: https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js
- Project: https://www.chartjs.org/  ·  https://github.com/chartjs/Chart.js
- License: MIT (© Chart.js Contributors)

Vendored (not fetched from a CDN at runtime) so the interactive HTML report stays a
single, self-contained, offline file: `report_interactive.chartjs_inline()` reads this
file and embeds it in a `<script>` tag.

UMD build exposes the global `window.Chart`. We use only category/linear scales (date
labels are pre-formatted strings), so no date adapter is required.

To refresh for a new Chart.js release:
    curl -sSL "https://cdn.jsdelivr.net/npm/chart.js@<version>/dist/chart.umd.min.js" \
      -o scripts/vendor/chart.umd.min.js
