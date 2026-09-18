# agents.md — MangaShelf 项目协作约定（Tauri 2 版）

## 环境与依赖（必须遵守）

- 技术栈：**Tauri 2 + Rust + Vue3 + Naive UI**。需要 Rust 工具链（stable）与 Node.js。
- **npm 一律使用 npmmirror**：`cd frontend && npm install --registry=https://registry.npmmirror.com`。
- cargo 首次构建较慢（bundled SQLite 需编译）属正常；不要擅自升级 `Cargo.toml` / `package.json` 里已锁定的依赖大版本。
- 运行 Rust 检查：`cargo build` / `cargo clippy`（在 `src-tauri/` 下执行）。

## 架构（2026-09 Tauri 重构后）

原 Python (FastAPI + pywebview) 版本已整体重写为 Rust，schema 与 Python 版完全兼容；
历史版本可在 `master` / `origin/feature/web-ui` 分支回溯。

```
src-tauri/src/             Rust 核心
  db.rs        SQLite 数据层（DDL/CRUD/批量组装；连接 Mutex 保护，绑定线程）
  service.rs   业务门面层（查询/搜索/筛选/导入/删除，含回滚机制）
  commands.rs  Tauri commands 层（IPC 入口，替代原 FastAPI 路由）
  library_manager.rs  库迁移（计划-执行-回滚三阶段）
  file_ops.rs  文件操作（序号重命名/路径校验）
  thumbnail.rs 缩略图生成（image crate Lanczos3，mtime 缓存）
  config.rs    配置常量
frontend/                 Vue3 + Vite + Naive UI
  src/api.js        Tauri IPC 封装（invoke）+ 窗口控制（win：minimize/maximize/startDrag…）
  src/store.js      全局状态（view: shelf|directory|reader、filters、theme）
  src/theme.js      深浅双主题设计令牌
  src/windowState.js 顶栏拖动（startDragging）与最大化状态共享
  src/components/   Bookshelf(等尺寸网格)、Reader(右起进度条)、TagSidebar、
                    EdgeResize(边缘缩放热区)、TopBar/TitleBar/WindowControls(无边框顶栏)、
                    ImportDialog、EditDialog、LibraryDialog、SetupGate
```

## 窗口管理专项说明（重要，易踩坑）

- 窗口 `decorations: false` 无边框，顶栏由前端 `TopBar`/`TitleBar` 自绘。
- 顶栏拖动/双击最大化/贴靠（Snap Layouts）走 Tauri `startDragging()`——系统原生行为自动生效。
- **边缘缩放必须保留 `EdgeResize.vue` 前端热区**：WebView 子窗口跨进程覆盖客户区，
  Win32 层的边缘命中测试拿不到鼠标事件（pywebview 时代已验证的架构限制，
  Tauri 下同样存在），删除该组件会导致窗口无法拖边缘缩放。

## 常用命令

```bash
# 开发（桌面窗口 + 前后端热重载）
cargo tauri dev

# 打包生产安装包
cargo tauri build

# 纯前端构建（产物由 tauri.conf.json 的 frontendDist 托管）
cd frontend && npm run build

# Rust 检查
cd src-tauri && cargo build && cargo clippy
```

- 实验/测试**不要拿用户真实图库做**；需要临时库时改用临时目录初始化（数据库路径
  见 `src-tauri/src/config.rs`，原 Python 版 `MANGASHELF_DB` 环境变量已不存在）。

## 项目背景速览

- 本地漫画/图片管理器；核心业务语义以 `service.rs` 为准（导入回滚、删除联动、
  迁移三阶段），改动前先读对应模块理解语义。
- SQLite 连接由 Mutex 保护；命令层（commands.rs）不直接摸 db.rs，统一经 service.rs。
- UI 交互基准：等尺寸对齐卡片网格（封面 5:7）、筛选切换时卡片整批"右出左入"过渡、
  R-18 模糊遮罩 + 侧栏开关、深浅双主题即时切换、卡片/进度条尺寸不随窗口宽度伸缩。

## 其他约定

- 中文注释与中文 UI 文案，保持现有风格。
- 涉及文件删除/迁移的改动要谨慎：现有代码已有多重防御（目录占用检查、导入回滚、迁移回滚）。
- 不要直接修改代码，务必先出计划，修改代码前先请用户同意。
