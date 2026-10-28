import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import io
import base64
import datetime
import json
import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from comfy.cli_args import args
from server import PromptServer

def filename_part(value, fallback, limit):
    """A download is one Windows filename, never a server/client path."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    # NTFS measures component length in UTF-16 code units (emoji take two).
    value = value.encode("utf-16-le")[:limit * 2].decode("utf-16-le", errors="ignore").rstrip(" .")
    return value or fallback


class AutoDownloadNode:

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "ComfyUI2Client"})
            },
            "optional": {
                "timestamp_format": ("STRING", {
                    "default": "%Y-%m-%d_%H-%M-%S",
                    "tooltip": "Python strftime: %Y year, %m month, %d day, %H hour, %M minute, %S second, %f microseconds. Empty: no date."
                }),
                "timezone": ("STRING", {
                    "default": "America/Mexico_City",
                    "tooltip": "IANA time zone, e.g. America/Mexico_City or UTC. local uses the ComfyUI server time zone."
                })
            },
            "hidden": {
                "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO", "unique_id": "UNIQUE_ID"
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "transmit_to_client"
    OUTPUT_NODE = True
    CATEGORY = "custom_nodes/Image"

    def transmit_to_client(self, image, filename_prefix, prompt=None, extra_pnginfo=None,
                           timestamp_format="%Y-%m-%d_%H-%M-%S",
                           timezone="America/Mexico_City", unique_id=None):
        try:
            tz = None if timezone == "local" else ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"Unknown time zone {timezone!r}. Use an IANA name such as "
                "America/Mexico_City or UTC; install tzdata if the system has no zone database."
            ) from exc
        now = datetime.datetime.now(tz)
        timestamp = filename_part(now.strftime(timestamp_format), "", 80) if timestamp_format else ""
        # One UUID per execution plus the index distinguishes batches and simultaneous runs.
        download_id = uuid.uuid4().hex
        metadata = None
        if not args.disable_metadata:
            metadata = PngInfo()
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for key in extra_pnginfo:
                    metadata.add_text(key, json.dumps(extra_pnginfo[key]))

        for index, img_tensor in enumerate(image):
            i = 255. * img_tensor.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            buffer = io.BytesIO()
            img.save(buffer, format="PNG", pnginfo=metadata)
            img_bytes = buffer.getvalue()
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')

            prefix = filename_part(filename_prefix.replace("%batch_num%", str(index)), "ComfyUI2Client", 100)
            parts = [prefix, timestamp, download_id, f"{index + 1:05d}"]
            PromptServer.instance.send_sync("auto_download_direct", {
                "data": img_base64,
                "filename": "_".join(part for part in parts if part) + ".png",
                "node_id": unique_id,
                "download_id": download_id,
                "batch_index": index,
            }, PromptServer.instance.client_id)

        return {"ui": {"images": []}}

NODE_CLASS_MAPPINGS = {"AutoDownloadNode": AutoDownloadNode}
NODE_DISPLAY_NAME_MAPPINGS = {"AutoDownloadNode": "AutoDownload2Client"}

