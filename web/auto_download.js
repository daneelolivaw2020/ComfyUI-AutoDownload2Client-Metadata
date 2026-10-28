import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Custom.AutoDownload",
    async setup() {
        // One listener in this ComfyUI document; fullscreen keeps the same listener.
        const listenerKey = Symbol.for("Custom.AutoDownload.listener");
        if (api[listenerKey]) {
            api.removeEventListener("auto_download_direct", api[listenerKey]);
        }
        const listener = (event) => {
            const { data, filename } = event.detail;
            const blob = base64ToBlob(data, "image/png");
            const url = window.URL.createObjectURL(blob);

            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            try {
                link.click();
            } finally {
                link.remove();
            }

            if (!updatePreview(event.detail, url)) {
                releaseLater([url]);
            }
        };
        api[listenerKey] = listener;
        api.addEventListener("auto_download_direct", listener);
    }
});

function releaseLater(urls) {
    // Firefox must have time to consume the Blob before it is revoked.
    setTimeout(() => urls.forEach(url => window.URL.revokeObjectURL(url)), 60_000);
}

function updatePreview(detail, url) {
    const { node_id, download_id, batch_index = 0 } = detail;
    const nodes = app.graph?.findNodesByType("AutoDownloadNode") || [];
    // Legacy backend: only infer a preview if there is exactly one matching node.
    const node = node_id != null
        ? nodes.find(node => String(node.id) === String(node_id))
        : (nodes.length === 1 ? nodes[0] : null);
    if (!node) return false;

    if (!download_id || node.autoDownloadRun !== download_id) {
        releaseLater(node.autoDownloadUrls || []);
        node.autoDownloadRun = download_id;
        node.autoDownloadUrls = [];
        node.imgs = [];
        node.imageIndex = null;
    }
    const img = new Image();
    img.onload = () => node.setDirtyCanvas(true);
    node.autoDownloadUrls[batch_index] = url;
    node.imgs[batch_index] = img;
    img.src = url;
    node.setDirtyCanvas(true);
    return true;
}

function base64ToBlob(base64, type) {
    const binStr = atob(base64);
    const len = binStr.length;
    const arr = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        arr[i] = binStr.charCodeAt(i);
    }
    return new Blob([arr], { type: type });
}
