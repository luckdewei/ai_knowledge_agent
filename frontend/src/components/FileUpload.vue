<template>
  <div
    class="file-upload"
    :class="{ 'is-dragover': isDragover, 'is-disabled': disabled }"
    @dragover.prevent="onDragover"
    @dragleave.prevent="onDragleave"
    @drop.prevent="onDrop"
    @click="triggerSelect"
  >
    <input
      ref="inputRef"
      type="file"
      class="hidden-input"
      :accept="accept"
      :multiple="multiple"
      @change="onFileChange"
    />
    <el-icon class="upload-icon" :size="40">
      <UploadFilled />
    </el-icon>
    <p class="upload-title">{{ title }}</p>
    <p class="upload-hint">{{ hint }}</p>
    <div v-if="uploading" class="upload-progress">
      <el-progress :percentage="progress" :stroke-width="6" />
    </div>
    <div v-if="fileList.length && showList" class="file-list">
      <div v-for="f in fileList" :key="f.uid" class="file-item">
        <el-icon><Document /></el-icon>
        <span class="file-name">{{ f.name }}</span>
        <el-tag v-if="f.status === 'success'" type="success" size="small">完成</el-tag>
        <el-tag v-else-if="f.status === 'error'" type="danger" size="small">失败</el-tag>
        <el-tag v-else type="info" size="small">上传中</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ingestionApi } from '@/api/ingestion'

interface UploadFileItem {
  uid: string
  name: string
  status: 'uploading' | 'success' | 'error'
}

const props = withDefaults(
  defineProps<{
    accept?: string
    multiple?: boolean
    disabled?: boolean
    autoTag?: boolean
    autoSummarize?: boolean
    title?: string
    hint?: string
    showList?: boolean
  }>(),
  {
    accept: '*/*',
    multiple: true,
    disabled: false,
    autoTag: true,
    autoSummarize: false,
    title: '拖拽文件到此处，或点击上传',
    hint: '支持 PDF、Markdown、文本、音频等',
    showList: true,
  },
)

const emit = defineEmits<{
  success: [payload: { knowledgeId?: string; fileName: string }]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const isDragover = ref(false)
const uploading = ref(false)
const progress = ref(0)
const fileList = ref<UploadFileItem[]>([])

function triggerSelect() {
  if (props.disabled || uploading.value) return
  inputRef.value?.click()
}

function onDragover() {
  if (!props.disabled) isDragover.value = true
}

function onDragleave() {
  isDragover.value = false
}

function onDrop(e: DragEvent) {
  isDragover.value = false
  const files = e.dataTransfer?.files
  if (files?.length) handleFiles(Array.from(files))
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) handleFiles(Array.from(input.files))
  input.value = ''
}

async function handleFiles(files: File[]) {
  const list = props.multiple ? files : files.slice(0, 1)
  uploading.value = true
  progress.value = 0

  for (let i = 0; i < list.length; i++) {
    const file = list[i]
    const item: UploadFileItem = {
      uid: `${Date.now()}-${i}`,
      name: file.name,
      status: 'uploading',
    }
    fileList.value.unshift(item)
    progress.value = Math.round(((i + 0.5) / list.length) * 100)

    try {
      const res = await ingestionApi.uploadFile(file, {
        auto_tag: props.autoTag,
        auto_summarize: props.autoSummarize,
      })
      item.status = 'success'
      emit('success', {
        knowledgeId: res.data?.knowledge_id,
        fileName: file.name,
      })
      ElMessage.success(`「${file.name}」已导入知识库`)
    } catch {
      item.status = 'error'
    }
    progress.value = Math.round(((i + 1) / list.length) * 100)
  }

  uploading.value = false
}
</script>

<style scoped>
.file-upload {
  border: 2px dashed #d9d9d9;
  border-radius: 8px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  background: #fafafa;
}

.file-upload:hover:not(.is-disabled) {
  border-color: #1890ff;
  background: #f0f7ff;
}

.file-upload.is-dragover {
  border-color: #1890ff;
  background: #e6f4ff;
}

.file-upload.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hidden-input {
  display: none;
}

.upload-icon {
  color: #1890ff;
  margin-bottom: 8px;
}

.upload-title {
  font-size: 15px;
  color: #333;
  margin-bottom: 4px;
}

.upload-hint {
  font-size: 13px;
  color: #999;
}

.upload-progress {
  margin-top: 16px;
  max-width: 320px;
  margin-left: auto;
  margin-right: auto;
}

.file-list {
  margin-top: 16px;
  text-align: left;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fff;
  border-radius: 6px;
  margin-top: 8px;
  font-size: 13px;
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
