import pathlib
import unittest


class PackagingMetadataTests(unittest.TestCase):
    def test_pyproject_declares_packages_and_console_script(self):
        text = pathlib.Path("pyproject.toml").read_text()
        self.assertIn('name = "agents-inc"', text)
        self.assertIn('"workerbees", "agents_inc._skills", "agents_inc._docs"', text)  # explicit packages list (D55)
        self.assertIn('agents-inc = "agents_inc.install.cli:main"', text)
        self.assertIn('agents_inc = ["*.json"]', text)


if __name__ == "__main__":
    unittest.main()
