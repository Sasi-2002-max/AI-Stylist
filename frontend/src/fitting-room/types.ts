/**
 * Fitting-room types (Part 44).
 *
 * These mirror the Part 43 FittingRoomResponse contract exactly.
 * Nullable backend fields (Optional[...] in Pydantic) arrive as `null`.
 * THE REAL RETAILER PRODUCT IS THE SOURCE OF TRUTH: nothing here is
 * invented on the frontend.
 */

export type MannequinGender = "female" | "male";

export interface FittingRoomMannequin {
  gender: MannequinGender;
  asset: string;
}

export interface FittingRoomProduct {
  product_id: string;
  store: string;
  brand: string;
  title: string;
  category: string;
  color: string | null;
  price: number;
  currency: string;
  sizes: string[];
  image_url: string | null;
  product_url: string;
  availability: boolean;
}

export interface ColorVariation {
  product_id: string;
  color: string | null;
  image_url: string | null;
  product_url: string;
  price: number;
  currency: string;
}

export interface SelectedProductRef {
  product_id: string;
  category: string;
  item_index: number;
}

export interface MissingItem {
  [key: string]: unknown;
}

export interface OutfitSummary {
  status: string;
  selected_products: SelectedProductRef[];
  total_price: number;
  missing_items: MissingItem[];
}

export interface FittingRoomItem {
  item_index: number;
  category: string;
  product: FittingRoomProduct | null;
  visual_source: "product_image" | null;
  color_variations: ColorVariation[];
  alternatives: FittingRoomProduct[];
  error: string | null;
}

export interface FittingRoomResponse {
  status: "ready" | "incomplete";
  mannequin: FittingRoomMannequin;
  outfit: OutfitSummary;
  items: FittingRoomItem[];
}