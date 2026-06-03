<template>
  <div class="markdown-body" :class="variant" v-html="html" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

const props = withDefaults(
  defineProps<{
    content: string
    /** assistant 气泡内浅色背景；on-dark 用于用户蓝色气泡 */
    variant?: 'default' | 'on-dark'
  }>(),
  { variant: 'default' },
)

const html = computed(() => renderMarkdown(props.content))
</script>
