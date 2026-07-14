import importlib
import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


class QlxConfigTests(unittest.TestCase):
    def test_env_int_falls_back_on_invalid_value(self):
        import qlx_config

        self.assertEqual(qlx_config.env_int("NO_SUCH_ENV_FOR_TEST", 123), 123)
        os.environ["QLX_TEST_BAD_INT"] = "not-a-number"
        try:
            self.assertEqual(qlx_config.env_int("QLX_TEST_BAD_INT", 456), 456)
        finally:
            os.environ.pop("QLX_TEST_BAD_INT", None)

    def test_env_str_ignores_blank_value(self):
        import qlx_config

        os.environ["QLX_TEST_BLANK"] = "   "
        try:
            self.assertEqual(qlx_config.env_str("QLX_TEST_BLANK", "fallback"), "fallback")
        finally:
            os.environ.pop("QLX_TEST_BLANK", None)

    def test_env_bool_parses_false_values(self):
        import qlx_config

        os.environ["QLX_TEST_BOOL"] = "0"
        try:
            self.assertFalse(qlx_config.env_bool("QLX_TEST_BOOL", True))
        finally:
            os.environ.pop("QLX_TEST_BOOL", None)

    def test_config_reads_port_from_env(self):
        os.environ["QLX_SERVER_PORT"] = "8999"
        try:
            import qlx_config

            reloaded = importlib.reload(qlx_config)
            self.assertEqual(reloaded.SERVER_PORT, 8999)
        finally:
            os.environ.pop("QLX_SERVER_PORT", None)
            import qlx_config

            importlib.reload(qlx_config)


if __name__ == "__main__":
    unittest.main()


