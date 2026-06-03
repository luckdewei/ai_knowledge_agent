<template>
  <div class="knowledge-page">
    <el-row :gutter="16" class="page-header">
      <el-col :span="16">
        <el-input
          v-model="keyword"
          placeholder="语义搜索知识库..."
          clearable
          @keyup.enter="onSearch"
        >
          <template #append>
            <el-button :icon="Search" @click="onSearch">搜索</el-button>
          </template>
        </el-input>
      </el-col>
      <el-col :span="8" class="header-actions">
        <el-button @click="onRefresh">刷新</el-button>
        <el-button type="primary" @click="showCreate = true">新建</el-button>
      </el-col>
    </el-row>

    <FileUpload class="upload-section" @success="onUploadSuccess" />

    <el-row :gutter="16" class="main-content">
      <el-col :span="8">
        <el-card shadow="never" class="list-card" v-loading="store.loading">
          <template #header>
            <span>知识列表 ({{ store.displayList.length }})</span>
          </template>
          <el-scrollbar height="calc(100vh - 340px)">
            <div
              v-for="item in store.displayList"
              :key="item.id"
              class="list-item"
              :class="{ active: store.selectedId === item.id }"
              @click="store.select(item.id)"
            >
              <div class="item-title">{{ item.title }}</div>
              <div class="item-meta">
                <el-tag size="small" type="info">{{ item.source_type }}</el-tag>
                <span>{{ formatDate(item.created_at) }}</span>
              </div>
              <div v-if="item.tags?.length" class="item-tags">
                <el-tag v-for="t in item.tags.slice(0, 3)" :key="t" size="small">{{ t }}</el-tag>
              </div>
            </div>
            <el-empty v-if="!store.displayList.length" description="暂无知识条目" />
          </el-scrollbar>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never" class="detail-card">
          <template v-if="store.selected">
            <div class="detail-toolbar">
              <el-radio-group v-model="viewMode" size="small">
                <el-radio-button value="preview">预览</el-radio-button>
                <el-radio-button value="edit">编辑</el-radio-button>
                <el-radio-button value="graph">关系图</el-radio-button>
              </el-radio-group>
              <el-button type="danger" text @click="onDelete">删除</el-button>
            </div>

            <template v-if="viewMode === 'preview'">
              <h2 class="detail-title">{{ store.selected.title }}</h2>
              <div class="detail-meta">
                <el-tag>{{ store.selected.source_type }}</el-tag>
                <span>更新于 {{ formatDate(store.selected.updated_at) }}</span>
              </div>
              <div v-if="store.selected.tags?.length" class="detail-tags">
                <el-tag v-for="t in store.selected.tags" :key="t">{{ t }}</el-tag>
              </div>
              <el-divider />
              <MarkdownBody class="detail-content" :content="previewContent" />
            </template>

            <template v-else-if="viewMode === 'edit'">
              <el-form label-width="72px">
                <el-form-item label="标题">
                  <el-input v-model="editForm.title" />
                </el-form-item>
                <el-form-item label="标签">
                  <el-select
                    v-model="editForm.tags"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    placeholder="输入标签"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item label="内容">
                  <div class="edit-md-layout">
                    <div class="edit-md-pane">
                      <div class="pane-head">
                        <span>Markdown</span>
                        <el-button link type="primary" @click="onFormatMarkdown">
                          整理为 Markdown
                        </el-button>
                      </div>
                      <el-input
                        v-model="editForm.content"
                        type="textarea"
                        :rows="16"
                        placeholder="支持 Markdown：标题 #、列表 -、代码块 ```"
                        class="md-source-input"
                      />
                    </div>
                    <div class="edit-md-pane edit-md-preview-pane">
                      <div class="pane-head"><span>预览</span></div>
                      <el-scrollbar class="edit-preview-scroll">
                        <MarkdownBody class="edit-preview-body" :content="editPreviewContent" />
                      </el-scrollbar>
                    </div>
                  </div>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
                  <el-button @click="resetEdit">重置</el-button>
                </el-form-item>
              </el-form>
            </template>

            <template v-else>
              <KnowledgeGraph :knowledge-id="store.selectedId" />
            </template>
          </template>
          <el-empty v-else description="请选择一条知识" />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog
      v-model="showCreate"
      :title="createDialogTitle"
      width="560px"
      destroy-on-close
      @open="onCreateDialogOpen"
    >
      <el-form :model="createForm" label-width="88px">
        <el-form-item label="来源">
          <el-select v-model="createForm.source_type" style="width: 100%">
            <el-option label="剪贴板 / 文本" value="clipboard" />
            <el-option label="网页" value="url" />
            <el-option label="文件" value="file" />
            <el-option label="语音" value="voice" />
          </el-select>
        </el-form-item>

        <template v-if="createForm.source_type === 'url'">
          <el-form-item label="网页 URL" required>
            <el-input
              v-model="createForm.url"
              placeholder="https://example.com/article"
              clearable
            />
          </el-form-item>
          <p class="form-hint">
            将自动抓取网页正文、标题与描述并保存到知识库（与上传文件相同流程）。
          </p>
        </template>

        <template v-else-if="createForm.source_type === 'file'">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="请使用页面上方的拖拽上传区域导入文件。"
          />
        </template>

        <template v-else>
          <el-form-item label="标题" required>
            <el-input v-model="createForm.title" placeholder="知识条目标题" />
          </el-form-item>
          <el-form-item label="内容" required>
            <el-input
              v-model="createForm.content"
              type="textarea"
              :rows="8"
              placeholder="粘贴笔记或正文"
            />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button
          v-if="createForm.source_type !== 'file'"
          type="primary"
          :loading="creating"
          @click="onCreate"
        >
          {{ createForm.source_type === 'url' ? '抓取并保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useKnowledgeStore } from '@/stores/knowledge'
import { knowledgeApi } from '@/api/knowledge'
import { ingestionApi } from '@/api/ingestion'
import type { SourceType } from '@/api/types'
import MarkdownBody from '@/components/MarkdownBody.vue'
import { formatKnowledgeContent } from '@/utils/contentMarkdown'
import FileUpload from '@/components/FileUpload.vue'
import KnowledgeGraph from '@/components/KnowledgeGraph.vue'

const store = useKnowledgeStore()
const keyword = ref('')
const viewMode = ref<'preview' | 'edit' | 'graph'>('preview')
const saving = ref(false)
const creating = ref(false)
const showCreate = ref(false)

const editForm = ref({ title: '', content: '', tags: [] as string[] })
const createForm = ref({
  title: '',
  content: '',
  url: '',
  source_type: 'clipboard' as SourceType,
})

const createDialogTitle = computed(() =>
  createForm.value.source_type === 'url' ? '从网页导入' : '新建知识',
)

const previewContent = computed(() =>
  store.selected ? formatKnowledgeContent(store.selected.content) : '',
)

const editPreviewContent = computed(() => formatKnowledgeContent(editForm.value.content))

function resetCreateForm() {
  createForm.value = {
    title: '',
    content: '',
    url: '',
    source_type: 'clipboard',
  }
}

function onCreateDialogOpen() {
  resetCreateForm()
}

function formatDate(d: string) {
  return dayjs(d).format('YYYY-MM-DD HH:mm')
}

function resetEdit() {
  const k = store.selected
  if (!k) return
  editForm.value = {
    title: k.title,
    content: formatKnowledgeContent(k.content),
    tags: [...(k.tags ?? [])],
  }
}

function onFormatMarkdown() {
  editForm.value.content = formatKnowledgeContent(editForm.value.content)
  ElMessage.success('已整理为 Markdown，保存后写入知识库')
}

watch(
  () => store.selected,
  (k) => {
    if (k) resetEdit()
  },
  { immediate: true },
)

async function onSearch() {
  await store.search(keyword.value)
}

async function onRefresh() {
  keyword.value = ''
  await store.fetchRecent()
}

async function onSave() {
  if (!store.selectedId) return
  saving.value = true
  try {
    await store.update(store.selectedId, {
      ...editForm.value,
      content: formatKnowledgeContent(editForm.value.content),
    })
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  if (!store.selectedId) return
  await ElMessageBox.confirm('确定删除该知识条目？', '提示', { type: 'warning' })
  await store.remove(store.selectedId)
}

async function onCreate() {
  if (createForm.value.source_type === 'url') {
    const url = createForm.value.url.trim()
    if (!url) {
      ElMessage.warning('请输入网页 URL（需以 http:// 或 https:// 开头）')
      return
    }
    if (!/^https?:\/\//i.test(url)) {
      ElMessage.warning('URL 需以 http:// 或 https:// 开头')
      return
    }
    creating.value = true
    try {
      const res = await ingestionApi.ingestUrl(url, {
        auto_tag: true,
        fetch_metadata: true,
      })
      const data = res.data
      if (!data?.success) {
        ElMessage.error(data?.error || res.message || '网页解析失败')
        return
      }
      if (!data.knowledge_id) {
        ElMessage.error('未返回知识条目 ID')
        return
      }
      const detail = await knowledgeApi.getById(data.knowledge_id)
      if (detail.data) {
        const idx = store.items.findIndex((k) => k.id === detail.data!.id)
        if (idx >= 0) {
          store.items[idx] = detail.data
          store.select(detail.data.id)
        } else {
          store.prepend(detail.data)
        }
        showCreate.value = false
        resetCreateForm()
        const msg = data.is_updated
          ? `已更新：${detail.data.title}`
          : data.is_duplicate
            ? '内容未变化，已打开原条目'
            : `已保存：${detail.data.title}`
        ElMessage.success(msg)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '网页抓取失败'
      ElMessage.error(msg)
    } finally {
      creating.value = false
    }
    return
  }

  if (!createForm.value.title.trim() || !createForm.value.content.trim()) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  creating.value = true
  try {
    const res = await knowledgeApi.create({
      title: createForm.value.title.trim(),
      content: createForm.value.content,
      source_type: createForm.value.source_type,
    })
    if (res.data) {
      store.prepend(res.data)
      showCreate.value = false
      resetCreateForm()
      ElMessage.success('创建成功')
    }
  } finally {
    creating.value = false
  }
}

async function onUploadSuccess() {
  await store.fetchRecent()
}

onMounted(() => {
  store.fetchRecent()
})
</script>

<style scoped>
.knowledge-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  align-items: center;
}

.header-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.upload-section {
  margin-bottom: 0;
}

.list-card,
.detail-card {
  min-height: calc(100vh - 280px);
}

.list-item {
  padding: 12px;
  border-radius: 6px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.list-item:hover,
.list-item.active {
  background: #e6f4ff;
}

.item-title {
  font-weight: 500;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #999;
}

.item-tags {
  margin-top: 6px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.detail-title {
  font-size: 20px;
  margin-bottom: 8px;
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #666;
  font-size: 13px;
}

.detail-tags {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-content {
  max-height: calc(100vh - 360px);
  overflow-y: auto;
  padding-right: 4px;
}

.edit-md-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  width: 100%;
}

.edit-md-pane {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
  min-height: 360px;
  display: flex;
  flex-direction: column;
}

.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: #666;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}

.md-source-input :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
  border: none;
  box-shadow: none;
  resize: vertical;
}

.edit-preview-scroll {
  flex: 1;
  max-height: 420px;
}

.edit-preview-body {
  padding: 12px 14px;
}

.form-hint {
  margin: -8px 0 12px 88px;
  font-size: 12px;
  color: #888;
  line-height: 1.5;
}
</style>
