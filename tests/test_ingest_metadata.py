import json
import tempfile
import unittest
from pathlib import Path

from ingest import write_metadata


class MetadataTests(unittest.TestCase):
    def test_write_metadata_persists_rounded_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_metadata(out, 331.000454)

            self.assertEqual(json.loads((out / "metadata.json").read_text()), {"duration": 331.0})


if __name__ == "__main__":
    unittest.main()
