/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base path of the API, default `/api/v1` (proxied by the dev server). */
  readonly VITE_API_BASE?: string;
  /** Dev-server proxy target, default `http://127.0.0.1:8000`. */
  readonly VITE_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
