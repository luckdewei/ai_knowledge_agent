<template>
    <div>
        <h1>Dashboard</h1>
    </div>
</template>

<script setup lang="ts">
import { healthApi, type HealthStatus } from '@/api/health'
import { onMounted, ref } from 'vue'

const health = ref<HealthStatus | null>(null)

onMounted(async () => {
    const response = await healthApi.check()
    health.value = response.data
})
</script>

<style scoped></style>