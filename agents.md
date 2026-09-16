# agents.md — MangaShelf 项目协作约定

## 环境与依赖（必须遵守）

- **venv 必须建立在项目根目录**（`H:\VsCode\manga_bookshelf\venv`），不要使用全局 Python，也不要把包装到系统环境。
- **pip 一律使用国内镜像源**，默认阿里云；**npm 使用 npmmirror**：
  ```bash
  venv/Scripts/python.exe -m pip install <pkg> -i https://mirrors.aliyun.com/pypi/simple/
  cd frontend && npm install --registry=https://registry.npmmirror.com
  ```
- 依赖以 `requirements.txt`（运行）/ `requirements-dev.txt`（开发+打包）为准，版本已锁定，不要擅自升级。
- 运行测试：
  ```bash
  venv/Scripts/python.exe -m pytest
  ```
- 不要直接修改代码，务必先出计划。
- 修改代码前先请用户同意。

## 架构（2026-09 UI 重构后）

新 UI 技术栈：**FastAPI + pywebview + Vue3 + Naive UI**（pywebview 原生窗口 + 本地 HTTP 服务，不是浏览器应用）。

```
Python 核心（保持零 Qt/零 Web 依赖，禁止改动其对外语义）
  database.py → services/library_service.py → library_manager.py
  ↓ 每请求一个 LibraryService 实例（sqlite 连接绑定线程）
backend/
  api.py      FastAPI 路由层：/api/objects、/api/import/*、/api/migrate、
              /api/objects/{id}/thumb|image|cover（按 id 反查路径，不收任意路径）
  server.py   入口：uvicorn 后台线程 + pywebview 窗口
              --serve 仅本地服务（浏览器调试）；--port 固定端口（配合 vite proxy）
frontend/     Vue3 + Vite + Naive UI（构建产物 dist/ 由 FastAPI 静态托管）
  src/store.js    全局状态（view: shelf|directory|reader、filters、theme）
  src/theme.js    深浅双主题设计令牌
  src/components/ Bookshelf(等尺寸网格+两阶段过渡动画)、Reader(右起进度条)、
                  TagSidebar、ImportDialog、EditDialog、LibraryDialog、SetupGate
```

## 常用命令

```bash
# 桌面窗口（生产形态）
venv/Scripts/python.exe backend/server.py

# 浏览器调试（后端 :8765，前端改动需 npm run build 后刷新）
venv/Scripts/python.exe backend/server.py --serve --port 8765

# 前端开发热重载（vite :5173，/api 代理到 8765）
cd frontend && npm run dev

# API 端到端验证（需先启动 --serve）
venv/Scripts/python.exe scripts/verify_api.py
```

- 临时/测试库路径用环境变量 `MANGASHELF_DB` 覆盖，**不要拿用户真实库做实验**。

## 项目背景速览

- 本地漫画/图片管理器；核心业务层（database/library_manager/services）+ 33 个无 GUI pytest 测试是地基，改动前必须先读对应测试理解语义。
- 线程约定：任何地方用 `LibraryService` 都要"每线程/每请求一个实例"。
- UI 交互基准：等尺寸对齐卡片网格（封面 5:7）、筛选切换时卡片整批"右出左入"过渡、R-18 模糊遮罩 + 侧栏开关、深浅双主题即时切换。

## 其他约定

- 中文注释与中文 UI 文案，保持现有风格。
- 涉及文件删除/迁移的改动要谨慎：现有代码已有多重防御（目录占用检查、导入回滚、迁移回滚）。
