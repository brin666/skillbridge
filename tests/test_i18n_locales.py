"""Basic locale consistency tests for frontend i18n files."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

UI_ROOT = Path(__file__).resolve().parents[1] / "ui"
LOCALE_DIR = UI_ROOT / "src" / "i18n" / "locales"


class LocaleTests(unittest.TestCase):
    def test_locales_exist_and_are_valid_json(self) -> None:
        for name in ("zh-CN.json", "en-US.json"):
            path = LOCALE_DIR / name
            self.assertTrue(path.is_file(), f"missing {name}")
            json.loads(path.read_text(encoding="utf-8"))

    def test_en_has_all_zh_keys(self) -> None:
        zh = json.loads((LOCALE_DIR / "zh-CN.json").read_text(encoding="utf-8"))
        en = json.loads((LOCALE_DIR / "en-US.json").read_text(encoding="utf-8"))

        def flatten(data, prefix=""):
            result = set()
            for key, value in data.items():
                full = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    result |= flatten(value, full)
                else:
                    result.add(full)
            return result

        missing = flatten(zh) - flatten(en)
        self.assertEqual(missing, set())


if __name__ == "__main__":
    unittest.main()
