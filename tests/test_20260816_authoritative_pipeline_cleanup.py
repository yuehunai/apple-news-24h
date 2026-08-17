import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apple_news_24h.py"


def load_module():
    spec = importlib.util.spec_from_file_location("apple_news_20260816_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def article_for(module, title, summary, source, facts=None):
    facts = facts or []
    tier, reason = module.classify_relevance_tier(title, summary, facts, source)
    return module.Article(
        source=source,
        url=f"https://example.com/{source}/{abs(hash((source, title)))}",
        title=title,
        summary=summary,
        key_facts=facts,
        category=module.choose_category(title, summary),
        published_utc=datetime(2026, 8, 16, tzinfo=timezone.utc),
        published_raw="2026-08-16T00:00:00Z",
        published_source="test",
        confidence="detail",
        tokens=module.article_tokens(title, " ".join([summary, *facts[:5]])),
        event_kind=module.detect_event_kind(title, summary, facts),
        relevance_tier=tier,
        relevance_reason=reason,
        regions=module.extract_regions(" ".join([title, summary, *facts[:5]])),
    )


class AuthoritativePipelineCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_background_apple_silicon_biography_cannot_promote_intel_driver_news(self):
        title = "Intel开源着色器编译器Jay迎来里程碑！Xe2/Xe3双平台通过Vulkan CTS认证"
        summary = (
            "Intel 的 Jay 编译器已通过 Vulkan CTS，并支持 Xe2 与 Xe3。"
            "项目负责人此前曾领导 Asahi Linux Apple Silicon 图形驱动开发。"
        )
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(tier, "weak", reason)

    def test_user_tool_for_old_mac_hardware_is_not_a_mac_product_roadmap(self):
        title = (
            "2019 款英特尔 MacBook Pro 运行 Windows 严重发热？"
            "苹果用户为其适配 48Hz 刷新率，让显卡功耗降低近八成同时大幅降温"
        )
        summary = (
            "用户自定义 48Hz 刷新率后，空闲 GPU 功耗从 14W 降至 3W，GPU 降温 15℃，"
            "还延长续航减少风扇噪音，目前已发布自制开源工具。#MacBook Pro# #苹果# "
            "IT之家 8 月 15 日消息，据 Wccftech 今日报道，Reddit 用户 stlk0 通过自制开源工具，"
            "将其搭载英特尔酷睿 i9 处理器的 2019 款 MacBook Pro 在 Windows Boot Camp 下的"
            "空闲 GPU 功耗从 14W 降至 3W，降幅近 80%。同时，其搭载的 AMD Radeon Pro 5300M "
            "显卡温度也从 66℃ 降至 51℃。据介绍，这位用户由于日常工作需要，长期通过 Boot Camp "
            "在 MacBook 上运行 Windows 系统，而不是使用 macOS，但此模式下设备不仅耗电更快，"
            "发热也更为严重。在尝试限制 CPU 功耗、关闭 Turbo Boost 及调整电源计划等方案均未奏效后，"
            "他发现 Radeon Pro 5300M 在屏幕以 60Hz 刷新率运行时，显存频率在空闲状态下仍维持高位。"
        )
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(tier, "weak", reason)

    def test_cross_platform_security_statistics_are_not_an_apple_vulnerability(self):
        title = "安全公司 Surfshark：微软 Windows 用户遭遇恶意软件攻击频率约为苹果 macOS 的 6 倍"
        summary = (
            "Surfshark 汇总其反病毒产品的检测记录并比较 Windows 与 macOS，"
            "Windows 用户占活跃用户的 66%，但贡献了 92% 的恶意软件检测事件。"
        )
        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "IT之家")
        self.assertEqual(identity.scope, "third-party-context")
        self.assertEqual(tier, "weak", reason)

    def test_unsourced_multi_product_smart_home_roadmap_is_an_editorial_roundup(self):
        title = "Apple has a huge product roadmap for the smart home: Here’s what’s coming - 9to5Mac"
        summary = (
            "The article collects previously reported expectations for HomePod mini, Apple TV 4K, "
            "a seven-inch home hub, and a later tabletop robot. It does not cite a new report."
        )
        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "9to5Mac")
        self.assertEqual(identity.content_form, "roundup")
        self.assertEqual(tier, "weak", reason)

    def test_title_led_apple_product_price_forecast_outranks_competitor_comparison(self):
        title = "史上最贵！iPhone Ultra顶配版售价有望突破2万元：跟华为三折叠价格相当"
        summary = (
            "消息人士预计苹果首款折叠屏 iPhone Ultra 起售价约 1.5 万元，"
            "顶配可能超过 2 万元；华为机型只用于价格比较。"
        )
        identity = self.module.title_led_identity(title, summary)
        tier, reason = self.module.classify_relevance_tier(title, summary, [], "快科技")
        self.assertEqual(identity.scope, "apple-direct")
        self.assertIn("price-change", identity.title_actions)
        self.assertEqual(tier, "strong", reason)

    def test_identical_cross_source_headline_merges_despite_body_extraction_differences(self):
        base_title = "苹果折叠屏将冲击行业TOP3：和三星华为形成三足鼎立之势"
        first = article_for(
            self.module,
            base_title,
            "Counterpoint 预计苹果折叠屏将推动市场增长 21%，并可能进入单品前三。",
            "快科技",
            ["苹果折叠屏的产能如果充足，明年第一季度有望进入单品前三。"],
        )
        second = article_for(
            self.module,
            f"{base_title} - Apple 苹果 - cnBeta.COM",
            (
                "同一报道还列出 A20 Pro、12GB 内存、5500mAh 电池和双 4800 万像素相机，"
                "但主体动作仍是同一份市场预测。"
            ),
            "cnBeta",
            ["Counterpoint 预计 2026 年折叠屏市场增长 21%。"],
        )
        groups = self.module.reconcile_articles(
            [first, second],
            profile_for=self.module.article_reconciliation_profile,
            initial_groups=[[first], [second]],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual({article.source for article in groups[0]}, {"快科技", "cnBeta"})


if __name__ == "__main__":
    unittest.main()
