#!/usr/bin/env python3
"""Collect recent Apple software and hardware news for the apple-news-24h skill.

The script intentionally uses Python's standard library only so it can run from
Codex automations without dependency setup. It discovers candidates from fixed
RSS/channel sources, opens detail pages to verify timestamps, clusters duplicate
coverage into events, and emits JSON or a Markdown draft.
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except Exception:  # pragma: no cover - zoneinfo exists on supported Python 3.
    ZoneInfo = None  # type: ignore[assignment]

    class ZoneInfoNotFoundError(Exception):
        pass


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 CodexAppleNews24h/1.0"
)

MAX_RESPONSE_BYTES = 4_000_000
MAX_FEEDS_FROM_OPML = 20
MAX_PAGE_LINKS = 240
DEFAULT_MAX_DETAIL_PAGES = 380
FETCH_TIMEOUT = 8.0
FETCH_RETRIES = 1
DEFAULT_CACHE_DIR = Path(tempfile.gettempdir()) / "apple-news-24h"
CACHE_MARKER_FILENAME = ".apple-news-24h-cache"
FINAL_BRIEF_ITEM_COVERAGE_RULE = (
    "Every eligible JSON event is a required final-brief boundary unless source review proves "
    "duplicate coverage of the same subject and action or a clear exclusion rule."
)
FINAL_BRIEF_OMISSION_NOT_ALLOWED_FOR = [
    "single_source",
    "speculative_or_rumor",
    "lower_prominence",
    "competitor_or_third_party_context",
    "same_day_major_news",
]

TIMEZONE_ABBREVIATIONS = {
    "UTC": timezone.utc,
    "GMT": timezone.utc,
    "Z": timezone.utc,
    "PST": timezone(timedelta(hours=-8), "PST"),
    "PDT": timezone(timedelta(hours=-7), "PDT"),
    "MST": timezone(timedelta(hours=-7), "MST"),
    "MDT": timezone(timedelta(hours=-6), "MDT"),
    "CST": timezone(timedelta(hours=-6), "CST"),
    "CDT": timezone(timedelta(hours=-5), "CDT"),
    "EST": timezone(timedelta(hours=-5), "EST"),
    "EDT": timezone(timedelta(hours=-4), "EDT"),
}

GENERIC_TIMEZONES = {
    "PT": "America/Los_Angeles",
    "ET": "America/New_York",
}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

APPLE_TERMS = [
    "apple",
    "wwdc",
    "iphone",
    "ipad",
    "mac",
    "macbook",
    "imac",
    "mac mini",
    "mac studio",
    "mac pro",
    "ios",
    "ipados",
    "macos",
    "watchos",
    "tvos",
    "visionos",
    "airpods",
    "apple watch",
    "vision pro",
    "homepod",
    "beats",
    "safari",
    "siri",
    "icloud",
    "airdrop",
    "隔空投送",
    "imessage",
    "messages app",
    "apple messages",
    "apple messages for business",
    "facetime",
    "app store",
    "apple music",
    "apple tv",
    "apple arcade",
    "apple one",
    "apple pay",
    "apple card",
    "carplay",
    "xcode",
    "swift",
    "apple intelligence",
    "m1",
    "m2",
    "m3",
    "m4",
    "m5",
    "m6",
    "c1",
    "c2",
    "苹果",
    "苹果公司",
    "苹果手机",
    "苹果电脑",
    "苹果智能",
    "苹果音乐",
    "苹果电视",
    "苹果支付",
    "苹果卡",
    "苹果手表",
    "苹果芯片",
    "苹果应用商店",
    "苹果商务消息",
    "商务消息",
    "库克",
]

BARE_APPLE_CHIP_TERMS = {"m1", "m2", "m3", "m4", "m5", "m6", "c1", "c2"}

APPLE_CHIP_CONTEXT_TERMS = [
    "apple",
    "apple silicon",
    "mac",
    "macbook",
    "imac",
    "mac mini",
    "mac studio",
    "mac pro",
    "ipad",
    "iphone",
    "vision pro",
    "苹果",
    "苹果芯片",
    "苹果电脑",
    "苹果手机",
]

POSITIVE_ACTION_TERMS = [
    "release",
    "released",
    "launch",
    "launched",
    "roll out",
    "rolling out",
    "available",
    "availability",
    "expand",
    "expanded",
    "update",
    "updated",
    "beta",
    "rc",
    "security",
    "vulnerability",
    "exploit",
    "patch",
    "fix",
    "bug",
    "feature",
    "features",
    "add",
    "adds",
    "added",
    "revamp",
    "revamps",
    "revamped",
    "drop support",
    "drops support",
    "resize",
    "resizes",
    "customize",
    "customise",
    "customization",
    "customisation",
    "let you",
    "lets you",
    "will let",
    "developer beta",
    "service",
    "support",
    "legal",
    "lawsuit",
    "subpoena",
    "doj",
    "court",
    "investigation",
    "government",
    "law enforcement",
    "data request",
    "regulatory",
    "antitrust",
    "privacy",
    "modem",
    "chip",
    "supplier",
    "production",
    "shipment",
    "manufacturing",
    "factory",
    "grow",
    "grew",
    "growth",
    "increase",
    "increased",
    "gain",
    "gained",
    "market share",
    "shipments",
    "rank",
    "ranks",
    "ranking",
    "quality index",
    "confirmed",
    "approved",
    "approval",
    "integrate",
    "integrated",
    "integration",
    "cast",
    "casting",
    "star",
    "starring",
    "original film",
    "movie",
    "series",
    "season",
    "streaming",
    "tariff",
    "donate",
    "donates",
    "donated",
    "donating",
    "donation",
    "relief efforts",
    "executive",
    "store",
    "policy",
    "发布",
    "推出",
    "上线",
    "更新",
    "新增",
    "优化",
    "改进",
    "调整",
    "适配",
    "修复",
    "漏洞",
    "安全",
    "测试版",
    "候选版",
    "扩展",
    "支持",
    "可用",
    "隐私",
    "诉讼",
    "传票",
    "法院",
    "调查",
    "司法部",
    "执法",
    "政府请求",
    "监管",
    "芯片",
    "调制解调器",
    "供应",
    "量产",
    "出货",
    "出货量",
    "份额",
    "增长",
    "排名",
    "榜单",
    "主演",
    "参演",
    "电影",
    "剧集",
    "下架",
    "恢复",
    "政策",
    "批准",
    "接入",
    "智能体",
    "成为首个",
    "首个",
]

EXCLUDE_TERMS = [
    "deal",
    "deals",
    "discount",
    "coupon",
    "promo",
    "sale",
    "record low price",
    "gift card",
    "best buy",
    "amazon sale",
    "how to",
    "guide",
    "tips",
    "tricks",
    "wallpaper",
    "newsletter",
    "roundup",
    "buying guide",
    "review",
    "hands-on",
    "bad time to buy",
    "should you buy",
    "want to upgrade",
    "why i use",
    "i use every day",
    "task manager",
    "award",
    "prestigious award",
    "优惠",
    "促销",
    "降价",
    "购买指南",
    "教程",
    "技巧",
    "播客",
    "壁纸",
    "评测",
]

URL_EXCLUDE_FRAGMENTS = [
    "/deals/",
    "/best-",
    "/buyersguide",
    "buyersguide.",
    "forums.",
    "/guide/",
    "/guides/",
    "/review/",
    "review",
    "/happy-hour",
    "/daily-",
    "podcast",
    "homekit-weekly",
    "mactracker",
    "/tag/podcast",
    "/tags/",
    "/newsroom/apple-stories",
]

HARD_EXCLUDE_TERMS = [
    "appleinsider podcast",
    "chatgpt mac users",
    "codex remote access",
    "codex to chatgpt",
    "fake apple",
    "homekit weekly",
    "macrumors show",
    "mactracker",
    "microsoft",
    "deals:",
    "giveaway",
    "record low",
    "upgrade decision",
    "mystery left",
    "amazon",
    "best buy",
    "switchbot",
    "windows 11",
    "qoder",
    "agenui",
    "hbm",
    "magflow",
    "alipay",
    "nintendo switch",
    "libernovo",
    "华为手机",
    "华为两款",
    "阿里",
    "高德",
    "三星",
    "绿联",
    "支付宝",
    "任天堂",
    "罗永浩",
    "微软确认",
]

NON_OVERRIDABLE_HARD_EXCLUDE_TERMS = [
    "appleinsider podcast",
    "deals:",
    "giveaway",
    "record low",
    "upgrade decision",
    "amazon",
    "best buy",
    "switchbot",
    "homekit weekly",
    "macrumors show",
    "mactracker",
]

STRONG_NEWS_ACTION_TERMS = [
    "adopt",
    "adopts",
    "adopted",
    "announce",
    "announced",
    "available",
    "availability",
    "expand",
    "expanded",
    "fix",
    "fixed",
    "launch",
    "launched",
    "legal",
    "lawsuit",
    "subpoena",
    "doj",
    "court",
    "investigation",
    "government",
    "law enforcement",
    "data request",
    "patch",
    "patched",
    "production",
    "grow",
    "grew",
    "growth",
    "increase",
    "increased",
    "gain",
    "gained",
    "market share",
    "shipments",
    "rank",
    "ranks",
    "ranking",
    "quality index",
    "release",
    "released",
    "wwdc",
    "roll out",
    "rolling out",
    "security",
    "supplier",
    "support",
    "testing",
    "confirmed",
    "cast",
    "casting",
    "star",
    "starring",
    "original film",
    "movie",
    "series",
    "season",
    "streaming",
    "update",
    "updated",
    "add",
    "adds",
    "added",
    "revamp",
    "revamps",
    "revamped",
    "drop support",
    "drops support",
    "resize",
    "resizes",
    "customize",
    "customise",
    "customization",
    "customisation",
    "let you",
    "lets you",
    "will let",
    "developer beta",
    "vulnerability",
    "发布",
    "推出",
    "上线",
    "更新",
    "新增",
    "优化",
    "改进",
    "调整",
    "适配",
    "出货量",
    "份额",
    "增长",
    "排名",
    "榜单",
    "主演",
    "参演",
    "电影",
    "剧集",
    "修复",
    "漏洞",
    "安全",
    "扩展",
    "支持",
    "可用",
    "诉讼",
    "传票",
    "法院",
    "调查",
    "司法部",
    "执法",
    "监管",
    "量产",
    "供应",
]

SOFTWARE_TERMS = [
    "ios",
    "ipados",
    "macos",
    "watchos",
    "tvos",
    "visionos",
    "beta",
    "rc",
    "security",
    "vulnerability",
    "exploit",
    "patch",
    "fix",
    "bug",
    "safari",
    "siri",
    "icloud",
    "app store",
    "apple music",
    "apple tv",
    "apple arcade",
    "apple one",
    "apple pay",
    "apple card",
    "airdrop",
    "隔空投送",
    "carplay",
    "apple intelligence",
    "hls",
    "podcast",
    "streaming",
    "xcode",
    "swift",
    "openai",
    "chatgpt",
    "health",
    "hearing",
    "hypertension",
    "sleep apnea",
    "service",
    "privacy",
    "enterprise",
    "软件",
    "系统",
    "服务",
    "更新",
    "漏洞",
    "安全",
    "修复",
    "测试版",
    "隐私",
    "健康",
    "助听",
    "高血压",
    "睡眠呼吸暂停",
]

HARDWARE_TERMS = [
    "iphone",
    "ipad",
    "mac",
    "macbook",
    "imac",
    "mac mini",
    "mac studio",
    "mac pro",
    "apple watch",
    "airpods",
    "vision pro",
    "homepod",
    "beats",
    "chip",
    "modem",
    "display",
    "camera",
    "battery",
    "supplier",
    "production",
    "manufacturing",
    "shipment",
    "factory",
    "m1",
    "m2",
    "m3",
    "m4",
    "m5",
    "m6",
    "c1",
    "c2",
    "硬件",
    "芯片",
    "调制解调器",
    "供应",
    "量产",
    "出货",
    "生产",
    "相机",
    "屏幕",
    "电池",
]

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "amid",
    "apple",
    "available",
    "because",
    "been",
    "being",
    "could",
    "from",
    "gets",
    "have",
    "here",
    "into",
    "just",
    "latest",
    "like",
    "more",
    "most",
    "news",
    "over",
    "report",
    "reportedly",
    "says",
    "than",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "through",
    "update",
    "with",
    "without",
    "will",
    "your",
}

GENERIC_MERGE_TOKENS = STOPWORDS | {
    "and",
    "are",
    "article",
    "blog",
    "for",
    "its",
    "media",
    "post",
    "published",
    "said",
    "software",
    "showcase",
    "shown",
    "the",
    "today",
    "when",
    "which",
    "year",
    "yesterday",
    "发布",
    "报道",
    "消息",
    "展示",
    "苹果",
}

GENERIC_SERVICE_CONTENT_MERGE_TOKENS = GENERIC_MERGE_TOKENS | {
    "and",
    "apple-music",
    "apple-one",
    "apple-tv",
    "content",
    "episode",
    "episodes",
    "film",
    "for",
    "movie",
    "music",
    "playlist",
    "require",
    "requires",
    "release",
    "releases",
    "reveal",
    "revealed",
    "reveals",
    "return",
    "coming",
    "current",
    "debut",
    "fall",
    "history",
    "soon",
    "status",
    "season",
    "series",
    "service",
    "show",
    "streaming",
    "subscription",
    "subscriptions",
    "sery",
    "the",
    "trial",
}

SERVICE_CONTENT_TOPIC_FACETS = {
    "apple-arcade",
    "apple-music",
    "apple-tv-content",
    "apple-tv-remote",
}

APP_STORE_POLICY_SUBTOPIC_FACETS = {
    "apple-pay-rewards",
    "epic-app-store-appeal",
    "uk-cma-app-store-payment-nfc",
}

BEATS_HARDWARE_MERGE_TOKENS = {
    "antonee",
    "robinson",
    "lamine",
    "yamal",
    "kang-in",
    "fcc",
    "studio",
    "studio-pro",
    "unreleased",
    "new-product",
    "next-generation",
    "two-tone",
    "royal-blue",
    "white",
    "headband",
    "ear-cup",
    "headphone",
    "headphones",
    "over-ear",
    "world-cup",
}

SOURCE_PRIORITY = {
    "MacRumors": 1,
    "9to5Mac": 2,
    "AppleInsider": 3,
    "The Verge": 4,
    "Apple Newsroom": 5,
    "IT之家": 6,
    "爱范儿": 7,
    "快科技": 8,
    "cnBeta": 9,
}

OFFICIAL_FACT_SOURCES = {"Apple Newsroom"}
MAX_KEY_FACTS = 18
MAX_OFFICIAL_KEY_FACTS = 24

MESSAGE_PLATFORM_TERMS = [
    "imessage",
    "messages app",
    "apple messages",
    "apple messages for business",
    "messages business chat",
    "apple's messages",
    "苹果商务消息",
    "商务消息",
    "苹果信息",
    "信息应用",
]

MESSAGE_AGENT_TERMS = [
    "ai agent",
    "ai assistant",
    "third-party ai",
    "proactive ai assistant",
    "poke",
    "智能体",
    "ai 助手",
    "第三方 ai",
]

MESSAGE_PLATFORM_ACTION_TERMS = [
    "approved",
    "approved for use",
    "available via",
    "officially available",
    "integrate",
    "integrated",
    "integration",
    "now has",
    "first third-party",
    "become the first",
    "批准",
    "接入",
    "成为首个",
    "首个接入",
    "首次接入",
]

DATA_VALUE_PATTERN = re.compile(
    r"(?i)(?:more than|over|nearly|about|approximately|around|at least|up to|"
    r"超过|逾|近|约|至少|高达|累计)?\s*(?:US\$|[$€£¥￥])?\s*"
    r"\d[\d,]*(?:\.\d+)?\s*(?:%|percent|percentage|billion|million|thousand|"
    r"万|亿|美元|元|人民币|个|款|项|次|名|份|台|家|座|"
    r"accounts?|users?|customers?|developers?|enrollments?|submissions?|apps?|"
    r"transactions?|ratings?|reviews?|countries?|regions?|markets?|storefronts?|"
    r"attempts?|cards?|devices?|models?|versions?|updates?|features?)?"
)

FEATURE_LIST_PATTERN = re.compile(
    r"(?i)\b(new|include|includes|including|feature|features|support|supports|"
    r"supported|adds?|added)\b|"
    r"包括|包含|新增|推出|支持|功能|特性"
)

FACT_CONTEXT_TERMS = (
    APPLE_TERMS
    + SOFTWARE_TERMS
    + HARDWARE_TERMS
    + [
        "app review",
        "storekit",
        "testflight",
        "developer",
        "developers",
        "account",
        "accounts",
        "transaction",
        "transactions",
        "rating",
        "ratings",
        "review",
        "reviews",
        "submission",
        "submissions",
        "country",
        "countries",
        "region",
        "regions",
        "market",
        "markets",
        "accessibility",
        "assistive",
        "health",
        "hearing",
        "braille",
        "caption",
        "captions",
        "magnifier",
        "开发者",
        "账户",
        "账号",
        "应用",
        "提交",
        "审核",
        "评分",
        "评论",
        "交易",
        "欺诈",
        "国家",
        "地区",
        "市场",
        "功能",
        "特性",
        "辅助功能",
        "健康",
        "助听",
        "盲文",
        "字幕",
        "放大器",
    ]
)

APPLE_RESEARCH_TERMS = [
    "research",
    "research paper",
    "research papers",
    "paper",
    "papers",
    "study",
    "studies",
    "conference",
    "cvpr",
    "ieee",
    "cvf",
    "computer vision",
    "machine learning",
    "artificial intelligence",
    "ai",
    "ml",
    "dataset",
    "model",
    "models",
    "论文",
    "研究",
    "研究论文",
    "会议",
    "计算机视觉",
    "机器学习",
    "人工智能",
    "模型",
]

APPLE_RESEARCH_ANCHOR_TERMS = [
    "research",
    "research paper",
    "research papers",
    "paper",
    "papers",
    "study",
    "studies",
    "cvpr",
    "ieee",
    "cvf",
    "computer vision",
    "academic conference",
    "research conference",
    "论文",
    "研究",
    "研究论文",
    "学术会议",
    "计算机视觉",
]

APPLE_RESEARCH_ACTION_TERMS = [
    "showcase",
    "showcased",
    "present",
    "presents",
    "presented",
    "presentation",
    "share",
    "shares",
    "shared",
    "publish",
    "publishes",
    "published",
    "participate",
    "participates",
    "participation",
    "accepted",
    "preview",
    "previews",
    "展示",
    "发表",
    "发布",
    "公布",
    "分享",
    "参与",
    "参会",
    "收录",
    "预热",
]

APPLE_HEALTH_RESEARCH_PRODUCT_TERMS = [
    "apple watch",
    "health app",
    "apple health",
    "researchkit",
    "carekit",
    "apple heart and movement study",
    "apple women's health study",
    "apple hearing study",
    "苹果手表",
    "健康 app",
    "健康应用",
    "苹果健康",
]

APPLE_HEALTH_DATA_TERMS = [
    "health data",
    "sleep data",
    "sleep patterns",
    "heart rate",
    "ecg",
    "electrocardiogram",
    "afib",
    "atrial fibrillation",
    "blood oxygen",
    "blood pressure",
    "hypertension",
    "cycle tracking",
    "menstrual",
    "mobility",
    "walking steadiness",
    "gait",
    "workout data",
    "sensor data",
    "watch data",
    "wearable data",
    "activity data",
    "健康数据",
    "睡眠数据",
    "睡眠模式",
    "心率",
    "心电图",
    "房颤",
    "血氧",
    "血压",
    "高血压",
    "经期",
    "月经",
    "活动数据",
    "传感器数据",
    "手表数据",
    "可穿戴数据",
]

APPLE_HEALTH_RESEARCH_ANCHOR_TERMS = [
    "researcher",
    "researchers",
    "study",
    "studies",
    "clinical study",
    "published",
    "analyzed",
    "analysis",
    "trial",
    "cohort",
    "participants",
    "findings",
    "peer-reviewed",
    "研究人员",
    "研究者",
    "研究",
    "论文",
    "发表",
    "发布",
    "分析",
    "临床",
    "参与者",
    "受试者",
    "队列",
    "结果",
]

HEALTH_RESEARCH_DATA_TOKENS = {
    term.lower().replace(" ", "-") for term in APPLE_HEALTH_DATA_TERMS if not any(ord(ch) > 127 for ch in term)
}
HEALTH_RESEARCH_CONTEXT_TOKENS = {
    "study",
    "studies",
    "research",
    "researcher",
    "researchers",
    "published",
    "analyzed",
    "analysis",
    "clinical",
    "trial",
    "cohort",
}

CROSS_LANGUAGE_TOKEN_MAP = {
    "find my": "find-my",
    "hide location": "hide-location",
    "location sharing": "location-sharing",
    "sharing duration": "sharing-duration",
    "英特尔": "intel",
    "台积电": "tsmc",
    "高通": "qualcomm",
    "芯片": "chip",
    "试产": "production",
    "量产": "production",
    "生产": "production",
    "基带": "modem",
    "调制解调器": "modem",
    "卫星": "satellite",
    "运营商": "carrier",
    "联网": "coverage",
    "信号": "coverage",
    "降价": "price",
    "涨价": "price-increase",
    "价格": "price",
    "售价": "price",
    "上调": "increase",
    "成本": "cost",
    "内存": "memory",
    "存储": "storage",
    "短缺": "shortage",
    "库克": "cook",
    "不可避免": "unavoidable",
    "中国": "china",
    "国行": "china",
    "股价": "stock",
    "收盘新高": "record",
    "马斯克": "musk",
    "取证": "discovery",
    "扩大": "expand",
    "漏洞": "vulnerability",
    "安全": "security",
    "入侵": "exploit",
    "不可修复": "unpatchable",
    "无法软件修复": "unpatchable",
    "查找": "find-my",
    "隐藏位置": "hide-location",
    "隐藏共享位置": "hide-location",
    "共享时长": "sharing-duration",
    "位置共享": "location-sharing",
    "巴西": "brazil",
    "应用商店": "app-store",
    "第三方应用商店": "alternative-marketplace",
    "替代应用市场": "alternative-marketplace",
    "第三方支付": "third-party-payment",
    "佣金": "commission",
    "欺诈": "fraud",
    "诈骗": "fraud",
    "开发者": "developer",
    "提交": "submission",
    "账户": "account",
    "账号": "account",
    "审核": "review",
    "交易": "transaction",
    "计算机视觉": "computer-vision",
    "人工智能": "ai",
    "机器学习": "machine-learning",
    "研究论文": "research-paper",
    "论文": "paper",
    "研究": "research",
    "研究人员": "researcher",
    "头戴式耳机": "headphones",
    "耳机": "headphones",
    "耳罩": "ear-cup",
    "头梁": "headband",
    "撞色": "two-tone",
    "皇家蓝": "royal-blue",
    "白色": "white",
    "未发布": "unreleased",
    "尚未发布": "unreleased",
    "新一代": "next-generation",
    "新款": "new-product",
    "世界杯": "world-cup",
    "球员": "athlete",
    "球星": "athlete",
    "迪士尼": "disney",
    "主题乐园": "theme-park",
    "乐园": "theme-park",
    "飞行项目": "ride",
    "景观": "landmark",
    "沉浸式": "immersive",
    "沉浸": "immersive",
    "空间计算": "spatial-computing",
    "美国": "america",
    "佛罗里达": "florida",
    "苹果手表": "apple-watch",
    "健康应用": "health-app",
    "苹果健康": "apple-health",
    "健康数据": "health-data",
    "睡眠数据": "sleep-data",
    "睡眠模式": "sleep-patterns",
    "心率": "heart-rate",
    "心电图": "ecg",
    "房颤": "afib",
    "血氧": "blood-oxygen",
    "血压": "blood-pressure",
    "会议": "conference",
    "展示": "showcase",
    "苹果": "apple",
}


@dataclass
class Source:
    name: str
    default_tz: str
    feeds: list[str] = field(default_factory=list)
    wordpress_posts_apis: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    domains: tuple[str, ...] = ()


@dataclass
class Candidate:
    source: str
    url: str
    title: str
    summary: str = ""
    feed_time_raw: str = ""
    discovered_from: str = ""
    context: str = ""


@dataclass
class Article:
    source: str
    url: str
    title: str
    summary: str
    key_facts: list[str]
    category: str
    published_utc: datetime
    published_raw: str
    published_source: str
    confidence: str
    tokens: set[str]
    event_kind: str = "general_company"
    relevance_tier: str = "strong"
    relevance_reason: str = ""
    regions: set[str] = field(default_factory=set)


@dataclass
class Event:
    event_id: str
    category: str
    title: str
    summary: str
    key_facts: list[str]
    published_utc: datetime
    published_raw: str
    published_source: str
    confidence: str
    articles: list[Article]
    tokens: set[str]
    event_kind: str = "general_company"
    relevance_tier: str = "strong"
    relevance_reason: str = ""
    regions: set[str] = field(default_factory=set)
    merge_warnings: list[str] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def zoneinfo_or_none(name: str | None) -> Any:
    if not name or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return None
    except Exception:
        return None


def detect_timezone(requested: str) -> tuple[Any, dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "requested": requested,
        "resolved": None,
        "method": None,
        "iana": False,
        "warnings": [],
    }

    if requested and requested != "auto":
        tz = zoneinfo_or_none(requested)
        if tz is not None:
            diagnostics.update({"resolved": requested, "method": "argument", "iana": True})
            return tz, diagnostics
        diagnostics["warnings"].append(f"Invalid --timezone value: {requested}")

    env_tz = os.environ.get("TZ")
    if env_tz:
        tz = zoneinfo_or_none(env_tz)
        if tz is not None:
            diagnostics.update({"resolved": env_tz, "method": "TZ", "iana": True})
            return tz, diagnostics
        diagnostics["warnings"].append(f"Invalid TZ environment value: {env_tz}")

    localtime = Path("/etc/localtime")
    try:
        real = localtime.resolve()
        text = str(real)
        marker = "/zoneinfo/"
        if marker in text:
            name = text.split(marker, 1)[1]
            tz = zoneinfo_or_none(name)
            if tz is not None:
                diagnostics.update(
                    {"resolved": name, "method": "/etc/localtime", "iana": True}
                )
                return tz, diagnostics
    except Exception as exc:
        diagnostics["warnings"].append(f"Could not inspect /etc/localtime: {exc}")

    try:
        result = subprocess.run(
            ["timedatectl"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
        match = re.search(r"Time zone:\s*([A-Za-z0-9_./+-]+)", result.stdout)
        if match:
            name = match.group(1)
            tz = zoneinfo_or_none(name)
            if tz is not None:
                diagnostics.update(
                    {"resolved": name, "method": "timedatectl", "iana": True}
                )
                return tz, diagnostics
    except Exception:
        pass

    tz = datetime.now().astimezone().tzinfo
    name = str(tz) if tz is not None else "UTC"
    diagnostics.update({"resolved": name, "method": "astimezone", "iana": False})
    diagnostics["warnings"].append(
        "Fell back to local UTC offset; DST-safe display names may be unavailable."
    )
    return tz or timezone.utc, diagnostics


def build_sources(now_local: datetime) -> list[Source]:
    dates = [now_local.date(), (now_local - timedelta(days=1)).date()]
    macrumors_pages = ["https://www.macrumors.com/"]
    nine_pages = ["https://9to5mac.com/"]
    for date in dates:
        macrumors_pages.append(
            f"https://www.macrumors.com/{date.year}/{date.month:02d}/{date.day:02d}/"
        )
        nine_pages.append(f"https://9to5mac.com/{date.year}/{date.month:02d}/{date.day:02d}/")

    return [
        Source(
            name="MacRumors",
            default_tz="America/Los_Angeles",
            feeds=["https://feeds.macrumors.com/MacRumors-All"],
            pages=macrumors_pages,
            domains=("macrumors.com", "www.macrumors.com"),
        ),
        Source(
            name="9to5Mac",
            default_tz="America/Los_Angeles",
            feeds=["https://9to5mac.com/feed/"],
            wordpress_posts_apis=[
                "https://9to5mac.com/wp-json/wp/v2/posts?per_page=40&_embed=wp:term&_fields=link,date_gmt,date,title,excerpt,_links.wp:term,_embedded.wp:term"
            ],
            pages=nine_pages,
            domains=("9to5mac.com",),
        ),
        Source(
            name="AppleInsider",
            default_tz="America/New_York",
            feeds=["https://appleinsider.com/rss/news/"],
            pages=["https://appleinsider.com/news"],
            domains=("appleinsider.com",),
        ),
        Source(
            name="The Verge",
            default_tz="America/New_York",
            feeds=[
                "https://www.theverge.com/rss/index.xml",
                "https://www.theverge.com/rss/apple/index.xml",
            ],
            pages=["https://www.theverge.com/apple", "https://www.theverge.com/tech"],
            domains=("theverge.com", "www.theverge.com"),
        ),
        Source(
            name="Apple Newsroom",
            default_tz="America/Los_Angeles",
            feeds=["https://www.apple.com/newsroom/rss-feed.rss"],
            pages=["https://www.apple.com/newsroom/"],
            domains=("apple.com", "www.apple.com"),
        ),
        Source(
            name="IT之家",
            default_tz="Asia/Shanghai",
            feeds=["https://www.ithome.com/rss/"],
            pages=[
                "https://www.ithome.com/",
                "https://www.ithome.com/apple/",
                "https://www.ithome.com/tags/%E8%8B%B9%E6%9E%9C/",
            ],
            domains=("ithome.com", "www.ithome.com"),
        ),
        Source(
            name="爱范儿",
            default_tz="Asia/Shanghai",
            feeds=["https://www.ifanr.com/feed", "http://live.ifanr.com/feed"],
            pages=["https://www.ifanr.com/"],
            domains=("ifanr.com", "www.ifanr.com", "live.ifanr.com"),
        ),
        Source(
            name="快科技",
            default_tz="Asia/Shanghai",
            feeds=["https://rss.mydrivers.com/opml.xml"],
            pages=["https://news.mydrivers.com/"],
            domains=("mydrivers.com", "news.mydrivers.com", "www.mydrivers.com"),
        ),
        Source(
            name="cnBeta",
            default_tz="Asia/Shanghai",
            feeds=["https://www.cnbeta.com.tw/backend.php"],
            pages=["https://www.cnbeta.com.tw/"],
            domains=("cnbeta.com.tw", "www.cnbeta.com.tw"),
        ),
    ]


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def prepare_cache_dir(cache_dir: Path, diagnostics: dict[str, Any]) -> Path:
    """Create a dedicated per-run cache directory and clear stale responses safely."""
    cache_dir = cache_dir.expanduser()
    resolved = cache_dir.resolve(strict=False)
    default_resolved = DEFAULT_CACHE_DIR.resolve(strict=False)
    diagnostics["cache"] = {
        "path": str(cache_dir),
        "resolved_path": str(resolved),
        "cleared_at": utc_now().isoformat(),
        "removed_entries": 0,
        "marker": CACHE_MARKER_FILENAME,
    }

    unsafe_targets = {Path("/").resolve(), Path("/tmp").resolve(strict=False)}
    try:
        unsafe_targets.add(Path.home().resolve())
    except Exception:
        pass
    if resolved in unsafe_targets:
        raise RuntimeError(f"Refusing to use unsafe cache directory: {cache_dir}")
    if cache_dir.exists() and cache_dir.is_symlink():
        raise RuntimeError(f"Refusing to clear symlinked cache directory: {cache_dir}")
    if cache_dir.exists() and not cache_dir.is_dir():
        raise RuntimeError(f"Cache path exists but is not a directory: {cache_dir}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    marker_path = cache_dir / CACHE_MARKER_FILENAME
    is_default_cache = resolved == default_resolved
    has_marker = marker_path.exists()
    existing_entries = list(cache_dir.iterdir())
    if not is_default_cache and not has_marker and existing_entries:
        raise RuntimeError(
            "Refusing to clear a non-default cache directory without the "
            f"{CACHE_MARKER_FILENAME} marker: {cache_dir}"
        )

    removed_entries = 0
    for entry in existing_entries:
        if entry.name == CACHE_MARKER_FILENAME:
            continue
        try:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed_entries += 1
        except FileNotFoundError:
            continue

    marker_path.write_text(
        "This directory is managed by apple-news-24h and is cleared at each run.\n",
        encoding="utf-8",
    )
    diagnostics["cache"]["removed_entries"] = removed_entries
    return cache_dir


def decode_response(raw: bytes, content_type: str | None) -> str:
    charset = None
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.I)
        if match:
            charset = match.group(1)
    if charset is None:
        head = raw[:2048].decode("ascii", errors="ignore")
        match = re.search(r"charset=['\"]?([A-Za-z0-9._-]+)", head, re.I)
        if match:
            charset = match.group(1)
    for encoding in [charset, "utf-8", "gb18030", "latin-1"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_url(
    url: str,
    cache_dir: Path,
    diagnostics: dict[str, Any],
    timeout: float | None = None,
    retries: int | None = None,
) -> str | None:
    url = iri_to_uri(url)
    timeout = FETCH_TIMEOUT if timeout is None else timeout
    retries = FETCH_RETRIES if retries is None else retries
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key(url)}.json"
    last_error = ""

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES)
                text = decode_response(raw, response.headers.get("content-type"))
                payload = {
                    "url": url,
                    "fetched_at": utc_now().isoformat(),
                    "status": getattr(response, "status", None),
                    "text": text,
                }
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                return text
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))

    diagnostics.setdefault("failed_fetches", []).append({"url": url, "error": last_error})
    return None


def iri_to_uri(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%:@")
    query = urllib.parse.quote(parts.query, safe="=&?/%:@,+")
    fragment = urllib.parse.quote(parts.fragment, safe="=&?/%:@,+")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def strip_tags(value: str) -> str:
    value = re.sub(r"(?is)<script\b.*?</script>", " ", value)
    value = re.sub(r"(?is)<style\b.*?</style>", " ", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def xml_text(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        name = child.tag.rsplit("}", 1)[-1].lower()
        if name in names and child.text:
            return strip_tags(child.text)
    return ""


def xml_text_raw(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        name = child.tag.rsplit("}", 1)[-1].lower()
        if name in names and child.text:
            return child.text
    return ""


def source_context_terms(raw_html: str, categories: list[str]) -> str:
    terms: list[str] = []

    def add(value: str) -> None:
        normalized = html.unescape(value).strip().lower()
        if not normalized:
            return
        normalized = normalized.replace("_", "-")
        for part in re.split(r"[,;/|]+", normalized):
            part = part.strip()
            if not part or part == "news":
                continue
            plain = part.replace("-", " ")
            if plain not in terms:
                terms.append(plain)

    for category in categories:
        add(category)
    for match in re.finditer(r"""data-layer-postcategory\s*=\s*['"]([^'"]+)['"]""", raw_html, re.I):
        add(match.group(1))
    return " ".join(terms)


def atom_link(element: ET.Element) -> str:
    for child in list(element):
        name = child.tag.rsplit("}", 1)[-1].lower()
        if name == "link":
            href = child.attrib.get("href")
            rel = child.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                return href.strip()
    return ""


def parse_xml_feed(text: str, source: Source, feed_url: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return candidates

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name == "opml":
        return candidates

    for item in root.iter():
        name = item.tag.rsplit("}", 1)[-1].lower()
        if name not in {"item", "entry"}:
            continue
        title = xml_text(item, {"title"})
        link = xml_text(item, {"link"})
        if not link:
            link = atom_link(item)
        raw_summary = xml_text_raw(item, {"description", "summary", "content", "encoded"})
        summary = strip_tags(raw_summary)
        published = xml_text(item, {"pubdate", "published", "updated", "dc:date"})
        categories = [
            strip_tags(child.text)
            for child in list(item)
            if child.tag.rsplit("}", 1)[-1].lower() == "category" and child.text
        ]
        context = source_context_terms(raw_summary, categories)
        if title and link:
            candidates.append(
                Candidate(
                    source=source.name,
                    url=urllib.parse.urljoin(feed_url, link),
                    title=title,
                    summary=summary,
                    feed_time_raw=published,
                    discovered_from=feed_url,
                    context=context,
                )
            )
    return candidates


def wordpress_rendered_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("rendered", "document_title", "raw"):
            rendered = value.get(key)
            if isinstance(rendered, str) and rendered.strip():
                return strip_tags(rendered)
        return ""
    if isinstance(value, str):
        return strip_tags(value)
    return ""


def wordpress_utc_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", cleaned):
        return f"{cleaned}+00:00"
    if cleaned.endswith("Z") or re.search(r"[+-]\d{2}:?\d{2}$", cleaned):
        return cleaned
    return cleaned


def parse_wordpress_posts_api(text: str, source: Source, api_url: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return candidates
    if not isinstance(payload, list):
        return candidates

    for item in payload:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        if not isinstance(link, str) or not link.strip():
            continue
        title = wordpress_rendered_text(item.get("title"))
        summary = wordpress_rendered_text(item.get("excerpt"))
        if not title:
            continue
        context_terms: list[str] = []
        embedded = item.get("_embedded")
        if isinstance(embedded, dict):
            term_groups = embedded.get("wp:term")
            if isinstance(term_groups, list):
                for group in term_groups:
                    if not isinstance(group, list):
                        continue
                    for term in group:
                        if not isinstance(term, dict):
                            continue
                        for key in ("name", "slug"):
                            value = term.get(key)
                            if isinstance(value, str) and value.strip():
                                context_terms.append(strip_tags(value).replace("-", " "))
        feed_time_raw = wordpress_utc_timestamp(item.get("date_gmt")) or wordpress_utc_timestamp(
            item.get("date")
        )
        candidates.append(
            Candidate(
                source=source.name,
                url=urllib.parse.urljoin(api_url, html.unescape(link.strip())),
                title=title,
                summary=summary,
                feed_time_raw=feed_time_raw,
                discovered_from=api_url,
                context=" ".join(dict.fromkeys(context_terms)),
            )
        )
    return candidates


def parse_opml_feed_urls(text: str) -> list[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    urls: list[str] = []
    for outline in root.iter():
        xml_url = outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl")
        if xml_url and xml_url.startswith(("http://", "https://")) and xml_url not in urls:
            urls.append(xml_url)
    return urls[:MAX_FEEDS_FROM_OPML]


def same_domain(url: str, domains: tuple[str, ...]) -> bool:
    if not domains:
        return True
    host = urllib.parse.urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def extract_ithome_listing_metadata(text: str, page_url: str, source: Source) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for item_match in re.finditer(r"(?is)<li\b[^>]*>.*?</li>", text):
        item_html = item_match.group(0)
        summary = ""
        summary_match = re.search(
            r"""(?is)<div\b(?=[^>]*class\s*=\s*['"][^'"]*\bm\b[^'"]*['"])[^>]*>(.*?)</div>""",
            item_html,
        )
        if summary_match:
            summary = strip_tags(summary_match.group(1))
        feed_time_raw = ""
        time_match = re.search(r"""data-ot\s*=\s*['"]([^'"]+)['"]""", item_html, re.I)
        if time_match:
            feed_time_raw = html.unescape(time_match.group(1)).strip()
        if not summary and not feed_time_raw:
            continue
        for link_match in re.finditer(r"(?is)<a\b([^>]+)>(.*?)</a>", item_html):
            attrs, label_html = link_match.groups()
            href_match = re.search(r"""href\s*=\s*['"]([^'"]+)['"]""", attrs, re.I)
            if not href_match:
                continue
            label = strip_tags(label_html)
            if not label or len(label) < 8:
                continue
            url = urllib.parse.urljoin(page_url, html.unescape(href_match.group(1)))
            if not url.startswith(("http://", "https://")):
                continue
            if not same_domain(url, source.domains):
                continue
            metadata[normalize_url(url)] = {"summary": summary, "feed_time_raw": feed_time_raw}
    return metadata


def parse_html_links(text: str, page_url: str, source: Source) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    listing_metadata = (
        extract_ithome_listing_metadata(text, page_url, source) if source.name == "IT之家" else {}
    )
    for match in re.finditer(r"(?is)<a\b([^>]+)>(.*?)</a>", text):
        attrs, label_html = match.groups()
        href_match = re.search(r"""href\s*=\s*['"]([^'"]+)['"]""", attrs, re.I)
        if not href_match:
            continue
        label = strip_tags(label_html)
        if not label or len(label) < 8:
            continue
        href = html.unescape(href_match.group(1))
        url = urllib.parse.urljoin(page_url, href)
        if url in seen or not url.startswith(("http://", "https://")):
            continue
        if not same_domain(url, source.domains):
            continue
        metadata = listing_metadata.get(normalize_url(url), {})
        seen.add(url)
        candidates.append(
            Candidate(
                source=source.name,
                url=url,
                title=label,
                summary=metadata.get("summary", ""),
                feed_time_raw=metadata.get("feed_time_raw", ""),
                discovered_from=page_url,
                context=source_context_terms(attrs, []),
            )
        )
        if len(candidates) >= MAX_PAGE_LINKS:
            break
    return candidates


@lru_cache(maxsize=16384)
def term_present(text: str, term: str) -> bool:
    if term.lower() == "wwdc":
        return re.search(r"(?<![a-z0-9])wwdc(?:\d{0,4})?(?![a-z0-9])", text.lower()) is not None
    if any(ord(ch) > 127 for ch in term):
        return term in text
    escaped = re.escape(term.lower())
    if " " in term or term in {"ios", "macos", "ipados", "watchos", "tvos", "visionos"}:
        return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def score_terms(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(1 for term in terms if term_present(lower, term.lower()))


def has_apple_chip_context(text: str) -> bool:
    lower = text.lower()
    return score_terms(lower, APPLE_CHIP_CONTEXT_TERMS) > 0


def has_swift_programming_context(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["swift"]) > 0
        and score_terms(
            lower,
            [
                "apple",
                "ios",
                "ipados",
                "macos",
                "watchos",
                "visionos",
                "xcode",
                "developer",
                "developers",
                "programming",
                "app development",
                "swiftui",
                "swift playgrounds",
                "苹果",
                "开发者",
                "编程",
                "应用开发",
            ],
        )
        > 0
    )


def has_safari_browser_context(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["safari ev", "safari suv", "tata safari", "塔塔 safari"]) > 0:
        return False
    return score_terms(
        lower,
        [
            "apple safari",
            "safari browser",
            "safari extension",
            "safari extensions",
            "mobile safari",
            "safari technology preview",
            "ios safari",
            "macos safari",
            "browser",
            "web browser",
            "浏览器",
            "苹果 safari",
            "safari 浏览器",
        ],
    ) > 0


def has_tim_cook_context(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["佩尼库克"]) > 0:
        return False
    return score_terms(
        lower,
        [
            "tim cook",
            "timothy cook",
            "apple ceo",
            "apple's ceo",
            "ceo tim",
            "蒂姆·库克",
            "蒂姆・库克",
            "苹果 ceo",
            "苹果CEO",
            "苹果首席执行官",
            "库克表示",
            "库克称",
            "库克说",
            "库克宣布",
            "库克回应",
        ],
    ) > 0 or (
        score_terms(lower, ["库克"]) > 0
        and score_terms(lower, ["苹果", "ceo", "首席执行官", "公司高管"]) > 0
    )


def effective_apple_term_score(text: str) -> int:
    lower = text.lower()
    score = 0
    for term in APPLE_TERMS:
        normalized = term.lower()
        if normalized in BARE_APPLE_CHIP_TERMS and not has_apple_chip_context(lower):
            continue
        if normalized == "swift" and not has_swift_programming_context(lower):
            continue
        if normalized == "safari" and not has_safari_browser_context(lower):
            continue
        if normalized == "库克" and not has_tim_cook_context(lower):
            continue
        if term_present(lower, normalized):
            score += 1
    return score


def loose_apple_product_marker(text: str) -> bool:
    lower = text.lower()
    return any(
        marker in lower
        for marker in [
            "apple",
            "iphone",
            "ipad",
            "macbook",
            "macos",
            "airpods",
            "vision pro",
            "apple watch",
            "苹果",
        ]
    )


def is_third_party_platform_update_improving_apple_device_interop(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if score_terms(
        lower,
        [
            "airpods",
            "beats",
            "iphone",
            "ipad",
            "apple watch",
            "苹果耳机",
            "苹果手机",
            "苹果设备",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "windows",
            "windows 11",
            "microsoft",
            "android",
            "google",
            "chromeos",
            "linux",
            "微软",
            "安卓",
            "谷歌",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "bluetooth",
            "pairing",
            "connection",
            "connections",
            "connectivity",
            "compatibility",
            "interoperability",
            "audio sync",
            "microphone",
            "phone link",
            "cross-platform",
            "蓝牙",
            "配对",
            "连接",
            "稳定性",
            "兼容性",
            "互通",
            "音频同步",
            "麦克风",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "fix",
            "fixes",
            "fixed",
            "improve",
            "improves",
            "improved",
            "optimize",
            "optimizes",
            "optimized",
            "update",
            "updates",
            "reliability",
            "stability",
            "修复",
            "优化",
            "改善",
            "提升",
            "更新",
        ],
    ) <= 0:
        return False
    return score_terms(title_lower, ["airpods", "beats", "iphone", "ipad", "apple watch", "苹果"]) > 0


def is_apple_online_store_status_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if score_terms(lower, ["app store", "应用商店"]) > 0:
        return False
    if score_terms(
        title_lower,
        [
            "apple's online store",
            "apple online store",
            "apple store is down",
            "apple store",
            "苹果在线商店",
            "苹果官网",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "apple's online store",
            "apple online store",
            "apple store online",
            "apple.com store",
            "苹果在线商店",
            "苹果官网",
            "苹果在线官网",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "is down",
            "goes down",
            "gone down",
            "we'll be right back",
            "making updates",
            "offline",
            "back up",
            "store update",
            "下线",
            "维护",
            "暂时关闭",
            "正在更新",
            "恢复上线",
        ],
    ) > 0


@lru_cache(maxsize=4096)
def has_apple_research_disclosure_context(text: str) -> bool:
    lower = text.lower()
    apple_research_actor_score = score_terms(
        lower,
        [
            "apple researchers",
            "apple researcher",
            "apple research",
            "apple machine learning research",
            "apple ml",
            "苹果研究人员",
            "苹果研究员",
            "苹果研究团队",
            "苹果机器学习",
        ],
    )
    if apple_research_actor_score > 0:
        return True
    return (
        re.search(
            r"\bapple\b[^.!?。！？]{0,80}\b(?:showcas\w*|present\w*|publish\w*|share\w*|preview\w*|participat\w*)\b[^.!?。！？]{0,80}\b(?:research|paper|papers|study|studies|cvpr|conference)\b",
            lower,
        )
        is not None
        or re.search(
            r"苹果[^。！？.!?]{0,80}(?:展示|发表|发布|公布|分享|参与|参会|预热)[^。！？.!?]{0,80}(?:研究|论文|学术会议|计算机视觉|机器学习)",
            lower,
        )
        is not None
    )


@lru_cache(maxsize=4096)
def is_apple_research_candidate(text: str) -> bool:
    if effective_apple_term_score(text) <= 0:
        return False
    research_score = score_terms(text, APPLE_RESEARCH_ANCHOR_TERMS)
    action_score = score_terms(text, APPLE_RESEARCH_ACTION_TERMS)
    if not has_apple_research_disclosure_context(text):
        return False
    if "cvpr" in text.lower() and action_score > 0:
        return True
    return research_score >= 2 and action_score > 0


@lru_cache(maxsize=4096)
def is_non_apple_product_research_context_story(text: str) -> bool:
    if effective_apple_term_score(text) <= 0:
        return False
    if is_apple_research_candidate(text) or is_apple_health_data_research_candidate(text):
        return False
    lower = text.lower()
    if score_terms(lower, ["vulnerability", "exploit", "secure-rom", "bootrom", "漏洞", "攻击", "破解"]) > 0:
        return False
    research_score = score_terms(lower, APPLE_RESEARCH_ANCHOR_TERMS + APPLE_HEALTH_RESEARCH_ANCHOR_TERMS)
    institution_score = score_terms(
        lower,
        [
            "university",
            "college",
            "nber",
            "researchers",
            "economist",
            "professor",
            "study",
            "paper",
            "大学",
            "学院",
            "研究人员",
            "经济学家",
            "教授",
            "论文",
            "生育率",
        ],
    )
    product_context_score = score_terms(
        lower,
        ["iphone", "ipad", "mac", "apple watch", "smartphone", "苹果手机", "智能手机"],
    )
    return research_score > 0 and institution_score > 0 and product_context_score > 0


@lru_cache(maxsize=4096)
def is_apple_health_data_research_candidate(text: str) -> bool:
    if effective_apple_term_score(text) <= 0:
        return False
    product_score = score_terms(text, APPLE_HEALTH_RESEARCH_PRODUCT_TERMS)
    data_score = score_terms(text, APPLE_HEALTH_DATA_TERMS)
    research_score = score_terms(text, APPLE_HEALTH_RESEARCH_ANCHOR_TERMS)
    return product_score > 0 and data_score > 0 and research_score > 0


def is_messages_platform_candidate(text: str) -> bool:
    if effective_apple_term_score(text) <= 0:
        return False
    message_score = score_messages_platform_terms(text)
    agent_score = score_terms(text, MESSAGE_AGENT_TERMS)
    action_score = score_messages_platform_actions(text)
    return message_score > 0 and agent_score > 0 and action_score > 0


THIRD_PARTY_PLATFORM_TERMS = [
    "app store",
    "mac app store",
    "apple app store",
    "iphone app",
    "ipad app",
    "mac app",
    "watchos app",
    "watchos platform",
    "apple watch app",
    "apple watch client",
    "vision pro app",
    "app for vision pro",
    "macos app",
    "苹果应用商店",
    "苹果 app store",
    "mac app store",
    "iphone 应用",
    "ipad 应用",
    "mac 应用",
    "watchos 应用",
    "watchos 平台",
    "apple watch 应用",
    "apple watch 客户端",
    "vision pro 应用",
]

THIRD_PARTY_PLATFORM_ACTION_TERMS = [
    "available on",
    "available for",
    "launches on",
    "launched on",
    "launches for",
    "released on",
    "released for",
    "listed on",
    "comes to",
    "support for",
    "supports",
    "上架",
    "登陆",
    "登录",
    "上线",
    "支持",
    "可用",
    "适配",
    "重返",
    "回归",
    "重新推出",
]

APPLE_FIRST_PARTY_RELEASE_TERMS = [
    "apple announces",
    "apple announced",
    "apple introduces",
    "apple introduced",
    "apple launches",
    "apple launched",
    "apple releases",
    "apple released",
    "apple unveils",
    "apple unveiled",
    "苹果宣布",
    "苹果推出",
    "苹果发布",
    "苹果上线",
    "苹果带来",
]

APPLE_FIRST_PARTY_APP_TERMS = [
    "apple developer app",
    "apple sports",
    "apple invites",
    "airport utility",
    "apple music",
    "apple tv",
    "apple arcade",
    "苹果开发者 app",
    "苹果音乐",
    "苹果电视",
]

APPLE_DEVELOPER_TOOL_TERMS = [
    "xcode",
    "swift",
    "testflight",
    "developer tools",
    "developer tool",
    "coding tool",
    "coding tools",
    "agentic coding",
    "开发者工具",
    "开发工具",
]

APPLE_DEVELOPER_TOOL_ACTION_TERMS = [
    "integration",
    "integrate",
    "integrated",
    "join apple",
    "joins apple",
    "joined apple",
    "joining apple",
    "open source",
    "remain open source",
    "support for",
    "supports",
    "adds",
    "expands",
    "native support",
    "plan, write, and review",
    "集成",
    "接入",
    "加入苹果",
    "加入 Apple",
    "开源",
    "支持",
    "新增",
    "扩展",
]

OFFICIAL_APPLE_ACCESSORY_TERMS = [
    "travel case",
    "case",
    "accessory",
    "accessories",
    "magsafe",
    "grip",
    "stand",
    "apple store online",
    "apple online store",
    "保护套",
    "旅行保护套",
    "配件",
    "手柄",
    "支架",
    "磁吸",
]

OFFICIAL_APPLE_ACCESSORY_ACTION_TERMS = [
    "added to apple",
    "added to apple's online store",
    "added to apple online store",
    "available exclusively from apple",
    "launched on apple",
    "now available from apple",
    "discontinuing",
    "discontinued",
    "unavailable",
    "no longer available",
    "removed from",
    "pulled from",
    "sold out",
    "下架",
    "上架",
    "上线",
    "开售",
    "新增",
    "停售",
    "停产",
    "不可用",
    "缺货",
]

OS_FEATURE_ACTION_TERMS = [
    "add",
    "adds",
    "added",
    "remove",
    "removes",
    "removed",
    "missing",
    "drops",
    "drop",
    "change",
    "changes",
    "changed",
    "update",
    "updates",
    "updated",
    "revamp",
    "revamps",
    "integration",
    "integrate",
    "integrated",
    "feature",
    "features",
    "新增",
    "移除",
    "删除",
    "缺失",
    "取消",
    "调整",
    "改进",
    "优化",
    "集成",
    "接入",
    "功能",
]

OS_SUMMARY_TERMS = [
    "roundup",
    "recap",
    "everything new",
    "what's new",
    "whats new",
    "all the new",
    "feature list",
    "features list",
    "主要更新点",
    "一文汇总",
    "汇总",
    "总览",
]


APPLE_OS_PLATFORM_TERMS = [
    "ios",
    "ipados",
    "macos",
    "watchos",
    "tvos",
    "visionos",
    "iphone",
    "ipad",
    "mac",
    "apple watch",
    "apple tv",
    "homepod",
    "系统",
]


APPLE_OS_COMPONENT_TERMS = [
    "home screen",
    "lock screen",
    "control center",
    "messages",
    "mail",
    "notes",
    "weather",
    "shortcuts",
    "photos",
    "wallet",
    "pages",
    "keynote",
    "numbers",
    "textedit",
    "productivity apps",
    "airport utility",
    "widgets",
    "widget",
    "siri",
    "apple intelligence",
    "rcs",
    "recovery mode",
    "airplay",
    "home app",
    "主屏幕",
    "锁屏",
    "控制中心",
    "信息",
    "邮件",
    "备忘录",
    "天气",
    "快捷指令",
    "照片",
    "钱包",
    "小组件",
    "恢复模式",
]


def is_apple_os_feature_or_summary_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if (
        is_messages_platform_candidate(text)
        or is_macos_terminal_paste_security_story(text)
        or is_third_party_platform_availability_candidate(text)
        or is_routine_third_party_apple_platform_story(text)
    ):
        return False
    if score_terms(lower, APPLE_OS_PLATFORM_TERMS) <= 0:
        return False
    if score_terms(
        lower,
        [
            "top stories",
            "weekly recap",
            "daily:",
            "9to5mac daily",
            "hands-on",
            "alternative",
            "third-party",
            "recap links",
            "本周回顾",
            "一周回顾",
            "动手体验",
            "替代品",
            "第三方",
        ],
    ) > 0:
        return False
    summary_score = score_terms(lower, OS_SUMMARY_TERMS)
    component_score = score_terms(lower, APPLE_OS_COMPONENT_TERMS)
    action_score = score_terms(
        lower,
        OS_FEATURE_ACTION_TERMS
        + POSITIVE_ACTION_TERMS
        + [
            "new",
            "new in",
            "enhancement",
            "enhancements",
            "improvement",
            "improvements",
            "brings",
            "bring",
            "write with siri",
            "retire",
            "retires",
            "retirement",
            "going away",
            "sunset",
            "remove from app store",
            "更新点",
            "新变化",
            "增强",
            "退场",
            "下架",
        ],
    )
    if summary_score > 0 and score_terms(lower, ["beta", "developer beta", "更新", "新增"]) > 0:
        return True
    return component_score > 0 and action_score > 0


def normalize_os_version_token(value: str) -> str:
    return value.replace(".", "-")


def os_release_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    if score_terms(lower, ["ios", "ipados", "macos", "watchos", "tvos", "visionos"]) <= 0:
        return set()
    version_values = {
        match.group(1)
        for match in re.finditer(
            r"(?<!\d)(\d{1,2}\.\d(?:\.\d)?)(?!\d)",
            lower,
        )
    }
    if not version_values:
        return set()
    release_action_score = score_terms(
        lower,
        [
            "beta",
            "developer beta",
            "release candidate",
            "release",
            "releases",
            " rc",
            "seeded",
            "seeds",
            "released",
            "rolling out",
            "now available",
            "patch",
            "patches",
            "fix",
            "fixes",
            "security fixes",
            "security issues",
            "security update",
            "security updates",
            "security vulnerabilities",
            "开发者预览版",
            "测试版",
            "候选版",
            "发布",
            "推送",
            "正式版",
            "安全更新",
            "漏洞",
            "修复",
        ],
    )
    if release_action_score <= 0:
        return set()
    facets = {f"os-release-version-{normalize_os_version_token(value)}" for value in version_values}
    if score_terms(lower, ["beta", "betas", "developer beta", "developer betas", "开发者预览版", "测试版"]) > 0:
        facets.add("os-release-beta")
        beta_numbers = set(re.findall(r"(?:beta|测试版)\s*(\d+)", lower))
        beta_numbers |= set(re.findall(r"beta\s*/?\s*rc\s*(?:间隔\s*)?(\d+)", lower))
        ordinal_beta_numbers = {
            "first": "1",
            "second": "2",
            "third": "3",
            "fourth": "4",
            "fifth": "5",
            "sixth": "6",
        }
        for ordinal, number in ordinal_beta_numbers.items():
            if re.search(rf"\b{ordinal}\s+(?:developer\s+)?betas?\b", lower):
                beta_numbers.add(number)
        for number in beta_numbers:
            facets.add(f"os-release-beta-{number}")
    if score_terms(lower, ["release candidate", " rc", "候选版"]) > 0:
        facets.add("os-release-rc")
    if score_terms(lower, ["security", "security fixes", "security vulnerabilities", "patch", "patches", "安全", "漏洞", "修复"]) > 0:
        facets.add("os-release-security")
    if score_terms(lower, ["正式版", "now available", "released"]) > 0 and "os-release-beta" not in facets:
        facets.add("os-release-final")
    return facets


def os_release_version_facets(facets: set[str]) -> set[str]:
    return {facet for facet in facets if facet.startswith("os-release-version-")}


def os_release_channel_facets(facets: set[str]) -> set[str]:
    return {facet for facet in facets if facet.startswith("os-release-") and not facet.startswith("os-release-version-")}


def os_release_facets_compatible(article_facets: set[str], event_facets: set[str]) -> bool:
    article_versions = os_release_version_facets(article_facets)
    event_versions = os_release_version_facets(event_facets)
    if not article_versions or not event_versions:
        return True
    if article_versions != event_versions:
        return False
    article_channels = os_release_channel_facets(article_facets)
    event_channels = os_release_channel_facets(event_facets)
    if article_channels and event_channels and not (article_channels & event_channels):
        return False
    return True


def same_os_release_event(article: Article, event: Event) -> bool:
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    article_versions = os_release_version_facets(article_facets)
    event_versions = os_release_version_facets(event_facets)
    if not article_versions or not event_versions or not (article_versions & event_versions):
        return False
    if not os_release_facets_compatible(article_facets, event_facets):
        return False
    article_channels = os_release_channel_facets(article_facets)
    event_channels = os_release_channel_facets(event_facets)
    return bool(article_channels & event_channels)


def allowed_url_excluded_candidate(candidate: Candidate, source: Source, text: str) -> bool:
    url_lower = candidate.url.lower()
    if source.name == "MacRumors" and "/guide/" in url_lower:
        return is_apple_os_feature_or_summary_story(text)
    if "review" in url_lower and detect_event_kind(candidate.title, candidate.summary, [candidate.context]) == "service_content":
        return True
    return False


def has_apple_first_party_release_context(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, APPLE_FIRST_PARTY_RELEASE_TERMS + APPLE_FIRST_PARTY_APP_TERMS) > 0:
        return True
    if re.search(
        r"\bapple\b[^.!?。！？]{0,48}\b(?:announc\w*|introduc\w*|launch\w*|releas\w*|unveil\w*|bring\w*)\b",
        lower,
    ):
        return True
    if re.search(r"苹果(?:公司)?[^。！？.!?，,；;：:]{0,32}(?:宣布|推出|发布|上线|带来|引入|新增)", lower):
        return True
    return False


def is_apple_developer_tool_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, APPLE_DEVELOPER_TOOL_TERMS) <= 0:
        return False
    if score_terms(
        lower,
        [
            "xcode",
            "testflight",
            "developer tools",
            "developer tool",
            "coding tool",
            "coding tools",
            "agentic coding",
            "swiftui",
            "swift playgrounds",
            "开发者工具",
            "开发工具",
        ],
    ) <= 0:
        if not has_swift_programming_context(lower):
            return False
    return score_terms(lower, APPLE_DEVELOPER_TOOL_ACTION_TERMS) > 0


def is_official_apple_accessory_market_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(lower, OFFICIAL_APPLE_ACCESSORY_TERMS) <= 0:
        return False
    official_store_context = score_terms(
        lower,
        [
            "apple store",
            "apple's online store",
            "apple online store",
            "apple store online",
            "apple.com",
            "苹果中国在线官网",
            "苹果在线官网",
            "苹果官网",
            "苹果官方商城",
            "苹果在线商店",
        ],
    ) > 0 or re.search(r"苹果[^。！？.!?]{0,24}(?:在线官网|官网|官方商城|在线商店)", lower) is not None
    if not official_store_context:
        return False
    return score_terms(lower, OFFICIAL_APPLE_ACCESSORY_ACTION_TERMS) > 0 or re.search(
        r"苹果[^。！？.!?]{0,32}(?:上架|上线|开售|新增|推出)",
        lower,
    ) is not None


def is_official_apple_refurbished_product_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "refurbished",
            "certified refurbished",
            "certified refurbished store",
            "apple refurbished",
            "apple certified refurbished",
            "online refurbished store",
            "refurbished store",
            "翻新",
            "认证翻新",
            "官方翻新",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "macbook",
            "mac",
            "ipad",
            "iphone",
            "apple watch",
            "vision pro",
            "homepod",
            "apple tv",
            "airpods",
            "苹果",
        ],
    ) <= 0:
        return False
    store_context = score_terms(
        lower,
        [
            "apple today began selling",
            "apple began selling",
            "apple store",
            "apple online store",
            "apple refurbished store",
            "online refurbished store",
            "refurbished store",
            "certified refurbished store",
            "through its certified refurbished store",
            "苹果官方翻新",
            "苹果认证翻新",
            "苹果官网",
            "苹果在线商店",
            "官网上线",
            "官网上架",
            "官网新增",
        ],
    ) > 0
    if not store_context:
        return False
    return score_terms(
        lower,
        [
            "available",
            "now available",
            "began selling",
            "selling refurbished",
            "price",
            "price hike",
            "上架",
            "上线",
            "开售",
            "发售",
            "涨价",
            "价格",
        ],
    ) > 0


def is_unreleased_beats_hardware_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["beats"]) <= 0:
        return False
    if score_terms(lower, ["deal", "deals", "discount", "coupon", "sale", "record low", "amazon", "best buy", "优惠", "促销", "降价"]) > 0:
        return False
    hardware_score = score_terms(
        lower,
        [
            "headphone",
            "headphones",
            "over-ear",
            "earbuds",
            "earphones",
            "speaker",
            "ear cups",
            "headband",
            "housings",
            "头戴式耳机",
            "耳机",
            "耳罩",
            "头梁",
            "机身",
        ],
    )
    if hardware_score <= 0:
        return False
    product_detail_score = score_terms(
        lower,
        [
            "unreleased",
            "upcoming",
            "new product",
            "new version",
            "new model",
            "fcc",
            "fcc database",
            "certification",
            "beats studio pro",
            "studio pro",
            "product line",
            "availability",
            "release timing",
            "two-tone",
            "color",
            "colors",
            "royal blue",
            "white headband",
            "ear cups",
            "customizable",
            "customization",
            "design",
            "尚未发布",
            "未发布",
            "新品",
            "新款",
            "新一代",
            "fcc 数据库",
            "fcc",
            "认证",
            "型号",
            "产品线",
            "发布时间",
            "撞色",
            "配色",
            "颜色",
            "皇家蓝",
            "白色头梁",
            "耳罩",
            "设计",
            "定制",
        ],
    )
    return product_detail_score >= 2


def is_apple_wallet_feature_story(text: str) -> bool:
    lower = text.lower()
    if is_third_party_financial_service_with_apple_pay_support("", text):
        return False
    if score_terms(
        lower,
        [
            "magsafe wallet",
            "magnetic wallet",
            "wallet attachment",
            "wallet case",
            "钱包配件",
            "磁吸钱包",
        ],
    ) > 0 and score_terms(lower, ["apple wallet", "apple pay", "apple cash", "wallet app", "钱包 app", "钱包应用"]) == 0:
        return False
    if score_terms(lower, ["apple wallet", "apple pay", "apple cash", "wallet app", "钱包 app", "钱包应用"]) > 0:
        return True
    if (
        score_terms(lower, ["digital id", "数字身份证", "数字身份", "数字证件", "身份凭证"]) > 0
        and score_terms(lower, ["apple", "iphone", "苹果", "苹果钱包", "护照"]) > 0
    ):
        return True
    wallet_feature_terms = [
        "passport",
        "driver's license",
        "digital id",
        "id support",
        "identity verification",
        "nationality verification",
        "boarding pass",
        "passes",
        "hotel key",
        "car key",
        "transit card",
        "payment card",
        "tap to share",
        "护照",
        "驾驶证",
        "数字身份证",
        "数字身份",
        "数字证件",
        "证件",
        "身份凭证",
        "身份核验",
        "国籍校验",
        "登机牌",
        "票卡",
        "酒店钥匙",
        "车钥匙",
        "交通卡",
        "支付卡",
    ]
    return (
        score_terms(lower, wallet_feature_terms) > 0
        and score_terms(lower, ["ios", "iphone", "apple", "苹果"]) > 0
        and score_terms(lower, ["wallet", "钱包", "pay", "支付", "digital id", "数字身份证", "数字身份"]) > 0
    )


def is_apple_os_support_compatibility_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if is_competitor_apple_marketing_comparison(text):
        return False
    if score_terms(
        lower,
        [
            "antivirus",
            "firewall",
            "vpn",
            "mac cleaner",
            "subscription",
            "reader discount",
            "50% off",
            "% off",
            "discount",
            "promo",
            "promotion",
        ],
    ) > 0:
        return False
    return (
        score_terms(
            lower,
            [
                "iphone",
                "iphones",
                "ipad",
                "ipads",
                "mac",
                "macs",
                "macbook",
                "macbooks",
                "imac",
                "imacs",
                "apple watch",
                "apple tv",
                "homepod",
                "vision pro",
            ],
        )
        > 0
        and score_terms(
            lower,
            [
                "software support",
                "support ends",
                "end software support",
                "drop support",
                "drops support",
                "dropped",
                "not support",
                "won't support",
                "no longer support",
                "losing support",
                "compatibility list",
                "compatible",
                "unsupported",
                "停止支持",
                "结束支持",
                "不再支持",
                "无缘",
                "兼容列表",
                "兼容性",
            ],
        )
        > 0
        and score_terms(lower, ["ios", "ipados", "macos", "watchos", "tvos", "visionos", "software", "系统"])
        > 0
    )


def is_third_party_security_software_promo_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if has_apple_first_party_release_context(lower) or is_macos_terminal_paste_security_story(text):
        return False
    if score_terms(
        lower,
        [
            "antivirus",
            "anti-virus",
            "firewall",
            "vpn",
            "mac cleaner",
            "malware scanner",
            "security suite",
            "intego",
            "cleanmymac",
            "安全套件",
            "杀毒",
            "防火墙",
        ],
    ) <= 0:
        return False
    return (
        score_terms(
            lower,
            [
                "subscription",
                "reader discount",
                "discount",
                "deal",
                "50% off",
                "% off",
                "promo",
                "promotion",
                "limited-time",
                "starts at",
                "pricing",
                "plan",
                "protect your mac",
                "your mac isn't immune",
                "折扣",
                "优惠",
                "促销",
                "订阅",
                "套餐",
            ],
        )
        > 0
    )


def is_routine_recap_comparison_or_buying_advice(title: str, text: str) -> bool:
    lower = text.lower()
    title_lower = title.lower()
    if score_terms(
        title_lower,
        [
            "buying advice",
            "buying guide",
            "should you buy",
            "bad time to buy",
            "buy now or wait",
            "upgrade or wait",
            "购机",
            "购买建议",
            "换机建议",
            "买还是等",
            "该不该买",
            "值不值",
            "值不值得买",
            "值得买吗",
        ],
    ) > 0:
        return True
    if is_apple_os_feature_or_summary_story(text):
        return False
    if score_terms(
        title_lower,
        [
            "top stories",
            "recap",
            "weekly recap",
            "roundup",
            "this week",
            "sunday reboot",
            "opinion",
            "commentary",
            "column",
            "本周回顾",
            "一周",
            "汇总",
            "评论",
            "专栏",
        ],
    ) > 0:
        return True
    if is_apple_os_support_compatibility_story(text):
        return False
    if is_competitor_apple_marketing_comparison(text):
        return True
    if has_apple_first_party_release_context(lower) or is_apple_developer_tool_story(lower):
        return False
    if (
        is_official_apple_accessory_market_story(lower)
        or is_official_apple_refurbished_product_story(lower)
        or is_unreleased_beats_hardware_story(lower)
    ):
        return False
    if score_terms(
        lower,
        [
            "buying advice",
            "buying guide",
            "should you buy",
            "bad time to buy",
            "want to upgrade",
            "upgrade decision",
            "buy now or wait",
            "upgrade or wait",
            "购机",
            "购买建议",
            "换机建议",
            "换机周期",
            "几年换",
            "最划算",
            "保值率",
            "现在上车",
            "上车还是等",
            "买还是等",
            "现在买",
            "等新机",
            "该不该买",
            "值不值得买",
        ],
    ) > 0:
        return True
    if is_routine_retail_discount_story(title, text):
        return True
    if re.search(r"(?i)(?:\bvs\.?\b|\bversus\b|compared|comparison|对比|较量)", title):
        return True
    if "hands-on" in title_lower and score_terms(
        lower,
        [
            "alternative",
            "third-party",
            "speaker",
            "dock",
            "hub",
            "charger",
            "monitor",
            "display",
            "belkin",
            "anker",
            "satechi",
            "denon",
            "amazon",
            "pricing",
            "price",
            "替代",
            "音箱",
            "第三方",
            "售价",
        ],
    ) > 0:
        return True
    return False


def is_routine_retail_discount_story(title: str, text: str) -> bool:
    lower = text.lower()
    title_lower = title.lower()
    if effective_apple_term_score(title) <= 0 and not loose_apple_product_marker(title):
        return False
    if is_apple_product_price_increase_story(text, title):
        return False
    retail_title_lower = title_lower.replace("京东方", "")
    retail_lower = lower.replace("京东方", "")
    if score_terms(
        retail_title_lower,
        [
            "deal",
            "deals",
            "discount",
            "coupon",
            "sale",
            "record low",
            "prime day",
            "$",
            "just $",
            "price drop",
            "save",
            "off",
            "国补",
            "补贴",
            "优惠",
            "促销",
            "降价",
            "立减",
            "到手",
            "换新",
            "再来",
            "京东",
            "天猫",
            "拼多多",
            "百亿补贴",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "apple card",
            "apple pay",
            "app store",
            "apple music",
            "apple tv+",
            "icloud",
            "daily cash",
            "official apple",
            "苹果官方",
            "苹果官网",
            "官方活动",
        ],
    ) > 0:
        return False
    return score_terms(
        retail_lower,
        [
            "amazon",
            "best buy",
            "walmart",
            "target",
            "retailer",
            "prime day",
            "京东",
            "天猫",
            "淘宝",
            "拼多多",
            "苏宁",
            "电商",
            "国补",
            "补贴",
            "优惠券",
            "换新",
        ],
    ) > 0


def is_apple_opinion_without_new_reporting(title: str, text: str) -> bool:
    lower = text.lower()
    title_lower = title.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    opinion_title = bool(
        re.search(r"(?i)^(?:why\s+)?apple\s+should\b", title_lower)
        or re.search(r"(?i)^should\s+apple\b", title_lower)
        or re.search(r"苹果[^。！？.!?]{0,12}(?:应该|该不该|要不要)", title)
    )
    if not opinion_title:
        return False
    if score_terms(
        lower,
        [
            "report",
            "reported",
            "reportedly",
            "source",
            "sources",
            "filing",
            "document",
            "announcement",
            "announced",
            "confirmed",
            "消息称",
            "报道称",
            "爆料",
            "宣布",
            "确认",
        ],
    ) > 0:
        return False
    return True


def is_apple_product_commentary_analysis_without_new_reporting(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if not (
        score_terms(
            title_lower,
            [
                "could be good news",
                "could be very good news",
                "here's why",
                "heres why",
                "what it means",
                "why this matters",
                "what this means",
                "opinion",
                "commentary",
                "analysis",
            ],
        )
        > 0
        or score_terms(lower[:900], ["i think", "i’m confident", "i'm confident", "my take", "the author argues"]) > 0
    ):
        return False
    if score_terms(
        lower,
        [
            "apple announced",
            "apple says",
            "apple said",
            "apple confirmed",
            "filing",
            "regulatory filing",
            "support document",
            "press release",
            "苹果宣布",
            "苹果确认",
            "苹果表示",
            "监管文件",
            "支持文档",
        ],
    ) > 0:
        return False
    return score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "apple watch",
            "vision pro",
            "airpods",
            "homepod",
            "apple tv",
            "iring",
            "苹果手表",
            "苹果电视",
        ],
    ) > 0


def is_third_party_surveillance_context_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if has_apple_first_party_release_context(lower):
        return False
    return (
        score_terms(
            lower,
            [
                "license plate reader",
                "license plate readers",
                "law enforcement",
                "cops",
                "police",
                "surveillance firm",
                "surveillance company",
                "signaltrace",
                "bluetooth devices",
                "track your iphone",
                "track your airpods",
                "执法",
                "警方",
                "监控公司",
                "车牌识别",
                "蓝牙设备",
                "追踪 iphone",
                "追踪 airpods",
            ],
        )
        > 0
    )


def is_third_party_device_management_service_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if has_apple_first_party_release_context(lower):
        return False
    vendor_or_service = score_terms(
        lower,
        [
            "mosyle",
            "jamf",
            "third-party platform",
            "third-party service",
            "mdm",
            "device management",
            "第三方平台",
            "第三方服务",
            "设备管理",
        ],
    )
    management_action = score_terms(
        lower,
        [
            "launches new service",
            "launches new platform",
            "announces",
            "manage mac",
            "manage ipad",
            "screen time",
            "parents manage",
            "school-issued",
            "k-12",
            "parental control",
            "推出服务",
            "推出平台",
            "家长管理",
            "屏幕时间",
            "学校设备",
        ],
    )
    return vendor_or_service > 0 and management_action > 0


def is_competitor_apple_marketing_comparison(text: str) -> bool:
    lower = text.lower()
    competitor_text = lower
    for phrase in [
        "intel mac",
        "intel macs",
        "intel-based mac",
        "intel-based macs",
        "intel machines",
        "intel apps",
        "intel app",
        "intel-compiled",
        "pre-apple silicon mac",
        "pre-apple silicon macs",
    ]:
        competitor_text = competitor_text.replace(phrase, "")
    competitor = any(
        marker in competitor_text
        for marker in [
            "amd",
            "nvidia",
            "intel",
            "dell",
            "windows",
            "winpc",
            "radeon",
            "ryzen",
            "惠普",
            "锐龙",
            "英伟达",
        ]
    )
    apple_subject = loose_apple_product_marker(lower) or "macos" in lower
    comparison_or_marketing = any(
        marker in lower
        for marker in [
            "marketing",
            "promotional",
            "compared",
            "comparison",
            " vs ",
            "battle",
            "rival",
            "game compatibility",
            "营销",
            "嘲讽",
            "矛头对准",
            "平台之争",
            "游戏兼容",
            "逐项对比",
            "给不了你的",
            "舍弃",
        ]
    )
    return competitor and apple_subject and comparison_or_marketing


def is_generic_consumer_electronics_health_safety_story(title: str, text: str) -> bool:
    lower = text.lower()
    title_lower = title.lower()
    if effective_apple_term_score(title) > 0:
        return False
    return (
        score_terms(
            lower,
            [
                "consumer electronics",
                "smartphones",
                "smartphone",
                "earbuds",
                "headphones",
                "smartwatch",
                "消费电子",
                "消费类电子",
                "智能手机",
                "耳机",
                "智能手表",
            ],
        )
        > 0
        and score_terms(
            lower,
            [
                "fda",
                "pacemaker",
                "defibrillator",
                "magnetic field",
                "magnet",
                "heart implant",
                "心脏起搏器",
                "起搏器",
                "除颤器",
                "植入式器械",
                "磁场",
            ],
        )
        > 0
        and score_terms(title_lower, ["fda", "pacemaker", "磁场", "起搏器", "消费电子", "电子产品"]) > 0
    )


def is_apple_car_asset_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(
            lower,
            [
                "apple car",
                "apple car project",
                "project titan",
                "vehicle testing",
                "vehicle testing assets",
                "car testing",
                "苹果汽车",
                "苹果造车",
                "自动驾驶项目",
                "汽车项目",
            ],
        )
        > 0
        and score_terms(
            lower,
            ["test site", "testing site", "proving ground", "test track", "facility", "site", "测试场", "试验场", "测试设施", "场地"],
        )
        > 0
        and score_terms(lower, ["bought", "acquired", "sold", "sale", "purchase", "waymo", "买下", "收购", "出售", "购入"]) > 0
    )


def is_macos_terminal_paste_security_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["macos", "mac"]) > 0
        and score_terms(lower, ["terminal", "终端"]) > 0
        and score_terms(lower, ["paste", "command", "script", "粘贴", "命令", "脚本"]) > 0
        and score_terms(
            lower,
            [
                "block",
                "blocks",
                "warning",
                "warnings",
                "popup",
                "security",
                "malware",
                "protect",
                "拦截",
                "阻止",
                "弹窗",
                "警告",
                "安全",
                "恶意软件",
                "防范",
            ],
        )
        > 0
    )


def is_apple_books_or_store_platform_trust_story(title: str, text: str = "") -> bool:
    combined = f"{title} {text}".lower()
    lead = f"{title} {text[:700]}".lower()
    platform_score = score_terms(
        lead,
        [
            "apple books",
            "apple book",
            "ibooks",
            "app store",
            "苹果图书",
            "苹果书店",
            "苹果应用商店",
            "应用商店",
        ],
    )
    issue_score = score_terms(
        combined,
        [
            "ai-generated",
            "knockoff",
            "knockoffs",
            "copycat",
            "impersonation",
            "fake",
            "scam",
            "fraud",
            "copyright",
            "infringing",
            "platform trust",
            "仿冒",
            "山寨",
            "盗版",
            "冒充",
            "欺诈",
            "诈骗",
            "侵权",
            "平台治理",
        ],
    )
    return platform_score > 0 and issue_score > 0


def is_third_party_accessory_platform_compatibility_story(title: str, text: str) -> bool:
    lower = text.lower()
    title_lower = title.lower()
    if (
        is_official_apple_accessory_market_story(lower)
        or is_official_apple_refurbished_product_story(lower)
        or is_unreleased_beats_hardware_story(lower)
        or is_direct_apple_hardware_roadmap_story(text, title)
        or is_apple_hardware_product_launch_story(text, title)
    ):
        return False
    if score_terms(
        title_lower,
        [
            "iphone",
            "ipad",
            "apple watch",
            "airpods",
            "vision pro",
            "homepod",
            "beats",
            "苹果",
        ],
    ) > 0 and score_terms(
        title_lower,
        [
            "compatible",
            "compatibility",
            "support",
            "supports",
            "adapter",
            "dock",
            "hub",
            "专用",
            "面向",
            "适配",
            "兼容",
            "支持",
        ],
    ) <= 0:
        return False
    if score_terms(title_lower, ["apple", "beats", "苹果", "官方"]) > 0:
        if score_terms(title_lower, ["专用", "compatible", "compatibility", "support", "supports", "适配", "支持"]) <= 0:
            return False
    accessory_score = score_terms(
        lower,
        [
            "dock",
            "hub",
            "charger",
            "charging station",
            "power bank",
            "adapter",
            "keyboard",
            "mouse",
            "monitor",
            "display",
            "touchscreen",
            "selfie screen",
            "magnetic",
            "magsafe",
            "case",
            "cases",
            "wallet",
            "wallets",
            "gear",
            "accessory",
            "accessories",
            "扩展坞",
            "充电器",
            "充电站",
            "移动电源",
            "适配器",
            "键盘",
            "鼠标",
            "显示器",
            "触控显示器",
            "自拍屏",
            "背屏",
            "磁吸",
            "潮玩自拍屏",
            "配件",
            "保护壳",
            "手机壳",
        ],
    )
    platform_compatibility_score = score_terms(
        lower,
        [
            "macos",
            "ios",
            "ipados",
            "iphone",
            "ipad",
            "mac",
            "compatible",
            "compatibility",
            "support",
            "supports",
            "platform",
            "for mac users",
            "平台",
            "兼容",
            "适配",
            "支持",
            "专用",
            "面向",
        ],
    )
    first_party_action_score = score_terms(
        lower,
        [
            "apple announces",
            "apple announced",
            "apple releases",
            "apple released",
            "apple launches",
            "apple launched",
            "apple store removes",
            "apple store removed",
            "苹果发布",
            "苹果推出",
            "苹果宣布",
            "苹果下架",
        ],
    )
    third_party_title_score = score_terms(
        title_lower,
        [
            "oppo",
            "xiaomi",
            "samsung",
            "lenovo",
            "anker",
            "belkin",
            "logitech",
            "viture",
            "雷鸟",
            "小米",
            "三星",
            "联想",
            "第三方",
            "潮玩自拍屏",
        ],
    )
    if is_apple_os_feature_or_summary_story(text) and third_party_title_score <= 0:
        return False
    return accessory_score > 0 and platform_compatibility_score > 0 and first_party_action_score == 0


def has_direct_apple_subject_context(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if (
        is_apple_developer_tool_story(lower)
        or is_official_apple_accessory_market_story(lower)
        or is_unreleased_beats_hardware_story(lower)
        or is_apple_books_or_store_platform_trust_story("", lower)
    ):
        return True
    product_or_platform_score = score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "apple watch",
            "airpods",
            "vision pro",
            "homepod",
            "apple tv",
            "ios",
            "ipados",
            "macos",
            "watchos",
            "tvos",
            "visionos",
            "app store",
            "apple wallet",
            "apple music",
            "xcode",
            "苹果",
            "苹果电视",
            "苹果手表",
            "苹果应用商店",
        ],
    )
    action_score = score_terms(lower, POSITIVE_ACTION_TERMS + STRONG_NEWS_ACTION_TERMS)
    return product_or_platform_score > 0 and action_score > 0


def should_hard_exclude_candidate(text: str) -> bool:
    lower = text.lower()
    if not any(term in lower for term in HARD_EXCLUDE_TERMS):
        return False
    if any(term in lower for term in NON_OVERRIDABLE_HARD_EXCLUDE_TERMS):
        return not is_apple_books_or_store_platform_trust_story("", lower)
    return not has_direct_apple_subject_context(text)


def is_source_daily_brief_candidate(candidate: Candidate, source: Source | None = None) -> bool:
    source_name = source.name if source is not None else candidate.source
    title = candidate.title
    if source_name == "IT之家":
        return re.search(r"(?i)(?<![a-z])it\s*早报", title) is not None
    if source_name == "爱范儿":
        return re.search(r"(?i)(?<![a-z])早\s*报", title) is not None
    return False


def is_ithome_daily_brief_candidate(candidate: Candidate, source: Source | None = None) -> bool:
    return is_source_daily_brief_candidate(candidate, source)


GENERIC_LINK_TITLES = {
    "1 comment",
    "comments",
    "expand expanding close",
    "expand",
    "read more",
    "more",
}


def title_quality_score(title: str) -> tuple[int, int, int]:
    cleaned = clean_sentence(title).lower()
    generic = cleaned in GENERIC_LINK_TITLES or bool(
        re.fullmatch(r"\d+\s+comments?", cleaned)
    )
    return (
        0 if generic else 1,
        1 if effective_apple_term_score(title) > 0 or loose_apple_product_marker(title) else 0,
        len(cleaned),
    )


def merge_candidate_text(primary: str, secondary: str) -> str:
    if not primary:
        return secondary
    if not secondary:
        return primary
    return combine_summaries(primary, secondary)


def merge_candidate_context(primary: str, secondary: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in [primary, secondary]:
        for part in re.split(r"\s+", value.strip()):
            cleaned = part.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            parts.append(cleaned)
            seen.add(cleaned)
    return " ".join(parts)


def merge_two_candidates(existing: Candidate, incoming: Candidate) -> Candidate:
    title = existing.title
    if title_quality_score(incoming.title) > title_quality_score(existing.title):
        title = incoming.title
    feed_time_raw = existing.feed_time_raw or incoming.feed_time_raw
    discovered_from = existing.discovered_from or incoming.discovered_from
    if incoming.feed_time_raw and not existing.feed_time_raw:
        discovered_from = incoming.discovered_from or discovered_from
    return Candidate(
        source=existing.source,
        url=existing.url,
        title=title,
        summary=merge_candidate_text(existing.summary, incoming.summary),
        feed_time_raw=feed_time_raw,
        discovered_from=discovered_from,
        context=merge_candidate_context(existing.context, incoming.context),
    )


def merge_duplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    merged_by_url: dict[str, Candidate] = {}
    order: list[str] = []
    for candidate in candidates:
        key = normalize_url(candidate.url)
        if key not in merged_by_url:
            merged_by_url[key] = candidate
            order.append(key)
            continue
        merged_by_url[key] = merge_two_candidates(merged_by_url[key], candidate)
    return [merged_by_url[key] for key in order]


def context_for_article_variant(is_roundup: bool, candidate_context: str) -> str:
    return "" if is_roundup else candidate_context


def is_third_party_platform_availability_candidate(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if app_store_policy_score(lower) > 0:
        return False
    if score_terms(lower, THIRD_PARTY_PLATFORM_TERMS) <= 0:
        return False
    if score_terms(lower, THIRD_PARTY_PLATFORM_ACTION_TERMS) <= 0:
        return False
    if has_apple_first_party_release_context(lower):
        return False
    return True


def is_routine_third_party_apple_platform_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if has_apple_first_party_release_context(lower):
        return False
    platform_score = score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "mac",
            "apple watch",
            "vision pro",
            "ios",
            "ipados",
            "macos",
            "watchos",
            "visionos",
            "app store",
            "苹果应用商店",
        ],
    )
    third_party_subject_score = score_terms(
        lower,
        [
            "third-party",
            "third party",
            "app developers",
            "bear app",
            "lettera",
            "markdown editor",
            "omnigroup",
            "omnioutliner",
            "whatsapp",
            "msi",
            "benq",
            "第三方",
        ],
    )
    action_score = score_terms(
        lower,
        [
            "available",
            "availability",
            "beta",
            "launch",
            "launches",
            "released",
            "roll out",
            "rolls out",
            "rolling out",
            "test",
            "testing",
            "tests",
            "testflight",
            "updated",
            "update",
            "version",
            "support",
            "supports",
            "localization",
            "languages",
            "上架",
            "上线",
            "发布",
            "更新",
            "支持",
            "适配",
            "语言",
        ],
    )
    return platform_score > 0 and third_party_subject_score > 0 and action_score > 0


def score_messages_platform_terms(text: str) -> int:
    lower = text.lower()
    score = 0
    for term in MESSAGE_PLATFORM_TERMS:
        if not term_present(lower, term.lower()):
            continue
        pattern = re.compile(
            r"(?:\b(?:no|not|without|never)\b|没有|未|尚未|无|并未|不(?:会|能|是)?)"
            r"[^。.!?]{0,32}"
            r"(?:integrat\w*|available|support\w*|use|接入|支持|可用)?"
            r"[^。.!?]{0,32}"
            + re.escape(term.lower()),
            re.I,
        )
        if pattern.search(lower):
            continue
        score += 1
    return score


def score_messages_platform_actions(text: str) -> int:
    lower = text.lower()
    score = 0
    for term in MESSAGE_PLATFORM_ACTION_TERMS:
        if not term_present(lower, term.lower()):
            continue
        pattern = re.compile(
            r"(?:\b(?:no|not|without|never)\b|没有|未|尚未|无|并未|不(?:会|能|是)?)"
            r"[^。.!?]{0,32}"
            + re.escape(term.lower()),
            re.I,
        )
        if pattern.search(lower):
            continue
        score += 1
    return score


def is_relevant_candidate(candidate: Candidate, source: Source) -> bool:
    if is_source_daily_brief_candidate(candidate, source):
        return False
    url_lower = candidate.url.lower()
    text = f"{candidate.title} {candidate.summary} {candidate.context}"
    lower_text = text.lower()
    if any(fragment in url_lower for fragment in URL_EXCLUDE_FRAGMENTS):
        if not allowed_url_excluded_candidate(candidate, source, text):
            return False
    if should_hard_exclude_candidate(text):
        return False
    apple_score = effective_apple_term_score(text)
    action_score = score_terms(text, POSITIVE_ACTION_TERMS)
    strong_score = score_terms(text, STRONG_NEWS_ACTION_TERMS)
    exclude_score = score_terms(text, EXCLUDE_TERMS)

    if source.name == "Apple Newsroom" and action_score > 0:
        apple_score = max(apple_score, 1)

    if apple_score <= 0:
        return False
    if is_routine_retail_discount_story(candidate.title, text):
        return False
    candidate_event_kind = detect_event_kind(candidate.title, candidate.summary, [candidate.context])
    if candidate_event_kind == "hardware_market":
        candidate_tier, _ = classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [candidate.context],
            candidate.source,
        )
        if candidate_tier == "strong":
            return True
    if is_apple_developer_tool_story(text):
        return True
    if is_official_apple_accessory_market_story(text):
        return True
    if is_official_apple_refurbished_product_story(text):
        return True
    if is_unreleased_beats_hardware_story(text):
        return True
    if is_apple_books_or_store_platform_trust_story(candidate.title, text):
        return True
    if is_apple_hardware_product_launch_story(text, candidate.title):
        return True
    if is_broad_apple_product_roadmap_story(text):
        return True
    if is_apple_company_org_change_story(text):
        return True
    if is_apple_executive_company_story(text):
        return True
    if is_apple_strategic_transaction_story(text):
        return True
    if candidate_event_kind == "service_content":
        return True
    if is_apple_research_candidate(text):
        return True
    if is_apple_health_data_research_candidate(text):
        return True
    if is_apple_os_feature_or_summary_story(text):
        return True
    if is_messages_platform_candidate(text):
        return True
    if candidate_event_kind == "ecosystem_interop":
        return True
    if is_third_party_platform_availability_candidate(text):
        return True
    if is_routine_third_party_apple_platform_story(text):
        return True
    official_service_promo = (
        score_terms(
            lower_text,
            ["apple card", "apple pay", "app store", "apple music", "apple tv", "icloud"],
        )
        > 0
        and score_terms(
            lower_text,
            ["promo", "promotion", "offer", "cash back", "daily cash", "free trial"],
        )
        > 0
    )
    if official_service_promo:
        return True
    if action_score <= 0 and strong_score <= 0 and source.name != "Apple Newsroom":
        return False
    if exclude_score > 0 and strong_score <= 0:
        return False
    return True


def source_default_tz(sources_by_name: dict[str, Source], source_name: str) -> str:
    source = sources_by_name.get(source_name)
    return source.default_tz if source else "UTC"


def tz_from_token(token: str | None, default_tz_name: str) -> Any:
    if token:
        normalized = token.upper().replace(".", "")
        if normalized.startswith(("+", "-")):
            compact = normalized.replace(":", "")
            if re.fullmatch(r"[+-]\d{4}", compact):
                sign = 1 if compact[0] == "+" else -1
                hours = int(compact[1:3])
                minutes = int(compact[3:5])
                return timezone(sign * timedelta(hours=hours, minutes=minutes))
        if normalized in TIMEZONE_ABBREVIATIONS:
            return TIMEZONE_ABBREVIATIONS[normalized]
        if normalized in GENERIC_TIMEZONES:
            tz = zoneinfo_or_none(GENERIC_TIMEZONES[normalized])
            if tz is not None:
                return tz
    tz = zoneinfo_or_none(default_tz_name)
    return tz or timezone.utc


def localize_naive(value: datetime, default_tz_name: str, tz_token: str | None = None) -> datetime:
    return value.replace(tzinfo=tz_from_token(tz_token, default_tz_name))


def parse_datetime_value(raw_value: str, default_tz_name: str) -> datetime | None:
    if not raw_value:
        return None
    raw = html.unescape(strip_tags(raw_value))
    raw = raw.replace("\xa0", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"^(Published|Updated|Posted|Last updated)\s*:?\s*", "", raw, flags=re.I)
    raw = raw.strip(" -|")

    iso_match = re.search(
        r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?",
        raw,
    )
    if iso_match:
        iso_text = iso_match.group(0).replace("Z", "+00:00")
        if "T" not in iso_text:
            iso_text = iso_text.replace(" ", "T", 1)
        if re.search(r"[+-]\d{4}$", iso_text):
            iso_text = f"{iso_text[:-2]}:{iso_text[-2:]}"
        iso_text = re.sub(
            r"(\.\d{6})\d+(?=(?:[+-]\d{2}:?\d{2})?$)",
            r"\1",
            iso_text,
        )
        try:
            parsed = datetime.fromisoformat(iso_text)
            if parsed.tzinfo is None:
                parsed = localize_naive(parsed, default_tz_name)
            return parsed
        except ValueError:
            pass

    slash_match = re.search(
        r"(\d{4})/(\d{1,2})/(\d{1,2})\s+"
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
        raw,
    )
    if slash_match:
        year_s, month_s, day_s, hour_s, minute_s, second_s = slash_match.groups()
        parsed = datetime(
            int(year_s),
            int(month_s),
            int(day_s),
            int(hour_s),
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name)

    month_pattern = (
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)"
    )
    natural_match = re.search(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*"
        + month_pattern
        + r"\s+(\d{1,2}),?\s+(\d{4})(?:,)?(?:\s+(?:at\s+)?)?"
        + r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
        + r"(a\.?m\.?|p\.?m\.?|AM|PM)?\s*([A-Z]{1,4}|[+-]\d{2}:?\d{2})?",
        raw,
        re.I,
    )
    if natural_match:
        month_name, day_s, year_s, hour_s, minute_s, second_s, ampm, tz_token = (
            natural_match.groups()
        )
        hour = int(hour_s)
        if ampm:
            ampm_clean = ampm.lower().replace(".", "")
            if ampm_clean == "pm" and hour != 12:
                hour += 12
            elif ampm_clean == "am" and hour == 12:
                hour = 0
        parsed = datetime(
            int(year_s),
            MONTHS[month_name.lower().rstrip(".")],
            int(day_s),
            hour,
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name, tz_token)

    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed:
            if parsed.tzinfo is None:
                parsed = localize_naive(parsed, default_tz_name)
            return parsed
    except Exception:
        pass

    chinese_match = re.search(
        r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*"
        r"(\d{1,2})[:：](\d{2})(?:[:：](\d{2}))?",
        raw,
    )
    if chinese_match:
        year_s, month_s, day_s, hour_s, minute_s, second_s = chinese_match.groups()
        year = int(year_s) if year_s else datetime.now().year
        parsed = datetime(
            year,
            int(month_s),
            int(day_s),
            int(hour_s),
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name)

    month_match = re.search(
        month_pattern
        + r"\s+(\d{1,2}),?\s+(\d{4})(?:,)?(?:\s+(?:at\s+)?)?"
        + r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
        + r"(a\.?m\.?|p\.?m\.?|AM|PM)?\s*([A-Z]{1,4}|[+-]\d{2}:?\d{2})?",
        raw,
        re.I,
    )
    if month_match:
        month_name, day_s, year_s, hour_s, minute_s, second_s, ampm, tz_token = (
            month_match.groups()
        )
        hour = int(hour_s)
        if ampm:
            ampm_clean = ampm.lower().replace(".", "")
            if ampm_clean == "pm" and hour != 12:
                hour += 12
            elif ampm_clean == "am" and hour == 12:
                hour = 0
        parsed = datetime(
            int(year_s),
            MONTHS[month_name.lower().rstrip(".")],
            int(day_s),
            hour,
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name, tz_token)

    numeric_match = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4})[,\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
        r"(a\.?m\.?|p\.?m\.?|AM|PM)?\s*([A-Z]{1,4}|[+-]\d{2}:?\d{2})?",
        raw,
        re.I,
    )
    if numeric_match:
        month_s, day_s, year_s, hour_s, minute_s, second_s, ampm, tz_token = (
            numeric_match.groups()
        )
        hour = int(hour_s)
        if ampm:
            ampm_clean = ampm.lower().replace(".", "")
            if ampm_clean == "pm" and hour != 12:
                hour += 12
            elif ampm_clean == "am" and hour == 12:
                hour = 0
        parsed = datetime(
            int(year_s),
            int(month_s),
            int(day_s),
            hour,
            int(minute_s),
            int(second_s or 0),
        )
        return localize_naive(parsed, default_tz_name, tz_token)

    return None


def parse_date_only_value(raw_value: str, default_tz_name: str) -> datetime | None:
    if not raw_value:
        return None
    raw = html.unescape(strip_tags(raw_value))
    raw = raw.replace("\xa0", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = raw.strip(" -|")
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})(?:Z)?\b", raw)
    if iso_match:
        year_s, month_s, day_s = iso_match.groups()
        parsed = datetime(int(year_s), int(month_s), int(day_s), 12, 0, 0)
        return localize_naive(parsed, default_tz_name)

    month_pattern = (
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)"
    )
    natural_match = re.search(
        month_pattern + r"\s+(\d{1,2}),?\s+(\d{4})",
        raw,
        re.I,
    )
    if natural_match:
        month_name, day_s, year_s = natural_match.groups()
        parsed = datetime(
            int(year_s),
            MONTHS[month_name.lower().rstrip(".")],
            int(day_s),
            12,
            0,
            0,
        )
        return localize_naive(parsed, default_tz_name)
    return None


def json_ld_objects(text: str) -> list[Any]:
    objects: list[Any] = []
    for match in re.finditer(
        r"(?is)<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        text,
    ):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            objects.append(json.loads(raw))
        except json.JSONDecodeError:
            raw = re.sub(r"(?is)^\s*<!--|-->\s*$", "", raw).strip()
            try:
                objects.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return objects


def iter_json_ld_nodes(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from iter_json_ld_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_json_ld_nodes(item)


def json_type_names(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    raw_type = value.get("@type")
    if isinstance(raw_type, str):
        return {raw_type}
    if isinstance(raw_type, list):
        return {item for item in raw_type if isinstance(item, str)}
    return set()


def find_json_key(value: Any, keys: set[str]) -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str):
                return item
        for item in value.values():
            found = find_json_key(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_json_key(item, keys)
            if found:
                return found
    return ""


def meta_content(text: str, names: list[str]) -> str:
    for name in names:
        pattern = (
            r"(?is)<meta\b(?=[^>]*(?:property|name|itemprop)=['\"]"
            + re.escape(name)
            + r"['\"])[^>]*content=['\"]([^'\"]+)['\"][^>]*>"
        )
        match = re.search(pattern, text)
        if match:
            return html.unescape(match.group(1)).strip()
        pattern = (
            r"(?is)<meta\b(?=[^>]*content=['\"]([^'\"]+)['\"])[^>]*"
            r"(?:property|name|itemprop)=['\"]"
            + re.escape(name)
            + r"['\"][^>]*>"
        )
        match = re.search(pattern, text)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def extract_title(text: str, fallback: str) -> str:
    title = meta_content(text, ["og:title", "twitter:title"])
    if title:
        return strip_tags(title)
    h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", text)
    if h1:
        return strip_tags(h1.group(1))
    title_tag = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    if title_tag:
        return strip_tags(title_tag.group(1))
    return fallback.strip()


TRAILING_PROMO_SECTION_PATTERNS = (
    r"my\s+favorite\s+apple\s+accessory\s+recommendations",
    r"worth\s+checking\s+out\s+on\s+amazon",
    r"chance(?:'|’|&#8217;|&rsquo;)s\s+favorites",
    r"do\s+more\s+with\s+your\s+apple\s+products",
    r"official\s+apple\s+store\s+on\s+amazon",
    r"amazon\s+prime\s+day\s+\d{4}",
    r"(?:prime\s+day\s+)?savings\s+on\s+apple\s+gear",
    r"apple\s+gear\s+savings",
    r"best\s+(?:iphone|ipad|mac|airpods|apple\s+tv\s+4k|apple\s+watch(?:\s+and\s+iphone)?|iphone\s+and\s+apple\s+watch|vision\s+pro|apple)\s+"
    r"(?:accessories|deals\s+and\s+accessories)",
)


def remove_trailing_promo_sections(text: str) -> str:
    """Cut 9to5-style affiliate recommendation blocks after the real article body."""
    earliest: int | None = None
    for pattern in TRAILING_PROMO_SECTION_PATTERNS:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        leading_text = strip_tags(text[: match.start()])
        if len(leading_text) < 120:
            continue
        earliest = match.start() if earliest is None else min(earliest, match.start())
    if earliest is None:
        return text
    return text[:earliest]


def remove_noise_blocks(text: str) -> str:
    text = remove_trailing_promo_sections(text)
    cleaned = re.sub(
        r"(?is)<!--\s*相关文章\s*-->.*?(?=<!--\s*评论\s*-->|<div\b[^>]+id=['\"]post_comm['\"]|</article>|</main>|$)",
        " ",
        text,
    )
    cleaned = re.sub(
        r"(?is)<div\b(?=[^>]*class=['\"][^'\"]*related_post[^'\"]*['\"])[^>]*>.*?"
        r"(?=<!--\s*评论\s*-->|<div\b[^>]+id=['\"]post_comm['\"]|</article>|</main>|$)",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"(?is)<div\b(?=[^>]*id=['\"]fls['\"])[^>]*>.*?(?:</div>|$)",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"(?is)<p\b(?=[^>]*(?:class|id)=['\"][^'\"]*(?:ad-tips|advertis|newsletter|subscribe)[^'\"]*['\"])[^>]*>.*?</p>",
        " ",
        cleaned,
    )
    noisy_attr = (
        r"(?:related|recirc|recommend|featured|newsletter|subscribe|comment|"
        r"advertis|ad-container|affiliate|post-nav|sharedaddy|social|share|"
        r"navs_newsinfo|xg_newsinfo)"
    )
    pattern = (
        r"(?is)<(?P<tag>aside|section|div|nav)\b(?=[^>]*(?:class|id)=['\"][^'\"]*"
        + noisy_attr
        + r"[^'\"]*['\"])[^>]*>.*?</(?P=tag)>"
    )
    previous = None
    for _ in range(4):
        if cleaned == previous:
            break
        previous = cleaned
        cleaned = re.sub(pattern, " ", cleaned)
    return remove_trailing_promo_sections(cleaned)


PREFERRED_CONTENT_CLASS_FRAGMENTS = (
    "post-content",
    "post_content",
    "entry-content",
    "article-content",
    "article-body",
    "article__body",
    "single__content",
    "story-content",
    "pagebody-copy",
    "article-copy",
    "body-copy",
)


def balanced_element_inner(text: str, start_index: int, tag_name: str) -> str:
    start_match = re.match(rf"(?is)<{tag_name}\b[^>]*>", text[start_index:])
    if not start_match:
        return ""
    inner_start = start_index + start_match.end()
    depth = 1
    for match in re.finditer(rf"(?is)</?{tag_name}\b[^>]*>", text[inner_start:]):
        token = match.group(0)
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return text[inner_start : inner_start + match.start()]
        elif not token.endswith("/>"):
            depth += 1
    return text[inner_start:]


def preferred_content_scope(text: str) -> str:
    candidates: list[tuple[int, str]] = []
    pattern = re.compile(r"(?is)<(?P<tag>div|section|article|main)\b(?P<attrs>[^>]*)>")
    for match in pattern.finditer(text):
        attrs = match.group("attrs").lower()
        if not any(fragment in attrs for fragment in PREFERRED_CONTENT_CLASS_FRAGMENTS):
            continue
        inner = balanced_element_inner(text, match.start(), match.group("tag").lower())
        if not inner:
            continue
        plain = strip_tags(remove_noise_blocks(inner))
        paragraph_score = len(re.findall(r"(?is)<(?:p|li)\b", inner)) * 200
        heading_penalty = 250 if "sidebar" in attrs or "is-clickable-card" in attrs else 0
        score = paragraph_score + min(len(plain), 4000) - heading_penalty
        if len(plain) >= 80:
            candidates.append((score, inner))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return remove_noise_blocks(candidates[0][1])


def article_scope(text: str) -> str:
    preferred = preferred_content_scope(text)
    if preferred:
        return preferred
    for tag in ["article", "main"]:
        match = re.search(rf"(?is)<{tag}\b[^>]*>(.*?)</{tag}>", text)
        if match:
            return remove_noise_blocks(match.group(1))
    return remove_noise_blocks(text)


class ArticleTextExtractor(HTMLParser):
    block_tags = {"p", "li", "h2", "h3", "tr", "blockquote"}
    div_class_fragments = (
        "pagebody-copy",
        "article-copy",
        "body-copy",
        "entry-content",
        "post-content",
        "story-content",
    )
    void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.units: list[tuple[str, str]] = []
        self._capture_tag: str | None = None
        self._capture_kind = ""
        self._depth = 0
        self._parts: list[str] = []

    def _is_block(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in self.block_tags:
            return True
        if tag != "div":
            return False
        classes = " ".join(value or "" for name, value in attrs if name.lower() == "class")
        return any(fragment in classes for fragment in self.div_class_fragments)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._capture_tag:
            if tag == "br":
                self._parts.append(" ")
            if tag not in self.void_tags:
                self._depth += 1
            return
        if self._is_block(tag, attrs):
            self._capture_tag = tag
            self._capture_kind = tag
            self._depth = 1
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_tag:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._capture_tag:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = re.sub(r"\s+", " ", "".join(self._parts)).strip()
        min_len = 20 if self._capture_kind in {"li", "tr"} else 30
        if len(text) >= min_len:
            self.units.append((self._capture_kind, html.unescape(text)))
        self._capture_tag = None
        self._capture_kind = ""
        self._parts = []


def extract_text_units(text: str) -> list[tuple[str, str]]:
    scoped_text = article_scope(text)
    parser = ArticleTextExtractor()
    try:
        parser.feed(scoped_text)
    except Exception:
        parser.units = []
    units = parser.units
    if units:
        return units

    fallback_units: list[tuple[str, str]] = []
    for match in re.finditer(r"(?is)<(?P<tag>p|li|h2|h3|tr)\b[^>]*>(?P<body>.*?)</(?P=tag)>", scoped_text):
        cleaned = strip_tags(match.group("body"))
        min_len = 20 if match.group("tag").lower() in {"li", "tr"} else 30
        if len(cleaned) >= min_len:
            fallback_units.append((match.group("tag").lower(), cleaned))
    return fallback_units


def fact_noise(value: str) -> bool:
    lower = value.lower()
    if re.search(r"广告声明|文内含有的对外跳转链接|it之家所有文章均包含本声明", lower, re.I):
        return True
    if re.search(r"当前位置[:：]|当前位置：首页|相关阅读[:：]|相关文章[:：]|延伸阅读[:：]|更多阅读[:：]|豫icp备|icp备|公网安备", lower, re.I):
        return True
    if re.match(r"^apple (?:music|arcade|news\+|tv\+|one(?: bundle)?)\s+[–-]\s*[$￥¥€£]?\d", lower) and "after free trial" in lower:
        return True
    if (
        re.search(r"\bapple (?:music|arcade|news\+|tv\+?|one(?: bundle)?)\b", lower)
        and re.search(r"\b(?:available|requires|subscription|sign up|per month|free trial)\b", lower)
        and re.search(r"(?:[$€£¥￥]\d|\bfree trial\b|\bsubscription\b)", lower)
        and score_terms(
            lower,
            [
                "cash back",
                "chase",
                "credit card",
                "daily cash",
                "discount",
                "offer",
                "perk",
                "promo",
                "promotion",
                "reserve",
                "sapphire",
                "优惠",
                "折扣",
                "促销",
                "权益",
            ],
        )
        == 0
    ):
        return True
    if (
        re.search(r"\b(?:amazon|amzn\.to|best buy)\b", lower)
        and re.search(r"\b(?:priced from|currently priced|reg\.|record low|discount|deal)\b", lower)
    ):
        return True
    if len(value) < 140 and re.match(r"^《.+》$", value.strip()):
        return True
    if (
        len(value) < 120
        and not re.search(r"[，,。；;]", value)
        and score_terms(
            lower,
            ["首发", "铺路", "嘲笑", "反转", "退场", "曝光", "前瞻", "发布"],
        )
        > 0
        and (effective_apple_term_score(value) > 0 or loose_apple_product_marker(value))
    ):
        return True
    if (
        len(value) < 120
        and not re.search(r"[，,。；;]", value)
        and (effective_apple_term_score(value) > 0 or loose_apple_product_marker(value))
        and ("！" in value or "!" in value)
        and ("：" in value or ":" in value)
    ):
        return True
    if (
        len(value) < 100
        and not re.search(r"[，,。；;]", value)
        and (effective_apple_term_score(value) > 0 or loose_apple_product_marker(value))
        and ("：" in value or ":" in value)
    ):
        return True
    if re.match(r"^[a-z]{3} [a-z]{3} \d{2} \d{4}, \d{1,2}:\d{2} [ap]m [a-z]{3}\b", lower) and "minute read" in lower:
        return True
    if lower.startswith(("worth checking out", "related:", "related stories")):
        return True
    if (
        len(value) < 140
        and not re.search(r"[.!?。！？]$", value)
        and re.search(
            r"\b(will reportedly|reportedly add|here'?s|every new feature|new features to|what rumors say|"
            r"coming soon|launch later|set to launch|feature release timing)\b",
            lower,
        )
    ):
        return True
    if len(value) < 120 and lower.endswith(", more") and "more than" not in lower:
        return True
    if len(value) < 120 and lower.endswith(" and more") and "more than" not in lower:
        return True
    if len(value) < 80 and re.search(
        r"subscribe|newsletter|advertisement|cookie|privacy policy|share article|"
        r"media text of this article|read more|related stories|open menu|login register",
        lower,
    ):
        return True
    if lower.startswith(("share article", "media text of this article", "advertisement", "subscribe")):
        return True
    return False


def clean_fact_text(value: str) -> str:
    value = strip_tags(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(?:App Review|Account Fraud|Ratings and Reviews|Payment and Credit Card Fraud|Keeping Kids Safe)\s+", "", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    return value


def data_value_count(value: str) -> int:
    return sum(1 for match in DATA_VALUE_PATTERN.finditer(value) if re.search(r"\d", match.group(0)))


def split_fact_candidates(tag: str, value: str) -> list[str]:
    if tag in {"li", "tr"} or len(value) <= 700:
        return [value]
    parts = [
        clean_fact_text(part)
        for part in re.split(r"(?<=[.!?。！？])\s+", value)
        if clean_fact_text(part)
    ]
    return parts or [value]


def is_key_fact(tag: str, value: str) -> bool:
    numbers = data_value_count(value)
    is_short_list_fact = (
        tag in {"li", "tr"}
        and len(value) >= 20
        and numbers > 0
        and (effective_apple_term_score(value) > 0 or loose_apple_product_marker(value))
    )
    if (len(value) < 35 and not is_short_list_fact) or fact_noise(value):
        return False
    has_context = score_terms(value, FACT_CONTEXT_TERMS) > 0
    has_feature_list = FEATURE_LIST_PATTERN.search(value) is not None
    has_list_shape = tag in {"li", "tr"} or len(re.findall(r"[,;；、，]", value)) >= 2
    if is_short_list_fact:
        return True
    if numbers >= 2:
        return True
    if numbers and (has_context or has_list_shape or has_feature_list):
        return True
    if tag in {"li", "tr"} and has_context and (has_feature_list or len(value) <= 500):
        return True
    if tag in {"li", "tr"} and len(value) <= 500 and (has_feature_list or has_list_shape):
        return True
    if has_context and has_feature_list and has_list_shape:
        return True
    return False


def add_unique_text(
    parts: list[str],
    seen: set[str],
    value: str,
    max_chars: int = 900,
    min_chars: int = 35,
) -> bool:
    cleaned = clean_fact_text(value)
    if len(cleaned) > max_chars:
        sentences = re.split(r"(?<=[.!?。！？])\s+", cleaned)
        shortened = ""
        for sentence in sentences:
            next_value = f"{shortened} {sentence}".strip()
            if len(next_value) > max_chars:
                break
            shortened = next_value
        cleaned = shortened or cleaned[:max_chars].rstrip()
    if len(cleaned) < min_chars:
        return False
    compact = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", cleaned.lower()).strip()
    if not compact:
        return False
    key = compact[:180]
    for existing in seen:
        if key in existing or existing in key:
            return False
    parts.append(cleaned)
    seen.add(key)
    return True


def key_fact_min_chars(value: str) -> int:
    cleaned = clean_fact_text(value)
    if (
        20 <= len(cleaned) < 35
        and data_value_count(cleaned) > 0
        and (effective_apple_term_score(cleaned) > 0 or loose_apple_product_marker(cleaned))
    ):
        return 20
    return 35


def extract_key_facts(text: str, title: str, source_name: str) -> list[str]:
    limit = MAX_OFFICIAL_KEY_FACTS if source_name in OFFICIAL_FACT_SOURCES else MAX_KEY_FACTS
    facts: list[str] = []
    seen: set[str] = set()
    title_text = clean_fact_text(title)
    for tag, unit in extract_text_units(text):
        cleaned = clean_fact_text(unit)
        if not cleaned:
            continue
        if title_text and cleaned.lower() == title_text.lower():
            continue
        for candidate in split_fact_candidates(tag, cleaned):
            if (
                source_name not in OFFICIAL_FACT_SOURCES
                and tag in {"h2", "h3"}
                and data_value_count(candidate) == 0
            ):
                continue
            if is_key_fact(tag, candidate):
                min_chars = 20 if tag in {"li", "tr"} else key_fact_min_chars(candidate)
                add_unique_text(facts, seen, candidate, min_chars=min_chars)
                if len(facts) >= limit:
                    return facts
    return facts


def extract_summary(text: str, fallback: str) -> str:
    scoped_text = article_scope(text)
    parts: list[str] = []
    seen: set[str] = set()
    description = meta_content(
        text,
        ["og:description", "twitter:description", "description", "Description"],
    )
    if description:
        cleaned_description = strip_tags(description)
        if cleaned_description:
            parts.append(cleaned_description)
            seen.add(cleaned_description.lower()[:120])
    for match in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", scoped_text):
        cleaned = strip_tags(match.group(1))
        if len(cleaned) >= 60 and not fact_noise(cleaned) and not re.search(
            r"newsletter|subscribe|advertis|open menu|front page|login register|"
            r"visit forums|roundups|buyer'?s guide|direct messages|anonymous form|"
            r"广告声明|文内含有的对外跳转链接|IT之家所有文章均包含本声明|"
            r"当前位置[:：]|相关阅读[:：]|相关文章[:：]|延伸阅读[:：]|ICP备|公网安备",
            cleaned,
            re.I,
        ):
            key = cleaned.lower()[:120]
            if key not in seen:
                parts.append(cleaned)
                seen.add(key)
        if len(parts) >= 5:
            break
    if parts:
        return " ".join(parts)
    return strip_tags(fallback)


def combine_summaries(primary: str, secondary: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in [primary, secondary]:
        cleaned = clean_sentence(value)
        if not cleaned:
            continue
        for sentence in re.split(r"(?<=[.!?。！？])\s+", cleaned):
            sentence = clean_sentence(sentence)
            if not sentence:
                continue
            key = sentence.lower()[:120]
            if key in seen:
                continue
            parts.append(sentence)
            seen.add(key)
            if len(parts) >= 8:
                break
    return " ".join(parts)


def is_roundup_article_title(title: str) -> bool:
    lower = title.lower()
    return score_terms(
        lower,
        [
            "早报",
            "科技早报",
            "科技早参",
            "每日早报",
            "daily brief",
            "daily briefing",
            "morning brief",
            "morning briefing",
            "roundup",
        ],
    ) > 0


def structured_roundup_item_candidates(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []

    def flush_current() -> None:
        nonlocal current
        if not current:
            return
        item = clean_fact_text(" ".join(current))
        if len(item) >= 18:
            items.append(item)
        current = []

    scoped_text = article_scope(text)
    units: list[tuple[str, str]] = []
    for match in re.finditer(r"(?is)<(?P<tag>h2|h3|p|li)\b[^>]*>(?P<body>.*?)</(?P=tag)>", scoped_text):
        cleaned = clean_fact_text(match.group("body"))
        if cleaned:
            units.append((match.group("tag").lower(), cleaned))
    if not units:
        units = extract_text_units(text)

    for tag, value in units:
        cleaned = clean_fact_text(value)
        if tag in {"h2", "h3"}:
            flush_current()
            if len(cleaned) < 8 or fact_noise(cleaned):
                continue
            current = [cleaned]
            continue
        if len(cleaned) < 18 or fact_noise(cleaned):
            continue
        if current:
            current.append(cleaned)
            continue
        if re.match(r"^\d{1,2}[、.．]\s*", cleaned):
            for part in split_roundup_item_candidates(cleaned):
                if len(part) >= 18:
                    items.append(part)
    flush_current()
    return items


def clean_roundup_item_text(value: str) -> str:
    cleaned = clean_fact_text(value)
    cleaned = re.sub(r">>\s*查看详情", "", cleaned)
    cleaned = re.sub(r"^\d{1,2}[、.．]\s*", "", cleaned)
    return clean_fact_text(cleaned)


def split_roundup_item_candidates(value: str) -> list[str]:
    cleaned = clean_roundup_item_text(value)
    if not cleaned:
        return []
    rough_parts = re.split(r"[；;]\s*|(?=\b\d{1,2}[、.．])|(?=\s\d{1,2}[、.．])", cleaned)
    parts: list[str] = []
    for part in rough_parts:
        part = clean_roundup_item_text(part)
        if len(part) >= 18:
            parts.append(part)
    return parts or [cleaned]


def is_apple_roundup_item(value: str) -> bool:
    lower = value.lower()
    if re.search(r"(?:not|no)\s+(?:direct\s+)?relation(?:ship)?\s+to\s+apple|unrelated\s+to\s+apple|与苹果[^。！？.!?]{0,16}无(?:直接)?关系|和苹果[^。！？.!?]{0,16}无(?:直接)?关系", lower):
        return False
    if (
        is_non_apple_primary_subject_with_incidental_apple_context(value, value)
        or is_former_apple_staff_background_story(value)
        or is_third_party_app_or_service_status_story(value, value)
        or is_third_party_accessory_platform_compatibility_story(value, value)
    ):
        return False
    apple_score = effective_apple_term_score(value) + score_terms(lower, ["tim cook", "库克"])
    if apple_score <= 0 and not loose_apple_product_marker(value):
        return False
    action_score = score_terms(
        lower,
        POSITIVE_ACTION_TERMS
        + STRONG_NEWS_ACTION_TERMS
        + [
            "price increase",
            "price increases",
            "cost increase",
            "memory shortage",
            "chip shortage",
            "storage shortage",
            "涨价",
            "上调",
            "升至",
            "提升",
            "提高",
            "配备",
            "升级到",
            "升级至",
            "短缺",
            "成本",
            "不可避免",
        ],
    )
    return action_score > 0


def roundup_title_from_item(value: str) -> str:
    cleaned = clean_roundup_item_text(value)
    first_sentence = re.split(r"(?<=[.!?。！？])\s+", cleaned)[0]
    first_sentence = re.sub(r"\s*>>\s*查看详情.*$", "", first_sentence)
    if len(first_sentence) <= 140:
        return first_sentence
    return first_sentence[:137].rstrip() + "..."


def focus_roundup_article(
    title: str,
    summary: str,
    key_facts: list[str],
    raw_text: str = "",
) -> tuple[str, str, list[str]]:
    if not is_roundup_article_title(title):
        return title, summary, key_facts
    focused: list[str] = []
    seen: set[str] = set()
    structured_items = structured_roundup_item_candidates(raw_text) if raw_text else []
    if structured_items:
        item_candidates = structured_items
    else:
        item_candidates = []
        for value in [title, summary, *key_facts]:
            item_candidates.extend(split_roundup_item_candidates(value))
    for item in item_candidates:
        if is_apple_roundup_item(item):
            add_unique_text(focused, seen, item)
    if not focused:
        return title, summary, key_facts
    focused_title = roundup_title_from_item(focused[0])
    focused_summary = " ".join(focused[:5])
    return focused_title, focused_summary, focused[:MAX_KEY_FACTS]


def roundup_article_variants(
    original_title: str,
    title: str,
    summary: str,
    key_facts: list[str],
) -> list[tuple[str, str, list[str]]]:
    if not is_roundup_article_title(original_title) or len(key_facts) <= 1:
        return [(title, summary, key_facts)]
    variants: list[tuple[str, str, list[str]]] = []
    for fact in key_facts:
        cleaned_fact = clean_roundup_item_text(fact)
        if not is_apple_roundup_item(cleaned_fact):
            continue
        variants.append((roundup_title_from_item(cleaned_fact), cleaned_fact, [cleaned_fact]))
    return variants or [(title, summary, key_facts)]


def extract_time_candidates(text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for obj in json_ld_objects(text):
        for key_group, label in [
            ({"datePublished", "dateCreated"}, "json-ld datePublished"),
            ({"dateModified", "uploadDate"}, "json-ld dateModified"),
        ]:
            found = find_json_key(obj, key_group)
            if found:
                candidates.append((found, label))

    for names, label in [
        (
            [
                "article:published_time",
                "article:published",
                "datePublished",
                "date",
                "pubdate",
                "publish_date",
                "dc.date",
                "dc.date.issued",
            ],
            "meta published",
        ),
        (["article:modified_time", "dateModified", "lastmod"], "meta modified"),
    ]:
        found = meta_content(text, names)
        if found:
            candidates.append((found, label))

    for match in re.finditer(r"(?is)<time\b([^>]*)>(.*?)</time>", text):
        attrs, body = match.groups()
        datetime_match = re.search(r"""datetime\s*=\s*['"]([^'"]+)['"]""", attrs, re.I)
        if datetime_match:
            candidates.append((datetime_match.group(1), "time datetime"))
        body_text = strip_tags(body)
        if body_text:
            candidates.append((body_text, "time text"))

    text_only = strip_tags(text[:120_000])
    date_patterns = [
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}(?:,)?\s+"
        r"(?:at\s+)?\d{1,2}:\d{2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|AM|PM)?\s*"
        r"(?:PST|PDT|PT|EST|EDT|ET|GMT|UTC|[+-]\d{2}:?\d{2})?",
        r"(?:\d{4}\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}\s*日\s*"
        r"\d{1,2}[:：]\d{2}(?:[:：]\d{2})?",
        r"\d{4}/\d{1,2}/\d{1,2}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?",
        r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2})?"
        r"(?:Z|[+-]\d{2}:?\d{2})?",
    ]
    for pattern in date_patterns:
        for match in re.finditer(pattern, text_only, re.I):
            candidates.append((match.group(0), "body date pattern"))
            if len(candidates) > 20:
                return candidates
    return candidates


def extract_apple_newsroom_time_candidates(text: str) -> list[tuple[str, str, bool]]:
    """Return Apple Newsroom publication candidates only.

    Newsroom pages often refresh dateModified and VideoObject uploadDate when
    media assets change. Those values are not the article's publication time.
    """
    candidates: list[tuple[str, str, bool]] = []
    for obj in json_ld_objects(text):
        for node in iter_json_ld_nodes(obj):
            if not isinstance(node, dict):
                continue
            type_names = json_type_names(node)
            if "NewsArticle" not in type_names and "Article" not in type_names:
                continue
            raw = node.get("datePublished") or node.get("dateCreated")
            if isinstance(raw, str) and raw.strip():
                candidates.append((raw, "apple newsroom datePublished", True))

    for names, label in [
        (
            [
                "article:published_time",
                "article:published",
                "datePublished",
                "pubdate",
                "publish_date",
                "dc.date",
                "dc.date.issued",
            ],
            "apple newsroom meta published",
        ),
    ]:
        found = meta_content(text, names)
        if found:
            candidates.append((found, label, True))

    visible_date = re.search(
        r"(?is)<[^>]+class=['\"][^'\"]*category-eyebrow__date[^'\"]*['\"][^>]*>(.*?)</[^>]+>",
        text,
    )
    if visible_date:
        cleaned = strip_tags(visible_date.group(1))
        if cleaned:
            candidates.append((cleaned, "apple newsroom visible date", True))

    for match in re.finditer(r"(?is)<time\b([^>]*)>(.*?)</time>", text):
        attrs, body = match.groups()
        datetime_match = re.search(r"""datetime\s*=\s*['"]([^'"]+)['"]""", attrs, re.I)
        if datetime_match:
            candidates.append((datetime_match.group(1), "apple newsroom time datetime", True))
        body_text = strip_tags(body)
        if body_text:
            candidates.append((body_text, "apple newsroom time text", True))
    return candidates


def extract_article(
    candidate: Candidate,
    source: Source,
    text: str,
    diagnostics: dict[str, Any],
) -> tuple[str, str, list[str], datetime | None, str, str, str]:
    title = extract_title(text, candidate.title)
    summary = extract_summary(text, candidate.summary)
    key_facts = extract_key_facts(text, title, source.name)
    title, summary, key_facts = focus_roundup_article(title, summary, key_facts, text)
    default_tz = source.default_tz

    if source.name == "Apple Newsroom":
        time_candidates = extract_apple_newsroom_time_candidates(text)
    else:
        time_candidates = [(raw, label, False) for raw, label in extract_time_candidates(text)]

    for raw, label, allow_date_only in time_candidates:
        parsed = parse_datetime_value(raw, default_tz)
        if parsed is None and allow_date_only:
            parsed = parse_date_only_value(raw, default_tz)
        if parsed is not None:
            return title, summary, key_facts, parsed.astimezone(timezone.utc), raw, label, "detail"

    if source.name == "Apple Newsroom":
        diagnostics.setdefault("low_confidence_articles", []).append(
            {
                "url": candidate.url,
                "source": source.name,
                "reason": "No parseable Apple Newsroom publication date; ignored modified/upload/feed timestamps.",
            }
        )
        return title, summary, key_facts, None, "", "", "missing"

    if candidate.feed_time_raw:
        parsed = parse_datetime_value(candidate.feed_time_raw, default_tz)
        if parsed is not None:
            diagnostics.setdefault("low_confidence_articles", []).append(
                {
                    "url": candidate.url,
                    "source": source.name,
                    "reason": "Used feed timestamp because detail page time was unavailable.",
                }
            )
            return (
                title,
                summary,
                key_facts,
                parsed.astimezone(timezone.utc),
                candidate.feed_time_raw,
                "feed fallback",
                "feed",
            )

    diagnostics.setdefault("low_confidence_articles", []).append(
        {"url": candidate.url, "source": source.name, "reason": "No parseable timestamp."}
    )
    return title, summary, key_facts, None, "", "", "missing"


def discovery_key_facts(candidate: Candidate) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for value in [candidate.summary, candidate.context]:
        cleaned = clean_fact_text(value)
        if not cleaned:
            continue
        for fact in split_fact_candidates("p", cleaned):
            if is_key_fact("p", fact) or (
                effective_apple_term_score(fact) > 0
                and score_terms(fact, POSITIVE_ACTION_TERMS + STRONG_NEWS_ACTION_TERMS) > 0
            ):
                add_unique_text(facts, seen, fact)
    if not facts and candidate.summary:
        add_unique_text(facts, seen, candidate.summary)
    return facts


def fallback_article_from_discovery(
    candidate: Candidate,
    source: Source,
    diagnostics: dict[str, Any],
) -> tuple[str, str, list[str], datetime | None, str, str, str]:
    if source.name == "Apple Newsroom" or not candidate.feed_time_raw:
        return candidate.title, candidate.summary, [], None, "", "", "missing"
    parsed = parse_datetime_value(candidate.feed_time_raw, source.default_tz)
    if parsed is None:
        return candidate.title, candidate.summary, [], None, "", "", "missing"
    summary = clean_fact_text(candidate.summary)
    key_facts = discovery_key_facts(candidate)
    diagnostics.setdefault("low_confidence_articles", []).append(
        {
            "url": candidate.url,
            "source": source.name,
            "reason": "Used discovery timestamp and listing/feed summary because selected detail page fetch failed.",
        }
    )
    return (
        candidate.title,
        summary,
        key_facts,
        parsed.astimezone(timezone.utc),
        candidate.feed_time_raw,
        "discovery fallback",
        "discovery",
    )


def article_tokens(title: str, summary: str) -> set[str]:
    lower = f"{title} {summary}".lower()
    tokens = set()
    for word in re.findall(r"[a-z0-9][a-z0-9+.-]{2,}", lower):
        word = word.strip(".-")
        if len(word) < 3 or word in STOPWORDS:
            continue
        tokens.add(word)
        if word.endswith("ies") and len(word) > 5:
            tokens.add(f"{word[:-3]}y")
        elif word.endswith("s") and len(word) > 4:
            tokens.add(word[:-1])
    for number in re.findall(r"(?<!\d)\d{2}(?!\d)", lower):
        tokens.add(number)
    for term in (
        APPLE_TERMS
        + POSITIVE_ACTION_TERMS
        + SOFTWARE_TERMS
        + HARDWARE_TERMS
        + APPLE_RESEARCH_TERMS
        + APPLE_RESEARCH_ACTION_TERMS
        + APPLE_HEALTH_RESEARCH_PRODUCT_TERMS
        + APPLE_HEALTH_DATA_TERMS
        + APPLE_HEALTH_RESEARCH_ANCHOR_TERMS
    ):
        if term.lower() in BARE_APPLE_CHIP_TERMS and not has_apple_chip_context(lower):
            continue
        if term_present(lower, term.lower()):
            normalized = term.lower().replace(" ", "-")
            if normalized not in STOPWORDS:
                tokens.add(normalized)
    for phrase, token in CROSS_LANGUAGE_TOKEN_MAP.items():
        if phrase in lower:
            tokens.add(token)
    if "股价" in lower:
        tokens.add("shares")
    return tokens


APPLE_PRICE_TIMING_FACETS = {
    "apple-current-product-price-increase",
    "apple-future-product-price-forecast",
    "apple-retail-promotion-price-context",
}

APPLE_PRICE_DETAIL_FACETS = {
    "apple-price-external-reaction",
    "apple-price-retailer-retroactive-adjustment",
    "apple-price-supplier-cost-dispute",
    "apple-refurbished-store-price-context",
}

APPLE_PRICE_SUBTOPIC_FACETS = APPLE_PRICE_TIMING_FACETS | APPLE_PRICE_DETAIL_FACETS


REGION_TERMS = {
    "india": ["india", "indian", "cci", "印度"],
    "texas": ["texas", "德州", "得州"],
    "germany": ["germany", "german", "berlin", "德国", "柏林"],
    "europe": ["europe", "european", "eu", "欧盟", "欧洲"],
    "china": ["china", "chinese", "mainland china", "中国", "大陆"],
    "japan": ["japan", "japanese", "yokohama", "日本", "横滨"],
    "united-states": ["united states", "u.s.", "us ", "usa", "america", "美国"],
    "latin-america": ["latin america", "拉美", "拉丁美洲"],
    "united-kingdom": ["united kingdom", "uk", "britain", "英国"],
}

REGION_SENSITIVE_EVENT_KINDS = {
    "legal_antitrust",
    "regional_regulation",
    "developer_program",
    "retail_store",
    "hardware_market",
}

REGION_WARNING_EXEMPT_FACETS = {
    "apple-product-price-increase",
    *APPLE_PRICE_SUBTOPIC_FACETS,
}

SUMMARY_LEVEL_EVENT_MERGE_FACETS = {
    "airdrop-vulnerability",
    "apple-arcade",
    "apple-creator-studio",
    "apple-music-top-artists",
    "apple-company-org-change",
    "apple-pay-rewards",
    "apple-product-data-leak",
    "apple-product-data-leak-enforcement",
    "apple-product-data-leak-specs",
    "apple-product-price-increase",
    "apple-refurbished-iphone",
    "apple-refurbished-ipad",
    "apple-refurbished-mac",
    "apple-refurbished-product",
    "apple-restricted-memory-supplier-approval",
    "apple-watch-redesign",
    *APPLE_PRICE_SUBTOPIC_FACETS,
    "apple-product-roadmap-list",
    "apple-wallet-digital-id",
    "bootrom-secure-rom-exploit",
    "brazil-app-store-policy",
    "epic-app-store-appeal",
    "find-my-location-sharing",
    "foldable-iphone-supply-chain",
    "iwork-apps-update",
    "iphone-air-successor",
    "iphone-color-mockup",
    "iphone-parts-factory-contamination",
    "system-performance-optimization",
    "uk-cma-app-store-payment-nfc",
}

SYSTEM_PERFORMANCE_MERGE_TOKENS = {
    "30",
    "40",
    "40+",
    "70",
    "80",
    "airdrop",
    "app",
    "faster",
    "launch",
    "load",
    "performance",
    "speed",
    "优化",
    "提速",
    "隔空投送",
}

def extract_regions(text: str) -> set[str]:
    lower = re.sub(r"\s+", " ", text.lower())
    regions: set[str] = set()
    for region, terms in REGION_TERMS.items():
        for term in terms:
            if term.endswith(" "):
                if term in lower:
                    regions.add(region)
                    break
            elif term_present(lower, term):
                regions.add(region)
                break
    if score_terms(lower, ["countries", "regions", "markets", "全球", "多国", "多个国家"]) > 0:
        regions.add("multi-region")
    return regions


APP_STORE_POLICY_TERMS = [
    "app store review guidelines",
    "review guidelines",
    "guideline",
    "guidelines",
    "rule",
    "rules",
    "low-quality",
    "low quality",
    "low-effort",
    "low effort",
    "spam",
    "spamming",
    "app review",
    "alternative app marketplace",
    "alternative app marketplaces",
    "alternative marketplace",
    "alternative marketplaces",
    "third-party payment",
    "third-party payments",
    "external link",
    "external links",
    "web distribution",
    "commission",
    "commissions",
    "cade",
    "developer program",
    "removal",
    "remove",
    "rejection",
    "reject",
    "submission",
    "submissions",
    "fraud",
    "fraudulent",
    "应用审核",
    "第三方应用商店",
    "替代应用市场",
    "第三方支付",
    "外链",
    "网页分发",
    "佣金",
    "巴西",
    "审核指南",
    "审核规则",
    "开发者指南",
    "低质量",
    "低价值",
    "垃圾应用",
    "开发者计划",
    "开发者账户",
    "移除",
    "拒绝",
    "提交",
    "欺诈",
]


def app_store_policy_score(text: str) -> int:
    if score_terms(text, ["app store", "应用商店"]) <= 0:
        return 0
    return score_terms(text, APP_STORE_POLICY_TERMS)


def is_brazil_app_store_policy_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["brazil", "brazilian", "cade", "巴西"]) > 0
        and score_terms(lower, ["ios", "iphone", "app", "apps", "developer", "developers", "应用", "开发者"]) > 0
        and score_terms(lower, ["apple", "苹果"]) > 0
        and score_terms(
            lower,
            [
                "alternative app marketplace",
                "alternative app marketplaces",
                "alternative marketplace",
                "alternative marketplaces",
                "third-party payment",
                "third-party payments",
                "web distribution",
                "external link",
                "第三方应用商店",
                "替代应用市场",
                "第三方支付",
                "网页分发",
                "外链",
            ],
        )
        > 0
    )


def is_uk_cma_app_store_payment_nfc_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["cma", "competition and markets authority", "英国竞争与市场管理局", "英国监管机构", "英国政府"]) > 0
        and score_terms(lower, ["apple", "苹果"]) > 0
        and score_terms(lower, ["app store", "应用商店", "ios", "iphone"]) > 0
        and score_terms(
            lower,
            [
                "app store rules",
                "app store rule",
                "app store payment",
                "app store payments",
                "loosen",
                "open up",
                "access to ios",
                "strategic market status",
                "sms",
                "copying more eu",
                "eu app store rules",
                "developers",
                "developer access",
                "off-platform payment",
                "outside the app store",
                "external payment",
                "third-party payment",
                "nfc",
                "near-field communication",
                "contactless",
                "wallet",
                "规则",
                "开放",
                "开发者",
                "战略市场地位",
                "平台外支付",
                "外部支付",
                "平台外",
                "引导",
                "nfc",
                "非接触式",
                "钱包",
            ],
        )
        > 0
    )


def is_epic_app_store_appeal_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["epic", "epic games", "埃pic", "斯威尼"]) > 0
        and score_terms(lower, ["apple", "app store", "苹果", "应用商店"]) > 0
        and score_terms(
            lower,
            [
                "supreme court",
                "appeal",
                "contempt",
                "anti-steering",
                "external link",
                "commission",
                "最高法院",
                "上诉",
                "藐视法庭",
                "反引导",
                "外链",
                "抽佣",
            ],
        )
        > 0
    )


def is_siri_ai_eu_dma_regulatory_meeting_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["apple", "tim cook", "cook", "苹果", "库克"]) > 0
        and score_terms(lower, ["siri ai", "siri", "apple intelligence", "ai tools", "新版 siri", "人工智能", "ai 工具"]) > 0
        and score_terms(
            lower,
            [
                "eu",
                "european commission",
                "henna virkkunen",
                "virkkunen",
                "digital markets act",
                "dma",
                "欧盟",
                "欧盟委员会",
                "维尔库宁",
                "数字市场法",
            ],
        )
        > 0
        and score_terms(
            lower,
            [
                "meeting",
                "virtual meeting",
                "talks",
                "conversation",
                "constructive",
                "regulator",
                "regulators",
                "compliance",
                "violating",
                "举行",
                "会谈",
                "沟通",
                "建设性",
                "监管",
                "违反",
                "推出",
            ],
        )
        > 0
    )


def is_apple_pay_rewards_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["apple pay"]) > 0
        and score_terms(lower, ["american express", "amex", "membership rewards", "points", "积分", "运通"]) > 0
        and score_terms(lower, ["redeem", "redemption", "checkout", "抵扣", "兑换", "结账"]) > 0
    )


def is_third_party_financial_service_with_apple_pay_support(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if is_epic_app_store_appeal_story(lower) or is_uk_cma_app_store_payment_nfc_story(lower):
        return False
    if score_terms(title_lower, ["apple wallet", "apple pay", "apple cash", "wallet app", "钱包 app", "钱包应用"]) > 0:
        return False
    if score_terms(lower, ["apple pay"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "supports apple pay",
            "support apple pay",
            "compatible with apple pay",
            "add to apple pay",
            "visa",
            "mastercard",
            "card",
            "cashback",
            "cash back",
            "yield",
            "interest",
            "fdic",
            "bank",
            "banking",
            "finance",
            "financial service",
            "金融服务",
            "银行卡",
            "金属卡",
            "返现",
            "年化",
            "活期",
            "利息",
            "银行",
            "支持 apple pay",
            "支持苹果支付",
        ],
    ) <= 0:
        return False
    return score_terms(
        title_lower,
        [
            "x money",
            "paypal",
            "venmo",
            "revolut",
            "cash app",
            "visa",
            "mastercard",
            "bank",
            "银行",
            "金融",
            "马斯克",
        ],
    ) > 0 or score_terms(lower, ["third-party", "第三方", "premium", "visa"]) > 0


def is_bootrom_secure_rom_exploit_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["bootrom", "secure-rom", "securerom", "usbliter8"]) > 0
        and score_terms(lower, ["a12", "a13", "iphone 11", "iphone xs", "iphone xr"]) > 0
        and score_terms(lower, ["vulnerability", "exploit", "unpatchable", "漏洞", "无法软件修复", "不可修复"]) > 0
    )


def is_find_my_location_sharing_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["find my", "find my app", "查找"]) > 0
        and score_terms(
            lower,
            [
                "hide location",
                "location sharing",
                "sharing duration",
                "custom sharing",
                "landscape",
                "隐藏位置",
                "隐藏共享位置",
                "位置共享",
                "共享时长",
                "横屏",
            ],
        )
        > 0
    )


def is_how_to_guide_without_new_apple_action(title: str, text: str) -> bool:
    title_lower = title.lower().strip()
    if not (title_lower.startswith("how to ") or title_lower.startswith("here's how ")):
        return False
    return not (
        has_apple_first_party_release_context(text)
        or is_apple_developer_tool_story(text)
        or app_store_policy_score(text) > 0
    )


def is_apple_company_org_change_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    org_structure_score = score_terms(
        lower,
        [
            "apple's design team",
            "apple design team",
            "apple's product design",
            "product design organization",
            "leadership",
            "management",
            "organization",
            "organisational",
            "organizational",
            "design department",
            "苹果设计部门",
            "苹果设计团队",
            "设计部门",
            "设计团队",
            "管理层",
            "组织",
            "架构",
            "产品决策",
        ],
    )
    person_role_score = score_terms(
        lower,
        [
            "apple executive",
            "apple exec",
            "top executive",
            "another executive",
            "departing executive",
            "senior executive",
            "apple's svp",
            "apple svp",
            "senior vice president",
            "vice president",
            "苹果高管",
            "苹果高级副总裁",
            "高级副总裁",
            "高管",
        ],
    )
    movement_score = score_terms(
        lower,
        [
            "loses",
            "lost",
            "leave",
            "leaves",
            "leaving",
            "depart",
            "departs",
            "departed",
            "departing",
            "join",
            "joins",
            "joined",
            "move to",
            "moves to",
            "moved to",
            "poached",
            "hired",
            "recruited",
            "to openai",
            "离职",
            "离开",
            "转投",
            "加入",
            "挖角",
            "聘请",
        ],
    )
    structural_change_score = score_terms(
        lower,
        [
            "change",
            "changes",
            "changed",
            "rebalance",
            "rebuild",
            "restore",
            "lost influence",
            "decline",
            "declined",
            "taking over",
            "take over",
            "successor",
            "succeed",
            "replace",
            "调整",
            "改变",
            "变化",
            "重组",
            "下滑",
            "弱化",
            "提升",
            "接任",
            "继任",
            "主导",
            "权重",
            "地位",
        ],
    )
    factual_change_score = score_terms(
        lower,
        [
            "report",
            "reports",
            "reported",
            "according to",
            "says",
            "said",
            "loses",
            "lost",
            "leave",
            "leaves",
            "leaving",
            "depart",
            "departs",
            "departed",
            "join",
            "joins",
            "joined",
            "hire",
            "hires",
            "hired",
            "recruit",
            "recruits",
            "recruited",
            "move to",
            "moves to",
            "moved to",
            "take over",
            "taken over",
            "taking over",
            "successor",
            "succeed",
            "replace",
            "incoming ceo",
            "rebalance",
            "报道称",
            "报道",
            "消息称",
            "古尔曼",
            "彭博社",
            "透露",
            "指出",
            "称",
            "梳理",
            "离职",
            "离开",
            "转投",
            "加入",
            "接任",
            "继任",
            "任命",
            "聘请",
            "重组",
        ],
    )
    if person_role_score > 0 and movement_score > 0:
        return True
    return org_structure_score > 0 and structural_change_score > 0 and factual_change_score > 0


def is_apple_executive_company_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    role_score = score_terms(
        lower,
        [
            "apple's svp",
            "apple’s svp",
            "apple svp",
            "apple's senior vice president",
            "apple’s senior vice president",
            "apple senior vice president",
            "apple executive",
            "apple exec",
            "apple services chief",
            "apple tv chief",
            "apple music chief",
            "svp of services",
            "senior vice president of services",
            "苹果高管",
            "苹果服务主管",
            "苹果电视主管",
            "苹果音乐主管",
            "苹果高级副总裁",
        ],
    )
    if role_score <= 0:
        return False
    company_or_service_score = score_terms(
        lower,
        [
            "services",
            "service",
            "apple tv",
            "apple tv+",
            "apple music",
            "app store",
            "icloud",
            "health",
            "streaming",
            "platform",
            "leadership",
            "company",
            "服务",
            "苹果电视",
            "苹果音乐",
            "应用商店",
            "平台",
            "领导",
            "公司",
        ],
    )
    action_score = score_terms(
        lower,
        [
            "award",
            "awarded",
            "honor",
            "honored",
            "honour",
            "honoured",
            "recognize",
            "recognized",
            "recognised",
            "named",
            "person of the year",
            "accepts",
            "received",
            "speaking",
            "interview",
            "said",
            "comment",
            "comments",
            "获奖",
            "表彰",
            "认可",
            "评为",
            "年度人物",
            "接受",
            "发表",
            "采访",
            "表示",
        ],
    )
    return company_or_service_score > 0 and action_score > 0


def is_apple_strategic_transaction_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    transaction_score = score_terms(
        lower,
        [
            "merger",
            "merge",
            "merging",
            "acquisition",
            "acquire",
            "acquires",
            "acquired",
            "acquiring",
            "buyout",
            "takeover",
            "purchases",
            "purchasing",
            "strategic deal",
            "transaction",
            "合并",
            "并购",
            "收购",
            "交易",
        ],
    )
    if transaction_score <= 0:
        return False
    direct_acquisition = (
        re.search(r"\bapple\b[^.!?。！？]{0,64}\b(?:acquires?|acquired|acquiring|buys?|bought|purchase[sd]?|purchasing)\b", lower)
        is not None
        or re.search(r"\b(?:acquired|acquiring|bought|purchased|purchasing)\b[^.!?。！？]{0,48}\bby\s+apple\b", lower)
        is not None
        or re.search(r"苹果[^。！？.!?]{0,48}(?:收购|买下|购入)", lower) is not None
        or re.search(r"(?:被|由)苹果[^。！？.!?]{0,24}(?:收购|买下|购入)", lower) is not None
    )
    if direct_acquisition:
        return True
    discussion_score = score_terms(
        lower,
        [
            "conversation",
            "conversations",
            "talk",
            "talks",
            "talked",
            "discuss",
            "discussed",
            "discussion",
            "interest",
            "interested",
            "profile",
            "interview",
            "said",
            "says",
            "revealed",
            "沟通",
            "讨论",
            "谈判",
            "兴趣",
            "采访",
            "表示",
            "透露",
            "推进",
        ],
    )
    counterparty_score = score_terms(
        lower,
        [
            "company",
            "companies",
            "ceo",
            "executive",
            "disney",
            "twitter",
            "x corp",
            "公司",
            "企业",
            "首席执行官",
            "高管",
            "迪士尼",
            "推特",
        ],
    )
    direct_pairing = (
        re.search(r"\bapple\b[^.!?。！？]{0,48}\b(?:and|with)\b[^.!?。！？]{0,48}", lower)
        is not None
        or re.search(r"[^。！？.!?]{0,32}(?:与|和|同)苹果[^。！？.!?]{0,48}(?:合并|并购|收购|交易|沟通|讨论)", lower)
        is not None
        or re.search(r"苹果[^。！？.!?]{0,48}(?:与|和|同)[^。！？.!?]{0,48}(?:合并|并购|收购|交易|沟通|讨论)", lower)
        is not None
    )
    return discussion_score > 0 and (counterparty_score > 0 or direct_pairing)


def strategic_transaction_counterparty_facets(text: str) -> set[str]:
    lower = text.lower()
    facets: set[str] = set()
    counterparties = {
        "disney": ["disney", "迪士尼"],
        "twitter": ["twitter", "x corp", "推特"],
        "ai-startup": ["ai startup", "ai company", "人工智能初创", "ai 初创"],
        "rabbit-play": ["rabbit 3 times", "rabbit 3 ties", "play", "swift development tool", "app design tool"],
    }
    for name, terms in counterparties.items():
        if score_terms(lower, terms) > 0:
            facets.add(f"transaction-counterparty-{name}")
    return facets


def is_former_apple_staff_background_story(text: str) -> bool:
    lower = text.lower()
    former_staff_score = score_terms(
        lower,
        [
            "former apple",
            "ex-apple",
            "former vision pro",
            "前苹果",
            "前 apple",
            "苹果前员工",
            "苹果、奥迪前员工",
            "前苹果员工",
            "曾在苹果",
        ],
    )
    if former_staff_score <= 0 and not re.search(r"(?:苹果|apple)[^。！？.!?]{0,16}前员工|前[^。！？.!?]{0,12}(?:苹果|apple)[^。！？.!?]{0,8}员工", lower):
        return False
    if is_apple_company_org_change_story(lower):
        return False
    if has_apple_first_party_release_context(lower) or is_apple_developer_tool_story(lower):
        return False
    return score_terms(
        lower,
        [
            "midjourney",
            "startup",
            "company",
            "medical",
            "ultrasound",
            "scanner",
            "electric vehicle",
            "light electric vehicle",
            "vehicle",
            "ev",
            "automaker",
            "audi",
            "amble",
            "公司",
            "医疗",
            "超声波",
            "扫描仪",
            "电动车",
            "轻型电动车",
            "汽车",
            "车型",
            "奥迪",
            "月球车",
        ],
    ) > 0


def is_legacy_apple_protocol_third_party_removal(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["appletalk"]) > 0
        and score_terms(lower, ["linux", "kernel", "内核"]) > 0
        and score_terms(lower, ["remove", "removal", "removed", "移除", "删除"]) > 0
    )


def is_third_party_xr_smart_glasses_context_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(
        lower,
        [
            "android xr",
            "xreal",
            "snap specs",
            "spectacles",
            "meta orion",
            "viture",
            "xr glasses",
            "ar glasses",
            "smart glasses",
            "reality elite",
            "智能眼镜",
            "ar 眼镜",
            "xr 眼镜",
        ],
    ) <= 0:
        return False
    if has_apple_first_party_release_context(lower) or score_terms(
        lower,
        [
            "apple smart glasses",
            "apple glasses",
            "apple product roadmap",
            "apple's product roadmap",
            "apple’s product roadmap",
            "apple vision products",
            "vision products roadmap",
            "vision pro series",
            "apple is developing",
            "apple plans",
            "vision pro 2",
            "vision pro successor",
            "苹果智能眼镜",
            "苹果眼镜",
            "苹果产品路线图",
            "vision 产品路线图",
            "苹果计划",
            "苹果正在",
            "vision pro 后续",
        ],
    ) > 0:
        return False
    return effective_apple_term_score(lower) > 0 or score_terms(
        lower,
        ["iphone moment", "iphone 时刻", "vision pro", "苹果", "iphone"],
    ) > 0


def is_apple_music_top_artists_chart_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple music", "苹果音乐"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "top 20",
            "top twenty",
            "most-streamed",
            "most streamed",
            "all-time artists",
            "chart data",
            "drake",
            "taylor swift",
            "future",
            "最常被收听",
            "串流收听",
            "前二十名",
            "艺术家",
            "史上",
        ],
    ) > 0


def is_apple_tv_hardware_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple tv", "苹果电视"]) <= 0:
        return False
    if score_terms(lower, ["apple tv+", "apple tv plus", "苹果 tv+", "苹果原创", "apple original"]) > 0:
        return False
    if score_terms(
        lower,
        [
            "movie",
            "film",
            "season",
            "episode",
            "series",
            "show",
            "streaming",
            "chief",
            "cue",
            "cannes",
            "剧集",
            "电影",
            "流媒体",
            "高管",
        ],
    ) > 0 and score_terms(lower, ["4k", "hardware", "device", "set-top", "机顶盒", "硬件", "设备"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "apple tv 4k",
            "new apple tv",
            "next-generation apple tv",
            "set-top box",
            "apple tv hardware",
            "苹果 tv 4k",
            "苹果电视 4k",
            "新款 apple tv",
            "新款苹果电视",
            "机顶盒",
        ],
    ) > 0


def is_apple_hardware_product_launch_story(text: str, title: str = "") -> bool:
    lower = text.lower()
    title_lower = (title or text[:180]).lower()
    if is_foldable_iphone_successor_roadmap_story(text):
        return True
    if effective_apple_term_score(lower) <= 0:
        return False
    if is_apple_os_support_compatibility_story(text):
        return False
    if is_apple_tv_hardware_story(text):
        return True
    if score_terms(
        title_lower,
        [
            "android",
            "huawei",
            "xiaomi",
            "samsung",
            "xreal",
            "snap",
            "smart glasses",
            "xr",
            "安卓",
            "华为",
            "小米",
            "三星",
            "智能眼镜",
            "硬刚苹果",
        ],
    ) > 0:
        return False
    product_score = score_terms(
        title_lower,
        [
            "iphone",
            "ipad",
            "macbook",
            "mac",
            "airpods",
            "apple watch",
            "watch ultra",
            "vision pro",
            "homepod",
            "苹果手表",
            "苹果手机",
            "苹果平板",
        ],
    )
    if product_score <= 0:
        return False
    action_score = score_terms(
        lower,
        [
            "launch",
            "launches",
            "launching",
            "coming",
            "debut",
            "arrive",
            "release",
            "rumor",
            "rumors",
            "reported",
            "reportedly",
            "new model",
            "next-generation",
            "this fall",
            "later this year",
            "unveil",
            "推出",
            "发布",
            "登场",
            "亮相",
            "传闻",
            "爆料",
            "消息称",
            "今年晚些时候",
            "下半年",
            "秋季",
            "新机",
            "新表",
            "新品",
        ],
    )
    hardware_detail_score = score_terms(
        lower,
        [
            "design",
            "redesign",
            "thinner",
            "camera",
            "display",
            "screen",
            "panel",
            "oled",
            "chip",
            "processor",
            "modem",
            "sensor",
            "sensors",
            "battery",
            "touch id",
            "face id",
            "camera control",
            "memory",
            "ram",
            "storage",
            "case",
            "housing",
            "外观",
            "设计",
            "更薄",
            "摄像头",
            "相机",
            "屏幕",
            "面板",
            "芯片",
            "处理器",
            "调制解调器",
            "传感器",
            "健康传感器",
            "续航",
            "电池",
            "内存",
            "存储",
            "机身",
            "表壳",
        ],
    )
    if action_score <= 0 or hardware_detail_score <= 0:
        return False
    if score_terms(lower, ["ios", "ipados", "macos", "watchos", "tvos", "visionos"]) > 0 and score_terms(
        lower,
        [
            "beta",
            "developer beta",
            "software update",
            "firmware",
            "feature",
            "app",
            "应用",
            "固件",
            "测试版",
            "系统更新",
        ],
    ) > 0:
        return False
    return True


def is_direct_apple_hardware_roadmap_story(text: str, title: str = "") -> bool:
    lower = text.lower()
    title_lower = (title or text[:180]).lower()
    actor_context = f"{title_lower} {lower[:700]}"
    if is_foldable_iphone_successor_roadmap_story(text):
        return True
    if effective_apple_term_score(lower) <= 0:
        return False
    if is_apple_os_support_compatibility_story(text):
        return False
    if is_primary_apple_chip_roadmap_title(title or text[:180]):
        return True
    apple_actor_score = score_terms(
        actor_context,
        [
            "apple is developing",
            "apple is working",
            "apple has",
            "apple plans",
            "apple to",
            "apple will",
            "apple could",
            "apple may",
            "apple reportedly",
            "apple rumored",
            "apple is rumored",
            "苹果正开发",
            "苹果正在开发",
            "苹果开发",
            "苹果计划",
            "苹果将",
            "苹果有望",
            "消息称苹果",
            "传闻苹果",
        ],
    )
    if apple_actor_score <= 0:
        return False
    product_score = score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "mac studio",
            "airpods",
            "apple watch",
            "vision pro",
            "homepod",
            "apple tv",
            "iring",
            "smart ring",
            "ring wearable",
            "苹果手表",
            "苹果电视",
            "智能戒指",
            "戒指",
        ],
    )
    roadmap_score = score_terms(
        lower,
        [
            "develop",
            "developing",
            "development",
            "working on",
            "in the works",
            "roadmap",
            "timeline",
            "planned",
            "plans",
            "expected",
            "reportedly",
            "rumor",
            "rumors",
            "leaker",
            "testing",
            "测试",
            "开发",
            "研发",
            "计划",
            "路线",
            "爆料",
            "消息称",
            "传闻",
        ],
    )
    return product_score > 0 and roadmap_score > 0


def is_non_apple_vendor_response_to_apple_product_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if effective_apple_term_score(text) <= 0:
        return False
    if title_lower.startswith("apple ") or title_lower.startswith("苹果"):
        return False
    if score_terms(
        title_lower,
        [
            "apple",
            "apple ",
            "iphone",
            "ipad",
            "mac ",
            "macbook",
            "airpods",
            "vision pro",
            "apple watch",
            "苹果",
        ],
    ) > 0:
        return False
    non_apple_subject_score = score_terms(
        lower,
        [
            "pc vendor",
            "pc vendors",
            "pc maker",
            "pc makers",
            "oem",
            "amd",
            "intel",
            "microsoft",
            "surface",
            "windows pc",
            "wildcat lake",
            "ryzen",
            "snapdragon",
            "厂商",
            "供应商",
            "pc厂商",
            "pc 厂商",
            "英特尔",
            "微软",
            "锐龙",
            "骁龙",
        ],
    )
    response_score = score_terms(
        lower,
        [
            "respond to",
            "response to",
            "compete with",
            "rival",
            "against",
            "versus",
            "vs",
            "rebrand",
            "old chips",
            "older chips",
            "rename",
            "面对苹果",
            "迎战",
            "应对",
            "对比",
            "直接对比",
            "换名",
            "旧芯片",
            "重新包装",
            "套娃",
        ],
    )
    apple_product_context = score_terms(
        lower,
        [
            "macbook",
            "macbook neo",
            "iphone",
            "ipad",
            "apple watch",
            "苹果推出",
            "苹果产品",
        ],
    )
    return non_apple_subject_score > 0 and response_score > 0 and apple_product_context > 0


def has_direct_apple_subject_anchor(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    lead = f"{title_lower} {lower[:700]}"
    if effective_apple_term_score(title_lower) > 0 and score_terms(
        title_lower,
        [
            "apple",
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "airpods",
            "apple watch",
            "vision pro",
            "homepod",
            "apple tv",
            "ios",
            "ipados",
            "macos",
            "watchos",
            "visionos",
            "苹果",
        ],
    ) > 0:
        return True
    return score_terms(
        lead,
        [
            "apple asks",
            "apple asked",
            "apple requests",
            "apple requested",
            "apple will",
            "apple is",
            "apple has",
            "apple supplier",
            "apple's supplier",
            "iphone factory",
            "iphone parts",
            "iphone component",
            "iphone board",
            "iphone display",
            "macbook",
            "ipad",
            "airpods",
            "apple watch",
            "vision pro",
            "apple tv",
            "ios",
            "ipados",
            "macos",
            "watchos",
            "visionos",
            "苹果请求",
            "苹果申请",
            "苹果供应商",
            "苹果在印度的主要供应商",
            "苹果主要供应商",
            "iphone 工厂",
            "iphone 零件",
            "iphone 电路板",
            "iphone 主板",
            "iphone 屏幕",
            "苹果公司",
        ],
    ) > 0


def is_third_party_app_usage_on_apple_platform_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    lead = f"{title_lower} {lower[:1200]}"
    third_party_app_score = score_terms(
        title_lower,
        [
            "microsoft edge",
            "edge browser",
            "edge",
            "chrome",
            "firefox",
            "brave",
            "browser",
            "browsers",
            "微软 edge",
            "edge 浏览器",
            "微软",
            "浏览器",
        ],
    )
    apple_platform_score = score_terms(
        lead,
        [
            "mac",
            "mac users",
            "mac user",
            "macos",
            "iphone",
            "ipad",
            "apple device",
            "apple devices",
            "苹果 mac",
            "mac 用户",
            "mac 电脑",
            "苹果用户",
            "苹果设备",
            "苹果电脑",
        ],
    )
    usage_score = score_terms(
        lead,
        [
            "user",
            "users",
            "using",
            "use",
            "download",
            "performance",
            "faster",
            "memory",
            "compatible",
            "compatibility",
            "recommend",
            "preference",
            "用户",
            "使用",
            "力挺",
            "吐槽",
            "辩护",
            "更快",
            "省内存",
            "内存占用",
            "兼容",
            "体验",
            "推荐",
        ],
    )
    apple_action_score = score_terms(
        lead,
        [
            "apple announced",
            "apple released",
            "apple allowed",
            "apple requires",
            "apple changed",
            "default browser",
            "browser engine",
            "webkit",
            "app store rule",
            "platform policy",
            "苹果宣布",
            "苹果发布",
            "苹果允许",
            "苹果要求",
            "苹果调整",
            "默认浏览器",
            "浏览器引擎",
            "应用商店规则",
            "平台政策",
        ],
    )
    return third_party_app_score > 0 and apple_platform_score > 0 and usage_score > 0 and apple_action_score <= 0


def is_non_apple_primary_subject_with_incidental_apple_context(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if effective_apple_term_score(f"{title} {text}") <= 0:
        return False
    if is_third_party_app_usage_on_apple_platform_story(title, text):
        return True
    non_apple_primary_score = score_terms(
        title_lower,
        [
            "qualcomm",
            "snapdragon",
            "xiaomi",
            "android",
            "samsung",
            "huawei",
            "lenovo",
            "legion",
            "tata motors",
            "tata car",
            "li auto",
            "ideal auto",
            "jeep",
            "dongfeng",
            "electric vehicle",
            "light electric vehicle",
            "automaker",
            "plex",
            "supercomputer",
            "nvidia",
            "amd",
            "mediatek",
            "dimensity",
            "oppo",
            "vivo",
            "honor",
            "google",
            "microsoft",
            "meta",
            "高通",
            "骁龙",
            "小米",
            "安卓",
            "三星",
            "华为",
            "联想",
            "拯救者",
            "塔塔汽车",
            "理想汽车",
            "理想 i",
            "吉普",
            "东风",
            "电动汽车",
            "轻型电动车",
            "电动车",
            "汽车",
            "车型",
            "suv",
            "超算",
            "超级计算机",
            "英伟达",
            "联发科",
            "天玑",
            "荣耀",
            "微软",
        ],
    )
    if non_apple_primary_score <= 0:
        return False
    third_party_vehicle_with_platform_context = (
        score_terms(
            title_lower,
            [
                "li auto",
                "ideal auto",
                "jeep",
                "dongfeng",
                "electric vehicle",
                "vehicle",
                "automaker",
                "理想汽车",
                "吉普",
                "东风",
                "电动汽车",
                "电动车",
                "汽车",
                "车型",
                "suv",
            ],
        )
        > 0
        and score_terms(lower, ["carplay", "apple carplay", "spotify", "本地化应用"]) > 0
    )
    if third_party_vehicle_with_platform_context:
        return True
    if effective_apple_term_score(title) <= 0 and not loose_apple_product_marker(title):
        return True
    if has_direct_apple_subject_anchor(title, text):
        return False
    direct_apple_action_score = score_terms(
        lower[:900],
        [
            "apple asks",
            "apple requested",
            "apple announced",
            "apple released",
            "apple supplier",
            "apple's supplier",
            "苹果请求",
            "苹果申请",
            "苹果宣布",
            "苹果发布",
            "苹果推出",
            "苹果供应商",
            "苹果主要供应商",
        ],
    )
    if direct_apple_action_score > 0:
        return False
    return True


def is_competitor_launch_against_apple_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    competitor_score = score_terms(
        title_lower,
        [
            "huawei",
            "mate",
            "samsung",
            "galaxy",
            "xiaomi",
            "vivo",
            "oppo",
            "honor",
            "android",
            "华为",
            "三星",
            "小米",
            "vivo",
            "oppo",
            "荣耀",
            "安卓",
        ],
    )
    if competitor_score <= 0:
        return False
    if score_terms(title_lower, ["iphone", "apple", "苹果"]) <= 0:
        return False
    comparison_score = score_terms(
        f"{title_lower} {lower[:500]}",
        [
            "versus",
            "vs",
            "compete",
            "competes",
            "rival",
            "challenge",
            "battle",
            "showdown",
            "迎战",
            "对决",
            "硬刚",
            "对标",
            "挑战",
            "巅峰对决",
        ],
    )
    direct_apple_action_score = score_terms(
        lower[:700],
        [
            "apple announced",
            "apple released",
            "apple supplier",
            "apple will use",
            "苹果宣布",
            "苹果发布",
            "苹果推出",
            "苹果供应商",
            "苹果将采用",
        ],
    )
    return comparison_score > 0 and direct_apple_action_score <= 0


def is_service_content_story(text: str) -> bool:
    lower = text.lower()
    if is_apple_tv_hardware_story(text):
        return False
    if score_terms(lower, ["apple music", "apple arcade", "classical", "苹果音乐"]) > 0:
        return True
    apple_tv_score = score_terms(lower, ["apple tv", "apple tv+", "苹果电视"])
    if apple_tv_score <= 0:
        return False
    return (
        score_terms(
            lower,
            [
                "stream",
                "streaming",
                "movie",
                "film",
                "original film",
                "season",
                "episode",
                "comedy",
                "drama",
                "thriller",
                "premiere",
                "debut",
                "grand prix",
                "formula 1",
                "f1",
                "剧集",
                "电影",
                "首播",
                "大奖赛",
                "直播",
            ],
        )
        > 0
    )


def is_airdrop_vulnerability_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["airdrop", "隔空投送"]) > 0
        and score_terms(
            lower,
            [
                "vulnerability",
                "vulnerabilities",
                "flaw",
                "flaws",
                "security",
                "crash",
                "denial of service",
                "dos",
                "cispa",
                "漏洞",
                "安全",
                "崩溃",
                "拒绝服务",
            ],
        )
        > 0
    )


def is_apple_creator_studio_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["creator studio", "apple creator studio", "创作坊"]) > 0
        and score_terms(
            lower,
            [
                "apple",
                "final cut",
                "pixelmator",
                "logic pro",
                "motion",
                "compressor",
                "final cut camera",
                "苹果",
                "final cut",
                "pixelmator",
                "logic pro",
            ],
        )
        > 0
    )


def is_iwork_apps_update_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["pages", "keynote", "numbers", "page 文稿", "keynote 讲演", "numbers 表格"]) >= 2
        and score_terms(lower, ["update", "updates", "version", "15.3", "features", "升至", "更新", "版本", "功能"]) > 0
    )


def is_apple_watch_redesign_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["apple watch"]) > 0
        and score_terms(
            lower,
            [
                "redesign",
                "overhaul",
                "new design",
                "band attachment",
                "band system",
                "watch x",
                "major design",
                "改款",
                "重新设计",
                "重大改版",
                "表带",
                "连接方式",
            ],
        )
        > 0
    )


def is_carplay_platform_feature_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["carplay"]) <= 0:
        return False
    platform_context_score = score_terms(
        lower,
        [
            "ios",
            "ios update",
            "ios release",
            "wwdc",
            "developer beta",
            "public beta",
            "apple unveiled",
            "apple introduced",
            "apple added",
            "apple is allowing",
            "苹果 ios",
            "苹果推出",
            "苹果新增",
            "开发者测试版",
            "公测版",
        ],
    )
    feature_action_score = score_terms(
        lower,
        OS_FEATURE_ACTION_TERMS
        + STRONG_NEWS_ACTION_TERMS
        + [
            "feature",
            "features",
            "enhancement",
            "enhancements",
            "interface",
            "siri",
            "mini player",
            "conversation mode",
            "airplay",
            "route sharing",
            "media app upgrades",
            "功能",
            "升级",
            "界面",
            "路线共享",
            "导航",
        ],
    )
    third_party_primary_score = score_terms(
        lower,
        [
            "spotify",
            "google maps",
            "waze",
            "third-party app",
            "third party app",
            "car maker",
            "automaker",
            "车企",
            "第三方应用",
        ],
    )
    apple_platform_score = score_terms(lower, ["apple", "苹果", "siri", "apple music", "apple tv", "podcasts"])
    return (
        platform_context_score > 0
        and feature_action_score > 0
        and (apple_platform_score > 0 or score_terms(lower, ["ios"]) > 0)
        and not (
            third_party_primary_score > 0
            and score_terms(lower, ["ios", "apple introduced", "apple added", "苹果新增"]) == 0
        )
    )


def os_feature_component_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    facets: set[str] = set()
    if (
        score_terms(
            lower,
            [
                "performance optimization",
                "performance optimizations",
                "faster",
                "speed up",
                "speed improvements",
                "app launch",
                "launch faster",
                "load faster",
                "airdrop transfers",
                "底层优化",
                "性能优化",
                "提速",
                "启动提速",
                "加载提速",
                "隔空投送",
            ],
        )
        > 0
        and score_terms(lower, ["ios", "ipados", "macos", "watchos", "visionos", "iphone", "ipad", "mac"]) > 0
        and score_terms(lower, ["up to", "ways", "percent", "%", "30%", "70%", "80%", "40+", "40 多", "多项", "最高"]) > 0
    ):
        facets.add("system-performance-optimization")
    if (
        score_terms(lower, ["weather app", "weather", "天气应用", "天气"]) > 0
        and score_terms(lower, ["forecast", "precipitation", "wind", "highlights", "hourly", "10-day", "降水", "风力", "亮点", "小时", "10 天"]) > 0
    ):
        facets.add("weather-app-forecast")
    if (
        score_terms(lower, ["keyboard", "input method", "typing", "chinese input", "language support", "输入法", "键盘", "中文输入", "拼音", "候选词", "标点", "生僻字"]) > 0
        and score_terms(lower, ["ios", "ipados", "iphone", "ipad", "system", "系统"]) > 0
    ):
        facets.add("keyboard-input-method")
    if (
        score_terms(lower, ["messages app", "messages", "imessage", "信息应用", "信息 app", "信息"]) > 0
        and score_terms(lower, ["drawing", "markup", "sketch", "annotate", "绘图", "标注", "涂鸦"]) > 0
    ):
        facets.add("messages-drawing-markup")
    if (
        score_terms(lower, ["safari", "safari browser", "浏览器"]) > 0
        and score_terms(lower, ["tab", "tabs", "extension", "extensions", "notify me", "apple intelligence", "ai", "标签页", "扩展", "网页监控", "自动整理"]) > 0
    ):
        facets.add("safari-browser-features")
    if (
        score_terms(lower, ["visionos", "vision pro"]) > 0
        and score_terms(lower, ["m5 vision pro", "m5 款 vision pro", "m5 vision pro 头显"]) > 0
        and score_terms(
            lower,
            [
                "afm 3 core advanced",
                "advanced on-device model",
                "local ai model",
                "on-device model",
                "exclusive to the m5",
                "m5 model",
                "miss out",
                "siri ai voice customization",
                "two features",
                "two unique",
                "voice customization",
                "本地 ai 模型",
                "语音定制",
                "独占",
            ],
        )
        > 0
    ):
        facets.add("visionos-m5-ai-features")
    if (
        score_terms(lower, ["watchos", "apple watch"]) > 0
        and score_terms(lower, ["siri app", "find my app", "find devices", "find items", "find people", "siri 应用", "查找应用"]) > 0
    ):
        facets.add("watchos-siri-findmy-apps")
    if (
        score_terms(lower, ["carplay"]) > 0
        and score_terms(lower, ["route sharing", "route", "navigation", "路线共享", "路线", "导航"]) > 0
    ):
        facets.add("carplay-route-sharing")
    if is_carplay_platform_feature_story(lower):
        facets.add("carplay-platform-feature")
    if score_terms(
        lower,
        [
            "recovery mode",
            "recovery repair mode",
            "recovery 修复模式",
            "恢复模式",
            "恢复助理",
            "diagnostic",
            "diagnostics",
            "诊断",
            "抹掉所有内容",
            "nearby device recovery",
            "附近设备恢复",
        ],
    ) > 0:
        facets.add("device-recovery-mode")
    if (
        score_terms(lower, ["restore image", "recovery image", "ipsw", "image download", "download link", "镜像下载", "恢复镜像", "下载链接"]) > 0
        and score_terms(lower, ["ios", "ipados", "iphone", "ipad"]) > 0
    ):
        facets.add("restore-image-availability")
    if (
        score_terms(lower, ["apple notes", "notes app", "notes", "备忘录", "笔记"]) > 0
        and score_terms(lower, ["divider", "dividers", "markdown", "siri", "image playground", "分隔线", "图像生成"]) > 0
    ):
        facets.add("notes-app-update")
    if (
        score_terms(lower, ["shortcuts", "shortcut builder", "shortcut", "快捷指令"]) > 0
        and score_terms(lower, ["workflow", "automation", "plain english", "natural language", "apple intelligence", "工作流", "自动化", "自然语言", "生成"]) > 0
    ):
        facets.add("shortcuts-automation-builder")
    if (
        score_terms(lower, ["livecommunicationkit", "callkit", "voip", "全屏来电", "来电显示", "默认通话应用"]) > 0
        or (
            score_terms(lower, ["锁屏", "lock screen", "locked screen"]) > 0
            and score_terms(lower, ["call", "calling", "phone", "voip", "来电", "通话"]) > 0
        )
    ):
        facets.add("communication-framework-callkit")
    if (
        score_terms(lower, ["facetime"]) > 0
        and score_terms(lower, ["dual camera", "dual capture", "front and rear", "前后摄像头", "双摄像头", "双摄", "翻转"]) > 0
    ):
        facets.add("facetime-dual-camera")
    if (
        score_terms(lower, ["afp", "apple filing protocol", "time capsule", "time machine", "airport disk"]) > 0
        and score_terms(lower, ["smb", "smbv2", "smbv3", "network backup", "网络备份", "备份", "协议"]) > 0
    ):
        facets.add("time-machine-afp-smb")
    if (
        score_terms(lower, ["asahi linux", "startup disk", "startup volume", "bootable volume", "boot volume", "启动盘", "启动卷", "引导卷", "磁盘启动"]) > 0
        and score_terms(lower, ["partition", "volume", "detect", "detection", "分区", "检测", "启动选择器"]) > 0
    ):
        facets.add("boot-volume-detection")
    if (
        score_terms(lower, ["rosetta", "rosetta 2", "intel app", "intel apps", "intel-built", "intel-compiled", "英特尔架构应用"]) > 0
        and score_terms(lower, ["support", "last", "final", "remove", "removes", "end", "支持", "最后", "停用", "取消"]) > 0
    ):
        facets.add("rosetta-intel-app-support")
    if (
        score_terms(lower, ["hardware fault", "fault rate", "failure rate", "reliable", "reliability", "返修率", "硬件故障", "可靠性"]) > 0
        and score_terms(lower, ["apple silicon", "macbook", "intel mac", "苹果芯片", "英特尔机型"]) > 0
    ):
        facets.add("mac-hardware-reliability")
    return facets


def is_vision_pro_spatial_experience_story(text: str) -> bool:
    lower = text.lower()
    return (
        score_terms(lower, ["vision pro"]) > 0
        and score_terms(
            lower,
            [
                "attraction",
                "disney",
                "epcot",
                "enterprise",
                "immersive",
                "ride",
                "simulation",
                "soarin",
                "spatial",
                "theme park",
                "training",
                "主题乐园",
                "乐园",
                "迪士尼",
                "飞行项目",
                "空间计算",
                "沉浸",
                "沉浸式",
                "仿真",
                "培训",
            ],
        )
        > 0
    )


def is_iphone_parts_factory_contamination_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone", "apple", "苹果"]) <= 0:
        return False
    factory_score = score_terms(
        lower,
        [
            "factory",
            "plant",
            "supplier",
            "parts",
            "tata",
            "hosur",
            "tamil nadu",
            "工厂",
            "供应商",
            "零部件",
            "塔塔",
            "霍苏尔",
        ],
    )
    contamination_score = score_terms(
        lower,
        [
            "contamination",
            "contaminated",
            "pollution",
            "wastewater",
            "water",
            "tds",
            "probe",
            "investigation",
            "污染",
            "废水",
            "井水",
            "超标",
            "调查",
        ],
    )
    return factory_score > 0 and contamination_score > 0


def is_apple_product_data_leak_story(text: str, title: str = "") -> bool:
    lower = text.lower()
    title_lower = (title or text[:200]).lower()
    if effective_apple_term_score(text) <= 0 and score_terms(
        lower,
        ["iphone", "ipad", "mac", "macbook", "a20", "c2 modem", "苹果"],
    ) <= 0:
        return False
    product_score = score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "apple product",
            "a20",
            "c2 modem",
            "苹果",
            "a20 pro",
            "c2 调制解调器",
        ],
    )
    leak_score = score_terms(
        lower,
        [
            "stolen",
            "steal",
            "breach",
            "hacked",
            "hackers",
            "dark web",
            "schematics",
            "data sheets",
            "logic board",
            "files",
            "source files",
            "被黑",
            "黑客",
            "泄露",
            "流入暗网",
            "暗网",
            "机密文件",
            "资料",
            "原理图",
            "数据表",
        ],
    )
    supplier_score = score_terms(
        lower,
        [
            "supplier",
            "factory",
            "facility",
            "plant",
            "manufacturing",
            "tata",
            "foxconn",
            "pegatron",
            "wistron",
            "代工厂",
            "供应商",
            "工厂",
            "塔塔",
            "富士康",
            "和硕",
            "纬创",
        ],
    )
    sensitive_hardware_score = score_terms(
        lower,
        [
            "schematics",
            "data sheets",
            "logic board",
            "board designs",
            "modem files",
            "c2 modem",
            "原理图",
            "逻辑板",
            "主板",
            "数据表",
            "调制解调器",
            "机密文件",
        ],
    )
    title_leak_subject = product_score > 0 and score_terms(
        title_lower,
        [
            "stolen",
            "hacked",
            "schematics",
            "data sheet",
            "data sheets",
            "files",
            "被黑",
            "资料",
            "机密文件",
            "流入暗网",
        ],
    ) > 0
    generic_leak_only = (
        score_terms(lower, ["leak", "leaked", "泄露", "爆料"]) > 0
        and leak_score <= 0
        and sensitive_hardware_score <= 0
        and supplier_score <= 0
    )
    if generic_leak_only:
        return False
    visual_only_leak = (
        score_terms(lower, ["image", "images", "photo", "photos", "picture", "render", "renders", "渲染图", "图片", "照片"]) > 0
        and score_terms(lower, ["file", "files", "document", "documents", "data sheet", "data sheets", "schematic", "schematics", "dark web", "stolen", "hacked", "文件", "文档", "资料", "数据表", "图纸", "暗网", "被窃取", "黑客"]) <= 0
        and supplier_score <= 0
    )
    if visual_only_leak:
        return False
    return product_score > 0 and (leak_score > 0 or title_leak_subject) and (
        supplier_score > 0 or sensitive_hardware_score > 0 or title_leak_subject
    )


def is_apple_product_data_leak_enforcement_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    title_scope = (title or text[:220]).lower()
    title_enforcement_subject = (
        score_terms(title_scope, ["apple", "iphone", "ipad", "mac", "苹果"]) > 0
        and score_terms(title_scope, ["leak", "leaks", "leaked", "leak video", "泄露", "爆料"]) > 0
        and score_terms(title_scope, ["dmca", "takedown", "removed", "disappear", "disappears", "crackdown", "strike", "striking", "下架", "删除", "消失", "打击", "清除", "追责", "投诉", "封禁"]) > 0
    )
    if not title_enforcement_subject and not is_apple_product_data_leak_story(lower, title):
        return False
    return score_terms(
        lower,
        [
            "dmca",
            "takedown",
            "takedowns",
            "take down",
            "removed",
            "disappear",
            "disappeared",
            "legal team",
            "crackdown",
            "complaint",
            "complaints",
            "copyright",
            "striking",
            "下架",
            "删除",
            "消失",
            "打击",
            "清除",
            "追责",
            "投诉",
            "法务",
            "版权",
            "封禁",
        ],
    ) > 0


def is_apple_product_data_leak_specs_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    title_scope = (title or text[:220]).lower()
    title_specs_subject = (
        score_terms(title_scope, ["apple", "iphone", "ipad", "mac", "苹果"]) > 0
        and score_terms(title_scope, ["leak", "leaks", "leaked", "泄露", "爆料"]) > 0
        and not (
            score_terms(title_scope, ["image", "images", "photo", "photos", "picture", "render", "renders", "渲染图", "图片", "照片"]) > 0
            and score_terms(title_scope, ["file", "files", "document", "documents", "data sheet", "data sheets", "schematic", "schematics", "c2", "modem", "qualcomm", "文件", "文档", "资料", "数据表", "图纸", "基带"]) <= 0
        )
        and score_terms(
            title_scope,
            [
                "spec",
                "specs",
                "specification",
                "data sheet",
                "data sheets",
                "file",
                "files",
                "document",
                "documents",
                "logic board",
                "bill of materials",
                "bom",
                "c2",
                "modem",
                "qualcomm",
                "wmcm",
                "packaging",
                "package",
                "规格",
                "参数",
                "资料",
                "文件",
                "文档",
                "物料清单",
                "主板",
                "基带",
                "封装",
            ],
        )
        > 0
    )
    if not title_specs_subject:
        if not is_apple_product_data_leak_story(lower, title):
            return False
        if score_terms(
            lower,
            [
                "file",
                "files",
                "document",
                "documents",
                "data sheet",
                "data sheets",
                "schematic",
                "schematics",
                "bill of materials",
                "bom",
                "technical document",
                "technical documents",
                "机密文件",
                "文件",
                "文档",
                "技术文档",
                "资料",
                "数据表",
                "图纸",
                "物料清单",
            ],
        ) <= 0:
            return False
    return score_terms(
        lower,
        [
            "spec",
            "specs",
            "specification",
            "specifications",
            "a20",
            "a20 pro",
            "c2",
            "modem",
            "qualcomm",
            "camera",
            "ram",
            "12gb",
            "packaging",
            "package",
            "wmcm",
            "规格",
            "参数",
            "芯片",
            "基带",
            "相机",
            "摄像头",
            "内存",
            "封装",
        ],
    ) > 0


def is_third_party_benchmark_comparison_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    third_party_subject_score = score_terms(
        lower,
        [
            "amd",
            "core ",
            "dell",
            "geforce",
            "huawei",
            "intel",
            "mediatek",
            "nvidia",
            "qualcomm",
            "radeon",
            "ryzen",
            "snapdragon",
            "windows pc",
            "wildcat lake",
            "xps",
            "英特尔",
            "酷睿",
            "高通",
            "骁龙",
            "英伟达",
            "联发科",
            "华为",
            "戴尔",
            "锐龙",
        ],
    )
    benchmark_score = score_terms(
        lower,
        [
            "benchmark",
            "geekbench",
            "passmark",
            "single-core",
            "multi-core",
            "score",
            "scores",
            "跑分",
            "单核",
            "多核",
            "成绩",
            "得分",
        ],
    )
    comparison_score = score_terms(
        lower,
        [
            "compared",
            "matches",
            "matching",
            "outperforms",
            "rival",
            "versus",
            "vs",
            "on par",
            "对比",
            "相比",
            "追平",
            "持平",
            "媲美",
            "超过",
            "反超",
            "不输",
        ],
    )
    apple_chip_score = score_terms(lower, ["apple silicon", "苹果芯片"])
    if re.search(r"\b[am]\d{1,2}(?:\s*(?:pro|max|ultra))?\b", lower):
        apple_chip_score += 1
    apple_subject_score = score_terms(
        lower,
        [
            "apple tests",
            "apple tested",
            "apple benchmark",
            "apple's chip",
            "apple chip",
            "苹果测试",
            "苹果芯片跑分",
        ],
    )
    return (
        third_party_subject_score > 0
        and benchmark_score > 0
        and comparison_score > 0
        and apple_chip_score > 0
        and apple_subject_score == 0
    )


def has_title_apple_product_subject(title: str) -> bool:
    lower = title.lower()
    return effective_apple_term_score(title) > 0 or score_terms(
        lower,
        [
            "tim cook",
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "airpods",
            "apple watch",
            "vision pro",
            "库克",
            "苹果",
        ],
    ) > 0


def is_apple_product_price_increase_story(text: str, title: str = "") -> bool:
    title_lower = title.lower()
    inferred_title_lower = title_lower or text[:180].lower()
    title_price_story = (
        score_terms(
            inferred_title_lower,
            [
                "apple",
                "iphone",
                "ipad",
                "mac",
                "macbook",
                "mac mini",
                "homepod",
                "apple tv",
                "vision pro",
                "apple watch",
                "airpods",
                "苹果",
            ],
        )
        > 0
        and score_terms(
            inferred_title_lower,
            [
                "price increase",
                "price increases",
                "price hike",
                "price hikes",
                "increased prices",
                "raises prices",
                "raised prices",
                "raising prices",
                "hikes prices",
                "hikes",
                "went up in price",
                "up in price",
                "starting price",
                "more expensive",
                "涨价",
                "调价",
                "价格",
            ],
        )
        > 0
    )
    if title and not has_title_apple_product_subject(title) and not title_price_story:
        return False
    if title and not title_price_story and is_primary_apple_chip_roadmap_title(title):
        return False
    if not title and not title_price_story and is_primary_apple_chip_roadmap_title(text[:180]):
        return False
    lower = text.lower()
    apple_product_score = score_terms(
        lower,
        [
            "apple",
            "tim cook",
            "iphone",
            "ipad",
            "mac",
            "mac mini",
            "mac studio",
            "homepod",
            "apple tv",
            "vision pro",
            "apple watch",
            "airpods",
            "苹果",
            "库克",
        ],
    )
    price_increase_score = score_terms(
        lower,
        [
            "price increase",
            "price increases",
            "increased prices",
            "raises prices",
            "raised prices",
            "raising prices",
            "hikes prices",
            "prices go up",
            "went up in price",
            "up in price",
            "more expensive",
            "increase device costs",
            "price-inflated",
            "price hike",
            "starting price",
            "hikes",
            "涨价",
            "上调",
            "提高",
            "更贵",
            "成本转嫁",
            "价格上涨",
        ],
    )
    cost_driver_score = score_terms(
        lower,
        [
            "memory",
            "storage",
            "dram",
            "nand",
            "ssd",
            "chip shortage",
            "chip shortages",
            "shortage",
            "shortages",
            "cost",
            "costs",
            "ai demand",
            "内存",
            "存储",
            "存储芯片",
            "短缺",
            "成本",
            "ai 需求",
            "芯片",
        ],
    )
    if title_price_story and apple_product_score > 0 and price_increase_score > 0:
        if score_terms(lower, ["stock price", "share price", "market cap", "股价", "市值"]) <= 0:
            return True
    return apple_product_score > 0 and price_increase_score > 0 and cost_driver_score > 0


def is_apple_retail_promotion_price_context_story(text: str, title: str = "") -> bool:
    scope = f"{title} {text}".lower()
    if effective_apple_term_score(scope) <= 0:
        return False
    if score_terms(
        scope,
        [
            "back to school",
            "back-to-school",
            "education discount",
            "gift card",
            "promo",
            "promotion",
            "offer",
            "返校季",
            "返校",
            "教育优惠",
            "礼品卡",
            "促销活动",
            "促销",
            "优惠活动",
        ],
    ) <= 0:
        return False
    return score_terms(
        scope,
        [
            "price increase",
            "price increases",
            "price hike",
            "raised prices",
            "increased prices",
            "price",
            "涨价",
            "调价",
            "价格",
            "缓冲",
            "抵消",
        ],
    ) > 0


def is_future_apple_product_price_forecast_story(text: str, title: str = "") -> bool:
    headline_scope = (title or text[:220]).lower()
    if effective_apple_term_score(headline_scope) <= 0 and score_terms(headline_scope, ["iphone", "ipad", "mac"]) <= 0:
        return False
    future_product_score = score_terms(
        headline_scope,
        [
            "iphone 18",
            "iphone 19",
            "iphone ultra",
            "foldable iphone",
            "folding iphone",
            "iphone fold",
            "next iphone",
            "future iphone",
            "2027 iphone",
            "2028 iphone",
            "iPhone 18".lower(),
            "iPhone Ultra".lower(),
            "折叠屏 iphone",
            "折叠 iphone",
            "折叠屏手机",
            "下一代 iphone",
            "未来 iphone",
            "明年 iphone",
            "万元机",
        ],
    )
    if future_product_score <= 0:
        return False
    price_forecast_score = score_terms(
        headline_scope,
        [
            "could start",
            "may start",
            "expected",
            "estimated",
            "forecast",
            "report",
            "reportedly",
            "rumor",
            "rumored",
            "prediction",
            "price",
            "pricing",
            "more expensive",
            "涨价",
            "售价",
            "起售价",
            "价格",
            "万元",
            "预计",
            "预估",
            "预测",
            "消息称",
            "爆料",
            "或",
            "将",
        ],
    )
    return price_forecast_score > 0


def is_apple_price_external_reaction_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    actor_score = score_terms(
        lower,
        [
            "elon musk",
            "musk",
            "analyst",
            "executive",
            "investor",
            "industry watcher",
            "industry executive",
            "ceo",
            "cfo",
            "马斯克",
            "分析师",
            "高管",
            "业内人士",
            "行业人士",
            "投资人",
        ],
    )
    reaction_score = score_terms(
        lower,
        [
            "react",
            "reaction",
            "respond",
            "response",
            "defend",
            "backed",
            "backs",
            "support",
            "supports",
            "agrees",
            "commented",
            "weighs in",
            "回应",
            "评价",
            "评论",
            "表态",
            "支持",
            "声援",
            "力挺",
            "赞同",
            "转发",
        ],
    )
    return actor_score > 0 and reaction_score > 0


def is_apple_price_supplier_cost_dispute_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    supplier_score = score_terms(
        lower,
        [
            "micron",
            "memory supplier",
            "chip supplier",
            "component supplier",
            "supplier executive",
            "chipmaker",
            "dram supplier",
            "nand supplier",
            "美光",
            "供应商",
            "芯片厂商",
            "内存厂商",
            "存储厂商",
            "高管",
        ],
    )
    dispute_score = score_terms(
        lower,
        [
            "criticize",
            "criticized",
            "criticism",
            "dispute",
            "pushback",
            "pass on",
            "passes on",
            "passing on",
            "cost pass-through",
            "markup",
            "mark up",
            "overcharge",
            "margin",
            "质疑",
            "批评",
            "怒怼",
            "争议",
            "转嫁",
            "加价",
            "成本转嫁",
            "终端加价",
            "利润",
        ],
    )
    return supplier_score > 0 and dispute_score > 0


def is_apple_price_retailer_retroactive_adjustment_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    retailer_score = score_terms(
        lower,
        [
            "authorized reseller",
            "authorised reseller",
            "authorized retailer",
            "authorised retailer",
            "reseller",
            "retailer",
            "dealer",
            "store",
            "seller",
            "third-party seller",
            "third party seller",
            "经销商",
            "授权经销商",
            "零售商",
            "销售商",
            "卖家",
            "门店",
            "第三方商家",
        ],
    )
    existing_order_score = score_terms(
        lower,
        [
            "already ordered",
            "existing order",
            "placed an order",
            "paid in full",
            "full payment",
            "preorder",
            "pre-order",
            "customer",
            "buyer",
            "purchase",
            "purchased",
            "delivery",
            "ship",
            "下单",
            "已下单",
            "订单",
            "全额",
            "全款",
            "已付款",
            "买家",
            "客户",
            "消费者",
            "交付",
            "发货",
        ],
    )
    retroactive_price_score = score_terms(
        lower,
        [
            "retroactive",
            "after the price hike",
            "after the price increase",
            "pay the difference",
            "price difference",
            "make up the difference",
            "top up",
            "cancel the order",
            "refund",
            "refused to honor",
            "补差价",
            "补足差价",
            "追溯",
            "事后",
            "单方面",
            "涨价后",
            "调价后",
            "涨价前",
            "调价前",
            "全额退款",
            "取消订单",
            "拒绝按原价",
            "原价履约",
            "追加收费",
        ],
    )
    retroactive_price_pattern = re.search(r"(?:补|追要|追缴|追加)[^，。；;:：]{0,16}差价", lower) is not None
    return retailer_score > 0 and existing_order_score > 0 and (retroactive_price_score > 0 or retroactive_price_pattern)


def is_apple_refurbished_store_price_context_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    refurb_score = score_terms(
        lower,
        [
            "certified refurbished",
            "official refurbished",
            "refurbished",
            "refurb",
            "apple refurbished store",
            "官翻",
            "官方翻新",
            "翻新版",
            "翻新机",
        ],
    )
    availability_score = score_terms(
        lower,
        [
            "available",
            "launches",
            "launched",
            "listed",
            "now on sale",
            "starts at",
            "store",
            "上架",
            "开售",
            "发售",
            "起售价",
            "售价",
            "苹果官网",
            "官方商城",
        ],
    )
    return refurb_score > 0 and availability_score > 0


def is_iphone_color_mockup_or_finish_rumor(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(lower, ["iphone"]) <= 0:
        return False
    color_score = score_terms(
        lower,
        [
            "dark cherry",
            "cherry",
            "burgundy",
            "red finish",
            "red color",
            "new color",
            "new colors",
            "color option",
            "color options",
            "finish",
            "finishes",
            "red",
            "配色",
            "颜色",
            "樱桃红",
            "红色",
            "红色款",
            "深樱桃",
            "酒红",
            "银灰",
            "浅蓝",
            "黑灰",
        ],
    )
    visual_or_leak_score = score_terms(
        lower,
        [
            "sim tray",
            "tray",
            "dummy",
            "dummy model",
            "mockup",
            "render",
            "leaked image",
            "leaked photo",
            "leaked video",
            "image shared",
            "photo",
            "photos",
            "video",
            "testing",
            "test unit",
            "alleged",
            "leaker",
            "leak",
            "leaked",
            "weibo",
            "x platform",
            "卡托",
            "机模",
            "渲染图",
            "图片",
            "照片",
            "视频",
            "测试",
            "曝光",
            "泄露",
            "爆料",
            "偷跑",
            "流出",
            "消息源",
            "博主",
        ],
    )
    if color_score <= 0 or visual_or_leak_score <= 0:
        return False
    if is_official_apple_refurbished_product_story(lower):
        refurb_context_score = score_terms(
            lower,
            [
                "refurbished",
                "certified refurbished",
                "online refurbished store",
                "refurbished store",
                "官翻",
                "官方翻新",
                "翻新版",
                "翻新机",
            ],
        )
        color_sale_score = score_terms(
            lower,
            [
                "both colors available",
                "available in",
                "comes in",
                "black or white",
                "colors available",
                "可选",
                "黑色",
                "白色",
            ],
        )
        if refurb_context_score > 0 and color_sale_score > 0 and visual_or_leak_score <= 1:
            return False
    return True


def apple_product_price_topic_facets(text: str, title: str = "") -> set[str]:
    if not is_apple_product_price_increase_story(text, title):
        return set()
    facets = {"apple-product-price-increase"}
    if is_apple_retail_promotion_price_context_story(text, title):
        facets.add("apple-retail-promotion-price-context")
    elif is_future_apple_product_price_forecast_story(text, title):
        facets.add("apple-future-product-price-forecast")
    else:
        facets.add("apple-current-product-price-increase")
    if is_apple_price_external_reaction_story(text, title):
        facets.add("apple-price-external-reaction")
    if is_apple_price_retailer_retroactive_adjustment_story(text, title):
        facets.add("apple-price-retailer-retroactive-adjustment")
    if is_apple_price_supplier_cost_dispute_story(text, title):
        facets.add("apple-price-supplier-cost-dispute")
    if is_apple_refurbished_store_price_context_story(text, title):
        facets.add("apple-refurbished-store-price-context")
    return facets


def is_apple_restricted_memory_supplier_approval_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    memory_score = score_terms(
        lower,
        [
            "memory",
            "ram",
            "dram",
            "nand",
            "storage chip",
            "storage chips",
            "memory chips",
            "内存",
            "存储芯片",
            "存储",
        ],
    )
    if memory_score <= 0:
        return False
    supplier_or_restriction_score = score_terms(
        lower,
        [
            "cxmt",
            "changxin",
            "blacklisted supplier",
            "blacklisted chinese supplier",
            "blacklisted company",
            "blacklist",
            "entity list",
            "chinese military company blacklist",
            "1260h",
            "restricted supplier",
            "sanctioned supplier",
            "长鑫",
            "长鑫存储",
            "黑名单",
            "实体清单",
            "受限供应商",
            "军方背景",
        ],
    )
    if supplier_or_restriction_score <= 0:
        return False
    approval_score = score_terms(
        lower,
        [
            "ask",
            "asks",
            "asked",
            "petition",
            "petitioned",
            "lobby",
            "lobbies",
            "lobbying",
            "clearance",
            "permission",
            "approval",
            "approve",
            "allowed",
            "allow it to buy",
            "let it buy",
            "blessing",
            "申请",
            "请求",
            "寻求批准",
            "获准",
            "许可",
            "批准",
            "放行",
        ],
    )
    authority_score = score_terms(
        lower,
        [
            "trump",
            "trump administration",
            "white house",
            "pentagon",
            "commerce department",
            "u.s. government",
            "us government",
            "administration",
            "特朗普",
            "白宫",
            "五角大楼",
            "美国政府",
            "商务部",
        ],
    )
    return approval_score > 0 and authority_score > 0


def is_apple_memory_supply_constraint_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "memory",
            "ram",
            "dram",
            "lpddr",
            "storage chip",
            "memory chips",
            "内存",
            "存储芯片",
            "存储",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "supply gap",
            "supply shortage",
            "supply constraints",
            "shortage",
            "tight supply",
            "procurement",
            "purchase",
            "buy",
            "pull-in",
            "data center",
            "capacity",
            "供需缺口",
            "供应紧张",
            "短缺",
            "采购",
            "拉货",
            "数据中心",
            "产能",
        ],
    ) > 0


def is_apple_chip_process_roadmap_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(lower, ["chip", "chips", "a20", "a22", "tsmc", "process", "node", "wafer", "芯片", "台积电", "制程", "工艺", "晶圆"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "1.4nm",
            "1.4 nm",
            "2nm",
            "2 nm",
            "n2",
            "n2p",
            "advanced process",
            "process roadmap",
            "nanometer",
            "capacity",
            "1.4纳米",
            "2纳米",
            "先进制程",
            "制程路线",
            "产能",
            "抢占",
        ],
    ) > 0


def price_subtopic_facets(facets: set[str]) -> set[str]:
    return facets & APPLE_PRICE_SUBTOPIC_FACETS


def price_detail_facets(facets: set[str]) -> set[str]:
    return facets & APPLE_PRICE_DETAIL_FACETS


def price_timing_facets(facets: set[str]) -> set[str]:
    return facets & APPLE_PRICE_TIMING_FACETS


def price_summary_key_facets(facets: set[str]) -> set[str]:
    return price_detail_facets(facets) or price_timing_facets(facets)


def price_facets_compatible(left: set[str], right: set[str]) -> bool:
    if "apple-product-price-increase" not in left or "apple-product-price-increase" not in right:
        return True
    left_details = price_detail_facets(left)
    right_details = price_detail_facets(right)
    if left_details or right_details:
        return bool(left_details and right_details and left_details & right_details)
    left_timing = price_timing_facets(left)
    right_timing = price_timing_facets(right)
    if left_timing and right_timing:
        return bool(left_timing & right_timing)
    return not (left_timing or right_timing)


def restricted_memory_supplier_approval_facets_compatible(left: set[str], right: set[str]) -> bool:
    restricted_facet = "apple-restricted-memory-supplier-approval"
    return (restricted_facet in left) == (restricted_facet in right)


def strategic_transaction_facets_compatible(left: set[str], right: set[str]) -> bool:
    transaction_facet = "apple-strategic-transaction"
    left_has = transaction_facet in left
    right_has = transaction_facet in right
    if left_has != right_has:
        return False
    if not left_has:
        return True
    left_counterparties = {facet for facet in left if facet.startswith("transaction-counterparty-")}
    right_counterparties = {facet for facet in right if facet.startswith("transaction-counterparty-")}
    if left_counterparties and right_counterparties:
        return bool(left_counterparties & right_counterparties)
    return True


def shared_specific_strategic_transaction(left: set[str], right: set[str]) -> bool:
    if "apple-strategic-transaction" not in left or "apple-strategic-transaction" not in right:
        return False
    left_counterparties = {facet for facet in left if facet.startswith("transaction-counterparty-")}
    right_counterparties = {facet for facet in right if facet.startswith("transaction-counterparty-")}
    return bool(left_counterparties and right_counterparties and left_counterparties & right_counterparties)


def is_non_apple_price_followup_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    if score_terms(
        title_lower,
        [
            "price increase",
            "price hike",
            "raised prices",
            "raises prices",
            "hikes prices",
            "more expensive",
            "涨价",
            "调价",
            "上调",
            "提高",
            "提价",
            "价格上调",
            "售价上调",
            "售价",
        ],
    ) <= 0:
        return False
    if score_terms(f"{title_lower} {text.lower()[:280]}", ["apple", "苹果"]) <= 0:
        return False
    if score_terms(
        title_lower,
        [
            "apple product price",
            "apple price increase",
            "apple price increases",
            "apple raises prices",
            "apple raised prices",
            "apple plans to raise",
            "苹果产品涨价",
            "苹果产品价格",
            "苹果计划上调",
            "苹果公司上调",
            "苹果硬件售价",
            "苹果产品售价",
            "iphone 等苹果产品",
            "ipad 和 mac",
            "mac 和 ipad",
        ],
    ) > 0:
        return False
    third_party_subject_score = score_terms(
        title_lower,
        [
            "microsoft",
            "xbox",
            "sony",
            "playstation",
            "nintendo",
            "google",
            "pixel",
            "samsung",
            "lg",
            "meta",
            "quest",
            "tesla",
            "dji",
            "drone",
            "drones",
            "memory",
            "storage",
            "smartphone",
            "phone maker",
            "phone makers",
            "微软",
            "索尼",
            "任天堂",
            "谷歌",
            "三星",
            "lg",
            "meta",
            "特斯拉",
            "大疆",
            "无人机",
            "手机",
            "国产手机",
            "内存",
            "存储",
            "厂商",
        ],
    )
    if third_party_subject_score <= 0:
        return False
    apple_subject_positions = [
        pos
        for pos in [title_lower.find(term) for term in ["apple", "苹果", "iphone", "ipad", "mac", "macbook"]]
        if pos >= 0
    ]
    third_party_positions = [
        pos
        for pos in [
            title_lower.find(term)
            for term in [
                "xbox",
                "microsoft",
                "微软",
                "sony",
                "索尼",
                "samsung",
                "三星",
                "google",
                "谷歌",
                "dji",
                "大疆",
                "无人机",
                "国产手机",
                "手机",
                "内存",
                "存储",
            ]
        ]
        if pos >= 0
    ]
    followup_score = score_terms(
        title_lower,
        [
            "following apple",
            "after apple",
            "in response to apple",
            "as apple",
            "joins apple",
            "跟进苹果",
            "紧随苹果",
            "继苹果",
            "在苹果",
            "随着苹果",
            "效仿苹果",
        ],
    )
    if (
        apple_subject_positions
        and third_party_positions
        and min(apple_subject_positions) < min(third_party_positions)
        and followup_score <= 0
    ):
        return False
    return followup_score > 0 or (
        bool(apple_subject_positions)
        and bool(third_party_positions)
        and min(apple_subject_positions) > min(third_party_positions)
    )


def is_non_apple_component_market_background_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if score_terms(title_lower, ["apple", "iphone", "ipad", "mac", "macbook", "苹果"]) > 0:
        return False
    if score_terms(lower, ["apple", "iphone", "ipad", "mac", "macbook", "苹果"]) <= 0:
        return False
    component_or_industry_score = score_terms(
        title_lower,
        [
            "memory",
            "storage",
            "dram",
            "nand",
            "chip",
            "semiconductor",
            "micron",
            "sk hynix",
            "samsung",
            "elpidia",
            "smartphone",
            "phone makers",
            "内存",
            "存储",
            "芯片",
            "半导体",
            "美光",
            "海力士",
            "三星",
            "尔必达",
            "手机",
            "国产手机",
            "厂商",
        ],
    )
    if component_or_industry_score <= 0:
        return False
    background_score = score_terms(
        f"{title_lower} {lower[:360]}",
        [
            "industry",
            "market",
            "history",
            "profit",
            "profits",
            "collapse",
            "bank",
            "price",
            "prices",
            "涨价",
            "价格",
            "行业",
            "市场",
            "利润",
            "倒闭",
            "银行",
            "国运",
            "背景",
            "回顾",
        ],
    )
    if background_score <= 0:
        return False
    direct_apple_action_score = score_terms(
        lower[:420],
        [
            "apple announced",
            "apple raised",
            "apple increased",
            "apple explains",
            "apple said",
            "apple supplier",
            "苹果宣布",
            "苹果上调",
            "苹果涨价",
            "苹果回应",
            "苹果表示",
            "苹果供应商",
        ],
    )
    if direct_apple_action_score > 0 and score_terms(title_lower, ["美光", "micron"]) > 0:
        return False
    return True


def is_multi_vendor_chip_or_phone_roadmap_background_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if score_terms(title_lower, ["apple", "iphone", "ipad", "mac", "macbook", "苹果"]) > 0:
        return False
    if effective_apple_term_score(lower) <= 0:
        return False
    non_apple_subject_score = score_terms(
        title_lower,
        [
            "mediatek",
            "dimensity",
            "qualcomm",
            "snapdragon",
            "huawei",
            "mate",
            "xiaomi",
            "vivo",
            "oppo",
            "oneplus",
            "iqoo",
            "android",
            "smartphone",
            "phone",
            "chip",
            "soc",
            "联发科",
            "天玑",
            "高通",
            "骁龙",
            "华为",
            "小米",
            "安卓",
            "手机",
            "芯片",
        ],
    )
    if non_apple_subject_score <= 0:
        return False
    multi_vendor_context_score = score_terms(
        lower[:1200],
        [
            "qualcomm, apple",
            "apple and mediatek",
            "apple and qualcomm",
            "alongside apple",
            "compared with apple",
            "高通、苹果",
            "苹果和联发科",
            "苹果和高通",
            "苹果、联发科",
            "陆续推出各自",
            "同一时间点",
            "竞品",
            "对比",
        ],
    )
    apple_background_score = score_terms(
        lower[:1600],
        [
            "a20",
            "iphone air",
            "iphone 18",
            "apple's chip",
            "苹果 a20",
            "苹果芯片",
            "苹果手机",
        ],
    )
    return multi_vendor_context_score > 0 and apple_background_score > 0


def is_primary_apple_chip_roadmap_title(title: str) -> bool:
    lower = title.lower()
    if score_terms(lower, ["m5", "m6", "m7", "chip", "chips", "芯片"]) <= 0:
        return False
    if score_terms(lower, ["price", "prices", "hike", "hikes", "increase", "increased", "涨价", "调价", "价格"]) > 0:
        return False
    return score_terms(
        lower,
        [
            "skip",
            "skips",
            "expected",
            "launch",
            "launches",
            "could launch",
            "roadmap",
            "timeline",
            "ai-focused",
            "pro",
            "max",
            "ultra",
            "跳过",
            "推出",
            "路线",
            "规划",
        ],
    ) > 0


def is_broad_multi_vendor_market_report(text: str, title: str = "") -> bool:
    lower = text.lower()
    title_lower = title.lower()
    if score_terms(lower, ["shipment", "shipments", "market share", "market", "omdia", "counterpoint", "出货", "份额", "市场"]) <= 0:
        return False
    title_competitor_count = sum(
        1
        for term in [
            "lenovo",
            "huawei",
            "hp",
            "dell",
            "asus",
            "acer",
            "samsung",
            "联想",
            "华为",
            "惠普",
            "戴尔",
            "华硕",
            "宏碁",
            "三星",
        ]
        if term in title_lower
    )
    if (
        title_competitor_count >= 2
        and score_terms(title_lower, ["market", "omdia", "counterpoint", "出货", "份额", "市场", "报告"]) > 0
        and score_terms(title_lower, ["apple", "iphone", "ipad", "mac", "macbook", "苹果"]) > 0
        and not re.search(
            r"(?:apple|iphone|ipad|mac|苹果)[^。.!?，,；;\n]{0,80}(?:\d+(?:\.\d+)?\s*(?:%|万|million|billion)|同比|增长|下降|份额|出货)",
            title_lower,
        )
    ):
        return True
    if score_terms(title_lower, ["apple", "iphone", "ipad", "mac", "macbook", "苹果", "iPhone", "iPad"]) > 0 and score_terms(
        title_lower,
        ["grew", "growth", "rises", "rose", "ranked", "shipments grew", "同比增长", "增长", "排名", "份额"],
    ) > 0:
        return False
    competitor_count = sum(
        1
        for term in [
            "lenovo",
            "huawei",
            "hp",
            "dell",
            "asus",
            "acer",
            "samsung",
            "联想",
            "华为",
            "惠普",
            "戴尔",
            "华硕",
            "宏碁",
            "三星",
        ]
        if term in lower
    )
    if competitor_count < 2:
        return False
    apple_specific_metric = re.search(
        r"(?:apple|iphone|ipad|mac|苹果)[^。.!?，,；;\n]{0,80}(?:\d+(?:\.\d+)?\s*(?:%|万|million|billion)|同比|增长|下降|份额|出货)",
        lower,
    )
    if apple_specific_metric:
        return False
    return True


def is_apple_specific_market_share_report_story(text: str, title: str = "") -> bool:
    scope = f"{title} {text}".lower()
    headline_scope = (title or text[:220]).lower()
    if score_terms(headline_scope, ["apple", "iphone", "ipad", "mac", "macbook", "apple watch", "苹果"]) <= 0:
        return False
    if score_terms(
        scope,
        [
            "market share",
            "shipments",
            "counterpoint",
            "canalys",
            "idc",
            "omdia",
            "份额",
            "出货",
            "出货量",
            "市场占有率",
            "报告",
        ],
    ) <= 0:
        return False
    return score_terms(
        scope,
        [
            "record",
            "grew",
            "growth",
            "gain",
            "gaining",
            "rising",
            "reaching",
            "同比",
            "增长",
            "提升",
            "达到",
            "创纪录",
            "%",
        ],
    ) > 0


def is_competitor_or_company_story_using_apple_as_benchmark(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if effective_apple_term_score(text) <= 0:
        return False
    benchmark_score = score_terms(
        lower,
        [
            "challenge apple",
            "compete with apple",
            "rival apple",
            "beat apple",
            "catch up with apple",
            "apple-like",
            "like apple",
            "叫板苹果",
            "赶超苹果",
            "对标苹果",
            "硬刚苹果",
            "媲美苹果",
            "苹果风格",
            "类似苹果",
        ],
    )
    if benchmark_score <= 0:
        return False
    non_apple_subject_score = score_terms(
        lower,
        [
            "android",
            "huawei",
            "honor",
            "xiaomi",
            "vivo",
            "oppo",
            "samsung",
            "tesla",
            "dyson",
            "dreame",
            "国产",
            "安卓",
            "华为",
            "荣耀",
            "小米",
            "三星",
            "特斯拉",
            "戴森",
            "追觅",
            "厂商",
        ],
    )
    if non_apple_subject_score <= 0:
        return False
    if score_terms(
        title_lower,
        [
            "apple",
            "iphone",
            "ipad",
            "mac",
            "airpods",
            "apple watch",
            "vision pro",
            "苹果发布",
            "苹果推出",
            "苹果开发",
            "苹果正在",
            "消息称苹果",
        ],
    ) > 0 and score_terms(title_lower, ["叫板苹果", "赶超苹果", "对标苹果", "硬刚苹果"]) <= 0:
        return False
    if has_apple_first_party_release_context(lower) and score_terms(title_lower, ["叫板苹果", "赶超苹果", "对标苹果", "硬刚苹果"]) <= 0:
        return False
    return True


def is_third_party_app_or_service_status_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if is_foldable_iphone_successor_roadmap_story(f"{title} {text}"):
        return False
    if title_lower.startswith("apple ") or title_lower.startswith("苹果"):
        return False
    if app_store_policy_score(lower) > 0:
        return False
    if has_first_party_software_title_subject(title) or has_apple_first_party_release_context(text):
        return False
    if score_terms(
        lower,
        ["ios", "ipados", "macos", "iphone", "ipad", "mac", "app store", "apple watch", "vision pro", "苹果应用商店"],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "third-party",
            "third party",
            "app",
            "apps",
            "application",
            "client",
            "service",
            "email client",
            "calculator app",
            "utility",
            "workflow",
            "agent",
            "open source",
            "openstreetmap",
            "map app",
            "maps app",
            "第三方",
            "应用",
            "客户端",
            "服务",
            "开源",
            "地图应用",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "shutting down",
            "shuts down",
            "shutdown",
            "close",
            "closes",
            "closing",
            "discontinue",
            "discontinues",
            "discontinued",
            "sunset",
            "sunsetting",
            "launched",
            "launches",
            "released",
            "updated",
            "brings",
            "gets",
            "expanding to",
            "native",
            "builds",
            "created",
            "停运",
            "关闭",
            "终止",
            "下线",
            "上线",
            "发布",
            "更新",
            "获得",
            "打造",
            "带来",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "apple acquired",
            "joins apple",
            "apple approved",
            "apple policy",
            "apple requires",
            "苹果收购",
            "加入苹果",
            "苹果批准",
            "苹果政策",
        ],
    ) == 0


def is_broad_apple_product_roadmap_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(
        lower,
        [
            "20 products",
            "around 20 products",
            "about 20 products",
            "20 new products",
            "approximately 20 products",
            "约 20 款",
            "约20款",
            "20 款新品",
            "20款新品",
            "20 款产品",
            "20款产品",
        ],
    ) <= 0:
        return False
    if effective_apple_term_score(lower) <= 0:
        return False
    product_line_hits = sum(
        1
        for terms in [
            ["iphone"],
            ["mac", "macbook"],
            ["ipad"],
            ["apple watch", "watch"],
            ["airpods"],
            ["homepod", "home hub", "apple tv"],
            ["vision pro", "apple glasses", "smart glasses", "智能眼镜"],
            ["苹果眼镜"],
        ]
        if score_terms(lower, terms) > 0
    )
    if product_line_hits < 3:
        return False
    return score_terms(
        lower,
        [
            "2026",
            "2027",
            "rest of 2026",
            "remainder of 2026",
            "across rest",
            "product roadmap",
            "roadmap",
            "new products",
            "mark gurman",
            "gurman",
            "power on",
            "未来两年",
            "产品路线图",
            "古尔曼",
            "下半年",
        ],
    ) >= 2


def is_foldable_iphone_supply_chain_story(text: str) -> bool:
    lower = text.lower()
    foldable_score = score_terms(
        lower,
        ["foldable iphone", "iphone fold", "folding iphone", "折叠屏 iphone", "折叠 iphone", "折叠屏手机"],
    )
    if foldable_score <= 0 and not (
        score_terms(lower, ["iphone"]) > 0 and score_terms(lower, ["foldable", "folding", "折叠屏", "折叠"]) > 0
    ):
        return False
    production_score = score_terms(
        lower,
        [
            "production",
            "mass production",
            "manufacturing",
            "small batch",
            "target guidance",
            "launch target",
            "量产",
            "生产",
            "小批量",
            "目标指引",
        ],
    )
    supply_score = score_terms(
        lower,
        [
            "supply chain",
            "supplier",
            "suppliers",
            "supply",
            "supplies",
            "supplied",
            "供应链",
            "供应商",
            "供货",
            "代工",
        ],
    )
    return production_score > 0 and (supply_score > 0 or production_score >= 2)


def is_foldable_iphone_successor_roadmap_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone ultra 2", "iphone ultra2", "second-generation foldable iphone", "second generation foldable iphone"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "green light",
            "greenlit",
            "go-ahead",
            "given the go-ahead",
            "approved",
            "confirmed",
            "development",
            "project",
            "second-generation",
            "second generation",
            "后继机型",
            "第二代",
            "确认启动",
            "开了绿灯",
            "绿灯",
            "已确认",
            "开发",
            "项目",
        ],
    ) > 0


def is_apple_display_panel_supply_chain_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple", "iphone", "ipad", "macbook", "apple watch", "苹果"]) <= 0:
        return False
    if score_terms(lower, ["oled", "display panel", "panel", "screen", "屏幕", "面板"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "production",
            "mass production",
            "supplier",
            "suppliers",
            "supply",
            "supplies",
            "order",
            "orders",
            "rfi",
            "量产",
            "供应",
            "供应商",
            "供货",
            "订单",
            "包揽",
            "出货",
        ],
    ) > 0


def is_competitor_display_panel_story_using_apple_as_background(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = f"{title} {text}".lower()
    if score_terms(title_lower, ["oled", "display panel", "panel", "screen", "屏幕", "面板"]) <= 0:
        return False
    if score_terms(lower, ["order", "orders", "supply", "supplier", "production", "panel", "订单", "供应", "供货", "量产", "合作"]) <= 0:
        return False
    if score_terms(
        title_lower,
        [
            "iphone",
            "ipad",
            "macbook",
            "apple watch",
            "vision pro",
            "airpods",
            "beats",
            "苹果 iphone",
            "苹果ipad",
            "苹果 mac",
            "苹果手表",
            "苹果头显",
        ],
    ) > 0:
        return False
    competitor_customer_or_product = score_terms(
        title_lower,
        [
            "galaxy",
            "samsung galaxy",
            "galaxy s",
            "galaxy z",
            "samsung order",
            "samsung orders",
            "三星订单",
            "三星 galaxy",
            "三星galaxy",
            "三星 s",
            "三星s",
            "华为",
            "小米",
            "oppo",
            "vivo",
            "荣耀",
        ],
    ) > 0
    if not competitor_customer_or_product:
        return False
    return score_terms(
        lower,
        [
            "after apple",
            "following apple",
            "after losing apple",
            "lost apple",
            "losing apple",
            "继苹果之后",
            "继失去苹果",
            "失去苹果",
            "苹果之后",
            "苹果订单之后",
        ],
    ) > 0


def is_title_primary_software_system_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if score_terms(
        title_lower,
        [
            "ios",
            "ipados",
            "macos",
            "watchos",
            "visionos",
            "tvos",
            "siri",
            "apple intelligence",
            "imessage",
            "messages",
            "safari",
            "mail",
            "notes",
            "calendar",
            "home app",
            "camera app",
            "shortcuts",
            "系统",
            "信息",
            "浏览器",
            "邮件",
            "备忘录",
            "日历",
        ],
    ) <= 0:
        return False
    return (
        is_apple_os_feature_or_summary_story(text)
        or score_terms(title_lower, OS_FEATURE_ACTION_TERMS) > 0
        or score_terms(
            lower,
            [
                "system prompt",
                "refuse",
                "summarize urls",
                "summarize url",
                "url",
                "beta",
                "feature",
                "change",
                "changes",
                "prompt",
                "提示词",
                "拒绝",
                "摘要",
                "链接",
                "测试版",
                "功能",
                "变化",
            ],
        )
        > 0
    )


def has_first_party_software_title_subject(title: str) -> bool:
    lower = title.lower()
    platform_app_launch = score_terms(
        lower,
        [
            "ios 版",
            "ios版",
            "ipados 版",
            "ipados版",
            "mac 版",
            "mac版",
            "watchos 版",
            "watchos版",
            "客户端",
            "上线",
            "上架",
            "适配",
        ],
    ) > 0
    if re.search(r"\b(?:ios|ipados|macos|watchos|tvos|visionos)\s*(?:\d{1,2}|beta|developer beta)\b", lower) and not platform_app_launch:
        return True
    return score_terms(
        lower,
        [
            "apple calendar",
            "apple mail",
            "apple notes",
            "apple wallet",
            "apple messages",
            "apple home",
            "siri",
            "apple intelligence",
            "imessage",
            "airdrop",
            "safari",
            "airpods feature",
            "camera app",
            "home app",
            "shortcuts",
            "find my",
            "airport utility",
            "苹果 ios",
            "苹果 ipados",
            "苹果 macos",
            "苹果 watchos",
            "苹果 tvos",
            "苹果 visionos",
            "苹果日历",
            "苹果邮件",
            "苹果备忘录",
            "苹果钱包",
            "苹果信息",
            "苹果家庭",
            "日历更新",
            "邮件",
            "备忘录",
            "钱包",
            "相机 app",
            "家庭 app",
            "快捷指令",
            "查找",
        ],
    ) > 0


def is_third_party_app_platform_launch_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    if has_first_party_software_title_subject(title):
        return False
    if has_apple_first_party_release_context(text):
        return False
    if score_terms(
        lower,
        ["ios", "ipados", "macos", "watchos", "visionos", "app store", "apple watch", "iphone", "ipad", "mac", "苹果应用商店"],
    ) <= 0:
        return False
    if score_terms(
        title_lower,
        [
            "ios version",
            "ios app",
            "native ios app",
            "mac app",
            "watchos app",
            "apple watch app",
            "ios 版",
            "ios版",
            "ipados 版",
            "ipados版",
            "mac 版",
            "mac版",
            "watchos 版",
            "watchos版",
            "客户端",
            "应用",
            "地图应用",
            "app",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "launch",
            "launches",
            "launched",
            "available",
            "released",
            "rolls out",
            "gets",
            "expands to",
            "expanding to",
            "supports",
            "support",
            "compatible",
            "上线",
            "上架",
            "发布",
            "推出",
            "适配",
            "支持",
            "获得",
            "打造",
            "带来",
        ],
    ) > 0


def is_legacy_apple_platform_third_party_app_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if has_apple_first_party_release_context(lower):
        return False
    legacy_platform_score = score_terms(
        lower,
        [
            "classic mac os",
            "mac os 9",
            "macos 9",
            "powerpc",
            "macintosh",
            "open transport",
            "经典 macos",
            "经典macos",
            "经典 mac os",
            "经典mac os",
            "停产多年的",
        ],
    )
    third_party_app_score = score_terms(
        lower,
        [
            "developer",
            "openstreetmap",
            "client",
            "app",
            "application",
            "map app",
            "maps app",
            "开发者",
            "客户端",
            "应用",
            "地图应用",
        ],
    )
    action_score = score_terms(
        lower,
        ["released", "created", "builds", "brings", "发布", "打造", "带来"],
    )
    return legacy_platform_score > 0 and third_party_app_score > 0 and action_score > 0


def is_third_party_legacy_apple_hardware_replica_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if has_apple_first_party_release_context(lower):
        return False
    specific_legacy_hardware_score = score_terms(
        lower,
        [
            "apple ii",
            "apple ii plus",
            "apple 2",
            "apple ][",
            "6502",
            "8-bit",
            "8 位",
            "早期 8 位",
        ],
    )
    if specific_legacy_hardware_score <= 0:
        return False
    third_party_project_score = score_terms(
        lower,
        [
            "project",
            "replica",
            "recreate",
            "recreated",
            "clone",
            "hardware replica",
            "modern components",
            "simon boak",
            "项目",
            "复刻",
            "硬件复刻",
            "现代元件",
            "开发者",
        ],
    )
    return third_party_project_score > 0


def is_apple_support_security_guidance_story(title: str, text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(text) <= 0:
        return False
    if score_terms(
        lower,
        [
            "support page",
            "support document",
            "support article",
            "support docs",
            "support page",
            "what to do",
            "advice",
            "guidance",
            "支持页面",
            "支持文档",
            "官方支持",
            "建议",
            "指南",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "stolen",
            "scam",
            "scams",
            "lost mode",
            "remote erase",
            "trusted devices",
            "theft and loss",
            "phishing",
            "fraud",
            "被盗",
            "诈骗",
            "丢失模式",
            "远程抹掉",
            "受信任设备",
            "盗抢",
            "防诈骗",
            "钓鱼",
        ],
    ) > 0


def is_primary_apple_display_panel_supply_chain_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    if score_terms(title_lower, ["oled", "display panel", "panel", "screen", "屏幕", "面板"]) <= 0:
        return False
    return is_apple_display_panel_supply_chain_story(f"{title} {text}")


def display_panel_product_groups_from_text(text: str) -> set[str]:
    lower = text.lower()
    groups: set[str] = set()
    if score_terms(lower, ["foldable iphone", "folding iphone", "iphone fold", "折叠屏 iphone", "折叠 iphone", "折叠屏iPhone".lower()]) > 0 or (
        score_terms(lower, ["iphone"]) > 0 and score_terms(lower, ["foldable", "folding", "折叠屏", "折叠"]) > 0
    ):
        groups.add("foldable-iphone")
    if score_terms(lower, ["iphone 18 pro", "iphone pro", "iphone 18", "iphone 17 pro"]) > 0:
        groups.add("iphone-pro")
    elif score_terms(lower, ["iphone"]) > 0 and "foldable-iphone" not in groups:
        groups.add("iphone")
    if score_terms(lower, ["ipad", "ipad mini", "ipad pro"]) > 0:
        groups.add("ipad")
    if score_terms(lower, ["macbook", "macbook pro", "macbook air"]) > 0:
        groups.add("macbook")
    if score_terms(lower, ["apple watch", "watch series", "苹果手表"]) > 0:
        groups.add("apple-watch")
    return groups


def hardware_product_families_from_text(text: str) -> set[str]:
    lower = text.lower()
    iphone_context = re.sub(r"\biphone[-\s]+(?:style|like)\b", "", lower)
    groups: set[str] = set()
    if score_terms(iphone_context, ["iphone", "iphone 18", "iphone 17", "iphone air", "foldable iphone", "folding iphone", "折叠屏 iphone", "折叠 iphone"]) > 0:
        groups.add("iphone")
    if score_terms(lower, ["macbook", "macbook pro", "macbook air", "macbook ultra", "touchscreen macbook", "触控 macbook"]) > 0:
        groups.update({"mac", "macbook"})
    if score_terms(lower, ["mac studio"]) > 0:
        groups.update({"mac", "mac-studio"})
    if score_terms(lower, ["mac mini"]) > 0:
        groups.update({"mac", "mac-mini"})
    if score_terms(lower, ["imac"]) > 0:
        groups.update({"mac", "imac"})
    if (
        score_terms(lower, ["mac", "m5", "m6", "m7", "apple silicon", "苹果芯片"]) > 0
        and score_terms(lower, ["iphone", "ipad", "vision pro", "apple watch", "airpods"]) <= 0
    ):
        groups.add("mac")
    if score_terms(lower, ["ipad", "ipad pro", "ipad air", "ipad mini"]) > 0:
        groups.add("ipad")
    if score_terms(lower, ["apple watch", "watch series", "watch ultra", "苹果手表"]) > 0:
        groups.add("apple-watch")
    if score_terms(lower, ["airpods", "airpods pro", "airpods max"]) > 0:
        groups.add("airpods")
    if score_terms(lower, ["vision pro", "vision products", "smart glasses", "vision series", "苹果头显"]) > 0:
        groups.add("vision")
    if score_terms(lower, ["apple tv", "apple tv 4k", "苹果电视"]) > 0:
        groups.add("apple-tv")
    if score_terms(lower, ["iring", "smart ring", "ring wearable", "apple ring", "智能戒指"]) > 0:
        groups.add("smart-ring")
    return groups


def apple_chip_roadmap_facets_from_text(text: str) -> set[str]:
    if is_apple_chip_process_roadmap_story(text):
        return {"apple-chip-process-roadmap"}
    if not is_primary_apple_chip_roadmap_title(text):
        return set()
    families = hardware_product_families_from_text(text)
    facets: set[str] = set()
    if "mac" in families:
        facets.add("mac-chip-roadmap")
    if "iphone" in families:
        facets.add("iphone-chip-roadmap")
    if "ipad" in families:
        facets.add("ipad-chip-roadmap")
    if not facets:
        facets.add("apple-chip-roadmap")
    return facets


def iphone_hardware_rumor_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    if score_terms(lower, ["iphone", "iphone 18", "iphone 18 pro", "iphone 18e", "iphone air", "苹果 iPhone".lower()]) <= 0:
        return set()
    facets: set[str] = set()
    if (
        score_terms(lower, ["a20", "a20 pro", "iphone 18 pro", "苹果 a20"]) > 0
        and score_terms(
            lower,
            [
                "wmcm",
                "motherboard",
                "logic board",
                "package",
                "packaging",
                "side-mounted",
                "side mounted",
                "dram has been moved",
                "主板",
                "封装",
                "内存旁置",
                "并排封装",
                "内存被放置",
            ],
        )
        > 0
    ):
        facets.add("iphone-chip-packaging")
    if score_terms(lower, ["vc", "vapor chamber", "cooling", "heat dissipation", "thermal", "均热板", "散热", "导热"]) > 0:
        facets.add("iphone-thermal-design")
    if score_terms(lower, ["launch date", "debut", "unveil", "event", "september", "gurman", "mark gurman", "发布时间", "发布会", "亮相", "古尔曼", "9 月", "九月"]) > 0:
        facets.add("iphone-launch-timing")
    if score_terms(lower, ["drop test", "drop-test", "drop tests", "drop testing", "drop-test photos", "跌落测试", "坠落测试"]) > 0:
        facets.add("iphone-drop-test-leak")
    if score_terms(lower, ["dynamic island", "face id", "ct scan", "cutout", "hole punch", "front camera", "灵动岛", "ct 扫描", "开孔", "前置摄像头"]) > 0:
        facets.add("iphone-front-cutout")
    if score_terms(lower, ["iphone air 2", "iphone air successor", "next iphone air", "苹果 iphone air 2", "air 2"]) > 0:
        facets.add("iphone-air-successor")
    if (
        score_terms(lower, ["ram", "memory", "9gb", "9 gb", "lpddr", "内存", "9gb 内存", "9gb内存"]) > 0
        and score_terms(lower, ["price", "prices", "涨价", "降回", "不会降", "售价"]) > 0
    ):
        facets.add("iphone-memory-price-forecast")
    if (
        score_terms(lower, ["ram", "memory", "9gb", "9 gb", "12gb", "12 gb", "内存", "9gb 内存", "9gb内存", "12gb 内存", "12gb内存"]) > 0
        and score_terms(lower, ["support", "supports", "won't support", "will not support", "feature", "features", "apple intelligence", "siri", "支持", "不支持", "功能"]) > 0
    ):
        facets.add("iphone-memory-feature-support")
    return facets


def broad_hardware_topic_bridge_only(article_facets: set[str], event_facets: set[str]) -> bool:
    shared = article_facets & event_facets
    if not shared:
        return False
    bridge_facets = {"apple-chip-roadmap", "iphone-chip-roadmap", "mac-chip-roadmap", "hardware-roadmap"}
    return bool(shared) and shared <= bridge_facets


def _topic_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    facets: set[str] = set()
    facets |= os_feature_component_facets_from_text(lower)
    facets |= os_release_facets_from_text(lower)
    if is_broad_apple_product_roadmap_story(lower):
        facets.add("apple-product-roadmap-list")
    if is_apple_company_org_change_story(lower):
        facets.add("apple-company-org-change")
    if is_apple_strategic_transaction_story(lower):
        facets.add("apple-strategic-transaction")
        facets |= strategic_transaction_counterparty_facets(lower)
    price_facets = apple_product_price_topic_facets(lower)
    facets |= price_facets
    if is_apple_restricted_memory_supplier_approval_story(lower):
        facets.add("apple-restricted-memory-supplier-approval")
    if is_apple_memory_supply_constraint_story(lower):
        facets.add("apple-memory-supply-constraint")
    data_leak_enforcement_story = is_apple_product_data_leak_enforcement_story(lower)
    data_leak_specs_story = is_apple_product_data_leak_specs_story(lower)
    data_leak_story = is_apple_product_data_leak_story(lower) or data_leak_enforcement_story or data_leak_specs_story
    if not data_leak_story:
        facets |= apple_chip_roadmap_facets_from_text(lower)
    facets |= iphone_hardware_rumor_facets_from_text(lower)
    if is_foldable_iphone_successor_roadmap_story(lower):
        facets.add("foldable-iphone-successor-roadmap")
    if is_foldable_iphone_supply_chain_story(lower):
        facets.add("foldable-iphone-supply-chain")
    if is_apple_display_panel_supply_chain_story(lower):
        facets.add("apple-display-panel-supply-chain")
    if is_brazil_app_store_policy_story(lower):
        facets.add("brazil-app-store-policy")
    if is_uk_cma_app_store_payment_nfc_story(lower):
        facets.add("uk-cma-app-store-payment-nfc")
    if is_siri_ai_eu_dma_regulatory_meeting_story(lower):
        facets.add("siri-ai-eu-dma-meeting")
    if is_epic_app_store_appeal_story(lower):
        facets.add("epic-app-store-appeal")
    if is_apple_pay_rewards_story(lower):
        facets.add("apple-pay-rewards")
    if is_bootrom_secure_rom_exploit_story(lower):
        facets.add("bootrom-secure-rom-exploit")
    if is_find_my_location_sharing_story(lower):
        facets.add("find-my-location-sharing")
    if is_airdrop_vulnerability_story(lower):
        facets.add("airdrop-vulnerability")
    if is_apple_creator_studio_story(lower):
        facets.add("apple-creator-studio")
    if is_iwork_apps_update_story(lower):
        facets.add("iwork-apps-update")
    if is_apple_watch_redesign_story(lower):
        facets.add("apple-watch-redesign")
    if is_official_apple_refurbished_product_story(lower):
        if score_terms(lower, ["iphone"]) > 0:
            facets.add("apple-refurbished-iphone")
        elif score_terms(lower, ["macbook", "mac"]) > 0:
            facets.add("apple-refurbished-mac")
        elif score_terms(lower, ["ipad"]) > 0:
            facets.add("apple-refurbished-ipad")
        else:
            facets.add("apple-refurbished-product")
    if is_apple_music_top_artists_chart_story(lower):
        facets.add("apple-music-top-artists")
    if is_vision_pro_spatial_experience_story(lower):
        facets.add("vision-pro-spatial-experience")
    if is_iphone_parts_factory_contamination_story(lower):
        facets.add("iphone-parts-factory-contamination")
    if data_leak_story:
        facets.add("apple-product-data-leak")
        if data_leak_enforcement_story:
            facets.add("apple-product-data-leak-enforcement")
        if data_leak_specs_story:
            facets.add("apple-product-data-leak-specs")
    if is_apple_specific_market_share_report_story(lower):
        facets.add("apple-market-share-report")
    if (
        score_terms(lower, ["beats"]) > 0
        and score_terms(lower, ["headphone", "headphones", "earbuds", "耳机", "耳罩"]) > 0
    ):
        facets.add("beats-headphones")
    if is_iphone_color_mockup_or_finish_rumor(lower):
        facets.add("iphone-color-mockup")
    if (
        score_terms(lower, ["iphone air 2", "iphone air successor", "next iphone air", "苹果 iPhone Air 2"]) > 0
        and score_terms(
            lower,
            [
                "dual lens",
                "dual-lens",
                "two cameras",
                "a20",
                "advanced testing",
                "spring 2027",
                "successor",
                "双摄",
                "超广角",
                "高级测试",
                "明年春季",
                "春季发售",
            ],
        )
        > 0
    ):
        facets.add("iphone-air-successor")
    if (
        (
            score_terms(lower, ["foldable iphone", "iphone fold", "iphone ultra", "折叠屏 iphone", "折叠屏手机", "折叠 iphone"]) > 0
            or (
                score_terms(lower, ["iphone"]) > 0
                and score_terms(lower, ["foldable", "fold", "折叠屏", "折叠"]) > 0
            )
        )
        and score_terms(
            lower,
            [
                "render",
                "renders",
                "rendering",
                "jon prosser",
                "prosser",
                "usb-c",
                "camera control",
                "7.8-inch",
                "7.8 英寸",
                "5800mah",
                "5800 mah",
                "9mm",
                "prototype",
                "mockup",
                "dummy",
                "hinge",
                "渲染图",
                "机模",
                "样机",
                "爆料人",
                "相机控制按钮",
                "接口",
                "扬声器格栅",
                "无痕铰链",
                "侧边指纹",
            ],
        )
        > 0
    ):
        facets.add("foldable-iphone-render-leak")
    if is_apple_developer_tool_story(lower):
        facets.add("developer-tool-integration")
    if app_store_policy_score(lower) > 0:
        facets.add("app-store-policy")
    if (
        score_terms(lower, ["app store", "应用商店"]) > 0
        and score_terms(
            lower,
            [
                "subscription",
                "subscriptions",
                "subscription bundle",
                "subscription bundles",
                "bundle",
                "bundles",
                "suite",
                "suites",
                "in-app purchase",
                "auto-renewable",
                "订阅",
                "捆绑",
                "套装",
                "应用内购买",
            ],
        )
        > 0
    ):
        facets.add("app-store-subscriptions")
    if score_terms(lower, ["apple arcade", "苹果 arcade"]) > 0:
        facets.add("apple-arcade")
    if score_terms(lower, ["apple music", "music app", "苹果音乐"]) > 0:
        facets.add("apple-music")
    if is_apple_tv_hardware_story(lower):
        facets.add("apple-tv-hardware")
    elif (
        score_terms(lower, ["apple tv", "苹果电视"]) > 0
        and score_terms(lower, ["remote", "siri remote", "home screen", "遥控器", "主屏幕"]) > 0
    ):
        facets.add("apple-tv-remote")
    elif not price_facets and score_terms(lower, ["apple tv", "apple tv+", "苹果电视"]) > 0:
        facets.add("apple-tv-content")
    if (
        score_terms(lower, ["pull-to-refresh", "swipe down to refresh", "refresh gesture", "下拉刷新"]) > 0
        and score_terms(lower, ["macos", "mac"]) > 0
    ):
        facets.add("macos-pull-refresh")
    if (
        score_terms(
            lower,
            [
                "performance",
                "smoothness",
                "fluidity",
                "responsive",
                "responsiveness",
                "lag",
                "lags",
                "stutter",
                "stuttering",
                "slowdown",
                "slowdowns",
                "snappier",
                "user feedback",
                "reddit",
                "流畅度",
                "流畅",
                "卡顿",
                "掉帧",
                "反应迟缓",
                "响应速度",
                "用户反馈",
                "社区用户",
                "像是换了台",
            ],
        )
        > 0
        and score_terms(lower, ["macos", "mac"]) > 0
    ):
        facets.add("macos-performance-feedback")
    if (
        score_terms(lower, ["sidecar", "direct touch", "touch input", "随航", "直接触控", "触控输入"]) > 0
        and score_terms(lower, ["macos", "ipados", "ipad", "mac"]) > 0
    ):
        facets.add("sidecar-touch")
    if (
        score_terms(lower, ["iphone mirroring", "resize", "window size", "iphone 镜像", "窗口", "调整大小"]) > 0
        and score_terms(lower, ["macos", "iphone"]) > 0
    ):
        facets.add("iphone-mirroring")
    if is_macos_terminal_paste_security_story(lower):
        facets.add("macos-terminal-paste-protection")
    if (
        score_terms(lower, ["menu icon", "menu icons", "menu bar", "菜单图标", "无图标菜单"]) > 0
        and score_terms(lower, ["macos", "mac"]) > 0
    ):
        facets.add("macos-menu-icons")
    if (
        score_terms(lower, ["adoption rate", "adoption rates", "install rate", "install rates", "installed on", "采用率", "安装率", "装机率"]) > 0
        and score_terms(lower, ["ios", "ipados", "macos", "watchos", "visionos", "iphone", "ipad"]) > 0
    ):
        facets.add("os-adoption")
    if (
        score_terms(lower, ["airpods"]) > 0
        and score_terms(lower, ["firmware", "beta firmware", "测试版固件", "固件"]) > 0
    ):
        facets.add("airpods-firmware")
    if (
        score_terms(lower, ["wallpaper", "壁纸"]) > 0
        and score_terms(lower, ["ai", "apple intelligence", "extend", "expansion", "扩图", "扩展"]) > 0
    ):
        facets.add("ai-wallpaper")
    elif (
        score_terms(lower, ["wallpaper", "celosia", "壁纸"]) > 0
        and score_terms(lower, ["ios", "ipados", "macos", "carplay", "system", "系统"]) > 0
    ):
        facets.add("system-wallpaper")
    if (
        score_terms(lower, ["siri", "apple intelligence", "ai credibility", "ai strategy", "ai 可信度", "人工智能"]) > 0
        and score_terms(lower, ["wwdc", "ios", "ipados", "macos", "watchos", "visionos", "生态系统", "ecosystem"]) > 0
    ):
        facets.add("apple-ai-platform")
    if (
        score_terms(lower, ["app store", "应用商店"]) > 0
        and score_terms(
            lower,
            [
                "app discovery",
                "discover",
                "discovery",
                "personalized recommendation",
                "personalized recommendations",
                "recommendation",
                "recommendations",
                "search",
                "应用发现",
                "个性化推荐",
                "推荐",
                "搜索",
                "获客",
            ],
        )
        > 0
    ):
        facets.add("app-store-discovery")
    if (
        score_terms(lower, ["compatibility", "compatible", "support", "drop support", "not support", "兼容", "支持", "无缘"]) > 0
        and score_terms(lower, ["ios", "ipados", "macos", "watchos", "visionos"]) > 0
    ):
        facets.add("os-compatibility")
    if (
        score_terms(lower, ["touch macbook", "touchscreen macbook", "touch-screen macbook", "触控 macbook"]) > 0
        or (
            score_terms(lower, ["macbook ultra", "macbook"]) > 0
            and score_terms(lower, ["touch", "touchscreen", "touch-screen", "oled", "dynamic island", "m6", "触控", "灵动岛"]) > 0
        )
    ):
        facets.add("macbook-touch-roadmap")
    if (
        not price_facets
        and
        score_terms(lower, ["macbook", "macbook neo", "macbook air", "macbook pro"]) > 0
        and score_terms(
            lower,
            [
                "memory",
                "ram",
                "12gb",
                "16gb",
                "24gb",
                "local ai",
                "local model",
                "on-device ai",
                "on-device model",
                "afm",
                "core advanced",
                "内存",
                "本地 ai",
                "本地模型",
                "端侧",
                "容量",
            ],
        )
        > 0
    ):
        facets.add("macbook-memory-ai")
    if (
        score_terms(lower, ["macbook", "macbook pro"]) > 0
        and score_terms(
            lower,
            [
                "overheat",
                "overheating",
                "thermal",
                "heat",
                "screen discoloration",
                "discoloration",
                "color distortion",
                "hardware fault",
                "高负载",
                "过热",
                "发热",
                "屏幕变色",
                "颜色失真",
                "色偏",
                "故障",
            ],
        )
        > 0
    ):
        facets.add("macbook-thermal-defect")
    if score_terms(lower, ["macbook ultra", "foldable iphone", "dynamic island", "oled", "m6", "触控 macbook", "折叠 iphone", "灵动岛"]) > 0:
        facets.add("hardware-roadmap")
    if is_apple_wallet_feature_story(lower):
        facets.add("apple-wallet")
        if score_terms(
            lower,
            [
                "digital id",
                "passport",
                "identity verification",
                "nationality verification",
                "数字身份证",
                "数字身份",
                "身份凭证",
                "身份核验",
                "国籍校验",
                "护照",
            ],
        ) > 0:
            facets.add("apple-wallet-digital-id")
    if score_terms(lower, ["call context", "phone app", "customer service calls", "通话", "来电", "订单号"]) > 0:
        facets.add("phone-call-context")
    return facets


@lru_cache(maxsize=4096)
def cached_topic_facets_from_text(text: str) -> frozenset[str]:
    return frozenset(_topic_facets_from_text(text))


def topic_facets_from_text(text: str) -> set[str]:
    return set(cached_topic_facets_from_text(text))


def _merge_guard_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    facets: set[str] = set()
    facets |= os_feature_component_facets_from_text(lower)
    facets |= os_release_facets_from_text(lower)
    if is_broad_apple_product_roadmap_story(lower):
        facets.add("apple-product-roadmap-list")
    if is_apple_company_org_change_story(lower):
        facets.add("apple-company-org-change")
    facets |= apple_product_price_topic_facets(lower)
    if is_apple_restricted_memory_supplier_approval_story(lower):
        facets.add("apple-restricted-memory-supplier-approval")
    if is_apple_memory_supply_constraint_story(lower):
        facets.add("apple-memory-supply-constraint")
    data_leak_enforcement_story = is_apple_product_data_leak_enforcement_story(lower)
    data_leak_specs_story = is_apple_product_data_leak_specs_story(lower)
    data_leak_story = is_apple_product_data_leak_story(lower) or data_leak_enforcement_story or data_leak_specs_story
    if data_leak_story:
        facets.add("apple-product-data-leak")
        if data_leak_enforcement_story:
            facets.add("apple-product-data-leak-enforcement")
        if data_leak_specs_story:
            facets.add("apple-product-data-leak-specs")
    if is_apple_specific_market_share_report_story(lower):
        facets.add("apple-market-share-report")
    if is_brazil_app_store_policy_story(lower):
        facets.add("brazil-app-store-policy")
    if is_uk_cma_app_store_payment_nfc_story(lower):
        facets.add("uk-cma-app-store-payment-nfc")
    if is_siri_ai_eu_dma_regulatory_meeting_story(lower):
        facets.add("siri-ai-eu-dma-meeting")
    if is_epic_app_store_appeal_story(lower):
        facets.add("epic-app-store-appeal")
    if is_apple_pay_rewards_story(lower):
        facets.add("apple-pay-rewards")
    if is_airdrop_vulnerability_story(lower):
        facets.add("airdrop-vulnerability")
    if is_apple_creator_studio_story(lower):
        facets.add("apple-creator-studio")
    if is_iwork_apps_update_story(lower):
        facets.add("iwork-apps-update")
    if is_apple_watch_redesign_story(lower):
        facets.add("apple-watch-redesign")
    if is_official_apple_refurbished_product_story(lower):
        if score_terms(lower, ["iphone"]) > 0:
            facets.add("apple-refurbished-iphone")
        elif score_terms(lower, ["macbook", "mac"]) > 0:
            facets.add("apple-refurbished-mac")
        elif score_terms(lower, ["ipad"]) > 0:
            facets.add("apple-refurbished-ipad")
        else:
            facets.add("apple-refurbished-product")
    if not data_leak_story:
        facets |= apple_chip_roadmap_facets_from_text(lower)
    facets |= iphone_hardware_rumor_facets_from_text(lower)
    if is_foldable_iphone_successor_roadmap_story(lower):
        facets.add("foldable-iphone-successor-roadmap")
    if is_foldable_iphone_supply_chain_story(lower):
        facets.add("foldable-iphone-supply-chain")
    platform_groups = {
        "platform-ios": ["ios", "iphone"],
        "platform-ipados": ["ipados", "ipad"],
        "platform-macos": ["macos", "mac"],
        "platform-watchos": ["watchos", "apple watch"],
        "platform-tvos": ["tvos", "apple tv"],
        "platform-visionos": ["visionos", "vision pro"],
    }
    for facet, terms in platform_groups.items():
        if score_terms(lower, terms) > 0:
            facets.add(facet)
    if facets & {"platform-ios", "platform-ipados"}:
        facets.add("platform-mobile-os")
    if score_terms(lower, OS_SUMMARY_TERMS) > 0 and facets:
        facets.add("system-summary")
    component_action_facets = {
        facet
        for facet in facets
        if not facet.startswith("platform-") and facet != "system-performance-optimization"
    }
    if (
        score_terms(lower, OS_FEATURE_ACTION_TERMS) > 0
        and score_terms(lower, ["app", "application", "built-in app", "messages app", "phone app", "walkie-talkie", "应用", "内置应用", "对讲机"]) > 0
        and component_action_facets
    ):
        facets.add("built-in-app-change")
    if (
        score_terms(lower, ["input method", "keyboard", "typing", "输入法", "键盘", "联想词", "标点", "生僻字"]) > 0
        and facets
    ):
        facets.add("input-method-change")
    if is_apple_developer_tool_story(lower):
        facets.add("developer-tool-integration")
    return facets


@lru_cache(maxsize=4096)
def cached_merge_guard_facets_from_text(text: str) -> frozenset[str]:
    return frozenset(_merge_guard_facets_from_text(text))


def merge_guard_facets_from_text(text: str) -> set[str]:
    return set(cached_merge_guard_facets_from_text(text))


BROAD_TOPIC_FACETS = {"os-compatibility", "hardware-roadmap"}
LOW_CONFIDENCE_MERGE_FACETS = {"apple-ai-platform"}
IPHONE_HARDWARE_RUMOR_TOPIC_FACETS = {
    "iphone-air-successor",
    "iphone-chip-packaging",
    "iphone-drop-test-leak",
    "iphone-front-cutout",
    "iphone-launch-timing",
    "iphone-memory-feature-support",
    "iphone-memory-price-forecast",
    "iphone-thermal-design",
}
SPLITTABLE_HARDWARE_TOPIC_FACETS = {
    "apple-company-org-change",
    *APPLE_PRICE_SUBTOPIC_FACETS,
    "apple-display-panel-supply-chain",
    "apple-product-data-leak",
    "apple-product-data-leak-enforcement",
    "apple-product-data-leak-specs",
    "apple-product-price-increase",
    "apple-refurbished-iphone",
    "apple-refurbished-ipad",
    "apple-refurbished-mac",
    "apple-refurbished-product",
    "apple-tv-hardware",
    "apple-watch-redesign",
    "beats-headphones",
    "foldable-iphone-render-leak",
    "foldable-iphone-successor-roadmap",
    "foldable-iphone-supply-chain",
    *IPHONE_HARDWARE_RUMOR_TOPIC_FACETS,
    "iphone-color-mockup",
    "macbook-memory-ai",
    "macbook-thermal-defect",
    "macbook-touch-roadmap",
    "apple-chip-roadmap",
    "apple-chip-process-roadmap",
    "apple-memory-supply-constraint",
    "ipad-chip-roadmap",
    "iphone-chip-roadmap",
    "mac-chip-roadmap",
    "apple-market-share-report",
    "vision-pro-spatial-experience",
}
SPLITTABLE_SERVICE_TOPIC_FACETS = {
    "apple-arcade",
    "apple-creator-studio",
    "apple-music",
    "apple-tv-content",
    "iwork-apps-update",
}
SPLITTABLE_POLICY_TOPIC_FACETS = APP_STORE_POLICY_SUBTOPIC_FACETS | {
    "airdrop-vulnerability",
}
SPLITTABLE_TOPIC_FACETS = SPLITTABLE_HARDWARE_TOPIC_FACETS | SPLITTABLE_SERVICE_TOPIC_FACETS | SPLITTABLE_POLICY_TOPIC_FACETS
BRIDGE_SPLIT_TOPIC_FACETS = {"apple-chip-roadmap", "iphone-chip-roadmap", "mac-chip-roadmap", "hardware-roadmap"}
NO_SPLIT_SHARED_CORE_TOPIC_FACETS = {
    "apple-product-data-leak",
}
TITLE_DOMINANT_TOPIC_FACETS = {
    "apple-refurbished-iphone",
    "apple-refurbished-ipad",
    "apple-refurbished-mac",
    "apple-refurbished-product",
    "foldable-iphone-render-leak",
    "iphone-air-successor",
    "iphone-color-mockup",
    "iphone-drop-test-leak",
}
DATA_LEAK_ENFORCEMENT_OBJECT_FACETS = {
    "iphone-color-mockup",
    "iphone-drop-test-leak",
}


def primary_topic_facets(title: str, summary: str = "") -> set[str]:
    title_facets = topic_facets_from_text(title)
    combined_facets = topic_facets_from_text(f"{title} {summary}")
    data_leak_detail_facets = {"apple-product-data-leak-enforcement", "apple-product-data-leak-specs"}
    if "apple-product-data-leak-enforcement" in title_facets:
        enforcement_facets = title_facets - DATA_LEAK_ENFORCEMENT_OBJECT_FACETS
        return enforcement_facets or title_facets
    if title_facets & TITLE_DOMINANT_TOPIC_FACETS:
        dominant_facets = title_facets - data_leak_detail_facets - {"apple-product-data-leak"}
        return dominant_facets or title_facets
    if title_facets & data_leak_detail_facets:
        return title_facets
    if combined_facets & data_leak_detail_facets:
        return combined_facets
    if "app-store-policy" in title_facets and "brazil-app-store-policy" in combined_facets:
        return combined_facets
    if combined_facets & APP_STORE_POLICY_SUBTOPIC_FACETS:
        return combined_facets
    if "apple-restricted-memory-supplier-approval" in combined_facets:
        return combined_facets
    if "visionos-m5-ai-features" in combined_facets:
        return combined_facets
    if "apple-product-price-increase" in title_facets:
        combined_price_details = price_detail_facets(combined_facets)
        title_price_details = price_detail_facets(title_facets)
        if combined_price_details and not title_price_details:
            return title_facets | combined_price_details
    if title_facets and (title_facets - BROAD_TOPIC_FACETS):
        return title_facets
    return combined_facets or title_facets


def primary_merge_guard_facets(title: str, summary: str = "") -> set[str]:
    title_facets = merge_guard_facets_from_text(title)
    combined_facets = merge_guard_facets_from_text(f"{title} {summary}")
    if "apple-restricted-memory-supplier-approval" in combined_facets:
        return combined_facets
    if "apple-product-price-increase" in title_facets:
        combined_price_details = price_detail_facets(combined_facets)
        title_price_details = price_detail_facets(title_facets)
        if combined_price_details and not title_price_details:
            return title_facets | combined_price_details
    if title_facets and merge_guard_action_facets(title_facets):
        return title_facets
    return combined_facets or title_facets


def article_primary_facets(article: Article) -> set[str]:
    return primary_topic_facets(article.title, article.summary)


def event_primary_facets(event: Event) -> set[str]:
    facets: set[str] = set()
    for article in event.articles:
        facets |= article_primary_facets(article)
    return facets


def article_splittable_topic_facets(article: Article) -> set[str]:
    facets = effective_topic_facets(article_primary_facets(article))
    splittable = facets & SPLITTABLE_TOPIC_FACETS
    specific = splittable - BRIDGE_SPLIT_TOPIC_FACETS
    return specific or splittable


def independent_splittable_topic_facets(facets: set[str]) -> set[str]:
    iphone_rumor_boundary_facets = IPHONE_HARDWARE_RUMOR_TOPIC_FACETS | {
        "apple-product-data-leak",
        "apple-product-data-leak-enforcement",
        "apple-product-data-leak-specs",
        "apple-refurbished-iphone",
        "apple-refurbished-ipad",
        "apple-refurbished-mac",
        "apple-refurbished-product",
        "foldable-iphone-render-leak",
        "foldable-iphone-successor-roadmap",
        "iphone-color-mockup",
    }
    return facets & iphone_rumor_boundary_facets


def splittable_topic_facets_compatible(left_facets: set[str], right_facets: set[str]) -> bool:
    left = independent_splittable_topic_facets(effective_topic_facets(left_facets))
    right = independent_splittable_topic_facets(effective_topic_facets(right_facets))
    if not left or not right:
        return True
    shared = left & right
    if not shared:
        return False
    if left == right:
        return True
    if "iphone-air-successor" in shared:
        return True
    if "apple-product-data-leak" in left or "apple-product-data-leak" in right:
        leak_detail_facets = {
            "apple-product-data-leak-enforcement",
            "apple-product-data-leak-specs",
            "iphone-chip-packaging",
            "iphone-drop-test-leak",
        }
        if (left & leak_detail_facets) or (right & leak_detail_facets):
            return bool((left & leak_detail_facets) and (right & leak_detail_facets) and (left & right & leak_detail_facets))
        allowed_data_leak_facets = {"apple-product-data-leak", *leak_detail_facets}
        return bool(shared) and left <= allowed_data_leak_facets and right <= allowed_data_leak_facets
    if len(left) > 1 or len(right) > 1:
        return False
    return True


def app_store_policy_subtopic_facets_compatible(left_facets: set[str], right_facets: set[str]) -> bool:
    left = effective_topic_facets(left_facets) & APP_STORE_POLICY_SUBTOPIC_FACETS
    right = effective_topic_facets(right_facets) & APP_STORE_POLICY_SUBTOPIC_FACETS
    if not left or not right:
        return True
    return bool(left & right)


def event_splittable_topic_facets(event: Event) -> set[str]:
    facets: set[str] = set()
    for article in event.articles:
        facets |= article_splittable_topic_facets(article)
    return facets


def article_merge_guard_facets(article: Article) -> set[str]:
    return primary_merge_guard_facets(article.title, article.summary)


def event_merge_guard_facets(event: Event) -> set[str]:
    facets: set[str] = set()
    for article in event.articles:
        facets |= article_merge_guard_facets(article)
    return facets


def effective_topic_facets(facets: set[str]) -> set[str]:
    specific = facets - BROAD_TOPIC_FACETS
    return specific or facets


def merge_guard_platform_facets(facets: set[str]) -> set[str]:
    return {facet for facet in facets if facet.startswith("platform-")}


def merge_guard_action_facets(facets: set[str]) -> set[str]:
    return facets - merge_guard_platform_facets(facets)


def merge_guard_facets_compatible(article_facets: set[str], event_facets: set[str]) -> bool:
    if not article_facets or not event_facets:
        return True
    if not (article_facets & event_facets):
        return False
    if not os_release_facets_compatible(article_facets, event_facets):
        return False
    if not strategic_transaction_facets_compatible(article_facets, event_facets):
        return False
    if not app_store_policy_subtopic_facets_compatible(article_facets, event_facets):
        return False
    if not restricted_memory_supplier_approval_facets_compatible(article_facets, event_facets):
        return False
    article_release_versions = os_release_version_facets(article_facets)
    event_release_versions = os_release_version_facets(event_facets)
    article_release_channels = os_release_channel_facets(article_facets)
    event_release_channels = os_release_channel_facets(event_facets)
    if (
        article_release_versions
        and event_release_versions
        and article_release_versions & event_release_versions
        and article_release_channels
        and event_release_channels
        and article_release_channels & event_release_channels
    ):
        return True
    article_platforms = merge_guard_platform_facets(article_facets)
    event_platforms = merge_guard_platform_facets(event_facets)
    article_actions = merge_guard_action_facets(article_facets)
    event_actions = merge_guard_action_facets(event_facets)
    if (article_actions & event_actions) & {"apple-product-price-increase"}:
        return price_facets_compatible(article_actions, event_actions)
    if len(article_platforms) > 2 and event_platforms and article_platforms != event_platforms:
        return False
    if len(event_platforms) > 2 and article_platforms and article_platforms != event_platforms:
        return False
    if article_actions and not (article_actions & event_actions):
        return False
    if event_actions and not (article_actions & event_actions):
        return False
    return True


def detect_event_kind(title: str, summary: str, key_facts: list[str] | None = None) -> str:
    facts = " ".join(key_facts or [])
    text = f"{title} {summary} {facts}"
    lower = text.lower()
    title_lower = title.lower()
    if is_competitor_launch_against_apple_story(title, text):
        return "third_party_ecosystem"
    if is_siri_ai_eu_dma_regulatory_meeting_story(text):
        return "regional_regulation"
    if is_epic_app_store_appeal_story(text):
        return "legal_antitrust"
    if is_third_party_financial_service_with_apple_pay_support(title, text):
        return "third_party_ecosystem"
    if "iphone-color-mockup" in topic_facets_from_text(f"{title} {summary}"):
        return "hardware_market"
    if (
        score_terms(lower, ["airdrop", "隔空投送"]) > 0
        and score_terms(
            lower,
            ["quick share", "nearby share", "google", "pixel", "android", "cross-platform", "interoperability", "谷歌", "安卓", "互通"],
        )
        > 0
    ):
        return "ecosystem_interop"
    if is_third_party_platform_update_improving_apple_device_interop(title, text):
        return "ecosystem_interop"
    if is_apple_online_store_status_story(title, text):
        return "retail_store"
    if is_official_apple_refurbished_product_story(text):
        return "retail_store"
    if is_apple_pay_rewards_story(text):
        return "wallet_feature"
    if score_terms(lower, ["apple arcade", "苹果 arcade"]) > 0:
        return "service_content"
    if is_uk_cma_app_store_payment_nfc_story(text):
        return "regional_regulation"
    if is_airdrop_vulnerability_story(text):
        return "security_privacy"
    if is_apple_creator_studio_story(text):
        return "os_app"
    if is_iwork_apps_update_story(text):
        return "os_app"
    if is_brazil_app_store_policy_story(text):
        return "app_store_trust"
    if is_apple_books_or_store_platform_trust_story(title, text):
        return "app_store_trust"
    if is_non_apple_primary_subject_with_incidental_apple_context(title, text):
        return "third_party_ecosystem"
    if is_former_apple_staff_background_story(text):
        return "third_party_ecosystem"
    if is_legacy_apple_platform_third_party_app_story(title, text):
        return "third_party_ecosystem"
    if is_third_party_legacy_apple_hardware_replica_story(title, text):
        return "third_party_ecosystem"
    if is_third_party_app_or_service_status_story(title, text):
        return "third_party_ecosystem"
    if is_routine_third_party_apple_platform_story(title):
        return "third_party_ecosystem"
    if is_third_party_platform_availability_candidate(title):
        return "third_party_ecosystem"
    if is_third_party_accessory_platform_compatibility_story(title, text):
        return "third_party_ecosystem"
    if is_third_party_app_platform_launch_story(title, text):
        return "third_party_ecosystem"
    if is_apple_product_price_increase_story(text, title):
        return "hardware_market"
    if is_apple_product_data_leak_story(text, title) and not is_apple_support_security_guidance_story(title, text):
        return "hardware_market"
    if is_apple_company_org_change_story(text):
        return "company_org"
    if is_apple_executive_company_story(text):
        if score_terms(lower, ["services", "apple tv", "apple tv+", "apple music", "app store", "icloud", "streaming", "服务主管", "苹果电视", "苹果音乐"]) > 0:
            return "service_content"
        return "company_org"
    if is_apple_support_security_guidance_story(title, text):
        return "security_privacy"
    if is_messages_platform_candidate(text):
        return "messages_platform"
    if is_non_apple_vendor_response_to_apple_product_story(title, text):
        return "third_party_ecosystem"
    if is_competitor_or_company_story_using_apple_as_benchmark(title, text):
        return "third_party_ecosystem"
    if is_multi_vendor_chip_or_phone_roadmap_background_story(title, text):
        return "third_party_ecosystem"
    if is_competitor_display_panel_story_using_apple_as_background(title, text):
        return "third_party_ecosystem"
    if is_apple_product_price_increase_story(text, title):
        return "hardware_market"
    if is_apple_product_data_leak_story(text, title):
        return "hardware_market"
    if os_release_facets_from_text(text):
        return "os_app"
    if is_apple_product_commentary_analysis_without_new_reporting(title, text):
        return "general_company"
    if is_direct_apple_hardware_roadmap_story(text, title):
        return "hardware_market"
    if is_apple_os_feature_or_summary_story(text) and score_terms(lower, OS_SUMMARY_TERMS) > 0:
        return "os_app"
    if is_apple_wallet_feature_story(text) and score_terms(
        title_lower,
        ["apple wallet", "wallet", "digital id", "digital-id", "钱包", "数字身份证", "数字身份", "身份核验"],
    ) > 0:
        return "wallet_feature"
    if is_title_primary_software_system_story(title, text):
        return "os_app"
    if app_store_policy_score(lower) > 0:
        return "app_store_trust"
    if is_routine_third_party_apple_platform_story(text):
        return "third_party_ecosystem"
    if is_third_party_platform_availability_candidate(text):
        return "third_party_ecosystem"
    if is_apple_display_panel_supply_chain_story(text) or is_foldable_iphone_supply_chain_story(text):
        return "hardware_market"
    if is_third_party_surveillance_context_story(text) or is_third_party_device_management_service_story(text):
        return "third_party_ecosystem"
    if is_routine_recap_comparison_or_buying_advice(title, text):
        return "general_company"
    if is_apple_tv_hardware_story(text):
        return "hardware_market"
    if is_apple_hardware_product_launch_story(text, title):
        return "hardware_market"
    if is_apple_executive_company_story(text):
        if score_terms(lower, ["services", "apple tv", "apple tv+", "apple music", "app store", "icloud", "streaming", "服务", "苹果电视", "苹果音乐"]) > 0:
            return "service_content"
        return "general_company"
    if is_apple_car_asset_story(text):
        return "hardware_market"
    if is_apple_strategic_transaction_story(text):
        return "general_company"
    if is_messages_platform_candidate(text):
        return "messages_platform"
    if is_apple_os_feature_or_summary_story(text) and score_terms(lower, OS_SUMMARY_TERMS) > 0:
        return "os_app"
    if is_apple_wallet_feature_story(text):
        return "wallet_feature"
    if is_apple_os_feature_or_summary_story(text):
        return "os_app"
    if is_routine_third_party_apple_platform_story(text):
        return "third_party_ecosystem"
    if is_third_party_accessory_platform_compatibility_story(title, text):
        return "third_party_ecosystem"
    if is_apple_developer_tool_story(text):
        return "developer_tool"
    if is_official_apple_accessory_market_story(text):
        return "hardware_market"
    if is_unreleased_beats_hardware_story(text):
        return "hardware_market"
    if is_carplay_platform_feature_story(text):
        return "os_app"
    if is_third_party_benchmark_comparison_story(text):
        return "third_party_ecosystem"
    if "visionos-m5-ai-features" in topic_facets_from_text(text):
        return "os_app"
    if is_iphone_parts_factory_contamination_story(text):
        return "hardware_market"
    if is_broad_apple_product_roadmap_story(text):
        return "hardware_market"
    if is_apple_health_data_research_candidate(text):
        return "health_research"
    if is_apple_research_candidate(text):
        return "apple_research"
    if is_messages_platform_candidate(text):
        return "messages_platform"
    if is_service_content_story(text):
        return "service_content"
    if app_store_policy_score(lower) > 0:
        return "app_store_trust"
    if is_third_party_platform_availability_candidate(text):
        return "third_party_ecosystem"
    if is_third_party_xr_smart_glasses_context_story(text):
        return "third_party_ecosystem"
    if "iphone-mirroring" in topic_facets_from_text(text):
        return "os_app"
    if is_macos_terminal_paste_security_story(text):
        return "security_privacy"
    if is_third_party_security_software_promo_story(text):
        return "third_party_ecosystem"
    if is_apple_os_support_compatibility_story(text):
        return "os_compatibility"
    if (
        score_terms(lower, ["rosetta", "rosetta 2", "intel app", "intel apps", "intel-built", "intel-compiled", "英特尔架构应用", "intel 架构应用"]) > 0
        and score_terms(lower, ["macos", "mac", "support", "end", "remove", "淘汰", "提醒", "支持", "无法运行", "未来"]) > 0
    ):
        return "os_compatibility"
    if (
        score_terms(title_lower, ["ios", "ipados", "macos", "watchos", "tvos", "visionos", "系统"]) > 0
        and score_terms(title_lower, OS_FEATURE_ACTION_TERMS) > 0
    ):
        return "os_app"
    if (
        score_terms(lower, ["thread", "matter", "homekit", "smart home", "home app", "tvos", "homepod", "智能家居", "家庭 app"]) > 0
        and score_terms(lower, ["apple tv", "tvos", "homepod", "homekit", "苹果电视", "苹果"]) > 0
        and score_terms(lower, OS_FEATURE_ACTION_TERMS + POSITIVE_ACTION_TERMS) > 0
    ):
        return "os_app"
    if score_terms(lower, ["age assurance", "age verification", "child safety", "state law", "texas", "年龄验证", "儿童安全"]) > 0:
        return "regional_regulation"
    if score_terms(lower, ["antitrust", "competition regulator", "cci", "doj", "subpoena", "lawsuit", "court", "investigation", "probe", "反垄断", "司法部", "传票", "法院", "监管调查"]) > 0:
        return "legal_antitrust"
    if score_terms(lower, ["developer center", "developer academy", "developer lab", "开发者中心", "开发者学院"]) > 0:
        return "developer_program"
    if "macos-performance-feedback" in topic_facets_from_text(text):
        return "os_app"
    if (
        score_terms(lower, ["vision pro"]) > 0
        and score_terms(lower, ["app", "application", "native app", "free app", "应用", "原生应用", "免费应用"]) > 0
        and score_terms(lower, ["apple releases", "apple launches", "apple announces", "苹果发布", "苹果推出", "苹果宣布"]) == 0
    ):
        return "third_party_ecosystem"
    if score_terms(lower, ["privacy", "security", "vulnerability", "exploit", "mythos", "data protection", "隐私", "安全", "漏洞"]) > 0:
        return "security_privacy"
    if score_terms(lower, ["ad", "advertisement", "campaign", "commercial", "广告", "营销"]) > 0:
        return "marketing_ad"
    if is_service_content_story(text):
        return "service_content"
    if (
        score_terms(lower, ["apple store", "retail store", "store closure", "store closures", "store opening", "opens store", "零售店", "苹果店"]) > 0
        and score_terms(lower, ["app store"]) == 0
    ):
        return "retail_store"
    if score_terms(lower, ["vision products", "vision pro series", "smart glasses", "ai glasses", "product roadmap", "roadmap", "产品路线图", "智能眼镜"]) > 0:
        return "hardware_market"
    if (
        score_terms(lower, ["iphone", "iphones", "ipad", "ipads", "mac", "macs", "macbook", "macbooks", "imac", "imacs"]) > 0
        and score_terms(lower, ["support", "compatible", "compatibility", "drop support", "not support", "won't support", "不支持", "兼容", "无缘"]) > 0
        and score_terms(lower, ["ios", "ipados", "macos", "software", "系统"]) > 0
    ):
        return "os_compatibility"
    if (
        score_terms(lower, ["iphone", "ipad", "apple watch"]) > 0
        and score_terms(
            lower,
            [
                "carrier",
                "cellular data",
                "data plan",
                "unlimited data",
                "monthly plan",
                "wireless carrier",
                "network",
                "运营商",
                "蜂窝数据",
                "流量套餐",
                "无限流量",
            ],
        )
        > 0
    ):
        return "hardware_market"
    if (
        score_terms(lower, ["iphone", "ipad", "mac", "macbook", "airpods", "apple watch", "vision pro"]) > 0
        and score_terms(lower, ["launch", "launches", "coming", "rumor", "rumors", "reportedly", "新品", "发布", "推出", "传闻"]) > 0
        and score_terms(lower, ["ios", "ipados", "macos", "watchos", "visionos"]) == 0
    ):
        return "hardware_market"
    if score_terms(lower, ["shipment", "shipments", "market share", "counterpoint", "supplier", "production", "manufacturing", "factory", "chip", "modem", "出货", "份额", "供应", "量产", "生产", "芯片"]) > 0:
        return "hardware_market"
    if score_terms(lower, ["ios", "ipados", "macos", "watchos", "visionos", "safari", "siri", "apple wallet", "app store", "apple card", "apple pay", "airdrop", "imessage", "messages app", "系统", "应用商店"]) > 0:
        return "os_app"
    if score_terms(lower, ["google", "nvidia", "microsoft", "meta", "samsung", "wechat", "harmonyos", "third-party", "app for vision pro", "vision pro app", "英伟达", "微信", "鸿蒙", "第三方"]) > 0:
        return "third_party_ecosystem"
    return "general_company"


def classify_relevance_tier(
    title: str,
    summary: str,
    key_facts: list[str] | None = None,
    source_name: str = "",
) -> tuple[str, str]:
    facts = " ".join(key_facts or [])
    text = f"{title} {summary} {facts}"
    lower = text.lower()
    event_kind = detect_event_kind(title, summary, key_facts)
    apple_score = effective_apple_term_score(text)
    title_apple_score = effective_apple_term_score(title)
    third_party_score = score_terms(
        lower,
        [
            "google",
            "pixel",
            "android",
            "nvidia",
            "amd",
            "huawei",
            "vivo",
            "mediatek",
            "dimensity",
            "microsoft",
            "meta",
            "samsung",
            "suno",
            "wechat",
            "harmonyos",
            "third-party",
            "app for vision pro",
            "vision pro app",
            "xiaomi",
            "lm studio",
            "locally app",
            "local model",
            "local models",
            "llm",
            "llms",
            "cirrus",
            "steam",
            "rx",
            "minimax",
            "midjourney",
            "moore threads",
            "mthreads",
            "谷歌",
            "安卓",
            "英伟达",
            "amd",
            "华为",
            "荣耀",
            "vivo",
            "联发科",
            "天玑",
            "摩尔线程",
            "微信",
            "鸿蒙",
            "第三方",
            "小米",
            "midjourney",
            "西锐",
            "音乐生成",
        ],
    )
    if source_name == "Apple Newsroom":
        return "strong", "official Apple source"
    if is_competitor_launch_against_apple_story(title, text):
        return "weak", "third-party or competitor product launch using Apple mainly as comparison context"
    if is_siri_ai_eu_dma_regulatory_meeting_story(text):
        return "strong", "Apple-specific EU Digital Markets Act and Siri AI regulatory meeting"
    if is_uk_cma_app_store_payment_nfc_story(text):
        return "strong", "Apple-specific regional regulation event"
    if is_epic_app_store_appeal_story(text):
        return "strong", "Apple-specific App Store legal appeal event"
    if is_third_party_financial_service_with_apple_pay_support(title, text):
        return "weak", "third-party financial service with Apple Pay used only as a supported payment method"
    if is_airdrop_vulnerability_story(text):
        return "strong", "Apple AirDrop security vulnerability or ecosystem impact"
    if "iphone-color-mockup" in topic_facets_from_text(f"{title} {summary}"):
        return "strong", "Apple iPhone color, mockup, or physical-part rumor"
    if score_terms(lower, ["apple arcade", "苹果 arcade"]) > 0 and score_terms(
        lower,
        ["adds", "adding", "available", "launch", "lands", "coming", "games", "game", "新增", "上线", "游戏"],
    ) > 0:
        return "strong", "Apple Arcade catalog or service content update"
    if event_kind == "app_store_trust" and apple_score > 0:
        return "strong", "Apple platform trust, store policy, or review event"
    if is_apple_strategic_transaction_story(title):
        return "strong", "Apple strategic transaction or merger discussion"
    if is_apple_opinion_without_new_reporting(title, text):
        return "weak", "opinion or commentary without new Apple reporting"
    if is_apple_product_commentary_analysis_without_new_reporting(title, text):
        return "weak", "Apple product commentary or analysis without a new Apple action"
    if is_legacy_apple_platform_third_party_app_story(title, text):
        return "weak", "third-party app or service on a legacy Apple platform without a new Apple action"
    if is_third_party_legacy_apple_hardware_replica_story(title, text):
        return "weak", "third-party project recreating legacy Apple hardware without a new Apple action"
    if is_third_party_app_or_service_status_story(title, text):
        return "weak", "third-party app or service Apple-platform status story without a direct Apple action"
    if is_third_party_accessory_platform_compatibility_story(title, text):
        return "weak", "third-party accessory story with Apple platform compatibility used mainly as context"
    if is_third_party_app_platform_launch_story(title, text):
        return "weak", "third-party app or service Apple-platform story without a direct Apple platform action"
    if is_non_apple_primary_subject_with_incidental_apple_context(title, text):
        return "weak", "non-Apple primary subject with Apple used only as incidental context"
    if is_former_apple_staff_background_story(text):
        return "weak", "third-party company story using former Apple staff as background"
    if event_kind == "company_org":
        return "strong", "Apple company leadership, design, or organization change"
    if event_kind == "ecosystem_interop":
        return "ecosystem", "direct Apple ecosystem interoperability or compatibility impact"
    if is_non_apple_vendor_response_to_apple_product_story(title, text):
        return "weak", "third-party vendor response to an Apple product used mainly as market context"
    if is_competitor_or_company_story_using_apple_as_benchmark(title, text):
        return "weak", "competitor or third-party company story using Apple mainly as benchmark context"
    if is_multi_vendor_chip_or_phone_roadmap_background_story(title, text):
        return "weak", "multi-vendor chip or phone roadmap story using Apple mainly as context"
    if is_competitor_display_panel_story_using_apple_as_background(title, text):
        return "weak", "competitor display-panel or supply-chain story using Apple mainly as prior-order context"
    if is_apple_display_panel_supply_chain_story(text) or is_foldable_iphone_supply_chain_story(text):
        return "strong", "Apple hardware supply-chain or display-panel roadmap event"
    if is_third_party_surveillance_context_story(text):
        return "weak", "third-party surveillance story using Apple devices mainly as context"
    if is_third_party_device_management_service_story(text):
        return "weak", "third-party device-management service for Apple devices"
    if event_kind == "os_app" and is_title_primary_software_system_story(title, text):
        return "strong", "Apple OS, built-in app, or feature-summary change"
    if is_direct_apple_hardware_roadmap_story(text, title):
        return "strong", "Apple hardware roadmap or product-development event"
    if is_routine_recap_comparison_or_buying_advice(title, text):
        return "weak", "third-party or routine recap, comparison, hands-on, or buying advice without a new Apple action"
    if event_kind == "wallet_feature":
        return "strong", "Apple-specific wallet feature event"
    if is_apple_tv_hardware_story(text):
        return "strong", "Apple TV hardware event"
    if is_apple_product_data_leak_story(text, title):
        return "strong", "Apple product or supplier data-leak event"
    if os_release_facets_from_text(text):
        return "strong", "Apple OS release, beta, RC, or security update"
    if is_apple_hardware_product_launch_story(text, title):
        return "strong", "Apple hardware product launch or roadmap event"
    if (
        third_party_score > 0
        and apple_score > 0
        and title_apple_score == 0
        and not is_third_party_platform_availability_candidate(text)
        and score_terms(
        lower,
        [
            "apple will use",
            "apple to use",
            "apple taps",
            "apple adopts",
            "apple supplier",
            "苹果将调用",
            "苹果采用",
            "苹果供应商",
        ],
        ) == 0
    ):
        return "weak", "third-party or competitor story with Apple used mainly as context"
    if is_apple_os_feature_or_summary_story(text):
        return "strong", "Apple OS, built-in app, or feature-summary change"
    if event_kind == "messages_platform":
        return "strong", "Apple Messages or iMessage platform capability change"
    if is_routine_third_party_apple_platform_story(text):
        return "weak", "third-party app or service Apple-platform story without a direct Apple platform action"
    if is_apple_developer_tool_story(text):
        return "strong", "Apple first-party developer tool or Xcode capability change"
    if is_official_apple_accessory_market_story(text):
        return "strong", "Apple official hardware accessory availability change"
    if is_official_apple_refurbished_product_story(text):
        return "strong", "Apple official refurbished product availability or pricing change"
    if is_carplay_platform_feature_story(text):
        return "strong", "Apple CarPlay platform feature change"
    if is_airdrop_vulnerability_story(text):
        return "strong", "Apple AirDrop security vulnerability or ecosystem impact"
    if is_third_party_benchmark_comparison_story(text):
        return "weak", "third-party benchmark comparison using Apple mainly as context"
    if is_apple_car_asset_story(text):
        return "strong", "Apple vehicle testing asset or hardware-related company action"
    if is_how_to_guide_without_new_apple_action(title, text):
        return "weak", "how-to or troubleshooting guide without a new Apple action"
    if is_non_apple_product_research_context_story(text):
        return "weak", "non-Apple research using an Apple product mainly as study context"
    if is_non_apple_price_followup_story(title, text):
        return "weak", "non-Apple product price story using Apple pricing mainly as context"
    if is_non_apple_component_market_background_story(title, text):
        return "weak", "non-Apple component or industry price story using Apple mainly as background"
    if is_multi_vendor_chip_or_phone_roadmap_background_story(title, text):
        return "weak", "multi-vendor chip or phone roadmap story using Apple mainly as context"
    if is_apple_company_org_change_story(text):
        return "strong", "Apple company leadership, design, or organization change"
    if is_apple_executive_company_story(text):
        return "strong", "Apple executive, company, or services leadership event"
    if is_apple_strategic_transaction_story(text):
        return "strong", "Apple strategic transaction or merger discussion"
    if is_former_apple_staff_background_story(text):
        return "weak", "third-party company story using former Apple staff as background"
    if is_legacy_apple_protocol_third_party_removal(text):
        return "weak", "third-party project removing a legacy Apple protocol without a new Apple action"
    if is_third_party_xr_smart_glasses_context_story(text):
        return "weak", "third-party XR or smart-glasses story with Apple used mainly as context"
    if is_apple_product_price_increase_story(text, title):
        return "strong", "Apple-specific hardware pricing or cost event"
    if is_broad_multi_vendor_market_report(text, title):
        return "weak", "broad multi-vendor market report without Apple-specific shipment or share detail"
    if is_generic_consumer_electronics_health_safety_story(title, text):
        return "weak", "generic consumer-electronics safety story with Apple products used as examples"
    if event_kind == "app_store_trust" and apple_score > 0:
        return "strong", "Apple-specific App Store policy event"
    if is_third_party_security_software_promo_story(text):
        return "weak", "third-party security software promotion or compatibility story"
    if is_third_party_platform_availability_candidate(text):
        return "weak", "third-party app or service availability on Apple platforms"
    if event_kind == "third_party_ecosystem":
        return "weak", "third-party app or service Apple-platform story without a direct Apple platform action"
    if third_party_score > 0 and apple_score > 0 and score_terms(
        lower,
        [
            "apple will use",
            "apple to use",
            "apple taps",
            "apple adopts",
            "apple supplier",
            "苹果将调用",
            "苹果采用",
            "苹果供应商",
        ],
    ) == 0:
        if title_apple_score == 0 or event_kind == "third_party_ecosystem" or score_terms(
            lower,
            ["rival", "compared", "competes", "versus", "alternative to", "对标", "媲美", "竞品", "硬刚", "反超"],
        ) > 0:
            return "weak", "third-party or competitor story with Apple used mainly as context"
        if score_terms(
            lower,
            ["app", "application", "available on", "launches to", "mac users", "run on mac", "登陆", "上架", "支持 macos", "mac 用户"],
        ) > 0:
            return "weak", "third-party app or service availability on Apple platforms"
    if event_kind == "marketing_ad":
        return "weak", "routine marketing or advertisement without a material Apple product change"
    if event_kind in {
        "health_research",
        "apple_research",
        "regional_regulation",
        "legal_antitrust",
        "developer_program",
        "developer_tool",
        "app_store_trust",
        "security_privacy",
        "messages_platform",
        "service_content",
        "os_compatibility",
        "wallet_feature",
        "retail_store",
        "hardware_market",
        "os_app",
    } and apple_score > 0:
        return "strong", f"Apple-specific {event_kind.replace('_', ' ')} event"
    if third_party_score > 0 and apple_score > 0:
        return "weak", "third-party or competitor story with Apple used mainly as context"
    return "strong" if apple_score > 0 else "weak", "Apple term match" if apple_score > 0 else "no strong Apple action"


def choose_category(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    title_text = title.lower()
    event_kind = detect_event_kind(title, summary)
    if event_kind in {
        "ecosystem_interop",
        "health_research",
        "apple_research",
        "regional_regulation",
        "legal_antitrust",
        "developer_program",
        "developer_tool",
        "app_store_trust",
        "security_privacy",
        "messages_platform",
        "service_content",
        "os_compatibility",
        "wallet_feature",
        "os_app",
    }:
        return "software_systems"
    if event_kind in {"retail_store", "hardware_market"}:
        return "hardware_products"
    if (
        score_terms(title_text, ["apple store", "retail store", "苹果店", "零售店"]) > 0
        and score_terms(title_text, ["app store"]) == 0
    ):
        return "hardware_products"
    if score_terms(title_text, ["game", "games", "edition", "steam", "apple tv"]) > 0:
        return "software_systems"
    if is_apple_health_data_research_candidate(text):
        return "software_systems"
    if score_terms(
        title_text,
        [
            "apple card",
            "apple cash",
            "apple wallet",
            "app store",
            "ios",
            "ipados",
            "macos",
            "watchos",
            "visionos",
            "siri",
            "chatgpt",
            "openai",
            "whatsapp",
        ],
    ) > 0:
        return "software_systems"
    if score_terms(
        title_text,
        ["iphone", "ipad", "macbook", "airpods", "apple watch", "vision pro"],
    ) > 0:
        return "hardware_products"
    if score_terms(title_text, ["iphone", "ipad", "mac", "macbook", "airpods", "apple watch"]) > 0 and score_terms(
        title_text,
        [
            "price",
            "prices",
            "slashed",
            "discount",
            "charging",
            "fastest-charging",
            "products",
            "launch",
            "coming",
            "降价",
            "价格",
            "充电",
            "产品",
        ],
    ) > 0:
        return "hardware_products"
    software_score = score_terms(text, SOFTWARE_TERMS)
    hardware_score = score_terms(text, HARDWARE_TERMS)
    health_terms = ["health", "hearing", "hypertension", "sleep apnea", "健康", "助听", "高血压"]
    hardware_deciders = [
        "chip",
        "modem",
        "supplier",
        "production",
        "manufacturing",
        "shipment",
        "factory",
        "satellite",
        "carrier",
        "coverage",
        "cell coverage",
        "direct-to-device",
        "芯片",
        "调制解调器",
        "供应",
        "量产",
        "出货",
        "卫星",
        "运营商",
        "蜂窝",
        "信号",
    ]
    if score_terms(text, health_terms) > 0:
        return "software_systems"
    if score_terms(text, hardware_deciders) > 0:
        return "hardware_products"
    if hardware_score > software_score + 1:
        return "hardware_products"
    return "software_systems"


def collect_candidates(
    source: Source,
    cache_dir: Path,
    diagnostics: dict[str, Any],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    source_success = False

    for feed_url in source.feeds:
        text = fetch_url(feed_url, cache_dir, diagnostics)
        if text is None:
            continue
        source_success = True
        if feed_url.lower().endswith(".opml") or "<opml" in text[:500].lower():
            for nested_url in parse_opml_feed_urls(text):
                nested_text = fetch_url(nested_url, cache_dir, diagnostics)
                if nested_text:
                    candidates.extend(parse_xml_feed(nested_text, source, nested_url))
            continue
        candidates.extend(parse_xml_feed(text, source, feed_url))

    for api_url in source.wordpress_posts_apis:
        text = fetch_url(api_url, cache_dir, diagnostics, timeout=max(FETCH_TIMEOUT, 15.0), retries=0)
        if text is None:
            continue
        source_success = True
        api_candidates = parse_wordpress_posts_api(text, source, api_url)
        api_counts = diagnostics.setdefault("source_wordpress_api_candidate_counts", {})
        api_counts[source.name] = api_counts.get(source.name, 0) + len(api_candidates)
        candidates.extend(api_candidates)

    for page_url in source.pages:
        text = fetch_url(page_url, cache_dir, diagnostics)
        if text is None:
            continue
        source_success = True
        candidates.extend(parse_html_links(text, page_url, source))

    if not source_success:
        diagnostics.setdefault("failed_sources", []).append(source.name)

    filtered_by_url: dict[str, Candidate] = {}

    def candidate_completeness(candidate: Candidate) -> tuple[int, int, int, int]:
        return (
            1 if candidate.summary else 0,
            1 if candidate.feed_time_raw else 0,
            len(candidate.summary),
            len(candidate.context),
        )

    for candidate in merge_duplicate_candidates(candidates):
        normalized_url = normalize_url(candidate.url)
        if not same_domain(candidate.url, source.domains):
            continue
        if is_source_daily_brief_candidate(candidate, source):
            excluded_counts = diagnostics.setdefault("source_excluded_daily_brief_counts", {})
            excluded_counts[source.name] = excluded_counts.get(source.name, 0) + 1
            continue
        if not is_relevant_candidate(candidate, source):
            continue
        existing = filtered_by_url.get(normalized_url)
        if existing is not None and candidate_completeness(existing) >= candidate_completeness(candidate):
            continue
        filtered_by_url[normalized_url] = candidate
    filtered = list(filtered_by_url.values())
    diagnostics.setdefault("source_candidate_counts", {})[source.name] = len(filtered)
    return filtered


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [
        (key, value)
        for key, value in query
        if not key.lower().startswith(("utm_", "fbclid", "gclid"))
    ]
    clean_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            clean_query,
            "",
        )
    )


def candidate_detail_priority(candidate: Candidate) -> tuple[int, int, int, str]:
    text = f"{candidate.title} {candidate.summary} {candidate.context}"
    kind = detect_event_kind(candidate.title, candidate.summary, [candidate.context])
    tier, _ = classify_relevance_tier(
        candidate.title,
        candidate.summary,
        [candidate.context],
        candidate.source,
    )
    score = 0
    if tier == "strong":
        score += 40
    elif tier == "ecosystem":
        score += 30
    if is_third_party_platform_availability_candidate(text):
        score += 70
    if is_apple_developer_tool_story(text):
        score += 30
    if (
        score_terms(candidate.title, ["ios", "ipados", "macos", "watchos", "tvos", "visionos", "系统"]) > 0
        and score_terms(candidate.title, OS_FEATURE_ACTION_TERMS) > 0
    ):
        score += 20
    if kind in {
        "messages_platform",
        "service_content",
        "security_privacy",
        "wallet_feature",
        "os_app",
        "os_compatibility",
        "hardware_market",
        "legal_antitrust",
        "regional_regulation",
        "developer_program",
        "developer_tool",
        "app_store_trust",
        "retail_store",
        "health_research",
        "apple_research",
        "ecosystem_interop",
    }:
        score += 20
    if kind == "legal_antitrust":
        score += 15
    if score_terms(
        text,
        [
            "apple tv",
            "apple music",
            "apple arcade",
            "imessage",
            "messages app",
            "apple messages",
            "apple wallet",
            "app store",
            "ios",
            "macos",
            "iphone",
            "macbook",
            "wwdc",
            "developer app",
            "developer conference",
            "苹果商务消息",
            "苹果电视",
            "苹果开发者 app",
            "开发者大会",
        ],
    ) > 0:
        score += 10
    if score_terms(text, ["wwdc", "worldwide developers conference", "开发者大会"]) > 0:
        score += 20
    if candidate.feed_time_raw:
        score += 5
    date_match = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", candidate.url)
    date_score = 0
    if date_match:
        date_score = int("".join(date_match.groups()))
    return score, date_score, len(candidate.summary or candidate.context), candidate.url


def candidate_url_date_bucket(
    candidate: Candidate,
    source: Source,
    window_start_utc: datetime,
    now_utc: datetime,
) -> int:
    match = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", candidate.url)
    if not match:
        return 0
    try:
        source_tz = ZoneInfo(source.default_tz) if ZoneInfo is not None else timezone.utc
    except ZoneInfoNotFoundError:
        source_tz = timezone.utc
    year, month, day = (int(value) for value in match.groups())
    start = datetime(year, month, day, 0, 0, tzinfo=source_tz).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    if end <= window_start_utc:
        return -2
    if start <= now_utc and end > window_start_utc:
        return 1
    return 0


def candidate_time_bucket(
    candidate: Candidate,
    source: Source,
    window_start_utc: datetime | None,
    now_utc: datetime | None,
) -> int:
    if window_start_utc is None or now_utc is None:
        return 0
    if candidate.feed_time_raw:
        parsed = parse_datetime_value(candidate.feed_time_raw, source.default_tz)
        if parsed is not None:
            published = parsed.astimezone(timezone.utc)
            if window_start_utc < published <= now_utc:
                return 2
            if published <= window_start_utc:
                return -2
            return -1
    return candidate_url_date_bucket(candidate, source, window_start_utc, now_utc)


def candidate_detail_sort_key(
    candidate: Candidate,
    source: Source,
    window_start_utc: datetime | None,
    now_utc: datetime | None,
) -> tuple[int, int, int, int, str]:
    score, date_score, detail_len, url = candidate_detail_priority(candidate)
    return candidate_time_bucket(candidate, source, window_start_utc, now_utc), score, date_score, detail_len, url


def select_detail_candidates(
    candidates: list[Candidate],
    sources_by_name: dict[str, Source],
    limit: int,
    window_start_utc: datetime | None = None,
    now_utc: datetime | None = None,
) -> list[Candidate]:
    by_source: dict[str, list[Candidate]] = {name: [] for name in sources_by_name}
    for candidate in candidates:
        by_source.setdefault(candidate.source, []).append(candidate)

    for source_name, bucket in by_source.items():
        source = sources_by_name.get(source_name)
        if source is None:
            bucket.sort(key=candidate_detail_priority, reverse=True)
            continue
        bucket.sort(
            key=lambda item: candidate_detail_sort_key(
                item,
                source,
                window_start_utc,
                now_utc,
            ),
            reverse=True,
        )

    source_order = sorted(
        by_source,
        key=lambda name: SOURCE_PRIORITY.get(name, 99),
    )
    selected: list[Candidate] = []
    index = 0
    while len(selected) < limit:
        added = False
        for source_name in source_order:
            bucket = by_source.get(source_name, [])
            if index < len(bucket):
                selected.append(bucket[index])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        index += 1
    return selected


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def event_kind_compatible(article: Article, event: Event) -> bool:
    if article.event_kind == event.event_kind:
        return True
    strict_kinds = {"messages_platform"}
    if article.event_kind in strict_kinds or event.event_kind in strict_kinds:
        return False
    boundary_kinds = {
        "company_org",
        "legal_antitrust",
        "regional_regulation",
        "developer_program",
        "retail_store",
    }
    if not ({article.event_kind, event.event_kind} & boundary_kinds):
        article_facets = effective_topic_facets(article_primary_facets(article))
        event_facets = effective_topic_facets(event_primary_facets(event))
        if article_facets and event_facets and article_facets & event_facets:
            return True
    if "general_company" in {article.event_kind, event.event_kind}:
        return True
    return False


def relevance_tier_compatible(article: Article, event: Event) -> bool:
    if article.relevance_tier == event.relevance_tier:
        return True
    return "weak" not in {article.relevance_tier, event.relevance_tier}


def regions_compatible(article: Article, event: Event) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-product-price-increase" in common_facets:
        return True
    kind = article.event_kind if article.event_kind == event.event_kind else event.event_kind
    if kind not in REGION_SENSITIVE_EVENT_KINDS:
        return True
    article_regions = article.regions - {"multi-region"}
    event_regions = event.regions - {"multi-region"}
    if not article_regions or not event_regions:
        return True
    return bool(article_regions & event_regions)


def specific_merge_facets(facets: set[str]) -> set[str]:
    return effective_topic_facets(facets) - BROAD_TOPIC_FACETS - LOW_CONFIDENCE_MERGE_FACETS


def strong_shared_merge_tokens(shared: set[str]) -> set[str]:
    return {
        token
        for token in shared
        if token not in GENERIC_MERGE_TOKENS
        and not re.fullmatch(r"\d{1,4}", token)
        and token
        not in {"iphone", "ipad", "mac", "ios", "ipados", "macos", "watchos", "tvos", "visionos", "update", "new"}
    }


def article_merge_context(article: Article) -> str:
    return " ".join([article.title, article.summary, *article.key_facts[:6]])


def event_merge_context(event: Event) -> str:
    parts: list[str] = [event.title, event.summary, *event.key_facts[:6]]
    for item in event.articles:
        parts.extend([item.title, item.summary, *item.key_facts[:3]])
    return " ".join(parts)


def display_panel_supply_scope_compatible(article: Article, event: Event) -> bool:
    article_context = article_merge_context(article)
    event_context = event_merge_context(event)
    article_primary = is_primary_apple_display_panel_supply_chain_story(article.title, article_context)
    event_primary = is_primary_apple_display_panel_supply_chain_story(event.title, event_context)
    if not article_primary and not event_primary:
        return True
    if article_primary != event_primary:
        return False

    article_groups = display_panel_product_groups_from_text(article_context)
    event_groups = display_panel_product_groups_from_text(event_context)
    if not article_groups or not event_groups:
        return False

    shared_groups = article_groups & event_groups
    if not shared_groups:
        return False
    article_broad = len(article_groups) >= 3
    event_broad = len(event_groups) >= 3
    if article_broad != event_broad:
        return False
    if article_broad and event_broad:
        return len(shared_groups) >= 2
    return True


def topic_facets_compatible(
    article: Article,
    event: Event,
    shared: set[str] | None = None,
    similarity: float | None = None,
) -> bool:
    if not display_panel_supply_scope_compatible(article, event):
        return False
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if not restricted_memory_supplier_approval_facets_compatible(article_facets, event_facets):
        return False
    if not strategic_transaction_facets_compatible(article_facets, event_facets):
        return False
    if not app_store_policy_subtopic_facets_compatible(article_facets, event_facets):
        return False
    if not splittable_topic_facets_compatible(article_facets, event_facets):
        return False
    if not article_facets or not event_facets:
        explicit_specific = specific_merge_facets(article_facets | event_facets)
        if explicit_specific and article.event_kind == event.event_kind == "hardware_market":
            article_groups = hardware_product_families_from_text(article_merge_context(article))
            event_groups = hardware_product_families_from_text(event_merge_context(event))
            if article_groups and event_groups and not (article_groups & event_groups):
                return False
            strong_shared = strong_shared_merge_tokens(shared or set())
            if len(strong_shared) < 3 or (similarity or 0.0) < 0.18:
                return False
        topic_match = True
    else:
        topic_match = bool(article_facets & event_facets)
    if not topic_match:
        return False
    if broad_hardware_topic_bridge_only(article_facets, event_facets):
        article_groups = hardware_product_families_from_text(article_merge_context(article))
        event_groups = hardware_product_families_from_text(event_merge_context(event))
        if article_groups and event_groups and not (article_groups & event_groups):
            return False
    article_guard_facets = article_merge_guard_facets(article)
    event_guard_facets = event_merge_guard_facets(event)
    if not merge_guard_facets_compatible(article_guard_facets, event_guard_facets):
        if not shared_specific_strategic_transaction(article_facets, event_facets):
            return False
    return True


def event_relevance_tier(articles: list[Article]) -> tuple[str, str]:
    priority = {"weak": 0, "ecosystem": 1, "strong": 2}
    selected = max(articles, key=lambda item: priority.get(item.relevance_tier, 0))
    return selected.relevance_tier, selected.relevance_reason


SOFTWARE_EVENT_KINDS = {
    "ecosystem_interop",
    "health_research",
    "apple_research",
    "regional_regulation",
    "legal_antitrust",
    "developer_program",
    "developer_tool",
    "app_store_trust",
    "security_privacy",
    "messages_platform",
    "company_org",
    "service_content",
    "os_compatibility",
    "wallet_feature",
    "os_app",
}


HARDWARE_EVENT_KINDS = {"retail_store", "hardware_market"}


def event_category_from_metadata(title: str, summary: str, key_facts: list[str], event_kind: str) -> str:
    if event_kind in SOFTWARE_EVENT_KINDS:
        return "software_systems"
    if event_kind in HARDWARE_EVENT_KINDS:
        return "hardware_products"
    return choose_category(title, " ".join([summary, *key_facts[:5]]))


def event_source_for_reclassification(event: Event) -> str:
    if any(article.source == "Apple Newsroom" for article in event.articles):
        return "Apple Newsroom"
    return event.articles[0].source if event.articles else ""


def refresh_event_metadata(event: Event) -> None:
    article_kind = event.event_kind
    article_category = event.category
    article_tier, article_reason = event_relevance_tier(event.articles) if event.articles else (event.relevance_tier, event.relevance_reason)
    summary_kind = detect_event_kind(event.title, event.summary, event.key_facts)
    summary_tier, summary_reason = classify_relevance_tier(
        event.title,
        event.summary,
        event.key_facts,
        event_source_for_reclassification(event),
    )
    priority = {"weak": 0, "ecosystem": 1, "strong": 2}
    summary_context = " ".join([event.summary, *event.key_facts[:5]])
    summary_allows_downgrade = is_routine_recap_comparison_or_buying_advice(event.title, event.summary) or (
        summary_tier == "weak"
        and (
            effective_apple_term_score(f"{event.title} {summary_context}") <= 0
            or is_non_apple_primary_subject_with_incidental_apple_context(event.title, summary_context)
            or is_former_apple_staff_background_story(summary_context)
            or is_legacy_apple_platform_third_party_app_story(event.title, summary_context)
            or is_third_party_legacy_apple_hardware_replica_story(event.title, summary_context)
            or is_third_party_app_or_service_status_story(event.title, summary_context)
            or is_third_party_accessory_platform_compatibility_story(event.title, summary_context)
            or is_third_party_app_platform_launch_story(event.title, summary_context)
        )
    )
    if priority.get(article_tier, 0) > priority.get(summary_tier, 0) and not summary_allows_downgrade:
        event.event_kind = article_kind
        event.relevance_tier = article_tier
        event.relevance_reason = article_reason
        event.category = article_category
        return
    event.event_kind = summary_kind
    event.relevance_tier = summary_tier
    event.relevance_reason = summary_reason
    event.category = event_category_from_metadata(event.title, event.summary, event.key_facts, event.event_kind)


def event_merge_warnings(articles: list[Article]) -> list[str]:
    warnings: list[str] = []
    kinds = {item.event_kind for item in articles if item.event_kind != "general_company"}
    regions = set().union(*(item.regions for item in articles)) if articles else set()
    normalized_regions = regions - {"multi-region"}
    facet_sets = [effective_topic_facets(article_primary_facets(item)) for item in articles]
    explicit_facet_sets = [facets for facets in facet_sets if facets]
    common_facets = set.intersection(*explicit_facet_sets) if len(explicit_facet_sets) > 1 else set()
    if len(kinds) > 1 and not common_facets:
        warnings.append("mixed event kinds")
    if (
        len(articles) > 1
        and
        len(normalized_regions) > 1
        and not any(item.event_kind not in REGION_SENSITIVE_EVENT_KINDS for item in articles)
        and not (common_facets & REGION_WARNING_EXEMPT_FACETS)
    ):
        warnings.append("multiple region-specific markers")
    tiers = {item.relevance_tier for item in articles}
    if "weak" in tiers and len(tiers) > 1:
        warnings.append("mixed relevance tiers")
    if len(explicit_facet_sets) > 1:
        if not common_facets:
            warnings.append("mixed primary topic facets")
    return warnings


def same_beats_hardware_sighting(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "beats-headphones" not in common_facets:
        return False
    shared_anchors = shared & BEATS_HARDWARE_MERGE_TOKENS
    if {"antonee", "robinson"} <= shared_anchors:
        return True
    if len(shared_anchors) >= 2:
        return True
    return False


def same_apple_strategic_transaction(article: Article, event: Event) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-strategic-transaction" not in common_facets:
        return False
    counterparty_facets = {facet for facet in common_facets if facet.startswith("transaction-counterparty-")}
    return bool(counterparty_facets)


def same_system_performance_optimization(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "system-performance-optimization" not in common_facets:
        return False
    shared_anchors = shared & SYSTEM_PERFORMANCE_MERGE_TOKENS
    if len(shared_anchors) >= 2:
        return True
    return False


def same_apple_product_price_increase(article: Article, event: Event, shared: set[str]) -> bool:
    if "retail_store" in {article.event_kind, event.event_kind} and article.event_kind != event.event_kind:
        return False
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    common_facets = article_facets & event_facets
    if "apple-product-price-increase" not in common_facets:
        return False
    if not price_facets_compatible(article_facets, event_facets):
        return False
    price_anchors = {
        "1299",
        "270",
        "599",
        "799",
        "chip",
        "chips",
        "cook",
        "cost",
        "costs",
        "dram",
        "increase",
        "increases",
        "memory",
        "nand",
        "price",
        "price-increase",
        "shortage",
        "shortages",
        "storage",
        "unavoidable",
        "成本",
        "短缺",
        "芯片",
        "涨价",
        "价格",
        "内存",
        "存储",
        "库克",
        "不可避免",
    }
    shared_anchors = shared & price_anchors
    if len(shared_anchors) >= 2:
        return True
    return False


def same_airdrop_vulnerability_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "airdrop-vulnerability" not in common_facets:
        return False
    return bool(shared & {"airdrop", "vulnerability", "vulnerabilities", "漏洞", "隔空投送"})


def service_content_title_tokens_from_text(text: str) -> set[str]:
    return {
        token
        for token in article_tokens(text, "")
        if token not in GENERIC_SERVICE_CONTENT_MERGE_TOKENS
        and not re.fullmatch(r"\d{1,4}", token)
    }


def service_content_title_shared_tokens(article: Article, event: Event, shared: set[str]) -> set[str]:
    article_title_tokens = service_content_title_tokens_from_text(article.title)
    event_title_tokens: set[str] = set()
    for item in event.articles:
        event_title_tokens |= service_content_title_tokens_from_text(item.title)
    return shared & article_title_tokens & event_title_tokens


def article_service_topic_facets(article: Article) -> set[str]:
    return effective_topic_facets(article_primary_facets(article)) & SERVICE_CONTENT_TOPIC_FACETS


def event_service_topic_facets(event: Event) -> set[str]:
    return effective_topic_facets(event_primary_facets(event)) & SERVICE_CONTENT_TOPIC_FACETS


def should_merge(article: Article, event: Event) -> bool:
    shared = article.tokens & event.tokens
    similarity = jaccard(article.tokens, event.tokens)
    article_research = is_apple_research_candidate(
        " ".join([article.title, article.summary, *article.key_facts[:3]])
    )
    event_research = any(
        is_apple_research_candidate(" ".join([item.title, item.summary, *item.key_facts[:3]]))
        for item in event.articles
    )
    if article_research != event_research:
        return False
    if article_research and event_research:
        if "cvpr" in shared:
            return True
        if {"research", "paper"} <= shared and (
            {"apple", "ai", "computer-vision", "conference"} & (article.tokens | event.tokens)
        ):
            return True
        if len({"computer-vision", "conference", "research", "paper", "ai"} & shared) >= 2:
            return True
    article_health_research = is_apple_health_data_research_candidate(
        " ".join([article.title, article.summary, *article.key_facts[:3]])
    )
    event_health_research = any(
        is_apple_health_data_research_candidate(" ".join([item.title, item.summary, *item.key_facts[:3]]))
        for item in event.articles
    )
    if article_health_research != event_health_research:
        return False
    if article_health_research and event_health_research:
        if (HEALTH_RESEARCH_DATA_TOKENS & shared) and (HEALTH_RESEARCH_CONTEXT_TOKENS & shared):
            return True
    if not event_kind_compatible(article, event):
        return False
    if not relevance_tier_compatible(article, event):
        return False
    if not regions_compatible(article, event):
        return False
    if not topic_facets_compatible(article, event, shared, similarity):
        return False
    if article.event_kind == event.event_kind == "messages_platform":
        if "poke" in shared:
            return True
        platform_shared = {"imessage", "messages", "messages-app", "apple-messages", "apple-messages-for-business"} & shared
        agent_shared = {"ai", "agent", "assistant", "智能体"} & (article.tokens | event.tokens)
        action_shared = {"approved", "integration", "integrated", "接入", "批准"} & (article.tokens | event.tokens)
        if platform_shared and agent_shared and action_shared:
            return True
    if same_beats_hardware_sighting(article, event, shared):
        return True
    if same_apple_strategic_transaction(article, event):
        return True
    if same_system_performance_optimization(article, event, shared):
        return True
    if same_apple_product_price_increase(article, event, shared):
        return True
    if same_airdrop_vulnerability_event(article, event, shared):
        return True
    if same_os_release_event(article, event):
        return True
    strong_shared = strong_shared_merge_tokens(shared)
    if article.event_kind == event.event_kind == "service_content":
        article_service_facets = article_service_topic_facets(article)
        event_service_facets = event_service_topic_facets(event)
        if article_service_facets and event_service_facets and not (article_service_facets & event_service_facets):
            return False
        service_shared = {
            token
            for token in strong_shared
            if token not in GENERIC_SERVICE_CONTENT_MERGE_TOKENS
        }
        title_shared = service_content_title_shared_tokens(article, event, service_shared)
        if not title_shared:
            return False
        if len(title_shared) >= 2 and similarity >= 0.05:
            return True
        if len(title_shared) == 1 and len(service_shared) >= 4 and similarity >= 0.10:
            return True
        return False
    if similarity >= 0.38 and len(shared) >= 3:
        return True
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-wallet-digital-id" in common_facets:
        return True
    if "foldable-iphone-successor-roadmap" in common_facets:
        return True
    if "foldable-iphone-supply-chain" in common_facets:
        return True
    if "developer-tool-integration" in common_facets and len(strong_shared) >= 3:
        return True
    common_specific_facets = common_facets - LOW_CONFIDENCE_MERGE_FACETS
    if common_specific_facets and len(strong_shared) >= 3 and similarity >= 0.08:
        return True
    if len(strong_shared) >= 3 and similarity >= 0.18:
        return True
    version_tokens = {token for token in shared if re.match(r"^(ios|macos|ipados|watchos|tvos|visionos|-?\d)", token)}
    if version_tokens and len(strong_shared) >= 2 and similarity >= 0.22:
        return True
    if {"macos", "vulnerability"} <= shared or {"macos", "exploit"} <= shared:
        return True
    if "mythos" in shared and ({"macos", "mac", "security", "vulnerability"} & shared):
        return True
    if "anthropic" in shared and "security" in shared and ({"macos", "mac"} & shared):
        return True
    if "intel" in shared and ({"chip", "production"} & shared):
        return True
    if "satellite" in shared and ({"carrier", "coverage", "iphone"} & shared):
        return True
    if "apple-card" in shared and ("airpods" in shared or "cash" in shared or "daily-cash" in shared):
        return True
    if "app-store" in shared and len(shared) >= 2:
        app_store_context = {
            "fraud",
            "fraudulent",
            "safety",
            "security",
            "protection",
            "protections",
            "review",
            "submission",
            "submissions",
            "developer",
            "developers",
            "account",
            "accounts",
            "transaction",
            "transactions",
        }
        if (app_store_context & article.tokens) and (app_store_context & event.tokens):
            return True
    if {"iphone", "17", "price"} <= shared:
        return True
    if {"apple", "stock"} <= shared and ({"record", "share", "shares"} & shared):
        return True
    if {"shares", "record"} <= shared:
        return True
    if "musk" in shared and ({"openai", "chatgpt", "siri"} & shared) and (
        {"court", "lawsuit", "discovery"} & shared
    ):
        return True
    return False


def clean_sentence(value: str) -> str:
    value = strip_tags(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    return value


def is_price_response_or_rationale_fact(value: str) -> bool:
    lower = value.lower()
    return score_terms(
        lower,
        [
            "statement",
            "said",
            "says",
            "tim cook",
            "unavoidable",
            "not welcome news",
            "working tirelessly",
            "find solutions",
            "shielded",
            "memory",
            "storage",
            "shortage",
            "component costs",
            "ai data center",
            "begin raising prices",
            "声明",
            "表示",
            "库克",
            "不可避免",
            "不受欢迎",
            "寻找解决方案",
            "上调部分产品价格",
            "开始上调",
            "内存",
            "存储",
            "短缺",
            "组件成本",
        ],
    ) > 0


def price_response_or_rationale_priority(value: str) -> int:
    lower = value.lower()
    priority = 0
    if score_terms(
        lower,
        [
            "not welcome news",
            "working tirelessly",
            "find solutions",
            "不受欢迎",
            "努力寻找解决方案",
            "寻找解决方案",
        ],
    ) > 0:
        priority += 120
    if score_terms(lower, ["shielded customers", "shielded", "保护消费者", "避免转嫁"]) > 0:
        priority += 90
    if score_terms(
        lower,
        [
            "begin raising prices",
            "needs to begin raising prices",
            "unavoidable",
            "inevitable",
            "tim cook",
            "开始上调",
            "不可避免",
            "库克",
        ],
    ) > 0:
        priority += 75
    if score_terms(
        lower,
        [
            "statement",
            "said apple",
            "apple said",
            "said",
            "says",
            "声明",
            "表示",
        ],
    ) > 0:
        priority += 25
    if score_terms(
        lower,
        [
            "memory",
            "storage",
            "shortage",
            "component costs",
            "ai data center",
            "ram",
            "ssd",
            "内存",
            "存储",
            "短缺",
            "组件成本",
        ],
    ) > 0:
        priority += 40
    return priority


def price_response_or_rationale_candidates(article: Article) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    index = 0
    summary = clean_sentence(article.summary)
    if summary:
        for sentence in re.split(r"(?<=[.!?。！？])\s+", summary):
            sentence = clean_sentence(sentence)
            if sentence and is_price_response_or_rationale_fact(sentence):
                candidates.append((price_response_or_rationale_priority(sentence), index, sentence))
                index += 1
    for fact in article.key_facts:
        if is_price_response_or_rationale_fact(fact):
            candidates.append((price_response_or_rationale_priority(fact), index, fact))
            index += 1
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in candidates]


def compact_price_response_must_include_fact(candidates: list[str]) -> str:
    combined = " ".join(clean_sentence(item) for item in candidates if clean_sentence(item))
    lower = combined.lower()
    clauses: list[str] = []
    if (
        score_terms(lower, ["ai data center", "ai data centers", "artificial intelligence data center", "人工智能数据中心"]) > 0
        and score_terms(lower, ["memory", "storage", "ram", "ssd", "内存", "存储"]) > 0
    ) or score_terms(lower, ["component price increase", "component costs", "元器件价格", "组件成本"]) > 0:
        clauses.append(
            "AI data centers drove extraordinary memory and storage demand and unusually fast component-cost increases"
        )
    if score_terms(lower, ["shielded", "shielded customers", "内部消化", "保护消费者", "避免冲击"]) > 0:
        if score_terms(lower, ["ipad", "mac"]) >= 2:
            clauses.append("Apple says it previously shielded customers but now must raise prices on products including iPad and Mac")
        else:
            clauses.append("Apple says it previously shielded customers but now must raise prices on some products")
    elif score_terms(lower, ["begin raising prices", "needs to begin raising prices", "开始上调", "提高部分产品"]) > 0:
        if score_terms(lower, ["ipad", "mac"]) >= 2:
            clauses.append("Apple says it must begin raising prices on products including iPad and Mac")
        else:
            clauses.append("Apple says it must begin raising prices on some products")
    if score_terms(lower, ["not welcome news", "并非好消息", "不受欢迎"]) > 0 and score_terms(
        lower,
        ["working tirelessly", "find solutions", "寻找解决方案", "竭尽全力"],
    ) > 0:
        clauses.append("Apple acknowledges this is not welcome news and says it is working tirelessly to find solutions")
    elif score_terms(lower, ["working tirelessly", "find solutions", "寻找解决方案", "竭尽全力"]) > 0:
        clauses.append("Apple says it is working tirelessly to find solutions")
    if not clauses:
        return clean_sentence(candidates[0]) if candidates else ""
    return "Apple's response: " + "; ".join(clauses) + "."


def event_key_fact_limit(articles: list[Article], price_event: bool = False) -> int:
    base_limit = MAX_OFFICIAL_KEY_FACTS if any(item.source in OFFICIAL_FACT_SOURCES for item in articles) else MAX_KEY_FACTS
    if len(articles) <= 1:
        return base_limit
    fact_slots = sum(min(len(item.key_facts), 8) for item in articles)
    expansion = len(articles) * (3 if price_event else 2)
    cap = 72 if price_event else 48
    return min(cap, max(base_limit, min(fact_slots + (1 if price_event else 0), base_limit + expansion)))


def is_price_change_fact(value: str) -> bool:
    lower = value.lower()
    has_change = score_terms(
        lower,
        [
            "up from",
            "increased from",
            "raised from",
            "now starts at",
            "starts at",
            "涨价",
            "上调至",
            "起售价从",
            "调整为",
        ],
    ) > 0
    has_price_value = bool(re.search(r"[$€£¥]\s?\d|\d+\s?(?:美元|元|人民币)", value))
    return has_change and has_price_value


def is_market_reaction_fact(value: str) -> bool:
    lower = value.lower()
    return score_terms(
        lower,
        [
            "stock",
            "shares",
            "analyst",
            "rating",
            "target",
            "wall street",
            "outperform",
            "股价",
            "分析师",
            "评级",
            "目标价",
            "跑赢大盘",
        ],
    ) > 0 and (data_value_count(value) > 0 or "%" in value)


def is_price_scope_fact(value: str) -> bool:
    lower = value.lower()
    has_scope_signal = score_terms(
        lower,
        [
            "not included",
            "unchanged in price",
            "escaped",
            "hasn't yet increased",
            "more price increases",
            "broader set of price increases",
            "start of",
            "14 products",
            "next round",
            "not covered",
            "未覆盖",
            "暂未覆盖",
            "后续",
            "新一轮涨价",
            "14 款",
        ],
    ) > 0
    has_price_context = score_terms(
        lower,
        [
            "price",
            "prices",
            "pricing",
            "price increases",
            "price hikes",
            "售价",
            "涨价",
            "调价",
            "上调",
            "提价",
        ],
    ) > 0
    return has_scope_signal and has_price_context


def low_value_price_event_fact(value: str) -> bool:
    lower = value.lower()
    return score_terms(
        lower,
        [
            "podcast",
            "listen to",
            "itunes",
            "stitcher",
            "tunein",
            "overcast",
            "prime day",
            "deals",
            "best buy",
            "amazon",
            "carry-on",
            "buying advice",
            "dedicated rss feed",
        ],
    ) > 0


def event_fact_priority(value: str, price_event: bool = False) -> int:
    score = data_value_count(value) * 10
    if score_terms(value, FACT_CONTEXT_TERMS) > 0:
        score += 8
    if not price_event:
        return score
    if low_value_price_event_fact(value):
        score -= 120
    if is_price_change_fact(value):
        score += 100
        if len(value) <= 220:
            score += 55
        elif len(value) <= 360:
            score += 25
        elif len(value) > 650:
            score -= 90
        elif len(value) > 480:
            score -= 55
    if is_market_reaction_fact(value):
        score += 90
    if is_price_scope_fact(value):
        score += 70
    if is_price_response_or_rationale_fact(value):
        score += 45
    if score_terms(
        value,
        [
            "macbook",
            "ipad",
            "vision pro",
            "homepod",
            "apple tv",
            "airpods",
            "apple watch",
            "iphone",
            "imac",
            "mac mini",
            "mac studio",
        ],
    ) > 0:
        score += 15
    return score


def article_ranked_key_facts(article: Article, price_event: bool = False) -> list[str]:
    if not price_event:
        return article.key_facts
    scored = [
        (event_fact_priority(fact, price_event), index, fact)
        for index, fact in enumerate(article.key_facts)
    ]
    return [
        fact
        for score, _, fact in sorted(scored, key=lambda item: (-item[0], item[1]))
        if score >= 35
    ]


def article_fact_round_robin(articles: list[Article], price_event: bool = False) -> Iterator[str]:
    ranked_facts = [article_ranked_key_facts(article, price_event) for article in articles]
    max_facts = max((len(facts) for facts in ranked_facts), default=0)
    for index in range(max_facts):
        for facts in ranked_facts:
            if index < len(facts):
                yield facts[index]


def price_event_fact_candidates(articles: list[Article]) -> list[tuple[int, int, int, str]]:
    candidates: list[tuple[int, int, int, str]] = []
    for article_index, article in enumerate(articles):
        for fact_index, fact in enumerate(article.key_facts):
            if low_value_price_event_fact(fact):
                continue
            price_change = is_price_change_fact(fact)
            market_reaction = is_market_reaction_fact(fact)
            price_scope = is_price_scope_fact(fact)
            price_response = is_price_response_or_rationale_fact(fact)
            if not (price_change or market_reaction or price_scope or price_response):
                continue
            if price_response and not (price_change or market_reaction or price_scope):
                continue
            score = event_fact_priority(fact, price_event=True)
            if score >= 35:
                candidates.append((score, article_index, fact_index, fact))
    return candidates


def collect_price_event_key_facts(
    articles: list[Article],
    facts: list[str],
    seen: set[str],
    limit: int,
) -> list[str]:
    candidates = price_event_fact_candidates(articles)
    def price_change_sort_key(item: tuple[int, int, int, str]) -> tuple[int, int, int, int]:
        score, article_index, fact_index, fact = item
        concise_rank = 0 if len(fact) <= 220 else 1
        return (concise_rank, -score, article_index, fact_index)

    buckets: list[tuple[int, list[tuple[int, int, int, str]]]] = [
        (
            max(8, min(52, limit - 16)),
            [item for item in candidates if is_price_change_fact(item[3])],
        ),
        (
            max(4, min(8, limit // 6)),
            [item for item in candidates if is_market_reaction_fact(item[3])],
        ),
        (
            max(4, min(8, limit // 6)),
            [item for item in candidates if is_price_scope_fact(item[3])],
        ),
    ]
    used: set[tuple[int, int, str]] = set()
    for bucket_index, (bucket_limit, bucket) in enumerate(buckets):
        added = 0
        if bucket_index == 0:
            sorted_bucket = sorted(bucket, key=price_change_sort_key)
        else:
            sorted_bucket = sorted(bucket, key=lambda item: (-item[0], item[1], item[2]))
        for score, article_index, fact_index, fact in sorted_bucket:
            if (article_index, fact_index, fact) in used:
                continue
            if add_unique_text(facts, seen, fact, min_chars=key_fact_min_chars(fact)):
                added += 1
                used.add((article_index, fact_index, fact))
            if len(facts) >= limit:
                return facts
            if added >= bucket_limit:
                break
    for score, article_index, fact_index, fact in sorted(candidates, key=lambda item: (-item[0], item[1], item[2])):
        if (article_index, fact_index, fact) in used:
            continue
        add_unique_text(facts, seen, fact, min_chars=key_fact_min_chars(fact))
        if len(facts) >= limit:
            return facts
    return facts


def collect_event_key_facts(articles: list[Article]) -> list[str]:
    ordered = sorted(
        articles,
        key=lambda item: (
            0 if item.source in OFFICIAL_FACT_SOURCES else 1,
            SOURCE_PRIORITY.get(item.source, 99),
            item.published_utc,
        ),
    )
    facts: list[str] = []
    seen: set[str] = set()
    event_article_facets: set[str] = set()
    for article in articles:
        event_article_facets |= article_primary_facets(article)
    price_event = "apple-current-product-price-increase" in event_article_facets
    limit = event_key_fact_limit(ordered, price_event)
    if price_event:
        price_candidates: list[tuple[int, int, str]] = []
        index = 0
        for article in ordered:
            for fact in price_response_or_rationale_candidates(article):
                price_candidates.append((price_response_or_rationale_priority(fact), index, fact))
                index += 1
        price_candidates.sort(key=lambda item: (-item[0], item[1]))
        compact_fact = compact_price_response_must_include_fact([fact for _, _, fact in price_candidates])
        if compact_fact:
            add_unique_text(facts, seen, compact_fact, min_chars=key_fact_min_chars(compact_fact))
        return collect_price_event_key_facts(ordered, facts, seen, limit)
    for fact in article_fact_round_robin(ordered, price_event):
        add_unique_text(facts, seen, fact, min_chars=key_fact_min_chars(fact))
        if len(facts) >= limit:
            return facts
    return facts


def event_must_include_facts(event: Event) -> list[str]:
    must_include: list[str] = []
    seen: set[str] = set()
    price_event = "apple-current-product-price-increase" in event_primary_facets(event)
    if price_event:
        candidates: list[tuple[int, int, str]] = []
        index = 0
        for fact in event.key_facts:
            if is_price_response_or_rationale_fact(fact):
                candidates.append((price_response_or_rationale_priority(fact), index, fact))
                index += 1
        for article in sorted(
            event.articles,
            key=lambda item: (SOURCE_PRIORITY.get(item.source, 99), item.published_utc),
        ):
            for fact in price_response_or_rationale_candidates(article):
                candidates.append((price_response_or_rationale_priority(fact), index, fact))
                index += 1
        candidates.sort(key=lambda item: (-item[0], item[1]))
        compact_fact = compact_price_response_must_include_fact([fact for _, _, fact in candidates])
        if compact_fact:
            add_unique_text(must_include, seen, compact_fact, min_chars=key_fact_min_chars(compact_fact))
    return must_include


def build_event_summary(articles: list[Article]) -> tuple[str, str, list[str]]:
    representative = sorted(
        articles,
        key=lambda item: (SOURCE_PRIORITY.get(item.source, 99), item.published_utc),
    )[0]
    title = clean_sentence(representative.title)
    details: list[str] = []
    seen: set[str] = set()
    for article in sorted(
        articles,
        key=lambda item: (SOURCE_PRIORITY.get(item.source, 99), item.published_utc),
    ):
        summary = clean_sentence(article.summary)
        if not summary:
            continue
        sentences = re.split(r"(?<=[.!?。！？])\s+", summary)
        for sentence in sentences:
            sentence = clean_sentence(sentence)
            if len(sentence) < 40:
                continue
            key = sentence.lower()[:100]
            if key in seen:
                continue
            seen.add(key)
            details.append(sentence)
            if len(details) >= 3:
                break
        if len(details) >= 3:
            break
    key_facts = collect_event_key_facts(articles)
    for fact in key_facts[:8]:
        key = clean_sentence(fact).lower()[:100]
        if key in seen:
            continue
        seen.add(key)
        details.append(fact)
    if details:
        summary = f"{title}. {' '.join(details)}"
    else:
        summary = title
    return title, summary, key_facts


def rebuild_event_from_articles(event: Event, articles: list[Article]) -> Event:
    event.articles = sorted(articles, key=lambda item: item.published_utc)
    event.tokens = set().union(*(item.tokens for item in event.articles))
    representative = min(event.articles, key=lambda item: item.published_utc)
    event.published_utc = representative.published_utc
    event.published_raw = representative.published_raw
    event.published_source = representative.published_source
    event.confidence = representative.confidence
    categories = [item.category for item in event.articles]
    event.category = max(set(categories), key=categories.count)
    kinds = [item.event_kind for item in event.articles]
    event.event_kind = max(set(kinds), key=kinds.count)
    event.relevance_tier, event.relevance_reason = event_relevance_tier(event.articles)
    event.regions = set().union(*(item.regions for item in event.articles))
    event.merge_warnings = event_merge_warnings(event.articles)
    event.title, event.summary, event.key_facts = build_event_summary(event.articles)
    refresh_event_metadata(event)
    return event


def event_summary_article(event: Event) -> Article:
    token_summary = " ".join([event.summary, *event.key_facts[:8]])
    return Article(
        source="event-summary",
        url=f"event:{event.event_id}",
        title=event.title,
        summary=event.summary,
        key_facts=list(event.key_facts),
        category=event.category,
        published_utc=event.published_utc,
        published_raw=event.published_raw,
        published_source=event.published_source,
        confidence=event.confidence,
        tokens=article_tokens(event.title, token_summary),
        event_kind=event.event_kind,
        relevance_tier=event.relevance_tier,
        relevance_reason=event.relevance_reason,
        regions=set(event.regions),
    )


def event_summary_event(event: Event) -> Event:
    article = event_summary_article(event)
    return Event(
        event_id=event.event_id,
        category=event.category,
        title=event.title,
        summary=event.summary,
        key_facts=list(event.key_facts),
        published_utc=event.published_utc,
        published_raw=event.published_raw,
        published_source=event.published_source,
        confidence=event.confidence,
        articles=[article],
        tokens=set(article.tokens),
        event_kind=event.event_kind,
        relevance_tier=event.relevance_tier,
        relevance_reason=event.relevance_reason,
        regions=set(event.regions),
        merge_warnings=list(event.merge_warnings),
    )


def event_summary_primary_facets(event: Event) -> set[str]:
    context = " ".join([event.summary, *event.key_facts[:8]])
    return effective_topic_facets(primary_topic_facets(event.title, context))


def event_summary_merge_keys(event: Event) -> set[tuple[str, tuple[str, ...]]]:
    keys: set[tuple[str, tuple[str, ...]]] = set()
    facets = event_summary_primary_facets(event)
    if not facets:
        return keys
    summary_article = event_summary_article(event)
    guard_facets = primary_merge_guard_facets(
        summary_article.title,
        " ".join([summary_article.summary, *summary_article.key_facts[:8]]),
    )
    platforms = tuple(
        sorted(
            facet
            for facet in merge_guard_platform_facets(guard_facets)
            if facet != "platform-mobile-os"
        )
    )
    if "apple-product-price-increase" in facets:
        if "apple-restricted-memory-supplier-approval" in facets:
            keys.add(("apple-restricted-memory-supplier-approval", ()))
        else:
            price_subtopics = sorted(price_summary_key_facets(facets))
            if price_subtopics:
                for subtopic in price_subtopics:
                    keys.add((subtopic, ()))
            else:
                keys.add(("apple-product-price-increase", ()))
    elif "apple-restricted-memory-supplier-approval" in facets:
        keys.add(("apple-restricted-memory-supplier-approval", ()))
    for facet in sorted(facets & IPHONE_HARDWARE_RUMOR_TOPIC_FACETS):
        keys.add((facet, ()))
    if "apple-product-data-leak" in facets:
        context = " ".join([event.title, event.summary, *event.key_facts[:8]]).lower()
        leak_detail_facets = facets & {
            "apple-product-data-leak-enforcement",
            "apple-product-data-leak-specs",
            "iphone-chip-packaging",
            "iphone-drop-test-leak",
        }
        if leak_detail_facets:
            for facet in sorted(leak_detail_facets):
                keys.add((facet, ()))
            return keys
        product_score = score_terms(
            context,
            [
                "iphone",
                "iphone 18",
                "iphone 18 pro",
                "a20",
                "a20 pro",
                "c2",
                "modem",
                "logic board",
                "主板",
                "基带",
                "芯片",
            ],
        )
        leak_score = score_terms(
            context,
            [
                "schematics",
                "data sheets",
                "files",
                "stolen",
                "leaked",
                "dark web",
                "cyberattack",
                "data leak",
                "主板图纸",
                "图纸",
                "资料",
                "文件",
                "泄露",
                "被窃取",
                "黑客",
                "暗网",
            ],
        )
        if product_score >= 2 and leak_score >= 1:
            keys.add(("apple-product-data-leak", ()))
    if "apple-product-roadmap-list" in facets:
        anchors = summary_article.tokens & {
            "20",
            "2026",
            "2027",
            "airpods",
            "apple-glasses",
            "apple-watch",
            "foldable",
            "gurman",
            "homepod",
            "ipad",
            "iphone",
            "mac",
            "macbook",
            "product",
            "products",
            "roadmap",
            "vision",
            "watch",
            "古尔曼",
            "新品",
            "产品",
            "路线图",
            "折叠屏",
            "智能眼镜",
        }
        if len(anchors) >= 4:
            keys.add(("apple-product-roadmap-list", ()))
    if "apple-company-org-change" in facets:
        anchors = summary_article.tokens & {
            "ceo",
            "cook",
            "design",
            "design-team",
            "industrial-design",
            "john-ternus",
            "leadership",
            "management",
            "organization",
            "product-design",
            "ternus",
            "库克",
            "特努斯",
            "设计",
            "设计团队",
            "设计部门",
            "管理层",
            "组织",
            "架构",
            "权重",
        }
        if len(anchors) >= 2:
            keys.add(("apple-company-org-change", ()))
    if "apple-music-top-artists" in facets:
        keys.add(("apple-music-top-artists", ()))
    if "bootrom-secure-rom-exploit" in facets:
        anchors = summary_article.tokens & {"a12", "a13", "bootrom", "securerom", "secure-rom", "usbliter8"}
        if len(anchors) >= 2:
            keys.add(("bootrom-secure-rom-exploit", ()))
    if "find-my-location-sharing" in facets:
        anchors = summary_article.tokens & {"find-my", "hide-location", "location-sharing", "sharing-duration"}
        if len(anchors) >= 1:
            keys.add(("find-my-location-sharing", ()))
    if "apple-wallet-digital-id" in facets:
        anchors = summary_article.tokens & {
            "apple-wallet",
            "digital-id",
            "digital",
            "identity",
            "passport",
            "verification",
            "nationality",
            "wallet",
            "数字身份证",
            "数字身份",
            "身份凭证",
            "身份核验",
            "国籍校验",
            "护照",
        }
        if len(anchors) >= 2:
            keys.add(("apple-wallet-digital-id", ()))
    if "apple-pay-rewards" in facets:
        anchors = summary_article.tokens & {"apple-pay", "american", "express", "amex", "membership", "rewards", "points", "checkout"}
        if len(anchors) >= 2:
            keys.add(("apple-pay-rewards", ()))
    for facet in sorted(facets & {"apple-refurbished-iphone", "apple-refurbished-ipad", "apple-refurbished-mac", "apple-refurbished-product"}):
        anchors = summary_article.tokens & {"apple", "refurbished", "iphone", "ipad", "mac", "macbook", "store", "官翻", "翻新", "官方"}
        if len(anchors) >= 2:
            keys.add((facet, ()))
    primary_display_panel_scope = is_primary_apple_display_panel_supply_chain_story(
        event.title,
        " ".join([event.summary, *event.key_facts[:8]]),
    )
    if "foldable-iphone-supply-chain" in facets and not primary_display_panel_scope:
        anchors = summary_article.tokens & {
            "foldable",
            "foldable-iphone",
            "iphone",
            "supply",
            "supply-chain",
            "supplier",
            "production",
            "供应链",
            "供货",
            "小批量",
            "量产",
            "折叠屏",
            "折叠屏-iphone",
        }
        if len(anchors) >= 2:
            keys.add(("foldable-iphone-supply-chain", ()))
    if "foldable-iphone-successor-roadmap" in facets:
        anchors = summary_article.tokens & {
            "iphone",
            "iphone-ultra",
            "iphone-ultra-2",
            "ultra",
            "ultra2",
            "foldable",
            "greenlit",
            "go-ahead",
            "development",
            "confirmed",
            "air-3",
            "air",
            "第二代",
            "折叠屏",
            "开了绿灯",
            "确认启动",
            "开发",
        }
        if len(anchors) >= 2:
            keys.add(("foldable-iphone-successor-roadmap", ()))
    if "brazil-app-store-policy" in facets:
        anchors = summary_article.tokens & {"brazil", "app-store", "alternative-marketplace", "third-party-payment", "commission"}
        if len(anchors) >= 2:
            keys.add(("brazil-app-store-policy", ()))
    if "uk-cma-app-store-payment-nfc" in facets:
        anchors = summary_article.tokens & {"uk", "cma", "app-store", "payment", "payments", "nfc", "ios", "developer", "developers", "英国", "平台外支付", "应用商店"}
        if len(anchors) >= 2:
            keys.add(("uk-cma-app-store-payment-nfc", ()))
    if "apple-arcade" in facets:
        anchors = summary_article.tokens & {"apple-arcade", "arcade", "family", "feud", "game", "games", "catalog", "游戏"}
        if len(anchors) >= 2:
            keys.add(("apple-arcade", ()))
    if "iphone-air-successor" in facets:
        anchors = summary_article.tokens & {"iphone", "air", "air-2", "dual", "camera", "a20", "dynamic-island", "双摄", "超广角", "灵动岛"}
        if len(anchors) >= 2:
            keys.add(("iphone-air-successor", ()))
    if "iphone-color-mockup" in facets:
        context = " ".join([event.title, event.summary, *event.key_facts[:8]]).lower()
        anchors = summary_article.tokens & {"iphone", "color", "colors", "dark", "cherry", "sim", "tray", "mockup"}
        if len(anchors) >= 2 or (
            score_terms(context, ["iphone", "苹果"]) > 0
            and score_terms(context, ["color", "colors", "dark cherry", "sim tray", "配色", "颜色", "樱桃红", "卡托", "机模"]) > 0
        ):
            keys.add(("iphone-color-mockup", ()))
    if "iphone-parts-factory-contamination" in facets:
        anchors = summary_article.tokens & {"iphone", "factory", "plant", "tata", "hosur", "contamination", "wastewater", "pollution", "water", "工厂", "污染", "废水", "塔塔"}
        if len(anchors) >= 2:
            keys.add(("iphone-parts-factory-contamination", ()))
    if "system-performance-optimization" in facets:
        anchors = summary_article.tokens & SYSTEM_PERFORMANCE_MERGE_TOKENS
        if len(anchors) >= 2 and platforms:
            keys.add(("system-performance-optimization", platforms))
    return keys


def events_summary_merge_allowed(left: Event, right: Event) -> bool:
    left_facets = event_summary_primary_facets(left)
    right_facets = event_summary_primary_facets(right)
    common_facets = left_facets & right_facets
    if not (common_facets & SUMMARY_LEVEL_EVENT_MERGE_FACETS):
        return False
    left_guard_facets = event_merge_guard_facets(left)
    right_guard_facets = event_merge_guard_facets(right)
    return merge_guard_facets_compatible(left_guard_facets, right_guard_facets)


def events_should_merge(left: Event, right: Event) -> bool:
    left_has_retail = any(article.event_kind == "retail_store" for article in left.articles)
    right_has_retail = any(article.event_kind == "retail_store" for article in right.articles)
    if left_has_retail != right_has_retail:
        return False
    left_splittable_facets = event_splittable_topic_facets(left)
    right_splittable_facets = event_splittable_topic_facets(right)
    if not splittable_topic_facets_compatible(left_splittable_facets, right_splittable_facets):
        return False
    if "weak" in {left.relevance_tier, right.relevance_tier} and left.relevance_tier != right.relevance_tier:
        return False
    if any(should_merge(article, right) for article in left.articles) or any(
        should_merge(article, left) for article in right.articles
    ):
        return True
    if event_summary_merge_keys(left) & event_summary_merge_keys(right):
        return True
    if not events_summary_merge_allowed(left, right):
        return False
    left_summary = event_summary_article(left)
    right_summary = event_summary_article(right)
    left_event = event_summary_event(left)
    right_event = event_summary_event(right)
    return should_merge(left_summary, right_event) or should_merge(
        right_summary, left_event
    )


def consolidate_events(events: list[Event]) -> list[Event]:
    changed = True
    while changed:
        changed = False
        consolidated: list[Event] = []
        for event in sorted(events, key=lambda item: item.published_utc):
            matched: Event | None = None
            for existing in consolidated:
                if events_should_merge(event, existing):
                    matched = existing
                    break
            if matched is None:
                consolidated.append(event)
                continue
            rebuild_event_from_articles(matched, [*matched.articles, *event.articles])
            changed = True
        events = consolidated
    return events


def event_from_article_group(source_event: Event, articles: list[Article]) -> Event:
    event_id = hashlib.sha1(
        " ".join(sorted(normalize_url(article.url) for article in articles)).encode("utf-8")
    ).hexdigest()[:12]
    event = Event(
        event_id=event_id,
        category=source_event.category,
        title=source_event.title,
        summary=source_event.summary,
        key_facts=list(source_event.key_facts),
        published_utc=source_event.published_utc,
        published_raw=source_event.published_raw,
        published_source=source_event.published_source,
        confidence=source_event.confidence,
        articles=[],
        tokens=set(),
        event_kind=source_event.event_kind,
        relevance_tier=source_event.relevance_tier,
        relevance_reason=source_event.relevance_reason,
        regions=set(source_event.regions),
        merge_warnings=[],
    )
    return rebuild_event_from_articles(event, articles)


def best_topic_group_for_article(article: Article, groups: dict[tuple[str, ...], list[Article]]) -> tuple[str, ...] | None:
    best_key: tuple[str, ...] | None = None
    best_score = 0.0
    for key, group in groups.items():
        group_tokens = set().union(*(item.tokens for item in group))
        score = jaccard(article.tokens, group_tokens)
        if score > best_score:
            best_score = score
            best_key = key
    if best_score < 0.04:
        return None
    return best_key


def split_mixed_topic_event(event: Event) -> list[Event]:
    retail_articles = [article for article in event.articles if article.event_kind == "retail_store"]
    non_retail_articles = [article for article in event.articles if article.event_kind != "retail_store"]
    if retail_articles and non_retail_articles:
        return [
            event_from_article_group(event, retail_articles),
            event_from_article_group(event, non_retail_articles),
        ]
    if "mixed relevance tiers" in event.merge_warnings:
        non_weak_articles = [article for article in event.articles if article.relevance_tier != "weak"]
        weak_articles = [article for article in event.articles if article.relevance_tier == "weak"]
        non_weak_facets: set[str] = set()
        for article in non_weak_articles:
            non_weak_facets |= effective_topic_facets(article_primary_facets(article)) - LOW_CONFIDENCE_MERGE_FACETS
        if non_weak_articles and weak_articles and non_weak_facets:
            weak_same_topic: list[Article] = []
            weak_split: list[Article] = []
            for article in weak_articles:
                article_facets = effective_topic_facets(article_primary_facets(article)) - LOW_CONFIDENCE_MERGE_FACETS
                if article_facets and article_facets & non_weak_facets:
                    weak_same_topic.append(article)
                else:
                    weak_split.append(article)
            if weak_split:
                return [
                    event_from_article_group(event, [*non_weak_articles, *weak_same_topic]),
                    *[event_from_article_group(event, [article]) for article in weak_split],
                ]
    if "mixed primary topic facets" not in event.merge_warnings:
        return [event]
    splittable_event = (
        event.category == "hardware_products"
        or event.event_kind == "hardware_market"
        or event.event_kind == "service_content"
        or bool(event_splittable_topic_facets(event))
    )
    if not splittable_event:
        return [event]

    groups: dict[tuple[str, ...], list[Article]] = {}
    unassigned: list[Article] = []
    for article in event.articles:
        facets = article_splittable_topic_facets(article)
        if not facets:
            unassigned.append(article)
            continue
        groups.setdefault(tuple(sorted(facets)), []).append(article)

    if len(groups) < 2:
        return [event]
    shared_group_facets = set.intersection(*(set(key) for key in groups)) if groups else set()
    if shared_group_facets & NO_SPLIT_SHARED_CORE_TOPIC_FACETS:
        groups_have_specific_facets = any(set(key) - NO_SPLIT_SHARED_CORE_TOPIC_FACETS for key in groups)
        if not groups_have_specific_facets:
            return [event]

    for article in unassigned:
        if article.relevance_tier == "weak":
            groups.setdefault((f"weak:{normalize_url(article.url)}",), []).append(article)
            continue
        if article.event_kind not in {event.event_kind, "general_company"}:
            groups.setdefault((f"kind:{article.event_kind}:{normalize_url(article.url)}",), []).append(article)
            continue
        key = best_topic_group_for_article(article, groups)
        if key is None:
            return [event]
        groups[key].append(article)

    return [event_from_article_group(event, articles) for articles in groups.values()]


def split_mixed_topic_events(events: list[Event]) -> list[Event]:
    split_events: list[Event] = []
    for event in events:
        split_events.extend(split_mixed_topic_event(event))
    return split_events


def cluster_articles(articles: list[Article]) -> list[Event]:
    events: list[Event] = []
    for article in sorted(articles, key=lambda item: item.published_utc):
        matched: Event | None = None
        for event in events:
            if should_merge(article, event):
                matched = event
                break
        if matched:
            matched.articles.append(article)
            matched.tokens |= article.tokens
            if article.published_utc < matched.published_utc:
                matched.published_utc = article.published_utc
                matched.published_raw = article.published_raw
                matched.published_source = article.published_source
                matched.confidence = article.confidence
            if matched.category != article.category:
                categories = [item.category for item in matched.articles]
                matched.category = max(set(categories), key=categories.count)
            kinds = [item.event_kind for item in matched.articles]
            matched.event_kind = max(set(kinds), key=kinds.count)
            matched.relevance_tier, matched.relevance_reason = event_relevance_tier(matched.articles)
            matched.regions = set().union(*(item.regions for item in matched.articles))
            matched.merge_warnings = event_merge_warnings(matched.articles)
            matched.title, matched.summary, matched.key_facts = build_event_summary(matched.articles)
            refresh_event_metadata(matched)
        else:
            title, summary, key_facts = build_event_summary([article])
            event_id = hashlib.sha1(
                f"{article.published_utc.isoformat()} {article.title}".encode("utf-8")
            ).hexdigest()[:12]
            event = Event(
                event_id=event_id,
                category=article.category,
                title=title,
                summary=summary,
                key_facts=key_facts,
                published_utc=article.published_utc,
                published_raw=article.published_raw,
                published_source=article.published_source,
                confidence=article.confidence,
                articles=[article],
                tokens=set(article.tokens),
                event_kind=article.event_kind,
                relevance_tier=article.relevance_tier,
                relevance_reason=article.relevance_reason,
                regions=set(article.regions),
                merge_warnings=event_merge_warnings([article]),
            )
            refresh_event_metadata(event)
            events.append(event)
    consolidated = consolidate_events(events)
    split_events = split_mixed_topic_events(consolidated)
    return sorted(consolidate_events(split_events), key=lambda event: event.published_utc)


def source_link(source: str, url: str, markdown: bool = True) -> str:
    if markdown:
        return f"[{source}]({url})"
    return source


def event_to_dict(event: Event, local_tz: Any) -> dict[str, Any]:
    sorted_articles = sorted(
        event.articles,
        key=lambda item: (SOURCE_PRIORITY.get(item.source, 99), item.published_utc),
    )
    sources = []
    seen_sources: set[tuple[str, str]] = set()
    for article in sorted_articles:
        key = (article.source, normalize_url(article.url))
        if key in seen_sources:
            continue
        seen_sources.add(key)
        sources.append({"name": article.source, "url": article.url})
    event_dict = {
        "id": event.event_id,
        "category": event.category,
        "event_kind": event.event_kind,
        "relevance_tier": event.relevance_tier,
        "relevance_reason": event.relevance_reason,
        "regions": sorted(event.regions),
        "merge_warnings": event.merge_warnings,
        "title": event.title,
        "summary": event.summary,
        "key_facts": event.key_facts,
        "published": {
            "raw": event.published_raw,
            "source": event.published_source,
            "confidence": event.confidence,
            "utc": event.published_utc.isoformat(),
            "local": event.published_utc.astimezone(local_tz).isoformat(),
        },
        "sources": sources,
    }
    must_include = event_must_include_facts(event)
    if must_include:
        event_dict["must_include_facts"] = must_include
    return event_dict


def build_final_brief_queue(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        sources = event.get("sources", [])
        item = {
            "index": index,
            "id": event.get("id"),
            "required": True,
            "coverage_rule": FINAL_BRIEF_ITEM_COVERAGE_RULE,
            "omission_not_allowed_for": FINAL_BRIEF_OMISSION_NOT_ALLOWED_FOR,
            "category": event.get("category"),
            "event_kind": event.get("event_kind"),
            "relevance_tier": event.get("relevance_tier"),
            "relevance_reason": event.get("relevance_reason"),
            "title": event.get("title"),
            "source_names": [source.get("name") for source in sources if source.get("name")],
            "source_urls": [source.get("url") for source in sources if source.get("url")],
        }
        must_include = event.get("must_include_facts", [])
        if must_include:
            item["must_include_facts"] = must_include
        queue.append(item)
    return queue


def required_final_brief_titles(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = []
    for item in queue:
        entry = {
            "index": item.get("index"),
            "event_id": item.get("id"),
            "required": item.get("required"),
            "separate_bullet_by_default": True,
            "coverage_rule": item.get("coverage_rule"),
            "omission_not_allowed_for": item.get("omission_not_allowed_for", []),
            "category": item.get("category"),
            "title": item.get("title"),
            "sources": item.get("source_names", []),
        }
        must_include = item.get("must_include_facts", [])
        if must_include:
            entry["must_include_facts"] = must_include
        required.append(entry)
    return required


def render_brief_scaffold(data: dict[str, Any]) -> str:
    category_titles = [
        ("software_systems", "软件与系统"),
        ("hardware_products", "硬件与产品"),
    ]
    events = data.get("events", [])
    lines: list[str] = [
        "# Apple 24H Brief Coverage Checklist",
        "",
        "Use every item below as a required final-brief boundary unless source review proves duplicate coverage of the same subject and action.",
        "Do not omit an item merely because it is single-source, speculative, lower-profile, competitor-adjacent, or less prominent than same-day major news.",
        "",
    ]
    for category, title in category_titles:
        lines.append(f"**{title}**")
        lines.append("")
        selected = [event for event in events if event.get("category") == category]
        if not selected:
            lines.append("- 在指定时间窗口内，该分类下没有发现符合条件的新闻。")
            lines.append("")
            continue
        for event in selected:
            source_bits = [
                source_link(source["name"], source["url"], markdown=True)
                for source in event.get("sources", [])
            ]
            source_text = "，".join(source_bits) if source_bits else "来源缺失"
            must_include = [
                clean_sentence(fact)
                for fact in event.get("must_include_facts", [])
                if clean_sentence(fact)
            ]
            detail_text = f"；必收细节：{' '.join(must_include)}" if must_include else ""
            lines.append(f"- {event.get('title') or '未命名事件'}{detail_text} （来源：{source_text}）")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(data: dict[str, Any]) -> str:
    category_titles = [
        ("software_systems", "软件与系统"),
        ("hardware_products", "硬件与产品"),
    ]
    events = data.get("events", [])
    lines: list[str] = []
    for category, title in category_titles:
        lines.append(f"**{title}**")
        lines.append("")
        selected = [event for event in events if event.get("category") == category]
        if not selected:
            lines.append("在指定时间窗口内，该分类下没有发现符合条件的新闻。")
            lines.append("")
            continue
        for index, event in enumerate(selected, start=1):
            source_bits = [
                source_link(source["name"], source["url"], markdown=True)
                for source in event.get("sources", [])
            ]
            source_text = "，".join(source_bits) if source_bits else "来源缺失"
            summary = clean_sentence(event.get("summary") or event.get("title") or "")
            key_facts = [
                clean_sentence(fact)
                for fact in event.get("key_facts", [])
                if clean_sentence(fact)
            ]
            remaining_facts = [
                fact
                for fact in key_facts
                if fact.lower()[:120] not in summary.lower()
            ]
            if remaining_facts:
                summary = f"{summary} Key facts: {' '.join(remaining_facts)}"
            lines.append(f"{index}. {summary} （来源：{source_text}）")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def fallback_queries(now_local: datetime) -> list[str]:
    dates = [
        now_local.strftime("%Y-%m-%d"),
        (now_local - timedelta(days=1)).strftime("%Y-%m-%d"),
    ]
    domains = [
        "macrumors.com",
        "9to5mac.com",
        "appleinsider.com",
        "theverge.com",
        "ithome.com",
        "ifanr.com",
        "mydrivers.com",
        "cnbeta.com.tw",
    ]
    queries = []
    for domain in domains:
        for date in dates:
            queries.append(f"site:{domain} Apple OR 苹果 {date}")
    return queries


def write_output_file(path: str, data: dict[str, Any], output_format: str) -> Path:
    output_path = Path(path).expanduser()
    if output_path.exists() and output_path.is_dir():
        raise RuntimeError(f"Output path is a directory: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    if output_format == "json":
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = render_markdown(data)
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, output_path)
    return output_path


def brief_scaffold_path(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_suffix(".brief.md")
    return output_path.with_name(f"{output_path.name}.brief.md")


def write_brief_scaffold_file(output_path: Path, data: dict[str, Any]) -> Path:
    brief_path = brief_scaffold_path(output_path)
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = brief_path.with_name(f".{brief_path.name}.tmp")
    text = data.get("final_brief_markdown") or render_brief_scaffold(data)
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, brief_path)
    return brief_path


def run(args: argparse.Namespace) -> dict[str, Any]:
    global FETCH_RETRIES, FETCH_TIMEOUT
    FETCH_TIMEOUT = args.timeout
    FETCH_RETRIES = args.retries

    local_tz, timezone_diagnostics = detect_timezone(args.timezone)
    now_local = datetime.now(local_tz)
    now_utc = now_local.astimezone(timezone.utc)
    window_start_utc = now_utc - timedelta(hours=args.hours)
    diagnostics: dict[str, Any] = {
        "timezone": timezone_diagnostics,
        "failed_sources": [],
        "failed_fetches": [],
        "low_confidence_articles": [],
        "selected_detail_fetch_failures": [],
        "source_detail_selection_counts": {},
        "source_discovery_fallback_counts": {},
        "source_candidate_counts": {},
        "source_article_counts": {},
    }
    cache_dir = prepare_cache_dir(Path(args.cache_dir), diagnostics)

    sources = build_sources(now_local)
    sources_by_name = {source.name: source for source in sources}
    candidates: list[Candidate] = []
    for source in sources:
        candidates.extend(collect_candidates(source, cache_dir, diagnostics))

    deduped_candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        normalized = normalize_url(candidate.url)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        deduped_candidates.append(candidate)

    articles: list[Article] = []
    for candidate in select_detail_candidates(
        deduped_candidates,
        sources_by_name,
        args.max_detail_pages,
        window_start_utc,
        now_utc,
    ):
        source = sources_by_name.get(candidate.source)
        if source is None:
            continue
        diagnostics["source_detail_selection_counts"][candidate.source] = (
            diagnostics["source_detail_selection_counts"].get(candidate.source, 0) + 1
        )
        page_text = fetch_url(candidate.url, cache_dir, diagnostics)
        if page_text is None:
            diagnostics["selected_detail_fetch_failures"].append(
                {
                    "source": candidate.source,
                    "url": candidate.url,
                    "title": candidate.title,
                    "feed_time_raw": candidate.feed_time_raw,
                    "discovered_from": candidate.discovered_from,
                }
            )
            (
                title,
                summary,
                key_facts,
                published_utc,
                published_raw,
                published_source,
                confidence,
            ) = fallback_article_from_discovery(candidate, source, diagnostics)
            if published_utc is not None:
                diagnostics["source_discovery_fallback_counts"][candidate.source] = (
                    diagnostics["source_discovery_fallback_counts"].get(candidate.source, 0) + 1
                )
        else:
            (
                title,
                summary,
                key_facts,
                published_utc,
                published_raw,
                published_source,
                confidence,
            ) = extract_article(
                candidate,
                source,
                page_text,
                diagnostics,
            )
        if published_utc is None:
            continue
        if not (window_start_utc < published_utc <= now_utc):
            continue
        is_roundup = is_roundup_article_title(candidate.title)
        if not is_roundup:
            summary = combine_summaries(summary, candidate.summary)
        for article_title, article_summary, article_key_facts in roundup_article_variants(
            candidate.title,
            title,
            summary,
            key_facts,
        ):
            variant_context = context_for_article_variant(is_roundup, candidate.context)
            if not is_relevant_candidate(
                Candidate(
                    source=candidate.source,
                    url=candidate.url,
                    title=article_title,
                    summary=article_summary,
                    feed_time_raw=candidate.feed_time_raw,
                    context=variant_context,
                ),
                source,
            ):
                continue
            event_context_summary = " ".join(part for part in [article_summary, variant_context] if part)
            category = choose_category(article_title, event_context_summary)
            token_base = article_summary[:700] if is_roundup else candidate.summary or article_summary[:700]
            token_summary = " ".join([token_base, variant_context, *article_key_facts[:5]])
            tokens = article_tokens(article_title, token_summary)
            event_kind = detect_event_kind(article_title, event_context_summary, article_key_facts)
            relevance_tier, relevance_reason = classify_relevance_tier(
                article_title,
                event_context_summary,
                article_key_facts,
                candidate.source,
            )
            regions = extract_regions(" ".join([article_title, article_summary, variant_context, *article_key_facts[:5]]))
            articles.append(
                Article(
                    source=candidate.source,
                    url=candidate.url,
                    title=article_title,
                    summary=article_summary,
                    key_facts=article_key_facts,
                    category=category,
                    published_utc=published_utc,
                    published_raw=published_raw,
                    published_source=published_source,
                    confidence=confidence,
                    tokens=tokens,
                    event_kind=event_kind,
                    relevance_tier=relevance_tier,
                    relevance_reason=relevance_reason,
                    regions=regions,
                )
            )
            diagnostics["source_article_counts"][candidate.source] = (
                diagnostics["source_article_counts"].get(candidate.source, 0) + 1
            )

    events_all = cluster_articles(articles)
    events = [event for event in events_all if event.relevance_tier != "weak"]
    deferred_events = [event for event in events_all if event.relevance_tier == "weak"]
    diagnostics["event_counts"] = {
        "total": len(events_all),
        "included": len(events),
        "deferred": len(deferred_events),
    }
    event_dicts = [event_to_dict(event, local_tz) for event in events]
    deferred_event_dicts = [event_to_dict(event, local_tz) for event in deferred_events]
    final_brief_queue = build_final_brief_queue(event_dicts)
    required_titles = required_final_brief_titles(final_brief_queue)
    data: dict[str, Any] = {
        "generated_at": now_utc.isoformat(),
        "timezone": {
            "requested": args.timezone,
            "resolved": timezone_diagnostics.get("resolved"),
            "method": timezone_diagnostics.get("method"),
            "iana": timezone_diagnostics.get("iana"),
        },
        "window": {
            "hours": args.hours,
            "start_utc": window_start_utc.isoformat(),
            "end_utc": now_utc.isoformat(),
            "start_local": window_start_utc.astimezone(local_tz).isoformat(),
            "end_local": now_utc.astimezone(local_tz).isoformat(),
        },
        "final_brief_coverage": {
            "source": "events",
            "required_event_count": len(event_dicts),
            "rule": FINAL_BRIEF_ITEM_COVERAGE_RULE,
            "omission_not_allowed_for": FINAL_BRIEF_OMISSION_NOT_ALLOWED_FOR,
        },
        "final_brief_queue": final_brief_queue,
        "required_final_brief_titles": required_titles,
        "events": event_dicts,
        "deferred_events": deferred_event_dicts,
    }
    data["final_brief_markdown"] = render_brief_scaffold({"events": event_dicts})

    if args.include_diagnostics:
        diagnostics["fallback_queries"] = fallback_queries(now_local)
        data["diagnostics"] = diagnostics

    return data


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect recent 24-hour Apple software and hardware news.",
    )
    parser.add_argument("--hours", type=float, default=24.0, help="Lookback window in hours.")
    parser.add_argument(
        "--timezone",
        default="auto",
        help="IANA timezone name or 'auto' to detect the system timezone.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help="Directory for saving successful HTTP responses for diagnostics.",
    )
    parser.add_argument(
        "--output",
        help="Write the full crawler result to this file and print only a short status JSON.",
    )
    parser.add_argument(
        "--include-diagnostics",
        action="store_true",
        help="Include source failures and low-confidence timestamp notes.",
    )
    parser.add_argument(
        "--max-detail-pages",
        type=int,
        default=DEFAULT_MAX_DETAIL_PAGES,
        help="Maximum candidate detail pages to open after discovery.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=FETCH_TIMEOUT,
        help="HTTP timeout per request in seconds.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=FETCH_RETRIES,
        help="Network retries per URL after the first attempt.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        data = run(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.output:
        output_target = Path(args.output).expanduser()
        if args.format == "json":
            data["brief_output"] = str(brief_scaffold_path(output_target))
        output_path = write_output_file(args.output, data, args.format)
        brief_output_path = None
        if args.format == "json":
            brief_output_path = write_brief_scaffold_file(output_path, data)
        status = {
            "ok": True,
            "events": len(data.get("events", [])),
            "required_final_brief_events": len(data.get("final_brief_queue", [])),
            "required_final_brief_titles": data.get("required_final_brief_titles", []),
            "format": args.format,
            "output": str(output_path),
            "coverage_source": "Use required_final_brief_titles plus brief_output as the coverage checklist, then enrich from output events/key_facts; do not omit required items merely because they are single-source, speculative, lower-profile, or competitor-adjacent.",
        }
        if brief_output_path is not None:
            status["brief_output"] = str(brief_output_path)
        print(json.dumps(status, ensure_ascii=False, sort_keys=True))
        return 0
    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(data), end="")
        if args.include_diagnostics:
            print("\n<!-- diagnostics")
            print(json.dumps(data.get("diagnostics", {}), ensure_ascii=False, indent=2))
            print("-->")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
