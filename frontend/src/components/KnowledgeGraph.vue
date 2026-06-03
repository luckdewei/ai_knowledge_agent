<template>
  <div class="knowledge-graph">
    <div v-if="loading" class="graph-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载关系网络...</span>
    </div>
    <div v-else-if="!network?.nodes?.length" class="graph-empty">
      <el-empty description="暂无关系数据，请先积累知识并建立关联" />
    </div>
    <div v-show="network?.nodes?.length" ref="chartRef" class="graph-chart" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { insightsApi } from '@/api/insights'
import type { KnowledgeNetwork } from '@/api/types'

const props = defineProps<{
  knowledgeId: string | null
  depth?: number
}>()

const chartRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const network = ref<KnowledgeNetwork | null>(null)
let chart: echarts.ECharts | null = null

async function load() {
  if (!props.knowledgeId) {
    network.value = null
    chart?.clear()
    return
  }
  loading.value = true
  try {
    const res = await insightsApi.getKnowledgeNetwork(props.knowledgeId, props.depth ?? 2)
    network.value = res.data ?? { nodes: [], edges: [] }
    await new Promise((r) => requestAnimationFrame(r))
    render()
  } finally {
    loading.value = false
  }
}

function render() {
  if (!chartRef.value || !network.value?.nodes.length) return
  if (!chart) chart = echarts.init(chartRef.value)

  const centerId = props.knowledgeId
  const nodes = network.value.nodes.map((n) => ({
    id: n.id,
    name: n.title,
    symbolSize: n.id === centerId ? 48 : 28,
    itemStyle: {
      color: n.id === centerId ? '#1890ff' : '#52c41a',
    },
    label: { show: true, fontSize: 10 },
  }))

  const links = network.value.edges.map((e) => ({
    source: e.source,
    target: e.target,
    value: e.weight,
    lineStyle: { width: Math.max(1, e.weight * 3), curveness: 0.2 },
  }))

  chart.setOption({
    tooltip: {},
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        force: {
          repulsion: 280,
          edgeLength: [80, 160],
          gravity: 0.1,
        },
        data: nodes,
        links,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 8,
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 4 },
        },
      },
    ],
  })
}

function onResize() {
  chart?.resize()
}

watch(() => props.knowledgeId, load, { immediate: true })

onMounted(() => {
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.knowledge-graph {
  width: 100%;
  height: 100%;
  min-height: 400px;
  position: relative;
}

.graph-chart {
  width: 100%;
  height: 400px;
}

.graph-loading,
.graph-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  gap: 8px;
  color: #666;
}
</style>
