"use client";

import { useState, useCallback, useRef } from "react";
import { executeIntent, streamIntent } from "@/lib/delentia-client";
import type {
  FDIAScore,
  HexaCoreRole,
  IntentExecuteResponse,
  JITNAPacketV3,
} from "@/lib/types";

export type IntentState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; response: IntentExecuteResponse }
  | { status: "error"; message: string };

export interface UseIntentOptions {
  apiKey?: string;
  gateway?: string;
  mode?: "quick" | "standard" | "deep" | "mirror" | "agent";
}

export interface UseIntentReturn {
  state: IntentState;
  lastFdia: FDIAScore | null;
  lastRole: HexaCoreRole | null;
  lastPacket: JITNAPacketV3 | null;
  run: (intent: string) => Promise<void>;
  reset: () => void;
}

/**
 * React hook for firing intents at the Delentia OS Gateway.
 * Provides loading/success/error state + last FDIA score + HexaCore role used.
 */
export function useIntent(options: UseIntentOptions = {}): UseIntentReturn {
  const [state, setState] = useState<IntentState>({ status: "idle" });
  const [lastFdia, setLastFdia] = useState<FDIAScore | null>(null);
  const [lastRole, setLastRole] = useState<HexaCoreRole | null>(null);
  const [lastPacket, setLastPacket] = useState<JITNAPacketV3 | null>(null);

  const run = useCallback(
    async (intent: string) => {
      if (!intent.trim()) return;

      setState({ status: "loading" });
      try {
        const response = await executeIntent(intent, options);
        setState({ status: "success", response });

        if (response.output.fdia_score) {
          setLastFdia(response.output.fdia_score);
        }
        if (response.output.hexa_role) {
          setLastRole(response.output.hexa_role);
        }
        if (response.jitna_packet) {
          setLastPacket(response.jitna_packet);
        }
      } catch (err) {
        setState({
          status: "error",
          message: err instanceof Error ? err.message : "Unknown error",
        });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [options.apiKey, options.gateway, options.mode]
  );

  const reset = useCallback(() => {
    setState({ status: "idle" });
  }, []);

  return { state, lastFdia, lastRole, lastPacket, run, reset };
}

// ─── Streaming hook ───────────────────────────────────────────────────────────

export interface StreamState {
  status: "idle" | "streaming" | "done" | "error";
  partial: string;       // accumulated token text so far
  fdia: FDIAScore | null;
  hexaRole: string | null;
  errorMessage: string | null;
}

export interface UseStreamIntentReturn {
  streamState: StreamState;
  runStream: (intent: string) => Promise<void>;
  abortStream: () => void;
  resetStream: () => void;
}

const INITIAL_STREAM_STATE: StreamState = {
  status: "idle",
  partial: "",
  fdia: null,
  hexaRole: null,
  errorMessage: null,
};

/**
 * useStreamIntent — streams tokens from /v1/kernel/stream WebSocket.
 * Updates `streamState.partial` in real-time as tokens arrive (typewriter effect).
 */
export function useStreamIntent(
  options: UseStreamIntentOptions = {}
): UseStreamIntentReturn {
  const [streamState, setStreamState] = useState<StreamState>(INITIAL_STREAM_STATE);
  const abortRef = useRef(false);

  const runStream = useCallback(
    async (intent: string) => {
      if (!intent.trim()) return;
      abortRef.current = false;

      setStreamState({
        status: "streaming",
        partial: "",
        fdia: null,
        hexaRole: null,
        errorMessage: null,
      });

      try {
        for await (const event of streamIntent(intent, options)) {
          if (abortRef.current) break;

          if (event.type === "token") {
            setStreamState((prev) => ({ ...prev, partial: prev.partial + event.data }));
          } else if (event.type === "fdia") {
            setStreamState((prev) => ({ ...prev, fdia: event.data as FDIAScore }));
          } else if (event.type === "done") {
            const d = event.data as { hexa_role?: string; fdia_score?: FDIAScore };
            setStreamState((prev) => ({
              ...prev,
              status: "done",
              hexaRole: d.hexa_role ?? prev.hexaRole,
              fdia: d.fdia_score ?? prev.fdia,
            }));
          } else if (event.type === "error") {
            setStreamState((prev) => ({
              ...prev,
              status: "error",
              errorMessage: event.data as string,
            }));
          }
        }
      } catch (err) {
        setStreamState((prev) => ({
          ...prev,
          status: "error",
          errorMessage: err instanceof Error ? err.message : "Stream failed",
        }));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [options.apiKey, options.gateway, options.mode]
  );

  const abortStream = useCallback(() => {
    abortRef.current = true;
    setStreamState((prev) =>
      prev.status === "streaming" ? { ...prev, status: "done" } : prev
    );
  }, []);

  const resetStream = useCallback(() => {
    abortRef.current = true;
    setStreamState(INITIAL_STREAM_STATE);
  }, []);

  return { streamState, runStream, abortStream, resetStream };
}

export interface UseStreamIntentOptions {
  apiKey?: string;
  gateway?: string;
  mode?: "quick" | "standard" | "deep" | "mirror" | "agent";
}
