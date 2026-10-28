"""Run: python -m unittest discover -s tests -v (no ComfyUI/GPU required)."""

import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import datetime
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class Tensor:
    """Only the CPU/numpy interface used at the node's image boundary."""
    def __init__(self, pixels):
        self.pixels = np.asarray(pixels, dtype=np.float32)
        self.shape = self.pixels.shape

    def cpu(self):
        return self

    def numpy(self):
        return self.pixels


args = types.SimpleNamespace(disable_metadata=False)
server = types.SimpleNamespace(client_id="test-client", events=[])


def send_sync(event, data, sid=None):
    server.events.append((event, data, sid))


server.send_sync = send_sync
stubs = {
    "server": types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=server)),
    "comfy": types.ModuleType("comfy"),
    "comfy.cli_args": types.SimpleNamespace(args=args),
}
spec = importlib.util.spec_from_file_location("auto_download_under_test", ROOT / "auto_download.py")
node_module = importlib.util.module_from_spec(spec)
# Restore only our ComfyUI stubs. patch.dict(sys.modules) also removes newly
# imported C extension modules (notably _zoneinfo), invalidating their state
# on otherwise clean Python installations.
missing = object()
original_modules = {name: sys.modules.get(name, missing) for name in stubs}
sys.modules.update(stubs)
try:
    spec.loader.exec_module(node_module)
finally:
    for name, original in original_modules.items():
        if original is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


class MetadataTests(unittest.TestCase):
    def setUp(self):
        server.events.clear()
        args.disable_metadata = False
        self.node = node_module.AutoDownloadNode()
        self.pixels = np.array([[[0, 0.5, 1], [1.5, -0.5, 0.25]]], dtype=np.float32)
        self.batch = [Tensor(self.pixels)]
        self.prompt = {"1": {"class_type": "Example", "inputs": {"text": "México 🌵"}}}
        self.workflow = {
            "version": 0.4, "last_node_id": 7, "last_link_id": 1,
            "nodes": [{"id": 7, "type": "AutoDownloadNode", "pos": [32, 64],
                       "size": [315, 200], "flags": {}, "order": 0, "mode": 0,
                       "inputs": [], "outputs": [], "properties": {},
                       "widgets_values": ["Luis_prueba"]}],
            "links": [], "groups": [], "config": {}, "extra": {"note": "完整 workflow"},
        }

    def png(self, index=0):
        return Image.open(io.BytesIO(base64.b64decode(server.events[index][1]["data"])))

    def test_hidden_metadata_inputs(self):
        hidden = self.node.INPUT_TYPES()["hidden"]
        self.assertEqual(hidden["prompt"], "PROMPT")
        self.assertEqual(hidden["extra_pnginfo"], "EXTRA_PNGINFO")

    def test_full_metadata_and_pixels_round_trip(self):
        extra = {"workflow": self.workflow, "other_extension": {"value": [1, "á"]}}
        result = self.node.transmit_to_client(self.batch, "Luis_prueba", self.prompt, extra)
        self.assertEqual(result, {"ui": {"images": []}})
        self.assertEqual(server.events[0][0], "auto_download_direct")
        png = self.png()
        self.assertEqual(json.loads(png.info["prompt"]), self.prompt)
        self.assertEqual(json.loads(png.info["workflow"]), self.workflow)
        self.assertEqual(json.loads(png.info["other_extension"]), extra["other_extension"])
        np.testing.assert_array_equal(np.array(png), np.clip(255 * self.pixels, 0, 255).astype(np.uint8))

    def test_every_batch_image_has_full_metadata(self):
        self.node.transmit_to_client(self.batch * 4, "batch", self.prompt, {"workflow": self.workflow})
        self.assertEqual(len(server.events), 4)
        for i in range(4):
            self.assertEqual(json.loads(self.png(i).info["workflow"]), self.workflow)
            self.assertEqual(json.loads(self.png(i).info["prompt"]), self.prompt)

    def test_disable_metadata_matches_save_image(self):
        args.disable_metadata = True
        self.node.transmit_to_client(self.batch, "private", self.prompt, {"workflow": self.workflow})
        self.assertEqual(self.png().info, {})

    def test_legacy_call_without_metadata_still_downloads(self):
        self.node.transmit_to_client(self.batch, "legacy")
        self.assertEqual(self.png().format, "PNG")

    def test_rgba_batch(self):
        self.node.transmit_to_client([Tensor(np.ones((2, 3, 4)))], "rgba", self.prompt, {"workflow": self.workflow})
        self.assertEqual(self.png().mode, "RGBA")
        self.assertEqual(json.loads(self.png().info["workflow"]), self.workflow)

    def test_batch_and_same_instant_runs_have_distinct_names(self):
        for _ in range(2):
            self.node.transmit_to_client(self.batch * 4, "Luis_batch", timestamp_format="")
        names = [event[1]["filename"] for event in server.events]
        self.assertEqual(len(set(names)), 8)
        self.assertTrue(names[0].endswith("_00001.png"))
        self.assertTrue(names[3].endswith("_00004.png"))

    def test_mexico_city_date_independent_of_server_timezone(self):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 28, 3, 4, 5, 123456, tzinfo=datetime.timezone.utc).astimezone(tz)

        with patch.object(node_module.datetime, "datetime", FixedDateTime):
            self.node.transmit_to_client(self.batch, "Luis", timestamp_format="%Y-%m-%d_%H-%M-%S_%f_%z")
        self.assertTrue(server.events[0][1]["filename"].startswith("Luis_2026-10-27_21-04-05_123456_-0600_"))

    def test_invalid_timezone_is_rejected_before_download(self):
        with self.assertRaisesRegex(ValueError, "Unknown time zone"):
            self.node.transmit_to_client(self.batch, "Luis", timezone="Not/AZone")
        self.assertEqual(server.events, [])

    def test_windows_names_are_sanitized_and_bounded(self):
        self.node.transmit_to_client(self.batch, '../CON:bad\\file?*' + 'x' * 300,
                                     timestamp_format="%Y/%m/%d %H:%M:%S" + 'z' * 200)
        name = server.events[0][1]["filename"]
        self.assertLess(len(name), 256)
        self.assertNotRegex(name, r'[<>:"/\\|?*\x00-\x1f]')
        self.assertTrue(name.endswith(".png"))

    def test_node_identity_and_client_routing(self):
        self.node.transmit_to_client(self.batch * 2, "Luis_under_scores", unique_id="37")
        self.assertEqual([e[1]["batch_index"] for e in server.events], [0, 1])
        for _, payload, sid in server.events:
            self.assertEqual(payload["node_id"], "37")
            self.assertEqual(sid, "test-client")

    def test_native_batch_placeholder(self):
        self.node.transmit_to_client(self.batch * 2, "item_%batch_num%", timestamp_format="")
        self.assertTrue(server.events[0][1]["filename"].startswith("item_0_"))
        self.assertTrue(server.events[1][1]["filename"].startswith("item_1_"))

    def test_long_unicode_name_fits_windows_component(self):
        self.node.transmit_to_client(self.batch, "🌵" * 300, timestamp_format="🌙" * 100)
        name = server.events[0][1]["filename"]
        self.assertLess(len(name.encode("utf-16-le")) // 2, 256)

    def test_encoding_does_not_write_server_files(self):
        with patch("builtins.open", side_effect=AssertionError("Unexpected disk write")):
            self.node.transmit_to_client(self.batch, "memory", self.prompt, {"workflow": self.workflow})
        self.assertEqual(json.loads(self.png().info["workflow"]), self.workflow)


if __name__ == "__main__":
    unittest.main()
