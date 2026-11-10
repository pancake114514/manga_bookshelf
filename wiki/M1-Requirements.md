# M1 Requirements —— M1 范围需求与验收口径

> **事实源声明**：本文的「需求」与「验收标准」均由代码反推（即：M1 = 当前 v0.1.1 代码已实现的能力），不是从小抄或历史计划抄来的承诺。每行给出代码依据（仓库根相对路径:行号）。
> 产品定位与批次边界见 [产品定义与边界](产品定义与边界.md)；名词见 [产品术语表](产品术语表.md)；技术实现见 docs/technical/README.md（本轮并行任务产出）。
> 验收方式：本文只描述**可观察、可复现**的判定口径。标「未验证」的条目表示代码存在但未在真机（Tauri 运行时）走通，不得视为已验收。

## 0. 能力总览

| 编号 | 模块 | 能力 | 主依据 |
| --- | --- | --- | --- |
| R-SHELF | 书架 | 网格、密度、排序、渐进渲染、多选批量、卡片操作 | frontend/src/components/Bookshelf.vue |
| R-FILTER | 筛选与搜索 | 关键词搜索 + 标签/系列/评分组合筛选 + 搜索建议 | src-tauri/src/commands.rs:349-394、frontend/src/components/TagSidebar.vue |
| R-SERIES | 系列与分卷 | 归系列、卷号查重、平铺/分组双视图、分卷导航 | src-tauri/src/service.rs:480-501、frontend/src/components/Bookshelf.vue:176-227 |
| R-DETAIL | 详情页 | 元信息、可点击标签、缩略图网格、书签角标、对象侧栏 | frontend/src/components/DirectoryView.vue、DirectorySidebar.vue |
| R-READER | 阅读器 | 方向、双页、缩放、进度条、书签、快捷键、全屏 | frontend/src/components/Reader.vue |
| R-IMPORT | 导入 | 新建目录/追加目录/追加散图/批量多选、命名解析、.thumb 封面、整体回滚 | src-tauri/src/service.rs:661-915、frontend/src/components/ImportDialog.vue |
| R-MAINT | 库维护 | 整库迁移、库校验与修复、缩略图缓存清理、单实例与关闭拦截 | src-tauri/src/library_manager.rs:194-324、src-tauri/src/service.rs:230-423 |
| R-UI | 外观与窗口 | 主题令牌单源、深浅切换、无边框窗口、快捷键 | frontend/src/theme.js、frontend/src/App.vue、src-tauri/tauri.conf.json:18-34 |

## 1. 书架（R-SHELF）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-SHELF-01 | 以等尺寸封面网格展示对象，封面比例 5:7 | 卡片封面区 aspect-ratio 恒为 5/7；列宽为固定像素，窗口拉宽只增加右侧留白、不改变卡片尺寸 | frontend/src/styles.css:171、139-152 |
| R-SHELF-02 | 三档密度（紧凑/标准/大图），选择持久化 | 列宽分别为 132 / 176 / 232 px，gap 10 / 16 / 20 px；切换后写 config 键 ui_density，重启后保持 | frontend/src/styles.css:139-152、frontend/src/store.js:6-17、118-122 |
| R-SHELF-03 | 排序 5 种 + 升降序，排序选择持久化 | 排序键：created_at / name / images / rating / progress；字符串用中文 localeCompare。仅前端排序，不重新请求后端。持久化键 ui_sort（JSON 存 key+desc） | frontend/src/components/Bookshelf.vue:150-173、frontend/src/store.js:113-116 |
| R-SHELF-04 | 大库渐进渲染，首屏不全量挂载 DOM | 首屏仅渲染 80 张；滚动到距底部 600px 内每次追加 100 张；结果集/视图变化时重置为 80 | frontend/src/components/Bookshelf.vue:112-132 |
| R-SHELF-05 | 卡片显示阅读状态：在读进度条 / 读完角标 / 未读无标记 | 进度条宽度 = 进度%（公式见 R-READER-08）；读完角标条件 last_read_idx >= image_count-1；两者互斥 | frontend/src/components/ObjectCard.vue:19-23、111-116、frontend/src/utils.js:11-16 |
| R-SHELF-06 | 卡片悬浮可一键续读（直达上次进度） | 点击播放按钮取详情后进入阅读器，起始下标 = min(last_read_idx, image_count-1)；0 图对象提示「该对象没有内容」且不进入 | frontend/src/components/Bookshelf.vue:422-436 |
| R-SHELF-07 | 多选批量：批量打标签、批量删除（可选同时删本地文件） | 全选/取消全选基于全量结果集（不受渲染截断影响）；批量打标签为「追加并去重」，逐对象提交并显示 n/N 进度；批量删除逐对象调用，警告聚合展示（>3 条折叠为「等 N 条提示」） | frontend/src/components/Bookshelf.vue:71-78、322-402 |
| R-SHELF-08 | 卡片右键菜单与悬浮操作（续读/编辑/换封面/删除/打开目录） | 右键菜单 5 项；「在资源管理器中打开」直接调后端，其余复用卡片事件 | frontend/src/components/ObjectCard.vue:73-104 |
| R-SHELF-09 | 切换到新结果集有整批过渡动画，大结果集自动降级 | 结果集 > 300 时跳过动画直接替换；否则「整批右出 → 左入」，交错延迟上限 420ms；prefers-reduced-motion 下禁用动画 | frontend/src/components/Bookshelf.vue:134-143、246-274、frontend/src/styles.css:122-135 |
| R-SHELF-10 | 空库有明确空态 | 结果为空且无动画阶段时显示「书架空空如也，点击右上角「导入」…」 | frontend/src/components/Bookshelf.vue:65-66 |

## 2. 筛选与搜索（R-FILTER）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-FILTER-01 | 关键词搜索覆盖对象名、标签值、系列名 | 后端单条 SQL：o.name / t.value / s.name 三处 LIKE；通配符（反斜杠/百分号/下划线）在进入 LIKE 前已转义；大小写不敏感由 SQLite LIKE 决定 | src-tauri/src/db.rs:574-602 |
| R-FILTER-02 | 搜索输入防抖，不逐字请求 | 输入 200ms 后才写入 store.keyword 并触发查询 | frontend/src/components/TopBar.vue:66-67 |
| R-FILTER-03 | 搜索建议标注命中类别，作者与系列优先，最多 8 条 | 建议来自标签值聚合（排除 r18）+ 系列名；按「作者(0) → 系列(1) → 其他(2)」排序后截断 8 条；点击建议即以该词搜索 | frontend/src/components/TopBar.vue:70-93 |
| R-FILTER-04 | 标签类目多选筛选：类目内 OR、类目间 AND | 同一类目勾选多个值取并集；不同类目之间取交集 | src-tauri/src/db.rs:978-1002 |
| R-FILTER-05 | 评分筛选语义为「N 星及以上」 | 点第 N 颗星 → filters.rating = [N, N+1, …, 5]；再点同一星级清除 | frontend/src/components/TagSidebar.vue:80-95 |
| R-FILTER-06 | 系列筛选可与标签筛选组合 | filters 里 series 键走系列名查询（SQL IN），其余键在内存里再按标签过滤 | src-tauri/src/commands.rs:360-391、src-tauri/src/service.rs:143-158 |
| R-FILTER-07 | R-18 默认隐藏，开关可显示 | 后端 include_r18 默认 false，r18 对象在组装阶段被剔除；侧栏开关持久化键 ui_r18（存 '1'/'0'） | src-tauri/src/commands.rs:357、src-tauri/src/db.rs:531-537、frontend/src/store.js:108-111 |
| R-FILTER-08 | 筛选状态有可见反馈，可一键清除 | 工具栏显示「共 N 个对象（R-18 已隐藏）· 搜索「词」」；任一筛选存在时出现「清除全部筛选」 | frontend/src/components/Bookshelf.vue:4-6、frontend/src/components/TagSidebar.vue:45-47、72-73 |

## 3. 系列与分卷（R-SERIES）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-SERIES-01 | 对象可归入系列并按名幂等创建系列 | 系列名相同即复用同一系列记录（UNIQUE name），不重复建；改名走同一入口 | src-tauri/src/db.rs:681-695、src-tauri/src/service.rs:480-501 |
| R-SERIES-02 | 同系列卷号查重，冲突拒绝写入并说明冲突对象 | 报错文案为「该系列已存在卷 {vol}：「{other}」，请使用其他卷号」；查重发生在写库前，冲突时名称/标签等其他字段也不落库 | src-tauri/src/db.rs:408-425、src-tauri/src/service.rs:491-496、src-tauri/src/commands.rs:452-460 |
| R-SERIES-03 | 编辑系列后自动预填下一可用卷号 | 选中已有系列 → 取该系列现有卷号（排除自身当前卷）最大值 +1；新系列 → 1；清空系列 → 卷号同时清空；请求返回前用户改过卷号则不覆盖 | frontend/src/components/EditDialog.vue:165-183 |
| R-SERIES-04 | 书架支持平铺/系列分组双视图，分组可折叠 | 分组键为 series_name，遗漏的归「未分组」并排最后；组间按系列名中文排序；组内 volume 升序且空卷号殿后，再按当前全局排序键 | frontend/src/components/Bookshelf.vue:176-227 |
| R-SERIES-05 | 分组视图同样遵守渐进渲染预算 | 折叠组不占预算；组头「共 N 卷」始终显示全量计数，组内仅渲染预算内的成员 | frontend/src/components/Bookshelf.vue:217-226 |
| R-SERIES-06 | 系列列表返回成员数与首封面 | first_cover 取该系列内 volume 最小（NULL 殿后）对象的 cover_image；列表按系列名排序 | src-tauri/src/db.rs:697-726 |
| R-SERIES-07 | 详情页侧栏可按卷号跳转同系列其他卷 | 按 series_id 取全部卷，排序为「有卷号在前 → 卷号升序 → 创建时间」；仅当卷数 > 1 时显示分卷列表，当前卷高亮 | src-tauri/src/db.rs:644-664、frontend/src/components/DirectorySidebar.vue:12-26 |
| R-SERIES-08 | 系列变空时自动清理，不留空系列 | 对象移出或删除后执行 prune_empty_series（幂等） | src-tauri/src/db.rs:427-439、src-tauri/src/service.rs:498-499、590-591 |

## 4. 详情页（R-DETAIL）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-DETAIL-01 | 元信息区展示封面、标题、系列·卷号、评分、标签 | 系列行格式「{系列名} · 第 {volume} 卷」（无卷号则只显示系列名）；无标签时显示「暂无标签」；封面加载失败隐藏整个封面块而非显示裂图 | frontend/src/components/DirectoryView.vue:6-31 |
| R-DETAIL-02 | 标签可点击回书架筛选 | 点击任意非 r18 标签 → 以该标签为筛选条件并切回书架；r18 标签不可点击（只展示「R-18」） | frontend/src/components/DirectoryView.vue:21-27、105-108 |
| R-DETAIL-03 | 缩略图网格展示全部页，固定列宽 | 列宽 150px 固定，auto-fill 排列，不随窗口伸缩；每格显示文件名 | frontend/src/components/DirectoryView.vue:33-43、154-157 |
| R-DETAIL-04 | 有书签的页显示角标 | 进入详情页按对象 ID 加载书签并转成页下标集合；切换同系列其他卷时必须重新加载（否则沿用上一卷的角标） | frontend/src/components/DirectoryView.vue:58-68、35-41 |
| R-DETAIL-05 | 双击缩略图从该页进入阅读器 | 传入 index=该页下标、from=directory，返回时回详情页 | frontend/src/components/DirectoryView.vue:111-114、frontend/src/components/Reader.vue:462-468 |
| R-DETAIL-06 | 对象侧栏：分卷导航 + 书签列表 + 张数/进度 + 打开存储目录 | 书签行显示 P{page_idx+1} 与备注（无备注回退文件名），点击进阅读器定位；脚注显示「N 张 · 已读 x%」；打开目录失败给出错误提示 | frontend/src/components/DirectorySidebar.vue:28-48、96-120 |
| R-DETAIL-07 | 详情页与书架侧栏宽度/收起态分别记忆 | 侧栏宽度 180–400px 可拖，收起为 28px 细条；Ctrl+B 切换；书架与详情各自一套持久化键 | frontend/src/constants.js:19-22、frontend/src/sidebar.js:8-44、frontend/src/store.js:129-138 |

## 5. 阅读器（R-READER）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-READER-01 | 阅读方向默认右→左（日漫），可切换并持久化 | 默认 rtl=true；切换写 config 键 ui_reader_direction（'rtl'/'ltr'），重启阅读器后恢复 | frontend/src/components/Reader.vue:125、323-327、449 |
| R-READER-02 | 双页对开：封面单显，从第 2 页起对开，且右开本主位在右 | 对齐规则：index 0 单显；否则对齐到奇数下标（1,3,5…）。RTL 时当前下标图在右、下一张在左，LTR 相反。因此双页同屏为 1-based 的「第 2、3 页」「第 4、5 页」…… | frontend/src/components/Reader.vue:169-184 |
| R-READER-03 | 双页模式下翻页步长为 2，切页时页码标签显示区间 | 双页且 i+1<total 时标签为「{i+1}-{i+2} / {total}」，否则「{i+1} / {total}」；切换双页开关时立即按对开基页重对齐 | frontend/src/components/Reader.vue:155-160、201-202、315-322 |
| R-READER-04 | 缩放四态：适应页面 / 适应宽度 / 原始尺寸 / 自由缩放，前三种持久化 | 三态按钮写 config 键 ui_reader_zoom（fit/width/original），重启恢复；free 为临时态不持久化 | frontend/src/components/Reader.vue:109、119、328-332、447-449 |
| R-READER-05 | Ctrl+滚轮自由缩放，范围 20%–800%，步长 10%，以光标为锚点 | 每次 wheel 事件 ±10%，clamp 到 [20, 800]；从其他模式进入时以当前显示尺寸换算基准百分比（画面不跳变）；缩放后修正 scroll 使光标处内容不动；双击页面恢复「适应页面」 | frontend/src/components/Reader.vue:334-366、404-406 |
| R-READER-06 | 自由缩放下可按住拖拽平移，且不与点击翻页冲突 | 位移 > 4px 视为拖拽（不翻页）；点击落在左 1/3 与右 1/3 时按方向翻页（RTL 左=下一页，LTR 右=下一页） | frontend/src/components/Reader.vue:368-403 |
| R-READER-07 | 滚轮翻页有 75ms 冷却；非「适应页面」模式下滚轮只滚动不翻页 | fit 模式下滚轮上下翻页、横向滚轮按阅读方向翻页；任意模式下 ctrl+滚轮始终为缩放 | frontend/src/components/Reader.vue:415-427 |
| R-READER-08 | 进度条可拖动，拖动中即时预览、松手才落库 | 拖动时页码/滑块即时跟随，图片加载按 200ms 节流，松手才 goTo 并落库；进度条两侧内缩 20px，RTL 自右端起；页码 = round(ratio*(total-1)) | frontend/src/components/Reader.vue:75-96、475-513 |
| R-READER-09 | 阅读进度自动保存，退出必落库 | 翻页后 400ms 防抖写入 last_read_idx；组件卸载（返回/Esc/切换视图任一退出路径）再兜底写一次 | frontend/src/components/Reader.vue:186-191、453-460 |
| R-READER-10 | 书签：B 键/按钮增删、进度条刻度、备注行内编辑 | 当前页已有书签时按钮为主色态；点刻度跳页；备注保存走同一 upsert（同页覆盖） | frontend/src/components/Reader.vue:9-35、215-281 |
| R-READER-11 | 翻页无闪白，且交替翻页不串图 | 新图完整解码后才切换显示，旧图保持显示；快速连翻时用代际计数丢弃过期请求；双页两页都就绪才整屏切换 | frontend/src/components/Reader.vue:131-137、283-313 |
| R-READER-12 | 预加载相邻页 | 进入与每次翻页时预载前后各 3 张 | frontend/src/components/Reader.vue:204-213、450 |
| R-READER-13 | 键盘快捷键 | ↑/↓ 前后翻页；←/→ 按方向翻页；Esc 返回；F 或 F11 全屏；D 双页；B 书签；输入框内不劫持 | frontend/src/components/Reader.vue:429-442 |
| R-READER-14 | 工具栏 2.2s 无操作自动隐藏；真全屏走窗口层 | 鼠标静止 2200ms 后顶栏与底栏淡出且不可点；全屏通过窗口 API（非 HTML requestFullscreen），退出阅读器时兜底还原 | frontend/src/components/Reader.vue:408-413、470-473、458 |
| R-READER-15 | 0 图对象有明确空态而非无限转圈 | total=0 时显示「该对象没有内容」 | frontend/src/components/Reader.vue:67-68 |

## 6. 导入（R-IMPORT）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-IMPORT-01 | 四种导入方式 | 新建目录 / 导入文件夹到已有目录 / 导入图片文件到已有目录 / 批量多选文件夹各建一个对象 | frontend/src/components/ImportDialog.vue:4-16 |
| R-IMPORT-02 | 对象名合法性在导入前校验 | 非空；长度 ≤ 200（当前按字节计，见 §10.1 第 13 条）；不含反斜杠、正斜杠、冒号、星号、问号、双引号、尖括号、竖线共九个非法字符；非 Windows 保留名（CON/PRN/AUX/NUL/COM0-9/LPT0-9）；不以点或空格开头/结尾。失败显示具体原因并中止 | src-tauri/src/file_ops.rs:158-194、frontend/src/components/ImportDialog.vue:331-334 |
| R-IMPORT-03 | 从文件夹名解析命名规则并预填 | 规则：可选数字编号前缀 + 可选圆括号 CM 段 + 可选方括号作者段 + 本名，兼容全角括号；对象名 = 去掉编号前缀的全名，cm/author 进标签且不覆盖已填值 | frontend/src/naming.js:1-56、frontend/src/components/ImportDialog.vue:198-210 |
| R-IMPORT-04 | 只导入受支持的图片格式，跳过隐藏文件 | 支持 .jpg .jpeg .png .bmp .webp .gif .tiff .tif；以点开头的文件不计入正文 | src-tauri/src/config.rs:3-5、src-tauri/src/file_ops.rs:42-64 |
| R-IMPORT-05 | 保留原文件名；重名时加 (n) 递增 | 首次为原名，之后 名(1).ext、名(2).ext…；多扩展名只按最后一段处理（archive.tar.gz → archive.tar(1).gz） | src-tauri/src/file_ops.rs:70-100 |
| R-IMPORT-06 | 页序按自然排序写入，追加接在末尾 | 新建对象从 0 起按自然序编号；追加起点为 MAX(sort_order)+1（不是 COUNT），删除中间页后再追加也不会与已有页重号 | src-tauri/src/file_ops.rs:19-64、src-tauri/src/db.rs:884-895、src-tauri/src/service.rs:726-729 |
| R-IMPORT-07 | .thumb 文件作为封面且不进正文 | 源目录存在 .thumb* → 复制进存储目录并记为封面（优先于首图）；纯 .thumb 无扩展名时按魔数判定是否图片；伪 .thumb 被忽略并回退首图；.thumb 复制失败仅告警不影响导入 | src-tauri/src/file_ops.rs:105-155、src-tauri/src/service.rs:731-745、780-793 |
| R-IMPORT-08 | 导入失败整体回滚，不残留半成品 | 任一步出错：删除已建对象/已入库图片行、删除本次新建的目录、逐个删除本次已复制文件 | src-tauri/src/service.rs:798-844 |
| R-IMPORT-09 | 目标目录占用防御 | 新建时：<root>/<name> 已被其他对象登记 → 拒绝；目录存在且非空（不属任何对象）→ 拒绝并说明「为避免误删其中文件」；追加时存储目录丢失 → 按对象名重建，若重建路径被占用 → 拒绝 | src-tauri/src/service.rs:685-721、622-651 |
| R-IMPORT-10 | 导入期间不阻塞其他操作 | 复制阶段不持 DB 锁，仅建对象与入库各持一次短锁；导入命令以 async 命令跑独立线程 | src-tauri/src/service.rs:655-659、src-tauri/src/commands.rs:548-550 |
| R-IMPORT-11 | 批量导入逐项报结果，可中途停止 | 每项先校验名称再导入，逐项显示 ✓/✗ 与原因；「停止剩余」在下一次循环开始时生效；空目录（0 张）默认不勾选 | frontend/src/components/ImportDialog.vue:60-93、275-314 |
| R-IMPORT-12 | 计数失败必须显式呈现，不得静默按 0 | countImages 抛错时该行显示「读取失败：{原因}（已默认不勾选）」 | frontend/src/components/ImportDialog.vue:230-258 |

## 7. 库维护（R-MAINT）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-MAINT-01 | 首次使用需设置图库根，且只接受可写目录 | 目录不存在 → 「目录不存在」；写测试文件失败 → 「没有写入权限，请选择其他目录」；后端以 ok:false 返回（非 reject），前端必须判 ok 否则会把只读目录当成功 | src-tauri/src/library_manager.rs:32-40、src-tauri/src/commands.rs:332-339、frontend/src/components/SetupGate.vue:38-56 |
| R-MAINT-02 | 库路径状态可查询，目录失效时不静默 | get_state 返回 storage_root + valid（目录存在且可写），valid=false 时前端回到设置页 | src-tauri/src/commands.rs:319-330、frontend/src/App.vue:18-20 |
| R-MAINT-03 | 整库迁移三阶段，移动目录期间不长时间持锁 | ①短锁出计划 + WAL checkpoint(TRUNCATE) + 先写 .bak.tmp 再改名为 .bak；②无锁 fs::rename；③短锁单事务改库。备份失败在移目录之前中止 | src-tauri/src/library_manager.rs:204-225、254-310 |
| R-MAINT-04 | 迁移前置校验 | 新旧目录相同 → 拒绝；互相包含（按路径组件判定，D:/Manga2 不算在 D:/Manga 内）→ 拒绝；新根不可写 → 拒绝；任一对象存储目录不存在 → 拒绝并指出对象名 | src-tauri/src/library_manager.rs:46-64、79-113 |
| R-MAINT-05 | 迁移失败可回滚，且不会谎报成功 | 目录移动失败 → 逆序搬回，回滚若有失败则附「请手动恢复」清单；DB 阶段失败（含 COMMIT 失败）同样走该出口 | src-tauri/src/library_manager.rs:160-192、272-310 |
| R-MAINT-06 | 迁移期间阻断会写文件的命令与退出 | 迁移独占位生效期间：导入/删除/应用修复返回「图库迁移正在进行中…」；关闭窗口弹「正在迁移图库」确认；守卫在函数退出（含 panic）时复位 | src-tauri/src/service.rs:28-35、96-109、src-tauri/src/lib.rs:160-207 |
| R-MAINT-07 | 迁移后清理旧缓存与备份，库外路径给提示 | 成功时删除旧根的 .thumbcache 与 .bak；迁移后未改动的图片/封面路径作为 warning 返回并在界面提示条数 | src-tauri/src/library_manager.rs:231-245、313-323、frontend/src/components/LibraryDialog.vue:185-190 |
| R-MAINT-08 | 库校验只读报告四类异常 | 报告含 objects_total / missing_images_total / unregistered_total / abnormal[]（每项：目录是否存在、缺失图片名、未登记文件名）/ orphan_dirs[]；扫盘在 DB 锁外进行 | src-tauri/src/service.rs:230-325 |
| R-MAINT-09 | 校验修复三类操作幂等，顺序固定 | 移除缺失记录（复查文件仍缺失才删）→ 补登记（以 DB 现状比对，页序本对象内连续递增）→ 删除空对象（不删文件，判定复查）。重复执行结果不再变化 | src-tauri/src/service.rs:327-423 |
| R-MAINT-10 | 修复项默认值区分破坏性 | 移除缺失记录、补登记默认勾选；删除空对象默认不勾（破坏性） | frontend/src/components/LibraryDialog.vue:130-142 |
| R-MAINT-11 | 缩略图缓存清理：失效条目 + 2GB 总量上限 | 按「活动源 × 三个尺寸档 × 当前 mtime/size」算出应保留集合，其余删除；仍超 2GB 则按 mtime 最旧优先删；跳过 .tmp；返回删除数与释放字节 | src-tauri/src/thumbnail.rs:188-264、src-tauri/src/service.rs:210-224、src-tauri/src/config.rs:13-14 |
| R-MAINT-12 | 缩略图缓存键含生成器版本与源指纹 | 版本参与哈希（算法升级即全量失效）；mtime（纳秒）+ size 参与文件名（源图被替换即失效）；先写 .tmp 再 rename | src-tauri/src/thumbnail.rs:20-49、135-144 |
| R-MAINT-13 | 缩略图生成应用 EXIF 方向 | 解码时读取 orientation 并 apply，手机竖拍不再旋转错误 | src-tauri/src/thumbnail.rs:91-100 |
| R-MAINT-14 | 缩略图生成并发受限，不抢占 UI 线程 | 未命中缓存的重活受信号量限制为 2 并发；缓存命中不占许可；协议处理放在后台线程（异步协议） | src-tauri/src/lib.rs:18-58、88-133 |
| R-MAINT-15 | 删除对象：清缓存、删记录、级联、可选删文件，失败只告警 | 顺序：清该对象缩略图缓存 → 删对象行（tags/images/bookmarks 级联）→ 清空系列 → 若 delete_files 且目录不与别的对象共享则物理删除；共享/占用只返回 warning，不回滚 DB 删除 | src-tauri/src/service.rs:555-616 |
| R-MAINT-16 | 删除进行中拦截退出 | 删除计数 > 0 时关闭窗口需二次确认（「正在删除，确定退出吗？」），确认后才放行 | src-tauri/src/commands.rs:520-546、src-tauri/src/lib.rs:160-207 |
| R-MAINT-17 | 单实例运行 | 注册为第一个插件；二次启动唤起已有窗口（show + unminimize + set_focus）后新进程退出 | src-tauri/src/lib.rs:75-84 |
| R-MAINT-18 | 数据库版本化迁移，DDL 与版本号同事务 | 全新库执行基线 DDL 后置 user_version=1；老库只置版本不重建表；v2 加 series、v3 加 bookmarks，每步 DDL 与 PRAGMA 同事务提交 | src-tauri/src/db.rs:213-264、108-190 |
| R-MAINT-19 | 在系统中定位对象目录 | 取 storage_path，目录不存在 → 「目录不存在：{path}」；成功则 reveal_item_in_dir | src-tauri/src/commands.rs:771-789 |

## 8. 外观与窗口（R-UI）

| 编号 | 需求 | 验收标准（可验证口径） | 依据 |
| --- | --- | --- | --- |
| R-UI-01 | 深浅主题，选择持久化 | 切换写 config 键 ui_theme（'dark'/'light'），启动时恢复；非法值回落 dark | frontend/src/store.js:68、103-106、frontend/src/App.vue:2 |
| R-UI-02 | 设计令牌单一真源 | 同一批令牌值同时驱动 Naive UI 主题与 CSS 变量；下拉/气泡等 teleport 到 body 的弹层也从 html 根变量取值 | frontend/src/theme.js:1-88、frontend/src/App.vue:58-63 |
| R-UI-03 | 视觉纪律：直角、单一强调色、无阴影/渐变 | borderRadius 恒 '0px'；唯一强调色 #D2232F（深浅主题同值）；卡片 hover 只改边框色不浮起 | frontend/src/theme.js:8-54、frontend/src/styles.css:153-166 |
| R-UI-04 | 字体 Inter 单字族，字重分层 | fontFamily 为 Inter → Helvetica Neue → Segoe UI → Microsoft YaHei UI → sans-serif | frontend/src/theme.js:29、53 |
| R-UI-05 | 无边框窗口与自绘标题栏 | decorations=false；顶栏可拖动（原生 startDragging）/双击最大化；双击标题栏切换最大化状态同步 | src-tauri/tauri.conf.json:20-29、frontend/src/api.js:89-92、frontend/src/windowState.js |
| R-UI-06 | 窗口默认与最小尺寸 | 默认 1280×820，最小 1000×680 | src-tauri/tauri.conf.json:22-25 |
| R-UI-07 | 启动失败与未初始化有不同界面 | bootError 优先于 ready 渲染「启动失败 + 重试」；storageRoot 为空才显示设置向导；重试时回到加载态 | frontend/src/App.vue:11-33、frontend/src/store.js:56-93 |
| R-UI-08 | 全局快捷键 | Ctrl+F 聚焦搜索；Ctrl+B 切换当前视图侧栏（输入框内不劫持）；Esc 退出多选 | frontend/src/components/TopBar.vue:95-102、frontend/src/App.vue:69-76、frontend/src/components/Bookshelf.vue:404-408 |
| R-UI-09 | 封面换图后不会继续显示旧缓存图 | 封面 URL 带 ?v=<sha2 前 6 字节>（由 cover_image 与首图路径派生），路径变则 URL 变 | src-tauri/src/commands.rs:265-275、286 |

## 9. 验收现状汇总

| 状态 | 数量 | 说明 |
| --- | --- | --- |
| 代码存在 + 后端单测覆盖 | 66 项单测（db 4 / service 32 / commands 5 / file_ops 10 / thumbnail 6 / library_manager 9） | 统计口径：src-tauri/src 下 #[test] 数量 |
| 代码存在 + 前端单测覆盖 | 12 项断言（naming.test.mjs，已实跑 ALL PASS） | frontend/test/naming.test.mjs:18-67 |
| 代码存在但未真机验证 | 见 §10 第 19 条 | 需 Tauri 运行时，浏览器无 IPC |
| 已知缺陷（未修） | 见 §10 第 1–14 条 | 来自 handoff.md 批次 2–4 |
| 待产品判断 | 见 §10 第 15–16 条 | 行为是否属缺陷尚无结论 |

## 10. 已知未达成 / 未验证

### 10.1 已知缺陷（代码可证，未修）

| # | 现象 | 依据 | 影响 |
| --- | --- | --- | --- |
| 1 | 关键词搜索时系列/标签筛选被整体丢弃：q 非空只走 search_objects | src-tauri/src/commands.rs:383-391 | 搜索框与侧栏筛选同时使用时结果忽略筛选，用户以为筛选生效 |
| 2 | 编辑对象分 4 次独立提交（系列/名称/标签/封面），中途失败留下部分保存 | src-tauri/src/commands.rs:452-471 | 与「整单不落库」的注释承诺不符 |
| 3 | 服务层不校验对象名，IPC 可绕过前端校验；Path::join 未断言仍在图库根内 | src-tauri/src/service.rs:685-704、646-651 | 名称含 .. 时可写到库外；叠加删除会误删库外目录 |
| 4 | collect_images 读目录失败返回空 Vec（无 Result） | src-tauri/src/file_ops.rs:42-47 | 无权限/网络盘断开时导入继续，产出 0 图「导入成功」 |
| 5 | 老库（user_version=0 且已有 objects）不执行基线 DDL，缺唯一索引 idx_tags_unique | src-tauri/src/db.rs:222-246、150-155 | 历史库重复标签无法被约束拦截 |
| 6 | 删除对象持 DB 锁执行清缓存 + remove_dir_all | src-tauri/src/service.rs:565-616 | 大目录/机械盘时其他命令被堵住数秒 |
| 7 | 协议层读文件整入内存且无大小上限；.thumb 嗅探也整读 | src-tauri/src/lib.rs:212-228、src-tauri/src/file_ops.rs:124-131 | 超大图并发有 OOM 风险 |
| 8 | 多数查询命令非 async，在 IPC 主线程执行 | src-tauri/src/commands.rs:349-394、396-428、745-752、755-760 | 与持锁阶段叠加会冻结窗口 |
| 9 | DB 初始化失败直接 panic；且服务创建早于单实例插件注册 | src-tauri/src/lib.rs:67-73、75-84 | release 无控制台时用户只见进程消失；二次启动会短暂并发打开库 |
| 10 | set_config_value 无 key 白名单，可绕过 setup 直接改 storage_root | src-tauri/src/commands.rs:622-629 | 图库根指向未校验目录 |
| 11 | 缩略图 .tmp 无唯一后缀，同缓存键并发 rename 可能竞争失败并回退发原图 | src-tauri/src/thumbnail.rs:135-144 | 偶发发原图、性能劣化 |
| 12 | copy_image_keep_name 用 exists() + copy，存在 TOCTOU 与半文件 | src-tauri/src/file_ops.rs:86-99 | 并发导入同名文件可能覆盖/残缺 |
| 13 | 名称长度按字节（len）而非字符计数；未过滤控制字符；未覆盖「CON .txt」这类带空格保留名 | src-tauri/src/file_ops.rs:163-192 | 中文名 200 字节上限≈66 字；个别保留名漏网 |
| 14 | collect_images 不判 file_type().is_file()，名为 cover.jpg 的子目录也会被收集 | src-tauri/src/file_ops.rs:44-53 | 导入时该目录被当图片复制并失败，计入 failed |

### 10.2 待产品判断（无结论）

| # | 现象 | 依据 | 待定问题 |
| --- | --- | --- | --- |
| 15 | get_series_volumes 固定传 include_r18=true | src-tauri/src/commands.rs:745-752 | 全局关闭 R-18 时详情侧栏仍出现 R-18 分卷：是设计还是缺陷 |
| 16 | CSP 为 null | src-tauri/tauri.conf.json:32 | 是否需设 CSP |
| 17 | 单页对象（image_count=1、last_read_idx=0）导入后立即显示「读完」角标 | frontend/src/components/ObjectCard.vue:113-116 | 与「未读无标记」的产品表述冲突，需确认是否应排除单页对象 |
| 18 | 「阅读进度」排序用 idx/image_count，卡片进度条用 idx/(image_count-1) | frontend/src/components/Bookshelf.vue:156 vs frontend/src/utils.js:15 | 同一概念两套口径，排序与显示会不同步 |

### 10.3 真机未验证（不得视为已验收）

| # | 未验证项 | 原因 | 依据 |
| --- | --- | --- | --- |
| 19 | R-18 遮罩逐卡解除、阅读器偏好恢复、迁移/删除的关闭拦截、capabilities 收紧后的打包冒烟 | 需 Tauri 运行时；浏览器无 IPC，native 对话框/全屏/协议均不可测 | handoff.md:68、105-109 |
| 20 | COMMIT 真失败的回滚分支 | 只有结构上与事务内失败共用出口，无注入测试 | handoff.md:107 |
| 21 | 单次导入的「取消」 | 后端接口有 cancel_check 参数，但 IPC 恒传 None、界面无取消入口 | src-tauri/src/commands.rs:562-571、src-tauri/src/service.rs:752-757 |
| 22 | 存量 sort_order 重排 | 明确不做（会错位 last_read_idx 与 bookmarks.page_idx） | handoff.md:73 |

### 10.4 ⚠ 与文档差异（已于 2026-11-10 按方案 A 对齐）

> D1–D8 已通过修改 `README.md` / `handoff.md` / `AGENTS.MD` 对齐到代码（纯文档修正，未改代码）。
> 下表记录的是**修正前**的说法，保留作历史对照。D1/D2/D3/D8 背后的功能缺口仍然真实存在，见 §10.1 第 5、21 条。

| # | 原文档说法 | 代码事实 | 依据 |
| --- | --- | --- | --- |
| D1 | README.md:43「导入/取消全路径回滚」暗示可取消导入 | 取消能力仅存在于后端参数，IPC 未暴露、界面无入口 | src-tauri/src/commands.rs:562-571 |
| D2 | README.md:44「库校验：缺失图片/未登记文件/空对象/孤儿目录报告 + 幂等修复」 | 孤儿目录**只报告不修复**，可修复的只有前 3 类 | src-tauri/src/service.rs:303-316、327-423 |
| D3 | README.md:21「卡片阅读进度可视化：在读进度条 / 读完角标 / 未读无标记」 | 单页对象（1 张、未读）同时满足「读完」，角标与「未读无标记」冲突 | frontend/src/components/ObjectCard.vue:113-116 |
| D4 | README.md:33「双页对开（封面单显、自动对齐奇偶页）」 | 实际规则是「封面单显 + 奇数下标为基页」，即第 2/3、4/5 页同屏；「奇偶页」表述含糊 | frontend/src/components/Reader.vue:179-184 |
| D5 | README.md:26「可点击标签」 | r18 标签不可点击（仅展示 R-18） | frontend/src/components/DirectoryView.vue:21-27 |
| D6 | AGENTS.md:34 路由表指向 HANDOFF.md（大写） | 仓库实际文件为 handoff.md（小写）；2026-11-10 已改为小写 | 仓库根目录列表 |
| D7 | AGENTS.md:38 路由表指向 docs/milestones.md | 修正前不存在；2026-11-10 已创建（190 行） | docs/milestones.md |
| D8 | README.md:82-83「老库启动时自动增量升级」 | 老库确实升级到 v3，但不重跑基线 DDL，唯一索引可能缺失（见 §10.1 第 5 条） | src-tauri/src/db.rs:222-246 |