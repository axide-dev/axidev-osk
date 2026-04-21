import type { BrowserWindow } from 'electron';

export type NoActivateClientAreaHandle = {
  dispose: () => boolean;
  installed: boolean;
  platform: NodeJS.Platform;
  supported: boolean;
};

export type NoActivateClientAreaLogLevel =
  | 'silent'
  | 'error'
  | 'warn'
  | 'info'
  | 'debug';

export declare function installNoActivateClientArea(
  window: BrowserWindow,
): NoActivateClientAreaHandle;

export declare function isSupported(): boolean;

export declare function getLogLevel(): NoActivateClientAreaLogLevel;

export declare function setLogLevel(
  level: NoActivateClientAreaLogLevel,
): NoActivateClientAreaLogLevel;
