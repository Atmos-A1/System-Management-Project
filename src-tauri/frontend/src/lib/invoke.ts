import { invoke } from "@tauri-apps/api/core";

export interface MetricArgs {
  method: string;
  params?: Record<string, unknown>;
}

export async function invokeMetric(args: MetricArgs): Promise<unknown> {
  return invoke("invoke_metric", {
    method: args.method,
    params: args.params,
  });
}
