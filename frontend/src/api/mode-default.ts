import type { DataMode } from "./client";
// Standalone export: live FastAPI backend by default; set VITE_DATA_MODE=fixture for offline preview/tests.
export const DEFAULT_DATA_MODE: DataMode = "live";
