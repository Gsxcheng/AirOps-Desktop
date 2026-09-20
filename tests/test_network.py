import unittest

from airops_desktop.network import _command_read_policy, _looks_like_cli_prompt


class NetworkTests(unittest.TestCase):
    def test_prompt_detection(self):
        self.assertTrue(_looks_like_cli_prompt("switch-01#"))
        self.assertTrue(_looks_like_cli_prompt("<HUAWEI>"))
        self.assertTrue(_looks_like_cli_prompt("[HUAWEI]"))
        self.assertFalse(_looks_like_cli_prompt("ordinary output"))

    def test_large_config_has_long_safety_ceiling(self):
        policy = _command_read_policy("display current-configuration", 30)
        self.assertGreaterEqual(policy["hard_timeout"], 3600)
        self.assertGreaterEqual(policy["idle_fallback"], 30)


if __name__ == "__main__":
    unittest.main()
