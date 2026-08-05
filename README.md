# MangaShelf — 本地漫画管理器

基于 PyQt6 + SQLite + Pillow 的本地漫画/图片管理工具。

## 功能

- 📚 **书架视图**：封面网格展示，支持 R-18 开关（默认隐藏）
- 🔍 **搜索与筛选**：按对象名/标签关键字搜索；按标签类别多选筛选
- 📥 **导入**：新建目录对象（整个文件夹）；或导入到已有对象
- 🏷️ **标签系统**：作品、作者、角色、CM/活动、R-18、修正
- 🗃️ **库管理**：迁移图库根目录（自动更新对象目录与图片路径）
- 🖼️ **目录视图**：图片缩略图网格，类 Windows 文件浏览器
- 📖 **阅读器**：
  - 点击左 1/3 → 下一页，点击右 1/3 → 上一页
  - 键盘方向键翻页，Esc 返回
  - 自定义进度条（从右向左，圆形滑块），自动保存阅读进度
- ✏️ **右键编辑**：编辑对象信息、更换封面、删除对象

## 安装与运行

### 依赖

```bash
pip install -r requirements.txt
```

开发/打包另需：

```bash
pip install -r requirements-dev.txt
```

### 运行

```bash
python main.py
```

首次启动会要求选择一个目录作为图库根目录，所有导入的图片将复制到该目录下管理。

## 项目结构

```
manga_shelf/
├── main.py               # 程序入口 + 首次运行设置 + 日志/异常兜底
├── database.py           # SQLite 数据库层
├── library_manager.py    # 库配置与迁移（check_writable、migrate_library）
├── config.py             # 应用常量配置（不含可变状态）
├── requirements.txt
├── requirements-dev.txt  # 开发/打包依赖（PyInstaller）
├── MangaShelf.spec       # PyInstaller 打包配置
├── services/
│   └── library_service.py # 业务门面层（UI 只依赖本服务）
├── ui/
│   ├── widgets.py        # 通用控件 + 主题样式
│   ├── sidebar.py        # 侧边栏（标签筛选 + R18 开关）
│   ├── main_window.py    # 主窗口（视图调度）
│   ├── bookshelf.py      # 书架视图（封面卡片网格）
│   ├── directory_view.py # 目录视图（图片缩略图网格）
│   ├── image_viewer.py   # 图片阅读器
│   ├── import_dialog.py  # 导入对话框
│   ├── library_dialog.py # 库管理（迁移）对话框
│   └── tag_editor.py     # 标签编辑对话框
├── utils/
│   ├── thumbnail.py      # 缩略图生成（Pillow，带缓存）
│   └── file_utils.py     # 文件操作（复制、校验）
└── tests/
    ├── conftest.py                # pytest fixtures（临时库/根目录/图片生成）
    └── test_library_service.py    # LibraryService 测试
```

## 支持格式

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.gif` `.tiff` `.tif`

## 数据库位置

- Windows：`%APPDATA%\MangaShelf\library.db`
- Linux/Mac：`~/.local/share/MangaShelf/library.db`

运行日志写入数据库同目录下的 `manga_shelf.log`。

## 测试

```bash
pip install -r requirements-dev.txt
pytest
```

## 打包为 exe（可选）

```bash
pip install -r requirements-dev.txt
pyinstaller MangaShelf.spec
```

产物输出到 `dist/MangaShelf.exe`。
