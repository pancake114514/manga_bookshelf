# MangaShelf — 本地漫画管理器

基于 FastAPI + pywebview + Vue3/Naive UI 的本地漫画/图片管理工具(Python 核心 + SQLite + Pillow)。

## 功能

- 📚 **书架视图**:封面等尺寸网格展示,支持 R-18 开关(默认隐藏)、深浅双主题即时切换
- 🔍 **搜索与筛选**:按对象名/标签关键字搜索;按标签类别多选筛选
- 📥 **导入**:新建目录对象(整个文件夹);或追加导入到已有对象
- 🏷️ **标签系统**:作品、作者、角色、CM/活动、修正、R-18
- 🗃️ **库管理**:迁移图库根目录(自动更新对象目录与图片路径;同名目录自动重命名,库外路径迁移后提示)
- 🖼️ **目录视图**:图片缩略图网格
- 📖 **阅读器**:
  - 点击左 1/3 → 下一页,点击右 1/3 → 上一页
  - 键盘方向键翻页,Esc 返回
  - 自定义进度条(从右向左,圆形滑块),自动保存阅读进度

## 安装与运行

### 依赖

```bash
venv/Scripts/python.exe -m pip install -r requirements.txt
# Web 栈(本地 HTTP 服务 + 桌面窗口)
venv/Scripts/python.exe -m pip install fastapi uvicorn pywebview
```

前端构建产物 `frontend/dist/` 已由仓库托管时无需 Node;改动前端则需:

```bash
cd frontend && npm install --registry=https://registry.npmmirror.com && npm run build
```

### 运行

```bash
# 桌面窗口(生产形态)
venv/Scripts/python.exe backend/server.py

# 浏览器调试(后端 :8765)
venv/Scripts/python.exe backend/server.py --serve --port 8765
```

首次启动会要求选择一个目录作为图库根目录,所有导入的图片将复制到该目录下管理。

## 项目结构

```
manga_bookshelf/
├── database.py           # SQLite 数据库层
├── library_manager.py    # 库配置与迁移（check_writable、migrate_library）
├── config.py             # 应用常量配置（不含可变状态）
├── requirements.txt
├── requirements-dev.txt  # 开发依赖（pytest 等）
├── services/
│   └── library_service.py # 业务门面层（每线程/每请求一个实例）
├── backend/
│   ├── api.py            # FastAPI 路由层（/api/*，静态托管 frontend/dist）
│   └── server.py         # 入口：uvicorn 后台线程 + pywebview 窗口
├── frontend/             # Vue3 + Vite + Naive UI
│   └── src/
│       ├── store.js      # 全局状态
│       ├── theme.js      # 深浅双主题设计令牌
│       ├── api.js        # 后端 API 封装 + pywebview 桥
│       └── components/   # Bookshelf / Reader / TagSidebar / 各对话框等
├── utils/
│   ├── thumbnail.py      # 缩略图生成（Pillow，带缓存）
│   └── file_utils.py     # 文件操作（复制、校验）
├── scripts/
│   ├── verify_api.py     # API 端到端验证
│   └── theme_check.cjs   # 深浅主题切换回归（playwright-core）
└── tests/
    ├── conftest.py                # pytest fixtures（临时库/根目录/图片生成）
    ├── test_library_service.py    # LibraryService 测试
    ├── test_library_manager.py    # 库迁移（同名重命名/路径更新/警告）测试
    └── test_file_utils.py         # 文件工具（路径校验/序号复制）测试
```

## 支持格式

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.gif` `.tiff` `.tif`

## 数据库位置

- Windows:`%APPDATA%\MangaShelf\library.db`
- Linux/Mac:`~/.local/share/MangaShelf/library.db`

可用环境变量 `MANGASHELF_DB` 覆盖数据库路径(测试/临时库场景)。

## 测试

```bash
venv/Scripts/python.exe -m pip install -r requirements-dev.txt
venv/Scripts/python.exe -m pytest
```
