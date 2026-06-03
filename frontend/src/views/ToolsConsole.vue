<template>
  <div class="tools-page">
    <el-row :gutter="16">
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>可用工具</template>
          <el-skeleton v-if="loadingList" :rows="4" animated />
          <el-collapse v-else v-model="activeTool">
            <el-collapse-item
              v-for="tool in tools"
              :key="tool.name"
              :title="tool.name"
              :name="tool.name"
            >
              <p class="tool-desc">{{ tool.description }}</p>
              <el-tag
                v-for="p in tool.parameters"
                :key="p.name"
                size="small"
                class="param-tag"
              >
                {{ p.name }}{{ p.required ? '*' : '' }} ({{ p.type }})
              </el-tag>
            </el-collapse-item>
          </el-collapse>
          <el-empty v-if="!loadingList && !tools.length" description="暂无已注册工具" />
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card shadow="never">
          <template #header>调用工具</template>
          <el-form label-width="88px">
            <el-form-item label="工具">
              <el-select v-model="form.tool_name" placeholder="选择工具" style="width: 100%">
                <el-option
                  v-for="t in tools"
                  :key="t.name"
                  :label="t.name"
                  :value="t.name"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="参数 JSON">
              <el-input
                v-model="form.paramsJson"
                type="textarea"
                :rows="10"
                placeholder='{"action":"list","status":"pending"}'
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="executing" @click="onExecute">
                执行
              </el-button>
              <el-button @click="fillPreset">填充示例</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card v-if="lastResult" shadow="never" class="result-card">
          <template #header>
            执行结果
            <el-tag :type="lastResult.success ? 'success' : 'danger'" size="small">
              {{ lastResult.success ? '成功' : '失败' }}
            </el-tag>
          </template>
          <pre class="result-json">{{ formatResult(lastResult) }}</pre>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { toolsApi, type ToolInfo, type ToolExecuteResult } from '@/api/tools'

const tools = ref<ToolInfo[]>([])
const loadingList = ref(false)
const executing = ref(false)
const activeTool = ref<string[]>([])
const lastResult = ref<ToolExecuteResult | null>(null)

const form = ref({
  tool_name: 'todo',
  paramsJson: '{\n  "action": "list",\n  "status": "pending"\n}',
})

const presets: Record<string, string> = {
  todo: '{\n  "action": "list",\n  "status": "pending"\n}',
  search: '{\n  "query": "Python",\n  "source": "knowledge",\n  "top_k": 5\n}',
  calendar: '{\n  "action": "query",\n  "days": 7\n}',
  email: '{\n  "action": "send",\n  "to": "user@example.com",\n  "subject": "测试",\n  "body": "你好"\n}',
}

async function loadTools() {
  loadingList.value = true
  try {
    const res = await toolsApi.list()
    tools.value = res.data ?? []
    if (tools.value.length && !form.value.tool_name) {
      form.value.tool_name = tools.value[0].name
    }
  } finally {
    loadingList.value = false
  }
}

function fillPreset() {
  form.value.paramsJson = presets[form.value.tool_name] ?? '{}'
}

async function onExecute() {
  let params: Record<string, unknown>
  try {
    params = JSON.parse(form.value.paramsJson)
  } catch {
    ElMessage.error('参数 JSON 格式不正确')
    return
  }
  executing.value = true
  try {
    const res = await toolsApi.execute(form.value.tool_name, params)
    lastResult.value = res.data ?? null
    ElMessage.success('执行完成')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    executing.value = false
  }
}

function formatResult(r: ToolExecuteResult) {
  return JSON.stringify(r, null, 2)
}

onMounted(loadTools)
</script>

<style scoped>
.tools-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tool-desc {
  color: #666;
  font-size: 13px;
  margin-bottom: 8px;
}

.param-tag {
  margin: 0 6px 6px 0;
}

.result-card {
  margin-top: 16px;
}

.result-json {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  overflow: auto;
  max-height: 360px;
}
</style>
