<template>
  <div class="login-page">
    <el-card class="login-card" shadow="hover">
      <template #header>
        <div class="card-title">
          <h2>智能个人知识库</h2>
          <p>账号登录 · 个人数据空间</p>
        </div>
      </template>

      <el-tabs v-model="tab">
        <el-tab-pane label="登录" name="login">
          <el-form :model="loginForm" label-width="72px" @submit.prevent="onLogin">
            <el-form-item label="账号">
              <el-input
                v-model="loginForm.username"
                autocomplete="username"
                placeholder="注册时的账号名"
              />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="loginForm.password"
                type="password"
                show-password
                autocomplete="current-password"
              />
            </el-form-item>
            <el-button type="primary" class="submit-btn" :loading="loading" @click="onLogin">
              登录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form :model="regForm" label-width="72px" @submit.prevent="onRegister">
            <el-form-item label="账号">
              <el-input
                v-model="regForm.username"
                autocomplete="username"
                placeholder="至少 2 个字符，全局唯一"
              />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="regForm.password"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="至少 6 位"
              />
            </el-form-item>
            <el-button
              type="primary"
              class="submit-btn"
              :loading="loading"
              @click="onRegister"
            >
              注册并登录
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const tab = ref<'login' | 'register'>('login')
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
})

const regForm = reactive({
  username: '',
  password: '',
})

function validateAccount(username: string, password: string): string | null {
  const name = username.trim()
  if (!name || !password) {
    return '请填写账号和密码'
  }
  if (name.length < 2) {
    return '账号至少 2 个字符'
  }
  if (password.length < 6) {
    return '密码至少 6 位'
  }
  return null
}

async function onLogin() {
  const err = validateAccount(loginForm.username, loginForm.password)
  if (err) {
    ElMessage.warning(err)
    return
  }
  loading.value = true
  try {
    await authStore.login({
      username: loginForm.username.trim(),
      password: loginForm.password,
    })
    ElMessage.success('登录成功')
    router.replace('/')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  const err = validateAccount(regForm.username, regForm.password)
  if (err) {
    ElMessage.warning(err)
    return
  }
  loading.value = true
  try {
    await authStore.register({
      username: regForm.username.trim(),
      password: regForm.password,
    })
    ElMessage.success('注册成功')
    router.replace('/')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e6f4ff 0%, #f5f5f5 50%, #fff 100%);
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 400px;
}

.card-title h2 {
  margin: 0 0 4px;
  font-size: 20px;
}

.card-title p {
  margin: 0;
  font-size: 13px;
  color: #888;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
}
</style>
