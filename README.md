# MangaShelf — 本地漫画管理器

基于 **Tauri 2 + Rust + Vue3 + Naive UI** 的本地漫画/图片管理工具。
原 Python (FastAPI + pywebview) 版本的核心逻辑已完全用 Rust 重写，窗口壳迁移到 Tauri 2 无边框窗口。

## 功能

**书架管理**
- 封面等尺寸网格（5:7），紧凑/标准/大图三档密度，固定列宽不随窗口伸缩
- 搜索（对象名/标签值/系列名）+ 搜索建议（标注命中类别：作品/作者/系列…）
- 侧栏筛选：标签类别多选、评分（N 星及以上）、系列名，可组合
- 排序：添加时间/名称/页数/评分/阅读进度；渐进渲染，大库流畅
- 系列与分卷：对象归入系列并编号，同系列卷号查重，书架平铺/系列分组双视图（可折叠）
- 卡片阅读进度可视化：在读进度条 / 读完角标 / 未读无标记；悬浮一键续读（直达上次进度）
- 多选批量操作：批量打标签、批量删除（含本地文件可选）
- R-18 模糊遮罩 + 独立开关

**详情页**
- 元信息区：封面、评分、系列·卷号、可点击标签（点击即回书架筛选）
- 对象侧栏：同系列分卷导航（当前卷高亮、点击直达）、书签列表（点击进阅读器定位）、
  张数/阅读进度/打开存储目录
- 缩略图网格，书签页显示角标标记

**阅读器**
- 日漫右开本默认，阅读方向（右→左 / 左→右）可切换并持久化
- 双页对开（封面单显、自动对齐奇偶页）、适应页面/适应宽度/原始尺寸
- Ctrl+滚轮自由缩放（20%–800%，光标锚点）+ 按住拖拽平移
- 进度条拖动实时预览（节流加载）、书签系统（B 键/进度条刻度/备注）
- 翻页就绪切换（无闪白）、相邻页预加载、阅读进度自动保存
- 工具栏自动隐藏、真全屏（Win32 窗口层）

**导入与维护**
- 目录导入 / 追加文件夹 / 追加散图 / 批量多选文件夹一次建多个对象
- 命名规则解析：`[编号-](CM号)[作者名] 本名` 自动预填对象名与 cm/author 标签（兼容全角括号）
- `.thumb` 前缀文件识别为封面（按魔数嗅探），不混入正文页
- 导入/取消全路径回滚；库迁移三阶段（计划-执行-回滚，迁移前 WAL checkpoint 备份）
- 库校验：缺失图片/未登记文件/空对象/孤儿目录报告 + 幂等修复
- 缩略图缓存清理（失效条目 + 2GB 总量上限）；EXIF 方向应用（手机照片不再旋转错误）
- 单实例运行（二次启动唤起已有窗口）

## 项目结构

```
manga_bookshelf/
├── src-tauri/                  # Rust 后端 + Tauri 配置
│   ├── tauri.conf.json         # 窗口/打包配置（版本号）
│   ├── capabilities/           # Tauri 权限配置
│   └── src/
│       ├── lib.rs              # 应用初始化、图片协议（异步缩略图）、单实例、关闭拦截
│       ├── config.rs           # 常量配置
│       ├── db.rs               # SQLite 数据层（版本化 schema 迁移 v1→v3）
│       ├── service.rs          # 业务门面层（导入回滚/库校验/系列/书签）
│       ├── library_manager.rs  # 库迁移三阶段
│       ├── commands.rs         # Tauri commands（IPC 入口）
│       ├── file_ops.rs         # 文件操作（保留原文件名、重名递增、.thumb 识别）
│       └── thumbnail.rs        # 缩略图（并发限流 + 大比率快速路径）
├── frontend/                   # Vue3 + Vite + Naive UI
│   ├── naming.js               # 文件夹名解析（独立模块，带单测）
│   └── src/
│       ├── api.js              # Tauri IPC 封装
│       ├── store.js            # 全局状态（主题/筛选/视图/系列）
│       └── components/         # 书架/详情/阅读器/侧栏/各对话框等组件
├── dev.mjs                     # 开发模式随机端口启动器（20000-60000）
├── frontend/test/              # naming.js 单测（node 直接运行）
└── .github/workflows/          # CI（构建+测试）与 Release（tag 自动打包）
```

## 数据库

- 位置：Windows `%APPDATA%\MangaShelf\library.db`；Linux/Mac `~/.local/share/MangaShelf/library.db`
- 环境变量 `MANGASHELF_DB` 可覆盖路径
- schema 版本化（`PRAGMA user_version`），老库（含 Python 版）启动时自动增量升级，
  基线 DDL 与版本号同事务原子提交，升级中断不会损坏库

## 开发

前置要求：[Rust stable](https://rustup.rs/)、[Node.js](https://nodejs.org/) ≥ 18

```bash
# 前端依赖（npmmirror 镜像）
cd frontend && npm install --registry=https://registry.npmmirror.com

# 开发模式（随机端口启动器，规避 vite 端口残留冲突）
node dev.mjs

# 或直接（固定 5173）
./frontend/node_modules/.bin/tauri dev    # 必须在仓库根目录运行

# 检查与测试
cd src-tauri && cargo clippy --all-targets -- -D warnings && cargo test
node --test frontend/test/naming.test.mjs

# 生产构建（本地）
./frontend/node_modules/.bin/tauri build
# 产物：src-tauri/target/release/bundle/{nsis,msi}/
```

## 发布

CI 自动打包：推送 `v*` tag（如 `v0.1.0`）后，GitHub Actions 自动构建并发布
NSIS 安装器与 MSI 到 [Releases](https://github.com/pancake114514/manga_bookshelf/releases)。
tag 版本须与 `tauri.conf.json` / `Cargo.toml` / `package.json` 三处一致（工作流内置校验）。

```bash
# 更新三处版本号后：
git tag v0.1.0 && git push origin v0.1.0
```

## 支持格式

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.gif` `.tiff` `.tif`

## 窗口操作

Tauri 2 无边框窗口（`decorations: false`）：顶栏拖动/双击最大化/Snap Layouts、
Win+方向贴靠、边缘拖拽缩放（原生 `startResizeDragging`）、阅读器全屏、单实例。

## License

MIT
