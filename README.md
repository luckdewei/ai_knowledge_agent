# knowledge_agent

## 服务端

### 安装依赖

```bash
cd backend
# 下载开发依赖
uv sync
# 下载开发依赖
uv sync --extra dev --extra test
```

### docker

1. 启动本地 docker 服务
2. 在项目根目录 运行 `docker-compose up -d` 安装启动 `postresql` , `redis`

### 运行服务端

```bash
cd backend
# 启动服务
fastapi dev
```

## 客户端

```bash
cd frontend
# 安装依赖
pnpm i
# 启动服务
pnpm dev
```
