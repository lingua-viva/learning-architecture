import { contextBridge, ipcRenderer } from "electron";

type BackendReadyCallback = (url: string) => void;

contextBridge.exposeInMainWorld("lvDesktop", {
  getVersion: () => ipcRenderer.invoke("lv:get-version"),
  readFile: (relativePath: string) => ipcRenderer.invoke("lv:read-file", relativePath),
  notify: (title: string, body: string) => ipcRenderer.invoke("lv:notify", { title, body }),
  onBackendReady: (callback: BackendReadyCallback) => {
    const listener = (_event: Electron.IpcRendererEvent, url: string) => callback(url);
    ipcRenderer.on("lv:backend-ready", listener);
    return () => ipcRenderer.removeListener("lv:backend-ready", listener);
  }
});
