"""Verify output settings used by live dashboard edits."""

import importlib.util
import sys
import unittest

from test_config_http import PLUGIN_ROOT

name = "web_analyzer_test_package.core.result_formatter"
if name not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_ROOT / "core/result_formatter.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
ResultFormatter = sys.modules[name].ResultFormatter


class ResultSettingsTests(unittest.TestCase):
    def setUp(self):
        self.formatter = ResultFormatter(enable_emoji=False, enable_statistics=False)
        self.data = {
            "title": "<Page>",
            "content": "Article body",
            "url": "https://example.test",
        }

    def test_custom_preset_uses_template_without_separate_enable_switch(self):
        text = self.formatter.apply_result_settings(
            "Summary",
            self.data["url"],
            self.data,
            result_template="custom",
            template_content="{title}: {analysis_result}",
        )
        self.assertEqual(text, "<Page>: Summary")

    def test_html_template_escapes_inserted_page_content(self):
        text = self.formatter.apply_result_settings(
            "<script>bad</script>",
            self.data["url"],
            self.data,
            enable_custom_template=True,
            template_content="<h1>{title}</h1>{analysis_result}",
            template_format="html",
        )
        self.assertIn("<h1>&lt;Page&gt;</h1>", text)
        self.assertNotIn("<script>", text)

    def test_plain_template_removes_html_markup(self):
        text = self.formatter.apply_result_settings(
            "Summary",
            self.data["url"],
            self.data,
            enable_custom_template=True,
            template_content="<h1>Heading</h1><p>{analysis_result}</p>",
            template_format="plain",
        )
        self.assertNotIn("<h1>", text)
        self.assertIn("Summary", text)

    def test_statistics_flag_applies_to_custom_template(self):
        args = {"enable_custom_template": True, "template_content": "{stats}"}
        self.assertEqual(
            self.formatter.apply_result_settings(
                "", self.data["url"], self.data, **args
            ),
            "",
        )
        self.formatter.enable_statistics = True
        self.assertIn(
            "字符数",
            self.formatter.apply_result_settings(
                "", self.data["url"], self.data, **args
            ),
        )

    def test_detailed_template_obeys_emoji_setting(self):
        text = self.formatter.apply_result_settings(
            "Summary", self.data["url"], result_template="detailed"
        )
        self.assertNotIn("📌", text)
        self.formatter.enable_emoji = True
        self.assertIn(
            "📌",
            self.formatter.apply_result_settings(
                "Summary", self.data["url"], result_template="detailed"
            ),
        )


if __name__ == "__main__":
    unittest.main()
