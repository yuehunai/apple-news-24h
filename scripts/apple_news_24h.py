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
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

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
DEFAULT_MAX_DETAIL_PAGES = 300
FETCH_TIMEOUT = 8.0
FETCH_RETRIES = 1
DEFAULT_CACHE_DIR = Path(tempfile.gettempdir()) / "apple-news-24h"
CACHE_MARKER_FILENAME = ".apple-news-24h-cache"

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
    "donation",
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
    "it早报",
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
    "article",
    "blog",
    "media",
    "post",
    "published",
    "showcase",
    "shown",
    "today",
    "yesterday",
    "发布",
    "报道",
    "消息",
    "展示",
    "苹果",
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
MAX_KEY_FACTS = 10
MAX_OFFICIAL_KEY_FACTS = 18

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
    "价格": "price",
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


def term_present(text: str, term: str) -> bool:
    if term.lower() == "wwdc":
        return re.search(r"(?<![a-z0-9])wwdc(?:\d{0,4})?(?![a-z0-9])", text.lower()) is not None
    if any(ord(ch) > 127 for ch in term):
        return term in text
    escaped = re.escape(term.lower())
    if " " in term or term in {"ios", "macos", "ipados", "watchos", "tvos", "visionos"}:
        return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None
    return re.search(rf"\b{escaped}\b", text) is not None


def score_terms(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(1 for term in terms if term_present(lower, term.lower()))


def has_apple_chip_context(text: str) -> bool:
    lower = text.lower()
    return score_terms(lower, APPLE_CHIP_CONTEXT_TERMS) > 0


def effective_apple_term_score(text: str) -> int:
    lower = text.lower()
    score = 0
    for term in APPLE_TERMS:
        normalized = term.lower()
        if normalized in BARE_APPLE_CHIP_TERMS and not has_apple_chip_context(lower):
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


def is_apple_research_candidate(text: str) -> bool:
    if effective_apple_term_score(text) <= 0:
        return False
    research_score = score_terms(text, APPLE_RESEARCH_ANCHOR_TERMS)
    action_score = score_terms(text, APPLE_RESEARCH_ACTION_TERMS)
    if "cvpr" in text.lower() and action_score > 0:
        return True
    return research_score >= 2 and action_score > 0


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
    "support for",
    "supports",
    "adds",
    "expands",
    "native support",
    "plan, write, and review",
    "集成",
    "接入",
    "支持",
    "新增",
    "扩展",
]

OFFICIAL_APPLE_ACCESSORY_TERMS = [
    "travel case",
    "case",
    "accessory",
    "accessories",
    "apple store online",
    "保护套",
    "旅行保护套",
    "配件",
]

OFFICIAL_APPLE_ACCESSORY_ACTION_TERMS = [
    "discontinuing",
    "discontinued",
    "unavailable",
    "no longer available",
    "removed from",
    "pulled from",
    "sold out",
    "下架",
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
    "all the new",
    "feature list",
    "features list",
    "主要更新点",
    "一文汇总",
    "汇总",
    "总览",
]


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
    return score_terms(lower, APPLE_DEVELOPER_TOOL_ACTION_TERMS) > 0


def is_official_apple_accessory_market_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(lower, OFFICIAL_APPLE_ACCESSORY_TERMS) <= 0:
        return False
    return score_terms(lower, OFFICIAL_APPLE_ACCESSORY_ACTION_TERMS) > 0


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
    wallet_feature_terms = [
        "passport",
        "driver's license",
        "digital id",
        "id support",
        "boarding pass",
        "passes",
        "hotel key",
        "car key",
        "transit card",
        "payment card",
        "tap to share",
        "护照",
        "驾驶证",
        "数字证件",
        "证件",
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
        and score_terms(lower, ["wallet", "钱包", "pay", "支付"]) > 0
    )


def is_apple_os_support_compatibility_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if is_competitor_apple_marketing_comparison(text):
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


def is_routine_recap_comparison_or_buying_advice(title: str, text: str) -> bool:
    lower = text.lower()
    title_lower = title.lower()
    if score_terms(
        title_lower,
        ["top stories", "recap", "weekly recap", "roundup", "this week", "本周回顾", "一周", "汇总"],
    ) > 0:
        return True
    if is_apple_os_support_compatibility_story(text):
        return False
    if is_competitor_apple_marketing_comparison(text):
        return True
    if has_apple_first_party_release_context(lower) or is_apple_developer_tool_story(lower):
        return False
    if is_official_apple_accessory_market_story(lower) or is_unreleased_beats_hardware_story(lower):
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
            "购机",
            "购买建议",
            "换机周期",
            "几年换",
            "最划算",
            "保值率",
        ],
    ) > 0:
        return True
    if re.search(r"(?i)(?:\bvs\.?\b|\bversus\b|compared|comparison|对比|较量)", title):
        return True
    if "hands-on" in title_lower and score_terms(
        lower,
        ["third-party", "belkin", "anker", "satechi", "amazon", "pricing", "price", "第三方", "售价"],
    ) > 0:
        return True
    return False


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
        score_terms(lower, ["apple car", "project titan", "苹果汽车", "苹果造车", "自动驾驶项目", "汽车项目"]) > 0
        and score_terms(
            lower,
            ["test site", "testing site", "proving ground", "test track", "facility", "site", "测试场", "试验场", "测试设施", "场地"],
        )
        > 0
        and score_terms(lower, ["bought", "acquired", "sold", "sale", "purchase", "waymo", "买下", "收购", "出售", "购入"]) > 0
    )


def has_direct_apple_subject_context(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if (
        is_apple_developer_tool_story(lower)
        or is_official_apple_accessory_market_story(lower)
        or is_unreleased_beats_hardware_story(lower)
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
        return True
    return not has_direct_apple_subject_context(text)


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
    if has_apple_first_party_release_context(lower) or is_apple_developer_tool_story(lower):
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
            "launch",
            "launches",
            "released",
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
            r"(?:no|not|without|never|没有|未|尚未|无|并未|不(?:会|能|是)?)"
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
            r"(?:no|not|without|never|没有|未|尚未|无|并未|不(?:会|能|是)?)"
            r"[^。.!?]{0,32}"
            + re.escape(term.lower()),
            re.I,
        )
        if pattern.search(lower):
            continue
        score += 1
    return score


def is_relevant_candidate(candidate: Candidate, source: Source) -> bool:
    url_lower = candidate.url.lower()
    if any(fragment in url_lower for fragment in URL_EXCLUDE_FRAGMENTS):
        return False
    text = f"{candidate.title} {candidate.summary} {candidate.context}"
    lower_text = text.lower()
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
    if is_apple_developer_tool_story(text):
        return True
    if is_official_apple_accessory_market_story(text):
        return True
    if is_unreleased_beats_hardware_story(text):
        return True
    if is_apple_research_candidate(text):
        return True
    if is_apple_health_data_research_candidate(text):
        return True
    if is_messages_platform_candidate(text):
        return True
    if detect_event_kind(candidate.title, candidate.summary) == "ecosystem_interop":
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
    r"official\s+apple\s+store\s+on\s+amazon",
    r"amazon\s+prime\s+day\s+\d{4}",
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
        r"advertis|ad-container|affiliate|post-nav|sharedaddy|social|share)"
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
        if len(text) >= 30:
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
        if len(cleaned) >= 30:
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
    if len(value) < 35 or fact_noise(value):
        return False
    numbers = data_value_count(value)
    has_context = score_terms(value, FACT_CONTEXT_TERMS) > 0
    has_feature_list = FEATURE_LIST_PATTERN.search(value) is not None
    has_list_shape = tag in {"li", "tr"} or len(re.findall(r"[,;；、，]", value)) >= 2
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


def add_unique_text(parts: list[str], seen: set[str], value: str, max_chars: int = 900) -> bool:
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
    if len(cleaned) < 35:
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
                add_unique_text(facts, seen, candidate)
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


def os_feature_component_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    facets: set[str] = set()
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
        score_terms(lower, ["watchos", "apple watch"]) > 0
        and score_terms(lower, ["siri app", "find my app", "find devices", "find items", "find people", "siri 应用", "查找应用"]) > 0
    ):
        facets.add("watchos-siri-findmy-apps")
    if (
        score_terms(lower, ["carplay"]) > 0
        and score_terms(lower, ["route sharing", "route", "navigation", "路线共享", "路线", "导航"]) > 0
    ):
        facets.add("carplay-route-sharing")
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
    if score_terms(lower, ["livecommunicationkit", "callkit", "voip", "全屏来电", "锁屏", "来电显示", "默认通话应用"]) > 0:
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


def topic_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    facets: set[str] = set()
    facets |= os_feature_component_facets_from_text(lower)
    if is_vision_pro_spatial_experience_story(lower):
        facets.add("vision-pro-spatial-experience")
    if (
        score_terms(lower, ["beats"]) > 0
        and score_terms(lower, ["headphone", "headphones", "earbuds", "耳机", "耳罩"]) > 0
    ):
        facets.add("beats-headphones")
    if (
        score_terms(lower, ["iphone"]) > 0
        and score_terms(lower, ["dummy", "mockup", "color", "colors", "dark cherry", "机模", "配色", "颜色", "深樱桃", "浅蓝", "深灰"]) > 0
    ):
        facets.add("iphone-color-mockup")
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
    if score_terms(lower, ["apple music", "music app", "苹果音乐"]) > 0:
        facets.add("apple-music")
    if (
        score_terms(lower, ["apple tv", "苹果电视"]) > 0
        and score_terms(lower, ["remote", "siri remote", "home screen", "遥控器", "主屏幕"]) > 0
    ):
        facets.add("apple-tv-remote")
    elif score_terms(lower, ["apple tv", "apple tv+", "苹果电视"]) > 0:
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
    if score_terms(lower, ["call context", "phone app", "customer service calls", "通话", "来电", "订单号"]) > 0:
        facets.add("phone-call-context")
    return facets


def merge_guard_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    facets: set[str] = set()
    facets |= os_feature_component_facets_from_text(lower)
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
    if (
        score_terms(lower, OS_FEATURE_ACTION_TERMS) > 0
        and score_terms(lower, ["app", "application", "built-in app", "messages app", "phone app", "walkie-talkie", "应用", "内置应用", "对讲机"]) > 0
        and facets
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


BROAD_TOPIC_FACETS = {"os-compatibility", "hardware-roadmap"}


def primary_topic_facets(title: str, summary: str = "") -> set[str]:
    title_facets = topic_facets_from_text(title)
    if title_facets and (title_facets - BROAD_TOPIC_FACETS):
        return title_facets
    combined_facets = topic_facets_from_text(f"{title} {summary}")
    return combined_facets or title_facets


def primary_merge_guard_facets(title: str, summary: str = "") -> set[str]:
    title_facets = merge_guard_facets_from_text(title)
    if title_facets and merge_guard_action_facets(title_facets):
        return title_facets
    combined_facets = merge_guard_facets_from_text(f"{title} {summary}")
    return combined_facets or title_facets


def article_primary_facets(article: Article) -> set[str]:
    return primary_topic_facets(article.title, article.summary)


def event_primary_facets(event: Event) -> set[str]:
    facets: set[str] = set()
    for article in event.articles:
        facets |= article_primary_facets(article)
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
    article_platforms = merge_guard_platform_facets(article_facets)
    event_platforms = merge_guard_platform_facets(event_facets)
    article_actions = merge_guard_action_facets(article_facets)
    event_actions = merge_guard_action_facets(event_facets)
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
    if (
        score_terms(lower, ["airdrop", "隔空投送"]) > 0
        and score_terms(
            lower,
            ["quick share", "nearby share", "google", "pixel", "android", "cross-platform", "interoperability", "谷歌", "安卓", "互通"],
        )
        > 0
    ):
        return "ecosystem_interop"
    if is_apple_developer_tool_story(text):
        return "developer_tool"
    if is_official_apple_accessory_market_story(text):
        return "hardware_market"
    if is_unreleased_beats_hardware_story(text):
        return "hardware_market"
    if is_apple_car_asset_story(text):
        return "hardware_market"
    if is_routine_recap_comparison_or_buying_advice(title, text):
        return "general_company"
    if is_apple_health_data_research_candidate(text):
        return "health_research"
    if is_apple_research_candidate(text):
        return "apple_research"
    if is_messages_platform_candidate(text):
        return "messages_platform"
    if app_store_policy_score(lower) > 0:
        return "app_store_trust"
    if is_third_party_platform_availability_candidate(text):
        return "third_party_ecosystem"
    if is_routine_third_party_apple_platform_story(text):
        return "third_party_ecosystem"
    if is_apple_wallet_feature_story(text):
        return "wallet_feature"
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
    service_core_score = score_terms(
        lower,
        ["apple tv", "apple tv+", "apple music", "apple arcade", "streaming", "movie", "film", "classical", "original film", "苹果电视", "苹果音乐", "电影"],
    )
    service_series_score = score_terms(lower, ["series", "season", "剧集"])
    if service_core_score > 0 or (service_series_score > 0 and score_terms(lower, ["apple tv", "streaming", "original", "苹果电视"]) > 0):
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
            "西锐",
            "音乐生成",
        ],
    )
    if source_name == "Apple Newsroom":
        return "strong", "official Apple source"
    if event_kind == "ecosystem_interop":
        return "ecosystem", "direct Apple ecosystem interoperability or compatibility impact"
    if is_apple_developer_tool_story(text):
        return "strong", "Apple first-party developer tool or Xcode capability change"
    if is_official_apple_accessory_market_story(text):
        return "strong", "Apple official hardware accessory availability change"
    if is_apple_car_asset_story(text):
        return "strong", "Apple vehicle testing asset or hardware-related company action"
    if is_routine_recap_comparison_or_buying_advice(title, text):
        return "weak", "third-party or routine recap, comparison, hands-on, or buying advice without a new Apple action"
    if is_generic_consumer_electronics_health_safety_story(title, text):
        return "weak", "generic consumer-electronics safety story with Apple products used as examples"
    if event_kind == "messages_platform":
        return "strong", "Apple Messages or iMessage platform capability change"
    if is_third_party_platform_availability_candidate(text):
        return "weak", "third-party app or service availability on Apple platforms"
    if event_kind == "third_party_ecosystem" or is_routine_third_party_apple_platform_story(text):
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

    for candidate in candidates:
        normalized_url = normalize_url(candidate.url)
        if not same_domain(candidate.url, source.domains):
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
    kind = article.event_kind if article.event_kind == event.event_kind else event.event_kind
    if kind not in REGION_SENSITIVE_EVENT_KINDS:
        return True
    article_regions = article.regions - {"multi-region"}
    event_regions = event.regions - {"multi-region"}
    if not article_regions or not event_regions:
        return True
    return bool(article_regions & event_regions)


def topic_facets_compatible(article: Article, event: Event) -> bool:
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if not article_facets or not event_facets:
        topic_match = True
    else:
        topic_match = bool(article_facets & event_facets)
    if not topic_match:
        return False
    article_guard_facets = article_merge_guard_facets(article)
    event_guard_facets = event_merge_guard_facets(event)
    if not merge_guard_facets_compatible(article_guard_facets, event_guard_facets):
        return False
    return True


def event_relevance_tier(articles: list[Article]) -> tuple[str, str]:
    priority = {"weak": 0, "ecosystem": 1, "strong": 2}
    selected = max(articles, key=lambda item: priority.get(item.relevance_tier, 0))
    return selected.relevance_tier, selected.relevance_reason


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
    if len(normalized_regions) > 1 and not any(item.event_kind not in REGION_SENSITIVE_EVENT_KINDS for item in articles):
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
    if not topic_facets_compatible(article, event):
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
    strong_shared = {
        token
        for token in shared
        if token not in GENERIC_MERGE_TOKENS
        and not re.fullmatch(r"\d{1,4}", token)
        and token
        not in {"iphone", "ipad", "mac", "ios", "ipados", "macos", "watchos", "tvos", "visionos", "update", "new"}
    }
    if similarity >= 0.38 and len(shared) >= 3:
        return True
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if common_facets and len(strong_shared) >= 3 and similarity >= 0.08:
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


def collect_event_key_facts(articles: list[Article]) -> list[str]:
    ordered = sorted(
        articles,
        key=lambda item: (
            0 if item.source in OFFICIAL_FACT_SOURCES else 1,
            SOURCE_PRIORITY.get(item.source, 99),
            item.published_utc,
        ),
    )
    limit = MAX_OFFICIAL_KEY_FACTS if any(item.source in OFFICIAL_FACT_SOURCES for item in articles) else MAX_KEY_FACTS
    facts: list[str] = []
    seen: set[str] = set()
    for article in ordered:
        for fact in article.key_facts:
            add_unique_text(facts, seen, fact)
            if len(facts) >= limit:
                return facts
    return facts


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
        else:
            title, summary, key_facts = build_event_summary([article])
            event_id = hashlib.sha1(
                f"{article.published_utc.isoformat()} {article.title}".encode("utf-8")
            ).hexdigest()[:12]
            events.append(
                Event(
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
            )
    return sorted(events, key=lambda event: event.published_utc)


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
    return {
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
        summary = combine_summaries(summary, candidate.summary)
        if published_utc is None:
            continue
        if not (window_start_utc < published_utc <= now_utc):
            continue
        if not is_relevant_candidate(
            Candidate(
                source=candidate.source,
                url=candidate.url,
                title=title,
                summary=summary,
                feed_time_raw=candidate.feed_time_raw,
                context=candidate.context,
            ),
            source,
        ):
            continue
        event_context_summary = " ".join(part for part in [summary, candidate.context] if part)
        category = choose_category(title, event_context_summary)
        token_summary = " ".join([candidate.summary or summary[:700], candidate.context, *key_facts[:5]])
        tokens = article_tokens(title, token_summary)
        event_kind = detect_event_kind(title, event_context_summary, key_facts)
        relevance_tier, relevance_reason = classify_relevance_tier(
            title,
            event_context_summary,
            key_facts,
            candidate.source,
        )
        regions = extract_regions(" ".join([title, summary, candidate.context, *key_facts[:5]]))
        articles.append(
            Article(
                source=candidate.source,
                url=candidate.url,
                title=title,
                summary=summary,
                key_facts=key_facts,
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
        "events": [event_to_dict(event, local_tz) for event in events],
        "deferred_events": [event_to_dict(event, local_tz) for event in deferred_events],
    }

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
        output_path = write_output_file(args.output, data, args.format)
        status = {
            "ok": True,
            "events": len(data.get("events", [])),
            "format": args.format,
            "output": str(output_path),
        }
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
