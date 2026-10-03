# 词表（可直接在此文档修改）

> 来源：grilling 共识（2026-10-02）。**这份文档是词表的人工编辑版**——增删改直接写在下面的表格里；
> 实现阶段会把它编译进 `backend/app/data/garment_vocabulary.json`（结构见文末），并生成前后端选择器列表。
> **风格/颜色/类型**在 UI 上也有「添加 / 改名 / 停用」；改动会**写回 JSON 并自动同步本表对应行**——本表始终是唯一编辑面。
> 类型只能在现有部位下加类别；颜色可加新色系/新具体色（**hex 必填**）。
>
> - **slug**：存库的稳定标识（英文，改中文名不改 slug）
> - **中文名**：UI 显示、AI 闭集输出的候选名
> - 标 ★ 的是新增项（不在现有 31 类型里），不想要直接删行
> - 你例子里的「上衣-背心」= 部位`上衣` + 类别`tank-top(背心)`；`vest` 译作「马甲」，避免和背心撞名

## 一、类型：部位 → 类别

### 上衣 `tops`

| slug | 中文名 | 备注 |
|------|--------|------|
| tank-top | 背心 | |
| shirt | 衬衫 | |
| vest | 马甲 | |
| sweater | 毛衣 | |
| bandeau | 抹胸 | ★ |
| polo | Polo衫 | |
| t-shirt | T恤 | |
| hoodie | 卫衣 | |
| top | 其他上衣 | 兜底 |

### 下装 `bottoms`

| slug | 中文名 | 备注 |
|------|--------|------|
| skirt | 半裙 | |
| pants | 长裤 | |
| shorts | 短裤 | |
| jeans | 牛仔裤 | |
| slacks | 西裤 | ★ |
| sweatpants | 运动裤 | ★ |
| bottom | 其他下装 | 兜底 |

### 连衣裙/套装 `dresses`

| slug | 中文名 | 备注 |
|------|--------|------|
| jumpskirt | 背心裙 | |
| slip-dress | 吊带裙 | ★ |
| dress | 连衣裙 | |
| suit | 套装 | |

### 外套 `outerwear`

| slug | 中文名 | 备注 |
|------|--------|------|
| coat | 大衣 | |
| trench | 风衣 | ★ |
| jacket | 夹克 | |
| cardigan | 开衫 | |
| blazer | 西装外套 | |
| down-jacket | 羽绒服 | ★ |

### 鞋袜 `footwear`

| slug | 中文名 | 备注 |
|------|--------|------|
| heels | 高跟鞋 | ★ |
| sandals | 凉鞋 | |
| shoes | 皮鞋 | |
| slippers | 拖鞋 | ★ |
| socks | 袜子 | |
| boots | 靴子 | |
| sneakers | 运动鞋 | |

### 配饰 `accessories`

| slug | 中文名 | 备注 |
|------|--------|------|
| bag | 包 | |
| tie | 领带 | |
| hat | 帽子 | |
| circle-lens | 美瞳 | ★ |
| watch | 手表 | ★ |
| scarf | 围巾 | |
| glasses | 眼镜 | ★ |
| belt | 腰带 | |
| accessories | 其他配饰 | 兜底 |

### 首饰 `jewelry`

| slug | 中文名 | 备注 |
|------|--------|------|
| ear-cuff | 耳骨夹 | ★ |
| earrings | 耳饰 | ★，含耳环/耳钉 |
| hair-accessory | 发饰 | ★ |
| ring | 戒指 | ★ |
| bracelet | 手链 | ★ |
| bangle | 手镯 | ★ |
| neck-ring | 项环 | ★ |
| necklace | 项链 | ★ |
| brooch | 胸针 | ★ |
| jewelry | 其他首饰 | 兜底 |

（★ = 新增类；`blouse`（女式衬衫）、`jumpsuit`（连体裤）已删（无旧数据、不需映射）；原 `subtype` 现称「**备注**」，继续做自由文本，如「V领」「牛仔」「高腰」——**不进词表**，AI 可给建议、可手改。）

## 二、颜色：色系 → 具体色

> 选色规则：**主色可多选、辅色可多选（可空）**，都从具体色里选；
> 色系由具体色自动推导（筛选/展示用），不单独存。
> 每个色系留一个「正X」兜底，避免"纯绿"无处安放。图案/花纹走现有 `pattern` 字段，不占颜色位。
> **排序**：**部位**按固定逻辑序（上衣→下装→连衣裙/套装→外套→鞋袜→配饰→首饰）；**部位内类别**按中文名拼音，**兜底（其他xx）垫底**；**色系**按固定色序（黑白灰→棕→红→橙黄→绿→蓝→紫→粉→金属）；**风格**按中文名拼音。色系**内部**：**正X 固定第一**、其余按**渐变**（明度亮→暗；橙黄系按色相黄→橙）；黑白灰/金属内部保持表序。文档与 UI 同序；新加入的插对应位置（类别插拼音位但不越过兜底，颜色插渐变位，风格插拼音位）。每系只有一个锚点正X（橙黄系=正黄，正橙排渐变位）。

### 黑白灰系 `neutral`

| slug | 中文名 | hex（可调） |
|------|--------|------|
| black | 黑 | `#1a1a1a` |
| white | 白 | `#f7f7f7` |
| gray | 灰 | `#9e9e9e` |
| dark-gray | 深灰 | `#5b5b5b` |
| light-gray | 浅灰 | `#c9c9c9` |
| off-white | 米白 | `#f2ede3` |

### 棕色系 `brown`

| slug | 中文名 | hex |
|------|--------|------|
| brown | 正棕 | `#6d4c41` |
| khaki | 卡其 | `#bfa882` |
| camel | 驼色 | `#c19a6b` |
| caramel | 焦糖 | `#a1663b` |
| coffee | 咖啡棕 | `#4e342e` |

### 红色系 `red`

| slug | 中文名 | hex |
|------|--------|------|
| red | 正红 | `#e60012` |
| cherry | 樱桃红 | `#b31c3f` |
| brick | 砖红 | `#a1422f` |
| wine | 酒红 | `#8a2b42` |
| dark-red | 深红 | `#3f0b12` |

### 橙黄系 `orange-yellow`

| slug | 中文名 | hex |
|------|--------|------|
| yellow | 正黄 | `#ffd600` |
| lemon | 柠檬黄 | `#f2e600` |
| cream | 米黄 | `#efe3c2` |
| ginger | 姜黄 | `#d29b2e` |
| pumpkin | 南瓜色 | `#f79433` |
| orange | 正橙 | `#ef6c00` |
| tangerine | 脏橘 | `#c26a3e` |

### 绿色系 `green`

| slug | 中文名 | hex |
|------|--------|------|
| green | 正绿 | `#2e7d32` |
| mint | 薄荷绿 | `#9adbc8` |
| avocado | 牛油果绿 | `#87a96b` |
| grass | 草绿 | `#7cb342` |
| olive | 橄榄绿 | `#6b7b3a` |
| army | 军绿 | `#4b5320` |
| dark-green | 墨绿 | `#1b4332` |

### 蓝色系 `blue`

| slug | 中文名 | hex |
|------|--------|------|
| blue | 正蓝 | `#1565c0` |
| sky | 天蓝 | `#64b5f6` |
| misty | 雾霾蓝 | `#8fa9bf` |
| royal | 宝蓝 | `#2456a5` |
| denim | 牛仔蓝 | `#3d5a80` |
| klein | 克莱因蓝 | `#002fa7` |
| navy | 藏青 | `#1b2a4a` |

### 紫色系 `purple`

| slug | 中文名 | hex |
|------|--------|------|
| purple | 正紫 | `#6a1b9a` |
| taro | 浅紫 | `#d2c5ef` |
| lavender | 薰衣草紫 | `#967bb6` |
| grape | 葡萄紫 | `#5e35b1` |

### 粉色系 `pink`

| slug | 中文名 | hex |
|------|--------|------|
| pink | 正粉 | `#f06292` |
| sakura | 樱花粉 | `#f8bbd0` |
| lotus | 藕粉 | `#d8a7b1` |
| coral | 珊瑚粉 | `#f08080` |
| rose | 玫红 | `#c2185b` |

### 金属系 `metallic`

| slug | 中文名 | hex |
|------|--------|------|
| gold | 金 | `#d4af37` |
| silver | 银 | `#c0c0c0` |

共 9 系 48 色。

## 三、季节 / 温度

| 项 | 值域 |
|----|------|
| 季节（衣物标签，多选，AI 打 + 手改） | `spring` 春 / `summer` 夏 / `fall` 秋 / `winter` 冬 / `all-season` 四季 |
| 温度（衣物属性） | 自由上下限两格数值（℃），如 12–22；不设档位 |
| 季节（穿搭记录） | **按记录日期自动推导**（3-5月春 / 6-9月夏 / 10-11月秋 / 12-2月冬），可手改 |

## 四、不动的部分

- `materials`（棉/麻/丝…15 项）、`formality`（6 级正式度）：沿用现有词表值，本次不改。
- 预设城市（杭州/香港/合肥/深圳）**不进词表**，放设置里（可扩展、可设默认城市）。

## 五、风格 `styles`（可随时增行）

> 软词表：**UI 选择器上有「添加」按钮可当场新建**；本表是种子（出厂默认），直接改表重编译也行。
> AI 打标签从当前列表（种子 + 运行时新增）闭集选，多选、可空。
> 下面是起手示例，可随意删改；与「正式度」互不占用（风格=气质取向，正式度=场合程度）。

| slug | 中文名 | 备注 |
|------|--------|------|
| three-pits | 泛三坑 | Lo、JK、汉服、新中式等 |
| retro | 复古 | |
| goth | 哥特 | |
| minimal | 极简 | |
| party | 派对 | |
| office | 上班 | |
| genderless | 无性别 | |
| casual | 休闲 | |
| alt | 亚比 | |
| elegant | 优雅 | |
| chinese | 中式 | |

## 六、实现时编译成的运行时结构（供参考，不用改）

```json
{
  "body_parts": [
    { "slug": "tops", "label": "上衣", "types": ["t-shirt", "shirt", "..."] }
  ],
  "types": [
    { "slug": "tank-top", "label": "背心", "body_part": "tops", "role": "base_top", "wash_interval": 2 }
  ],
  "colors": {
    "families": [{ "slug": "green", "label": "绿色系" }],
    "values": [
      { "slug": "army", "label": "军绿", "family": "green", "hex": "#4b5320" }
    ]
  },
  "seasons": ["spring", "summer", "fall", "winter", "all-season"],
  "styles": [{ "slug": "casual", "label": "休闲" }],
  "materials": [],
  "formality": []
}
```
