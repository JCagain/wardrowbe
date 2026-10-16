# 实现进度与实现期裁定

> 性质：**实现侧的台账**，不是需求。需求以 [personal-wardrobe-spec.md](./personal-wardrobe-spec.md)（原件，不改）
> \+ [personal-wardrobe-spec-fixes.md](./personal-wardrobe-spec-fixes.md)（勘误，不改，冲突时为准）为准。
> 本文记三件事：fixes 各条落到了哪个 commit；实现中做出的、改变或细化了需求语义的裁定；
> 明知不修的取舍。fixes 清单里的「现状」列是 2026-10-08 审计时的快照，**以本文为最新**。

## 一、fixes 清单实现进度

| fixes # | 内容 | 状态 | commit |
|---|---|---|---|
| D2 / 15 / 16 | 打标手动触发、取最佳像素 | ✅ | 294f390, 06533dd（Ruling 45–49） |
| D6 / 8 / 11 / 21 | 主图 RGBA PNG + L 模式 mask 旁挂 | ✅ | 4129261, 6ea1e8c, 1c5bff1 |
| 1 / 2 / 3 | 参考物检出、可手改框与类型、灰卡/白纸两种基准 | ✅ | 95fae2e, 5eda4a4, 0998cba, 60089f7, 6b9145c, 5cd7a0a |
| 4 | 色温/色调滑块 + 重算 | ✅ | 580402b, 6b9145c, 5cd7a0a（色调增益见 §三） |
| 5 / 6 | 校色前原图副本 `_src.jpg`、重置回原图 | ✅ | 29978be, 580402b |
| 7 | 增益有界 [0.25, 4.0] | ✅ | 8191a43, 14a0330 |
| 7a | `_src.jpg` 随旋转同步 | ✅ | a46526b, 480234c |
| 9 | 纯色底只作展示 | ✅（按 §二 21c：前端 CSS 背景，无服务端合成端点） | 4129261 |
| 10 / 12 | mask 持久化、画笔加/减 | ✅ | 4129261, 51583af |
| 13 | 改 mask 后三档同步重生成 | ✅ | 51583af, 2462836 |
| 14 | 还原重抠（`_orig.jpg`） | ✅（生命周期见 §二「抠图前备份」） | 既有 + §三 |
| 55 | compose 转发 `AI_API_KEY` | ✅ | 6859f26 |
| 62 / 63 | 校色、mask 测试覆盖 | ✅ | 随上列各 commit |
| 17 / 18 | 打标闭集：颜色/风格/季节从在役词表渲染为 slug=中文名；类型只渲染 slug（无中文名），AI 回中文名时按在役标签反查回 slug；AI 输出 primary_colors[] + secondary_colors[] 直写列 | ✅ | c72a00d, e132635, d60185b, 940ff90, c17f3b1, 039648f, 9881dab |
| 23 / 25–28 / 30–38 / 44（记录侧） | 记录：outfit_photos（1..N，只做转正+三档+旋转）、日期默认今天可改、季节按日期推导可手改、城市（设置预设杭州/香港/合肥/深圳，可扩展、可设默认、可空）、天气按城市+日期预填（过去日期走 archive）可改可清、关联任意件（含 0）可后补、关联增删 / 删记录自动 ± wear_count 并写 item_history、场合/备注可空；studio 场合可空 | ✅ | 24e5616, d87ee8b, f131693, 92362db, 1bcd5b2, cc7053b, a9481b8, 373feb5, 4d61e3c, f941d94 |
| 40 / 41 / 42 / 43 / 45 / 46 / 47 / 49 / 50 | 「浏览与编辑」计划（分支 feat/browse-edit）：#40 网格筛选（部位/类别/色系/具体色/风格/季节）；#41 色系与具体色分开，默认只按主色，另可切辅色 / 主或辅（Ruling 66）；#42 季节手改；#43 穿着次数显示 + 手改（Ruling 68）；#45 反查（Ruling 69）；#46 常搭 top 8（Ruling 70）；#47 记录时间线 + 深链（Ruling 71）；#49 统计页渲染本月 + 管线四桶（Ruling 72/73）；#50 颜色 / 风格分布标「件次」 | ✅ | 33675c5（筛选）, 4e01293（wear_count / 反查 / 常搭）, 63e6ff2（统计记录数）, f6df5fe + a20f59f（数据层、首页「本周」卡下线）, cc663ce（筛选栏）, 2c3c3f8（对话框拆分）, e7d6efa + 4679ac7（详情分区、季节手改）, 22dbc8c（历史时间线）, dde51bb（统计页）, 56422e6（终审修复） |
| 44 | 关联增删 / 删记录自动 ± wear_count | ✅ | 记录计划，Ruling 60–65 |
| 48 | 统计三档 scope（全部 / 排除退役 / 仅在役） | ✅ | 早于本计划；fixes 已裁定以 §10.16 为准 |
| 51 / 52 | 词表 gen 降为固定集合 + 类型生成 + 结构校验；软词表一律运行时取用（Ruling 74 / 75） | ✅ | 57ceca9（gen / 结构校验）, 4c50673 + 34b4eef（运行时取用） |
| 53 | 颜色插入：正X 锚点固定第一、渐变（橙黄按色相）（Ruling 76） | ✅ | a30a026 |
| 54 | 词表即时生效（D1） | ✅ | c72a00d 起懒读（`test_runtime_added_color_reaches_the_prompt_without_restart` 锁定），原文 §10.18 作废；后端类型→role / 默认洗涤间隔原先在 import 时绑定（`clothing.py` / `schemas/item.py`），新增类型要重启才生效，已改为 `role_for_type` / `default_wash_interval` 每次现读（`test_live_vocab_roles.py` 锁定） |
| 57 | 家庭评分三路由摘挂（Ruling 77） | ✅ | 6f4ae12 |
| 58 | UI 锁 zh-CN（Ruling 78） | ✅ | 8ab338a |
| 59 | k8s 进摘名单，README 标注下线 | ✅ | af0b5ea |
| 60 | 原文 §10 两个「16.」 | ✅（裁定，不改原文） | —（Ruling 79） |
| 61 | §10.7 两态作废，以 §10.16 三态为准 | ✅ | 已随 #48 / lifecycle 实现 |
| 29 | embedding 存储与同步 | ✅ 向量表 + 指纹过期（ea0c7e1）；image 队列同步作业 + 每分钟 cron + 设置页同步/全部重建（95138cb, c5ba702, 1a7b139, d05fa8d） | ea0c7e1, 95138cb, c5ba702, 1a7b139, d05fa8d |
| 39 | AI 建议关联：召回 + 框选 | ⚠️ 功能完成：单框建议端点（召回 top-15 按部位、视觉分组复判、5–8 候选、绝不写库）+ 框选对话框内挑选（55b1eb8, a2aab90, 600ee07, 167f8f1）；**召回质量待用户录够衣物后实跑 probe 确认** | 7fc60bb, 3da114e, ca50bf8, 577cf20, 41531d6, 55b1eb8, a2aab90, 600ee07, 167f8f1 |
| 56 | embedding 配置 | ✅ env 配置 + 客户端（a01244b），Ruling 80 | a01244b |
| D3 / 19 | 温度不由 AI 打，纯手填：`temp_low` / `temp_high` 可空数值列，录入页与详情页手填，打标提示与输出均无温度 | ✅ | 879c760（列）, ecb67ca（表单） |
| 20 / 24 | `subtype` 自由文本直传；UI 显示名「备注」，列名沿用 `subtype` 不迁移 | ✅ | ecb67ca |
| 22 | 购买时间默认 = 录入日的年月（本地日历），可改可清；批量上传无表单，保持为空（Ruling 101） | ✅ | 4f2adb7 |
| 64 | 记录测试：photos（`test_record_photos_api.py` 增删/重排/旋转）、city（`test_records_api.py` 设与清空、`test_weather_lookup_uses_city_coordinates`）、季节推导（`test_season.py`、`test_create_minimal_defaults_today_and_derived_season`、`record-season.test.ts`）、天气预填与历史天气（`test_weather_for_date.py` 近期走 forecast / 久远走 archive）、0 件保存（`test_create_minimal_…`、`test_patch_to_zero_items_and_back`） | ✅（逐项核对） | 随记录计划各 commit |
| 65 | 反查（`test_records_reverse_lookup_by_item`）、wear_count 手改与自动 ±（`test_manual_wear_count_then_records_delta`、`test_records_api.py` 增删/改日期/删记录/不为负）、常搭共现（`test_companions_*`） | ✅（逐项核对） | 4e01293 |
| 66 | 网格筛选补的维度：部位、色系、具体色（主/辅/任一）、风格，另含季节（`test_item_filters.py`、`wardrobe-filters.test.ts`） | ✅（逐项核对） | 33675c5, cc663ce |
| spec §8 备份 | 备份 = DB dump + 图片卷 + 词表 JSON：`scripts/backup.sh`，步骤与恢复见 [docs/backup.md](../backup.md)；脚本实跑过，dump 灌进临时库验证可恢复 | ✅ | 见本行所在 commit |

**fixes #6 与 #7a 的措辞冲突**：#6 写「校色/抠图/旋转都不得覆盖它」，#7a 要求旋转同步旋转它。以 **#7a 为准**——「不可变」指不得被处理产物覆盖，不禁止几何同步。

## 二、实现期裁定（代码注释引用的出处）

| 裁定 | 内容 |
|---|---|
| **Ruling 9** | 换主图（set-primary）把 `calibration_original_path` / `original_image_path` / `mask_path` 置 null，文件一个不删（`_src` 不可再生）；旧主图的旁挂文件成孤儿，不回收。 |
| **Ruling 10** | 抠图备份 `_orig.jpg` 尺寸与工作图不符即视为过期：`remove_background` 警告后以工作图重新播种再抠；`restore_original` 直接 ValueError（API 映射 400），不写回、不删备份。 |
| **Ruling 19**（检出算法） | 用户给的结构先验：实拍时白卡→灰卡→黑卡**成条相邻**摆放。检出先找「三块扁平矩形 + 沿主轴 L 单调阶梯」的三联条（看相对亮度，曝光不变），命中则以中间灰卡为参考、三框一起给 UI；不成条退回单卡兜底（中性块里灰卡优先、白纸次之）；没有中性候选返回 None，不猜白平衡。 |
| **Ruling 24**（中性闸门） | 参考卡是中性反射体：候选的平均色度须低于「全图色度中位数 ×1.6，夹在 [16, 80]」，挡住饱和彩块冒充灰卡。 |
| **Task R19 / R23** | 实现 Ruling 19 的任务编号；R23 = fixes #7a（旋转同步 `_src`）。 |
| **Ruling 21a** | 校色端点的 HTTP 响应带 `mask_cleared`，只在真删了 mask 文件时为 true，UI 据此提示「请重新抠图」。 |
| **Ruling 21c** | fixes #9 的「请求时指定底色临时合成」以前端 CSS 背景实现，不加服务端合成端点。`composite_on_white` 只作打标输入。 |
| **Ruling 28** | mask 与图像尺寸不一致即报错（400），不静默缩放——没有合法路径会造成不一致。 |
| **Ruling 38** | 校色状态是**会话态**，不落库。刷新后步骤条显示「未校色」；重置随时可用，不影响正确性。将来若加列，只改详情页初始化处。 |
| **抠图前备份** | `_orig.jpg` 是**当前抠图**的来源像素：抠图时首次生成；旋转时同步旋转；重新校色或还原原图时作废（删文件、`original_image_path` 置空）；画笔补抠与重抠都从它取 RGB（rembg 会把透明区 RGB 清零）。 |
| **Ruling 42**（录入页步骤条） | 录入页还没有物品，步骤条只作指引：`interactive={false}`，状态 span，无操作按钮。 |
| **Ruling 45** | 单张与批量上传两条路径都不再自动入队 `tag_item_image`（含批量只为自动打标而建的 redis 池）；`skip_ai` 入参保留但不起作用（D2 兼容）。 |
| **Ruling 46** | 上传后 `mark_pending(set_ready=True)`：status=ready、tagging_status=pending（`set_ready=False` 会让物品卡在 processing）。 |
| **Ruling 47** | 白底合成图是临时产物：写系统临时目录、不进存储目录，`analysis_input()` 在 `finally` 里删除。 |
| **Ruling 48** | `tag_item_image` 从 DB 行（`image_path`/`mask_path`）经 `resolve_analysis_path` 取输入，不信入队时的 `image_path` 参数（保留仅为队列兼容）；存在性检查针对解析后的工作图。 |
| **Ruling 49** | 前端步骤条「打标」改调 `useReanalyzeItem`（`POST /items/{id}/analyze`）：queued/already_queued → 已入队提示；deferred（视觉未启用）与 cooldown → 信息提示；出错 → 错误提示。`useRetagItem` 保留（仅 hook 定义，无调用方）。 |
| **Ruling 51** | 校色端点（detect/apply/manual/reset）在 `calibration_original_path` 为 NULL 时惰性补种 `_src`（`ImageService.ensure_calibration_source`）并落列：盘上已有且尺寸吻合 → 原样收养；否则有尺寸吻合的 `_orig` 备份 → 取备份像素；否则取工作图转 RGB（JPEG q95）；已有但尺寸不符 → 告警后覆盖。取代原先的 400 "no calibration source"。 |
| **Ruling 52** | `calibration/detect` 读校色副本 `_src`，不读工作图：抠图后工作图背景 RGB 已清零，卡条是黑的，永远检不出。 |
| **Ruling 53** | 详情对话框在旋转 / 还原原图 / 替换主图 / 设为主图成功后清掉旧检出框（`pending` 退回 `none`）；`restore-original` 补上与 remove-background / mask 同款的「后台 job 在跑 → 409」守卫。 |
| **Ruling 54**（已知取舍） | 无 `_orig` 备份的旧抠图物品，惰性补种 `_src` 时取到的是黑底工作图（RGB 已清零），补种出黑底 `_src`。只记取舍、不改码：分支前抠图都留 `_orig`，仅备份丢失时才会出现。 |
| **Ruling 55** | 提示词候选写成 `slug=中文名`，解析取 `=` 左侧；停用条目不进提示词、AI 回了也丢弃，但不影响旧物品的历史值与手改。 |
| **Ruling 56** | AI 仍回旧 `primary_color` / `colors` 时按字段走旧键兼容解析；`tags` blob 自 2026-10-14 起写新键（`primary_colors` / `secondary_colors`），旧键只读兼容。 |
| **Ruling 57** | `tags` blob 的颜色投影按列进行：只有过滤后非空的值才写入，空不等于清空；新指派主色而无可用辅色时，从现有辅色里剔除与新主色重叠的颜色。 |
| **Ruling 58** | `pattern` / `fit` 仍是代码内固定集合（spec §1.4 输出清单不含二者，不在本次闭集化范围）。 |
| **Ruling 59** | 主色至少一个：AI 只给辅色（主色空、辅色非空）时辅色整体升为主色、辅色清空（`_parse_tags_from_response`，info 日志；主辅都空仍 warning，**取代此前「只记 warning 不提升」的做法**）；手改保存强制至少一个主色（含未打标物品）——后端 `ItemUpdate.primary_colors` 显式给出空列表 → 422（未带该键不触发），详情对话框保存前拦截并 toast `primaryColorRequired`；上传不强制；`tags` blob 投影本就不会写空主色（Ruling 57）。 |
| **Ruling 60** | 记录存 `outfits`（`source = record`），走独立路由 `/records` + `RecordService`；studio/lookbook 的「已穿不可改关联」等约束不适用于记录。旧「历史」页即记录主页。通用 /outfits 列表、日历、批量删除与按 id 的各路由一律排除 source=record（按 id 访问记录返回 404），记录只能经 /records 改删，保证计数与文件清理不被绕过。 |
| **Ruling 61** | 记录照片 1..N（用户裁定 2026-10-14：开发库无旧记录，按 spec 字面）：新建至少 1 张，编辑时删到最后一张 → 409。照片只做 EXIF 转正 + 三档 + 手动 90° 旋转（用户裁定），不校色不抠图、不留 `_src`。 |
| **Ruling 62** | 天气只存 `temp_high` / `temp_low` / `condition`（用户裁定），`condition` 为 10 值闭集 slug（WMO 码映射），中文名走前端 i18n。预填由前端在城市/日期变化时调 `GET /records/weather`，后端保存时只存表单值、不自行补拉——「清空」不会被覆盖。forecast 端点覆盖过去 60 天 ~ 未来 15 天，更早走 archive；更远的未来不拉；任何失败返回 null。 |
| **Ruling 63** | 城市存 `user_preferences.cities`（NULL = 预设四城，带坐标），记录只存城市名；新增城市经 Nominatim 地理编码取坐标，找不到 422、服务不可用 502。删除城市不影响旧记录的城市名，但其天气查询返回 null。 |
| **Ruling 64** | `wear_count` 只做增量：关联新增 +1、移除 −1（下限 0）、删记录对全部关联 −1；`item_history` 每关联一行（`outfit_id` = 记录），随关联增删、随改日期改 `worn_at`、随改场合改 `occasion`；`last_worn_at` 在受影响衣物上重算为其 `item_history` 最大 `worn_at`。记录不碰洗护字段。 |
| **Ruling 65** | 改日期即按新日期重推导季节（用户裁定 2026-10-14）：PATCH 改了日期且同一请求未带 `season` → 后端 `season_for_date(新日期)`；带了则以所带为准；不改日期则不动季节（保留手改值）。前端改日期时同步重设季节下拉，用户可再手改后保存。 |
| **Ruling 66**（网格筛选） | 每维单值；色系与具体色按「颜色匹配」开关匹配主色（默认）/ 辅色 / 主或辅（用户 2026-10-15 裁定：筛选分主辅色）；色系在查询时展开且含停用色；body_part 为空按类别推；具体季节同时命中「四季」；筛选选项含停用词条（标注已停用）。理由：老数据 body_part 可能为空、停用词条仍挂在旧衣物上。代价：默认由「主色∪辅色」收窄为仅主色，要按辅色筛须切开关。 |
| **Ruling 67**（批量全选同口径） | 列表与全选共用后端 `item_filter_clauses`，前端共用 `vocabFiltersToItemFilter`；「全选 → 删除」不会越过屏幕上的筛选。理由：避免批量动作误伤屏幕外的衣物。代价：筛选逻辑只能有一份，改动须两端同步测。 |
| **Ruling 68**（手改穿着次数） | 独立行内编辑、只发 `wear_count`；不写 `item_history`、不动 `last_worn_at`；之后的记录增删在新值上 ±；编辑表单保存不带 `wear_count`。理由：防止保存旧表单值把记录刚改过的次数写回。代价：手改次数与 `item_history` 条数可以不一致。 |
| **Ruling 69**（反查） | source=record、关联该衣物、日期倒序、分页（20/页）；旧 `item_history` 20 条时间线下线，统计格与月柱状图保留。理由：记录才是穿着的主出处。代价：经 studio / lookbook 穿过但无记录的日期不再显示在详情里。 |
| **Ruling 70**（常搭） | 只看记录内共现；按共同记录数降序、同数按 id；top 8；含退役衣物并标注。理由：口径与反查一致且结果稳定。代价：只穿过、从未同记录的搭配看不到。 |
| **Ruling 71**（时间线与深链） | `?view=timeline`；`?date=YYYY-MM-DD` 定位并选中；记录保存 / 删除后回到该日；月历视图空月份显示单日空态。理由：详情反查可直达某天记录。代价：URL 参数非法时静默忽略。 |
| **Ruling 72**（统计记录数） | source=record；按记录日期、用户时区日历月；不受 scope 影响；`total_outfits` / `outfits_this_*` 字段删除。用户 2026-10-15 裁定不要「本周」数：统计页只显示总数与本月，首页「本周」卡下线，API 不提供 `records_this_week`。理由：旧字段统计的是 AI 生成搭配，已不是产品主线。代价：没有周粒度；`dashboard.weeklySummary.*` 文案键保留未清理（各语种目录一致不动）。 |
| **Ruling 73**（管线状态分布） | 四个桶（ready / processing / archived / error）全显示，含 0；颜色 / 风格 / 类型分布用词表标签（颜色带色块 hex），颜色与风格计数写「N 件次」，类型计「件」不加次。理由：一眼看出卡在处理中或出错的数量。代价：词表加载前（或已删词条）回退显示 slug。 |
| **Ruling 74**（gen 范围） | generated 只含部位 / 季节 / 材质 / 正式度及其类型；`vocab:check` 另校验软词表结构（slug 唯一与格式、label 非空、type.body_part 合法且有 role、color.family 合法、hex 格式）。软词表无编译期回退，加载前选择器为空、标签回退 slug。理由：运行时增改不再让生成文件过期、CI 变红；spec §2「不再各存一份」。代价：首屏词表到达前选择器短暂为空。 |
| **Ruling 75**（role 注册表） | 类型→role 由 `useVocabulary` 拉到词表时写入模块级注册表（`lib/vocab-roles.ts`），studio 的纯函数排序 / 槽位读它；未加载时视为无槽位。studio 页 `/dashboard/outfits/new` 自己调 `useVocabulary()`，词表到达前画布显示 spinner、出错显示错误态并可重试——角色注册表必须先于任何 reducer 排序 / 槽位 / 警告就绪，直接打开或 `?edit=` 也不例外；同时 studio reducer 的 `LOAD` 与其他画布动作一样走 `canonicalItemOrder`。理由：reducer 不能调 hook。代价：模块级可变状态；冷加载时 studio 多等一次请求才显示；studio 以外的模块在词表未加载时调 `roleForType` 仍得 undefined；以非规范顺序保存的搭配在 studio 里按规范顺序显示（仅在用户保存时才改写已存顺序）。 |
| **Ruling 76**（颜色插入） | 锚点 = 色系首行且中文名以「正」开头，每系一个；新行永不越过锚点（含另一个「正X」）；无锚点时以「正」开头的新行成为锚点；其余按渐变（明度亮→暗；橙黄系按色相黄→橙，hue>180° 记为负）；黑白灰 / 金属追加尾部。JSON 与 vocabulary.md 共用 `color_insert_index`。理由：vocabulary.md 头部约定。代价：手改表时把非正X 行放到首位，该系即视为无锚点。 |
| **Ruling 77**（家庭评分） | `/outfits/{id}/family-rating(s)` 三路由去装饰器、函数保留；路由级测试移入 `tests/pruned/`；响应里的 `family_ratings*` 字段保留，不再有新写入（已有评分照常返回）。理由：spec §7「后端路由关闭或不挂」。代价：无。 |
| **Ruling 78**（锁 zh-CN） | request config 固定 zh-CN，不读 cookie / Accept-Language；zh-CN 仍以 en 为底合并消息；LocaleSwitcher 归档 `components/dormant/` 并进入口守卫；后端 `user.locale` 列与校验不动（前端不读）。理由：fixes D4。代价：无。 |
| **Ruling 79**（原文 §10 编号） | 原文不改。fixes 与代码注释沿用原文编号，§10.16 有两条（天气预填 / 状态三态）时以上下文区分；新写的注释引用 §10.16 须带标题（如「§10.16 状态三态」）。理由：fixes #60 只是勘误，原件不改。代价：编号查找需看标题。 |
| **Ruling 80**（embedding 只走 env） | embedding 端点只读 `AI_EMBEDDING_BASE_URL / _API_KEY / _MODEL`（`Settings.embedding_configured`），不进设置页的 `ai_endpoints`。理由：避开 CLAUDE.md 坑 3（设置页优先于 env）在第二个端点上重演。代价：换端点要改 `.env` 并 `docker compose up -d` 重建容器；`AI_EMBEDDING_TIMEOUT` 未在 docker-compose 转发（仅 env 可读，需要时写进 `.env` 并补转发）。 |
| **Ruling 81**（指纹扫描判过期） | 向量是否过期由 `source_fingerprint`（工作图 `path:mtime_ns:size` + mask 同款）与已存值比对，扫描时判定，不在各改图端点挂钩。理由：改像素的端点多（校色 / 抠图 / 画笔 / 旋转 / 换主图），挂钩必漏。代价：同路径、同 mtime、同大小的改写检测不到；每次扫描对每件 ready 衣物 stat 一次（个人规模可忽略）。 |
| **Ruling 82**（向量输入 = 白底抠图） | 衣物向量的输入与打标一致，取「当前最佳像素」：有 mask 文件时抠图合成到白底，否则用工作图。理由：背景不应进入相似度。代价：无 mask 的衣物按原图算。（透明通道的扩展见 Ruling 86。） |
| **Ruling 83**（候选含闲置 / 已退役） | 召回候选不按生命周期状态过滤，闲置与已退役的衣物也参与；只按用户、模型（以及可选的部位）过滤。理由：穿搭照里可能出现已退役的旧衣，漏召回比多召回更糟。代价：候选里会有已退役项，由第二期界面标注或排序。 |
| **Ruling 84**（框存照片行） | `garment_regions` 存在 `outfit_photos` 行的 JSON 列，坐标为原图像素；旋转照片时清空（坐标系已变，留着就是错框）；保存时夹到图像尺寸内。理由：框属于照片，不属于记录。代价：旋转后需重画；框不随图像裁切 / 缩放迁移。 |
| **Ruling 85**（框带部位，D7 细化） | 每个框带 `body_part`（词表内部位），检出时模型给出，非法部位丢弃，用户可改；单照最多 12 个框，小于 8 像素的框丢弃，越界夹到图内、反向坐标交换。理由：第二期召回按部位过滤候选（`load_candidates(body_part=...)`）。代价：模型误判部位时需手改。 |
| **Ruling 86**（透明工作图也白底合成） | `embedding_input_image` 只要工作图带 alpha（RGBA / LA / 带 transparency 的 P）就合成到白底，不限于存在 mask 文件。理由：D6 把抠图存成 RGBA，直接 `convert("RGB")` 会让 alpha 0 处的隐藏背景漏进向量。代价：不透明图无变化，无代价。 |
| **Ruling 87**（框选界面，用户裁定 10-15） | 照片条缩略图显示框数徽标；重新检出会覆盖现有框，先确认；灯箱不叠加框。理由：用户裁定。代价：灯箱里看不到框。 |
| **Ruling 88**（检出只返回，保存才写） | `detect` 只返回夹好的框与图像宽高，不写库；仅当模型输出解析为 JSON 对象且其 `regions` 为列表时才成功（否则 502），合法空列表照返回为空，含义「没检出穿着」。保存（PUT）是唯一写入方，所以取消检出或关闭对话框都不会改动已存的框。理由：把「模型胡话」与「确实没有」分开，并消除检出与保存之间的竞态。代价：检出结果在点保存前只在本地，关闭对话框即丢；模型回了对象但内容全被过滤时同样返回空。 |
| **Ruling 89**（对话框冻结图源） | 框选对话框在其生命周期内冻结图片 `src`。理由：签名 URL 内嵌时间戳，记录 refetch 会换 URL、重载图片并清空 canvas。代价：对话框开着时照片被别处替换不会反映，需关闭重开。 |
| **Ruling 90**（同步覆盖已退役，坏图跳过） | `sync_item_embeddings` 处理状态为 `ready` 与 `archived`（已退役项的终态）的衣物，坏图（`OSError` / `UnidentifiedImageError`）记日志后跳过，计入 `SyncResult.skipped`，不中断本批与后续批次。理由：Ruling 83 要求已退役项参与召回，必须先有向量；一张坏图不能卡死同步。代价：被跳过的衣物保持过期，每次同步都会重试并再跳过。 |
| **Ruling 91**（llama.cpp 多模态 embedding 请求格式） | `/v1/embeddings` 的每个 input 为 `{"prompt_string", "multimodal_data": [base64]}`；prompt 套 Qwen3-VL-Embedding 聊天模板（指令作 system 轮，默认 "Represent the user's input."，以 `<|endoftext|>` 收尾供 `--pooling last` 取）；媒体占位符每台服务随机，从 `GET /props` 的 `media_marker` 读，取不到回落 `<__media__>`。理由：实连发现 llama.cpp 该端点拒收 OpenAI 式 `content` 数组（500）；同一组图上聊天模板比裸占位符区分度略好（增强副本与无关图的最小间隔 0.030 对 −0.004）。代价：不再兼容 OpenRouter 式 content 数组端点；换非 Qwen 的 embedding 模型需改模板。 |
| **Ruling 92**（同步触发） | 同步触发 = image worker 每分钟 cron（先 `ping`，有过期件才入队）+ 设置页手动，不在改图端点挂钩。理由：承接 Ruling 81 指纹扫描，挂钩必漏。代价：新衣物最多晚约 1 分钟 + 一次运行预算才有向量；永远读不了的坏图让该用户每分钟起一次空跑作业。 |
| **Ruling 93**（同步作业） | 同步作业跑在 `arq:images`、作业 id 固定 `embedding-sync:{user_id}`（id 即去重）、每次运行限时 `embedding_sync_budget_seconds`（默认 60）；image worker 在 worker 级设置 `keep_result=0`。理由：不堵 27B 打标队列；限时避免旋转/抠图被长同步卡住；worker 级设置是因为 arq 失败路径忽略按函数的 `keep_result`，否则固定 id 会被占住一小时。代价：大批量重建分多轮跑完（CPU 上约 2.3 秒/件）。 |
| **Ruling 94**（全部重建） | 全部重建 = 把该用户向量行的指纹置空，旧向量在逐件替换前继续参与召回。理由：重建期间建议功能不中断。代价：仅限同模型重算；换模型本身就会让全部向量变 stale，旧模型行按 `model` 过滤不参与召回，直到逐件重算完成（后台同步自动做），期间召回集合会变小。 |
| **Ruling 95**（建议一次一框） | 建议一次一个框；前端按选中框发请求、可取消；后端在复判分组之间检查连接断开就停；端点从不写库。理由：27B 单次复判数十秒，整张照片一次做完会让请求过长且无法细粒度取消。代价：多个框要逐个点。 |
| **Ruling 96**（召回与部位） | 召回 `RECALL_K=15`；先按部位过滤，命中少于 `PART_MIN=5` 时用全库结果补足（部位命中排前）。理由：spec 10–20；部位过滤提高精度，回落防止部位标错时完全找不到。代价：回落时混入其他部位的衣物。 |
| **Ruling 97**（复判） | 复判每次 1 张裁块 + `RERANK_GROUP=5` 张候选（384px），判 same/similar/different；排序 = 判定优先、余弦其次；`different` 只在不足 5 件时补位，最多 8 件；某组失败该组 verdict 为空、全部失败时按召回序（见 Ruling 100）返回并给 `rerank_error`；读不了图的候选不送复判。理由：27B ctx 8192，6 张 384px 图约千余 token，留足余量；spec 产出 5–8。代价：15 个候选要 3 次视觉调用。 |
| **Ruling 98**（查询侧指令） | 查询侧指令默认关（`QUERY_INSTRUCTION=None`，用模型默认 system 轮），待用户实跑 probe 的 `--instruction` 对比后再定。理由：第一期冒烟没有真实裁块可比。代价：可能不是最优召回。 |
| **Ruling 99**（挑选入库） | 挑中的候选只进编辑页本地关联列表，随记录「保存」才落库；对话框的「保存」只存框。理由：spec §3.2 / 原则 4「永不自动入库」。代价：用户要记得回到记录页保存（文案提示）。 |
| **Ruling 100**（无复判时的排序） | 当没有任何一组产生复判结果（rerank 关闭、视觉禁用或全部分组失败）时，建议端点按召回序返回候选，最多 8 件；召回序为部位命中在前、回落补位在后。`rank_candidates`（判定优先、余弦其次）只在至少有一个 verdict 之后才应用。理由：计划中的 `rank_candidates` 纯按余弦重排，会把部位命中的候选压在其他部位的高余弦补位之下。代价：复判之后，同判定的候选之间部位优先级丢失。 |
| **Ruling 101**（购买时间默认） | 单件录入表单的购买时间初值 = 打开表单当刻的本地年月（`entryYearMonth`），关闭重置时重新取；批量上传不填。理由：fixes #22 要求可改可清，批量上传没有可见的字段让用户改或清，静默盖上日期等于写入用户没看见的数据。代价：批量录入的衣物购买时间为空，需在详情页补。 |
| **R39** | 管线 UI 的挂载与 mutation 归属：详情页挂步骤条、参考框编辑器、mask 画笔；录入页只挂步骤条。`onTag` 原调 `POST /items/{id}/retag`，**已被 Ruling 49 取代**（改调 `POST /items/{id}/analyze`）；`tagged` = `tagging_status === 'tagged'`。`mask_cleared` 为 true 时提示「请重新抠图」并重置本地 hasMask。 |
| **R34** | `ItemResponse` 暴露 `mask_path`；`mask_cleared` 只留在校色响应上。 |
| **R35**（参考框编辑器） | 画三个卡框、主框高亮；四角与边中点手柄可拖；灰卡/白纸基准切换；`onApply(box, baseline)` / `onManual()`；坐标为全分辨率图像像素，box 含右下。 |
| **R36** | 测试不钉中文串，用结构性 `data-testid` 断言；要验真实译文则 `vi.unmock('next-intl')` 加 provider。 |
| **R38 / R21a** | 别名：= Ruling 38 / Ruling 21a。 |
| **R1 / R2 / R3 / R4 / R5**（= Ruling 27–31，mask 画笔任务） | R1 = Ruling 27：笔画坐标为全分辨率 mask 像素，无 `scale` 参数，前端用 `mapPointerToImage` 换算。R2 = Ruling 28（见上）。R3 = Ruling 29：mask 端点写回三档路径，但不得复用会清空 `mask_path` 的 `_persist_image_op`。R4 = Ruling 30：后台任务持有物品路径期间 mask 端点返回 409。R5 = Ruling 31：签名与命令以现有代码为准，不照计划文本（仅过程约定）。 |
| **T7-A** | 画笔与框选拖动 clamp 到图内（现为 `natural - 1`）。 |
| **T7-B** | 画笔落点抽稀：与上一记录点距离 ≥ 半径×0.3 才记录，起止点必记，以守住 2000 笔画上限。 |
| **box 契约** | `(l, t, r, b)` 含右下；合法范围 `0 <= l <= r < width`。前端 clamp 到 `natural - 1`。 |

## 三、2026-10-13 自检修复

| 问题 | 修复 | commit |
|---|---|---|
| 派生文件路径散写 | `ImageFiles` 单一命名出处 | 81b8f0b |
| 三档写回重复、mask 端点寄居校色模块、500 无堆栈 | `assign_size_paths`、`api/mask.py`、`logger.exception` | 527d4cd |
| 旋转不转 `_orig.jpg` | 伴随文件统一旋转 | db0f42a, 31854fd |
| 重校色不作废 `_orig.jpg` | `_clear_matte` | 5e9af2a |
| 画笔补抠出黑块、重抠在黑底上抠 | 从 `_orig.jpg` 取 RGB | b455ef5 |
| 检出 O(n³) | 邻接枚举 + `STRIP_MAX_CANDIDATES = 30`（杂乱场景实测 37.8s → 2.4s） | a72ee53 |
| 真实照片无回归钉 | `tests/fixtures/reference_strip_1200.jpg` | bf6bf3a |
| 色调滑块无效 | 增益 ±30% | a5a9b17 |
| 框选器贴边 400 | clamp 到 `natural - 1` | e7eee93 |
| 录入页假按钮 | `interactive={false}` | 2f4a670 |

## 四、已知取舍（明知不修）

- **同物品并发同步写无锁、三档原地覆盖写**：单人自用，两个标签页同时改同一件衣物的概率可忽略；崩溃中途最多留下尺寸不一致的三档，重做一次操作即恢复。
- **检出候选上限 30**：超限的杂乱场景里卡若不在面积前 30，退回单卡兜底，不保证找到三联。
- **`item-detail-dialog.tsx` 拆分**：留给「浏览与编辑」计划（该计划本就要大改此对话框）。
- **`bg_color` 请求字段**：只为兼容旧调用保留，后端不消费。
- **`docker-compose.prod.yml` 未转发 `AI_API_KEY`**：该文件是摘不删的离线备查，不维护。
- **过期备份尺寸守卫只拦 90°/270°**：旧版本「先抠图后旋转」遗留、被转了 180° 的备份尺寸与工作图相同，检测不到；对它重抠 / 还原会把 180° 旋转撤销。单人自用，旋转后用户会看到并可再转。
- **换主图再换回会遗留孤儿旁挂**（Ruling 9）：set-primary 只把 sidecar 列置 NULL、不删文件，换走再换回后旧的 `_src` / `_mask` / `_orig` 留在盘上成孤儿。
- **`_src` 会在下次校色时按尺寸重新收养**（Ruling 51）：尺寸吻合就接回；但 mask / 备份**不会**重新挂回，所以此时打标用的是不带白底合成的 RGBA，直到重新抠图。
- **旧物品的 `_src` 是惰性补种的**（Ruling 51）：取自首次校色那一刻的当前像素（旧抠图则取 `_orig` 备份），所以对它们「重置」回到的是首次校色时的像素，而不是相机原图。
- **无 `_orig` 备份的旧抠图物品，补种出的 `_src` 是黑底**（Ruling 51 分支 c）：工作图 RGBA 的透明区 RGB 已被 rembg 清零，转 RGB 即黑底；此后校色 / 手动白平衡 / 重置会把工作图重建为不透明黑底图，检出也找不到卡。分支前的抠图都会留 `_orig`，实际只在备份被删的物品上出现；遇到时先重新上传原图。
- **补种 `_src` 非原子写**，中途崩溃留截断文件会让后续校色持续 500，需手动删 `{base}_src.jpg`；detect 补种无 409 守卫，抠图任务进行中触发可能补种到中间态（之后每次使用都按尺寸校验，危害限于一次错误补种）。
- **`last_worn_at` 只认 `item_history`**（Ruling 64）：studio / lookbook 的「标记穿过」「今天穿」路径不写 `item_history`，经由它们穿过的日期在下次记录改动重算时会被丢掉。记录是主路径，studio 处于 lookbook 角色，不补。
- **记录照片不支持拖拽排序**：按添加顺序，删除后重排连续编号。
- **studio 不填场合时跳过学习与推荐缓存清理**（fixes #27）：`OutfitPerformance.occasion` 为 NOT NULL，无场合的 studio 搭配不进学习模块（学习已按 §7 摘除）；也不清推荐缓存。
- **季节标签在词表加载前回退显示 slug**（generated 只导出 `SEASON_VALUES` 的 slug）；色系不再进 generated，选择器在词表加载前为空、标签回退 slug（Ruling 74 / 下条「词表加载前软词表选择器为空」）；统计页对已删词条同样回退 slug。
- **时间线与反查都靠「加载更多」**，不做无限滚动。
- **网格颜色筛选默认从「主色∪辅色」改为「仅主色」**；要按辅色筛需切「颜色匹配」（fixes #41，Ruling 66）。
- **词表加载前软词表选择器为空**（Ruling 74）：颜色 / 类型 / 风格等软词表选择器在词表请求返回前为空，标签回退显示 slug。
- **embedding 验证脚本（`python -m scripts.embedding_probe`）判读标准**：augment 自检 recall@5 ≥ 0.8 且向量未塌缩（不同衣物两两余弦均值 ≤ 0.95；最大值 > 0.98 只打印相似度最高的一对作警告，近重复衣物属正常）；退出码 0 通过 / 1 塌缩 / 2 端点不可用 / 3 偏弱（recall@5 < 0.8 但未塌缩）/ 4 输入有误（未知邮箱、就绪且有图的衣物不足 2 件、`--pair` 路径或 UUID 无效）；第二期开工前由用户起服务实跑。这两项是对同一件衣物的增强副本做的自洽检查，不是真实穿搭照裁块的召回，所以通过是必要而非充分条件；真实裁块用 `--pair 图片路径:衣物UUID` 做参考，不设硬门槛。
- **AI 建议的召回质量尚未用真实数据验证**：库里衣物不足；见下方「五、AI 建议实跑检查点」。

## 五、AI 建议实跑检查点

需要真实服务与足量衣物，代码审查与容器测试覆盖不到。由用户在 embedding 服务（9932）与 27B（9931）都起来后执行：

1. 把 ≥20 件衣物走完管线到 ready。
2. 设置页「衣物向量索引」卡点「立即同步」，直到已索引 N / N。
3. 跑 `docker compose exec backend python -m scripts.embedding_probe --user-email <邮箱>`（退出码 0/1/2/3/4 含义见上方判读标准）；再加 `--instruction "Find the catalogue photo of this garment"` 做 A/B，据此裁定 Ruling 98（查询侧指令开或关）。
4. 挑 2–3 张真实穿搭照，逐个框好衣物框点「AI 建议」，并用 `--pair 裁块图:衣物UUID` 记录余弦。
5. 把 #39 从 ⚠️ 改为 ✅，或记录发现的问题。

附加检查项（Ruling 95 / 终审 I1）：点「AI 建议」后立刻「取消」，确认后端停止继续复判（看 backend 日志不再出现后续分组的视觉调用）。代理路由已转发 `request.signal`，但 Next 14 是否把客户端断开传成 abort 无法在容器内验证，只能在此处实测；若不传播，需把 Ruling 95 的代价改为「取消只丢弃客户端结果，后端会跑完剩余分组」。
