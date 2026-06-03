<template>
  <div class="dashboard" v-loading="loading">
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="知识总量" :value="stats?.total_knowledge ?? 0" />
        </el-card>
      </el-col>
      <el-col v-for="(count, type) in stats?.by_source_type ?? {}" :key="type" :span="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic :title="sourceLabel(type)" :value="count" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card health">
          <div class="health-label">服务状态</div>
          <el-tag :type="healthOk ? 'success' : 'danger'" size="large">
            {{ healthOk ? '正常' : '异常' }}
          </el-tag>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>知识活跃度趋势</template>
          <TrendChart :data="trendData" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>标签云</template>
          <TagCloud :tags="stats?.top_tags ?? []" show-count @select="onTagSelect" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="section-row">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>上升主题</span>
            <el-text type="info" size="small" class="header-sub">
              {{ attention?.period?.early }} ~ {{ attention?.period?.late }}
            </el-text>
          </template>
          <el-table :data="attention?.rising_tags ?? []" size="small" stripe>
            <el-table-column prop="tag" label="标签" />
            <el-table-column prop="late_count" label="近期" width="72" />
            <el-table-column label="变化" width="100">
              <template #default="{ row }">
                <el-text type="success">+{{ row.change_percent }}%</el-text>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>下降主题</template>
          <el-table :data="attention?.falling_tags ?? []" size="small" stripe>
            <el-table-column prop="tag" label="标签" />
            <el-table-column prop="late_count" label="近期" width="72" />
            <el-table-column label="变化" width="100">
              <template #default="{ row }">
                <el-text type="danger">{{ row.change_percent }}%</el-text>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="attention?.insights?.length" shadow="never" class="insights-card">
      <template #header>趋势洞察</template>
      <ul class="insight-list">
        <li v-for="(tip, i) in attention.insights" :key="i">{{ tip }}</li>
      </ul>
    </el-card>

    <el-card shadow="never" class="upload-card">
      <template #header>快速导入</template>
      <FileUpload @success="onUploadSuccess" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { knowledgeApi } from '@/api/knowledge'
import { insightsApi } from '@/api/insights'
import { healthApi } from '@/api/health'
import type { KnowledgeStats, TrendPoint, AttentionShift } from '@/api/types'
import TrendChart from '@/components/TrendChart.vue'
import TagCloud from '@/components/TagCloud.vue'
import FileUpload from '@/components/FileUpload.vue'

const router = useRouter()
const loading = ref(false)
const healthOk = ref(false)
const stats = ref<KnowledgeStats | null>(null)
const trendData = ref<TrendPoint[]>([])
const attention = ref<AttentionShift | null>(null)

const sourceLabels: Record<string, string> = {
  file: '文件',
  url: '网页',
  clipboard: '剪贴板',
  voice: '语音',
  wechat: '微信',
}

function sourceLabel(type: string) {
  return sourceLabels[type] ?? type
}

function onTagSelect(tag: string) {
  router.push({ path: '/knowledge', query: { tag } })
}

async function load() {
  loading.value = true
  try {
    const [healthRes, statsRes, trendRes, attentionRes] = await Promise.all([
      healthApi.check(),
      knowledgeApi.getStats(),
      insightsApi.getActivityTrend(90),
      insightsApi.getAttentionShift(90),
    ])
    healthOk.value = healthRes.data?.status === 'healthy'
    stats.value = statsRes.data ?? null
    trendData.value = trendRes.data ?? []
    attention.value = attentionRes.data ?? null
  } finally {
    loading.value = false
  }
}

async function onUploadSuccess() {
  await load()
}

onMounted(load)
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-card {
  text-align: center;
}

.stat-card.health {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 88px;
}

.health-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.header-sub {
  margin-left: 8px;
}

.section-row {
  margin-top: 0;
}

.insight-list {
  margin: 0;
  padding-left: 20px;
  line-height: 1.8;
  color: #555;
}

.upload-card {
  margin-bottom: 8px;
}
</style>
