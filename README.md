# MangaShelf — 本地漫画管理器 (Tauri 2 重构版)

基于 **Tauri 2 + Rust + Vue3 + Naive UI** 的本地漫画/图片管理工具。
原 Python (FastAPI + pywebview) 版本的核心逻辑完全用 Rust 重写，窗口壳从 pywebview 迁移到 Tauri 2。

## 与原版的主要变化

| 维度 | 原版 (Python) | 新版 (Rust + Tauri) |
|---|---|---|
| 窗口壳 | pywebview + 585 行 Win32 ctypes | Tauri 2 内置窗口管理 |
| 后端 | FastAPI + uvicorn (HTTP) | Rust + Tauri IPC |
| 数据库 | sqlite3 (Python 标准库) | rusqlite (bundled SQLite) |
| 缩略图 | Pillow | image crate (Lanczos3) |
| 窗口操作 | 手动拖动/缩放/贴靠 | Tauri startDragging + 原生 Snap |
| 窗口 Snap Layouts | 不支持 | 支持（decorations:false + startDragging） |
| 安装包体积 | ~30-40MB (带 Python 运行时) | ~10-15MB (纯 Rust 原生二进制) |

## 功能（与原版一致）

- 书架视图：封面等尺寸网格展示，支持 R-18 开关、深浅双主题
- 搜索与筛选：按对象名/标签关键字搜索；按标签类别多选筛选
- 导入：新建目录对象或追加导入到已有对象
- 标签系统：作品、作者、角色、CM/活动、修正、R-18
- 库管理：迁移图库根目录（自动更新路径、同名重命名、库外路径警告）
- 目录视图：图片缩略图网格
- 阅读器：键盘翻页、自定义进度条、自动保存阅读进度

## 项目结构

```
manga_shelf/
├── src-tauri/                  # Rust 后端 + Tauri 配置
│   ├── Cargo.toml
│   ├── tauri.conf.json         # Tauri 窗口/打包配置
│   ├── build.rs
│   ├── capabilities/
│   │   └── default.json        # Tauri 权限配置
│   └── src/
│       ├── main.rs             # 入口
│       ├── lib.rs              # Tauri 应用初始化 + URI scheme
│       ├── config.rs           # 常量配置
│       ├── db.rs               # SQLite 数据层 (rusqlite)
│       ├── service.rs          # 业务门面层
│       ├── library_manager.rs  # 库迁移
│       ├── commands.rs         # Tauri commands (替代 FastAPI 路由)
│       ├── file_ops.rs         # 文件操作工具
│       └── thumbnail.rs        # 缩略图生成 (image crate)
├── frontend/                   # Vue3 + Vite + Naive UI
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue
│       ├── api.js              # Tauri IPC 封装
│       ├── store.js            # 全局状态
│       ├── theme.js            # 深浅双主题
│       ├── windowState.js      # 窗口状态管理
│       └── components/         # 14 个业务组件
├── config.py                   # 旧 Python 版（保留参考）
├── database.py                 # 旧 Python 版（保留参考）
└── requirements.txt            # 旧 Python 版（保留参考）
```

## 数据库兼容性

数据库 schema 与 Python 版完全一致，同一份 `library.db` 可直接迁移使用：
- Windows: `%APPDATA%\MangaShelf\library.db`
- Linux/Mac: `~/.local/share/MangaShelf/library.db`
- 环境变量 `MANGASHELF_DB` 可覆盖路径

## 开发

### 前置要求

- [Rust](https://rustup.rs/) (stable, ≥1.77)
- [Node.js](https://nodejs.org/) (≥18)
- Tauri 2 CLI: `cargo install tauri-cli --version "^2"`

### 安装依赖

```bash
# 前端依赖
cd frontend && npm install --registry=https://registry.npmmirror.com

# Rust 依赖（首次编译会自动拉取）
cd src-tauri && cargo build
```

### 开发模式

```bash
# Tauri dev（自动启动 vite dev server + Rust 后端）
cd src-tauri && cargo tauri dev

# 或使用全局 tauri CLI
tauri dev
```

### 生产构建

```bash
cd src-tauri && cargo tauri build
# 产物：src-tauri/target/release/mangashelf.exe
# 安装包：src-tauri/target/release/bundle/
```

## 支持格式

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.gif` `.tiff` `.tif`

## 窗口操作

Tauri 2 无边框窗口 (`decorations: false`) + `startDragging`:
- 顶栏拖动移动窗口（原生手感）
- 顶栏双击切换最大化
- Win+方向键原生贴靠
- 边缘拖拽缩放（EdgeResize 组件）
- 阅读器全屏（Tauri setFullscreen）

## License

MIT
