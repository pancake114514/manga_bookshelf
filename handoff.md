# MangaShelf 交接说明（handoff）

更新时间：2026-11-01 · 分支 `master` · 版本 v0.1.1（`src-tauri/Cargo.toml` / `frontend/package.json` 未递增，仍是 0.1.1）

> **历史快照**：本文记录 2026-11-01 的交接状态，不是当前需求。产品与技术事实源见
> `wiki/`、`docs/technical/`、`SPEC.md`（路由见 `AGENTS.MD` §7）。文中与代码不一致处以代码为准。

## 1. 当前状态

两路子代理审查（前端 Vue / 后端 Rust）共报出 **27 项缺陷 + 24 项死代码冗余**。本轮已处理：死代码全部（可安全删除的部分）、前端 5 项缺陷、后端批次 1（迁移数据安全）、页序修正。**后端批次 2–4 待做**，清单见 §5。

本轮提交（均已推送）：

| 提交 | 内容 |
|---|---|
| `455f665` refactor(ui) | 前端死代码清理 + 5 项界面缺陷修复 |
| `b67a256` fix(library) | 后端死代码/依赖/权限精简 + 批次 1 迁移数据安全 |
| `bf6347f` fix(library) | 页序自然排序 + 追加序号起点改 `MAX(sort_order)+1` |

审查起点提交是 `027760a`。

## 2. 已完成的工作

### 2.1 前端缺陷（5 项，全部逐行复核确认过）

| 严重度 | 位置 | 原问题 | 现在的处理 |
|---|---|---|---|
| P1 | `SetupGate.vue` confirm() | 后端对不可写目录返回 `Ok({ok:false})`（`commands.rs:333`），前端不判 `ok` → 只读目录被当成设置成功，重启又回到本页 | 检查 `res.ok`，失败显示 `res.error` 并中止 |
| P1 | `App.vue` + `store.js` boot() | `finally` 无条件 `ready=true`，此时 `storageRoot` 为 null → 渲染 SetupGate，`.boot-error` 永不可达，启动失败被伪装成"请先设置目录" | `bootError` 优先于 `ready` 渲染；`boot()` 开始处复位 `ready`，重试会回加载态 |
| P1 | `Bookshelf.vue` revealedSet | R-18 遮罩的解除集合只有定义和读取、从无写入，`ObjectCard` 也没有 reveal 事件 → 遮罩**永远点不开**（模糊由 `is-r18` 类控制，与 revealed 无关） | 补齐链路：遮罩 `@click.stop` emit `reveal`，书架记录会话内解除集合，模糊类改为 `isR18 && !revealed` |
| P2 | `Reader.vue` 偏好恢复 | `api.getConfig` 已解包 `ConfigResponse.value` 返回字符串，Reader 三处又取 `r.value` → 恒 undefined，双页/缩放/阅读方向永远回默认 | 直接使用返回字符串 |
| P2 | `ImportDialog.vue` addEntries | `countImages` 异常被 `catch {}` 归 0 → 与后端 `collect_images` 吞错叠加，静默产出"空对象 + 导入成功" | 记录 `count_error` 并在清单显示"读取失败：原因（已默认不勾选）" |

### 2.2 死代码清理

前端：`api.js` 零消费者导出（`TAG_CATEGORIES`/`TAG_CATEGORY_ORDER`，与 `constants.js` 双份分类定义）与 3 个空挂 wrapper；`constants.js` 的 `R18_CAT`；`EdgeResize`/`SetupGate` 恒真不可达分支（含 `bridgeOk` 与其提示块、`.hint` 样式）；`Reader` 卸载时无效的 `bookmarks=[]`；`styles.css` 中被组件 scoped 完全覆盖的重复 `.reader-stage`。

归一：`TAG_MERGE_CATS` → 复用 `CATS`；阅读进度公式抽到 `utils.js:readProgressPct`（卡片与详情侧栏共用）；侧栏 4 个几何常量收敛进 `constants.js`（原 `sidebar.js` 与 `store.js` 各写一份 180/400）；`TitleBar` 去掉与子 `WindowControls` 重复的 `syncMaximized`；`Reader.back()` 不再与 `onUnmounted` 各存一次进度、各退一次全屏。

后端：`image-webp`、`windows 0.58`（全仓无引用且与 Tauri 传递依赖重复）；`tauri-plugin-fs`/`shell` 只有 `.init()` 从未调用，连同 `capabilities/default.json` 的 `fs:*`、`shell:allow-execute`、`dialog:allow-save/message/ask/confirm` 一并移除（JS 只用 `dialog.open`，Rust 侧调用不过 ACL）；两份逐字相同的 `normalize_path` 合并为 `library_manager::normalize_path`；`.thumbcache` 常量收敛到 `config::THUMB_CACHE_DIR`；`check_writable`/`rename_series`/`delete_series` 三条前端零调用的命令链路（命令 + 注册 + service/db 层 + 相应测试断言，经确认删除）；`ObjectDetail.storage_path`、`ImageSummary.sort_order` 两个前端不读的响应字段；`get_image_count`（被 `next_sort_order` 取代）。

### 2.3 后端批次 1：迁移数据安全

1. **关闭拦截纳入迁移**：`LibraryService.migrating: AtomicBool` + RAII 守卫 `begin_migration()`（Drop 复位，panic 展开也不漏）；`lib.rs` 的 CloseRequested 读 `deletions_in_progress()==0 && !migrating` 才放行，按操作类型给不同提示文案。原实现只挡删除，迁移大库时关窗口会留下"目录已在新根、DB 仍指旧根"。
2. **COMMIT 失败也回滚**：DB 阶段改为 `inner → COMMIT → 失败则 ROLLBACK`，事务内失败/COMMIT 失败/移目录失败三条错误路径统一走新加的 `migration_failed()`（先逆序送回目录，回滚受阻才附"请手动恢复"清单）。
3. **移目录阶段不再长时间持 DB 锁**：拆成 ①短锁出计划 + checkpoint 备份（备份留锁内，否则可能缺 WAL 数据）→ ②**无锁**建根 + `fs::rename` → ③短锁单事务更新 DB → ④无锁清旧根缓存与 `.bak`。并发窗口由 `migrating` 独占位堵住：`import_directory`/`import_single_files`/`delete_object`/`apply_verify_fixes` 入口 `ensure_not_migrating()`。
   副作用：迁移期间的纯 DB 写（改名/标签/书签）不再被阻塞，但发生在 `.bak` 之后——若真要手工恢复 `.bak` 会丢这部分。原实现是全程持锁互斥。
4. **路径包含判定按组件**：`is_relative_to` 用 `strip_prefix` + 非空相对路径，`D:\Manga2` 不再被误判为在 `D:\Manga` 内（原字符串 `starts_with` 会错误拒绝合法迁移）。
5. **顺带修掉静默缺陷**：`rollback_moved_dirs` 原先在"原位被占/新位已消失"时跳过却返回空清单，等于对上层谎报回滚成功；现在两种情况都计入失败清单。

### 2.4 页序修正

1. `collect_images` 改自然排序键（数字段按数值、字符段按字符、整串兜底）：未补零命名不再排成 `1/10/2`；补零库结果与字典序等价。单文件导入的排序共用同一键。
2. 追加起点由 `COUNT(*)` 改 `MAX(sort_order)+1`（`db.next_sort_order`）：删过中间页或补登记后 `count < MAX`，新页会与已有页同号，被 `ORDER BY sort_order, filename` 的文件名兜底插到已有页**前面**。补登记的序号计数改为本对象内连续（原为跨对象累计，第二个对象起出现空洞）。
   存量库的 `sort_order` 一个都没改。

## 3. 如何验证

```bash
# 后端（当前 66 项单测全通过，clippy --all-targets 零警告）
cd src-tauri && cargo test --lib && cargo clippy --all-targets

# 前端（vite build 通过；naming 测试 ALL PASS）
cd frontend && npx vite build && node --test test/naming.test.mjs
```

注意事项：

- **不要跑 `cargo fmt`**：仓库本身不是 rustfmt-clean（`commands.rs` 等处有既有风格差异），跑了会产生大量无关 diff。
- `src-tauri/gen/schemas/*.json` 是 `tauri-build` 每次构建再生的产物，删插件/改 capabilities 后必然巨幅变动，属正常，随配置一起提交。
- 浏览器里跑 `npx vite` 只能验证渲染路径：Tauri IPC 在浏览器不可用，`boot()` 必然失败——现在（正确修复后）会显示"启动失败/重试"面板，这就是预期。R-18 遮罩解除、阅读器偏好恢复、迁移/删除的关闭拦截**都要真机 `npm run dev`（Tauri）才能验证，目前尚未在真机验证过**。
- 反向验证过新测试有效：临时把 `next_sort_order` 改回 `COUNT(*)` → `append_after_removal_continues_from_max_sort_order` 失败（实测得到 `["0.png","b.png"]`）；把补登记计数器改回跨对象累计 → `apply_verify_fixes_registers_pages_contiguously_per_object` 失败（`[0,2]`）。之后已还原。

## 4. 明确不做 / 需要产品先定

- **不重排存量 `sort_order`**。`objects.last_read_idx` 与 `bookmarks.page_idx` 都是位置索引，重排会让阅读进度和书签集体跳错页；`bookmarks` 有 `UNIQUE(object_id, page_idx)`，重映射要两阶段偏移或 DELETE+重插才不撞约束。另外追加导入是"续到末尾"语义，全局按名重排会把后补的页插回中间。实测你的库（1 对象 25 页，`IMG_*`/哈希名/中文名混合，`sort_order` 0..24 无重复，0 书签）重排是倒退。留口子方案：校验/修复向导加**单对象显式**动作"按文件名重排本书"，同事务 remap 索引。
- **不改行为**：详情页与侧栏两次 `list_bookmarks`、导入完成后两侧都刷 tags/series、`get_series` 的 `count/first_cover` 相关子查询、恒传 `None` 的进度/取消参数（仅测试在用）、`get_objects` 分页。前两条要去重必须提共享状态，属改行为。
- **待你判断**：`commands.rs:746 get_series_volumes` 固定传 `include_r18=true`，全局关闭 R-18 时系列侧栏仍显示 R-18 分卷——是设计还是缺陷；`tauri.conf.json:32 "csp": null` 是否需要设 CSP。
- 你原本未跟踪的 `package.json`（仓库根）与 `frontend/public/` 不属于本轮工作，我没有纳入任何提交。

## 5. 接下来的改动计划

行号以本轮提交后的代码为准。建议按批次做，每条一个提交。

### 批次 2｜一致性与数据正确性（P2，用户可直接观察到的优先）

| # | 位置 | 现状与影响 | 建议改法 |
|---|---|---|---|
| 2.1 | `commands.rs:383` `get_objects` | `q` 非空时只走 `search_objects`，`series_filter`/`tag_filters` 被整体丢弃 → 搜索框与标签/系列筛选可共存，但结果忽略筛选 | db 层新增 `search_objects_filtered(q, series, tags, include_r18)`，LIKE 与标签/系列 EXISTS 子句进同一条参数化查询（复用 `db.rs` 既有 filters 构造器）；`get_objects` 收成一个入口 |
| 2.2 | `commands.rs:446` `update_object` | 系列/名称/标签/封面分 4 次独立提交 → 中途失败留下"部分保存成功"，与代码注释承诺的"整单不落库"矛盾 | service 加单事务 `update_object(oid, patch)`；把 `set_series_for_object` 拆出 `fn set_series(db: &Database, ...)` 内部版本（模式同 `resolve_append_target_dir`） |
| 2.3 | 导入与改名 | 服务层不校验名称（前端有校验但 IPC 可绕过），`Path::join(name)` 可含 `..`/绝对路径 → 能把图片写到库外，再配合 `delete_object(delete_files)` 删库外目录 | `import_directory`/`import_single_files`/`update_object_name` 入口统一 `validate_windows_path_name`；join 后用 `normalize_path` 组件比较断言仍在 `storage_root` 内；删除前做同一断言 |
| 2.4 | `file_ops.rs:42` `collect_images` | `read_dir` 出错返回空 Vec（无 `Result`）→ 无权限/网络盘断开时导入继续、创建空对象、返回成功 | 改返回 `Result<Vec<String>, String>` 并上抛；`count_images` 命令同步；前端已能显示读取失败原因 |
| 2.5 | `db.rs:167 MIGRATE_STEPS` / `154 idx_tags_unique` | 老库（`user_version=0` 且已有 `objects`）只置版本 1 跑增量，不执行基线 DDL → 唯一索引 `idx_tags_unique` 与部分索引在历史库上缺失，重复标签留着 | 新增幂等增量步骤：先按 `(object_id,category,value)` 去重，再 `CREATE UNIQUE INDEX IF NOT EXISTS`，与版本号同事务；老库/新库两条路径都要有用例 |

### 批次 3｜响应性与健壮性（P2）

| # | 位置 | 现状 | 建议改法 |
|---|---|---|---|
| 3.1 | `service.rs:558` `delete_object`（`601` 处删目录） | 持 DB 锁跑 `clear_cached_thumbs` + `remove_dir_all` → 大目录/机械盘时所有 DB 命令被堵住数秒 | 锁内取快照并完成行删除，`drop(db)` 后再删缓存与目录（warnings 语义不变） |
| 3.2 | `lib.rs:212` `read_file_response`；`file_ops.rs` `.thumb` 嗅探 | `std::fs::read` 整文件入内存且无大小上限；嗅探也整读 → 超大 TIFF/PNG 并发有 OOM 风险 | 先 `metadata()` 取 `Content-Length`，超阈值（如 64MB）返 413 或改分块；嗅探只读前 12 字节 |
| 3.3 | `commands.rs:350` 等查询命令 | 非 `#[tauri::command(async)]`，默认在 IPC 主线程执行 → 与 3.1/批次 1 的持锁阶段叠加会冻结窗口 | `get_objects`/`get_object_detail`/`get_series_volumes`/`verify_library` 改 async（分页不动，见 §4）。⚠ 2026-11 复核：`verify_library` 已是 `#[tauri::command(async)]`，该子项已过时 |
| 3.4 | `lib.rs:67/71` | DB 初始化失败直接 `panic!`，release 是 `windows_subsystem="windows"` 无控制台 → 用户只见进程消失；且 `LibraryService::new` 在 single-instance 注册之前执行，二次启动的进程会短暂并发打开 SQLite | 改记日志 + 原生 dialog 报错（db 路径与 `.bak` 提示）后退出；把建服务挪到单实例插件之后 |

### 批次 4｜P3 收尾（每条局部小改）

`commands.rs:623 set_config_value` 加 key 白名单并拒绝 `storage_root`（否则 IPC 可绕过 setup/迁移直接改库根）；`thumbnail.rs:136` 缩略图 `*.tmp` 加唯一后缀，避免同缓存键并发 `rename` 竞争失败回退发原图；`file_ops.rs:87` `copy_image_keep_name` 用 `OpenOptions::create_new` 占位，消除 `exists()+copy` 的 TOCTOU 与半文件；`file_ops.rs:163` 名称长度按 `chars().count()`、过滤控制字符、覆盖 `CON .txt` 这类带空格保留名；`collect_images` 增 `file_type().is_file()`（名为 `cover.jpg` 的子目录现在会被收）；`db.rs` 多处 `filter_map(\|r\| r.ok())` 改为收集错误并 `log::warn`；`find_thumb_cover` 多个 `.thumb*` 候选时排序后取首个（当前依赖 `read_dir` 顺序，封面不确定）。

## 6. 已知未覆盖

- COMMIT 真失败的回滚分支没有注入测试，只有结构上与事务内失败共用出口。
- 前端 5 项修复里，R-18 遮罩解除与阅读器偏好恢复未在真机验证（浏览器无 IPC）。
- capabilities 收紧后没跑过真机 `tauri build` 冒烟；`fs`/`shell` 已确认全仓无引用，构建与 clippy 通过。
- 自然排序只影响新导入/新追加，不影响存量。
