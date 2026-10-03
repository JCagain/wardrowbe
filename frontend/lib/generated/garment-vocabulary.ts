// Generated from backend/app/data/garment_vocabulary.json by scripts/gen-garment-vocabulary.mjs.
// Do not edit by hand; run `npm run vocab:gen`.
export const CLOTHING_TYPE_VALUES = ['jumpskirt', 'slip-dress', 'dress', 'suit', 'bag', 'tie', 'hat', 'accessories', 'watch', 'scarf', 'glasses', 'belt', 'tank-top', 'shirt', 'vest', 'sweater', 'bandeau', 'polo', 'top', 't-shirt', 'hoodie', 'earrings', 'ring', 'jewelry', 'bracelet', 'bangle', 'necklace', 'brooch', 'coat', 'trench', 'jacket', 'cardigan', 'blazer', 'down-jacket', 'skirt', 'pants', 'shorts', 'jeans', 'bottom', 'slacks', 'sweatpants', 'heels', 'sandals', 'shoes', 'slippers', 'socks', 'boots', 'sneakers'] as const;
export const MATERIAL_VALUES = ['cotton', 'denim', 'leather', 'wool', 'polyester', 'silk', 'linen', 'knit', 'fleece', 'suede', 'velvet', 'nylon', 'canvas', 'down', 'shearling'] as const;
export const FORMALITY_VALUES = ['very-casual', 'casual', 'smart-casual', 'business-casual', 'formal', 'very-formal'] as const;
export const BODY_PART_VALUES = ['dresses', 'accessories', 'tops', 'jewelry', 'outerwear', 'bottoms', 'footwear'] as const;
export const SEASON_VALUES = ['spring', 'summer', 'fall', 'winter', 'all-season'] as const;
export const STYLE_VALUES = ['three-pits', 'retro', 'goth', 'minimal', 'party', 'office', 'casual', 'alt', 'elegant', 'chinese', 'androgynous'] as const;
export const COLOR_FAMILY_VALUES = ['orange-yellow', 'pink', 'neutral', 'red', 'metallic', 'blue', 'green', 'purple', 'brown'] as const;
export const TYPE_ENTRIES = [{"value":"jumpskirt","label":"背心裙","body_part":"dresses"},{"value":"slip-dress","label":"吊带裙","body_part":"dresses"},{"value":"dress","label":"连衣裙","body_part":"dresses"},{"value":"suit","label":"套装","body_part":"dresses"},{"value":"bag","label":"包","body_part":"accessories"},{"value":"tie","label":"领带","body_part":"accessories"},{"value":"hat","label":"帽子","body_part":"accessories"},{"value":"accessories","label":"其他配饰","body_part":"accessories"},{"value":"watch","label":"手表","body_part":"accessories"},{"value":"scarf","label":"围巾","body_part":"accessories"},{"value":"glasses","label":"眼镜","body_part":"accessories"},{"value":"belt","label":"腰带","body_part":"accessories"},{"value":"tank-top","label":"背心","body_part":"tops"},{"value":"shirt","label":"衬衫","body_part":"tops"},{"value":"vest","label":"马甲","body_part":"tops"},{"value":"sweater","label":"毛衣","body_part":"tops"},{"value":"bandeau","label":"抹胸","body_part":"tops"},{"value":"polo","label":"Polo衫","body_part":"tops"},{"value":"top","label":"其他上衣","body_part":"tops"},{"value":"t-shirt","label":"T恤","body_part":"tops"},{"value":"hoodie","label":"卫衣","body_part":"tops"},{"value":"earrings","label":"耳饰","body_part":"jewelry"},{"value":"ring","label":"戒指","body_part":"jewelry"},{"value":"jewelry","label":"其他首饰","body_part":"jewelry"},{"value":"bracelet","label":"手链","body_part":"jewelry"},{"value":"bangle","label":"手镯","body_part":"jewelry"},{"value":"necklace","label":"项链","body_part":"jewelry"},{"value":"brooch","label":"胸针","body_part":"jewelry"},{"value":"coat","label":"大衣","body_part":"outerwear"},{"value":"trench","label":"风衣","body_part":"outerwear"},{"value":"jacket","label":"夹克","body_part":"outerwear"},{"value":"cardigan","label":"开衫","body_part":"outerwear"},{"value":"blazer","label":"西装外套","body_part":"outerwear"},{"value":"down-jacket","label":"羽绒服","body_part":"outerwear"},{"value":"skirt","label":"半裙","body_part":"bottoms"},{"value":"pants","label":"长裤","body_part":"bottoms"},{"value":"shorts","label":"短裤","body_part":"bottoms"},{"value":"jeans","label":"牛仔裤","body_part":"bottoms"},{"value":"bottom","label":"其他下装","body_part":"bottoms"},{"value":"slacks","label":"西裤","body_part":"bottoms"},{"value":"sweatpants","label":"运动裤","body_part":"bottoms"},{"value":"heels","label":"高跟鞋","body_part":"footwear"},{"value":"sandals","label":"凉鞋","body_part":"footwear"},{"value":"shoes","label":"皮鞋","body_part":"footwear"},{"value":"slippers","label":"拖鞋","body_part":"footwear"},{"value":"socks","label":"袜子","body_part":"footwear"},{"value":"boots","label":"靴子","body_part":"footwear"},{"value":"sneakers","label":"运动鞋","body_part":"footwear"}] as const;
export const COLOR_VALUES = [{"value":"yellow","label":"正黄","family":"orange-yellow","hex":"#ffd600"},{"value":"lemon","label":"柠檬黄","family":"orange-yellow","hex":"#f2e600"},{"value":"cream","label":"米黄","family":"orange-yellow","hex":"#efe3c2"},{"value":"ginger","label":"姜黄","family":"orange-yellow","hex":"#d29b2e"},{"value":"pumpkin","label":"南瓜色","family":"orange-yellow","hex":"#f79433"},{"value":"orange","label":"正橙","family":"orange-yellow","hex":"#ef6c00"},{"value":"tangerine","label":"脏橘","family":"orange-yellow","hex":"#c26a3e"},{"value":"pink","label":"正粉","family":"pink","hex":"#f06292"},{"value":"sakura","label":"樱花粉","family":"pink","hex":"#f8bbd0"},{"value":"lotus","label":"藕粉","family":"pink","hex":"#d8a7b1"},{"value":"coral","label":"珊瑚粉","family":"pink","hex":"#f08080"},{"value":"rose","label":"玫红","family":"pink","hex":"#c2185b"},{"value":"white","label":"白","family":"neutral","hex":"#f7f7f7"},{"value":"black","label":"黑","family":"neutral","hex":"#1a1a1a"},{"value":"gray","label":"灰","family":"neutral","hex":"#9e9e9e"},{"value":"off-white","label":"米白","family":"neutral","hex":"#f2ede3"},{"value":"light-gray","label":"浅灰","family":"neutral","hex":"#c9c9c9"},{"value":"dark-gray","label":"深灰","family":"neutral","hex":"#5b5b5b"},{"value":"red","label":"正红","family":"red","hex":"#e60012"},{"value":"cherry","label":"樱桃红","family":"red","hex":"#b31c3f"},{"value":"brick","label":"砖红","family":"red","hex":"#a1422f"},{"value":"wine","label":"酒红","family":"red","hex":"#8a2b42"},{"value":"dark-red","label":"深红","family":"red","hex":"#3f0b12"},{"value":"gold","label":"金","family":"metallic","hex":"#d4af37"},{"value":"silver","label":"银","family":"metallic","hex":"#c0c0c0"},{"value":"blue","label":"正蓝","family":"blue","hex":"#1565c0"},{"value":"sky","label":"天蓝","family":"blue","hex":"#64b5f6"},{"value":"misty","label":"雾霾蓝","family":"blue","hex":"#8fa9bf"},{"value":"royal","label":"宝蓝","family":"blue","hex":"#2456a5"},{"value":"denim","label":"牛仔蓝","family":"blue","hex":"#3d5a80"},{"value":"klein","label":"克莱因蓝","family":"blue","hex":"#002fa7"},{"value":"navy","label":"藏青","family":"blue","hex":"#1b2a4a"},{"value":"green","label":"正绿","family":"green","hex":"#2e7d32"},{"value":"mint","label":"薄荷绿","family":"green","hex":"#9adbc8"},{"value":"avocado","label":"牛油果绿","family":"green","hex":"#87a96b"},{"value":"grass","label":"草绿","family":"green","hex":"#7cb342"},{"value":"olive","label":"橄榄绿","family":"green","hex":"#6b7b3a"},{"value":"army","label":"军绿","family":"green","hex":"#4b5320"},{"value":"dark-green","label":"墨绿","family":"green","hex":"#1b4332"},{"value":"purple","label":"正紫","family":"purple","hex":"#6a1b9a"},{"value":"taro","label":"浅紫","family":"purple","hex":"#d2c5ef"},{"value":"lavender","label":"薰衣草紫","family":"purple","hex":"#967bb6"},{"value":"grape","label":"葡萄紫","family":"purple","hex":"#5e35b1"},{"value":"brown","label":"正棕","family":"brown","hex":"#6d4c41"},{"value":"khaki","label":"卡其","family":"brown","hex":"#bfa882"},{"value":"camel","label":"驼色","family":"brown","hex":"#c19a6b"},{"value":"caramel","label":"焦糖","family":"brown","hex":"#a1663b"},{"value":"coffee","label":"咖啡棕","family":"brown","hex":"#4e342e"}] as const;
export const STYLE_LABELS = {"three-pits":"泛三坑","retro":"复古","goth":"哥特","minimal":"极简","party":"派对","office":"上班","casual":"休闲","alt":"亚比","elegant":"优雅","chinese":"中式","androgynous":"中性"} as const;

export const ITEM_ROLE: Record<string, string> = {
  jumpskirt: 'full_body',
  'slip-dress': 'full_body',
  dress: 'full_body',
  suit: 'suit',
  bag: 'accessory',
  tie: 'neckwear',
  hat: 'accessory',
  accessories: 'accessory',
  watch: 'accessory',
  scarf: 'accessory',
  glasses: 'accessory',
  belt: 'accessory',
  'tank-top': 'base_top',
  shirt: 'base_top',
  vest: 'mid_layer',
  sweater: 'base_top',
  bandeau: 'base_top',
  polo: 'base_top',
  top: 'base_top',
  't-shirt': 'base_top',
  hoodie: 'outer_layer',
  earrings: 'accessory',
  ring: 'accessory',
  jewelry: 'accessory',
  bracelet: 'accessory',
  bangle: 'accessory',
  necklace: 'accessory',
  brooch: 'accessory',
  coat: 'outer_layer',
  trench: 'outer_layer',
  jacket: 'outer_layer',
  cardigan: 'mid_layer',
  blazer: 'outer_layer',
  'down-jacket': 'outer_layer',
  skirt: 'bottom',
  pants: 'bottom',
  shorts: 'bottom',
  jeans: 'bottom',
  bottom: 'bottom',
  slacks: 'bottom',
  sweatpants: 'bottom',
  heels: 'footwear',
  sandals: 'footwear',
  shoes: 'footwear',
  slippers: 'footwear',
  socks: 'socks',
  boots: 'footwear',
  sneakers: 'footwear',
};
