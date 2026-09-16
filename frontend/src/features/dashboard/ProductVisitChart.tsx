import { BarChart } from 'echarts/charts'
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import {
  init,
  use as registerECharts,
  type EChartsCoreOption,
  type EChartsType,
} from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'

import type { MonthlyProductVisitItem } from '../../api/types'
import { dashboardColors } from './dashboardTheme'

registerECharts([
  BarChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  AriaComponent,
  CanvasRenderer,
])

interface ProductVisitChartProps {
  items: MonthlyProductVisitItem[]
  month: string
}

function chartOption(
  items: MonthlyProductVisitItem[],
  month: string,
): EChartsCoreOption {
  const showDataZoom = items.length > 8
  return {
    aria: {
      enabled: true,
      description: `${month} 产品月度拜访次数柱状图，展示总数、正常、异常和待评估次数。`,
    },
    color: [
      dashboardColors.total,
      dashboardColors.normal,
      dashboardColors.abnormal,
      dashboardColors.pending,
    ],
    animationDuration: 250,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (value: unknown) => `${String(value)} 次`,
    },
    legend: {
      top: 0,
      data: ['总数', '正常', '异常', '待评估'],
    },
    grid: {
      top: 52,
      right: 24,
      bottom: showDataZoom ? 92 : 66,
      left: 56,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.product.name),
      axisLabel: {
        interval: 0,
        rotate: items.length > 5 ? 20 : 0,
        width: 130,
        overflow: 'truncate',
      },
    },
    yAxis: {
      type: 'value',
      name: '拜访次数',
      minInterval: 1,
      min: 0,
    },
    dataZoom: showDataZoom
      ? [
          {
            type: 'inside',
            startValue: 0,
            endValue: 7,
          },
          {
            type: 'slider',
            height: 18,
            bottom: 20,
            startValue: 0,
            endValue: 7,
          },
        ]
      : [],
    series: [
      {
        name: '总数',
        type: 'bar',
        data: items.map((item) => item.totalCount),
        barMaxWidth: 34,
      },
      {
        name: '正常',
        type: 'bar',
        data: items.map((item) => item.normalCount),
        barMaxWidth: 34,
      },
      {
        name: '异常',
        type: 'bar',
        data: items.map((item) => item.abnormalCount),
        barMaxWidth: 34,
      },
      {
        name: '待评估',
        type: 'bar',
        data: items.map((item) => item.pendingCount),
        barMaxWidth: 34,
      },
    ],
  }
}

export function ProductVisitChart({ items, month }: ProductVisitChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }
    const chart: EChartsType = init(container, undefined, {
      renderer: 'canvas',
    })
    chart.setOption(chartOption(items, month))
    const resizeObserver = new ResizeObserver(() => chart.resize())
    resizeObserver.observe(container)
    return () => {
      resizeObserver.disconnect()
      chart.dispose()
    }
  }, [items, month])

  return (
    <div
      ref={containerRef}
      className="product-visit-chart"
      role="img"
      aria-label={`${month} 产品月度拜访次数柱状图`}
    />
  )
}
