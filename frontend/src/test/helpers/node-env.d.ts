declare module 'node:fs' {
  export function existsSync(path: string): boolean;
  export function readFileSync(path: string, encoding: string): string;
}

declare module 'node:path' {
  export function join(...paths: string[]): string;
  export function resolve(...paths: string[]): string;
  export const win32: {
    join(...paths: string[]): string;
  };
}

declare module 'node:url' {
  export function fileURLToPath(url: string): string;
}

declare const process: {
  env: Record<string, string | undefined>;
  platform: string;
};
