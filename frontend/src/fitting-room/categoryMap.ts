/**
 * Deterministic mapping: backend category -> frontend outfit slot.
 *
 * Exact, case-sensitive matching. Unknown categories return null and are
 * never silently mapped to another slot.
 */

export const OUTFIT_SLOTS = [
  "shirt",
  "t_shirt",
  "top",
  "pants",
  "jeans",
  "skirt",
  "dress",
  "shoes",
  "watch",
  "sunglasses",
  "bag",
  "accessory",
] as const;

export type OutfitSlot = (typeof OUTFIT_SLOTS)[number];

const CATEGORY_TO_SLOT: Readonly<Record<string, OutfitSlot>> = {
  shirts: "shirt",
  "t-shirts": "t_shirt",
  tops: "top",
  pants: "pants",
  jeans: "jeans",
  skirts: "skirt",
  dresses: "dress",
  shoes: "shoes",
  watches: "watch",
  sunglasses: "sunglasses",
  bags: "bag",
  accessories: "accessory",
};

export function slotForCategory(category: string): OutfitSlot | null {
  // hasOwnProperty guards against keys like "constructor" / "__proto__".
  return Object.prototype.hasOwnProperty.call(CATEGORY_TO_SLOT, category)
    ? CATEGORY_TO_SLOT[category]
    : null;
}

export function isOutfitSlot(value: string): value is OutfitSlot {
  return (OUTFIT_SLOTS as readonly string[]).includes(value);
}