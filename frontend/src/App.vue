<template>
  <div id="app">
    <el-container>
      <el-aside width="240px" class="aside">
        <div class="logo">
          <el-icon>
            <DataAnalysis />
          </el-icon>
          <span>知识助手</span>
        </div>
        <el-menu :default-active="activeMenu" router class="menu" background-color="#001529"
          text-color="rgba(255, 255, 255, 0.65)" active-text-color="#ffffff">
          <el-menu-item index="/">
            <el-icon>
              <Odometer />
            </el-icon>
            <span>仪表盘</span>
          </el-menu-item>
          <el-menu-item index="/knowledge">
            <el-icon>
              <Document />
            </el-icon>
            <span>知识库</span>
          </el-menu-item>
          <el-menu-item index="/agent">
            <el-icon>
              <ChatDotRound />
            </el-icon>
            <span>Agent 对话</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-container>
        <el-header class="header">
          <h3>智能个人知识库助手</h3>
        </el-header>

        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
#app {
  height: 100vh;
}

.aside {
  background-color: #001529;
  height: 100vh;
  color: white;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 18px;
  font-weight: bold;
  border-bottom: 1px solid #2c3e4e;
}

.menu {
  border-right: none;
}

.menu :deep(.el-menu-item:hover) {
  background-color: rgba(255, 255, 255, 0.08);
}

.menu :deep(.el-menu-item.is-active) {
  background-color: #1890ff;
}

.header {
  background-color: white;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  z-index: 10;
}
</style>