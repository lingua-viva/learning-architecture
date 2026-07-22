import { contextBridge, ipcRenderer } from "electron";

type BackendReadyCallback = (url: string) => void;
type SetupProgressCallback = (payload: { step: string; detail?: string }) => void;

contextBridge.exposeInMainWorld("lvDesktop", {
  // Existing API
  getVersion: () => ipcRenderer.invoke("lv:get-version"),
  readFile: (relativePath: string) => ipcRenderer.invoke("lv:read-file", relativePath),
  notify: (title: string, body: string) => ipcRenderer.invoke("lv:notify", { title, body }),
  onBackendReady: (callback: BackendReadyCallback) => {
    const listener = (_event: Electron.IpcRendererEvent, url: string) => callback(url);
    ipcRenderer.on("lv:backend-ready", listener);
    return () => ipcRenderer.removeListener("lv:backend-ready", listener);
  },

  // Setup wizard API
  installPython: () => ipcRenderer.invoke("lv:setup:installPython"),
  retrySetup: () => ipcRenderer.invoke("lv:setup:retryPython"),
  installOllama: () => ipcRenderer.invoke("lv:setup:installOllama"),
  skipOllama: () => ipcRenderer.invoke("lv:setup:skipOllama"),
  openExternal: (url: string) => ipcRenderer.invoke("lv:setup:openExternal", url),
  onSetupProgress: (callback: SetupProgressCallback) => {
    const listener = (_event: Electron.IpcRendererEvent, payload: { step: string; detail?: string }) => callback(payload);
    ipcRenderer.on("lv:setup:progress", listener);
    return () => ipcRenderer.removeListener("lv:setup:progress", listener);
  }
});
