"""Generate real backend PNG event payloads for the Firefox transport test."""
import json
from pathlib import Path
import sys

import numpy as np
from test_auto_download import Tensor, node_module, server

workflow = json.loads((Path(__file__).resolve().parents[1] / "examples/smoke-test-workflow.json").read_text())
prompt = {
    "1": {"class_type": "EmptyImage", "inputs": {"width": 64, "height": 64, "batch_size": 4, "color": 3368601}},
    "2": {"class_type": "AutoDownloadNode", "inputs": {
        "image": ["1", 0], "filename_prefix": "Luis_Prueba", "timestamp_format": "%Y-%m-%d_%H-%M-%S",
        "timezone": "America/Mexico_City"}},
}
pixels = np.full((64, 64, 3), [0.2, 0.4, 0.6], dtype=np.float32)
runs = []
for size in (1, 4, 1, 2):
    server.events.clear()
    node_module.AutoDownloadNode().transmit_to_client(
        [Tensor(pixels)] * size, "Luis_Prueba", prompt, {"workflow": workflow}, unique_id="2")
    runs.append([event[1] for event in server.events])
Path(sys.argv[1]).write_text(json.dumps({"runs": runs, "workflow": workflow, "prompt": prompt}), encoding="utf-8")
