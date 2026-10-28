"""Compare against an actual ComfyUI nodes.py without importing ComfyUI/torch.

Usage: python tests/compare_native.py /path/to/ComfyUI/nodes.py
The SaveImage class is extracted unchanged using Python's AST.
"""
import ast
import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from test_auto_download import MetadataTests, Tensor, args, node_module, server


source = Path(sys.argv[1])
tree = ast.parse(source.read_text(encoding="utf-8"))
save_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SaveImage")
case = MetadataTests()
case.setUp()
with tempfile.TemporaryDirectory() as temp:
    paths = types.SimpleNamespace(
        get_output_directory=lambda: temp,
        get_save_image_path=lambda *args: (temp, "native", 1, "", "native"),
    )
    scope = {"folder_paths": paths, "np": np, "Image": Image, "PngInfo": PngInfo,
             "args": args, "json": json, "os": os}
    exec(compile(ast.Module(body=[save_class], type_ignores=[]), str(source), "exec"), scope)
    for disabled in (False, True):
        args.disable_metadata = disabled
        extra = {"workflow": case.workflow, "other_extension": {"key": "español 🌵"}}
        batch = [Tensor(case.pixels)] * 3
        native = scope["SaveImage"]().save_images(batch, "native", case.prompt, extra)
        server.events.clear()
        node_module.AutoDownloadNode().transmit_to_client(batch, "client", case.prompt, extra)
        for native_entry, (_, payload, _) in zip(native["ui"]["images"], server.events, strict=True):
            with Image.open(Path(temp) / native_entry["filename"]) as native_png:
                with Image.open(io.BytesIO(base64.b64decode(payload["data"]))) as client_png:
                    assert native_png.info == client_png.info, "Metadata differs from native SaveImage"
                    np.testing.assert_array_equal(np.array(native_png), np.array(client_png))
print("PASS: 6 PNGs match actual native SaveImage metadata and pixels (enabled/disabled metadata).")
