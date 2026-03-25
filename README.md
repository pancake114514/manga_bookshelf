# MangaShelf — 二次元图片管理器

基于 PyQt6 + SQLite + Pillow 的本地漫画/图片管理工具。

## 功能

- 📚 **书架视图**：封面网格展示，支持 R-18 开关（默认隐藏）
- 🔍 **搜索与筛选**：按对象名/标签关键字搜索；按标签类别多选筛选
- 📥 **导入**：新建目录对象（整个文件夹）；或导入到已有对象
- 🏷️ **标签系统**：作品、作者、角色、CM/活动、R-18、修正
- 🖼️ **目录视图**：图片缩略图网格，类 Windows 文件浏览器
- 📖 **阅读器**：
  - 点击左 1/3 → 下一页，点击右 1/3 → 上一页
  - 键盘方向键翻页，Esc 返回
  - 自定义进度条（从右向左，圆形滑块），自动保存阅读进度
- ✏️ **右键编辑**：编辑对象信息、更换封面、删除对象

## 安装与运行

### 依赖

```bash
pip install PyQt6 Pillow
```

### 运行

```bash
cd manga_library
python main.py
```

首次启动会要求选择一个目录作为图库根目录，所有导入的图片将复制到该目录下管理。

## 项目结构

```
manga_library/
├── main.py               # 程序入口 + 首次运行设置
├── database.py           # SQLite 数据库层
├── config.py             # 全局配置与应用状态
├── requirements.txt
├── ui/
│   ├── widgets.py        # 通用控件 + 主题样式
│   ├── sidebar.py        # 侧边栏（标签筛选 + R18 开关）
│   ├── main_window.py    # 主窗口（视图调度）
│   ├── bookshelf.py      # 书架视图（封面卡片网格）
│   ├── directory_view.py # 目录视图（图片缩略图网格）
│   ├── image_viewer.py   # 图片阅读器
│   ├── import_dialog.py  # 导入对话框
│   └── tag_editor.py     # 标签编辑对话框
└── utils/
    ├── thumbnail.py      # 缩略图生成（Pillow，带缓存）
    └── file_utils.py     # 文件操作（复制、校验）
```

## 支持格式

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.gif` `.tiff` `.tif`

## 数据库位置

- Windows：`%APPDATA%\MangaShelf\library.db`
- Linux/Mac：`~/.local/share/MangaShelf/library.db`

## 打包为 exe（可选）

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name MangaShelf main.py
```
