<template>
  <div class="settings-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>API 密钥配置</span>
          <el-text type="info" size="small">
            未在页面填写的项将自动使用 backend/.env；保存后即时生效
          </el-text>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="8" animated />

      <template v-else>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="tip-alert"
          title="填写说明"
          description="输入新密钥并保存；若某字段留空并保存，将清除页面覆盖并恢复为 .env 中的值。列表中显示为掩码，不会回显完整密钥。"
        />

        <el-form
          ref="formRef"
          :model="form"
          label-width="160px"
          label-position="right"
          class="settings-form"
        >
          <template v-for="group in groupedFields" :key="group.name">
            <el-divider content-position="left">{{ group.name }}</el-divider>
            <el-form-item
              v-for="field in group.items"
              :key="field.key"
              :label="field.label"
            >
              <div class="field-row">
                <el-input
                  v-model="form[field.key]"
                  type="password"
                  show-password
                  clearable
                  :placeholder="placeholderFor(field)"
                  autocomplete="new-password"
                />
                <div class="field-meta">
                  <el-tag size="small" :type="sourceTagType(field.source)">
                    {{ sourceLabel(field.source) }}
                  </el-tag>
                  <span v-if="field.masked_value" class="masked">
                    当前：{{ field.masked_value }}
                  </span>
                  <span v-else class="masked none">未配置</span>
                </div>
                <div class="field-desc">{{ field.description }}</div>
                <div class="env-hint">环境变量：{{ field.env_var }}</div>
                <el-button
                  v-if="field.runtime_configured"
                  link
                  type="primary"
                  size="small"
                  class="restore-btn"
                  @click="restoreEnv(field.key)"
                >
                  恢复为 .env
                </el-button>
              </div>
            </el-form-item>
          </template>

          <el-form-item>
            <el-button type="primary" :loading="saving" @click="onSave">
              保存配置
            </el-button>
            <el-button @click="onResetForm">重置表单</el-button>
          </el-form-item>
        </el-form>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  settingsApi,
  type ApiKeyFieldView,
  type SettingsSource,
  type UpdateApiKeysPayload,
} from '@/api/settings'

const loading = ref(true)
const saving = ref(false)
const fields = ref<ApiKeyFieldView[]>([])

const form = reactive<Record<string, string>>({
  deepseek_api_key: '',
  embedding_api_key: '',
  speech_api_key: '',
  tavily_api_key: '',
  smtp_username: '',
  smtp_password: '',
})

const groupedFields = computed(() => {
  const map = new Map<string, ApiKeyFieldView[]>()
  for (const f of fields.value) {
    const g = f.group || '其他'
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(f)
  }
  return [...map.entries()].map(([name, items]) => ({ name, items }))
})

function sourceLabel(source: SettingsSource) {
  if (source === 'runtime') return '页面配置'
  if (source === 'env') return '.env'
  return '未配置'
}

function sourceTagType(source: SettingsSource) {
  if (source === 'runtime') return 'success'
  if (source === 'env') return 'warning'
  return 'info'
}

function placeholderFor(field: ApiKeyFieldView) {
  if (field.runtime_configured) {
    return '留空并保存可清除页面配置，改回 .env'
  }
  if (field.env_configured) {
    return '留空则使用 .env 中已配置的密钥'
  }
  return '请输入密钥'
}

function clearFormInputs() {
  for (const key of Object.keys(form)) {
    form[key] = ''
  }
}

async function load() {
  loading.value = true
  try {
    const res = await settingsApi.getKeys()
    fields.value = res.data?.fields ?? []
    clearFormInputs()
  } catch (e) {
    ElMessage.error(`加载配置失败：${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}

function buildPayload(): UpdateApiKeysPayload {
  const payload: UpdateApiKeysPayload = {}
  for (const [key, val] of Object.entries(form)) {
    const trimmed = val.trim()
    if (trimmed) {
      payload[key as keyof UpdateApiKeysPayload] = trimmed
    }
  }
  return payload
}

async function restoreEnv(key: string) {
  saving.value = true
  try {
    const res = await settingsApi.saveKeys({
      [key]: '',
    } as UpdateApiKeysPayload)
    fields.value = res.data?.fields ?? fields.value
    form[key] = ''
    ElMessage.success('已恢复为 .env 配置')
  } catch (e) {
    ElMessage.error(`操作失败：${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

async function onSave() {
  const payload = buildPayload()
  if (!Object.keys(payload).length) {
    ElMessage.warning('请至少填写一项要保存的密钥，或使用「恢复为 .env」')
    return
  }
  saving.value = true
  try {
    const res = await settingsApi.saveKeys(payload)
    fields.value = res.data?.fields ?? fields.value
    clearFormInputs()
    ElMessage.success(res.data?.message ?? '已保存')
  } catch (e) {
    ElMessage.error(`保存失败：${(e as Error).message}`)
  } finally {
    saving.value = false
  }
}

function onResetForm() {
  clearFormInputs()
}

onMounted(load)
</script>

<style scoped>
.settings-page {
  max-width: 880px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tip-alert {
  margin-bottom: 20px;
}

.settings-form {
  margin-top: 8px;
}

.field-row {
  width: 100%;
  max-width: 520px;
}

.field-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.masked {
  font-size: 12px;
  color: #666;
}

.masked.none {
  color: #999;
}

.field-desc {
  font-size: 12px;
  color: #888;
  margin-top: 4px;
}

.env-hint {
  font-size: 11px;
  color: #aaa;
  margin-top: 2px;
  font-family: monospace;
}

.restore-btn {
  margin-top: 4px;
  padding: 0;
}
</style>
