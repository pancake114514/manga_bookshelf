# 技术文档 · 总入口

MangaShelf 的技术文档索引。本目录所有结论以 `src-tauri/src/` 与 `frontend/src/` 的代码为唯一事实源；
与 [README](../../README.md)、[handoff](../../handoff.md) 冲突处一律按代码记述，并在正文以 **「⚠ 与文档差异」** 标注。

| 文档 | 覆盖内容 |
| --- | --- |
| **README.md**（本页） | 技术栈与版本、进程/线程模型、分层、模块职责（含行数）、文档导航 |
| [架构与模块](架构与模块.md) | 逐模块关键函数（带行号）、Builder 装配顺序、导入/删除/迁移/校验/缩略图的调用关系 |
| [数据模型](数据模型.md) | 完整 DDL（v1 基线 + v2/v3 增量）、字段语义、索引与唯一约束、CASCADE、存储布局、URL 规则 |
| [接口清单](接口清单.md) | 24 个 Tauri command 的入参/返回/副作用/错误形态、`mangashelf://` 协议、前端 `api.js` 映射 |
| [前端结构](前端结构.md) | Vue3 应用结构、渲染优先级、store 持久化键、api/theme/sidebar/windowState/naming、组件清单 |
| [质量与构建](质量与构建.md) | clippy/cargo test/vite build/CI/Release、本地开发端口协商、产物路径、约定与验证边界 |

## 1. 技术栈与版本

版本号三处一致为 **0.1.1**：`src-tauri/Cargo.toml:3`、`src-tauri/tauri.conf.json:4`、`frontend/package.json:4`。

| 组件 | 声明（Cargo.toml / package.json） | 锁定（Cargo.lock / package-lock.json） | 依据 |
| --- | --- | --- | --- |
| Rust edition / MSRV | 2021 / 1.77 | — | src-tauri/Cargo.toml:6-7 |
| Tauri | `2` | 2.11.5 | src-tauri/Cargo.toml:17；Cargo.lock |
| tauri-macros（`#[tauri::command]` 参数改写规则） | — | 2.6.3 | Cargo.lock |
| tauri-plugin-single-instance | `2.0.0-rc.5` | 2.4.5 | src-tauri/Cargo.toml:29 |
| tauri-plugin-dialog / opener | `2` | 2.7.3 / 2.5.5 | src-tauri/Cargo.toml:18-19 |
| rusqlite（bundled SQLite） | `0.32` | 0.32.1（libsqlite3-sys 0.30.1） | src-tauri/Cargo.toml:22 |
| image | `0.25`，features：jpeg/png/bmp/webp/gif/tiff | 0.25.10 | src-tauri/Cargo.toml:24 |
| sha2 / hex | `0.10` / `0.4` | 0.10.9 / 0.4.3 | src-tauri/Cargo.toml:25-26 |
| uuid（v4）/ serde / serde_json | `1` | 1.26.1 / 1.0.229 / 1.0.151 | src-tauri/Cargo.toml:20-23 |
| log / env_logger | 0.4 / 0.11 | 0.4.34 / 0.11.11 | src-tauri/Cargo.toml:27-28 |
| Vue | `^3.5.13` | 3.5.42 | frontend/package.json:15 |
| Vite / @vitejs/plugin-vue | `^6.0.7` / `^5.2.1` | 6.4.3 / 5.2.4 | frontend/package.json:19-20 |
| Naive UI | `^2.40.3` | 2.45.3 | frontend/package.json:14 |
| @tauri-apps/api / plugin-dialog / cli | `^2` / `^2` / `^2.11.4` | 2.11.1 / 2.7.3 / 2.11.4 | frontend/package.json:12-19 |

其他关键配置：

- 无边框窗口（`decorations:false`，1280×820，最小 1000×680）、`"csp": null`：`src-tauri/tauri.conf.json:19-33`。
- 权限集仅窗口控制 + `dialog:allow-open`：`src-tauri/capabilities/default.json:6-22`（`fs`/`shell` 已移除）。
- release：`opt-level=3`、`lto=true`、`strip=true`：`src-tauri/Cargo.toml:31-35`。

## 2. 进程与线程模型

单进程应用，进程内并发点全部手写（无 tokio/rayon，未配置线程池）。

| 执行体 | 产生方式 | 承担的工作 | 并发度 | 依据 |
| --- | --- | --- | --- | --- |
| OS 进程 | 用户启动 | 全部逻辑；第二个实例只唤起主窗口后退出 | 1 | lib.rs:78-84 |
| Tauri 主线程（事件循环） | `Builder::run` | 窗口事件、关闭拦截、**16 个未标 `async` 的命令**、协议 handler 的派发 | 1 | lib.rs:161-209 |
| Tauri sync_threadpool 线程 | `#[tauri::command(async)]` | 导入、删除、迁移、库校验、缓存清理、目录计数（8 个命令） | 线程池，可并行 | commands.rs:146/530/550/580/600/736/755/763 |
| 自定义协议 handler 线程 | `std::thread::spawn`，**每请求一条，无池化** | 解析 `mangashelf://` URL、读文件、必要时生成缩略图 | 不受限（WebView 一次可涌入上百请求） | lib.rs:98-132 |
| 缩略图生成许可 | 计数信号量 `THUMB_SEMAPHORE` | 缓存未命中的解码 + 缩放（CPU 重活） | **2** | lib.rs:22、24-58、105-118 |
| 退出确认线程 | `std::thread::spawn` | 原生模态框 `blocking_show`（阻塞式对话框不能放主线程） | 1 | lib.rs:188-204 |
| DB 访问 | `Mutex<Database>` 单连接 | 所有 SQL 串行执行 | 1（互斥） | service.rs:21-26 |

关键点：

1. **DB 是单连接、单互斥**（`LibraryService.db: Mutex<Database>`），因此命令之间的并发只体现在文件 IO 上；`delete_object` 甚至在持锁期间做 `clear_cached_thumbs` 与 `remove_dir_all`（service.rs:565-615）。
2. **锁中毒可恢复**：全部加锁点使用 `.unwrap_or_else(|p| p.into_inner())`，理由见 service.rs:5-6。
3. **协议层不排队读缓存**：先 `cached_thumb_path` 无锁探测，命中直接读文件（不占许可）；未命中才 `acquire()` 排队生成，`release()` 归还（lib.rs:101-118）。
4. **迁移独占**：`migrating: AtomicBool` + RAII 守卫（service.rs:25-35、96-101），迁移期间拒绝会写文件的命令。
5. **关闭拦截**：`CloseRequested` 读取 `deletions_in_progress()` 与 `migrating`，非 0/true 时 `prevent_close()` 并弹确认框（lib.rs:161-207）。

> ⚠ 与文档差异：lib.rs:77 注释称单实例插件"须注册为第一个插件；避免多进程并发写同一 SQLite 库"，
> 但 `LibraryService::new` 在 `Builder` 之前执行（lib.rs:67-73 vs 78），第二实例在插件生效前已打开数据库，
> 该注释的承诺只在插件回调之后成立。[handoff](../../handoff.md) §5 3.4 已把"建服务挪到单实例插件之后"列为待办。

## 3. 分层与依赖方向

```
frontend/ (Vue3 + Naive UI, WebView)
  components/*.vue ── api.js(invoke) ──► Tauri IPC          ┌─ <img src="..."> ─┐
  (数据/操作)                              │                  └─────────┬─────────┘
                                           ▼                            ▼
                              commands.rs（IPC 边界 + DTO）   lib.rs 协议 handler
                                           │                  mangashelf://（不经 IPC）
                                           ▼                            │
                              service.rs（业务门面 + Mutex + 迁移独占）  │
                                  │                │                    │
                     ┌────────────┘                └──────────┐         │
                     ▼                                        ▼         │
            db.rs（rusqlite / SQLite）              file_ops.rs ◄─────────┘
                                                    thumbnail.rs
                                                    library_manager.rs
```

| 规则 | 说明 | 依据 |
| --- | --- | --- |
| 单向依赖 | `commands → service → db`；`service` 另调 `file_ops / thumbnail / library_manager`；`db` 不反向依赖任何业务模块 | 各文件 `use` 语句 |
| 图片不过 IPC | 图片/缩略图/封面由自定义协议直供，IPC 只传 URL 字符串 | commands.rs:293-315、lib.rs:88-133 |
| 只有 commands 面向 JS | 其余模块的 `pub` 仅供 crate 内调用 | lib.rs:7-16 |
| 命令名 = Rust 函数名 | 宏用 `stringify!(#command)` 作为命令名（外部 crate `tauri-macros 2.6.3` 行为），故命令名恒为 snake_case | commands.rs:319-789 + lib.rs:134-159 |

## 4. 模块职责（含行数）

行数口径：文件内容行数（`Get-Content <file> | Measure-Object`/等价 `(Get-Content).Count`，含单元测试）。

| 文件 | 行数 | 职责 | 关键入口 |
| --- | ---: | --- | --- |
| src-tauri/src/main.rs | 6 | 进程入口，仅调用 `mangashelf_lib::run()`；release 关闭控制台窗口 | `main` (main.rs:4) |
| src-tauri/src/config.rs | 43 | 常量（支持格式、三档缩略图尺寸、缓存目录与 2GB 上限）、类别顺序、DB 路径解析 | `db_path` (29)、`is_supported_image` (20) |
| src-tauri/src/lib.rs | 247 | Builder 装配、单实例、关闭拦截、`mangashelf` 协议注册、缩略图信号量、图片响应与 MIME | `run` (61)、`read_file_response` (212)、`guess_mime` (230) |
| src-tauri/src/db.rs | 1211 | 数据模型、基线 DDL、版本化迁移、装配查询、标签/图片/系列/书签 CRUD | `Database::open` (199)、`migrate` (217)、`assemble_objects` (444) |
| src-tauri/src/service.rs | 1632 | 业务门面：锁、迁移独占、导入回滚、删除、库校验与修复、系列/书签 | `import_directory` (661)、`delete_object` (558)、`verify_library` (230) |
| src-tauri/src/commands.rs | 907 | IPC 边界：请求/响应 serde 结构体、DTO 组装、URL 生成、协议 URL 解析 | `get_objects` (350)、`resolve_image_url` (638)、`cover_version` (268) |
| src-tauri/src/file_ops.rs | 359 | 自然排序键、`collect_images`、保留文件名复制与 `(n)` 去重、`.thumb` 嗅探、Windows 名称校验 | `natural_key` (19)、`copy_image_keep_name` (70) |
| src-tauri/src/thumbnail.rs | 421 | 缩略图缓存键、EXIF 方向、双滤波策略、原子写、按源清理与总量清理 | `generate_thumbnail` (68)、`prune_thumb_cache` (199) |
| src-tauri/src/library_manager.rs | 557 | 库迁移三阶段（计划/执行/回滚）、路径规范化与包含判定、可写校验、备份 | `migrate_library` (194)、`normalize_path` (46) |
| **合计** | **5383** | 后端单测 66 个（db 4 / service 32 / commands 5 / file_ops 10 / thumbnail 6 / library_manager 9） | `#[test]` 计数 |

前端（非本次文档重点）：`frontend/src/api.js` 120 行是唯一 IPC 封装；`store.js` 138、`constants.js` 22；`frontend/test/naming.test.mjs` 为唯一前端测试。

## 5. 全局不变式（改动前先读）

| 不变式 | 内容 | 依据 |
| --- | --- | --- |
| 锁边界 | 慢速文件 IO 不持 DB 锁（导入三段式、迁移第②步）；例外是 `delete_object` 与补登记循环 | service.rs:655-659、library_manager.rs:254-275、service.rs:565-615 |
| 迁移互斥 | 迁移期间 `import_directory`/`import_single_files`/`delete_object`/`apply_verify_fixes` 一律拒绝；纯 DB 写（改名/标签/书签）不受阻 | service.rs:104-109、330、564、675、854；library_manager.rs:202 |
| 原子写 | 缩略图先写 `*.tmp` 再 `rename`；DB 基线 DDL 与 `PRAGMA user_version` 同事务 | thumbnail.rs:136-142、db.rs:232-246 |
| 路径比较 | 一律走 `normalize_path`（canonicalize + Windows 小写）；包含判定按路径组件 | library_manager.rs:46-64、service.rs:930 |
| 排序稳定 | 页序键 `natural_key`（数字段按值、整串兜底），追加起点为 `MAX(sort_order)+1` | file_ops.rs:19-38、db.rs:887-895 |
| 缓存可失效 | 缩略图缓存键含生成器版本 `v2` + 源路径 + 尺寸 + mtime + size | thumbnail.rs:22-49 |

## 6. 质量与验证规则

| 项 | 规则 | 依据 |
| --- | --- | --- |
| 后端测试 | `cd src-tauri && cargo test`（66 个单测） | 各 `mod tests` |
| 静态检查 | `cargo clippy --all-targets -- -D warnings` | README.md:102 |
| **禁止** `cargo fmt` | 仓库本身非 rustfmt-clean，格式化会产生大量无关 diff | handoff.md:66 |
| 前端测试（仅本地） | `node --test frontend/test/naming.test.mjs`；**CI 不执行**，需手动跑 | README.md:103 |
| CI 实际步骤 | `npm ci` → `npm run build`（前端产物，Tauri 构建的输入）→ `cargo clippy --all-targets -- -D warnings` → `cargo test` → `cargo build`（debug）；无前端测试 | .github/workflows/ci.yml:29-45 |
| CI 触发残留 | push 分支列表含已不存在的 `tauri` 分支（本地与 origin 均只有 `master`/`minimalism`），属无害残留 | ci.yml:5 |
| 构建产物 | `src-tauri/gen/schemas/*.json` 由 `tauri-build` 每次再生，随配置一起提交 | handoff.md:67 |

## 7. 文档导航

| 需要了解 | 去哪 | 状态 |
| --- | --- | --- |
| 技术栈、分层、模块与行数 | 本页 | ✅ 本次创建 |
| 模块内部实现与调用关系 | [架构与模块](架构与模块.md) | ✅ 本次创建 |
| 数据库表/字段/DDL/路径与 URL | [数据模型](数据模型.md) | ✅ 本次创建 |
| 24 个命令与协议接口 | [接口清单](接口清单.md) | ✅ 本次创建 |
| 前端应用结构与组件 | [前端结构](前端结构.md) | ✅ 已创建（同批） |
| 构建、CI 与验证边界 | [质量与构建](质量与构建.md) | ✅ 已创建（同批） |
| 产品验收口径 | [wiki/M1-Requirements.md](../../wiki/M1-Requirements.md)、[wiki/产品定义与边界.md](../../wiki/产品定义与边界.md)、[wiki/产品术语表.md](../../wiki/产品术语表.md) | ✅ 已创建（同批） |
| 当前任务目标与验收 | [SPEC.md](../../SPEC.md)、[specs/2026-11-doc-backfill.md](../../specs/2026-11-doc-backfill.md) | ✅ 已创建（同批） |
| 里程碑历史 | [docs/milestones.md](../milestones.md) | ✅ 已创建（同批） |
| 交接状态与待办 | [handoff.md](../../handoff.md) | ✅ 存在（AGENTS.MD 已于 2026-11-10 改为小写） |
| 项目总览与开发命令 | [README.md](../../README.md) | ✅ 存在 |

> ⚠ 与文档差异（2026-11-10 已修正）：`AGENTS.MD` 路由表原把交接文档写作 `HANDOFF.md`，仓库实际文件是 `handoff.md`
> （Windows 大小写不敏感可打开，Linux/CI 上会 404）；现路由表已改为小写并注明「历史快照」。
> `wiki/`、`SPEC.md`、`specs/`、`docs/milestones.md` 由同批的其他文档任务创建，本页只对 `docs/technical/` 负责；
> 本目录六页（README / 架构与模块 / 数据模型 / 接口清单 / 前端结构 / 质量与构建）同批落地。

## 8. 差异速查（详见各页）

| # | 说法 | 代码事实 | 详见 |
| --- | --- | --- | --- |
| 1 | README「搜索 + 侧栏筛选可组合」 | `q` 非空时只走 `search_objects`，系列/标签筛选被整体丢弃 | [接口清单](接口清单.md) §5 |
| 2 | 命令注释：Windows 为 `https://mangashelf.localhost` | 实际生成 `http://mangashelf.localhost` | [接口清单](接口清单.md) §3.1、§5.2 |
| 3 | README「老库（含 Python 版）启动时自动增量升级」 | 老库（`user_version=0` 且已有 `objects`）只补 v2/v3，不重跑基线 DDL，唯一索引等仍缺失 | [数据模型](数据模型.md) §8 |
| 4 | handoff §5 3.3 建议 `verify_library` 改 async | 已是 `#[tauri::command(async)]`，该建议过时 | [接口清单](接口清单.md) §5.2 |
| 5 | 迁移「三阶段」 | 实际是三段执行 + 独立 prepare + 失败统一出口；成功后才删 `.bak` | [架构与模块](架构与模块.md) §8.2 |
