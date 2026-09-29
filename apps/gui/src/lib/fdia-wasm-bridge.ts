/**
 * fdia-wasm-bridge.ts
 *
 * Safe wrapper around @delentia/fdia-wasm.
 * Falls back to JS computation if WASM fails to load
 * (e.g., in SSR / test environments where WASM is unavailable).
 */

import type { FDIAScore } from "./types";

type FdiaWasmModule = {
  compute_fdia: (D: number, I: number, A: number) => number;
  verify_signature: (hash: string, signature: string) => boolean;
};

let wasmModule: FdiaWasmModule | null = null;

/** Lazy-load the WASM module (client-side only) */
async function getWasmModule(): Promise<FdiaWasmModule | null> {
  if (wasmModule) return wasmModule;
  if (typeof window === "undefined") return null; // SSR guard

  try {
    // Dynamic import — bundler resolves at runtime
    const mod = await import("@delentia/fdia-wasm");
    wasmModule = mod as unknown as FdiaWasmModule;
    return wasmModule;
  } catch {
    console.warn("[FDIA WASM] Module unavailable — using JS fallback");
    return null;
  }
}

/** JS fallback: F = D^I × A (matches WASM implementation) */
function computeFDIAjs(D: number, I: number, A: number): number {
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  return Math.pow(clamp(D), clamp(I)) * clamp(A);
}

/**
 * Compute FDIA score, preferring WASM acceleration.
 * Always returns a valid FDIAScore (never throws).
 */
export async function computeFDIA(
  D: number,
  I: number,
  A: number
): Promise<FDIAScore> {
  const mod = await getWasmModule();

  let F: number;
  if (mod?.compute_fdia) {
    try {
      F = mod.compute_fdia(D, I, A);
    } catch {
      F = computeFDIAjs(D, I, A);
    }
  } else {
    F = computeFDIAjs(D, I, A);
  }

  return {
    D: Math.max(0, Math.min(1, D)),
    I: Math.max(0, Math.min(1, I)),
    A: Math.max(0, Math.min(1, A)),
    F: Math.max(0, Math.min(1, F)),
    signed: false,
    signature_hash: "",
  };
}

/**
 * Verify a SignedAI FDIA signature.
 * Returns false (permissive) if WASM is unavailable.
 */
export async function verifyFDIASignature(
  hash: string,
  signature: string
): Promise<boolean> {
  const mod = await getWasmModule();
  if (!mod?.verify_signature) return false;
  try {
    return mod.verify_signature(hash, signature);
  } catch {
    return false;
  }
}
