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
| 17 / 18 | 打标闭集：颜色/风格/季节/类型从在役词表渲染（slug=中文名）；AI 输出 primary_colors[] + secondary_colors[] 直写列 | ✅ | c72a00d, e132635, d60185b, 940ff90, c17f3b1, 039648f, COMMIT4 |

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
| **Ruling 45** | 单张与批量上传两条路径都不再自动入队 `tag_item_image`（含批量只为自动打标而建的 redis 池）；`skip_ai` 入参保留但不起作用（D2 兼容）。 |
| **Ruling 46** | 上传后 `mark_pending(set_ready=True)`：status=ready、tagging_status=pending（`set_ready=False` 会让物品卡在 processing）。 |
| **Ruling 47** | 白底合成图是临时产物：写系统临时目录、不进存储目录，`analysis_input()` 在 `finally` 里删除。 |
| **Ruling 48** | `tag_item_image` 从 DB 行（`image_path`/`mask_path`）经 `resolve_analysis_path` 取输入，不信入队时的 `image_path` 参数（保留仅为队列兼容）；存在性检查针对解析后的工作图。 |
| **Ruling 49** | 前端步骤条「打标」改调 `useReanalyzeItem`（`POST /items/{id}/analyze`）：queued/already_queued → 已入队提示；deferred（视觉未启用）与 cooldown → 信息提示；出错 → 错误提示。`useRetagItem` 保留（仅 hook 定义，无调用方）。 |
| **Ruling 51** | 校色端点（detect/apply/manual/reset）在 `calibration_original_path` 为 NULL 时惰性补种 `_src`（`ImageService.ensure_calibration_source`）并落列：盘上已有且尺寸吻合 → 原样收养；否则有尺寸吻合的 `_orig` 备份 → 取备份像素；否则取工作图转 RGB（JPEG q95）；已有但尺寸不符 → 告警后覆盖。取代原先的 400 "no calibration source"。 |
| **Ruling 52** | `calibration/detect` 读校色副本 `_src`，不读工作图：抠图后工作图背景 RGB 已清零，卡条是黑的，永远检不出。 |
| **Ruling 53** | 详情对话框在旋转 / 还原原图 / 替换主图 / 设为主图成功后清掉旧检出框（`pending` 退回 `none`）；`restore-original` 补上与 remove-background / mask 同款的「后台 job 在跑 → 409」守卫。 |
| **Ruling 55** | 提示词候选写成 `slug=中文名`，解析取 `=` 左侧；停用条目不进提示词、AI 回了也丢弃，但不影响旧物品的历史值与手改。 |
| **Ruling 56** | AI 仍回旧 `primary_color` / `colors` 时按字段走旧键兼容解析；`tags` blob 自 2026-10-14 起写新键（`primary_colors` / `secondary_colors`），旧键只读兼容。 |
| **Ruling 57** | `tags` blob 的颜色投影按列进行：只有过滤后非空的值才写入，空不等于清空；新指派主色而无可用辅色时，从现有辅色里剔除与新主色重叠的颜色。 |
| **Ruling 58** | `pattern` / `fit` 仍是代码内固定集合（spec §1.4 输出清单不含二者，不在本次闭集化范围）。 |
| **Ruling 42**（录入页步骤条） | 录入页还没有物品，步骤条只作指引：`interactive={false}`，状态 span，无操作按钮。 |
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
