"""核心纯本地逻辑测试，不访问网络。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pcl_core.accounts import AccountStore
from pcl_core.config import Config, Paths, detect_arch
from pcl_core.minecraft import merge_version_json, maven_path, parse_library_name, resolve_libraries
from pcl_core.util import offline_uuid, valid_version_id


class UtilTests(unittest.TestCase):
    def test_version_id_validation(self) -> None:
        self.assertTrue(valid_version_id("1.21.4"))
        self.assertTrue(valid_version_id("fabric-loader-0.16.10-1.21.4"))
        self.assertFalse(valid_version_id("../etc/passwd"))
        self.assertFalse(valid_version_id(""))
        self.assertFalse(valid_version_id("-bad-start"))

    def test_offline_uuid_stable_and_formatted(self) -> None:
        first = offline_uuid("Steve")
        second = offline_uuid("Steve")
        other = offline_uuid("Alex")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertEqual(len(first), 36)
        self.assertEqual(first.count("-"), 4)

    def test_maven_coordinates(self) -> None:
        group, artifact, version, classifier = parse_library_name(
            "org.lwjgl:lwjgl:3.3.3:natives-linux-arm64"
        )
        self.assertEqual(group, "org.lwjgl")
        self.assertEqual(artifact, "lwjgl")
        self.assertEqual(version, "3.3.3")
        self.assertEqual(classifier, "natives-linux-arm64")
        self.assertEqual(
            maven_path(group, artifact, version, classifier),
            "org/lwjgl/lwjgl/3.3.3/lwjgl-3.3.3-natives-linux-arm64.jar",
        )


class MergeTests(unittest.TestCase):
    def test_merge_child_and_parent(self) -> None:
        parent = {
            "id": "1.21.4",
            "type": "release",
            "mainClass": "net.minecraft.client.main.Main",
            "assetIndex": {"id": "21"},
            "assets": "21",
            "javaVersion": {"majorVersion": 21},
            "libraries": [
                {"name": "com.example:shared:1.0"},
                {"name": "org.lwjgl:lwjgl:3.3.3"},
            ],
            "arguments": {"game": ["--game"], "jvm": ["-Xmx2G"]},
        }
        child = {
            "id": "fabric-loader-0.16.10-1.21.4",
            "inheritsFrom": "1.21.4",
            "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
            "libraries": [
                {"name": "net.fabricmc:fabric-loader:0.16.10"},
                {"name": "com.example:shared:2.0"},
            ],
            "arguments": {"game": ["--fabric"], "jvm": []},
        }
        merged = merge_version_json(parent, child, "fabric-loader-0.16.10-1.21.4")
        self.assertEqual(merged["id"], "fabric-loader-0.16.10-1.21.4")
        self.assertEqual(merged["mainClass"], "net.fabricmc.loader.impl.launch.knot.KnotClient")
        self.assertNotIn("inheritsFrom", merged)
        names = [item["name"] for item in merged["libraries"]]
        self.assertEqual(names, [
            "net.fabricmc:fabric-loader:0.16.10",
            "com.example:shared:2.0",
            "org.lwjgl:lwjgl:3.3.3",
        ])
        self.assertEqual(merged["arguments"]["game"], ["--game", "--fabric"])
        self.assertEqual(merged["assetIndex"], {"id": "21"})
        self.assertEqual(merged["javaVersion"], {"majorVersion": 21})


class LibraryResolveTests(unittest.TestCase):
    def test_custom_maven_repository_is_preserved(self) -> None:
        version = {
            "libraries": [
                {"name": "org.ow2.asm:asm:9.10.1", "url": "https://maven.fabricmc.net/"},
                {"name": "com.example:lib:1.0", "downloads": {"artifact": {"path": "com/example/lib/1.0/lib-1.0.jar"}}},
            ]
        }
        plan = resolve_libraries(version, "linux", "arm64", {}, arm64_patch=False)
        urls = {item["name"]: item["url"] for item in plan["classpath"]}
        self.assertEqual(
            urls["org.ow2.asm:asm:9.10.1"],
            "https://maven.fabricmc.net/org/ow2/asm/asm/9.10.1/asm-9.10.1.jar",
        )
        self.assertIn("/com/example/lib/1.0/lib-1.0.jar", urls["com.example:lib:1.0"])


class ConfigTests(unittest.TestCase):
    def test_version_isolation_default_and_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = Paths(temp)
            config = Config(paths)
            config.update({"game_dir": str(Path(temp) / "game"), "version_isolation": True})
            isolated = config.version_game_dir("1.21.4")
            self.assertEqual(isolated, Path(temp) / "game" / "versions" / "1.21.4")
            shared = config.version_game_dir("1.21.4", {"isolated": False})
            self.assertEqual(shared, Path(temp) / "game")
            config.update({"version_isolation": False})
            self.assertEqual(config.version_game_dir("1.21.4"), Path(temp) / "game")

    def test_arch_override(self) -> None:
        old = os.environ.get("PCL_ARCH")
        try:
            os.environ["PCL_ARCH"] = "arm64"
            self.assertEqual(detect_arch(), "arm64")
            os.environ["PCL_ARCH"] = "x86_64"
            self.assertEqual(detect_arch(), "x86_64")
        finally:
            if old is None:
                os.environ.pop("PCL_ARCH", None)
            else:
                os.environ["PCL_ARCH"] = old


class AccountTests(unittest.TestCase):
    def test_add_select_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = Paths(temp)
            store = AccountStore(paths)
            default = store.list()["selected"]
            self.assertEqual(default["name"], "Steve")
            account = store.add("Alex")
            self.assertEqual(store.selected()["name"], "Alex")
            self.assertEqual(account["name"], "Alex")
            store.select(default["id"])
            self.assertEqual(store.selected()["name"], "Steve")
            store.remove(account["id"])
            names = [item["name"] for item in store.list()["accounts"]]
            self.assertEqual(names, ["Steve"])
            with self.assertRaises(Exception):
                store.remove(default["id"])


if __name__ == "__main__":
    unittest.main()
