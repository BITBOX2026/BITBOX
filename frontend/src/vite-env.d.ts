declare module "*.css" {
  const content: { [className: string]: string };
  export default content;
}

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_API_AUTH_TOKEN?: string;
  readonly VITE_DEV_PROXY_TARGET?: string;
  readonly VITE_STATION_NAME?: string;
  readonly VITE_KAKAO_MAP_APPKEY?: string;
}
 
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
