<template>
  <div ref="chartRef" class="trend-chart" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { TrendPoint } from '@/api/types'

const props = defineProps<{
  data: TrendPoint[]
  title?: string
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function render() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)

  const dates = props.data.map((d) => d.date)
  const counts = props.data.map((d) => d.count)

  chart.setOption({
    title: props.title ? { text: props.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const p = (params as { dataIndex: number }[])[0]
        const point = props.data[p?.dataIndex]
        if (!point) return ''
        const tags = point.tags?.length ? `<br/>标签: ${point.tags.join(', ')}` : ''
        return `${point.date}<br/>新增: ${point.count}${tags}`
      },
    },
    grid: { left: 48, right: 24, top: props.title ? 48 : 24, bottom: 32 },
    xAxis: { type: 'category', data: dates, axisLabel: { rotate: dates.length > 10 ? 35 : 0 } },
    yAxis: { type: 'value', name: '条数', minInterval: 1 },
    series: [
      {
        name: '知识新增',
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.15 },
        itemStyle: { color: '#1890ff' },
        data: counts,
      },
    ],
  })
}

function onResize() {
  chart?.resize()
}

watch(() => props.data, render, { deep: true })

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.trend-chart {
  width: 100%;
  height: 320px;
}
</style>
