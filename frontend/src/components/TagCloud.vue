<template>
  <div class="tag-cloud">
    <span
      v-for="item in sizedTags"
      :key="item.tag"
      class="tag-item"
      :style="{ fontSize: `${item.fontSize}px` }"
      @click="emit('select', item.tag)"
    >
      {{ item.tag }}
      <small v-if="showCount">({{ item.count }})</small>
    </span>
    <el-empty v-if="!sizedTags.length" description="暂无标签数据" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    tags: { tag: string; count: number }[]
    minSize?: number
    maxSize?: number
    showCount?: boolean
  }>(),
  { minSize: 12, maxSize: 28, showCount: false },
)

const emit = defineEmits<{ select: [tag: string] }>()

const sizedTags = computed(() => {
  if (!props.tags.length) return []
  const counts = props.tags.map((t) => t.count)
  const min = Math.min(...counts)
  const max = Math.max(...counts)
  const range = max - min || 1

  return props.tags.map((t) => ({
    ...t,
    fontSize:
      props.minSize +
      ((t.count - min) / range) * (props.maxSize - props.minSize),
  }))
})
</script>

<style scoped>
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  padding: 16px;
}

.tag-item {
  color: #1890ff;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.2s, transform 0.2s;
  line-height: 1.4;
}

.tag-item:hover {
  background: #e6f4ff;
  transform: scale(1.05);
}

.tag-item small {
  font-size: 0.75em;
  color: #999;
}
</style>
