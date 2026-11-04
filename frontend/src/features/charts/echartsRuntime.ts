/**
 * The ONLY module that imports echarts. It is loaded with a dynamic `import()` (see `loadEcharts`), so Vite
 * emits it as its own chunk and the shell never pays for charts until one is shown. Only the pieces the chart
 * kinds need are registered (tree-shaken `echarts/core` build; no `import * as echarts`).
 */
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { DataZoomInsideComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, BarChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, DataZoomInsideComponent, CanvasRenderer]);

export { init };
export type { ECharts };
