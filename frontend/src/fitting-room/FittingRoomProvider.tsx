"use client";

import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";

import type { OutfitSlot } from "./categoryMap";
import {
  createInitialState,
  fittingRoomReducer,
  type FittingRoomState,
} from "./fittingRoomState";
import type {
  ColorVariation,
  FittingRoomProduct,
  FittingRoomResponse,
  MannequinGender,
} from "./types";

interface FittingRoomContextValue {
  state: FittingRoomState;
  initFromResponse: (response: FittingRoomResponse) => void;
  setMannequin: (gender: MannequinGender) => void;
  selectProduct: (product: FittingRoomProduct) => void;
  selectVariation: (slot: OutfitSlot, variation: ColorVariation) => void;
  clearSlot: (slot: OutfitSlot) => void;
}

const FittingRoomContext = createContext<FittingRoomContextValue | null>(null);

export function FittingRoomProvider({
  initialMannequin,
  children,
}: {
  initialMannequin: MannequinGender;
  children: ReactNode;
}) {
  const [state, dispatch] = useReducer(fittingRoomReducer, initialMannequin, createInitialState);

  const value = useMemo<FittingRoomContextValue>(
    () => ({
      state,
      initFromResponse: (response) => dispatch({ type: "INIT_FROM_RESPONSE", response }),
      setMannequin: (gender) => dispatch({ type: "SET_MANNEQUIN", gender }),
      selectProduct: (product) => dispatch({ type: "SELECT_PRODUCT", product }),
      selectVariation: (slot, variation) => dispatch({ type: "SELECT_VARIATION", slot, variation }),
      clearSlot: (slot) => dispatch({ type: "CLEAR_SLOT", slot }),
    }),
    [state],
  );

  return <FittingRoomContext.Provider value={value}>{children}</FittingRoomContext.Provider>;
}

export function useFittingRoom(): FittingRoomContextValue {
  const ctx = useContext(FittingRoomContext);
  if (ctx === null) {
    throw new Error("useFittingRoom must be used inside <FittingRoomProvider>");
  }
  return ctx;
}