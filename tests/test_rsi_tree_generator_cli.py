"""
Tests for rsi_tree_generator.py CLI main() — covers lines 203-243, 247.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_tree_generator import main, RSITreeGenerator


class TestTreeGeneratorCLIGenerate(unittest.TestCase):
    """Test the 'generate' subcommand."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_trees = patch(
            "vsf_rsi.rsi_tree_generator.TREES_DIR", self._tmpdir
        )
        self._patcher_generated = patch(
            "vsf_rsi.rsi_tree_generator.GENERATED_DIR", self._tmpdir / "generated"
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_tree_generator.MANIFEST_FILE",
            self._tmpdir / "manifest.vsm",
        )
        self._patcher_trees.start()
        self._patcher_generated.start()
        self._patcher_manifest.start()

    def tearDown(self):
        self._patcher_trees.stop()
        self._patcher_generated.stop()
        self._patcher_manifest.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-tree-generator", "generate", "test_pred"])
    def test_generate_with_sample_gaps(self):
        """generate without --gaps-file uses sample gaps."""
        gen = RSITreeGenerator()
        with patch.object(gen, "generate_tree") as mock_gen:
            mock_gen.return_value = str(self._tmpdir / "test_pred_auto.tree.vsm")
            with patch(
                "vsf_rsi.rsi_tree_generator.RSITreeGenerator", return_value=gen
            ):
                with patch("builtins.print") as mock_print:
                    main()
            mock_gen.assert_called_once()
            args = mock_gen.call_args
            self.assertEqual(args[0][0], "test_pred")
            # Sample gaps include two items
            self.assertEqual(len(args[0][1]["gaps"]), 2)

    @patch("sys.argv", ["rsi-tree-generator", "generate", "test_pred", "--gaps-file"])
    def test_generate_with_gaps_file(self, ):
        """generate with --gaps-file loads gaps from file."""
        gaps = {"predicate": "test_pred", "gaps": [{"type": "from_file", "severity": "low"}]}
        gaps_file = self._tmpdir / "gaps.json"
        gaps_file.write_text(json.dumps(gaps))
        # Need to patch sys.argv properly with the file path
        with patch("sys.argv", ["rsi-tree-generator", "generate", "test_pred",
                                "--gaps-file", str(gaps_file)]):
            gen = RSITreeGenerator()
            with patch.object(gen, "generate_tree") as mock_gen:
                mock_gen.return_value = str(self._tmpdir / "out.vsm")
                with patch(
                    "vsf_rsi.rsi_tree_generator.RSITreeGenerator", return_value=gen
                ):
                    with patch("builtins.print") as mock_print:
                        main()
                mock_gen.assert_called_once()
                args = mock_gen.call_args
                self.assertEqual(args[0][1]["gaps"][0]["type"], "from_file")


class TestTreeGeneratorCLIList(unittest.TestCase):
    """Test the 'list' subcommand."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_trees = patch(
            "vsf_rsi.rsi_tree_generator.TREES_DIR", self._tmpdir
        )
        self._patcher_generated = patch(
            "vsf_rsi.rsi_tree_generator.GENERATED_DIR", self._tmpdir / "generated"
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_tree_generator.MANIFEST_FILE",
            self._tmpdir / "manifest.vsm",
        )
        self._patcher_trees.start()
        self._patcher_generated.start()
        self._patcher_manifest.start()

    def tearDown(self):
        self._patcher_trees.stop()
        self._patcher_generated.stop()
        self._patcher_manifest.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-tree-generator", "list"])
    def test_list_with_trees(self):
        """list prints tree count and entries."""
        gen = RSITreeGenerator()
        with patch.object(gen, "get_generated_trees") as mock_trees:
            mock_trees.return_value = [
                {"predicate": "foo", "path": "/tmp/foo.tree.vsm"},
                {"predicate": "bar", "path": "/tmp/bar.tree.vsm"},
            ]
            with patch(
                "vsf_rsi.rsi_tree_generator.RSITreeGenerator", return_value=gen
            ):
                with patch("builtins.print") as mock_print:
                    main()
            calls = [c[0][0] for c in mock_print.call_args_list]
            self.assertTrue(any("Generated trees: 2" in c for c in calls))
            self.assertTrue(any("foo" in c for c in calls))
            self.assertTrue(any("bar" in c for c in calls))

    @patch("sys.argv", ["rsi-tree-generator", "list"])
    def test_list_empty(self):
        """list with no trees prints count 0."""
        gen = RSITreeGenerator()
        with patch.object(gen, "get_generated_trees", return_value=[]):
            with patch(
                "vsf_rsi.rsi_tree_generator.RSITreeGenerator", return_value=gen
            ):
                with patch("builtins.print") as mock_print:
                    main()
            calls = [c[0][0] for c in mock_print.call_args_list]
            self.assertTrue(any("Generated trees: 0" in c for c in calls))


class TestTreeGeneratorCLIHelp(unittest.TestCase):
    """Test no-subcommand prints help."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_trees = patch(
            "vsf_rsi.rsi_tree_generator.TREES_DIR", self._tmpdir
        )
        self._patcher_generated = patch(
            "vsf_rsi.rsi_tree_generator.GENERATED_DIR", self._tmpdir / "generated"
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_tree_generator.MANIFEST_FILE",
            self._tmpdir / "manifest.vsm",
        )
        self._patcher_trees.start()
        self._patcher_generated.start()
        self._patcher_manifest.start()

    def tearDown(self):
        self._patcher_trees.stop()
        self._patcher_generated.stop()
        self._patcher_manifest.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-tree-generator"])
    def test_no_command_prints_help(self):
        """No subcommand prints help (line 243)."""
        gen = RSITreeGenerator()
        with patch.object(gen, "generate_tree") as mock_gen, \
             patch.object(gen, "get_generated_trees") as mock_trees, \
             patch(
                 "vsf_rsi.rsi_tree_generator.RSITreeGenerator", return_value=gen
             ):
            with patch("builtins.print"):
                main()
        mock_gen.assert_not_called()
        mock_trees.assert_not_called()


if __name__ == "__main__":
    unittest.main()
