import { invoke } from "@tauri-apps/api/core";

export interface MetricArgs {
  method: string;
  params?: Record<string, unknown>;
}

/**
 * Invoke a metric on the Python sidecar via the Tauri command.
 *
 * Tauri's `invoke` rejects with a string (the Rust `String` error type),
 * not an `Error` object. This wrapper normalizes the rejection to always
 * throw an `Error` with the message, so callers can use `err instanceof Error`
 * and `err.message` reliably.
 */
export async function invokeMetric(args: MetricArgs): Promise<unknown> {
  try {
    return await invoke("invoke_metric", {
      args: {
        method: args.method,
        params: args.params,
      },
    });
  } catch (err) {
    // Normalize: Tauri rejects with a string, wrap in Error for consistent handling
    throw new Error(typeof err === "string" ? err : String(err));
  }
}