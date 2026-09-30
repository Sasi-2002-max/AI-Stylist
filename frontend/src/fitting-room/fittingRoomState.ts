/**
 * Fitting-room state (Part 44) -- pure, framework-free.
 *
 * No network access and no imports beyond types/category mapping: selecting
 * a product only changes which already-resolved backend product occupies a
 * slot. It never triggers a shopping call and never fabricates a product.
 */

import { isOutfitSlot, OUTFIT_SLOTS, slotForCategory, type OutfitSlot } from "./categoryMap";
import type {
  ColorVariation,
  FittingRoomProduct,
  FittingRoomResponse,
  MannequinGender,
} from "./types";

/** A slot holds a full product, or a real color variation (see notes). */
export type SelectedProduct = FittingRoomProduct | ColorVariation;

export type SelectedOutfit = { mannequin: MannequinGender } & Partial<
  Record<OutfitSlot, SelectedProduct>
>;

export type SkipReason = "unknown_category" | "product_missing" | "slot_conflict";

export interface SkippedItem {
  item_index: number;
  category: string;
  product_id: string | null;
  reason: SkipReason;
}

export interface FittingRoomState {
  /** Backend status at initialisation time; "empty" before any init. */
  backendStatus: "empty" | "ready" | "incomplete";
  selectedOutfit: SelectedOutfit;
  /** Backend items that could not be placed in a slot (never silent). */
  skipped: SkippedItem[];
}

export type FittingRoomAction =
  | { type: "INIT_FROM_RESPONSE"; response: FittingRoomResponse }
  | { type: "SET_MANNEQUIN"; gender: MannequinGender }
  | { type: "SELECT_PRODUCT"; product: FittingRoomProduct }
  | { type: "SELECT_VARIATION"; slot: OutfitSlot; variation: ColorVariation }
  | { type: "CLEAR_SLOT"; slot: OutfitSlot };

export function createInitialState(mannequin: MannequinGender): FittingRoomState {
  return {
    backendStatus: "empty",
    selectedOutfit: { mannequin },
    skipped: [],
  };
}

export function isFullProduct(product: SelectedProduct): product is FittingRoomProduct {
  return "title" in product;
}

function initFromResponse(response: FittingRoomResponse): FittingRoomState {
  const selectedOutfit: SelectedOutfit = { mannequin: response.mannequin.gender };
  const skipped: SkippedItem[] = [];

  for (const item of response.items) {
    const productId = item.product ? item.product.product_id : null;
    const slot = slotForCategory(item.category);

    if (slot === null) {
      skipped.push({
        item_index: item.item_index,
        category: item.category,
        product_id: productId,
        reason: "unknown_category",
      });
      continue;
    }
    if (item.product === null) {
      skipped.push({
        item_index: item.item_index,
        category: item.category,
        product_id: null,
        reason: "product_missing",
      });
      continue;
    }
    if (selectedOutfit[slot] !== undefined) {
      skipped.push({
        item_index: item.item_index,
        category: item.category,
        product_id: productId,
        reason: "slot_conflict",
      });
      continue;
    }
    // Same object reference as the backend response: nothing copied/altered.
    selectedOutfit[slot] = item.product;
  }

  return { backendStatus: response.status, selectedOutfit, skipped };
}

function withSlot(state: FittingRoomState, slot: OutfitSlot, value: SelectedProduct): FittingRoomState {
  return {
    ...state,
    selectedOutfit: { ...state.selectedOutfit, [slot]: value },
  };
}

export function fittingRoomReducer(
  state: FittingRoomState,
  action: FittingRoomAction,
): FittingRoomState {
  switch (action.type) {
    case "INIT_FROM_RESPONSE":
      return initFromResponse(action.response);

    case "SET_MANNEQUIN":
      if (state.selectedOutfit.mannequin === action.gender) return state;
      return {
        ...state,
        selectedOutfit: { ...state.selectedOutfit, mannequin: action.gender },
      };

    case "SELECT_PRODUCT": {
      const slot = slotForCategory(action.product.category);
      if (slot === null) return state; // unknown category: safe no-op
      return withSlot(state, slot, action.product);
    }

    case "SELECT_VARIATION": {
      if (!isOutfitSlot(action.slot)) return state; // guards untyped callers
      // The whole slot value becomes the real variation product.
      return withSlot(state, action.slot, action.variation);
    }

    case "CLEAR_SLOT": {
      if (state.selectedOutfit[action.slot] === undefined) return state;
      const selectedOutfit: SelectedOutfit = { ...state.selectedOutfit };
      delete selectedOutfit[action.slot];
      return { ...state, selectedOutfit };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------- selectors

export function getSelectedProduct(
  state: FittingRoomState,
  slot: OutfitSlot,
): SelectedProduct | undefined {
  return state.selectedOutfit[slot];
}

/** Occupied slots, in stable OUTFIT_SLOTS order. */
export function getSelectedSlots(state: FittingRoomState): OutfitSlot[] {
  return OUTFIT_SLOTS.filter((slot) => state.selectedOutfit[slot] !== undefined);
}