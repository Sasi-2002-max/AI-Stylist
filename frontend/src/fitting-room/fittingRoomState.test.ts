import { afterEach, describe, expect, it, vi } from "vitest";

import { slotForCategory } from "./categoryMap";
import {
  createInitialState,
  fittingRoomReducer,
  getSelectedProduct,
  getSelectedSlots,
  isFullProduct,
  type FittingRoomAction,
  type FittingRoomState,
} from "./fittingRoomState";
import type {
  ColorVariation,
  FittingRoomItem,
  FittingRoomProduct,
  FittingRoomResponse,
  MannequinGender,
} from "./types";

// ---- TEST FIXTURE DATA ONLY (not a catalog) --------------------------------

function product(o: Partial<FittingRoomProduct> & { product_id: string }): FittingRoomProduct {
  return {
    store: "Demo Fashion",
    brand: "Urban Weave",
    title: `Item ${o.product_id}`,
    category: "shirts",
    color: "black",
    price: 1000,
    currency: "INR",
    sizes: ["M"],
    image_url: `https://example.test/${o.product_id}.jpg`,
    product_url: `https://example.test/${o.product_id}`,
    availability: true,
    ...o,
  };
}

const SHIRT = product({ product_id: "MOCK001", category: "shirts", title: "Black Oxford Shirt", price: 1299 });
const PANTS = product({ product_id: "MOCK014", category: "pants", color: "cream" });
const SHOES = product({ product_id: "MOCK027", category: "shoes", color: "brown", image_url: null });
const WATCH = product({ product_id: "MOCK040", category: "watches", color: "silver" });
const ALT_SHIRT = product({ product_id: "MOCK002", category: "shirts", color: "blue" });
const ALT_SHOES = product({ product_id: "MOCK031", category: "shoes", color: "black" });

const WHITE_VARIATION: ColorVariation = {
  product_id: "MOCK001-WHITE",
  color: "white",
  image_url: "https://example.test/MOCK001-WHITE.jpg",
  product_url: "https://example.test/MOCK001-WHITE",
  price: 1299,
  currency: "INR",
};

function item(index: number, category: string, p: FittingRoomProduct | null, error: string | null = null): FittingRoomItem {
  return {
    item_index: index,
    category,
    product: p,
    visual_source: p && p.image_url ? "product_image" : null,
    color_variations: [],
    alternatives: [],
    error,
  };
}

function response(
  items: FittingRoomItem[],
  gender: MannequinGender = "female",
  status: "ready" | "incomplete" = "ready",
): FittingRoomResponse {
  return {
    status,
    mannequin: { gender, asset: `assets/fitting-room/${gender}-mannequin.png` },
    outfit: {
      status: status === "ready" ? "complete" : "incomplete",
      selected_products: items.map((i) => ({
        product_id: i.product?.product_id ?? "",
        category: i.category,
        item_index: i.item_index,
      })),
      total_price: 0,
      missing_items: [],
    },
    items,
  };
}

const FULL = response([
  item(0, "shirts", SHIRT),
  item(1, "pants", PANTS),
  item(2, "shoes", SHOES),
]);

function initial(gender: MannequinGender = "female", r: FittingRoomResponse = FULL): FittingRoomState {
  return fittingRoomReducer(createInitialState(gender), { type: "INIT_FROM_RESPONSE", response: r });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---- tests -----------------------------------------------------------------

describe("initialisation from a Part 43 response", () => {
  it("1. initialises state from the response", () => {
    const s = initial();
    expect(s.backendStatus).toBe("ready");
    expect(s.selectedOutfit.shirt).toBe(SHIRT);
    expect(s.selectedOutfit.pants).toBe(PANTS);
    expect(s.selectedOutfit.shoes).toBe(SHOES);
    expect(s.skipped).toEqual([]);
  });

  it("2. preserves the female mannequin", () => {
    expect(initial("male", response([item(0, "shirts", SHIRT)], "female")).selectedOutfit.mannequin).toBe("female");
  });

  it("3. preserves the male mannequin", () => {
    expect(initial("female", response([item(0, "shirts", SHIRT)], "male")).selectedOutfit.mannequin).toBe("male");
  });

  it("supports switching the mannequin without touching products", () => {
    const s = initial();
    const next = fittingRoomReducer(s, { type: "SET_MANNEQUIN", gender: "male" });
    expect(next.selectedOutfit.mannequin).toBe("male");
    expect(next.selectedOutfit.shirt).toBe(SHIRT);
    expect(next.selectedOutfit.pants).toBe(PANTS);
    expect(next.selectedOutfit.shoes).toBe(SHOES);
  });

  it("keeps an incomplete backend status; does not upgrade it", () => {
    expect(initial("female", response([item(0, "shirts", SHIRT)], "female", "incomplete")).backendStatus).toBe("incomplete");
  });
});

describe("selecting products", () => {
  it("4. shirt selection works", () => {
    const s = fittingRoomReducer(createInitialState("female"), { type: "SELECT_PRODUCT", product: SHIRT });
    expect(getSelectedProduct(s, "shirt")).toBe(SHIRT);
  });

  it("5. pants selection works", () => {
    const s = fittingRoomReducer(createInitialState("female"), { type: "SELECT_PRODUCT", product: PANTS });
    expect(getSelectedProduct(s, "pants")).toBe(PANTS);
  });

  it("6. shoes selection works", () => {
    const s = fittingRoomReducer(createInitialState("female"), { type: "SELECT_PRODUCT", product: SHOES });
    expect(getSelectedProduct(s, "shoes")).toBe(SHOES);
  });

  it("7. watch selection works", () => {
    const s = fittingRoomReducer(createInitialState("female"), { type: "SELECT_PRODUCT", product: WATCH });
    expect(getSelectedProduct(s, "watch")).toBe(WATCH);
  });

  it("8. replacing a shirt does not modify pants or shoes", () => {
    const s = fittingRoomReducer(initial(), { type: "SELECT_PRODUCT", product: ALT_SHIRT });
    expect(s.selectedOutfit.shirt).toBe(ALT_SHIRT);
    expect(s.selectedOutfit.pants).toBe(PANTS);
    expect(s.selectedOutfit.shoes).toBe(SHOES);
  });

  it("9. replacing pants does not modify the shirt", () => {
    const otherPants = product({ product_id: "MOCK015", category: "pants" });
    const s = fittingRoomReducer(initial(), { type: "SELECT_PRODUCT", product: otherPants });
    expect(s.selectedOutfit.pants).toBe(otherPants);
    expect(s.selectedOutfit.shirt).toBe(SHIRT);
    expect(s.selectedOutfit.shoes).toBe(SHOES);
  });

  it("10. replacing shoes does not modify shirt or pants (sequence from the spec)", () => {
    let s = fittingRoomReducer(initial(), { type: "SELECT_PRODUCT", product: ALT_SHIRT });
    s = fittingRoomReducer(s, { type: "SELECT_PRODUCT", product: ALT_SHOES });
    expect(s.selectedOutfit).toEqual({
      mannequin: "female",
      shirt: ALT_SHIRT,
      pants: PANTS,
      shoes: ALT_SHOES,
    });
    expect(s.selectedOutfit.pants).toBe(PANTS);
  });

  it("does not mutate the previous state", () => {
    const before = initial();
    const snapshot = { ...before.selectedOutfit };
    fittingRoomReducer(before, { type: "SELECT_PRODUCT", product: ALT_SHIRT });
    expect(before.selectedOutfit).toEqual(snapshot);
  });
});

describe("clearing", () => {
  it("11. clearing a category works and leaves the others", () => {
    const s = fittingRoomReducer(initial(), { type: "CLEAR_SLOT", slot: "shirt" });
    expect(getSelectedProduct(s, "shirt")).toBeUndefined();
    expect("shirt" in s.selectedOutfit).toBe(false);
    expect(s.selectedOutfit.pants).toBe(PANTS);
    expect(s.selectedOutfit.shoes).toBe(SHOES);
    expect(getSelectedSlots(s)).toEqual(["pants", "shoes"]);
  });

  it("clearing an empty slot returns the same state", () => {
    const s = initial();
    expect(fittingRoomReducer(s, { type: "CLEAR_SLOT", slot: "watch" })).toBe(s);
  });
});

describe("real product data is preserved", () => {
  it("12-14. product_id, image_url and product_url are unchanged", () => {
    const s = initial();
    const shirt = getSelectedProduct(s, "shirt")!;
    expect(shirt.product_id).toBe("MOCK001");
    expect(shirt.image_url).toBe("https://example.test/MOCK001.jpg");
    expect(shirt.product_url).toBe("https://example.test/MOCK001");
  });

  it("keeps image_url null instead of inventing one", () => {
    expect(getSelectedProduct(initial(), "shoes")!.image_url).toBeNull();
  });

  it("preserves every product field exactly", () => {
    const shirt = getSelectedProduct(initial(), "shirt")!;
    expect(shirt).toEqual(SHIRT);
    expect(isFullProduct(shirt)).toBe(true);
  });
});

describe("color variations", () => {
  it("15. selecting a real variation replaces the entire product reference", () => {
    const s = fittingRoomReducer(initial(), {
      type: "SELECT_VARIATION",
      slot: "shirt",
      variation: WHITE_VARIATION,
    });
    const shirt = getSelectedProduct(s, "shirt")!;
    expect(shirt).toBe(WHITE_VARIATION);
    expect(shirt.product_id).toBe("MOCK001-WHITE");
    expect(shirt.image_url).toBe(WHITE_VARIATION.image_url);
    expect(shirt.product_url).toBe(WHITE_VARIATION.product_url);
    expect(shirt.product_id).not.toBe(SHIRT.product_id);
    expect(isFullProduct(shirt)).toBe(false); // no fabricated title/brand
    expect("title" in shirt).toBe(false);
    // only the shirt slot changed
    expect(s.selectedOutfit.pants).toBe(PANTS);
    expect(s.selectedOutfit.shoes).toBe(SHOES);
  });
});

describe("unknown / unplaceable backend data", () => {
  it.each(["hats", "Shirts", "constructor", "__proto__", ""])(
    "16. category %j maps to no slot",
    (category) => {
      expect(slotForCategory(category)).toBeNull();
    },
  );

  it("16. unknown categories on init are recorded, never remapped", () => {
    const hat = product({ product_id: "MOCK099", category: "hats" });
    const s = initial("female", response([item(0, "shirts", SHIRT), item(1, "hats", hat)]));
    expect(getSelectedSlots(s)).toEqual(["shirt"]);
    expect(s.skipped).toEqual([
      { item_index: 1, category: "hats", product_id: "MOCK099", reason: "unknown_category" },
    ]);
  });

  it("16. selecting an unknown-category product is a no-op", () => {
    const s = initial();
    const hat = product({ product_id: "MOCK099", category: "hats" });
    expect(fittingRoomReducer(s, { type: "SELECT_PRODUCT", product: hat })).toBe(s);
  });

  it("18. a product_not_found item is skipped, not fabricated", () => {
    const s = initial(
      "female",
      response([item(0, "shirts", null, "product_not_found"), item(1, "pants", PANTS)]),
    );
    expect(getSelectedProduct(s, "shirt")).toBeUndefined();
    expect(s.skipped).toEqual([
      { item_index: 0, category: "shirts", product_id: null, reason: "product_missing" },
    ]);
    expect(s.selectedOutfit.pants).toBe(PANTS);
  });

  it("a second item for an occupied slot is recorded as slot_conflict", () => {
    const s = initial("female", response([item(0, "shirts", SHIRT), item(1, "shirts", ALT_SHIRT)]));
    expect(s.selectedOutfit.shirt).toBe(SHIRT);
    expect(s.skipped[0].reason).toBe("slot_conflict");
  });
});

describe("no shopping calls, no fake products", () => {
  it("17. no network call happens in any state operation", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const actions: FittingRoomAction[] = [
      { type: "INIT_FROM_RESPONSE", response: FULL },
      { type: "SET_MANNEQUIN", gender: "male" },
      { type: "SELECT_PRODUCT", product: ALT_SHIRT },
      { type: "SELECT_VARIATION", slot: "shirt", variation: WHITE_VARIATION },
      { type: "CLEAR_SLOT", slot: "pants" },
    ];
    let s = createInitialState("female");
    for (const a of actions) s = fittingRoomReducer(s, a);

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("18. every selected product is exactly an object the backend supplied", () => {
    const s = initial();
    const supplied = new Set<unknown>(FULL.items.map((i) => i.product));
    for (const slot of getSelectedSlots(s)) {
      expect(supplied.has(getSelectedProduct(s, slot))).toBe(true);
    }
    expect(Object.keys(s.selectedOutfit).sort()).toEqual(["mannequin", "pants", "shirt", "shoes"]);
  });
});