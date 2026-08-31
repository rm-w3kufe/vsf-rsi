"""
Tests for rsi_forest_generator.py — Forest generation and evolution
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase, mock
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_forest_generator import RSIForestGenerator


class TestRSIForestGeneratorInit(TestCase):
    """Test RSIForestGenerator initialization."""

    @patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
    @patch("vsf_rsi.rsi_forest_generator.FORESTS_DIR")
    def test_init_default(self, mock_dir, mock_ga):
        """RSIForestGenerator can be initialized."""
        gen = RSIForestGenerator()
        self.assertIsNotNone(gen)
        mock_dir.mkdir.assert_called_with(parents=True, exist_ok=True)

    @patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
    @patch("vsf_rsi.rsi_forest_generator.FORESTS_DIR")
    def test_init_creates_ga(self, mock_dir, mock_ga):
        """__init__ creates self.ga as RSIGeneticAlgorithm instance."""
        gen = RSIForestGenerator()
        mock_ga.assert_called_once()
        self.assertIsNotNone(gen.ga)

    @patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
    @patch("vsf_rsi.rsi_forest_generator.FORESTS_DIR")
    def test_init_sets_forests_dir(self, mock_dir, mock_ga):
        """__init__ sets forests_dir from module constant."""
        gen = RSIForestGenerator()
        self.assertEqual(gen.forests_dir, mock_dir)


class TestGenerateForest(TestCase):
    """Test generate_forest method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_dir = patch(
            "vsf_rsi.rsi_forest_generator.FORESTS_DIR",
            self._tmpdir
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_forest_generator.MANIFEST_FILE",
            self._tmpdir / "manifest.vsm"
        )
        self._patcher_ga = patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
        self._mock_ga_cls = self._patcher_ga.start()
        self._mock_ga = self._mock_ga_cls.return_value
        self._patcher_dir.start()
        self._patcher_manifest.start()
        self.gen = RSIForestGenerator()

    def tearDown(self):
        self._patcher_dir.stop()
        self._patcher_manifest.stop()
        self._patcher_ga.stop()

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_generate_returns_dir_path(self, mock_load, mock_save):
        """generate_forest returns a path string."""
        mock_load.return_value = {"forests": []}
        # Create mock genomes
        genome1 = MagicMock()
        genome1.id = "p_0"
        genome1.name = "p_tree_0"
        genome1.fitness = 0.5
        genome1.generation = 0
        genome1.genes = {"branches": []}
        self._mock_ga.create_forest.return_value = [genome1]

        result = self.gen.generate_forest("test_pred", population_size=1)
        self.assertIsInstance(result, str)

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_generate_creates_forest_dir(self, mock_load, mock_save):
        """generate_forest creates a subdirectory for the predicate."""
        mock_load.return_value = {"forests": []}
        genome = MagicMock()
        genome.id = "g1"
        genome.name = "p_tree_0"
        genome.fitness = 0.5
        genome.generation = 0
        genome.genes = {"branches": []}
        self._mock_ga.create_forest.return_value = [genome]

        result = self.gen.generate_forest("my_pred")
        forest_dir = Path(result)
        self.assertTrue(forest_dir.exists())
        self.assertTrue(forest_dir.is_dir())

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_generate_writes_forest_json(self, mock_load, mock_save):
        """generate_forest writes forest.json metadata file."""
        mock_load.return_value = {"forests": []}
        genome = MagicMock()
        genome.id = "g1"
        genome.name = "p_tree_0"
        genome.fitness = 0.85
        genome.generation = 0
        genome.genes = {"branches": []}
        self._mock_ga.create_forest.return_value = [genome]

        result = self.gen.generate_forest("my_pred")
        forest_json = Path(result) / "forest.json"
        self.assertTrue(forest_json.exists())
        data = json.loads(forest_json.read_text())
        self.assertEqual(data["predicate"], "my_pred")
        self.assertEqual(len(data["trees"]), 1)
        self.assertAlmostEqual(data["trees"][0]["fitness"], 0.85)

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_generate_creates_vsm_tree_files(self, mock_load, mock_save):
        """generate_forest creates .tree.vsm files for each genome."""
        mock_load.return_value = {"forests": []}
        g1 = MagicMock()
        g1.id = "g1"; g1.name = "tree_a"; g1.fitness = 0.5
        g1.generation = 0; g1.genes = {"branches": [{"condition": "TRUE", "action": '{"home": "ok"}'}]}
        g2 = MagicMock()
        g2.id = "g2"; g2.name = "tree_b"; g2.fitness = 0.7
        g2.generation = 0; g2.genes = {"branches": []}
        self._mock_ga.create_forest.return_value = [g1, g2]

        result = self.gen.generate_forest("my_pred", population_size=2)
        forest_dir = Path(result)
        self.assertTrue((forest_dir / "tree_a.tree.vsm").exists())
        self.assertTrue((forest_dir / "tree_b.tree.vsm").exists())

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_generate_registers_manifest(self, mock_load, mock_save):
        """generate_forest registers the forest in the manifest."""
        mock_load.return_value = {"forests": []}
        genome = MagicMock()
        genome.id = "g1"; genome.name = "t"; genome.fitness = 0.5
        genome.generation = 0; genome.genes = {"branches": []}
        self._mock_ga.create_forest.return_value = [genome]

        self.gen.generate_forest("my_pred")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        self.assertEqual(len(saved["forests"]), 1)
        self.assertEqual(saved["forests"][0]["predicate"], "my_pred")

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_generate_calls_ga_create_forest(self, mock_load, mock_save):
        """generate_forest delegates to ga.create_forest."""
        mock_load.return_value = {"forests": []}
        genome = MagicMock()
        genome.id = "g1"; genome.name = "t"; genome.fitness = 0.5
        genome.generation = 0; genome.genes = {"branches": []}
        self._mock_ga.create_forest.return_value = [genome]

        self.gen.generate_forest("my_pred", population_size=5)
        self._mock_ga.create_forest.assert_called_once_with("my_pred")


class TestEvolveForest(TestCase):
    """Test evolve_forest method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_dir = patch(
            "vsf_rsi.rsi_forest_generator.FORESTS_DIR",
            self._tmpdir
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_forest_generator.MANIFEST_FILE",
            self._tmpdir / "manifest.vsm"
        )
        self._patcher_ga = patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
        self._mock_ga_cls = self._patcher_ga.start()
        self._mock_ga = self._mock_ga_cls.return_value
        self._patcher_dir.start()
        self._patcher_manifest.start()
        self.gen = RSIForestGenerator()

    def tearDown(self):
        self._patcher_dir.stop()
        self._patcher_manifest.stop()
        self._patcher_ga.stop()

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_evolve_returns_result_dict(self, mock_load, mock_save):
        """evolve_forest returns a dict with expected keys."""
        mock_load.return_value = {"forests": []}
        genome = MagicMock()
        genome.id = "g1"; genome.name = "t"; genome.fitness = 0.9
        genome.generation = 10; genome.genes = {"branches": []}
        self._mock_ga.evolve_forest.return_value = {
            "final_forest": [genome],
            "best_tree": genome,
            "generations": 10,
            "improvement": 0.3
        }
        # Create forest dir so evolve can write to it
        forest_dir = self._tmpdir / "my_pred"
        forest_dir.mkdir(parents=True, exist_ok=True)

        result = self.gen.evolve_forest("my_pred", generations=10)
        self.assertIn("final_forest", result)
        self.assertIn("best_tree", result)
        self.assertIn("generations", result)
        self.assertIn("improvement", result)

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_evolve_calls_ga_evolve_forest(self, mock_load, mock_save):
        """evolve_forest delegates to ga.evolve_forest."""
        mock_load.return_value = {"forests": []}
        genome = MagicMock()
        genome.id = "g1"; genome.name = "t"; genome.fitness = 0.8
        genome.generation = 5; genome.genes = {"branches": []}
        self._mock_ga.evolve_forest.return_value = {
            "final_forest": [genome],
            "best_tree": genome,
            "generations": 5,
            "improvement": 0.2
        }
        forest_dir = self._tmpdir / "ev_pred"
        forest_dir.mkdir(parents=True, exist_ok=True)

        self.gen.evolve_forest("ev_pred", generations=5)
        self._mock_ga.evolve_forest.assert_called_once_with("ev_pred", 5)

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._save_manifest")
    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_evolve_updates_forest_json(self, mock_load, mock_save):
        """evolve_forest updates forest.json with evolution metadata."""
        mock_load.return_value = {"forests": []}
        genome = MagicMock()
        genome.id = "g1"; genome.name = "t"; genome.fitness = 0.95
        genome.generation = 10; genome.genes = {"branches": []}
        self._mock_ga.evolve_forest.return_value = {
            "final_forest": [genome],
            "best_tree": genome,
            "generations": 10,
            "improvement": 0.4
        }
        forest_dir = self._tmpdir / "evo_pred"
        forest_dir.mkdir(parents=True, exist_ok=True)

        self.gen.evolve_forest("evo_pred", generations=10)
        forest_json = forest_dir / "forest.json"
        self.assertTrue(forest_json.exists())
        data = json.loads(forest_json.read_text())
        self.assertIn("evolved", data)
        self.assertEqual(data["generations"], 10)
        self.assertAlmostEqual(data["best_fitness"], 0.95)


class TestGetForest(TestCase):
    """Test get_forest method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher = patch(
            "vsf_rsi.rsi_forest_generator.FORESTS_DIR",
            self._tmpdir
        )
        self._patcher_ga = patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
        self._patcher_ga.start()
        self._patcher.start()
        self.gen = RSIForestGenerator()

    def tearDown(self):
        self._patcher.stop()
        self._patcher_ga.stop()

    def test_get_forest_returns_none_when_missing(self):
        """get_forest returns None when forest doesn't exist."""
        result = self.gen.get_forest("nonexistent")
        self.assertIsNone(result)

    def test_get_forest_returns_metadata(self):
        """get_forest returns forest metadata dict when forest exists."""
        forest_dir = self._tmpdir / "my_pred"
        forest_dir.mkdir()
        forest_data = {
            "predicate": "my_pred",
            "population_size": 5,
            "trees": [{"id": "t1", "fitness": 0.8}],
            "created": "2026-01-01T00:00:00Z"
        }
        (forest_dir / "forest.json").write_text(json.dumps(forest_data))
        result = self.gen.get_forest("my_pred")
        self.assertIsNotNone(result)
        self.assertEqual(result["predicate"], "my_pred")
        self.assertEqual(len(result["trees"]), 1)


class TestGetBestTree(TestCase):
    """Test get_best_tree method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher = patch(
            "vsf_rsi.rsi_forest_generator.FORESTS_DIR",
            self._tmpdir
        )
        self._patcher_ga = patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
        self._patcher_ga.start()
        self._patcher.start()
        self.gen = RSIForestGenerator()

    def tearDown(self):
        self._patcher.stop()
        self._patcher_ga.stop()

    def test_get_best_tree_returns_none_when_missing(self):
        """get_best_tree returns None when no forest exists."""
        result = self.gen.get_best_tree("nonexistent")
        self.assertIsNone(result)

    def test_get_best_tree_returns_none_when_empty(self):
        """get_best_tree returns None when forest has no trees."""
        forest_dir = self._tmpdir / "empty_pred"
        forest_dir.mkdir()
        (forest_dir / "forest.json").write_text(json.dumps({
            "predicate": "empty_pred",
            "trees": []
        }))
        result = self.gen.get_best_tree("empty_pred")
        self.assertIsNone(result)

    def test_get_best_tree_returns_highest_fitness(self):
        """get_best_tree returns tree with highest fitness."""
        forest_dir = self._tmpdir / "best_pred"
        forest_dir.mkdir()
        forest_data = {
            "predicate": "best_pred",
            "trees": [
                {"id": "t1", "name": "low", "fitness": 0.3, "generation": 1},
                {"id": "t2", "name": "high", "fitness": 0.95, "generation": 5},
                {"id": "t3", "name": "mid", "fitness": 0.6, "generation": 3},
            ]
        }
        (forest_dir / "forest.json").write_text(json.dumps(forest_data))
        result = self.gen.get_best_tree("best_pred")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "high")
        self.assertAlmostEqual(result["fitness"], 0.95)

    def test_get_best_tree_single_tree(self):
        """get_best_tree returns the only tree when forest has one."""
        forest_dir = self._tmpdir / "single_pred"
        forest_dir.mkdir()
        forest_data = {
            "predicate": "single_pred",
            "trees": [
                {"id": "t1", "name": "only", "fitness": 0.7, "generation": 1}
            ]
        }
        (forest_dir / "forest.json").write_text(json.dumps(forest_data))
        result = self.gen.get_best_tree("single_pred")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "only")


class TestListForests(TestCase):
    """Test list_forests method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher = patch(
            "vsf_rsi.rsi_forest_generator.MANIFEST_FILE",
            self._tmpdir / "manifest.vsm"
        )
        self._patcher_ga = patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
        self._patcher_ga.start()
        self._patcher.start()
        self.gen = RSIForestGenerator()

    def tearDown(self):
        self._patcher.stop()
        self._patcher_ga.stop()

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_list_forests_empty(self, mock_load):
        """list_forests returns empty list when no forests."""
        mock_load.return_value = {"forests": []}
        result = self.gen.list_forests()
        self.assertEqual(result, [])

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_list_forests_returns_all(self, mock_load):
        """list_forests returns all forest entries."""
        mock_load.return_value = {
            "forests": [
                {"predicate": "p1", "population_size": 10},
                {"predicate": "p2", "population_size": 5},
            ]
        }
        result = self.gen.list_forests()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["predicate"], "p1")
        self.assertEqual(result[1]["predicate"], "p2")

    @patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator._load_manifest")
    def test_list_forests_missing_key(self, mock_load):
        """list_forests handles manifest with no forests key."""
        mock_load.return_value = {}
        result = self.gen.list_forests()
        self.assertEqual(result, [])
