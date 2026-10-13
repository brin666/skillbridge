"""Tests for bilingual summary generation and cache migration."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.cache_manager import CacheManager
from backend.core.skill_scanner import SkillScanner
from backend.core.summary.manager import SummaryManager


def make_skill(skill_dir: Path, description: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: pdf\ndescription: {description}\n---\n",
        encoding="utf-8",
    )


class BilingualSummaryTests(unittest.TestCase):
    def test_chinese_and_english_summaries(self) -> None:
        manager = SummaryManager()
        parsed = {"description": "Create, edit, inspect and render PDF documents.", "body": "", "tags": []}
        summaries = manager.generate_bilingual(parsed)
        self.assertIn("PDF", summaries["zh-CN"])
        self.assertIn("PDF", summaries["en-US"])
        self.assertIn("创建", summaries["zh-CN"])
        self.assertIn("Create", summaries["en-US"])

    def test_chinese_summary_translates_common_verb_forms(self) -> None:
        summary = SummaryManager().generate(
            {"description": "This skill edits PDF files.", "body": ""}
        )
        self.assertIn("编辑", summary)
        self.assertIn("PDF", summary)
        self.assertNotIn("edits", summary)

    def test_uncertain_offline_translation_preserves_the_complete_source(self) -> None:
        source = "Summarize an immersive quasar telemetry archive."
        summary = SummaryManager().generate({"description": source, "body": ""})

        self.assertEqual(summary, "Summarize an immersive quasar telemetry archive")

    def test_offline_rules_translate_common_skill_capability_phrases(self) -> None:
        manager = SummaryManager()
        storyboard = manager.generate(
            {"description": "Generate a set of storyboard style image prompts from a user's idea.", "body": ""}
        )
        research = manager.generate(
            {"description": "Research live opportunities and application requirements.", "body": ""}
        )
        desktop = manager.generate(
            {"description": "Drive the desktop in the background without stealing focus.", "body": ""}
        )
        portfolio = manager.generate(
            {"description": "Use for AI assistant UX analysis portfolio reports.", "body": ""}
        )

        self.assertEqual(storyboard, "根据用户的创意生成一组分镜风格图像提示词")
        self.assertEqual(research, "用于调研近期机会及其申请要求。")
        self.assertEqual(desktop, "在后台控制桌面，不抢占焦点")
        self.assertEqual(portfolio, "适用于分析 AI 助手使用体验并生成作品集报告")

    def test_offline_rules_cover_common_skill_catalog_copy(self) -> None:
        manager = SummaryManager()
        create_skill = manager.generate(
            {"description": "Create or update a Codex skill with appropriately scoped instructions and any needed supporting resources.", "body": ""}
        )
        review = manager.generate(
            {"description": "Perform a read-only, defect-first review of a specified code change and return every actionable finding.", "body": ""}
        )
        ui = manager.generate(
            {"description": "Stop coding agents from shipping generic UI.", "body": ""}
        )

        self.assertEqual(create_skill, "创建或更新 Codex 技能，并配套提供范围合适的说明和所需资源")
        self.assertEqual(review, "只读审查指定的代码变更，优先查找缺陷并列出所有可执行的修复项")
        self.assertEqual(ui, "避免编程 Agent 产出千篇一律的界面")

    def test_offline_rules_translate_common_project_skill_intros(self) -> None:
        manager = SummaryManager()
        docs = manager.generate(
            {"description": "Use for Codex models/pricing, scheduled tasks, skills, settings, setup, troubleshooting, customization, automations, and self-knowledge—including 'you,' 'your,' 'this app,' or 'this coding agent' when they refer to Codex—and for OpenAI APIs/products and ChatGPT Work.", "body": ""}
        )
        find_skills = manager.generate(
            {"description": "Helps users discover and install skills from the open agent skills ecosystem.", "body": ""}
        )
        game = manager.generate(
            {"description": "Design game experience, systems, and levels.", "body": ""}
        )
        find_skills_intro = manager.generate(
            {"description": "This skill helps you discover and install skills from the open agent skills ecosystem.", "body": ""}
        )
        citation = manager.generate(
            {"description": "Provide current, cited OpenAI product, API, model, and Codex guidance.", "body": ""}
        )
        ui = manager.generate(
            {"description": "Give your coding agent better UI taste.", "body": ""}
        )

        self.assertIn("用于查询 Codex 模型与定价", docs)
        self.assertTrue(citation.startswith("提供最新的 OpenAI"))
        self.assertIn("帮助用户在开放的 Agent 技能生态中发现并安装技能", find_skills)
        self.assertIn("帮助用户在开放的 Agent 技能生态中发现并安装技能", find_skills_intro)
        self.assertEqual(game, "设计游戏体验、系统与关卡")
        self.assertEqual(ui, "帮助编程 Agent 提升界面审美")

    def test_offline_rules_preserve_product_names_inside_chinese_summaries(self) -> None:
        summary = SummaryManager().generate(
            {"description": "After Effects and Three.js", "body": ""}
        )
        product_summary = SummaryManager().generate(
            {"description": "After Effects is GUI software, so this skill delivers knowledge and readytopaste assets — expressions, rig setups, export checklists, diagnostic flows, naming schemes, and ExtendScript — rather than a rendered file.", "body": ""}
        )

        self.assertIn("After Effects", summary)
        self.assertIn("Three.js", summary)
        self.assertNotIn("After 效果", summary)
        self.assertNotIn("三.js", summary)
        self.assertTrue(product_summary.startswith("After Effects 是图形界面软件"))

    def test_agent_invocation_instructions_do_not_replace_the_skill_overview(self) -> None:
        description = (
            "Build an animation from scratch, making the decisions in the order that determines whether it feels right "
            "— should it animate at all, what purpose, which tool, which properties, which curve and duration, "
            "how it interrupts, how it exits."
        )
        result = SummaryManager().analyze(
            {
                "description": description,
                "main_purpose": "When this skill is first invoked without a specific question, respond only with: I'm ready to build animations that feel right.",
                "body": "## Initial Response\n\nWhen this skill is first invoked without a specific question, respond only with:\n\n## Overview\n\nBuild animations from user requests.",
            }
        )

        self.assertTrue(result["summaries"]["zh-CN"].startswith("从零开始制作动画"))
        self.assertNotIn("first invoked", result["summaries"]["zh-CN"])
        self.assertTrue(result["features"]["zh-CN"])
        self.assertTrue(all("first invoked" not in item for item in result["features"]["en-US"]))

    def test_summary_can_reuse_a_clear_localized_capability_when_intro_is_untranslated(self) -> None:
        result = SummaryManager().analyze(
            {
                "description": "Summarize an immersive quasar telemetry archive.",
                "body": "## Features\n\n- An immersive quasar telemetry analysis workflow for advanced archives.\n- 游戏化拆书\n",
            }
        )

        self.assertEqual(result["summaries"]["zh-CN"], "游戏化拆书")
        self.assertEqual(len(result["features"]["zh-CN"]), 2)

    def test_metadata_without_a_documented_function_becomes_unknown(self) -> None:
        result = SummaryManager().analyze(
            {
                "description": "Author / Author: Example Person",
                "main_purpose": "Author / Author: Example Person",
                "body": "# Skill Title\n",
            }
        )

        self.assertEqual(result["summaries"]["zh-CN"], "未知")
        self.assertEqual(result["summaries"]["en-US"], "Unknown")
        self.assertEqual(result["features"]["zh-CN"], [])

    def test_chinese_summary_keeps_usage_phrase_compact(self) -> None:
        summary = SummaryManager().generate(
            {"description": "Use this skill when the user asks for a storyboard.", "body": ""}
        )
        self.assertIn("适用于用户需要分镜", summary)

    def test_mixed_language_description_translates_explanatory_english(self) -> None:
        summary = SummaryManager().generate(
            {"description": "生成或编辑 raster images for the current project, such as website assets.", "body": ""}
        )
        self.assertIn("位图", summary)
        self.assertIn("当前项目", summary)
        self.assertIn("网站素材", summary)
        self.assertNotIn("for the current project", summary)

    def test_summary_uses_only_the_purpose_sentence_not_exclusion_notes(self) -> None:
        summary = SummaryManager().generate(
            {"description": "Create images. Do not use for SVG editing.", "body": ""}
        )
        self.assertIn("创建", summary)
        self.assertNotIn("SVG", summary)

    def test_verbose_trigger_description_uses_concise_body_purpose(self) -> None:
        parsed = {
            "description": (
                "Generate or edit raster images when the task benefits from AI-created bitmap visuals "
                "such as photos, illustrations, textures, sprites, mockups, or transparent-background cutouts. "
                "Do not use when the task is better handled in code."
            ),
            "main_purpose": (
                "Generates or edits images for the current project (for example website assets, game assets, "
                "UI mockups, product mockups, wireframes, logo design, photorealistic images, or infographics)."
            ),
            "body": "",
        }

        result = SummaryManager().analyze(parsed)

        self.assertIn("当前项目", result["summaries"]["zh-CN"])
        self.assertNotIn("mockups", result["summaries"]["zh-CN"])
        self.assertTrue(result["features"]["zh-CN"])

    def test_common_product_and_browser_skills_get_natural_chinese(self) -> None:
        manager = SummaryManager()
        prd = manager.generate({"description": "Use when you need to generate a standardized PRD document.", "body": ""})
        browser = manager.generate({"description": "Configure Hermes to use Chrome quietly in the background.", "body": ""})
        agent = manager.generate({"description": "Use, configure, theme, extend, and orchestrate Hermes Agent.", "body": ""})

        self.assertIn("标准化 PRD 文档", prd)
        self.assertIn("后台", browser)
        self.assertNotIn("Configure", browser)
        self.assertEqual(agent, "管理 Hermes Agent，支持配置、主题定制、扩展与 Agent 编排")

    def test_drawixx_purpose_and_features_are_localized_without_losing_product_terms(self) -> None:
        parsed = {
            "description": (
                "Generate import-ready Markdown and create, read, or fully update live Drawixx structure maps "
                "with optional ASCII or Mermaid diagram blocks."
            ),
            "main_purpose": (
                "Create a clear, editable heading tree for Drawixx. "
                "Markdown is the only AIfacing representation: use it to read, create, and fully update live maps. "
                "Drawixx may render that tree on an editable canvas."
            ),
            "body": "",
        }

        result = SummaryManager().analyze(parsed)
        combined = " ".join(result["features"]["zh-CN"])

        self.assertIn("Drawixx", result["summaries"]["zh-CN"])
        self.assertIn("完整更新", combined)
        self.assertIn("可编辑画布", combined)
        self.assertNotIn("AIfacing", combined)
        self.assertNotIn("use it", combined)

    def test_mixed_skill_sentences_translate_common_auxiliaries_and_possessives(self) -> None:
        summary = SummaryManager().generate(
            {"description": "A task's size alone does not require subagents.", "body": ""}
        )
        self.assertIn("任务规模本身不需要", summary)
        self.assertNotIn("does", summary)
        self.assertNotIn("task's", summary)

    def test_cache_uses_summaries_without_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cache_dir = base / "cache"
            skill_root = base / "skills"
            skill_dir = skill_root / "pdf"
            make_skill(skill_dir, "Create PDF documents.")
            cache = CacheManager(cache_dir)
            scanner = SkillScanner(cache_manager=cache)
            skills = scanner.scan_skill_paths([skill_root], agent_id="codex")
            self.assertIn("zh-CN", skills[0].summaries)
            self.assertIn("en-US", skills[0].summaries)

            entry = cache.get("pdf")
            self.assertIn("summaries", entry)
            entry["summaries"]["zh-CN"] = "缓存中文"
            cache.set("pdf", entry)
            skills = scanner.scan_skill_paths([skill_root], agent_id="codex")
            self.assertEqual(skills[0].summaries["zh-CN"], "缓存中文")

    def test_hash_change_regenerates_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cache_dir = base / "cache"
            skill_root = base / "skills"
            skill_dir = skill_root / "pdf"
            make_skill(skill_dir, "Old description")
            cache = CacheManager(cache_dir)
            scanner = SkillScanner(cache_manager=cache)
            scanner.scan_skill_paths([skill_root], agent_id="codex")
            make_skill(skill_dir, "New PDF description")
            skills = scanner.scan_skill_paths([skill_root], agent_id="codex")
            self.assertNotEqual(skills[0].summaries["zh-CN"], "")

    def test_old_summary_cache_is_rebuilt_for_new_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            skill_root = base / "skills"
            skill_dir = skill_root / "pdf"
            make_skill(skill_dir, "Create PDF documents.")
            cache = CacheManager(base / "cache")
            scanner = SkillScanner(cache_manager=cache)
            scanner.scan_skill_paths([skill_root], agent_id="codex")

            entry = cache.get("pdf")
            entry["summary_pipeline_version"] = 1
            entry["summaries"] = {"zh-CN": "Old English cache", "en-US": "Old English cache"}
            cache.set("pdf", entry)

            skills = scanner.scan_skill_paths([skill_root], agent_id="codex")
            self.assertIn("创建", skills[0].summaries["zh-CN"])
            self.assertEqual(skills[0].summaries["en-US"], "Create PDF documents")
            self.assertEqual(cache.get("pdf")["summary_pipeline_version"], 25)


if __name__ == "__main__":
    unittest.main()
