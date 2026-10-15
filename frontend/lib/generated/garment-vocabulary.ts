// Generated from backend/app/data/garment_vocabulary.json by scripts/gen-garment-vocabulary.mjs.
// Do not edit by hand; run `npm run vocab:gen`.
export const BODY_PART_VALUES = ['tops', 'bottoms', 'dresses', 'outerwear', 'footwear', 'accessories', 'jewelry'] as const;
export const BODY_PART_LABELS = {"tops":"上衣","bottoms":"下装","dresses":"连衣裙/套装","outerwear":"外套","footwear":"鞋袜","accessories":"配饰","jewelry":"首饰"} as const;
export const SEASON_VALUES = ['spring', 'summer', 'fall', 'winter', 'all-season'] as const;
export const MATERIAL_VALUES = ['cotton', 'denim', 'leather', 'wool', 'polyester', 'silk', 'linen', 'knit', 'fleece', 'suede', 'velvet', 'nylon', 'canvas', 'down', 'shearling'] as const;
export const FORMALITY_VALUES = ['very-casual', 'casual', 'smart-casual', 'business-casual', 'formal', 'very-formal'] as const;

export type BodyPart = (typeof BODY_PART_VALUES)[number];
export type Season = (typeof SEASON_VALUES)[number];
export type Material = (typeof MATERIAL_VALUES)[number];
export type Formality = (typeof FORMALITY_VALUES)[number];
