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
import concurrent.futures
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
DEFAULT_DETAIL_FETCH_WORKERS = 10
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
    "apple-music-top-artists",
    "apple-tv-content",
    "apple-tv-content-event-lineup",
    "apple-tv-content-trailer",
    "apple-tv-emmy-nominations",
    "apple-tv-sports-schedule",
    "apple-tv-purchase-4k-upgrade",
    "apple-tv-remote",
    "icloud-home-ai-camera-subscription",
}

SERVICE_CONTENT_DETAIL_TOPIC_FACETS = {
    "apple-music-top-artists",
    "apple-tv-content-event-lineup",
    "apple-tv-content-trailer",
    "apple-tv-emmy-nominations",
    "apple-tv-sports-schedule",
    "apple-tv-purchase-4k-upgrade",
}

APP_STORE_POLICY_SUBTOPIC_FACETS = {
    "app-store-card-payments",
    "apple-pay-rewards",
    "epic-app-store-appeal",
    "uk-cma-app-store-payment-nfc",
}

BEATS_HARDWARE_MERGE_TOKENS = {
    "antonee",
    "robinson",
    "lamine",
    "yamal",
    "beats",
    "cable",
    "cables",
    "charging",
    "power-pink",
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
    "印度": "india",
    "塔塔": "tata",
    "数据泄露": "data-leak",
    "信息泄露": "data-leak",
    "泄露": "leak",
    "窃取": "stolen",
    "被窃取": "stolen",
    "暗网": "dark-web",
    "机密": "confidential",
    "调查": "investigation",
    "计算机应急响应小组": "cert-in",
    "应急响应小组": "cert-in",
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
    "隐藏邮件地址": "hide-my-email",
    "隐藏邮箱": "hide-my-email",
    "真实邮箱": "email",
    "可溯源": "discovered",
    "反查": "discovered",
    "safari 技术预览版": "technology-preview",
    "模型上下文协议": "mcp",
    "智能体": "agent",
    "调试": "debug",
    "长鑫": "cxmt",
    "长鑫存储": "cxmt",
    "长江存储": "ymtc",
    "洽谈": "talks",
    "采购": "buy",
    "俄罗斯": "russia",
    "俄联邦": "russia",
    "反垄断": "antimonopoly",
    "罚款": "fine",
    "预装": "preinstall",
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
    "血糖": "blood-glucose",
    "传感器": "sensor",
    "表带": "band",
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
    macrumors_pages = ["https://www.macrumors.com/", "https://www.macrumors.com/guide/"]
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
                "https://9to5mac.com/wp-json/wp/v2/posts?per_page=100&_embed=wp:term&_fields=link,date_gmt,date,title,excerpt,_links.wp:term,_embedded.wp:term"
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


def fetch_detail_page_texts(
    candidates: list[Candidate],
    cache_dir: Path,
    diagnostics: dict[str, Any],
) -> list[str | None]:
    if not candidates:
        diagnostics["detail_fetch_workers"] = 0
        return []
    workers = min(DEFAULT_DETAIL_FETCH_WORKERS, len(candidates))
    diagnostics["detail_fetch_workers"] = workers
    if workers <= 1:
        return [fetch_url(candidate.url, cache_dir, diagnostics) for candidate in candidates]

    results: list[str | None] = [None] * len(candidates)
    failed_fetches: list[dict[str, Any]] = []

    def fetch_one(index: int, candidate: Candidate) -> tuple[int, str | None, list[dict[str, Any]]]:
        local_diagnostics: dict[str, Any] = {"failed_fetches": []}
        page_text = fetch_url(candidate.url, cache_dir, local_diagnostics)
        return index, page_text, list(local_diagnostics.get("failed_fetches", []))

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(fetch_one, index, candidate): index
            for index, candidate in enumerate(candidates)
        }
        for future in concurrent.futures.as_completed(future_map):
            index = future_map[future]
            try:
                result_index, page_text, local_failed_fetches = future.result()
            except Exception as exc:
                candidate = candidates[index]
                results[index] = None
                failed_fetches.append(
                    {
                        "url": candidate.url,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            results[result_index] = page_text
            failed_fetches.extend(local_failed_fetches)

    diagnostics.setdefault("failed_fetches", []).extend(failed_fetches)
    return results


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


@lru_cache(maxsize=8192)
def term_pattern(term: str) -> re.Pattern[str]:
    if term.lower() == "wwdc":
        return re.compile(r"(?<![a-z0-9])wwdc(?:\d{0,4})?(?![a-z0-9])")
    escaped = re.escape(term.lower())
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


@lru_cache(maxsize=16384)
def term_present(text: str, term: str) -> bool:
    normalized = term.lower()
    if normalized == "wwdc":
        return term_pattern(normalized).search(text.lower()) is not None
    if any(ord(ch) > 127 for ch in term):
        return term in text
    return term_pattern(normalized).search(text) is not None


@lru_cache(maxsize=32768)
def cached_score_terms(lower: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term_present(lower, term))


def score_terms(text: str, terms: Iterable[str]) -> int:
    lower = text.lower()
    normalized_terms = tuple(term.lower() for term in terms)
    return cached_score_terms(lower, normalized_terms)


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


@lru_cache(maxsize=16384)
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
    "beats charging cable",
    "beats charging cables",
    "charging cable",
    "charging cables",
    "magsafe",
    "grip",
    "stand",
    "apple store online",
    "apple online store",
    "保护套",
    "旅行保护套",
    "配件",
    "充电线",
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
    "now available",
    "now available from apple",
    "available from apple",
    "discontinuing",
    "discontinued",
    "unavailable",
    "no longer available",
    "removed from",
    "pulled from",
    "sold out",
    "下架",
    "上架",
    "开售",
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


def is_direct_apple_os_component_change_story(title: str, text: str) -> bool:
    """Prefer a direct OS/component headline over unrelated body context."""
    title_lower = title.lower()
    lead_lower = f"{title} {text[:700]}".lower()
    if score_terms(
        title_lower,
        [
            "apple wallet",
            "car key",
            "digital id",
            "app store",
            "苹果钱包",
            "车钥匙",
            "数字身份证",
            "数字身份",
            "应用商店",
        ],
    ) > 0:
        return False
    if score_terms(
        title_lower,
        ["ios", "ipados", "macos", "watchos", "tvos", "visionos"],
    ) <= 0:
        return False
    if score_terms(
        title_lower,
        [
            "app",
            "application",
            "feature",
            "features",
            "mail",
            "messages",
            "notes",
            "weather",
            "wallet",
            "safari",
            "siri",
            "shortcuts",
            "find my",
            "home",
            "carplay",
            "应用",
            "功能",
            "邮件",
            "信息",
            "备忘录",
            "天气",
            "钱包",
            "快捷指令",
            "查找",
            "家庭",
        ],
    ) <= 0 and score_terms(
        lead_lower,
        ["built-in app", "system-level feature", "内置应用", "系统级功能"],
    ) <= 0:
        return False
    return score_terms(
        title_lower,
        OS_FEATURE_ACTION_TERMS
        + OS_SUMMARY_TERMS
        + [
            "new",
            "what's new",
            "whats new",
            "losing",
            "missing",
            "goes away",
            "going away",
            "retired",
            "discontinued",
            "变化",
            "调整",
            "下线",
            "停用",
        ],
    ) > 0


def is_personal_os_feature_walkthrough_without_new_action(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = f"{title} {text}".lower()
    if score_terms(title_lower, ["ios", "ipados", "macos", "watchos", "tvos", "visionos"]) <= 0:
        return False
    if score_terms(
        title_lower,
        ["my favorite", "our favorite", "favorite features", "hands-on", "walkthrough", "[video]"],
    ) <= 0:
        return False
    if score_terms(
        title_lower,
        [
            "removes",
            "removed",
            "drops",
            "loses",
            "missing",
            "discontinued",
            "announces",
            "released",
            "移除",
            "取消",
            "下线",
            "停用",
            "发布",
            "宣布",
        ],
    ) > 0:
        return False
    return score_terms(
        lower,
        ["feature", "features", "app", "walkthrough", "quality-of-life", "功能", "应用", "体验"],
    ) > 0


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
    version_values |= {
        match.group(1)
        for match in re.finditer(
            r"(?<![a-z0-9])(?:ios|ipados|macos|watchos|tvos|visionos)\s+(\d{1,2})(?![\d.])",
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
            "testing",
            "internally testing",
            "internal testing",
            "visitor logs",
            "access logs",
            "开发者预览版",
            "测试版",
            "公测",
            "公测版",
            "内部测试",
            "访问日志",
            "网站日志",
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
    platform_groups = {
        "platform-ios": ["ios"],
        "platform-ipados": ["ipados"],
        "platform-macos": ["macos"],
        "platform-watchos": ["watchos"],
        "platform-tvos": ["tvos"],
        "platform-visionos": ["visionos"],
    }
    for facet, terms in platform_groups.items():
        if score_terms(lower, terms) > 0:
            facets.add(facet)
    if facets & {"platform-ios", "platform-ipados"}:
        facets.add("platform-mobile-os")
    if score_terms(lower, ["beta", "betas", "developer beta", "developer betas", "开发者预览版", "测试版", "公测", "公测版"]) > 0:
        facets.add("os-release-beta")
        beta_numbers = set(re.findall(r"(?:beta|测试版|公测版)\s*(\d+)", lower))
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
            if re.search(rf"\b{ordinal}\s+(?:developer\s+)?betas?\b", lower) or (
                re.search(rf"\b{ordinal}\b", lower)
                and score_terms(lower, ["beta", "betas", "developer beta", "developer betas"]) > 0
            ):
                beta_numbers.add(number)
        chinese_ordinal_beta_numbers = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
        }
        for ordinal, number in chinese_ordinal_beta_numbers.items():
            if re.search(rf"第{ordinal}个?(?:开发者)?(?:测试版|公测版)", lower):
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


def platform_facets_compatible(left_facets: set[str], right_facets: set[str]) -> bool:
    left_platforms = merge_guard_platform_facets(left_facets)
    right_platforms = merge_guard_platform_facets(right_facets)
    if not left_platforms or not right_platforms:
        return True
    if left_platforms & right_platforms:
        return True
    mobile_platforms = {"platform-ios", "platform-ipados", "platform-mobile-os"}
    return left_platforms <= mobile_platforms and right_platforms <= mobile_platforms


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
    if not is_os_release_availability_article(article):
        return False
    release_event_articles = [item for item in event.articles if is_os_release_availability_article(item)]
    if not release_event_articles:
        return False
    if os_release_title_specific_facets(article):
        return False
    if any(os_release_title_specific_facets(item) for item in release_event_articles):
        return False
    article_facets = os_release_facets_from_text(article.title)
    event_facets: set[str] = set()
    for item in release_event_articles:
        event_facets |= os_release_facets_from_text(item.title)
    article_versions = os_release_version_facets(article_facets)
    event_versions = os_release_version_facets(event_facets)
    if not article_versions or not event_versions or not (article_versions & event_versions):
        return False
    if not os_release_facets_compatible(article_facets, event_facets):
        return False
    article_channels = os_release_channel_facets(article_facets)
    event_channels = os_release_channel_facets(event_facets)
    return bool(article_channels & event_channels)


def os_release_title_specific_facets(article: Article) -> set[str]:
    return os_release_title_specific_facets_from_title(article.title)


def os_release_title_specific_facets_from_title(title: str) -> set[str]:
    facets = topic_facets_from_text(title)
    release_facets = os_release_version_facets(facets) | os_release_channel_facets(facets)
    platform_facets = merge_guard_platform_facets(facets) | {"platform-mobile-os", "system-summary"}
    specific = facets - release_facets - platform_facets
    if "platform-tvos" in facets:
        specific.discard("apple-tv-content")
    return specific


def is_os_release_availability_title(title: str) -> bool:
    title_lower = title.lower()
    if not os_release_facets_from_text(title):
        return False
    if is_os_point_release_internal_testing_story(title):
        return False
    release_title_terms = [
        "seed",
        "seeds",
        "seeded",
        "release",
        "releases",
        "released",
        "rolls out",
        "rolling out",
        "now available",
        "available",
        "coming soon",
        "expected",
        "patches",
        "patched",
        "fixes",
        "fixed",
        "security update",
        "security updates",
        "发布",
        "推送",
        "即将发布",
        "最快下周",
        "公测版",
        "上线",
        "可用",
        "修复",
        "安全更新",
    ]
    excluded_feature_title_terms = [
        "what's new",
        "whats new",
        "here's what's new",
        "features",
        "adds these",
        "includes",
        "new in",
        "新增",
        "新功能",
        "带来",
        "加入",
    ]
    if score_terms(title_lower, excluded_feature_title_terms) > 0 and score_terms(
        title_lower,
        ["seed", "seeds", "seeded", "release", "releases", "released", "rolls out", "rolling out", "now available", "发布", "推送"],
    ) <= 0:
        return False
    return score_terms(title_lower, release_title_terms) > 0


def is_os_release_availability_article(article: Article) -> bool:
    return is_os_release_availability_title(article.title)


def allowed_url_excluded_candidate(candidate: Candidate, source: Source, text: str) -> bool:
    url_lower = candidate.url.lower()
    if is_safari_mcp_server_story(text):
        return True
    if source.name == "MacRumors" and "/guide/" in url_lower:
        kind = detect_event_kind(candidate.title, candidate.summary, [candidate.context])
        tier, _ = classify_relevance_tier(
            candidate.title,
            candidate.summary,
            [candidate.context],
            candidate.source,
        )
        return is_apple_os_feature_or_summary_story(text) or (
            kind == "os_app"
            and tier == "strong"
            and score_terms(
                candidate.title.lower(),
                ["ios", "ipados", "macos", "watchos", "tvos", "visionos"],
            )
            > 0
        )
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


def is_safari_mcp_server_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple", "苹果", "webkit"]) <= 0:
        return False
    if score_terms(lower, ["safari technology preview", "safari 技术预览版", "safari"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "mcp",
            "model context protocol",
            "mcp server",
            "mcp 服务",
            "mcp 服务器",
            "模型上下文协议",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "coding agent",
            "coding agents",
            "ai agent",
            "ai agents",
            "debug",
            "debugging",
            "inspect",
            "browser automation",
            "web development",
            "console logs",
            "network requests",
            "page elements",
            "智能体",
            "编程智能体",
            "调试",
            "检查网页",
            "控制台日志",
            "网络请求",
            "页面元素",
        ],
    ) > 0


def is_hide_my_email_vulnerability_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "hide my email",
            "icloud+",
            "隐藏邮件地址",
            "隐藏邮箱",
            "隐藏我的电子邮件",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "bug",
            "flaw",
            "vulnerability",
            "privacy flaw",
            "real email",
            "email addresses",
            "exposes",
            "discovered",
            "uncover",
            "100%",
            "漏洞",
            "安全漏洞",
            "隐私漏洞",
            "真实邮箱",
            "真实邮件地址",
            "可溯源",
            "反查",
            "泄露",
            "暴露",
        ],
    ) > 0


def is_russia_fas_app_preinstall_regulation_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "russia",
            "russian",
            "federal antimonopoly service",
            "fas",
            "россия",
            "俄罗斯",
            "俄联邦",
            "联邦反垄断局",
            "反垄断局",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "fine",
            "fines",
            "penalty",
            "threatens",
            "antimonopoly",
            "antitrust",
            "discrimination",
            "discriminatory",
            "preinstall",
            "pre-installed",
            "search engine",
            "search engines",
            "local apps",
            "max",
            "rustore",
            "app discrimination",
            "罚款",
            "整改",
            "威胁",
            "反垄断",
            "歧视",
            "预装",
            "本土应用",
            "本地应用",
            "搜索引擎",
            "40 亿卢布",
            "4 billion",
            "$52 million",
        ],
    ) <= 0:
        return False
    return score_terms(lower, ["iphone", "ipad", "ios", "app store", "apps", "software", "应用", "软件"]) > 0


def is_apple_memory_supplier_sourcing_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "memory",
            "ram",
            "dram",
            "nand",
            "storage chip",
            "storage chips",
            "memory chips",
            "存储芯片",
            "存储",
            "内存",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "cxmt",
            "changxin",
            "changxin memory",
            "ymtc",
            "yangtze memory",
            "长鑫",
            "长鑫存储",
            "长江存储",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "talks",
            "in talks",
            "buy",
            "buying",
            "purchase",
            "procure",
            "procurement",
            "source",
            "sourcing",
            "supplier",
            "suppliers",
            "use",
            "using",
            "devices sold in china",
            "china market",
            "chinese market",
            "谈判",
            "洽谈",
            "采购",
            "购买",
            "采用",
            "供应",
            "供应商",
            "中国市场",
        ],
    ) > 0


def is_third_party_ai_agent_for_mac_without_apple_action(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if has_apple_first_party_release_context(lower):
        return False
    if score_terms(title_lower, ["apple", "苹果", "safari", "xcode", "webkit"]) > 0:
        return False
    if score_terms(
        lower,
        [
            "google",
            "gemini",
            "spark",
            "claude",
            "copilot",
            "chatgpt",
            "openai",
            "perplexity",
            "谷歌",
            "第三方",
        ],
    ) <= 0:
        return False
    if score_terms(lower, ["macos", "mac", "local mac files", "desktop app", "mac app", "mac 用户"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "ai agent",
            "agent",
            "automation",
            "automate",
            "local files",
            "connect to",
            "desktop app",
            "智能体",
            "代理",
            "自动化",
            "本地文件",
        ],
    ) > 0


def is_non_apple_device_comparison_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if has_apple_first_party_release_context(lower):
        return False
    if is_direct_apple_hardware_roadmap_story(lower, title):
        return False
    if is_direct_iphone_hardware_spec_rumor_story(title, lower):
        return False
    if is_apple_display_panel_supply_chain_story(lower) or is_foldable_iphone_supply_chain_story(lower):
        return False
    if score_terms(lower, ["airdrop", "quick share", "nearby share", "interoperability", "cross-platform", "隔空投送", "互通"]) > 0:
        return False
    if score_terms(
        lower,
        [
            "spacex",
            "xai",
            "elon musk",
            "musk",
            "tesla",
            "qualcomm",
            "google",
            "samsung",
            "nubia",
            "zte",
            "oneplus",
            "高通",
            "马斯克",
            "三星",
            "谷歌",
            "努比亚",
            "中兴",
            "一加",
        ],
    ) <= 0:
        return False
    if score_terms(lower, ["iphone", "apple", "苹果"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "thinner than",
            "thinner-than",
            "prototype",
            "handheld",
            "device",
            "phone",
            "smartphone",
            "ai phone",
            "comparison",
            "compared",
            "rival",
            "比 iphone 更薄",
            "薄于 iphone",
            "原型机",
            "设备",
            "手机",
            "ai 手机",
            "智能体手机",
            "对比",
        ],
    ) > 0


def is_third_party_consumer_app_update_on_apple_platform(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    third_party_app_subject_terms = [
        "mlb",
        "major league baseball",
        "netflix",
        "plex",
        "spotify",
        "pocket casts",
        "flighty",
        "whatsapp",
        "google",
        "jamf",
        "ubisoft",
        "tencent",
        "wechat",
        "harmonyos",
        "third-party",
        "third party",
        "第三方",
        "微信",
        "鸿蒙",
        "育碧",
        "腾讯",
    ]
    if title_lower.startswith("apple ") or title_lower.startswith("苹果"):
        return False
    if is_siri_ai_third_party_app_data_access_feature(title, text):
        return False
    if is_apple_strategic_transaction_story(lower) or score_terms(
        lower,
        [
            "joins apple",
            "joining apple",
            "acquired by apple",
            "apple acquisition",
            "apple has taken control",
            "apple acquired",
            "加入苹果",
            "苹果收购",
        ],
    ) > 0:
        return False
    if has_apple_first_party_release_context(lower) and score_terms(title_lower, third_party_app_subject_terms) <= 0:
        return False
    if score_terms(lower, ["airdrop", "quick share", "nearby share", "interoperability", "cross-platform", "隔空投送", "互通"]) > 0:
        return False
    if score_terms(title_lower, ["apple releases", "apple launches", "apple announces", "苹果发布", "苹果推出", "苹果宣布"]) > 0:
        return False
    vendor_score = score_terms(
        lower,
        [
            *third_party_app_subject_terms,
        ],
    )
    if vendor_score <= 0:
        return False
    if score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "ios",
            "ipados",
            "macos",
            "app store",
            "apple tv",
            "vision pro",
            "苹果平台",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "widget",
            "widgets",
            "app update",
            "version",
            "latest version",
            "feature",
            "features",
            "shortcut",
            "control center",
            "lock screen",
            "carplay",
            "apple watch",
            "catalog",
            "games",
            "game catalog",
            "scores",
            "real-time scores",
            "threat hunting",
            "小组件",
            "应用更新",
            "版本",
            "功能",
            "快捷指令",
            "控制中心",
            "锁屏",
            "游戏",
            "目录",
            "实时比分",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "adds",
            "added",
            "includes",
            "include",
            "launches",
            "released",
            "available",
            "drops",
            "requires",
            "fix",
            "fixes",
            "testing",
            "tests",
            "test",
            "new app",
            "new feature",
            "gives",
            "paying for",
            "full catalog",
            "latest version",
            "highlights",
            "推出",
            "上线",
            "新增",
            "更新",
            "测试",
            "灰度测试",
        ],
    ) > 0


def is_third_party_cross_platform_desktop_client_update(title: str, text: str) -> bool:
    """Identify vendor desktop-client releases where Mac is only one target OS."""
    title_lower = title.lower()
    lower = f"{title} {text}".lower()
    if score_terms(
        title_lower,
        ["apple", "macos", "app store", "apple silicon", "苹果", "苹果公司", "苹果平台"],
    ) > 0:
        return False
    if score_terms(title_lower, ["mac", "mac 版", "mac版"]) <= 0:
        return False
    if score_terms(title_lower, ["windows", "win", "pc", "桌面版", "电脑版"]) <= 0:
        return False
    if score_terms(
        title_lower,
        [
            "app",
            "client",
            "desktop",
            "version",
            "beta",
            "test version",
            "客户端",
            "桌面版",
            "电脑版",
            "版本",
            "测试版",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "update",
            "updated",
            "release",
            "released",
            "beta",
            "features",
            "adds",
            "发布",
            "更新",
            "推送",
            "新增",
            "功能",
        ],
    ) > 0


def is_siri_ai_third_party_app_data_access_feature(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(lower, ["siri", "siri ai", "apple intelligence", "苹果智能"]) <= 0:
        return False
    if score_terms(lower, ["ios", "ipados", "developer beta", "beta", "测试版", "开发者测试版"]) <= 0:
        return False
    if score_terms(lower, ["third-party app", "third-party apps", "third party app", "third party apps", "第三方应用"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "pull info",
            "pull information",
            "access information",
            "access info",
            "access data",
            "read data",
            "use third-party apps",
            "remaining battery",
            "request permission",
            "user permission",
            "调取",
            "读取",
            "访问权限",
            "申请应用访问权限",
            "剩余电量",
        ],
    ) > 0


def iphone_physical_dimension_product_families(text: str) -> set[str]:
    lower = text.lower()
    families: set[str] = set()
    for match in re.finditer(r"\biphone\s*(\d{1,2})\s*(pro(?:\s*max)?|ultra|air)?\b", lower):
        generation = match.group(1)
        tier = re.sub(r"\s+", "-", (match.group(2) or "").strip())
        if tier:
            families.add(f"iphone-{generation}-{tier}")
        else:
            families.add(f"iphone-{generation}")
    for match in re.finditer(r"iphone\s*(\d{1,2})\s*pro", lower):
        families.add(f"iphone-{match.group(1)}-pro")
    for match in re.finditer(r"iphone\s*(\d{1,2})\s*pro\s*max", lower):
        families.add(f"iphone-{match.group(1)}-pro-max")
    return families


def is_iphone_physical_dimension_rumor_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    dimension_terms = [
        "thicker",
        "thickness",
        "heavier",
        "heaviest",
        "weight",
        "weigh",
        "weighs",
        "grams",
        "240 grams",
        "camera bump",
        "camera plateau",
        "camera housing",
        "backplate",
        "aluminum frame",
        "aluminum casing",
        "2mm",
        "2 mm",
        "millimeters thicker",
        "9.9",
        "10.9",
        "11.54",
        "增厚",
        "厚度",
        "变厚",
        "更重",
        "重量",
        "240g",
        "克",
        "机身",
        "后摄平台",
        "摄像头平台",
        "摄像头模组",
        "铝合金中框",
        "铝合金机身",
    ]
    title_families = iphone_physical_dimension_product_families(title_lower)
    if not any(family.endswith("-pro") or family.endswith("-pro-max") for family in title_families):
        return False
    if score_terms(title_lower, dimension_terms) <= 0:
        return False
    product_families = iphone_physical_dimension_product_families(lower)
    if not any(family.endswith("-pro") or family.endswith("-pro-max") for family in product_families):
        return False
    if score_terms(lower, dimension_terms) <= 0:
        return False
    return score_terms(
        lower,
        [
            "leaker",
            "leaks",
            "rumor",
            "rumors",
            "probably",
            "could",
            "expected",
            "may",
            "might",
            "claims",
            "says",
            "point to",
            "points to",
            "report",
            "reported",
            "supply chain",
            "fixed focus",
            "weibo",
            "爆料",
            "传闻",
            "消息称",
            "据称",
            "供应链",
            "定焦数码",
        ],
    ) > 0


def is_apple_executive_government_meeting_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if is_siri_ai_eu_dma_regulatory_meeting_story(lower):
        return False
    if score_terms(
        lower,
        [
            "tim cook",
            "john ternus",
            "apple ceo",
            "apple executive",
            "apple executives",
            "apple chief",
            "库克",
            "苹果高管",
            "苹果 CEO",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "minister-president",
            "minister president",
            "minister",
            "governor",
            "government",
            "state official",
            "official",
            "regulator",
            "european commission",
            "eu",
            "bavaria",
            "munich",
            "州长",
            "部长",
            "政府",
            "官员",
            "监管",
            "巴伐利亚",
            "慕尼黑",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "meeting",
            "met with",
            "held a virtual meeting",
            "discussed",
            "talks",
            "investment",
            "jobs",
            "data protection",
            "overregulation",
            "会面",
            "会议",
            "会谈",
            "讨论",
            "投资",
            "就业",
            "数据保护",
            "监管",
        ],
    ) > 0


def is_apple_executive_event_attendance_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(
        lower,
        [
            "tim cook",
            "john ternus",
            "apple ceo",
            "apple executive",
            "apple executives",
            "apple hardware chief",
            "hardware engineering chief",
            "苹果 ceo",
            "库克",
            "苹果高管",
            "苹果硬件主管",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "conference",
            "retreat",
            "summit",
            "annual meeting",
            "sun valley",
            "allen & co",
            "allen and co",
            "闭门会议",
            "峰会",
            "年会",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "attend",
            "attends",
            "attended",
            "appear",
            "appears",
            "appeared",
            "takes his place",
            "joins",
            "出席",
            "现身",
            "参加",
        ],
    ) > 0


def is_direct_apple_regional_platform_regulation_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    lead_lower = text.lower()[:280]
    primary_age_terms = [
        "age verification",
        "age-verify",
        "age assurance",
        "age-gating",
        "parental consent",
        "年龄验证",
        "年龄核验",
        "家长同意",
    ]
    if score_terms(title_lower, primary_age_terms) <= 0 and score_terms(lead_lower, primary_age_terms) <= 0:
        return False
    if score_terms(
        lower,
        [
            "age verification",
            "age-verify",
            "age assurance",
            "age-gating",
            "child safety",
            "parental consent",
            "年龄验证",
            "年龄核验",
            "儿童安全",
            "家长同意",
        ],
    ) <= 0:
        return False
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "app store",
            "apple id",
            "apple account",
            "apple users",
            "users in texas",
            "age verification",
            "age-verify",
            "age assurance",
            "parental consent",
            "苹果账号",
            "苹果账户",
            "苹果用户",
            "应用商店",
            "年龄验证",
            "家长同意",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "must",
            "requires",
            "requirement",
            "ruling",
            "court",
            "judge",
            "law",
            "state law",
            "regulator",
            "continue",
            "compliance",
            "texas",
            "cma",
            "fas",
            "必须",
            "要求",
            "裁决",
            "法院",
            "法官",
            "法律",
            "监管",
            "继续",
            "合规",
            "德州",
            "得州",
        ],
    ) > 0


def is_direct_apple_regulated_technology_access_story(title: str, text: str) -> bool:
    """Match government controls that directly change Apple's access to technology."""
    title_lower = title.lower()
    lead_lower = f"{title} {text[:900]}".lower()
    if score_terms(title_lower, ["apple", "苹果"]) <= 0:
        return False
    if score_terms(
        lead_lower,
        [
            "government",
            "commerce department",
            "export control",
            "export controls",
            "export license",
            "export licenses",
            "restriction",
            "restrictions",
            "authorization",
            "authorized",
            "controlled technology",
            "监管",
            "政府",
            "出口管制",
            "出口许可",
            "限制",
            "授权",
        ],
    ) <= 0:
        return False
    if score_terms(
        lead_lower,
        [
            "access",
            "eases",
            "eased",
            "allows",
            "allowed",
            "approve",
            "approved",
            "bring",
            "ship",
            "import",
            "export",
            "获得",
            "放宽",
            "允许",
            "批准",
            "进口",
            "出口",
        ],
    ) <= 0:
        return False
    return score_terms(
        lead_lower,
        [
            "chip",
            "chips",
            "server",
            "servers",
            "data center",
            "data centre",
            "advanced computing",
            "equipment",
            "technology",
            "半导体",
            "芯片",
            "服务器",
            "数据中心",
            "设备",
            "技术",
        ],
    ) > 0


CHIP_FOUNDRY_ENTITY_TERMS = {
    "intel": ("intel", "英特尔"),
    "tsmc": ("tsmc", "台积电"),
    "samsung": ("samsung", "三星"),
    "globalfoundries": ("globalfoundries", "格芯"),
}


def chip_foundry_entities(text: str) -> set[str]:
    lower = text.lower()
    return {
        entity
        for entity, terms in CHIP_FOUNDRY_ENTITY_TERMS.items()
        if score_terms(lower, terms) > 0
    }


def is_apple_chip_tariff_exemption_story(title: str, text: str) -> bool:
    """Match a tariff exemption linked to an Apple chip-production commitment."""
    title_lower = title.lower()
    lead_lower = f"{title} {text[:1400]}".lower()
    if score_terms(title_lower, ["apple", "苹果"]) <= 0:
        return False
    if not chip_foundry_entities(lead_lower):
        return False
    if score_terms(
        lead_lower,
        [
            "chip",
            "chips",
            "semiconductor",
            "semiconductors",
            "foundry",
            "fabrication",
            "晶圆厂",
            "半导体",
            "芯片",
            "代工",
        ],
    ) <= 0:
        return False
    if score_terms(
        lead_lower,
        [
            "tariff exemption",
            "tariff exemptions",
            "exemption from",
            "exempt from",
            "avoided semiconductor tariffs",
            "avoid semiconductor tariffs",
            "关税豁免",
            "豁免关税",
            "免征关税",
            "避免半导体关税",
        ],
    ) <= 0:
        return False
    return score_terms(
        lead_lower,
        [
            "deal",
            "agreement",
            "contract",
            "commitment",
            "committed",
            "supply",
            "production",
            "manufacturing",
            "代工协议",
            "代工合作",
            "供应协议",
            "承诺",
            "同意",
            "生产",
            "制造",
            "换取",
        ],
    ) > 0


def is_apple_device_battery_regulation_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone", "iphones", "ipad", "ipads", "apple", "苹果"]) <= 0:
        return False
    if score_terms(lower, ["battery", "batteries", "电池"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "regulation",
            "regulations",
            "law",
            "legislation",
            "rule",
            "rules",
            "requirement",
            "requirements",
            "compliance",
            "exemption",
            "exempt",
            "eu",
            "european union",
            "法规",
            "法律",
            "新规",
            "规定",
            "要求",
            "合规",
            "豁免",
            "欧盟",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "removable",
            "replaceable",
            "user-replaceable",
            "user replaceable",
            "battery replacement",
            "battery removal",
            "可拆卸",
            "可更换",
            "用户更换",
            "更换电池",
            "拆卸电池",
        ],
    ) > 0


def is_direct_apple_airpods_firmware_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(lower, ["airpods", "airpods pro", "airpods max", "beats", "耳机"]) <= 0:
        return False
    if score_terms(lower, ["firmware", "beta firmware", "developer firmware", "固件", "开发固件"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "apple releases",
            "apple released",
            "apple seeds",
            "apple seeded",
            "apple pushes",
            "apple pushed",
            "apple rolls out",
            "苹果发布",
            "苹果推送",
            "苹果释出",
            "苹果向",
        ],
    ) > 0


def is_apple_product_legal_proceeding_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "apple watch",
            "airpods",
            "beats",
            "vision pro",
            "homepod",
            "苹果",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "lawsuit",
            "sue",
            "sues",
            "suing",
            "class-action",
            "class action",
            "court",
            "judge",
            "dismissed",
            "claims",
            "complaint",
            "settlement",
            "诉讼",
            "集体诉讼",
            "法院",
            "法官",
            "驳回",
            "索赔",
            "和解",
        ],
    ) >= 2


def is_ios_signing_status_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(lower, ["ios", "ipados", "iphone", "ipad"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "signing",
            "stops signing",
            "stopped signing",
            "no longer signing",
            "downgrade",
            "downgrading",
            "签名",
            "签署",
            "签名验证",
            "降级",
            "回退",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "stops signing",
            "stopped signing",
            "no longer signing",
            "downgrade",
            "downgrading",
            "关闭",
            "停止",
            "无法再",
            "不能再",
            "回不去",
            "降级",
            "回退",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "apple",
            "ios",
            "iphone",
            "苹果",
        ],
    ) > 0


def is_third_party_browser_security_feature_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if has_apple_first_party_release_context(lower):
        return False
    if score_terms(title_lower, ["safari", "webkit", "technology preview", "苹果", "apple"]) > 0:
        return False
    browser_score = score_terms(
        lower,
        [
            "opera",
            "chrome",
            "firefox",
            "brave",
            "arc browser",
            "edge browser",
            "browser",
            "browsers",
            "浏览器",
        ],
    )
    apple_platform_score = score_terms(
        lower,
        [
            "macos",
            "mac",
            "ios",
            "ipados",
            "iphone",
            "ipad",
            "apple platform",
            "苹果平台",
        ],
    )
    security_feature_score = score_terms(
        lower,
        [
            "security feature",
            "privacy feature",
            "clipboard",
            "paste protect",
            "malicious command",
            "attack",
            "protection",
            "defense",
            "防护",
            "防御",
            "剪贴板",
            "剪切板",
            "恶意命令",
            "攻击",
        ],
    )
    action_score = score_terms(
        lower,
        [
            "launch",
            "launches",
            "launched",
            "introduces",
            "introduced",
            "announces",
            "announced",
            "rolls out",
            "released",
            "推出",
            "发布",
            "宣布",
            "上线",
        ],
    )
    return browser_score > 0 and apple_platform_score > 0 and security_feature_score > 0 and action_score > 0


def is_official_apple_privacy_ad_campaign_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(lower, ["privacy", "app privacy", "tracking transparency", "隐私", "权限", "跟踪透明度"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "apple campaign",
            "apple privacy campaign",
            "apple commercial",
            "apple ad",
            "apple advertisement",
            "苹果新广告",
            "苹果广告",
            "苹果宣传活动",
            "隐私保护宣传活动",
            "发布了一条",
            "主演的影片",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "iphone",
            "app store",
            "app review",
            "privacy label",
            "permission",
            "permissions",
            "app tracking transparency",
            "iphone 管",
            "app 审核",
            "app 隐私标签",
            "app 权限",
            "app 跟踪透明度",
        ],
    ) > 0


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


def is_apple_wallet_car_key_partner_support_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(lower, ["apple wallet", "wallet app", "苹果钱包", "钱包 app", "钱包应用"]) <= 0:
        return False
    if score_terms(lower, ["car key", "car keys", "digital car key", "车钥匙", "数字车钥匙"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "ios",
            "iphone",
            "apple watch",
            "code",
            "codes",
            "beta",
            "support",
            "supports",
            "lucid",
            "xiaomi",
            "automaker",
            "automakers",
            "vehicle",
            "vehicles",
            "代码",
            "测试版",
            "支持",
            "适配",
            "小米",
            "车企",
            "车型",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "points to",
            "hints at",
            "suggests",
            "preparing to add",
            "new automakers",
            "support for",
            "add support",
            "出现",
            "现踪迹",
            "暗示",
            "指向",
            "将适配",
            "未来可用",
        ],
    ) > 0


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
    if score_terms(lower, ["apple arcade", "apple tv+", "apple music", "苹果 arcade", "苹果音乐"]) > 0 and score_terms(
        lower,
        ["adds", "adding", "added", "lands", "coming", "available", "catalog", "games", "episodes", "新增", "上线", "加入", "游戏"],
    ) > 0:
        return False
    if is_direct_iphone_hardware_spec_rumor_story(title, text) or "iphone-battery-capacity-leak" in topic_facets_from_text(f"{title} {text}"):
        return False
    if is_apple_specific_market_share_report_story(text, title):
        return False
    if score_terms(
        title_lower,
        [
            "buying advice",
            "buying guide",
            "should you buy",
            "bad time to buy",
            "buy now or wait",
            "upgrade or wait",
            "which ipad is right",
            "which iphone is right",
            "which mac is right",
            "which apple watch is right",
            "which airpods are right",
            "when is apple releasing",
            "when are new",
            "when is apple's",
            "when is apples",
            "right for you",
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
            "新品前瞻",
            "发布会前瞻",
            "产品前瞻",
            "新品展望",
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
            "which ipad is right",
            "which iphone is right",
            "which mac is right",
            "which apple watch is right",
            "which airpods are right",
            "when is apple releasing",
            "when are new",
            "when is apple's",
            "when is apples",
            "right for you",
            "previous offers",
            "might return",
            "whether they should wait",
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


def is_non_actionable_recap_title(title: str) -> bool:
    title_lower = title.lower().strip()
    return bool(re.match(r"^top stories\b", title_lower))


def is_rumor_feature_recap_without_new_reporting(title: str, text: str) -> bool:
    """Detect list-style rumor recaps that do not report a new Apple event."""
    title_lower = title.lower()
    lower = f"{title} {text}".lower()
    english_list_title = bool(
        re.search(
            r"\b(?:with|these|up to)\s+(?:at least\s+)?"
            r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
            r"(?:new\s+)?features?\b",
            title_lower,
        )
    )
    chinese_roundup_title = score_terms(
        title_lower,
        ["有何看点", "新品盘点", "功能盘点", "传闻汇总", "新品汇总", "一文看懂"],
    ) > 0
    if not (english_list_title or chinese_roundup_title):
        return False
    recap_evidence = score_terms(
        lower,
        [
            "below, we have recapped",
            "we have recapped",
            "recapped rumors",
            "previously reported",
            "rumored so far",
            "as of july",
            "no new reporting",
            "without new reporting",
            "据多家媒体披露",
            "汇总此前传闻",
            "盘点此前传闻",
            "此前已有报道",
            "没有新增消息",
            "无新增消息",
        ],
    )
    return recap_evidence > 0


def is_ai_generated_apple_product_image_debunk_without_new_action(title: str, text: str) -> bool:
    """Detect viral fake-image debunks whose Apple details are only recycled background."""
    title_lower = title.lower()
    lead_lower = f"{title} {text[:900]}".lower()
    if effective_apple_term_score(title) <= 0 and not loose_apple_product_marker(title):
        return False
    if score_terms(
        title_lower,
        [
            "ai-generated",
            "ai generated",
            "fake image",
            "fake photo",
            "hoax",
            "ai 生成",
            "ai生成",
            "ai 伪造",
            "ai伪造",
            "伪造照片",
            "系 ai 生成",
            "系ai生成",
        ],
    ) <= 0:
        return False
    if score_terms(
        lead_lower,
        [
            "photo",
            "image",
            "picture",
            "viral",
            "debunk",
            "fake",
            "照片",
            "图片",
            "刷屏",
            "破绽",
            "辨伪",
            "造假",
        ],
    ) <= 0:
        return False
    return score_terms(
        title_lower,
        [
            "apple announced",
            "apple unveiled",
            "apple confirmed",
            "apple shared",
            "苹果宣布",
            "苹果发布",
            "苹果确认",
            "苹果展示",
        ],
    ) == 0


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
        or re.search(r"(?i)^(?:we\s+really\s+)?need\s+(?:a\s+way|apple)\b", title_lower)
        or re.search(r"(?i)\bapple\s+needs?\s+to\b", title_lower)
        or re.search(r"(?i)\bwishlist\b", title_lower)
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


def has_former_apple_person_reference(text: str) -> bool:
    lower = text.lower()
    if score_terms(
        lower,
        [
            "former apple",
            "ex-apple",
            "apple veteran",
            "previously at apple",
            "worked at apple",
            "ipod father",
            "father of the ipod",
            "ipod creator",
            "tony fadell",
            "jony ive",
            "曾在苹果",
            "苹果老将",
            "ipod 之父",
            "ipod之父",
        ],
    ) > 0:
        return True
    person_role_pattern = (
        r"(?:前\s*(?:apple|苹果)(?:公司)?[^。！？.!?]{0,18}"
        r"(?:员工|高管|主管|工程师|设计师|负责人|经理|副总裁|总监|团队成员|团队负责人|成员|老将|资深人士))"
        r"|(?:(?:apple|苹果)(?:公司)?[^。！？.!?]{0,8}前[^。！？.!?]{0,12}"
        r"(?:员工|高管|主管|工程师|设计师|负责人|经理|副总裁|总监|团队成员|团队负责人|成员))"
    )
    return re.search(person_role_pattern, lower) is not None


def is_former_apple_figure_commentary_without_new_apple_action(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if not has_former_apple_person_reference(lower):
        return False
    if is_apple_company_org_change_story(lower):
        return False
    if score_terms(
        lower,
        [
            "apple hired",
            "apple hires",
            "apple appointed",
            "apple names",
            "apple loses",
            "joins apple",
            "leaves apple",
            "apple acquired",
            "apple announces",
            "apple announced",
            "apple confirmed",
            "apple says",
            "filing",
            "lawsuit",
            "苹果聘请",
            "苹果任命",
            "苹果挖角",
            "加入苹果",
            "离开苹果",
            "苹果收购",
            "苹果宣布",
            "苹果确认",
            "苹果表示",
            "诉讼",
        ],
    ) > 0 and score_terms(lower, ["does not report", "doesn't report", "without a new apple", "no new apple"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "says",
            "said",
            "argues",
            "believes",
            "commentary",
            "opinion",
            "column",
            "interview",
            "podcast",
            "matters",
            "表示",
            "认为",
            "称",
            "评论",
            "观点",
            "专栏",
            "采访",
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
            "jamf beacon",
            "beacon by jamf",
            "mdm",
            "device management",
            "threat hunting",
            "enterprise mac",
            "enterprise macs",
            "第三方平台",
            "第三方服务",
            "设备管理",
            "威胁狩猎",
            "企业 mac",
        ],
    )
    management_action = score_terms(
        lower,
        [
            "launches new service",
            "launches new platform",
            "announces",
            "add managed threat hunting",
            "active mac threat hunting",
            "premium threat hunting",
            "security teams",
            "investigate macos threats",
            "manage mac",
            "manage ipad",
            "screen time",
            "parents manage",
            "school-issued",
            "k-12",
            "parental control",
            "推出服务",
            "推出平台",
            "推出",
            "威胁狩猎",
            "调查 macos 威胁",
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
    competitor = score_terms(
        competitor_text,
        [
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
        ],
    ) > 0
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
        or is_direct_apple_airpods_firmware_story(title, text)
        or is_direct_apple_hardware_roadmap_story(text, title)
        or is_apple_wallet_car_key_partner_support_story(title, text)
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
            "case",
            "magsafe",
            "lightning",
            "mfi",
            "stylus",
            "digital pen",
            "touch pen",
            "专用",
            "面向",
            "适配",
            "兼容",
            "支持",
            "书写",
            "可书写",
            "转接头",
            "手机壳",
            "保护壳",
            "磁吸",
        ],
    ) <= 0:
        return False
    if score_terms(title_lower, ["apple", "beats", "苹果", "官方"]) > 0:
        if score_terms(
            title_lower,
            [
                "专用",
                "compatible",
                "compatibility",
                "support",
                "supports",
                "adapter",
                "case",
                "magsafe",
                "lightning",
                "mfi",
                "stylus",
                "digital pen",
                "touch pen",
                "适配",
                "支持",
                "书写",
                "可书写",
                "转接头",
                "手机壳",
                "保护壳",
                "磁吸",
            ],
        ) <= 0:
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
            "adaptor",
            "keyboard",
            "mouse",
            "monitor",
            "display",
            "touchscreen",
            "storage enclosure",
            "ssd enclosure",
            "external drive",
            "external storage",
            "portable ssd",
            "usb4 enclosure",
            "stylus",
            "digital pen",
            "touch pen",
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
            "lightning",
            "mfi",
            "扩展坞",
            "充电器",
            "充电站",
            "移动电源",
            "适配器",
            "转接头",
            "键盘",
            "鼠标",
            "显示器",
            "触控显示器",
            "硬盘盒",
            "移动硬盘",
            "高速硬盘盒",
            "外置硬盘",
            "固态硬盘盒",
            "手写笔",
            "触控笔",
            "数字笔",
            "圆珠笔",
            "自拍屏",
            "背屏",
            "磁吸",
            "潮玩自拍屏",
            "配件",
            "保护壳",
            "手机壳",
            "外壳",
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
            "lightning",
            "mfi",
            "magsafe",
            "平台",
            "兼容",
            "适配",
            "支持",
            "专用",
            "面向",
            "苹果",
            "磁吸",
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
            "apple patent",
            "patent",
            "patented",
            "granted",
            "苹果发布",
            "苹果推出",
            "苹果宣布",
            "苹果下架",
            "苹果专利",
            "专利",
            "获批",
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
            "asus",
            "proart",
            "雷鸟",
            "华硕",
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
    if is_apple_executive_event_attendance_story("", lower):
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
    direct_title_event = (
        is_apple_device_battery_regulation_story(text)
        or is_apple_chip_tariff_exemption_story(candidate.title, text)
        or is_direct_apple_regulated_technology_access_story(candidate.title, text)
        or is_direct_apple_os_component_change_story(candidate.title, text)
        or is_apple_specific_market_share_report_story(text, candidate.title)
    )
    if should_hard_exclude_candidate(text) and not direct_title_event:
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
    candidate_tier, _ = classify_relevance_tier(
        candidate.title,
        candidate.summary,
        [candidate.context],
        candidate.source,
    )
    if candidate_tier == "strong" and candidate_event_kind in {
        "app_store_trust",
        "company_org",
        "developer_tool",
        "hardware_market",
        "legal_antitrust",
        "os_app",
        "regional_regulation",
        "security_privacy",
        "wallet_feature",
    }:
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
    if is_apple_executive_government_meeting_story(candidate.title, text):
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
    r"my\s+favorite\s+(?:carplay|iphone|ipad|mac|apple\s+watch|apple\s+tv|vision\s+pro|airpods|apple)\s+accessories",
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


def remove_article_end_tail_sections(text: str) -> str:
    """Cut source footer/recommendation text after explicit article-end markers."""
    earliest: int | None = None
    for pattern in [
        r"【\s*本文结束\s*】",
        r"\b本文结束\b",
    ]:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        leading_text = strip_tags(text[: match.start()])
        if len(leading_text) < 80:
            continue
        earliest = match.start() if earliest is None else min(earliest, match.start())
    if earliest is None:
        return text
    return text[:earliest]


def remove_noise_blocks(text: str) -> str:
    text = remove_article_end_tail_sections(remove_trailing_promo_sections(text))
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
    return remove_article_end_tail_sections(remove_trailing_promo_sections(cleaned))


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
    if re.search(r"apple @ work is exclusively brought to you|about apple @ work|request your extended trial|\bmosyle\b", lower, re.I):
        return True
    if re.search(r"广告声明|文内含有的对外跳转链接|it之家所有文章均包含本声明", lower, re.I):
        return True
    if re.search(r"due to the political or social nature of the discussion|political news forum|posting is limited to forum members", lower, re.I):
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


def _topic_boundary_facets_for_text(title: str, summary: str = "") -> frozenset[str]:
    """Return concrete event-boundary facets that should not be crossed by background text."""
    facets = effective_topic_facets(primary_topic_facets(title, summary))
    boundary_facets = independent_splittable_topic_facets(facets)
    if not boundary_facets:
        boundary_facets = facets & (SPLITTABLE_TOPIC_FACETS | SUMMARY_LEVEL_EVENT_MERGE_FACETS)
    return frozenset(boundary_facets - BROAD_TOPIC_FACETS)


@lru_cache(maxsize=16384)
def cached_topic_boundary_facets_for_text(title: str, summary: str = "") -> frozenset[str]:
    return _topic_boundary_facets_for_text(title, summary)


def topic_boundary_facets_for_text(title: str, summary: str = "") -> set[str]:
    return set(cached_topic_boundary_facets_for_text(title, summary))


def topic_boundary_facets_conflict(primary_facets: set[str], secondary_facets: set[str]) -> bool:
    if not primary_facets or not secondary_facets:
        return False
    return not splittable_topic_facets_compatible(primary_facets, secondary_facets)


def discovery_text_conflicts_with_detail_topic(
    detail_title: str,
    detail_summary: str,
    discovery_text: str,
) -> bool:
    if not discovery_text:
        return False
    detail_facets = topic_boundary_facets_for_text(detail_title, detail_summary)
    discovery_facets = topic_boundary_facets_for_text("", discovery_text)
    return topic_boundary_facets_conflict(detail_facets, discovery_facets)


def safe_discovery_text_for_detail(detail_title: str, detail_summary: str, discovery_text: str) -> str:
    if discovery_text_conflicts_with_detail_topic(detail_title, detail_summary, discovery_text):
        return ""
    return discovery_text


def safe_combine_detail_and_discovery_summary(
    detail_title: str,
    detail_summary: str,
    discovery_summary: str,
) -> str:
    return combine_summaries(
        detail_summary,
        safe_discovery_text_for_detail(detail_title, detail_summary, discovery_summary),
    )


def safe_context_for_detail_article(
    is_roundup: bool,
    detail_title: str,
    detail_summary: str,
    candidate_context: str,
) -> str:
    if is_roundup:
        return ""
    return safe_discovery_text_for_detail(detail_title, detail_summary, candidate_context)


def hardware_rumor_supporting_fact_compatible(primary_facets: set[str], fact_facets: set[str]) -> bool:
    hardware_primary_facets = IPHONE_HARDWARE_RUMOR_TOPIC_FACETS | {
        "apple-future-product-price-forecast",
        "apple-product-price-increase",
        "foldable-iphone-render-leak",
        "foldable-iphone-successor-roadmap",
        "foldable-iphone-supply-chain",
        "iphone-component-cost-forecast",
    }
    hardware_supporting_fact_facets = hardware_primary_facets | {
        "apple-chip-process-roadmap",
        "apple-chip-roadmap",
        "iphone-chip-roadmap",
        "iphone-launch-timing",
        "iphone-memory-price-forecast",
    }
    return bool(primary_facets & hardware_primary_facets) and bool(
        fact_facets & hardware_supporting_fact_facets
    ) and not bool(
        fact_facets
        & {
            "apple-product-data-leak",
            "apple-product-data-leak-enforcement",
            "apple-product-data-leak-specs",
            "ios-signing-status",
        }
    )


def key_fact_topic_compatible_with_primary(primary_facets: set[str], fact_facets: set[str]) -> bool:
    if not topic_boundary_facets_conflict(primary_facets, fact_facets):
        return True
    return hardware_rumor_supporting_fact_compatible(primary_facets, fact_facets)


def filter_key_facts_for_primary_topic(title: str, summary: str, key_facts: list[str]) -> list[str]:
    primary_facets = topic_boundary_facets_for_text(title, summary)
    if not primary_facets:
        return key_facts
    filtered: list[str] = []
    for fact in key_facts:
        fact_facets = topic_boundary_facets_for_text("", fact)
        if fact_facets and not key_fact_topic_compatible_with_primary(primary_facets, fact_facets):
            continue
        filtered.append(fact)
    return filtered or key_facts


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
    key_facts = filter_key_facts_for_primary_topic(title, summary, key_facts)
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
    "apple-price-production-plan-response",
    "apple-price-retailer-retroactive-adjustment",
    "apple-price-stock-market-reaction",
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
    "russia": ["russia", "russian", "俄罗斯", "俄联邦"],
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
    "iphone-battery-capacity-leak",
    "iphone-logic-board-leak",
    "iphone-production-forecast",
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
    "apple-memory-supplier-sourcing",
    "apple-watch-redesign",
    "airpods-firmware-update",
    "airpods-max-condensation-lawsuit",
    "app-store-age-verification",
    *APPLE_PRICE_SUBTOPIC_FACETS,
    "apple-product-roadmap-list",
    "apple-wallet-digital-id",
    "bootrom-secure-rom-exploit",
    "brazil-app-store-policy",
    "epic-app-store-appeal",
    "find-my-location-sharing",
    "final-cut-camera-update",
    "foldable-iphone-supply-chain",
    "hide-my-email-vulnerability",
    "ios-signing-status",
    "iwork-apps-update",
    "iphone-air-successor",
    "iphone-color-mockup",
    "iphone-parts-factory-contamination",
    "russia-fas-app-preinstall-regulation",
    "safari-mcp-server",
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
    tutorial_title = (
        title_lower.startswith("how to ")
        or title_lower.startswith("here's how ")
        or score_terms(
            title_lower,
            [
                "how to get",
                "get your iphone ready",
                "get your ipad ready",
                "get your mac ready",
                "when you can install",
                "how you can install",
                "before installing",
                "install the beta",
                "怎么办",
                "打开这个功能",
                "一定提前打开",
                "提前打开",
                "提前开启",
                "找回概率",
                "别急着",
                "安装前",
                "如何安装",
                "如何找回",
                "准备安装",
            ],
        )
        > 0
    )
    if not tutorial_title:
        return False
    release_context = has_apple_first_party_release_context(text)
    forward_looking_or_prep = score_terms(
        f"{title} {text}".lower(),
        [
            "available this month",
            "would be released",
            "will be released",
            "should be available",
            "get ready",
            "prepare",
            "before installing",
            "准备",
            "本月上线",
            "即将",
        ],
    ) > 0
    if release_context and forward_looking_or_prep:
        return True
    return not (
        release_context
        or is_apple_developer_tool_story(text)
        or app_store_policy_score(text) > 0
    )


def is_personal_usage_or_settings_guide_without_new_apple_action(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    personal_or_usage_title = score_terms(
        title_lower,
        [
            "with these settings",
            "became more useful for me",
            "for me with",
            "how i use",
            "hidden feature",
            "useful hidden feature",
            "healthy habit",
            "turn any iphone into",
            "dumb phone",
            "time in daylight",
            "善用",
            "变儿童手机",
            "仅保留",
            "配置成儿童手机",
            "儿童手机",
        ],
    ) > 0
    if not personal_or_usage_title and (
        os_release_facets_from_text(lower)
        or (
            is_title_primary_software_system_story(title, lower)
            and score_terms(title_lower, ["how", "guide", "tips", "settings", "教程", "设置", "技巧"]) <= 0
        )
    ):
        return False
    instructional_body = score_terms(
        lower,
        [
            "go to the settings",
            "settings app",
            "tap sleep score",
            "toggle alerts",
            "screen time",
            "allowed apps",
            "assistive access",
            "only keep",
            "仅保留",
            "设置路径",
            "辅助访问",
            "允许使用的应用",
            "保留了",
        ],
    )
    if not personal_or_usage_title and instructional_body < 2:
        return False
    if not (personal_or_usage_title or instructional_body):
        return False
    if score_terms(
        title_lower,
        [
            "apple releases",
            "apple seeds",
            "apple seeded",
            "apple launches",
            "apple announces",
            "beta",
            "betas",
            "rc",
            "苹果发布",
            "苹果推出",
            "苹果宣布",
            "测试版",
            "候选版",
        ],
    ) > 0:
        return False
    return True


def is_podcast_episode_without_new_apple_reporting(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if score_terms(title_lower, ["podcast", "overtime", "episode", "节目"]) <= 0 and score_terms(
        lower,
        ["weekly video-first podcast", "subscribe to", "apple podcasts", "youtube channel", "播客", "节目"],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "exclusive",
            "exclusively reports",
            "reports that",
            "according to sources",
            "filing",
            "document",
            "独家",
            "消息称",
            "报道称",
            "文件显示",
        ],
    ) > 0:
        return False
    return True


def is_third_party_apple_device_preservation_or_showcase_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "time capsule",
            "sealed inside",
            "sealed in",
            "buried",
            "reopened in",
            "america250",
            "semiquincentennial",
            "preservation",
            "时间胶囊",
            "封存",
            "埋入",
            "纪念活动",
        ],
    ) <= 0:
        return False
    return score_terms(lower, ["iphone", "ipad", "mac", "macbook", "apple watch", "airpods", "苹果"]) > 0


def is_third_party_hardware_mod_or_repair_story_without_apple_action(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if score_terms(lower, ["iphone", "ipad", "mac", "macbook", "apple watch", "airpods", "苹果"]) <= 0:
        return False
    if os_release_facets_from_text(lower) or is_title_primary_software_system_story(title, lower):
        return False
    actor_score = score_terms(
        lower,
        [
            "reddit",
            "engineer",
            "shared",
            "工程师",
            "分享",
        ],
    )
    mod_action_score = score_terms(
        lower,
        [
            "self upgrade",
            "self-upgrade",
            "upgraded",
            "upgrade to",
            "modification",
            "modded",
            "soldering",
            "bga",
            "teardown",
            "自行",
            "自行为",
            "自行升级",
            "更换 nand",
            "升级 8tb",
            "焊接",
            "改造",
            "拆机",
            "不适合普通用户",
            "过程坎坷",
        ],
    )
    if actor_score <= 0 or mod_action_score <= 0:
        return False
    if score_terms(
        title_lower,
        ["apple repair", "self service repair", "applecare", "苹果自助维修", "官方维修"],
    ) > 0:
        return False
    return True


def is_usage_podcast_or_third_party_project_without_new_apple_action(title: str, text: str) -> bool:
    return (
        is_personal_usage_or_settings_guide_without_new_apple_action(title, text)
        or is_podcast_episode_without_new_apple_reporting(title, text)
        or is_third_party_apple_device_preservation_or_showcase_story(title, text)
        or is_third_party_hardware_mod_or_repair_story_without_apple_action(title, text)
    )


def is_non_apple_primary_subject_with_former_apple_background(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = f"{title} {text}".lower()
    if effective_apple_term_score(title_lower) > 0:
        return False
    former_apple_background = has_former_apple_person_reference(lower) or score_terms(
        lower,
        [
            "苹果公司初代处理器",
            "领导了苹果",
            "曾领导苹果",
        ],
    ) > 0
    if not former_apple_background:
        return False
    current_non_apple_subject = score_terms(
        lower,
        [
            "startup",
            "company",
            "ceo",
            "founder",
            "tenstorrent",
            "ai model",
            "large model",
            "llm",
            "openai",
            "anthropic",
            "kimi",
            "glm",
            "公司",
            "创始人",
            "首席执行官",
            "大模型",
            "中国大模型",
            "智谱",
            "月之暗面",
        ],
    ) > 0
    apple_action = score_terms(
        lower,
        [
            "apple hires",
            "apple hired",
            "apple loses",
            "apple lost",
            "apple poached",
            "apple appoints",
            "apple names",
            "苹果聘请",
            "苹果任命",
            "苹果高管离职",
            "苹果失去",
            "苹果挖角",
        ],
    ) > 0
    return current_non_apple_subject and not apple_action


def is_broad_ai_device_market_commentary_with_apple_example(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = f"{title} {text}".lower()
    if score_terms(title_lower, ["android users", "安卓用户"]) > 0 and score_terms(lower, ["apple intelligence", "apple ai", "iphone", "苹果ai", "苹果 ai"]) > 0:
        return True
    if score_terms(title_lower, ["ai phone", "ai phones", "ai pc", "aipc", "ai手机", "ai 手机"]) <= 0:
        return False
    if score_terms(lower, ["apple intelligence", "iphone", "苹果"]) <= 0:
        return False
    broad_market_score = score_terms(
        lower,
        [
            "consumer",
            "consumers",
            "market",
            "survey",
            "ubs",
            "upgrade intent",
            "buying decision",
            "aipc",
            "ai pc",
            "消费者",
            "买单",
            "市场",
            "调查",
            "换机意愿",
            "购机决策",
            "提前升级",
        ],
    )
    direct_apple_action = has_apple_first_party_release_context(lower) and score_terms(
        title_lower,
        ["apple", "iphone", "ios", "apple intelligence", "苹果"],
    ) > 0
    return broad_market_score > 0 and not direct_apple_action


def is_apple_work_column_without_new_apple_action(title: str, text: str) -> bool:
    title_lower = title.lower().strip()
    if not title_lower.startswith("apple @ work:"):
        return False
    direct_apple_action = score_terms(
        title_lower,
        [
            "apple launches",
            "apple announces",
            "apple releases",
            "apple released",
            "adds",
            "new feature",
            "new service",
        ],
    ) > 0
    return not direct_apple_action


def is_third_party_reference_or_explainer_project_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "mac",
            "macbook",
            "apple watch",
            "airpods",
            "苹果",
        ],
    ) <= 0:
        return False
    third_party_context_score = score_terms(
        lower,
        [
            "sheets.works",
            "ifixit",
            "interactive timeline",
            "visualization",
            "project",
            "video shows how",
            "how an iphone battery is made",
            "how a battery is made",
            "teardown video",
            "第三方",
            "互动时间线",
            "可视化",
            "项目",
            "视频讲解",
            "生产步骤",
        ],
    )
    reference_action_score = score_terms(
        title_lower,
        [
            "interactive timeline",
            "explore every",
            "every ipad ever",
            "every iphone ever",
            "video shows how",
            "how an iphone battery is made",
            "how an ipad is made",
            "how a mac is made",
            "互动时间线",
            "一览",
            "盘点",
            "视频讲解",
        ],
    )
    return third_party_context_score > 0 and reference_action_score > 0


def is_third_party_custom_unreleased_apple_product_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    third_party_customizer_score = score_terms(
        lower,
        [
            "caviar",
            "luxury custom",
            "custom brand",
            "customized",
            "customizer",
            "third-party",
            "定制品牌",
            "奢侈定制",
            "第三方厂商",
            "限量",
        ],
    )
    unreleased_product_score = score_terms(
        lower,
        [
            "unreleased",
            "rumored",
            "concept",
            "render",
            "not released",
            "has not released",
            "ahead of apple",
            "尚未发布",
            "传闻中",
            "概念",
            "渲染图",
            "替苹果率先发布",
            "提前推出",
        ],
    )
    apple_product_score = score_terms(
        lower,
        [
            "iphone",
            "ipad",
            "macbook",
            "apple watch",
            "airpods",
            "vision pro",
            "苹果",
        ],
    )
    return third_party_customizer_score > 0 and unreleased_product_score > 0 and apple_product_score > 0


def is_non_apple_public_response_with_apple_purchase_context(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if title_lower.startswith(("apple ", "苹果 ", "苹果公司", "苹果回应")):
        return False
    organization_score = score_terms(
        lower,
        [
            "foundation",
            "charity",
            "nonprofit",
            "company",
            "vendor",
            "基金会",
            "公益",
            "慈善",
            "公司",
            "机构",
            "供应商",
        ],
    )
    response_score = score_terms(
        lower,
        [
            "responds",
            "response",
            "statement",
            "apology",
            "apologizes",
            "回应",
            "说明",
            "致歉",
            "道歉",
        ],
    )
    donation_or_relief_score = score_terms(
        lower,
        [
            "donation",
            "donates",
            "donated",
            "relief",
            "disaster relief",
            "charitable",
            "fundraising",
            "捐赠",
            "捐款",
            "善款",
            "救灾",
            "驰援",
            "赈灾",
            "公益",
            "慈善",
        ],
    )
    controversy_score = score_terms(
        lower,
        [
            "controversy",
            "controversial",
            "questioned",
            "criticism",
            "criticized",
            "backlash",
            "惹争议",
            "争议",
            "质疑",
            "被批",
            "风波",
        ],
    )
    apple_purchase_score = score_terms(
        lower,
        [
            "apple computer",
            "apple computers",
            "mac computer",
            "macbook",
            "macbooks",
            "procurement",
            "purchase",
            "purchased",
            "苹果电脑",
            "苹果笔记本",
            "采购",
            "购置",
        ],
    )
    return organization_score > 0 and apple_purchase_score > 0 and (
        response_score > 0
        or donation_or_relief_score > 0
        or controversy_score > 0
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
    former_staff_score = score_terms(lower, ["former vision pro"]) > 0 or has_former_apple_person_reference(lower)
    if not former_staff_score:
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
    if is_third_party_reference_or_explainer_project_story(title, text):
        return False
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


def has_direct_iphone_product_title_subject(title: str) -> bool:
    title_lower = title.lower()
    if score_terms(title_lower, ["iphone moment", "iphone 时刻"]) > 0:
        return False
    if re.search(r"\biphone\s*(?:\d{1,2}|air|fold|ultra|pro|max|e)\b", title_lower):
        return True
    if re.search(r"苹果[^。！？.!?]{0,24}iphone", title_lower):
        return True
    if title_lower.startswith("iphone ") and score_terms(title_lower, ["apple", "苹果", "galaxy", "android", "三星", "安卓"]) <= 0:
        return True
    return False


def is_direct_iphone_hardware_spec_rumor_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if not has_direct_iphone_product_title_subject(title):
        return False
    competitor_in_title = score_terms(
        title_lower,
        ["android", "galaxy", "samsung", "huawei", "xiaomi", "oppo", "vivo", "honor", "pixel", "安卓", "三星", "华为", "小米", "荣耀"],
    ) > 0
    supplier_or_component_context = score_terms(
        title_lower,
        [
            "will use",
            "to use",
            "use samsung",
            "supplier",
            "supply",
            "sensor",
            "image sensor",
            "component",
            "搭载",
            "采用",
            "供应",
            "供应商",
            "图像传感器",
            "传感器",
            "组件",
        ],
    ) > 0
    if competitor_in_title and not supplier_or_component_context:
        return False
    hardware_detail_score = score_terms(
        lower,
        [
            "battery capacity",
            "battery",
            "mah",
            "sim",
            "esim",
            "dynamic island",
            "face id",
            "camera",
            "camera control",
            "color",
            "colour",
            "finish",
            "display",
            "screen",
            "chip",
            "modem",
            "baseband",
            "nand",
            "storage",
            "flash",
            "qlc",
            "tlc",
            "sensor",
            "容量",
            "电池容量",
            "电池",
            "实体 sim",
            "实体sim",
            "灵动岛",
            "配色",
            "颜色",
            "摄像头",
            "相机",
            "芯片",
            "调制解调器",
            "基带",
            "闪存",
            "存储",
            "传感器",
        ],
    )
    if hardware_detail_score <= 0:
        return False
    return score_terms(
        lower,
        [
            "rumor",
            "rumors",
            "leak",
            "leaks",
            "leaked",
            "revealed",
            "published",
            "posted",
            "report",
            "reported",
            "reportedly",
            "blogger",
            "weibo",
            "公布",
            "曝光",
            "泄露",
            "爆料",
            "消息称",
            "据称",
            "据悉",
            "透露",
            "新鲜出炉",
            "显示",
            "博主",
            "社交平台",
        ],
    ) > 0


def is_camera_airpods_code_clue_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["airpods", "airpods pro", "耳机"]) <= 0:
        return False
    if score_terms(lower, ["camera", "cameras", "camera-equipped", "摄像头", "相机"]) <= 0:
        return False
    camera_airpods_nearby = re.search(
        r"(?:airpods|airpods pro|耳机)[^。.!?；;，,\n]{0,60}(?:camera|cameras|camera-equipped|摄像头|相机)"
        r"|(?:camera|cameras|camera-equipped|摄像头|相机)[^。.!?；;，,\n]{0,60}(?:airpods|airpods pro|耳机)",
        lower,
    )
    if not camera_airpods_nearby:
        return False
    return score_terms(
        lower,
        [
            "b790",
            "code",
            "ios 27 beta",
            "developer beta",
            "two images",
            "cameras on either side",
            "system_prompt",
            "visual intelligence",
            "代码",
            "开发者测试版",
            "两侧摄像头",
            "2 张图像",
            "视觉智能",
        ],
    ) > 0


def is_camera_airpods_development_suspension_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["airpods", "airpods pro", "耳机"]) <= 0:
        return False
    if score_terms(lower, ["camera", "camera-equipped", "infrared", "摄像头", "红外"]) <= 0:
        return False
    camera_airpods_nearby = re.search(
        r"(?:airpods|airpods pro|耳机)[^。.!?；;，,\n]{0,60}(?:camera|camera-equipped|infrared|摄像头|红外)"
        r"|(?:camera|camera-equipped|infrared|摄像头|红外)[^。.!?；;，,\n]{0,60}(?:airpods|airpods pro|耳机)",
        lower,
    )
    if not camera_airpods_nearby:
        return False
    return score_terms(
        lower,
        [
            "suspended",
            "halted",
            "paused",
            "held back",
            "delayed",
            "kosutami",
            "h90",
            "暂停",
            "推迟",
            "延迟",
            "量产",
            "项目",
        ],
    ) > 0


def is_iphone_photography_awards_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone photography awards", "ippa", "iphone 摄影奖", "iphone 摄影大奖"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "winner",
            "winners",
            "winning",
            "awards",
            "award",
            "photo",
            "photos",
            "photography",
            "image",
            "images",
            "shot",
            "shots",
            "entries",
            "获奖",
            "获奖作品",
            "摄影",
            "照片",
            "图片",
            "作品",
        ],
    ) > 0


def is_icloud_service_perk_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["icloud+", "icloud plus", "icloud storage", "icloud", "homekit secure video"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "perk",
            "perks",
            "benefit",
            "benefits",
            "storage plan",
            "paid users",
            "subscriber",
            "subscribers",
            "subscription",
            "usage limits",
            "secure video",
            "权益",
            "订阅",
            "付费用户",
            "存储方案",
            "使用额度",
            "安全视频",
        ],
    ) > 0


def is_apple_service_card_payment_restore_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(
        lower,
        [
            "apple",
            "app store",
            "icloud",
            "apple account",
            "apple id",
            "苹果",
            "应用商店",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "credit card",
            "debit card",
            "card payment",
            "bank card",
            "payment option",
            "card payments",
            "card tokenisation",
            "card tokenization",
            "银行卡",
            "信用卡",
            "借记卡",
            "卡支付",
            "支付选项",
            "卡片代币化",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "restore",
            "restored",
            "restores",
            "restoring",
            "resume",
            "resumes",
            "resuming",
            "re-enable",
            "re-enabled",
            "testing",
            "test",
            "complied",
            "compliance",
            "恢复",
            "重新启用",
            "测试恢复",
            "小规模测试",
            "合规",
            "完成合规",
        ],
    ) > 0


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
    if is_third_party_platform_update_improving_apple_device_interop(title, text):
        return False
    if (
        score_terms(title_lower, ["google", "pixel", "谷歌"]) > 0
        and score_terms(title_lower, ["event", "launch", "launches", "debut", "发布会", "发布", "推出", "确认"]) > 0
        and score_terms(f"{title_lower} {lower[:500]}", ["before apple", "ahead of apple", "month before", "iphone", "foldable iphone", "抢先于苹果", "比苹果", "早于苹果"]) > 0
    ):
        return True
    if (
        score_terms(title_lower, ["claude", "anthropic"]) > 0
        and score_terms(title_lower, ["iphone", "ios", "mobile", "web", "expands", "launches", "上线", "扩展"]) > 0
        and not has_apple_first_party_release_context(f"{title} {text}")
    ):
        return True
    if (
        score_terms(title_lower, ["statcounter", "windows", "desktop system", "桌面系统"]) > 0
        and score_terms(f"{title_lower} {lower[:500]}", ["market share", "share", "占比", "份额", "windows"]) > 0
    ):
        return True
    if (
        score_terms(title_lower, ["android users", "安卓用户"]) > 0
        and score_terms(f"{title_lower} {lower[:500]}", ["apple intelligence", "apple ai", "iphone", "苹果ai", "苹果 ai", "转向iphone"]) > 0
    ):
        return True
    if is_third_party_app_usage_on_apple_platform_story(title, text):
        return True
    non_apple_primary_score = score_terms(
        title_lower,
        [
            "qualcomm",
            "snapdragon",
            "xiaomi",
            "redmi",
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
            "pixel",
            "microsoft",
            "meta",
            "claude",
            "anthropic",
            "statcounter",
            "windows",
            "高通",
            "骁龙",
            "小米",
            "红米",
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
            "谷歌",
            "像素",
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
    if is_apple_tv_purchase_4k_upgrade_story(text):
        return True
    if is_apple_tv_awards_nominations_story(text):
        return True
    if score_terms(lower, ["apple music", "apple arcade", "classical", "苹果音乐"]) > 0:
        return True
    if (
        is_apple_tv_mlb_schedule_story(text)
        or is_apple_tv_content_event_lineup_story(text)
        or is_apple_tv_content_trailer_story(text)
    ):
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
                "trailer",
                "teaser",
                "lineup",
                "panel",
                "comic-con",
                "grand prix",
                "formula 1",
                "f1",
                "剧集",
                "电影",
                "首播",
                "预告",
                "阵容",
                "展会",
                "动漫展",
                "大奖赛",
                "直播",
            ],
        )
        > 0
    )


def is_apple_tv_mlb_schedule_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple tv", "apple tv+", "苹果电视"]) <= 0:
        return False
    if score_terms(lower, ["mlb", "major league baseball", "friday night baseball", "美国职业棒球", "职棒"]) <= 0:
        return False
    return score_terms(lower, ["schedule", "matchups", "games", "august", "赛程", "比赛", "直播"]) > 0


def is_apple_tv_content_event_lineup_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple tv", "apple tv+", "苹果电视"]) <= 0:
        return False
    event_score = score_terms(lower, ["comic-con", "comic con", "hall h", "san diego", "动漫展", "圣迭戈"])
    lineup_score = score_terms(lower, ["lineup", "panel", "panels", "take over", "taking over", "阵容", "小组", "展会"])
    content_score = score_terms(lower, ["silo", "dark matter", "widow", "monarch", "for all mankind", "剧集", "电视剧"])
    return event_score > 0 and lineup_score > 0 and content_score > 0


def is_apple_tv_content_trailer_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple tv", "apple tv+", "苹果电视"]) <= 0:
        return False
    trailer_score = score_terms(lower, ["trailer", "teaser", "first look", "预告", "先导"])
    content_score = score_terms(lower, ["special", "series", "season", "film", "movie", "documentary", "snoopy", "peanuts", "剧集", "电影", "特别节目"])
    return trailer_score > 0 and content_score > 0


def is_siri_ai_lawsuit_settlement_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["siri", "apple intelligence", "苹果智能", "苹果 ai"]) <= 0:
        return False
    if score_terms(lower, ["lawsuit", "class action", "settlement", "claim", "payout", "false advertising", "诉讼", "集体诉讼", "和解", "赔偿", "虚假宣传"]) <= 0:
        return False
    return score_terms(lower, ["delayed", "delay", "iphone 15 pro", "iphone 16", "$250 million", "250 million", "2.5亿美元", "延迟", "延期"]) > 0


def is_india_tariff_iphone_manufacturing_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["india", "indian", "印度"]) <= 0:
        return False
    if score_terms(lower, ["tariff", "tariffs", "import duty", "import duties", "duty exemption", "customs", "关税", "进口税", "免税"]) <= 0:
        return False
    if score_terms(lower, ["apple", "iphone", "苹果"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "smartphone",
            "smartphones",
            "mobile phone",
            "phone parts",
            "electronics parts",
            "component",
            "components",
            "wireless charging",
            "lithium-ion",
            "battery cell",
            "manufacturing",
            "手机",
            "智能手机",
            "电子设备",
            "零部件",
            "无线充电",
            "锂离子",
            "电芯",
            "制造",
        ],
    ) > 0


def is_apple_on_device_ai_model_compression_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple", "iphone", "苹果"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "on-device",
            "on device",
            "directly on iphone",
            "directly on iphones",
            "run directly",
            "runs giant ai models on iphone",
            "run giant ai models on iphone",
            "without servers",
            "without server",
            "local ai",
            "本地 ai",
            "端侧",
            "本地运行",
            "直接运行",
        ],
    ) <= 0:
        return False
    ai_score = score_terms(lower, ["ai model", "large model", "larger ai", "llm", "qwen", "apple intelligence", "模型", "大模型", "人工智能"])
    compression_score = score_terms(lower, ["prisml", "compression", "compressed", "shrunk", "shrink", "1-bit", "one-bit", "quantization", "压缩", "量化"])
    return ai_score > 0 and compression_score > 0


def is_iphone_component_cost_forecast_story(text: str) -> bool:
    lower = text.lower()
    headline = lower[:260]
    if score_terms(headline, ["android", "安卓"]) > 0 and score_terms(headline, ["iphone 18 pro max", "iphone18 pro max"]) <= 0:
        return False
    if score_terms(lower, ["iphone 18 pro max", "iphone18 pro max", "苹果 iphone 18 pro max"]) <= 0:
        return False
    if score_terms(lower, ["component cost", "component costs", "bill of materials", "bom", "materials cost", "物料清单", "物料成本", "组件成本", "成本"]) <= 0:
        return False
    return score_terms(lower, ["counterpoint", "nand", "dram", "memory", "storage", "2nm", "packaging", "$300", "300", "内存", "存储", "闪存", "封装"]) > 0


def is_apple_tv_purchase_4k_upgrade_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple tv", "apple tv app", "itunes store", "苹果电视"]) <= 0:
        return False
    if score_terms(lower, ["4k"]) <= 0:
        return False
    if score_terms(lower, ["purchased tv show", "purchased tv shows", "tv shows", "shows", "剧集", "电视节目"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "free upgrade",
            "free 4k",
            "4k upgrade",
            "upgrading",
            "upgrades",
            "no additional charge",
            "at no added charge",
            "免费升级",
            "免费 4k",
            "无需额外付费",
        ],
    ) > 0


def is_apple_tv_awards_nominations_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple tv", "apple tv+", "苹果电视"]) <= 0:
        return False
    if score_terms(lower, ["emmy", "emmys", "艾美"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "nomination",
            "nominations",
            "nominated",
            "提名",
        ],
    ) > 0


def is_icloud_home_ai_camera_subscription_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["home app", "apple home", "家庭 app", "家庭应用", "homekit"]) <= 0:
        return False
    if score_terms(lower, ["icloud+", "icloud plus", "icloud plan", "icloud subscription", "icloud 订阅", "icloud+ 订阅"]) <= 0:
        return False
    if score_terms(lower, ["camera", "cameras", "ai camera", "apple intelligence", "摄像头", "相机", "ai"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "2tb",
            "2 tb",
            "$9.99",
            "subscription",
            "plan",
            "require",
            "requires",
            "charge",
            "订阅",
            "套餐",
            "收费",
            "需要",
        ],
    ) > 0


def is_eu_gatekeeper_designation_appeal_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple", "苹果"]) <= 0:
        return False
    if score_terms(lower, ["gatekeeper", "core platform service", "dma", "digital markets act", "看门人", "守门人"]) <= 0:
        return False
    if score_terms(lower, ["app store", "ios", "应用商店"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "appeal",
            "appeals",
            "rejected",
            "upheld",
            "general court",
            "european commission",
            "eu court",
            "court",
            "上诉",
            "驳回",
            "维持",
            "欧盟法院",
            "普通法院",
            "认定",
        ],
    ) > 0


def is_encrypted_hfs_support_removal_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["macos", "mac os", "苹果"]) <= 0:
        return False
    if score_terms(lower, ["encrypted mac os extended", "encrypted hfs+", "hfs+", "mac os extended", "mac os 扩展", "日志式，加密"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "drop support",
            "remove support",
            "no longer support",
            "support ends",
            "dies",
            "migrate to apfs",
            "不再支持",
            "停止支持",
            "迁移到 apfs",
            "apfs",
        ],
    ) > 0


def is_apple_translate_language_expansion_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple translate", "translate app", "翻译应用", "翻译 app", "翻译"]) <= 0:
        return False
    if score_terms(lower, ["ios", "ipados", "macos", "苹果"]) <= 0:
        return False
    if score_terms(
        lower,
        [
            "language",
            "languages",
            "accent",
            "accents",
            "cantonese",
            "30 languages",
            "nine",
            "9",
            "语言",
            "方言",
            "粤语",
            "30 种",
            "30种",
            "9 种",
            "9种",
            "新增支持",
        ],
    ) <= 0:
        return False
    return score_terms(lower, ["add", "adds", "added", "support", "supports", "新增", "支持", "达到"]) > 0


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
                "security vulnerability",
                "security vulnerabilities",
                "security flaw",
                "security flaws",
                "security issue",
                "security issues",
                "crash",
                "denial of service",
                "dos",
                "cispa",
                "漏洞",
                "安全漏洞",
                "安全缺陷",
                "安全问题",
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


def is_final_cut_camera_update_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["final cut camera"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "apple",
            "updated",
            "update",
            "released",
            "version",
            "clean hdmi",
            "hdmi out",
            "prores",
            "import",
            "final cut pro",
            "app store",
            "苹果",
            "更新",
            "版本",
            "纯净 hdmi",
            "hdmi 输出",
            "导入",
            "专业拍摄",
        ],
    ) > 0


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
        not is_iphone_photography_awards_story(lower)
        and
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
        not is_iphone_photography_awards_story(lower)
        and
        score_terms(
            lower,
            [
                "keyboard",
                "input method",
                "typing",
                "chinese input",
                "language support",
                "copy-and-paste",
                "copy and paste",
                "copy paste",
                "paste from",
                "paste",
                "clipboard",
                "输入法",
                "键盘",
                "中文输入",
                "拼音",
                "候选词",
                "标点",
                "生僻字",
                "复制",
                "粘贴",
                "剪贴板",
            ],
        )
        > 0
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
        score_terms(lower, ["siri", "siri ai"]) > 0
        and score_terms(lower, ["voice customization", "speaking pace", "expressivity", "语速", "表现力", "语音定制"]) > 0
    ):
        facets.add("siri-voice-customization")
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
            "stolen files",
            "leaked files",
            "internal files",
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
    if score_terms(
        headline_scope,
        [
            "price not announced",
            "pricing not announced",
            "price has not been announced",
            "price hasn't been announced",
            "price remains unknown",
            "pricing remains unknown",
            "只剩价格还没公布",
            "价格还没公布",
            "价格尚未公布",
            "价格未公布",
            "售价尚未公布",
            "售价未公布",
        ],
    ) > 0:
        return False
    price_anchor_score = score_terms(
        headline_scope,
        [
            "starting price",
            "starting at",
            "starts at",
            "could start",
            "may start",
            "expected to cost",
            "expected to start",
            "estimated price",
            "estimated pricing",
            "forecast price",
            "forecast pricing",
            "price forecast",
            "pricing forecast",
            "priced at",
            "price",
            "pricing",
            "more expensive",
            "涨价",
            "定价",
            "售价",
            "起售价",
            "起步价",
            "价格",
            "万元",
            "美元",
            "人民币",
        ],
    )
    if price_anchor_score <= 0:
        return False
    if re.search(r"(?:[$￥¥]\s*\d|\d[\d,.]*\s*(?:dollars?|usd|美元|元|万元|人民币))", headline_scope):
        return True
    return score_terms(
        headline_scope,
        [
            "expected",
            "estimated",
            "forecast",
            "reportedly",
            "rumor",
            "rumored",
            "prediction",
            "消息称",
            "爆料",
            "预计",
            "预估",
            "预测",
            "或",
            "将",
        ],
    ) > 0


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


def is_apple_price_stock_market_reaction_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    stock_score = score_terms(
        lower,
        [
            "stock",
            "stocks",
            "share price",
            "shares",
            "$aapl",
            "market cap",
            "market value",
            "股价",
            "股票",
            "市值",
        ],
    )
    reaction_score = score_terms(
        lower,
        [
            "recover",
            "recovers",
            "recovered",
            "rebound",
            "rebounds",
            "rebounded",
            "gain",
            "gains",
            "hit",
            "slump",
            "drop",
            "drops",
            "dive",
            "rally",
            "反弹",
            "回升",
            "上涨",
            "下跌",
            "重挫",
            "跳水",
        ],
    )
    return stock_score > 0 and reaction_score > 0


def is_apple_price_production_plan_response_story(text: str, title: str = "") -> bool:
    lower = f"{title} {text}".lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    production_score = score_terms(
        lower,
        [
            "production plan",
            "production plans",
            "production target",
            "production forecast",
            "build plan",
            "shipments",
            "shipment forecast",
            "cuts production",
            "cut production",
            "inventory",
            "生产计划",
            "生产目标",
            "出货",
            "出货预期",
            "削减",
            "下调",
            "库存",
        ],
    )
    price_or_demand_score = score_terms(
        lower,
        [
            "price increase",
            "price increases",
            "price hike",
            "higher prices",
            "demand",
            "sales",
            "涨价",
            "调价",
            "销量",
            "需求",
            "市场预期",
        ],
    )
    return production_score > 0 and price_or_demand_score > 0


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
    future_price_forecast = is_future_apple_product_price_forecast_story(text, title)
    if not is_apple_product_price_increase_story(text, title):
        if future_price_forecast:
            return {"apple-product-price-increase", "apple-future-product-price-forecast"}
        return set()
    facets = {"apple-product-price-increase"}
    if is_apple_retail_promotion_price_context_story(text, title):
        facets.add("apple-retail-promotion-price-context")
    elif future_price_forecast:
        facets.add("apple-future-product-price-forecast")
    else:
        facets.add("apple-current-product-price-increase")
    if is_apple_price_external_reaction_story(text, title):
        facets.add("apple-price-external-reaction")
    if is_apple_price_stock_market_reaction_story(text, title):
        facets.add("apple-price-stock-market-reaction")
    if is_apple_price_production_plan_response_story(text, title):
        facets.add("apple-price-production-plan-response")
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
    apple_chip_subject_score = score_terms(
        lower,
        [
            "apple silicon",
            "apple chip",
            "apple chips",
            "apple processor",
            "apple processors",
            "apple a-series",
            "a-series chip",
            "a-series processor",
            "m-series chip",
            "m-series processor",
            "a20 chip",
            "a20 processor",
            "a22 chip",
            "a22 processor",
            "苹果芯片",
            "苹果处理器",
            "苹果 a 系列",
            "苹果a系列",
            "a 系列芯片",
            "a系列芯片",
            "m 系列芯片",
            "m系列芯片",
            "a20 芯片",
            "a20芯片",
            "a20 处理器",
            "a20处理器",
            "a22 芯片",
            "a22芯片",
            "a22 处理器",
            "a22处理器",
        ],
    )
    apple_foundry_action_score = score_terms(
        lower,
        [
            "apple will use",
            "apple to use",
            "apple taps",
            "apple orders",
            "apple foundry",
            "for apple",
            "苹果将采用",
            "苹果将使用",
            "苹果采用",
            "苹果使用",
            "苹果下单",
            "苹果订单",
            "苹果代工",
            "代工苹果",
            "为苹果代工",
            "为苹果生产",
            "为苹果制造",
            "代工 a20",
            "代工a20",
        ],
    )
    if apple_chip_subject_score <= 0 and apple_foundry_action_score <= 0:
        return False
    if score_terms(lower, ["chip", "chips", "processor", "processors", "a20", "a22", "tsmc", "process", "node", "wafer", "芯片", "处理器", "台积电", "制程", "工艺", "晶圆"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "14a",
            "18a",
            "18a-p",
            "intel",
            "foundry",
            "fabrication",
            "manufacturing order",
            "outsourced",
            "denied",
            "debunked",
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
            "英特尔",
            "代工",
            "代工订单",
            "代工协议",
            "代工合作",
            "否认",
            "辟谣",
            "工艺",
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
    sourcing_facet = "apple-memory-supplier-sourcing"
    if sourcing_facet in left or sourcing_facet in right:
        supplier_facets = {restricted_facet, sourcing_facet}
        return bool((left & supplier_facets) and (right & supplier_facets))
    return (restricted_facet in left) == (restricted_facet in right)


def strategic_transaction_facets_compatible(left: set[str], right: set[str]) -> bool:
    transaction_facet = "apple-strategic-transaction"
    supplier_facets = {"apple-memory-supplier-sourcing", "apple-restricted-memory-supplier-approval"}
    if (left & supplier_facets) and (right & supplier_facets):
        return True
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
    non_apple_title_subject = score_terms(
        title_lower,
        [
            "android",
            "android brands",
            "smartphone market",
            "安卓",
            "手机市场",
            "手机厂商",
            "安卓厂商",
        ],
    ) > 0
    if score_terms(title_lower, ["apple", "iphone", "ipad", "mac", "macbook", "苹果"]) > 0 and not non_apple_title_subject:
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
    if (
        score_terms(title_lower, ["apple", "iphone", "ipad", "mac", "macbook", "苹果"]) > 0
        and score_terms(
            title_lower,
            [
                "huawei",
                "xiaomi",
                "redmi",
                "vivo",
                "oppo",
                "honor",
                "android",
                "华为",
                "小米",
                "红米",
                "荣耀",
                "安卓",
                "top6",
                "巨头",
                "厂商",
                "阵营",
            ],
        )
        <= 0
    ):
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
            "redmi",
            "vivo",
            "oppo",
            "oneplus",
            "iqoo",
            "honor",
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
            "红米",
            "荣耀",
            "安卓",
            "手机",
            "芯片",
            "top6",
            "厂商",
            "阵营",
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
            "apple android",
            "高通、苹果",
            "苹果和联发科",
            "苹果和高通",
            "苹果、联发科",
            "苹果安卓",
            "苹果、安卓",
            "苹果安卓集体",
            "苹果安卓集体跟进",
            "华为",
            "vivo",
            "荣耀",
            "小米",
            "安卓阵营",
            "top6",
            "巨头集体",
            "几家厂商",
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
            "苹果将成为",
            "苹果将",
            "苹果凭",
            "iphone ultra",
            "折叠屏iphone",
            "折叠屏 iphone",
        ],
    )
    return multi_vendor_context_score > 0 and apple_background_score > 0


def is_non_apple_product_design_reference_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    if score_terms(
        lower,
        [
            "redmi",
            "xiaomi",
            "huawei",
            "honor",
            "vivo",
            "oppo",
            "android",
            "红米",
            "小米",
            "华为",
            "荣耀",
            "安卓",
        ],
    ) <= 0:
        return False
    if score_terms(
        lower,
        [
            "reference iphone",
            "references iphone",
            "iphone-inspired",
            "iphone style",
            "iphone-like",
            "compared with iphone",
            "参考 iphone",
            "参考iphone",
            "配色参考",
            "设计参考",
            "对标 iphone",
            "对标iphone",
            "类似 iphone",
        ],
    ) <= 0:
        return False
    return score_terms(
        lower,
        [
            "apple announced",
            "apple released",
            "apple supplier",
            "苹果宣布",
            "苹果发布",
            "苹果供应商",
        ],
    ) == 0


def is_apple_legal_proceeding_story(text: str) -> bool:
    lower = text.lower()
    if effective_apple_term_score(lower) <= 0:
        return False
    headline = lower[:320]
    legal_headline_score = score_terms(
        headline,
        [
            "lawsuit",
            "sue",
            "sues",
            "suing",
            "sued",
            "court",
            "filing",
            "complaint",
            "jury trial",
            "trade secret",
            "trade secrets",
            "诉讼",
            "起诉",
            "法院",
            "法庭",
            "陪审团",
            "商业秘密",
        ],
    )
    product_render_headline_score = score_terms(
        headline,
        [
            "foldable iphone",
            "iphone fold",
            "iphone ultra",
            "render",
            "renders",
            "mockup",
            "dummy",
            "prototype",
            "leak",
            "rumor",
            "折叠屏",
            "渲染图",
            "机模",
            "样机",
            "泄露",
            "爆料",
        ],
    )
    if product_render_headline_score > 0 and score_terms(
        headline,
        [
            "released",
            "published",
            "shared",
            "showed",
            "revealed",
            "发布",
            "现身",
            "展示",
            "放出",
            "分享",
        ],
    ) > 0:
        return False
    if legal_headline_score <= 0 and product_render_headline_score > 0:
        return False
    proceeding_score = score_terms(
        lower,
        [
            "lawsuit",
            "sue",
            "sues",
            "suing",
            "sued",
            "court",
            "filing",
            "legal filing",
            "complaint",
            "jury trial",
            "trade secret",
            "trade secrets",
            "co-defendant",
            "lawsuit response",
            "诉讼",
            "起诉",
            "法院",
            "法庭",
            "提交文件",
            "法律文件",
            "陪审团",
            "商业秘密",
        ],
    )
    if proceeding_score <= 0:
        return False
    return score_terms(
        lower,
        [
            "prosser",
            "ramacciotti",
            "epic",
            "masimo",
            "doj",
            "department of justice",
            "cma",
            "cci",
            "fas",
            "apple lawsuit",
            "苹果诉讼",
            "苹果起诉",
        ],
    ) > 0 or proceeding_score >= 2


def is_os_point_release_internal_testing_story(text: str) -> bool:
    lower = text.lower()
    versions = {
        match.group(1)
        for match in re.finditer(
            r"(?<!\d)(\d{1,2}\.\d(?:\.\d)?)(?!\d)",
            lower,
        )
    }
    if not versions:
        return False
    if score_terms(lower, ["ios", "ipados", "macos", "watchos", "tvos", "visionos", "系统"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "internal testing",
            "internally testing",
            "testing",
            "visitor logs",
            "access logs",
            "engineers",
            "software engineers",
            "内部测试",
            "内部正测试",
            "正在测试",
            "访问日志",
            "网站日志",
            "软件工程师",
        ],
    ) > 0


def is_apple_watch_band_sensor_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["apple watch", "watch series", "苹果 watch", "苹果手表"]) <= 0:
        return False
    if score_terms(lower, ["band", "bands", "strap", "silicone band", "fluoroelastomer", "表带"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "sensor",
            "sensors",
            "health sensor",
            "glucose",
            "blood glucose",
            "blood sugar",
            "injection molded",
            "embedded",
            "传感器",
            "健康传感器",
            "血糖",
            "注塑",
            "内嵌",
            "嵌入",
        ],
    ) > 0


def is_iphone_image_sensor_supplier_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone", "苹果手机"]) <= 0:
        return False
    if score_terms(lower, ["image sensor", "camera sensor", "图像传感器", "摄像头传感器"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "samsung",
            "sony",
            "supplier",
            "suppliers",
            "supply",
            "produce",
            "factory",
            "austin",
            "texas",
            "三星",
            "索尼",
            "供应",
            "供货",
            "生产",
            "工厂",
            "奥斯汀",
            "得克萨斯",
        ],
    ) > 0


def is_iphone_memory_feature_support_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone 18", "iphone18", "iphone 18e", "iphone18e"]) <= 0:
        return False
    if score_terms(lower, ["9gb", "9 gb", "12gb", "12 gb", "ram", "memory", "内存", "运行内存"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "won't support",
            "will not support",
            "not support",
            "support",
            "feature",
            "features",
            "siri",
            "apple intelligence",
            "ios 27",
            "ios27",
            "缺席",
            "不支持",
            "功能",
            "语音",
            "听写",
            "ai 功能",
            "ai功能",
        ],
    ) > 0


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
    if is_foldable_iphone_supply_chain_story(f"{title} {text}"):
        return False
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
            "pc market",
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
            "gained",
            "growth",
            "gain",
            "gaining",
            "accounted",
            "accounting",
            "increase",
            "increased",
            "increasing",
            "lift",
            "lifted",
            "lifting",
            "outperform",
            "outperformed",
            "bright spot",
            "rising",
            "reaching",
            "同比",
            "增长",
            "提升",
            "达到",
            "创纪录",
            "占",
            "贡献",
            "逆势",
            "唯一亮点",
            "%",
        ],
    ) > 0


def is_apple_broadcom_chip_supply_deal_story(text: str, title: str = "") -> bool:
    scope = f"{title} {text}".lower()
    lead_scope = f"{title} {text[:900]}".lower()
    if score_terms(scope, ["apple", "苹果"]) <= 0 or score_terms(scope, ["broadcom", "博通"]) <= 0:
        return False
    chip_or_component_score = score_terms(
        lead_scope,
        [
            "chip",
            "chips",
            "custom chip",
            "custom chips",
            "asic",
            "radio chip",
            "radio chips",
            "radio frequency",
            "rf",
            "wi-fi",
            "wifi",
            "bluetooth",
            "wireless",
            "networking semiconductor",
            "semiconductor",
            "芯片",
            "定制芯片",
            "射频",
            "无线",
            "组件",
            "模块",
            "半导体",
        ],
    )
    deal_action_score = score_terms(
        lead_scope,
        [
            "extend",
            "extended",
            "expanding",
            "retain",
            "renew",
            "renewed",
            "partnership",
            "agreement",
            "deal",
            "supplier agreement",
            "supply deal",
            "through 2031",
            "to 2031",
            "until 2031",
            "2031",
            "续签",
            "延长",
            "延续",
            "扩大",
            "合作",
            "协议",
            "供应",
            "至2031年",
            "2031 年",
        ],
    )
    return chip_or_component_score > 0 and deal_action_score > 0


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
            "challenge macbook",
            "compete with macbook",
            "rival macbook",
            "beat macbook",
            "macbook-like",
            "like macbook",
            "叫板苹果",
            "赶超苹果",
            "对标苹果",
            "硬刚苹果",
            "媲美苹果",
            "苹果风格",
            "类似苹果",
            "叫板macbook",
            "赶超macbook",
            "对标macbook",
            "硬刚macbook",
            "媲美macbook",
            "macbook 风格",
            "类似 macbook",
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
            "intel",
            "core ",
            "wildcat lake",
            "windows pc",
            "windows laptop",
            "国产",
            "安卓",
            "华为",
            "荣耀",
            "小米",
            "三星",
            "特斯拉",
            "戴森",
            "追觅",
            "英特尔",
            "酷睿",
            "处理器",
            "windows 阵营",
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
    ) > 0 and score_terms(title_lower, ["叫板苹果", "赶超苹果", "对标苹果", "硬刚苹果", "叫板macbook", "赶超macbook", "对标macbook", "硬刚macbook"]) <= 0:
        return False
    if has_apple_first_party_release_context(lower) and score_terms(title_lower, ["叫板苹果", "赶超苹果", "对标苹果", "硬刚苹果", "叫板macbook", "赶超macbook", "对标macbook", "硬刚macbook"]) <= 0:
        return False
    return True


def is_third_party_app_or_service_status_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    combined = f"{title} {text}"
    if is_final_cut_camera_update_story(f"{title} {text}"):
        return False
    if is_apple_creator_studio_story(f"{title} {text}"):
        return False
    if is_direct_iphone_hardware_spec_rumor_story(title, text):
        return False
    if is_foldable_iphone_successor_roadmap_story(f"{title} {text}"):
        return False
    if title_lower.startswith("apple ") or title_lower.startswith("苹果"):
        return False
    if app_store_policy_score(lower) > 0:
        return False
    if is_title_primary_software_system_story(title, combined):
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
            "production target",
            "shipment",
            "shipments",
            "mass production",
            "manufacturing",
            "small batch",
            "expects to sell",
            "expected to sell",
            "sell",
            "sales",
            "order",
            "orders",
            "ordering",
            "panel order",
            "panel orders",
            "10 million",
            "ten million",
            "build target",
            "build targets",
            "unit",
            "units",
            "target guidance",
            "launch target",
            "量产",
            "生产",
            "生产目标",
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
            "panel",
            "panels",
            "display panel",
            "display panels",
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


def is_third_party_platform_app_launch_title(title: str) -> bool:
    lower = title.lower()
    platform_score = score_terms(
        lower,
        [
            "ios version",
            "ios app",
            "native ios app",
            "ipados app",
            "mac app",
            "macos app",
            "watchos app",
            "visionos app",
            "apple watch app",
            "app store",
            "ios 版",
            "ios版",
            "ipados 版",
            "ipados版",
            "mac 版",
            "mac版",
            "macos 版",
            "macos版",
            "watchos 版",
            "watchos版",
            "visionos 版",
            "visionos版",
            "苹果 ios 版",
            "苹果ios版",
            "苹果应用商店",
            "客户端",
            "应用",
            "app",
        ],
    )
    launch_score = score_terms(
        lower,
        [
            "launch",
            "launches",
            "launched",
            "available",
            "released",
            "rolls out",
            "lands",
            "comes to",
            "上线",
            "上架",
            "登陆",
            "登录",
            "发布",
            "推出",
            "适配",
        ],
    )
    if platform_score <= 0 or launch_score <= 0:
        return False
    third_party_subject_score = score_terms(
        lower,
        [
            "google",
            "microsoft",
            "meta",
            "openai",
            "chatgpt",
            "anthropic",
            "claude",
            "perplexity",
            "spotify",
            "netflix",
            "tencent",
            "wechat",
            "bytedance",
            "alibaba",
            "baidu",
            "xiaomi",
            "third-party",
            "third party",
            "谷歌",
            "微软",
            "腾讯",
            "微信",
            "字节",
            "阿里",
            "百度",
            "小米",
            "第三方",
        ],
    )
    quoted_app_subject = bool(
        re.search(r"(?:app|应用|客户端)\s*[“\"'][\w\u4e00-\u9fff -]{1,24}[”\"']", lower)
        or re.search(r"[“\"'][\w\u4e00-\u9fff -]{1,24}[”\"']\s*(?:app|应用|客户端)", lower)
    )
    if third_party_subject_score <= 0 and not quoted_app_subject:
        return False
    if score_terms(
        lower,
        [
            "apple releases",
            "apple launches",
            "apple announces",
            "apple seeds",
            "apple rolls out",
            "苹果发布",
            "苹果推出",
            "苹果宣布",
            "苹果推送",
        ],
    ) > 0:
        return False
    return True


def is_third_party_game_or_cross_platform_launch_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    title_lower = title.lower()
    if has_apple_first_party_release_context(text):
        return False
    if score_terms(lower, ["apple arcade", "苹果 arcade"]) > 0:
        return False
    if score_terms(lower, ["ios", "iphone", "ipad", "app store", "apple", "苹果 ios", "苹果应用商店"]) <= 0:
        return False
    game_or_app_score = score_terms(
        lower,
        [
            "game",
            "rpg",
            "mmo",
            "open-world",
            "sandbox",
            "app",
            "client",
            "游戏",
            "手游",
            "新游",
            "rpg",
            "开放世界",
            "沙盒",
            "客户端",
        ],
    )
    cross_platform_score = score_terms(
        lower,
        [
            "android",
            "harmonyos",
            "pc",
            "steam",
            "cross-platform",
            "multi-platform",
            "data sync",
            "account sync",
            "安卓",
            "鸿蒙",
            "多端",
            "互通",
            "数据互通",
            "账号互通",
            "全平台",
        ],
    )
    launch_score = score_terms(
        lower,
        [
            "launch",
            "launches",
            "launched",
            "release",
            "released",
            "available",
            "public beta",
            "open beta",
            "rolls out",
            "上线",
            "公测",
            "发布",
            "推出",
            "开服",
        ],
    )
    third_party_title_score = score_terms(
        title_lower,
        [
            "tencent",
            "netease",
            "mihoyo",
            "hoyoverse",
            "steam",
            "腾讯",
            "网易",
            "米哈游",
            "第三方",
        ],
    )
    if has_first_party_software_title_subject(title) and not (game_or_app_score > 0 and cross_platform_score > 0):
        return False
    return game_or_app_score > 0 and cross_platform_score > 0 and launch_score > 0 and (
        third_party_title_score > 0 or score_terms(title_lower, ["《", "》"]) > 0
    )


def is_third_party_app_platform_launch_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    lower = text.lower()
    third_party_platform_title = is_third_party_platform_app_launch_title(title)
    if has_first_party_software_title_subject(title) and not third_party_platform_title:
        return False
    if has_apple_first_party_release_context(text) and not third_party_platform_title:
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
    if score_terms(lower, ["apple", "苹果"]) > 0 and score_terms(
        lower,
        ["foldable phone", "folding phone", "foldable smartphone", "可折叠手机", "折叠手机", "折叠屏手机"],
    ) > 0:
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
        score_terms(lower, ["mac", "macs", "m5", "m6", "m7", "apple silicon", "苹果芯片"]) > 0
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
    if is_apple_m6_chip_roadmap_story(text):
        facets.add("apple-m6-chip-roadmap")
    if "mac" in families:
        facets.add("mac-chip-roadmap")
    if "iphone" in families:
        facets.add("iphone-chip-roadmap")
    if "ipad" in families:
        facets.add("ipad-chip-roadmap")
    if not facets:
        facets.add("apple-chip-roadmap")
    return facets


def is_apple_m6_chip_roadmap_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["m6"]) <= 0:
        return False
    if effective_apple_term_score(lower) <= 0 and score_terms(lower, ["mac", "macbook", "ipad pro", "苹果"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "m6 pro",
            "m6 max",
            "m7",
            "base m6",
            "standard m6",
            "skip",
            "skips",
            "skipping",
            "roadmap",
            "lineup",
            "mac mini",
            "imac",
            "mac studio",
            "macbook air",
            "ipad pro",
            "200gb/s",
            "200 gb/s",
            "标准版",
            "基础版",
            "单薄",
            "跳过",
            "规划",
            "产品线",
        ],
    ) > 0


def title_scoped_hardware_product_roadmap_facets(title: str) -> set[str]:
    lower = title.lower()
    if score_terms(
        lower,
        [
            "price",
            "prices",
            "price hike",
            "price hikes",
            "price increase",
            "cost",
            "costs",
            "shipment",
            "shipments",
            "market",
            "trendforce",
            "涨价",
            "调价",
            "价格",
            "成本",
            "出货",
            "市场",
        ],
    ) > 0:
        return set()
    if score_terms(
        lower,
        [
            "launch",
            "launches",
            "release",
            "released",
            "coming",
            "new",
            "refresh",
            "updated",
            "testing",
            "reportedly",
            "spring",
            "fall",
            "2026",
            "2027",
            "推出",
            "发布",
            "新款",
            "更新",
            "测试",
            "春季",
            "秋季",
            "明年",
        ],
    ) <= 0:
        return set()
    families = hardware_product_families_from_text(lower)
    if "macbook" in families:
        families.discard("mac")
    if families == {"macbook"}:
        return {"macbook-product-roadmap"}
    if families == {"ipad"}:
        return {"ipad-product-roadmap"}
    return set()


def title_scoped_foldable_iphone_production_facets(title: str) -> set[str]:
    lower = title.lower()
    if not is_foldable_iphone_production_target_context(lower):
        return set()
    return {"foldable-iphone-supply-chain", "iphone-production-forecast"}


def iphone_hardware_rumor_facets_from_text(text: str) -> set[str]:
    lower = text.lower()
    if score_terms(lower, ["iphone", "iphone 18", "iphone 18 pro", "iphone 18e", "iphone air", "苹果 iPhone".lower()]) <= 0:
        return set()
    facets: set[str] = set()
    if is_iphone_logic_board_leak_story(lower):
        facets.add("iphone-logic-board-leak")
    if (
        score_terms(lower, ["a20", "a20 pro", "iphone 18 pro", "苹果 a20"]) > 0
        and score_terms(
            lower,
            [
                "wmcm",
                "motherboard",
                "logic board",
                "logic-board",
                "package",
                "packaging",
                "side-mounted",
                "side mounted",
                "dram has been moved",
                "主板",
                "逻辑板",
                "封装",
                "晶圆级多芯片模块",
                "多芯片模块",
                "芯片侧边",
                "芯片一侧",
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
    if (
        not is_iphone_photography_awards_story(lower)
        and score_terms(
            lower,
            [
                "production",
                "shipments",
                "shipment forecast",
                "shipment forecasts",
                "output",
                "build target",
                "build targets",
                "demand",
                "cut production",
                "cut",
                "cuts",
                "reduce",
                "reduced",
                "lowered",
                "lowering",
                "削减",
                "下调",
                "减产",
                "出货",
                "产量",
                "生产目标",
                "需求",
            ],
        )
        > 0
    ):
        facets.add("iphone-production-forecast")
    if (
        score_terms(
            lower,
            [
                "camera",
                "cameras",
                "camera control",
                "variable aperture",
                "lidar",
                "sensor",
                "sensors",
                "photo",
                "image upgrade",
                "相机",
                "摄像头",
                "影像",
                "可变光圈",
                "激光雷达",
                "传感器",
            ],
        )
        > 0
    ):
        if score_terms(lower, ["patent", "patently", "专利", "公示", "获批"]) > 0:
            facets.add("iphone-camera-patent")
        else:
            facets.add("iphone-camera-design-leak")
    if score_terms(lower, ["launch date", "debut", "unveil", "event", "september", "gurman", "mark gurman", "发布时间", "发布会", "亮相", "古尔曼", "9 月", "九月"]) > 0:
        facets.add("iphone-launch-timing")
    if score_terms(lower, ["drop test", "drop-test", "drop tests", "drop testing", "drop-test photos", "跌落测试", "坠落测试"]) > 0:
        facets.add("iphone-drop-test-leak")
    if score_terms(lower, ["dynamic island", "face id", "ct scan", "cutout", "hole punch", "front camera", "灵动岛", "ct 扫描", "开孔", "前置摄像头"]) > 0:
        facets.add("iphone-front-cutout")
    if (
        score_terms(lower, ["battery capacity", "battery", "mah", "电池容量", "电池", "毫安时"]) > 0
        and not is_apple_device_battery_regulation_story(lower)
    ):
        facets.add("iphone-battery-capacity-leak")
    if score_terms(lower, ["modem", "baseband", "qualcomm", "c2", "c2 modem", "基带", "调制解调器", "高通"]) > 0:
        facets.add("iphone-modem-spec-leak")
    if score_terms(lower, ["nand", "flash", "qlc", "tlc", "闪存"]) > 0:
        facets.add("iphone-nand-storage-leak")
    if is_iphone_image_sensor_supplier_story(lower):
        facets.add("iphone-image-sensor-supplier")
    if score_terms(lower, ["sim", "esim", "physical sim", "实体 sim", "实体sim", "虚拟卡", "国行版", "中国大陆"]) > 0:
        facets.add("iphone-sim-esim-config")
    if score_terms(lower, ["iphone air 2", "iphone air successor", "next iphone air", "苹果 iphone air 2", "air 2"]) > 0:
        facets.add("iphone-air-successor")
    if (
        score_terms(lower, ["ram", "memory", "9gb", "9 gb", "lpddr", "内存", "9gb 内存", "9gb内存"]) > 0
        and score_terms(lower, ["price", "prices", "涨价", "降回", "不会降", "售价"]) > 0
    ):
        facets.add("iphone-memory-price-forecast")
    if is_iphone_memory_feature_support_story(lower):
        facets.add("iphone-memory-feature-support")
    return facets


def is_iphone_logic_board_leak_story(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone 18 pro", "iphone18 pro", "苹果 iphone 18 pro", "苹果iphone 18 pro"]) <= 0:
        return False
    board_score = score_terms(
        lower,
        [
            "logic board",
            "logic-board",
            "motherboard",
            "board",
            "主板",
            "主板图",
            "主板图纸",
            "逻辑板",
            "电路板",
        ],
    )
    component_score = score_terms(
        lower,
        [
            "a20",
            "a20 pro",
            "lpddr6",
            "wmcm",
            "dram",
            "ram",
            "qualcomm",
            "pmx75",
            "x80",
            "baseband",
            "modem",
            "package",
            "packaging",
            "side-mounted",
            "晶圆级多芯片模块",
            "多芯片模块",
            "主板图纸",
            "逻辑板图纸",
            "芯片参数",
            "供应链清单",
            "内存",
            "高通",
            "基带",
            "调制解调器",
            "封装",
            "芯片侧边",
            "芯片一侧",
        ],
    )
    leak_score = score_terms(
        lower,
        [
            "leak",
            "leaks",
            "leaked",
            "exposed",
            "photo",
            "photos",
            "image",
            "images",
            "曝光",
            "泄露",
            "流传",
            "谍照",
            "实物图",
            "图纸",
            "图片",
        ],
    )
    return board_score > 0 and component_score > 0 and leak_score > 0


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
    if is_apple_executive_event_attendance_story(lower, lower):
        facets.add("apple-executive-event-attendance")
    if is_apple_executive_government_meeting_story(lower, lower):
        facets.add("apple-executive-government-meeting")
    if is_apple_product_legal_proceeding_story(lower, lower) or is_apple_legal_proceeding_story(lower):
        facets.add("apple-legal-proceeding")
        if score_terms(lower, ["airpods max", "condensation", "冷凝", "结露"]) > 0:
            facets.add("airpods-max-condensation-lawsuit")
    if is_apple_chip_tariff_exemption_story(lower, lower):
        facets.add("apple-chip-tariff-exemption")
    if is_direct_apple_regulated_technology_access_story(lower, lower):
        facets.add("apple-regulated-technology-access")
    if is_apple_device_battery_regulation_story(lower):
        facets.add("apple-device-battery-regulation")
    if is_apple_strategic_transaction_story(lower):
        facets.add("apple-strategic-transaction")
        facets |= strategic_transaction_counterparty_facets(lower)
    price_facets = apple_product_price_topic_facets(lower)
    facets |= price_facets
    if is_apple_restricted_memory_supplier_approval_story(lower):
        facets.add("apple-restricted-memory-supplier-approval")
    if is_apple_memory_supplier_sourcing_story(lower):
        facets.add("apple-memory-supplier-sourcing")
    if is_apple_memory_supply_constraint_story(lower):
        facets.add("apple-memory-supply-constraint")
    if is_india_tariff_iphone_manufacturing_story(lower):
        facets.add("india-tariff-iphone-manufacturing")
    if is_siri_ai_lawsuit_settlement_story(lower):
        facets.add("siri-ai-lawsuit-settlement")
    if is_iphone_component_cost_forecast_story(lower):
        facets.add("iphone-component-cost-forecast")
    if is_foldable_iphone_supply_chain_story(lower):
        facets.add("foldable-iphone-supply-chain")
    if is_apple_display_panel_supply_chain_story(lower):
        facets.add("apple-display-panel-supply-chain")
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
    if is_eu_gatekeeper_designation_appeal_story(lower):
        facets.add("eu-gatekeeper-designation-appeal")
    if is_russia_fas_app_preinstall_regulation_story(lower):
        facets.add("russia-fas-app-preinstall-regulation")
    if is_siri_ai_eu_dma_regulatory_meeting_story(lower):
        facets.add("siri-ai-eu-dma-meeting")
    if is_epic_app_store_appeal_story(lower):
        facets.add("epic-app-store-appeal")
    if is_direct_apple_regional_platform_regulation_story(lower, lower):
        facets.add("apple-regional-platform-regulation")
        if score_terms(lower, ["age verification", "age-verify", "age assurance", "年龄验证"]) > 0:
            facets.add("app-store-age-verification")
    if is_apple_pay_rewards_story(lower):
        facets.add("apple-pay-rewards")
    if is_bootrom_secure_rom_exploit_story(lower):
        facets.add("bootrom-secure-rom-exploit")
    if is_find_my_location_sharing_story(lower):
        facets.add("find-my-location-sharing")
    if is_airdrop_vulnerability_story(lower):
        facets.add("airdrop-vulnerability")
    if is_hide_my_email_vulnerability_story(lower):
        facets.add("hide-my-email-vulnerability")
    if is_safari_mcp_server_story(lower):
        facets.add("safari-mcp-server")
    if is_apple_on_device_ai_model_compression_story(lower):
        facets.add("apple-on-device-ai-model-compression")
    if is_final_cut_camera_update_story(lower):
        facets.add("final-cut-camera-update")
    if is_apple_creator_studio_story(lower):
        facets.add("apple-creator-studio")
    if is_iwork_apps_update_story(lower):
        facets.add("iwork-apps-update")
    if is_apple_watch_redesign_story(lower):
        facets.add("apple-watch-redesign")
    if is_apple_watch_band_sensor_story(lower):
        facets.add("apple-watch-band-sensor-rumor")
    if is_apple_watch_band_sensor_story(lower):
        facets.add("apple-watch-band-sensor-rumor")
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
    if is_icloud_service_perk_story(lower):
        facets.add("icloud-service-perks")
    if is_icloud_home_ai_camera_subscription_story(lower):
        facets.add("icloud-home-ai-camera-subscription")
    if is_apple_service_card_payment_restore_story(lower):
        facets.add("app-store-card-payments")
    if is_apple_wallet_car_key_partner_support_story(lower, lower):
        facets.add("apple-wallet-car-key-partner-support")
    if is_camera_airpods_code_clue_story(lower):
        facets.add("camera-airpods-code-clue")
    if is_camera_airpods_development_suspension_story(lower):
        facets.add("camera-airpods-development-suspension")
    if is_direct_apple_airpods_firmware_story(lower, lower):
        facets.add("airpods-firmware-update")
    if is_ios_signing_status_story(lower, lower):
        facets.add("ios-signing-status")
    if is_os_point_release_internal_testing_story(lower):
        facets.add("os-internal-testing")
    if is_apple_watch_band_sensor_story(lower):
        facets.add("apple-watch-band-sensor-rumor")
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
    if is_iphone_photography_awards_story(lower):
        facets.add("iphone-photography-awards")
    if (
        score_terms(lower, ["beats"]) > 0
        and score_terms(lower, ["headphone", "headphones", "earbuds", "耳机", "耳罩"]) > 0
    ):
        facets.add("beats-headphones")
    if (
        score_terms(lower, ["beats"]) > 0
        and score_terms(lower, ["cable", "cables", "charging cable", "power pink", "充电线"]) > 0
    ):
        facets.add("beats-official-cables")
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
    if is_apple_broadcom_chip_supply_deal_story(lower):
        facets.add("apple-broadcom-chip-supply-deal")
    if is_apple_tv_purchase_4k_upgrade_story(lower):
        facets.add("apple-tv-purchase-4k-upgrade")
    if is_apple_tv_awards_nominations_story(lower):
        facets.add("apple-tv-emmy-nominations")
    if is_apple_tv_mlb_schedule_story(lower):
        facets.add("apple-tv-sports-schedule")
    if is_apple_tv_content_event_lineup_story(lower):
        facets.add("apple-tv-content-event-lineup")
    if is_apple_tv_content_trailer_story(lower):
        facets.add("apple-tv-content-trailer")
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
    if is_encrypted_hfs_support_removal_story(lower):
        facets.add("encrypted-hfs-support-removal")
    if is_apple_translate_language_expansion_story(lower):
        facets.add("apple-translate-language-expansion")
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
                "driver's license",
                "driver license",
                "drivers license",
                "state id",
                "state identification",
                "identity verification",
                "nationality verification",
                "数字身份证",
                "数字身份",
                "身份凭证",
                "身份核验",
                "国籍校验",
                "护照",
                "驾驶证",
                "州身份证",
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
    if is_apple_executive_event_attendance_story(lower, lower):
        facets.add("apple-executive-event-attendance")
    if is_apple_executive_government_meeting_story(lower, lower):
        facets.add("apple-executive-government-meeting")
    if is_apple_product_legal_proceeding_story(lower, lower) or is_apple_legal_proceeding_story(lower):
        facets.add("apple-legal-proceeding")
        if score_terms(lower, ["airpods max", "condensation", "冷凝", "结露"]) > 0:
            facets.add("airpods-max-condensation-lawsuit")
    if is_apple_chip_tariff_exemption_story(lower, lower):
        facets.add("apple-chip-tariff-exemption")
    if is_direct_apple_regulated_technology_access_story(lower, lower):
        facets.add("apple-regulated-technology-access")
    if is_apple_device_battery_regulation_story(lower):
        facets.add("apple-device-battery-regulation")
    facets |= apple_product_price_topic_facets(lower)
    if is_apple_restricted_memory_supplier_approval_story(lower):
        facets.add("apple-restricted-memory-supplier-approval")
    if is_apple_memory_supplier_sourcing_story(lower):
        facets.add("apple-memory-supplier-sourcing")
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
    if is_eu_gatekeeper_designation_appeal_story(lower):
        facets.add("eu-gatekeeper-designation-appeal")
    if is_russia_fas_app_preinstall_regulation_story(lower):
        facets.add("russia-fas-app-preinstall-regulation")
    if is_siri_ai_eu_dma_regulatory_meeting_story(lower):
        facets.add("siri-ai-eu-dma-meeting")
    if is_epic_app_store_appeal_story(lower):
        facets.add("epic-app-store-appeal")
    if is_direct_apple_regional_platform_regulation_story(lower, lower):
        facets.add("apple-regional-platform-regulation")
        if score_terms(lower, ["age verification", "age-verify", "age assurance", "年龄验证"]) > 0:
            facets.add("app-store-age-verification")
    if is_apple_pay_rewards_story(lower):
        facets.add("apple-pay-rewards")
    if is_apple_service_card_payment_restore_story(lower):
        facets.add("app-store-card-payments")
    if is_apple_wallet_car_key_partner_support_story(lower, lower):
        facets.add("apple-wallet-car-key-partner-support")
    if is_icloud_home_ai_camera_subscription_story(lower):
        facets.add("icloud-home-ai-camera-subscription")
    if is_airdrop_vulnerability_story(lower):
        facets.add("airdrop-vulnerability")
    if is_hide_my_email_vulnerability_story(lower):
        facets.add("hide-my-email-vulnerability")
    if is_safari_mcp_server_story(lower):
        facets.add("safari-mcp-server")
    if is_apple_on_device_ai_model_compression_story(lower):
        facets.add("apple-on-device-ai-model-compression")
    if is_final_cut_camera_update_story(lower):
        facets.add("final-cut-camera-update")
    if is_apple_creator_studio_story(lower):
        facets.add("apple-creator-studio")
    if is_iwork_apps_update_story(lower):
        facets.add("iwork-apps-update")
    if is_apple_watch_redesign_story(lower):
        facets.add("apple-watch-redesign")
    if is_apple_watch_band_sensor_story(lower):
        facets.add("apple-watch-band-sensor-rumor")
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
    if is_os_point_release_internal_testing_story(lower):
        facets.add("os-internal-testing")
    if is_foldable_iphone_successor_roadmap_story(lower):
        facets.add("foldable-iphone-successor-roadmap")
    if is_foldable_iphone_supply_chain_story(lower):
        facets.add("foldable-iphone-supply-chain")
    if is_apple_display_panel_supply_chain_story(lower):
        facets.add("apple-display-panel-supply-chain")
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
    if is_camera_airpods_code_clue_story(lower):
        facets.add("camera-airpods-code-clue")
    if is_camera_airpods_development_suspension_story(lower):
        facets.add("camera-airpods-development-suspension")
    if is_direct_apple_airpods_firmware_story(lower, lower):
        facets.add("airpods-firmware-update")
    if is_ios_signing_status_story(lower, lower):
        facets.add("ios-signing-status")
    if is_encrypted_hfs_support_removal_story(lower):
        facets.add("encrypted-hfs-support-removal")
    if is_apple_translate_language_expansion_story(lower):
        facets.add("apple-translate-language-expansion")
    if is_apple_tv_purchase_4k_upgrade_story(lower):
        facets.add("apple-tv-purchase-4k-upgrade")
    if is_apple_tv_awards_nominations_story(lower):
        facets.add("apple-tv-emmy-nominations")
    if is_apple_tv_mlb_schedule_story(lower):
        facets.add("apple-tv-sports-schedule")
    if is_apple_tv_content_event_lineup_story(lower):
        facets.add("apple-tv-content-event-lineup")
    if is_apple_tv_content_trailer_story(lower):
        facets.add("apple-tv-content-trailer")
    if (
        score_terms(lower, ["beats"]) > 0
        and score_terms(lower, ["cable", "cables", "charging cable", "power pink", "充电线"]) > 0
    ):
        facets.add("beats-official-cables")
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
    "iphone-battery-capacity-leak",
    "iphone-camera-design-leak",
    "iphone-camera-patent",
    "iphone-chip-packaging",
    "iphone-drop-test-leak",
    "iphone-front-cutout",
    "iphone-launch-timing",
    "iphone-logic-board-leak",
    "iphone-memory-feature-support",
    "iphone-memory-price-forecast",
    "iphone-modem-spec-leak",
    "iphone-nand-storage-leak",
    "iphone-physical-dimension-rumor",
    "iphone-image-sensor-supplier",
    "iphone-photography-awards",
    "iphone-production-forecast",
    "iphone-sim-esim-config",
    "iphone-thermal-design",
}
SPLITTABLE_HARDWARE_TOPIC_FACETS = {
    "apple-product-roadmap-list",
    "apple-company-org-change",
    *APPLE_PRICE_SUBTOPIC_FACETS,
    "apple-display-panel-supply-chain",
    "apple-device-battery-regulation",
    "apple-memory-supplier-sourcing",
    "apple-product-data-leak",
    "apple-product-data-leak-enforcement",
    "apple-product-data-leak-specs",
    "apple-product-price-increase",
    "apple-refurbished-iphone",
    "apple-refurbished-ipad",
    "apple-refurbished-mac",
    "apple-refurbished-product",
    "apple-tv-hardware",
    "apple-watch-band-sensor-rumor",
    "apple-watch-redesign",
    "beats-official-cables",
    "beats-headphones",
    "foldable-iphone-render-leak",
    "foldable-iphone-successor-roadmap",
    "foldable-iphone-supply-chain",
    *IPHONE_HARDWARE_RUMOR_TOPIC_FACETS,
    "iphone-color-mockup",
    "macbook-memory-ai",
    "macbook-thermal-defect",
    "macbook-product-roadmap",
    "macbook-touch-roadmap",
    "apple-chip-roadmap",
    "apple-chip-process-roadmap",
    "apple-memory-supply-constraint",
    "ipad-chip-roadmap",
    "ipad-product-roadmap",
    "iphone-chip-roadmap",
    "mac-chip-roadmap",
    "apple-market-share-report",
    "apple-executive-event-attendance",
    "apple-executive-government-meeting",
    "vision-pro-spatial-experience",
}
SPLITTABLE_SERVICE_TOPIC_FACETS = {
    "apple-arcade",
    "apple-creator-studio",
    "apple-music",
    "apple-music-top-artists",
    "apple-tv-content",
    "apple-tv-content-event-lineup",
    "apple-tv-content-trailer",
    "apple-tv-emmy-nominations",
    "apple-tv-sports-schedule",
    "apple-tv-purchase-4k-upgrade",
    "final-cut-camera-update",
    "iwork-apps-update",
    "icloud-home-ai-camera-subscription",
    "icloud-service-perks",
}
SPLITTABLE_POLICY_TOPIC_FACETS = APP_STORE_POLICY_SUBTOPIC_FACETS | {
    "airdrop-vulnerability",
    "apple-legal-proceeding",
    "airpods-max-condensation-lawsuit",
    "apple-wallet-digital-id",
    "apple-wallet-car-key-partner-support",
    "apple-regional-platform-regulation",
    "apple-regulated-technology-access",
    "app-store-age-verification",
    "apple-on-device-ai-model-compression",
    "eu-gatekeeper-designation-appeal",
    "hide-my-email-vulnerability",
    "india-tariff-iphone-manufacturing",
    "iphone-component-cost-forecast",
    "keyboard-input-method",
    "os-internal-testing",
    "russia-fas-app-preinstall-regulation",
    "safari-mcp-server",
    "siri-ai-lawsuit-settlement",
    "uk-cma-app-store-payment-nfc",
}
SPLITTABLE_OS_TOPIC_FACETS = {
    "airpods-firmware-update",
    "built-in-app-change",
    "ai-wallpaper",
    "apple-translate-language-expansion",
    "encrypted-hfs-support-removal",
    "ios-signing-status",
    "os-release-beta",
    "os-release-final",
    "os-release-rc",
    "os-release-security",
    "siri-voice-customization",
    "system-wallpaper",
    "watchos-siri-findmy-apps",
}
SPLITTABLE_TOPIC_FACETS = (
    SPLITTABLE_HARDWARE_TOPIC_FACETS
    | SPLITTABLE_SERVICE_TOPIC_FACETS
    | SPLITTABLE_POLICY_TOPIC_FACETS
    | SPLITTABLE_OS_TOPIC_FACETS
)
EXACT_SHARED_EVENT_TOPIC_FACETS = {
    "apple-chip-tariff-exemption",
    "apple-executive-event-attendance",
    "apple-on-device-ai-model-compression",
    "apple-translate-language-expansion",
    "apple-tv-emmy-nominations",
    "apple-tv-purchase-4k-upgrade",
    "apple-tv-sports-schedule",
    "apple-wallet-digital-id",
    "apple-wallet-car-key-partner-support",
    "encrypted-hfs-support-removal",
    "eu-gatekeeper-designation-appeal",
    "icloud-home-ai-camera-subscription",
    "india-tariff-iphone-manufacturing",
    "iphone-component-cost-forecast",
    "siri-ai-lawsuit-settlement",
    "uk-cma-app-store-payment-nfc",
}
BRIDGE_SPLIT_TOPIC_FACETS = {"apple-chip-roadmap", "iphone-chip-roadmap", "mac-chip-roadmap", "hardware-roadmap"}
NO_SPLIT_SHARED_CORE_TOPIC_FACETS = {
    "apple-product-data-leak",
    "iphone-logic-board-leak",
}
TITLE_DOMINANT_TOPIC_FACETS = {
    "apple-device-battery-regulation",
    "apple-refurbished-iphone",
    "apple-refurbished-ipad",
    "apple-refurbished-mac",
    "apple-refurbished-product",
    "foldable-iphone-render-leak",
    "iphone-air-successor",
    "iphone-color-mockup",
    "iphone-image-sensor-supplier",
    "iphone-drop-test-leak",
}
DATA_LEAK_ENFORCEMENT_OBJECT_FACETS = {
    "iphone-color-mockup",
    "iphone-drop-test-leak",
}
SOFTWARE_SUMMARY_HARDWARE_NOISE_FACETS = IPHONE_HARDWARE_RUMOR_TOPIC_FACETS | {
    "apple-chip-process-roadmap",
    "apple-chip-roadmap",
    "hardware-roadmap",
    "iphone-chip-roadmap",
}


def _primary_topic_facets(title: str, summary: str = "") -> frozenset[str]:
    title_facets = topic_facets_from_text(title)
    combined_text = f"{title} {summary}"
    combined_facets = topic_facets_from_text(combined_text)
    signing_facets = (title_facets | combined_facets) & (
        {"ios-signing-status"} | os_release_version_facets(title_facets | combined_facets) | merge_guard_platform_facets(title_facets | combined_facets)
    )
    if "ios-signing-status" in signing_facets:
        return frozenset(signing_facets)
    if is_os_release_availability_title(title) and not os_release_title_specific_facets_from_title(title):
        title_release_facets = os_release_facets_from_text(title)
        if title_release_facets:
            return frozenset(title_release_facets)
    camera_airpods_facets = combined_facets & {"camera-airpods-code-clue", "camera-airpods-development-suspension"}
    if camera_airpods_facets:
        if "camera-airpods-code-clue" in title_facets:
            return frozenset({"camera-airpods-code-clue"})
        if "camera-airpods-development-suspension" in title_facets:
            return frozenset({"camera-airpods-development-suspension"})
        if "camera-airpods-code-clue" in camera_airpods_facets and score_terms(
            f"{title} {summary}".lower(),
            ["b790", "code", "developer beta", "system_prompt", "代码", "开发者测试版"],
        ) > 0:
            return frozenset({"camera-airpods-code-clue"})
        return frozenset(camera_airpods_facets)
    if is_apple_chip_tariff_exemption_story(title, combined_text):
        return frozenset({"apple-chip-tariff-exemption"})
    if (
        is_direct_apple_regulated_technology_access_story(title, combined_text)
        and not is_apple_restricted_memory_supplier_approval_story(combined_text)
        and not is_apple_memory_supplier_sourcing_story(combined_text)
    ):
        return frozenset({"apple-regulated-technology-access"})
    if is_apple_device_battery_regulation_story(combined_text):
        return frozenset({"apple-device-battery-regulation"})
    if "apple-legal-proceeding" in title_facets:
        legal_specific = title_facets & SPLITTABLE_POLICY_TOPIC_FACETS
        return frozenset(legal_specific or {"apple-legal-proceeding"})
    if "iphone-memory-feature-support" in combined_facets:
        return frozenset({"iphone-memory-feature-support"})
    if is_direct_apple_os_component_change_story(title, combined_text):
        specific_facets = combined_facets & (EXACT_SHARED_EVENT_TOPIC_FACETS | APP_STORE_POLICY_SUBTOPIC_FACETS)
        if specific_facets:
            return frozenset(specific_facets | merge_guard_platform_facets(combined_facets))
        software_facets = (
            title_facets
            - SOFTWARE_SUMMARY_HARDWARE_NOISE_FACETS
            - {"apple-product-data-leak", "apple-product-data-leak-enforcement", "apple-product-data-leak-specs"}
        )
        meaningful_facets = software_facets - {"built-in-app-change"} - merge_guard_platform_facets(software_facets)
        if meaningful_facets:
            software_facets.discard("built-in-app-change")
        else:
            software_facets.add("built-in-app-change")
        return frozenset(software_facets)
    title_product_roadmap_facets = title_scoped_hardware_product_roadmap_facets(title)
    if title_product_roadmap_facets:
        return frozenset(title_product_roadmap_facets | (title_facets - BROAD_TOPIC_FACETS))
    title_foldable_production_facets = title_scoped_foldable_iphone_production_facets(title)
    if title_foldable_production_facets:
        return frozenset(title_foldable_production_facets | (title_facets - BROAD_TOPIC_FACETS))
    if "iphone-memory-feature-support" in combined_facets:
        return frozenset({"iphone-memory-feature-support"})
    exact_shared_facets = combined_facets & EXACT_SHARED_EVENT_TOPIC_FACETS
    if exact_shared_facets:
        return frozenset(exact_shared_facets | merge_guard_platform_facets(combined_facets))
    if is_apple_os_feature_or_summary_story(combined_text) and is_title_primary_software_system_story(title, combined_text):
        software_facets = os_feature_specific_facets(combined_facets - SOFTWARE_SUMMARY_HARDWARE_NOISE_FACETS)
        if software_facets:
            return frozenset(software_facets)
    if is_iphone_physical_dimension_rumor_story(title, combined_text):
        return frozenset({"iphone-physical-dimension-rumor"})
    data_leak_detail_facets = {"apple-product-data-leak-enforcement", "apple-product-data-leak-specs"}
    if "apple-product-data-leak-enforcement" in title_facets:
        enforcement_facets = title_facets - DATA_LEAK_ENFORCEMENT_OBJECT_FACETS
        return frozenset(enforcement_facets or title_facets)
    if title_facets & TITLE_DOMINANT_TOPIC_FACETS:
        dominant_facets = title_facets - data_leak_detail_facets - {"apple-product-data-leak"}
        return frozenset(dominant_facets or title_facets)
    if (
        is_apple_chip_process_roadmap_story(combined_text)
        and score_terms(
            title.lower(),
            ["14a", "18a", "18a-p", "intel", "tsmc", "foundry", "英特尔", "台积电", "制程", "工艺", "代工订单", "代工协议", "代工合作"],
        )
        > 0
    ):
        return frozenset({"apple-chip-process-roadmap"})
    if title_facets & data_leak_detail_facets:
        return frozenset(title_facets)
    if combined_facets & data_leak_detail_facets:
        return frozenset(combined_facets)
    if "apple-creator-studio" in title_facets:
        return frozenset(title_facets)
    if "final-cut-camera-update" in combined_facets:
        return frozenset({"final-cut-camera-update"})
    if "app-store-policy" in title_facets and "brazil-app-store-policy" in combined_facets:
        return frozenset(combined_facets)
    if combined_facets & APP_STORE_POLICY_SUBTOPIC_FACETS:
        return frozenset(combined_facets)
    memory_supplier_facets = combined_facets & {"apple-restricted-memory-supplier-approval", "apple-memory-supplier-sourcing"}
    if memory_supplier_facets:
        return frozenset(memory_supplier_facets)
    if "visionos-m5-ai-features" in combined_facets:
        return frozenset(combined_facets)
    if "iphone-component-cost-forecast" in combined_facets:
        return frozenset(
            {"iphone-component-cost-forecast"}
            | (combined_facets & {"apple-product-price-increase", "apple-future-product-price-forecast"})
        )
    market_report_primary = (
        "apple-market-share-report" in combined_facets
        and not is_foldable_iphone_panel_market_report_context(combined_text)
        and (
            is_apple_specific_market_share_report_story(title, "")
            or ("apple-product-price-increase" not in title_facets and is_apple_specific_market_share_report_story(combined_text, title))
        )
    )
    if market_report_primary:
        return frozenset({"apple-market-share-report"} | merge_guard_platform_facets(combined_facets))
    if "apple-product-price-increase" in title_facets:
        combined_price_details = price_detail_facets(combined_facets)
        title_price_details = price_detail_facets(title_facets)
        if combined_price_details and not title_price_details:
            return frozenset(title_facets | combined_price_details)
    if title_facets and (title_facets - BROAD_TOPIC_FACETS):
        return frozenset(title_facets)
    return frozenset(combined_facets or title_facets)


@lru_cache(maxsize=16384)
def cached_primary_topic_facets(title: str, summary: str = "") -> frozenset[str]:
    return _primary_topic_facets(title, summary)


def primary_topic_facets(title: str, summary: str = "") -> set[str]:
    return set(cached_primary_topic_facets(title, summary))


def _primary_merge_guard_facets(title: str, summary: str = "") -> frozenset[str]:
    title_facets = merge_guard_facets_from_text(title)
    combined_text = f"{title} {summary}"
    combined_facets = merge_guard_facets_from_text(combined_text)
    signing_facets = (title_facets | combined_facets) & (
        {"ios-signing-status"} | os_release_version_facets(title_facets | combined_facets) | merge_guard_platform_facets(title_facets | combined_facets)
    )
    if "ios-signing-status" in signing_facets:
        return frozenset(signing_facets)
    if is_os_release_availability_title(title) and not os_release_title_specific_facets_from_title(title):
        title_release_facets = os_release_facets_from_text(title)
        if title_release_facets:
            return frozenset(title_release_facets)
    camera_airpods_facets = combined_facets & {"camera-airpods-code-clue", "camera-airpods-development-suspension"}
    if camera_airpods_facets:
        if "camera-airpods-code-clue" in title_facets:
            return frozenset({"camera-airpods-code-clue"})
        if "camera-airpods-development-suspension" in title_facets:
            return frozenset({"camera-airpods-development-suspension"})
        if "camera-airpods-code-clue" in camera_airpods_facets and score_terms(
            f"{title} {summary}".lower(),
            ["b790", "code", "developer beta", "system_prompt", "代码", "开发者测试版"],
        ) > 0:
            return frozenset({"camera-airpods-code-clue"})
        return frozenset(camera_airpods_facets)
    if is_apple_chip_tariff_exemption_story(title, combined_text):
        return frozenset({"apple-chip-tariff-exemption"})
    if (
        is_direct_apple_regulated_technology_access_story(title, combined_text)
        and not is_apple_restricted_memory_supplier_approval_story(combined_text)
        and not is_apple_memory_supplier_sourcing_story(combined_text)
    ):
        return frozenset({"apple-regulated-technology-access"})
    if is_apple_device_battery_regulation_story(combined_text):
        return frozenset({"apple-device-battery-regulation"})
    if "apple-legal-proceeding" in title_facets:
        legal_specific = title_facets & SPLITTABLE_POLICY_TOPIC_FACETS
        return frozenset(legal_specific or {"apple-legal-proceeding"})
    if "iphone-memory-feature-support" in combined_facets:
        return frozenset({"iphone-memory-feature-support"} | merge_guard_platform_facets(combined_facets))
    if is_direct_apple_os_component_change_story(title, combined_text):
        specific_facets = combined_facets & (EXACT_SHARED_EVENT_TOPIC_FACETS | APP_STORE_POLICY_SUBTOPIC_FACETS)
        if specific_facets:
            return frozenset(specific_facets | merge_guard_platform_facets(combined_facets))
        software_facets = (
            title_facets
            - SOFTWARE_SUMMARY_HARDWARE_NOISE_FACETS
            - {"apple-product-data-leak", "apple-product-data-leak-enforcement", "apple-product-data-leak-specs"}
        )
        meaningful_facets = software_facets - {"built-in-app-change"} - merge_guard_platform_facets(software_facets)
        if meaningful_facets:
            software_facets.discard("built-in-app-change")
        else:
            software_facets.add("built-in-app-change")
        return frozenset(software_facets)
    title_product_roadmap_facets = title_scoped_hardware_product_roadmap_facets(title)
    if title_product_roadmap_facets:
        return frozenset(title_product_roadmap_facets | (title_facets - BROAD_TOPIC_FACETS))
    title_foldable_production_facets = title_scoped_foldable_iphone_production_facets(title)
    if title_foldable_production_facets:
        return frozenset(title_foldable_production_facets | (title_facets - BROAD_TOPIC_FACETS))
    if "iphone-memory-feature-support" in combined_facets:
        return frozenset({"iphone-memory-feature-support"} | merge_guard_platform_facets(combined_facets))
    exact_shared_facets = combined_facets & EXACT_SHARED_EVENT_TOPIC_FACETS
    if exact_shared_facets:
        return frozenset(exact_shared_facets | merge_guard_platform_facets(combined_facets))
    if is_apple_os_feature_or_summary_story(combined_text) and is_title_primary_software_system_story(title, combined_text):
        software_facets = os_feature_specific_facets(combined_facets - SOFTWARE_SUMMARY_HARDWARE_NOISE_FACETS)
        if software_facets:
            return frozenset(software_facets)
    if is_iphone_physical_dimension_rumor_story(title, combined_text):
        return frozenset({"iphone-physical-dimension-rumor"} | merge_guard_platform_facets(combined_facets))
    if "apple-creator-studio" in title_facets:
        return frozenset(title_facets)
    if "final-cut-camera-update" in combined_facets:
        return frozenset({"final-cut-camera-update"})
    if "apple-restricted-memory-supplier-approval" in combined_facets or "apple-memory-supplier-sourcing" in combined_facets:
        return frozenset(combined_facets)
    if "iphone-component-cost-forecast" in combined_facets:
        return frozenset({"iphone-component-cost-forecast"} | merge_guard_platform_facets(combined_facets))
    if "apple-watch-band-sensor-rumor" in combined_facets:
        return frozenset({"apple-watch-band-sensor-rumor"} | merge_guard_platform_facets(combined_facets))
    if "apple-product-price-increase" in title_facets:
        combined_price_details = price_detail_facets(combined_facets)
        title_price_details = price_detail_facets(title_facets)
        if combined_price_details and not title_price_details:
            return frozenset(title_facets | combined_price_details)
    if (
        is_apple_chip_process_roadmap_story(combined_text)
        and score_terms(
            title.lower(),
            ["14a", "18a", "18a-p", "intel", "tsmc", "foundry", "英特尔", "台积电", "制程", "工艺", "代工订单", "代工协议", "代工合作"],
        )
        > 0
    ):
        return frozenset({"apple-chip-process-roadmap"})
    if title_facets and merge_guard_action_facets(title_facets):
        return frozenset(title_facets)
    return frozenset(combined_facets or title_facets)


@lru_cache(maxsize=16384)
def cached_primary_merge_guard_facets(title: str, summary: str = "") -> frozenset[str]:
    return _primary_merge_guard_facets(title, summary)


def primary_merge_guard_facets(title: str, summary: str = "") -> set[str]:
    return set(cached_primary_merge_guard_facets(title, summary))


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
        "apple-product-roadmap-list",
        "apple-chip-process-roadmap",
        "apple-product-data-leak",
    "apple-product-data-leak-enforcement",
    "apple-product-data-leak-specs",
        "apple-legal-proceeding",
        "airpods-max-condensation-lawsuit",
        "airpods-firmware-update",
        "app-store-age-verification",
        "apple-wallet-digital-id",
        "apple-executive-event-attendance",
        "apple-translate-language-expansion",
        "apple-tv-emmy-nominations",
        "apple-tv-purchase-4k-upgrade",
        "apple-wallet-car-key-partner-support",
        "encrypted-hfs-support-removal",
        "eu-gatekeeper-designation-appeal",
        "icloud-home-ai-camera-subscription",
        "apple-memory-supplier-sourcing",
        "apple-refurbished-iphone",
        "apple-refurbished-ipad",
        "apple-refurbished-mac",
        "apple-refurbished-product",
        "camera-airpods-code-clue",
        "camera-airpods-development-suspension",
        "apple-watch-band-sensor-rumor",
        "ipad-product-roadmap",
        "macbook-product-roadmap",
        "foldable-iphone-render-leak",
        "foldable-iphone-successor-roadmap",
        "foldable-iphone-supply-chain",
        "final-cut-camera-update",
        "ios-signing-status",
        "iphone-color-mockup",
        "iphone-image-sensor-supplier",
        "hide-my-email-vulnerability",
        "keyboard-input-method",
        "apple-legal-proceeding",
        "apple-on-device-ai-model-compression",
        "os-internal-testing",
        "russia-fas-app-preinstall-regulation",
        "safari-mcp-server",
        "siri-ai-lawsuit-settlement",
        "india-tariff-iphone-manufacturing",
        "iphone-component-cost-forecast",
        "apple-tv-content-event-lineup",
        "apple-tv-content-trailer",
        "apple-tv-sports-schedule",
    }
    return facets & iphone_rumor_boundary_facets


def splittable_topic_facets_compatible(left_facets: set[str], right_facets: set[str]) -> bool:
    left = independent_splittable_topic_facets(effective_topic_facets(left_facets))
    right = independent_splittable_topic_facets(effective_topic_facets(right_facets))
    if not left and (effective_topic_facets(left_facets) & SPLITTABLE_TOPIC_FACETS):
        left = effective_topic_facets(left_facets) & SPLITTABLE_TOPIC_FACETS
    if not right and (effective_topic_facets(right_facets) & SPLITTABLE_TOPIC_FACETS):
        right = effective_topic_facets(right_facets) & SPLITTABLE_TOPIC_FACETS
    if not left or not right:
        return True
    shared = left & right
    allowed_foldable_panel_facets = {
        "apple-display-panel-supply-chain",
        "foldable-iphone-supply-chain",
        "iphone-production-forecast",
    }
    if (
        (left | right) <= allowed_foldable_panel_facets
        and "apple-display-panel-supply-chain" in (left | right)
        and "foldable-iphone-supply-chain" in (left | right)
    ):
        return True
    if not shared:
        return False
    if "iphone-logic-board-leak" in shared:
        allowed_logic_board_facets = {
            "apple-display-panel-supply-chain",
            "apple-product-data-leak",
            "apple-product-data-leak-specs",
            "iphone-camera-design-leak",
            "iphone-chip-packaging",
            "iphone-drop-test-leak",
            "iphone-launch-timing",
            "iphone-logic-board-leak",
            "iphone-modem-spec-leak",
            "iphone-nand-storage-leak",
            "iphone-thermal-design",
        }
        if left <= allowed_logic_board_facets and right <= allowed_logic_board_facets:
            return True
    if "system-wallpaper" in shared or "ai-wallpaper" in shared:
        return True
    if left == right:
        return True
    if "apple-watch-band-sensor-rumor" in shared:
        return True
    if "iphone-air-successor" in shared:
        return True
    if "iphone-color-mockup" in shared:
        allowed_color_facets = {"iphone-color-mockup", "iphone-sim-esim-config", "iphone-front-cutout"}
        if left <= allowed_color_facets and right <= allowed_color_facets:
            return True
    if "foldable-iphone-supply-chain" in shared:
        allowed_foldable_supply_facets = {
            "apple-display-panel-supply-chain",
            "foldable-iphone-supply-chain",
            "iphone-launch-timing",
            "iphone-production-forecast",
        }
        if left <= allowed_foldable_supply_facets and right <= allowed_foldable_supply_facets:
            return True
    if "ipad-product-roadmap" in shared:
        allowed_ipad_roadmap_facets = {
            "ipad-product-roadmap",
            "ipad-chip-roadmap",
        }
        if left <= allowed_ipad_roadmap_facets and right <= allowed_ipad_roadmap_facets:
            return True
    if "macbook-product-roadmap" in shared:
        allowed_macbook_roadmap_facets = {
            "macbook-product-roadmap",
            "macbook-touch-roadmap",
            "mac-chip-roadmap",
        }
        if left <= allowed_macbook_roadmap_facets and right <= allowed_macbook_roadmap_facets:
            return True
    if "apple-product-data-leak" in left or "apple-product-data-leak" in right:
        strict_leak_detail_facets = {
            "apple-product-data-leak-enforcement",
            "iphone-drop-test-leak",
        }
        if (left & strict_leak_detail_facets) or (right & strict_leak_detail_facets):
            return bool(
                (left & strict_leak_detail_facets)
                and (right & strict_leak_detail_facets)
                and (left & right & strict_leak_detail_facets)
            )
        spec_leak_detail_facets = {
            "apple-product-data-leak-specs",
            "iphone-battery-capacity-leak",
            "iphone-camera-design-leak",
            "iphone-chip-packaging",
            "iphone-color-mockup",
            "iphone-front-cutout",
            "iphone-logic-board-leak",
            "iphone-modem-spec-leak",
            "iphone-nand-storage-leak",
            "iphone-sim-esim-config",
        }
        allowed_data_leak_facets = {"apple-product-data-leak", *spec_leak_detail_facets}
        narrow_spec_leak_detail_facets = {
            "iphone-modem-spec-leak",
            "iphone-nand-storage-leak",
        }
        left_narrow_specs = left & narrow_spec_leak_detail_facets
        right_narrow_specs = right & narrow_spec_leak_detail_facets
        if left_narrow_specs and right_narrow_specs and not (left_narrow_specs & right_narrow_specs):
            return False
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


def event_title_scoped_hardware_product_roadmap_facets(event: Event) -> set[str]:
    facets: set[str] = set()
    for article in event.articles:
        facets |= title_scoped_hardware_product_roadmap_facets(article.title)
    return facets


def effective_topic_facets(facets: set[str]) -> set[str]:
    specific = facets - BROAD_TOPIC_FACETS
    return specific or facets


def os_feature_specific_facets(facets: set[str]) -> set[str]:
    release_facets = os_release_version_facets(facets) | os_release_channel_facets(facets)
    platform_facets = merge_guard_platform_facets(facets) | {"platform-mobile-os"}
    broad_os_facets = {"system-summary"}
    specific = facets - release_facets - platform_facets - broad_os_facets
    return specific or facets


def foldable_panel_supply_facets_compatible(left_facets: set[str], right_facets: set[str]) -> bool:
    allowed = {
        "apple-display-panel-supply-chain",
        "foldable-iphone-supply-chain",
        "iphone-production-forecast",
    }
    left = effective_topic_facets(left_facets) & allowed
    right = effective_topic_facets(right_facets) & allowed
    if not left or not right:
        return False
    union = left | right
    return (
        union <= allowed
        and "apple-display-panel-supply-chain" in union
        and ("foldable-iphone-supply-chain" in union or "iphone-production-forecast" in union)
    )


def merge_guard_platform_facets(facets: set[str]) -> set[str]:
    return {facet for facet in facets if facet.startswith("platform-")}


def merge_guard_action_facets(facets: set[str]) -> set[str]:
    return facets - merge_guard_platform_facets(facets)


def platform_only_shared_topic_facets(left_facets: set[str], right_facets: set[str]) -> bool:
    shared = left_facets & right_facets
    if not shared:
        return False
    platform_facets = merge_guard_platform_facets(shared) | {"platform-mobile-os"}
    return shared <= platform_facets


def non_platform_topic_facets(facets: set[str]) -> set[str]:
    return facets - merge_guard_platform_facets(facets) - {"platform-mobile-os"}


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
    if foldable_panel_supply_facets_compatible(article_actions, event_actions):
        return True
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
    if is_official_apple_privacy_ad_campaign_story(text):
        return "security_privacy"
    if is_apple_executive_event_attendance_story(title, text):
        return "company_org"
    if is_camera_airpods_code_clue_story(text) or is_camera_airpods_development_suspension_story(text):
        return "hardware_market"
    if is_iphone_photography_awards_story(text):
        return "hardware_market"
    if is_apple_service_card_payment_restore_story(text):
        return "app_store_trust"
    if is_apple_chip_tariff_exemption_story(title, text):
        return "regional_regulation"
    if (
        is_direct_apple_regulated_technology_access_story(title, text)
        and not is_apple_restricted_memory_supplier_approval_story(text)
        and not is_apple_memory_supplier_sourcing_story(text)
    ):
        return "regional_regulation"
    if is_apple_device_battery_regulation_story(text):
        return "hardware_market"
    if is_ai_generated_apple_product_image_debunk_without_new_action(title, text):
        return "third_party_ecosystem"
    if is_direct_apple_os_component_change_story(title, text):
        return "os_app"
    if is_third_party_cross_platform_desktop_client_update(title, text):
        return "third_party_ecosystem"
    if is_icloud_service_perk_story(text):
        return "service_content"
    if is_icloud_home_ai_camera_subscription_story(text):
        return "service_content"
    if is_safari_mcp_server_story(text):
        return "developer_tool"
    if is_final_cut_camera_update_story(text):
        return "os_app"
    if is_apple_wallet_car_key_partner_support_story(title, text):
        return "wallet_feature"
    if is_hide_my_email_vulnerability_story(text):
        return "security_privacy"
    if is_airdrop_vulnerability_story(text):
        return "security_privacy"
    if is_apple_tv_hardware_story(title):
        return "hardware_market"
    if is_apple_on_device_ai_model_compression_story(text):
        return "os_app"
    if is_india_tariff_iphone_manufacturing_story(text):
        return "hardware_market"
    if is_russia_fas_app_preinstall_regulation_story(text):
        return "regional_regulation"
    if is_apple_memory_supplier_sourcing_story(text):
        return "hardware_market"
    if is_apple_broadcom_chip_supply_deal_story(text, title):
        return "hardware_market"
    if is_broad_multi_vendor_market_report(text, title):
        return "third_party_ecosystem"
    if is_apple_specific_market_share_report_story(text, title):
        return "hardware_market"
    if is_apple_product_legal_proceeding_story(title, text) or is_apple_legal_proceeding_story(text):
        return "legal_antitrust"
    if is_apple_executive_government_meeting_story(title, text):
        return "company_org"
    if is_direct_apple_regional_platform_regulation_story(title, text):
        return "regional_regulation"
    if is_direct_apple_airpods_firmware_story(title, text):
        return "os_app"
    if is_siri_ai_third_party_app_data_access_feature(title, text):
        return "os_app"
    if is_iphone_physical_dimension_rumor_story(title, text):
        return "hardware_market"
    if is_iphone_component_cost_forecast_story(text):
        return "hardware_market"
    if is_competitor_display_panel_story_using_apple_as_background(title, text):
        return "third_party_ecosystem"
    if (
        is_third_party_ai_agent_for_mac_without_apple_action(title, text)
        or is_third_party_game_or_cross_platform_launch_story(title, text)
        or is_non_apple_device_comparison_story(title, text)
        or is_third_party_consumer_app_update_on_apple_platform(title, text)
        or is_third_party_browser_security_feature_story(title, text)
        or is_third_party_reference_or_explainer_project_story(title, text)
        or is_third_party_custom_unreleased_apple_product_story(title, text)
        or is_third_party_accessory_platform_compatibility_story(title, text)
        or is_non_apple_public_response_with_apple_purchase_context(title, text)
        or is_non_apple_primary_subject_with_former_apple_background(title, text)
        or is_broad_ai_device_market_commentary_with_apple_example(title, text)
        or is_apple_work_column_without_new_apple_action(title, text)
        or is_non_apple_component_market_background_story(title, text)
        or is_non_apple_product_research_context_story(text)
        or is_third_party_device_management_service_story(text)
        or is_multi_vendor_chip_or_phone_roadmap_background_story(title, text)
        or is_non_apple_product_design_reference_story(title, text)
    ):
        return "third_party_ecosystem"
    if is_apple_product_data_leak_story(text, title) and not is_apple_support_security_guidance_story(title, text):
        return "hardware_market"
    if is_apple_wallet_feature_story(text) and score_terms(
        title_lower,
        ["apple wallet", "wallet", "digital id", "digital-id", "钱包", "数字身份证", "数字身份", "身份核验"],
    ) > 0:
        return "wallet_feature"
    if "iphone-mirroring" in topic_facets_from_text(text):
        return "os_app"
    if is_apple_os_support_compatibility_story(text) or (
        score_terms(
            lower,
            ["rosetta", "rosetta 2", "intel app", "intel apps", "intel-built", "intel-compiled", "英特尔架构应用", "intel 架构应用"],
        )
        > 0
        and score_terms(lower, ["macos", "mac", "support", "end", "remove", "淘汰", "提醒", "支持", "无法运行", "未来"]) > 0
    ):
        return "os_compatibility"
    if (
        is_direct_iphone_hardware_spec_rumor_story(title, text)
        or is_apple_display_panel_supply_chain_story(text)
        or is_foldable_iphone_supply_chain_story(text)
    ):
        return "hardware_market"
    if is_apple_os_feature_or_summary_story(text) and is_title_primary_software_system_story(title, text):
        return "os_app"
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
    if is_apple_tv_hardware_story(text):
        return "hardware_market"
    if score_terms(lower, ["apple arcade", "苹果 arcade"]) > 0:
        return "service_content"
    if is_apple_tv_awards_nominations_story(text):
        return "service_content"
    if is_apple_tv_purchase_4k_upgrade_story(text):
        return "service_content"
    if (
        is_apple_tv_mlb_schedule_story(text)
        or is_apple_tv_content_event_lineup_story(text)
        or is_apple_tv_content_trailer_story(text)
    ):
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
    if is_third_party_game_or_cross_platform_launch_story(title, text):
        return "third_party_ecosystem"
    if is_routine_third_party_apple_platform_story(title):
        return "third_party_ecosystem"
    if is_third_party_platform_availability_candidate(title):
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
        score_terms(
            lower,
            [
                "apple store",
                "apple stores",
                "apple retail store",
                "apple retail stores",
                "retail store",
                "retail stores",
                "store closure",
                "store closures",
                "store opening",
                "store openings",
                "opens store",
                "零售店",
                "苹果零售店",
                "苹果直营店",
                "苹果店",
            ],
        )
        > 0
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
    if is_non_actionable_recap_title(title):
        return "weak", "routine recap without a new standalone Apple action"
    if is_rumor_feature_recap_without_new_reporting(title, text):
        return "weak", "rumor feature recap without new standalone reporting"
    if is_third_party_cross_platform_desktop_client_update(title, text):
        return "weak", "third-party cross-platform desktop client update without a direct Apple action"
    if is_ai_generated_apple_product_image_debunk_without_new_action(title, text):
        return "weak", "AI-generated Apple product image debunk without a new Apple action"
    if is_apple_chip_tariff_exemption_story(title, text):
        return "strong", "Apple chip-production commitment tied to a tariff exemption"
    if (
        is_direct_apple_regulated_technology_access_story(title, text)
        and not is_apple_restricted_memory_supplier_approval_story(text)
        and not is_apple_memory_supplier_sourcing_story(text)
    ):
        return "strong", "government action directly changes Apple's access to regulated technology"
    if is_apple_device_battery_regulation_story(text):
        return "strong", "battery regulation directly affects an Apple hardware product"
    if is_personal_os_feature_walkthrough_without_new_action(title, text):
        return "weak", "personal OS feature walkthrough without a new standalone Apple action"
    if is_direct_apple_os_component_change_story(title, text):
        return "strong", "direct Apple OS or built-in component change"
    if is_broad_multi_vendor_market_report(text, title):
        return "weak", "broad multi-vendor market report without Apple-specific shipment or share detail"
    if is_apple_specific_market_share_report_story(text, title):
        return "strong", "Apple-specific hardware shipment or market-share report"
    if is_routine_recap_comparison_or_buying_advice(title, text):
        return "weak", "third-party or routine recap, comparison, hands-on, or buying advice without a new Apple action"
    if is_how_to_guide_without_new_apple_action(title, text):
        return "weak", "how-to or troubleshooting guide without a new Apple action"
    if is_usage_podcast_or_third_party_project_without_new_apple_action(title, text):
        return "weak", "personal usage, podcast, or third-party Apple-device project without a new Apple action"
    if is_non_apple_primary_subject_with_former_apple_background(title, text):
        return "weak", "non-Apple primary subject with former Apple background"
    if is_broad_ai_device_market_commentary_with_apple_example(title, text):
        return "weak", "broad AI device market commentary using Apple mainly as an example"
    if is_apple_work_column_without_new_apple_action(title, text):
        return "weak", "Apple @ Work column or sponsored commentary without a new Apple action"
    if is_official_apple_privacy_ad_campaign_story(text):
        return "strong", "official Apple privacy campaign or advertising action"
    if is_apple_executive_event_attendance_story(title, text):
        return "strong", "Apple executive or leadership event attendance"
    if is_apple_wallet_car_key_partner_support_story(title, text):
        return "strong", "Apple Wallet car key partner support or code-reference event"
    if is_camera_airpods_code_clue_story(text):
        return "strong", "Apple camera-equipped AirPods code clue or product-development event"
    if is_camera_airpods_development_suspension_story(text):
        return "strong", "Apple camera-equipped AirPods development or roadmap event"
    if is_iphone_photography_awards_story(text):
        return "strong", "iPhone photography awards and camera ecosystem event"
    if is_apple_service_card_payment_restore_story(text):
        return "strong", "Apple service payment method restoration or compliance event"
    if is_icloud_service_perk_story(text):
        return "strong", "Apple iCloud service entitlement or subscription perk"
    if is_icloud_home_ai_camera_subscription_story(text):
        return "strong", "Apple Home app AI camera iCloud subscription requirement"
    if is_apple_on_device_ai_model_compression_story(text):
        return "strong", "Apple on-device AI model compression or larger local model event"
    if is_safari_mcp_server_story(text):
        return "strong", "Safari Technology Preview or Safari MCP developer tooling event"
    if is_hide_my_email_vulnerability_story(text):
        return "strong", "Apple Hide My Email privacy vulnerability"
    if is_airdrop_vulnerability_story(text):
        return "strong", "Apple AirDrop security vulnerability or ecosystem impact"
    if is_russia_fas_app_preinstall_regulation_story(text):
        return "strong", "Apple-specific Russia app preinstall or antimonopoly regulation"
    if is_india_tariff_iphone_manufacturing_story(text):
        return "strong", "India tariff exemption affecting Apple iPhone manufacturing"
    if is_apple_memory_supplier_sourcing_story(text):
        return "strong", "Apple-specific memory supplier sourcing event"
    if is_apple_broadcom_chip_supply_deal_story(text, title):
        return "strong", "Apple-specific Broadcom chip supply partnership event"
    if is_non_apple_component_market_background_story(title, text):
        return "weak", "non-Apple component or industry price story using Apple mainly as background"
    if is_broad_multi_vendor_market_report(text, title):
        return "weak", "broad multi-vendor market report without Apple-specific shipment or share detail"
    if is_apple_specific_market_share_report_story(text, title):
        return "strong", "Apple-specific hardware shipment or market-share report"
    if is_apple_product_legal_proceeding_story(title, text) or is_apple_legal_proceeding_story(text):
        return "strong", "Apple-specific lawsuit or legal proceeding"
    if is_apple_executive_government_meeting_story(title, text):
        return "strong", "Apple executive, government, or regional investment meeting"
    if is_direct_apple_regional_platform_regulation_story(title, text):
        return "strong", "Apple-specific regional platform regulation event"
    if is_direct_apple_airpods_firmware_story(title, text):
        return "strong", "Apple AirPods or Beats firmware update"
    if is_siri_ai_third_party_app_data_access_feature(title, text):
        return "strong", "Apple Siri or Apple Intelligence capability change"
    if is_iphone_physical_dimension_rumor_story(title, text):
        return "strong", "Apple iPhone physical design or dimension rumor"
    if is_iphone_component_cost_forecast_story(text):
        return "strong", "Apple iPhone component cost or bill-of-materials forecast"
    if (
        is_apple_chip_process_roadmap_story(text)
        and score_terms(
            title.lower(),
            ["14a", "18a", "18a-p", "intel", "tsmc", "foundry", "英特尔", "台积电", "制程", "工艺", "代工订单", "代工协议", "代工合作"],
        )
        > 0
    ):
        return "strong", "Apple chip process or foundry roadmap event"
    if is_apple_product_data_leak_story(text, title):
        return "strong", "Apple product or supplier data-leak event"
    if is_multi_vendor_chip_or_phone_roadmap_background_story(title, text):
        return "weak", "multi-vendor chip or phone roadmap story using Apple mainly as context"
    if is_non_apple_product_design_reference_story(title, text):
        return "weak", "non-Apple product story using iPhone design or color only as reference context"
    if is_competitor_display_panel_story_using_apple_as_background(title, text):
        return "weak", "competitor display-panel or supply-chain story using Apple mainly as prior-order context"
    if is_direct_iphone_hardware_spec_rumor_story(title, text):
        return "strong", "Apple iPhone hardware specification rumor"
    if is_routine_recap_comparison_or_buying_advice(title, text):
        return "weak", "third-party or routine recap, comparison, hands-on, or buying advice without a new Apple action"
    if is_apple_opinion_without_new_reporting(title, text):
        return "weak", "opinion or commentary without new Apple reporting"
    if is_how_to_guide_without_new_apple_action(title, text):
        return "weak", "how-to or troubleshooting guide without a new Apple action"
    if is_usage_podcast_or_third_party_project_without_new_apple_action(title, text):
        return "weak", "personal usage, podcast, or third-party Apple-device project without a new Apple action"
    if is_third_party_ai_agent_for_mac_without_apple_action(title, text):
        return "weak", "third-party AI agent for Mac without a direct Apple platform action"
    if is_third_party_game_or_cross_platform_launch_story(title, text):
        return "weak", "third-party game, app, or cross-platform launch without a direct Apple action"
    if is_non_apple_device_comparison_story(title, text):
        return "weak", "non-Apple device story using iPhone or Apple mainly as comparison context"
    if is_third_party_consumer_app_update_on_apple_platform(title, text):
        return "weak", "third-party app or consumer service update on Apple platforms without a direct Apple action"
    if is_third_party_browser_security_feature_story(title, text):
        return "weak", "third-party browser security feature with Apple platforms used mainly as compatibility context"
    if is_third_party_reference_or_explainer_project_story(title, text):
        return "weak", "third-party Apple-product reference, visualization, or explainer project without a new Apple action"
    if is_third_party_custom_unreleased_apple_product_story(title, text):
        return "weak", "third-party custom or concept version of an unreleased Apple product without a new Apple action"
    if is_non_apple_product_research_context_story(text):
        return "weak", "non-Apple research using an Apple product mainly as study context"
    if is_third_party_device_management_service_story(text):
        return "weak", "third-party device-management or security service for Apple devices"
    if is_third_party_accessory_platform_compatibility_story(title, text):
        return "weak", "third-party accessory story with Apple platform compatibility used mainly as context"
    if is_non_apple_public_response_with_apple_purchase_context(title, text):
        return "weak", "non-Apple organization response using Apple hardware purchase mainly as context"
    if is_apple_display_panel_supply_chain_story(text) or is_foldable_iphone_supply_chain_story(text):
        return "strong", "Apple hardware supply-chain or display-panel roadmap event"
    if is_final_cut_camera_update_story(text):
        return "strong", "Apple first-party Final Cut Camera app update"
    if is_apple_creator_studio_story(text):
        return "strong", "Apple first-party pro app or Creator Studio update"
    if is_apple_tv_purchase_4k_upgrade_story(text):
        return "strong", "Apple TV app purchased-content upgrade or entitlement event"
    if is_apple_tv_awards_nominations_story(text):
        return "strong", "Apple TV awards or nominations event"
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
    if is_apple_product_commentary_analysis_without_new_reporting(title, text):
        return "weak", "Apple product commentary or analysis without a new Apple action"
    if is_former_apple_figure_commentary_without_new_apple_action(title, text):
        return "weak", "former Apple figure commentary without a new Apple action"
    if is_legacy_apple_platform_third_party_app_story(title, text):
        return "weak", "third-party app or service on a legacy Apple platform without a new Apple action"
    if is_third_party_legacy_apple_hardware_replica_story(title, text):
        return "weak", "third-party project recreating legacy Apple hardware without a new Apple action"
    if is_third_party_app_or_service_status_story(title, text):
        return "weak", "third-party app or service Apple-platform status story without a direct Apple action"
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
    if is_multi_vendor_chip_or_phone_roadmap_background_story(title, text):
        return "weak", "multi-vendor chip or phone roadmap story using Apple mainly as context"
    if is_non_apple_product_design_reference_story(title, text):
        return "weak", "non-Apple product story using iPhone design or color only as reference context"
    if event_kind == "os_app" and is_title_primary_software_system_story(title, text):
        return "strong", "Apple OS, built-in app, or feature-summary change"
    if is_direct_apple_hardware_roadmap_story(text, title):
        return "strong", "Apple hardware roadmap or product-development event"
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
        score_terms(
            title_text,
            [
                "apple store",
                "apple stores",
                "apple retail store",
                "apple retail stores",
                "retail store",
                "retail stores",
                "苹果零售店",
                "苹果直营店",
                "苹果店",
                "零售店",
            ],
        )
        > 0
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
    if (
        is_third_party_platform_availability_candidate(text)
        and (
            kind == "ecosystem_interop"
            or is_third_party_platform_update_improving_apple_device_interop(candidate.title, text)
        )
    ):
        score += 70
    if is_apple_executive_government_meeting_story(candidate.title, text):
        score += 65
    if is_apple_chip_tariff_exemption_story(candidate.title, text):
        score += 55
    if is_direct_apple_regulated_technology_access_story(candidate.title, text):
        score += 55
    if is_direct_apple_regional_platform_regulation_story(candidate.title, text):
        score += 55
    if is_direct_apple_airpods_firmware_story(candidate.title, text):
        score += 45
    if is_safari_mcp_server_story(text):
        score += 70
    if is_russia_fas_app_preinstall_regulation_story(text):
        score += 55
    if is_apple_memory_supplier_sourcing_story(text):
        score += 55
    if is_hide_my_email_vulnerability_story(text):
        score += 45
    if "/guide/" in candidate.url.lower() and is_apple_os_feature_or_summary_story(text):
        score += 35
    if is_direct_apple_os_component_change_story(candidate.title, text):
        score += 35
    if is_apple_developer_tool_story(text):
        score += 30
    if (
        score_terms(candidate.title, ["ios", "ipados", "macos", "watchos", "tvos", "visionos", "系统"]) > 0
        and score_terms(candidate.title, OS_FEATURE_ACTION_TERMS) > 0
    ):
        score += 20
    if kind in {
        "messages_platform",
        "company_org",
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
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if article_facets & event_facets & EXACT_SHARED_EVENT_TOPIC_FACETS:
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
        if article_facets and event_facets and article_facets & event_facets:
            return True
    if "general_company" in {article.event_kind, event.event_kind}:
        return True
    return False


def relevance_tier_compatible(article: Article, event: Event) -> bool:
    if article.relevance_tier == event.relevance_tier:
        return True
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if article_facets & event_facets & EXACT_SHARED_EVENT_TOPIC_FACETS:
        return True
    return "weak" not in {article.relevance_tier, event.relevance_tier}


def regions_compatible(article: Article, event: Event) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-product-price-increase" in common_facets:
        return True
    if common_facets & {"iphone-battery-capacity-leak", "iphone-logic-board-leak"}:
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


def event_title_hardware_product_families(event: Event) -> set[str]:
    groups = hardware_product_families_from_text(event.title)
    for item in event.articles:
        groups |= hardware_product_families_from_text(item.title)
    return groups


def title_hardware_product_families_compatible(article: Article, event: Event) -> bool:
    if article.category != "hardware_products" and event.category != "hardware_products":
        return True
    article_groups = hardware_product_families_from_text(article.title)
    event_groups = event_title_hardware_product_families(event)
    if not article_groups or not event_groups:
        return True
    if article_groups & event_groups:
        return True
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if "apple-product-roadmap-list" in (article_facets | event_facets):
        return True
    return False


def event_title_hardware_product_families_compatible(left: Event, right: Event) -> bool:
    if left.category != "hardware_products" and right.category != "hardware_products":
        return True
    left_groups = event_title_hardware_product_families(left)
    right_groups = event_title_hardware_product_families(right)
    if not left_groups or not right_groups:
        return True
    if left_groups & right_groups:
        return True
    left_facets = effective_topic_facets(event_primary_facets(left))
    right_facets = effective_topic_facets(event_primary_facets(right))
    if "apple-product-roadmap-list" in (left_facets | right_facets):
        return True
    return False


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
    if not title_hardware_product_families_compatible(article, event):
        return False
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
    if ("apple-market-share-report" in article_facets) != ("apple-market-share-report" in event_facets):
        return False
    if article_facets & event_facets & EXACT_SHARED_EVENT_TOPIC_FACETS:
        return True
    title_scoped_roadmap_shared = (
        title_scoped_hardware_product_roadmap_facets(article.title)
        & event_title_scoped_hardware_product_roadmap_facets(event)
    )
    if title_scoped_roadmap_shared and article.event_kind == event.event_kind == "hardware_market":
        return True
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
        if not topic_match and foldable_panel_supply_facets_compatible(article_facets, event_facets):
            topic_match = True
    if not topic_match:
        return False
    shared_topic_facets = article_facets & event_facets
    if shared_topic_facets and shared_topic_facets <= LOW_CONFIDENCE_MERGE_FACETS:
        article_specific_facets = non_platform_topic_facets(article_facets) - LOW_CONFIDENCE_MERGE_FACETS
        event_specific_facets = non_platform_topic_facets(event_facets) - LOW_CONFIDENCE_MERGE_FACETS
        if article_specific_facets and event_specific_facets:
            return False
    release_or_platform_facets = (
        os_release_version_facets(shared_topic_facets)
        | os_release_channel_facets(shared_topic_facets)
        | merge_guard_platform_facets(shared_topic_facets)
        | {"platform-mobile-os"}
    )
    if shared_topic_facets and shared_topic_facets <= release_or_platform_facets:
        return same_os_release_event(article, event)
    platform_scoped_os_facets = {"system-wallpaper", "ai-wallpaper", "built-in-app-change"}
    if (
        article_facets & event_facets & platform_scoped_os_facets
        and not platform_facets_compatible(
            article_facets | article_merge_guard_facets(article),
            event_facets | event_merge_guard_facets(event),
        )
    ):
        return False
    if (
        platform_only_shared_topic_facets(article_facets, event_facets)
        and non_platform_topic_facets(article_facets)
        and non_platform_topic_facets(event_facets)
    ):
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
    summary_indicates_weak_context = (
        is_third_party_ai_agent_for_mac_without_apple_action(event.title, summary_context)
        or is_third_party_game_or_cross_platform_launch_story(event.title, summary_context)
        or is_non_apple_device_comparison_story(event.title, summary_context)
        or is_third_party_consumer_app_update_on_apple_platform(event.title, summary_context)
        or is_third_party_browser_security_feature_story(event.title, summary_context)
        or is_third_party_reference_or_explainer_project_story(event.title, summary_context)
        or is_third_party_custom_unreleased_apple_product_story(event.title, summary_context)
        or is_non_apple_product_design_reference_story(event.title, summary_context)
        or is_non_apple_product_research_context_story(summary_context)
        or is_third_party_device_management_service_story(summary_context)
        or is_third_party_app_platform_launch_story(event.title, summary_context)
        or is_non_apple_public_response_with_apple_purchase_context(event.title, summary_context)
        or is_former_apple_figure_commentary_without_new_apple_action(event.title, summary_context)
        or is_usage_podcast_or_third_party_project_without_new_apple_action(event.title, summary_context)
        or is_non_apple_component_market_background_story(event.title, summary_context)
    )
    article_group_indicates_weak_context = bool(event.articles) and all(
        (
            is_third_party_ai_agent_for_mac_without_apple_action(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_third_party_game_or_cross_platform_launch_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_non_apple_device_comparison_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_third_party_consumer_app_update_on_apple_platform(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_third_party_browser_security_feature_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_third_party_reference_or_explainer_project_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_third_party_custom_unreleased_apple_product_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_non_apple_product_design_reference_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_non_apple_product_research_context_story(
                " ".join([article.summary, *article.key_facts[:5]])
            )
            or is_third_party_device_management_service_story(
                " ".join([article.summary, *article.key_facts[:5]])
            )
            or is_third_party_app_platform_launch_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_non_apple_public_response_with_apple_purchase_context(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_former_apple_figure_commentary_without_new_apple_action(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_usage_podcast_or_third_party_project_without_new_apple_action(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
            or is_non_apple_component_market_background_story(
                article.title,
                " ".join([article.summary, *article.key_facts[:5]]),
            )
        )
        for article in event.articles
    )
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
            or is_third_party_custom_unreleased_apple_product_story(event.title, summary_context)
            or is_non_apple_product_design_reference_story(event.title, summary_context)
            or is_third_party_app_platform_launch_story(event.title, summary_context)
            or is_third_party_game_or_cross_platform_launch_story(event.title, summary_context)
            or is_non_apple_public_response_with_apple_purchase_context(event.title, summary_context)
            or is_former_apple_figure_commentary_without_new_apple_action(event.title, summary_context)
            or is_non_apple_component_market_background_story(event.title, summary_context)
            or is_usage_podcast_or_third_party_project_without_new_apple_action(event.title, summary_context)
        )
    )
    if (
        priority.get(article_tier, 0) > priority.get(summary_tier, 0)
        and not summary_allows_downgrade
        and not (summary_tier == "weak" and summary_indicates_weak_context)
        and not (summary_tier == "weak" and article_group_indicates_weak_context)
    ):
        event.event_kind = article_kind
        event.relevance_tier = article_tier
        event.relevance_reason = article_reason
        event.category = article_category
        return
    if (
        article_tier == "weak"
        and priority.get(summary_tier, 0) > priority.get(article_tier, 0)
        and summary_indicates_weak_context
    ):
        event.event_kind = article_kind
        event.relevance_tier = article_tier
        event.relevance_reason = article_reason
        event.category = article_category
        return
    if (
        article_kind in HARDWARE_EVENT_KINDS
        and summary_tier == "strong"
        and is_apple_product_data_leak_story(" ".join([event.title, event.summary, *event.key_facts[:8]]), event.title)
    ):
        event.event_kind = article_kind
        event.relevance_tier = summary_tier
        event.relevance_reason = summary_reason
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
        all_foldable_panel_market_reports = all(
            is_foldable_iphone_panel_market_report_context(" ".join([item.title, item.summary, *item.key_facts[:4]]))
            for item in articles
        )
        if not common_facets and not all_foldable_panel_market_reports:
            warnings.append("mixed primary topic facets")
    return warnings


def same_beats_hardware_sighting(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "beats-official-cables" in common_facets:
        return bool(shared & {"beats", "cable", "cables", "charging", "power-pink", "充电线"})
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


def same_apple_broadcom_chip_supply_deal_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-broadcom-chip-supply-deal" not in common_facets:
        return False
    anchors = {
        "apple",
        "broadcom",
        "2031",
        "chip",
        "chips",
        "custom",
        "supply",
        "agreement",
        "partnership",
        "deal",
        "radio",
        "wireless",
        "wi-fi",
        "wifi",
        "bluetooth",
        "苹果",
        "博通",
        "芯片",
        "定制",
        "供应",
        "协议",
        "合作",
        "射频",
        "无线",
    }
    if len(shared & anchors) >= 2:
        return True
    return True


def same_airdrop_vulnerability_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "airdrop-vulnerability" not in common_facets:
        return False
    return bool(shared & {"airdrop", "vulnerability", "vulnerabilities", "漏洞", "隔空投送"})


def same_hide_my_email_vulnerability_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "hide-my-email-vulnerability" not in common_facets:
        return False
    return bool(shared & {"hide-my-email", "icloud+", "email", "privacy", "vulnerability", "bug", "flaw", "漏洞", "邮箱", "隐私"})


def same_safari_mcp_server_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "safari-mcp-server" not in common_facets:
        return False
    return bool(shared & {"safari", "mcp", "server", "webkit", "technology-preview", "debug", "agent", "智能体", "调试"})


def same_airpods_firmware_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "airpods-firmware-update" not in common_facets and "airpods-firmware" not in common_facets:
        return False
    anchors = {
        "airpods",
        "airpods-pro",
        "airpods-max",
        "firmware",
        "beta",
        "9a5314b",
        "ios",
        "27",
        "gymkit",
        "固件",
        "开发",
        "测试",
        "推送",
    }
    return len(shared & anchors) >= 2


def same_hardware_company_context_event(article: Article, event: Event, shared: set[str]) -> bool:
    kinds = {article.event_kind, event.event_kind}
    if "company_org" not in kinds:
        return False
    if not (kinds <= {"company_org", "hardware_market", "general_company", "os_app"}):
        return False
    if article.category != "hardware_products" and event.category != "hardware_products":
        return False
    article_groups = hardware_product_families_from_text(article.title)
    event_groups = event_title_hardware_product_families(event)
    if not article_groups or not event_groups or not (article_groups & event_groups):
        return False
    if not merge_guard_facets_compatible(article_merge_guard_facets(article), event_merge_guard_facets(event)):
        return False
    strong_shared = strong_shared_merge_tokens(shared)
    product_anchors = {
        "iphone",
        "ipad",
        "macbook",
        "mac-mini",
        "mac-studio",
        "imac",
        "apple-watch",
        "airpods",
        "vision-pro",
        "apple-tv",
        "smart-ring",
        "mini",
        "studio",
    }
    generic_context_anchors = {
        "ai",
        "agent",
        "agents",
        "chip",
        "chips",
        "developer",
        "developers",
        "demand",
        "future",
        "product",
        "hardware",
        "software",
        "system",
        "苹果",
        "苹果公司",
        "芯片",
        "智能体",
    }
    entity_anchors = strong_shared - product_anchors - generic_context_anchors
    return bool(strong_shared & product_anchors) and len(strong_shared) >= 4 and bool(entity_anchors)


def same_apple_service_card_payment_restore_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "app-store-card-payments" not in common_facets:
        return False
    payment_anchors = {
        "app",
        "app-store",
        "icloud",
        "card",
        "cards",
        "credit",
        "debit",
        "payment",
        "payments",
        "bank",
        "banks",
        "india",
        "rbi",
        "tokenisation",
        "tokenization",
        "银行卡",
        "信用卡",
        "借记卡",
        "支付",
        "恢复",
        "印度",
    }
    return len(shared & payment_anchors) >= 3


def same_apple_market_share_report_event(article: Article, event: Event, shared: set[str]) -> bool:
    article_context = article_merge_context(article)
    event_context = event_merge_context(event)
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-market-share-report" not in common_facets and not (
        is_apple_specific_market_share_report_story(article_context, article.title)
        and is_apple_specific_market_share_report_story(event_context, event.title)
    ):
        return False
    article_products = hardware_product_families_from_text(article_context)
    event_products = event_title_hardware_product_families(event) or hardware_product_families_from_text(event_context)
    if article_products and event_products and not (article_products & event_products):
        return False
    market_anchors = {
        "counterpoint",
        "canalys",
        "idc",
        "omdia",
        "shipments",
        "shipment",
        "share",
        "market",
        "report",
        "research",
        "growth",
        "grew",
        "70",
        "90",
        "25",
        "2026",
        "q1",
        "出货",
        "出货量",
        "份额",
        "市场",
        "报告",
        "增长",
        "同比",
    }
    numeric_shared = {token for token in shared if re.fullmatch(r"\d+(?:\.\d+)?", token)}
    product_anchors = {
        "apple-watch",
        "watch",
        "smartwatch",
        "smartwatches",
        "edge",
        "ai",
        "iphone",
        "ipad",
        "mac",
        "pc",
        "手表",
        "智能手表",
        "端侧",
        "苹果",
    }
    return (len(shared & market_anchors) >= 3 and bool(shared & product_anchors)) or len(numeric_shared) >= 2


def same_russia_fas_app_preinstall_regulation_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "russia-fas-app-preinstall-regulation" not in common_facets:
        return False
    return bool(shared & {"russia", "russian", "fas", "fine", "antimonopoly", "preinstall", "local", "apps", "俄罗斯", "反垄断", "罚款", "预装"})


def is_foldable_iphone_panel_market_report_context(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone fold", "foldable iphone", "folding iphone", "iphone ultra", "折叠屏 iphone", "折叠 iphone", "折叠手机", "折叠屏手机"]) <= 0:
        return False
    if score_terms(lower, ["panel", "panels", "display", "screen", "面板", "屏幕", "显示订单"]) <= 0:
        return False
    return score_terms(lower, ["counterpoint", "research", "shipment", "shipments", "orders", "market share", "份额", "出货", "采购份额", "订单"]) > 0


def is_foldable_iphone_production_target_context(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone fold", "foldable iphone", "folding iphone", "iphone ultra", "折叠屏 iphone", "折叠 iphone", "折叠手机", "折叠屏手机"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "production target",
            "build target",
            "manufacture",
            "manufacturing",
            "sell around",
            "models",
            "units",
            "million",
            "nikkei",
            "price",
            "生产目标",
            "生产",
            "量产",
            "万台",
            "万部",
            "售价",
            "日经",
        ],
    ) > 0


def is_foldable_iphone_launch_timing_context(text: str) -> bool:
    lower = text.lower()
    if score_terms(lower, ["iphone fold", "foldable iphone", "folding iphone", "iphone ultra", "折叠屏 iphone", "折叠 iphone", "折叠机", "折叠屏手机"]) <= 0:
        return False
    return score_terms(
        lower,
        [
            "launch",
            "release",
            "preorder",
            "preorders",
            "delayed",
            "delay",
            "after iphone",
            "fourth quarter",
            "q4",
            "september",
            "normal delivery",
            "发售",
            "发布",
            "预购",
            "延期",
            "推迟",
            "第四季度",
            "9 月",
            "九月",
            "正常交付",
            "交付",
        ],
    ) > 0


def is_foldable_iphone_launch_timing_story(title: str, text: str) -> bool:
    title_lower = title.lower()
    if is_non_apple_primary_subject_with_incidental_apple_context(title, text):
        return False
    return is_foldable_iphone_launch_timing_context(title_lower)


def is_apple_stock_target_analyst_story(title: str, text: str) -> bool:
    lower = f"{title} {text}".lower()
    if score_terms(lower, ["apple", "aapl", "苹果"]) <= 0:
        return False
    if score_terms(lower, ["j.p. morgan", "jp morgan", "jpmorgan", "摩根大通"]) <= 0:
        return False
    if score_terms(lower, ["stock target", "price target", "target to", "target from", "raises", "bumps", "上调", "目标价"]) <= 0:
        return False
    return score_terms(lower, ["345", "$345", "stock", "shares", "aapl", "股价", "股票"]) > 0


def foldable_iphone_panel_and_production_contexts_compatible(article: Article, event: Event) -> bool:
    article_context = " ".join([article.title, article.summary, *article.key_facts[:4]])
    event_contexts = [" ".join([item.title, item.summary, *item.key_facts[:4]]) for item in event.articles]
    article_panel = is_foldable_iphone_panel_market_report_context(article_context)
    article_production = is_foldable_iphone_production_target_context(article_context)
    event_panel = any(is_foldable_iphone_panel_market_report_context(context) for context in event_contexts)
    event_production = any(is_foldable_iphone_production_target_context(context) for context in event_contexts)
    if article_panel and not article_production and event_production and not event_panel:
        return False
    if article_production and not article_panel and event_panel and not event_production:
        return False
    if (
        article_panel != event_panel
        and (article_panel or event_panel)
        and (article_production or event_production)
        and article_panel != article_production
    ):
        return False
    return True


def event_has_foldable_iphone_panel_market_report(event: Event) -> bool:
    return any(
        is_foldable_iphone_panel_market_report_context(" ".join([item.title, item.summary, *item.key_facts[:4]]))
        for item in event.articles
    )


def event_has_foldable_iphone_production_target(event: Event) -> bool:
    return any(
        is_foldable_iphone_production_target_context(" ".join([item.title, item.summary, *item.key_facts[:4]]))
        for item in event.articles
    )


def foldable_iphone_panel_and_production_events_compatible(left: Event, right: Event) -> bool:
    left_panel = event_has_foldable_iphone_panel_market_report(left)
    left_production = event_has_foldable_iphone_production_target(left)
    right_panel = event_has_foldable_iphone_panel_market_report(right)
    right_production = event_has_foldable_iphone_production_target(right)
    if left_panel and not left_production and right_production and not right_panel:
        return False
    if left_production and not left_panel and right_panel and not right_production:
        return False
    if (
        (left_panel or right_panel)
        and (left_production or right_production)
        and left_panel != right_panel
        and left_panel != left_production
        and right_panel != right_production
    ):
        return False
    return True


def same_foldable_iphone_panel_market_report(article: Article, event: Event, shared: set[str]) -> bool:
    article_context = " ".join([article.title, article.summary, *article.key_facts[:4]])
    if not is_foldable_iphone_panel_market_report_context(article_context):
        return False
    if not any(
        is_foldable_iphone_panel_market_report_context(" ".join([item.title, item.summary, *item.key_facts[:4]]))
        for item in event.articles
    ):
        return False
    if foldable_panel_supply_facets_compatible(article_primary_facets(article), event_primary_facets(event)):
        return True
    return bool(shared & {"counterpoint", "research", "29", "24", "shipments", "orders", "份额", "出货", "订单"})


def same_foldable_iphone_launch_timing_event(article: Article, event: Event, shared: set[str]) -> bool:
    article_context = article_merge_context(article).lower()
    event_context = event_merge_context(event).lower()
    if not is_foldable_iphone_launch_timing_story(article.title, article_context):
        return False
    if not any(is_foldable_iphone_launch_timing_story(item.title, article_merge_context(item)) for item in event.articles):
        return False
    timing_anchors = {
        "launch",
        "release",
        "preorder",
        "preorders",
        "delayed",
        "delay",
        "september",
        "q4",
        "发售",
        "发布",
        "预购",
        "延期",
        "推迟",
        "交付",
        "9",
        "月",
    }
    return bool(shared & timing_anchors) or (
        score_terms(article_context, ["september", "9 月", "九月", "fourth quarter", "q4", "第四季度", "延期", "正常交付"]) > 0
        and score_terms(event_context, ["september", "9 月", "九月", "fourth quarter", "q4", "第四季度", "延期", "正常交付"]) > 0
    )


def same_apple_stock_target_analyst_event(article: Article, event: Event, shared: set[str]) -> bool:
    article_context = article_merge_context(article).lower()
    event_context = event_merge_context(event).lower()
    if not is_apple_stock_target_analyst_story(article.title, article_context):
        return False
    if not is_apple_stock_target_analyst_story(event.title, event_context):
        return False
    return bool(shared & {"morgan", "jpmorgan", "aapl", "stock", "target", "345", "price", "目标价", "股价"})


def same_iphone_photography_awards_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "iphone-photography-awards" not in common_facets:
        return False
    return bool(shared & {"photography", "awards", "award", "ippa", "winner", "winners", "winning", "images", "shots"})


def same_camera_airpods_code_clue_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "camera-airpods-code-clue" not in common_facets:
        return False
    return True


def same_camera_airpods_development_suspension_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "camera-airpods-development-suspension" not in common_facets:
        return False
    return True


def same_apple_legal_proceeding_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-legal-proceeding" not in common_facets:
        return False
    if "airpods-max-condensation-lawsuit" in common_facets:
        return True
    party_anchors = {
        "prosser",
        "ramacciotti",
        "lipnik",
        "epic",
        "masimo",
        "musk",
        "openai",
        "doj",
        "cma",
        "cci",
        "fas",
    }
    if shared & party_anchors:
        return True
    legal_anchors = {
        "lawsuit",
        "court",
        "filing",
        "trade-secret",
        "trade-secrets",
        "jury",
        "complaint",
        "judge",
        "dismissed",
        "claims",
        "诉讼",
        "法院",
        "起诉",
        "驳回",
        "索赔",
        "商业秘密",
    }
    return len(shared & legal_anchors) >= 2


def same_apple_chip_tariff_exemption_event(article: Article, event: Event) -> bool:
    article_context = article_merge_context(article)
    event_context = event_merge_context(event)
    if not is_apple_chip_tariff_exemption_story(article.title, article_context):
        return False
    if not is_apple_chip_tariff_exemption_story(event.title, event_context):
        return False
    return bool(chip_foundry_entities(article_context) & chip_foundry_entities(event_context))


def same_ios_signing_status_event(article: Article, event: Event, shared: set[str]) -> bool:
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if "ios-signing-status" not in (article_facets & event_facets):
        return False
    article_versions = os_release_version_facets(article_facets)
    event_versions = os_release_version_facets(event_facets)
    if article_versions and event_versions and not (article_versions & event_versions):
        return False
    if not (article_versions & event_versions):
        shared_versions = {token for token in shared if re.match(r"^\d{1,2}(?:\.\d){0,2}$", token)}
        if not shared_versions and not (shared & {"26", "27"}):
            return False
    return bool(shared & {"ios", "iphone", "signing", "downgrade", "签名", "签署", "降级", "回退"})


def same_os_point_release_internal_testing_event(article: Article, event: Event, shared: set[str]) -> bool:
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if "os-internal-testing" not in (article_facets & event_facets):
        return False
    if not (os_release_version_facets(article_facets) & os_release_version_facets(event_facets)):
        return False
    platform_tokens = {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    if not (shared & platform_tokens):
        return False
    return True


def conflicting_os_point_release_internal_testing_platforms(article: Article, event: Event, shared: set[str]) -> bool:
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if "os-internal-testing" not in (article_facets & event_facets):
        return False
    if not (os_release_version_facets(article_facets) & os_release_version_facets(event_facets)):
        return False
    platform_tokens = {"ios", "ipados", "macos", "watchos", "tvos", "visionos"}
    return not bool(shared & platform_tokens)


def same_apple_watch_band_sensor_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-watch-band-sensor-rumor" not in common_facets:
        return False
    return bool(shared & {"apple-watch", "watch", "series", "12", "sensor", "band", "sensors", "传感器", "表带", "血糖"})


def same_apple_product_data_leak_event(article: Article, event: Event, shared: set[str]) -> bool:
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if "apple-product-data-leak" not in (article_facets & event_facets):
        return False
    enforcement_spec_pair = {"apple-product-data-leak-enforcement", "apple-product-data-leak-specs"}
    if (article_facets & enforcement_spec_pair) and (event_facets & enforcement_spec_pair):
        if not (article_facets & event_facets & enforcement_spec_pair):
            return False
    article_text = " ".join([article.title, article.summary, *article.key_facts[:5]])
    event_text = " ".join([event.title, event.summary, *event.key_facts[:8]])
    anchor_groups = [
        ["tata", "塔塔"],
        ["world leaks", "world-leaks"],
        ["dark web", "dark-web", "暗网"],
        ["data breach", "data-leak", "数据泄露", "信息泄露"],
        ["630gb", "630 gb", "630GB"],
        ["cert-in", "computer emergency response", "计算机应急响应小组", "应急响应小组"],
        ["india", "indian", "印度"],
    ]
    matched_anchors = 0
    for terms in anchor_groups:
        if score_terms(article_text.lower(), terms) > 0 and score_terms(event_text.lower(), terms) > 0:
            matched_anchors += 1
    shared_anchor_tokens = shared & {
        "tata",
        "world-leaks",
        "dark-web",
        "data-leak",
        "stolen",
        "confidential",
        "investigation",
        "cert-in",
        "india",
        "630gb",
    }
    return matched_anchors >= 2 or len(shared_anchor_tokens) >= 2


def same_apple_memory_supplier_sourcing_event(article: Article, event: Event, shared: set[str]) -> bool:
    supplier_facets = {"apple-memory-supplier-sourcing", "apple-restricted-memory-supplier-approval"}
    article_facets = effective_topic_facets(article_primary_facets(article))
    event_facets = effective_topic_facets(event_primary_facets(event))
    if not (article_facets & supplier_facets and event_facets & supplier_facets):
        return False
    if not restricted_memory_supplier_approval_facets_compatible(article_facets, event_facets):
        return False
    return bool(shared & {"cxmt", "ymtc", "changxin", "yangtze", "memory", "ram", "storage", "supplier", "suppliers", "长鑫", "长江存储", "存储", "内存"})


def same_apple_m6_chip_roadmap_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-m6-chip-roadmap" not in common_facets:
        return False
    article_text = article_merge_context(article).lower()
    event_text = event_merge_context(event).lower()
    anchor_terms = [
        "m6 pro",
        "m6 max",
        "m7",
        "base m6",
        "standard m6",
        "skip",
        "skips",
        "mac mini",
        "imac",
        "mac studio",
        "macbook air",
        "ipad pro",
        "200gb/s",
        "200 gb/s",
        "标准版",
        "基础版",
        "单薄",
        "跳过",
        "产品线",
    ]
    return score_terms(article_text, anchor_terms) > 0 and score_terms(event_text, anchor_terms) > 0


def same_iphone_logic_board_leak_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "iphone-logic-board-leak" not in common_facets:
        return False
    return bool(
        shared
        & {
            "iphone",
            "18",
            "pro",
            "a20",
            "lpddr6",
            "wmcm",
            "qualcomm",
            "baseband",
            "modem",
            "主板",
            "逻辑板",
            "高通",
            "基带",
        }
    )


def same_iphone_physical_dimension_rumor_event(article: Article, event: Event, shared: set[str]) -> bool:
    article_text = article_merge_context(article).lower()
    event_text = event_merge_context(event).lower()
    if not is_iphone_physical_dimension_rumor_story(article.title, article_text):
        return False
    if not any(is_iphone_physical_dimension_rumor_story(item.title, article_merge_context(item)) for item in event.articles):
        return False
    shared_products = iphone_physical_dimension_product_families(article_text) & iphone_physical_dimension_product_families(event_text)
    if not shared_products:
        return False
    dimension_anchors = {
        "thicker",
        "thickness",
        "heavier",
        "heaviest",
        "weight",
        "grams",
        "240",
        "camera",
        "bump",
        "plateau",
        "housing",
        "backplate",
        "aluminum",
        "2mm",
        "2",
        "9",
        "10",
        "millimeters",
        "fixed",
        "focus",
        "weibo",
        "增厚",
        "厚度",
        "变厚",
        "更重",
        "重量",
        "240g",
        "克",
        "机身",
        "后摄",
        "摄像头",
        "相机",
        "铝合金",
        "定焦数码",
    }
    if shared & dimension_anchors:
        return True
    return score_terms(article_text, ["2mm", "2 mm", "9.9", "10.9", "240 grams", "240g", "heavier", "weight", "增厚", "厚度", "重量"]) > 0 and score_terms(
        event_text,
        ["2mm", "2 mm", "9.9", "10.9", "240 grams", "240g", "heavier", "weight", "增厚", "厚度", "重量"],
    ) > 0


def same_iphone_battery_capacity_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "iphone-battery-capacity-leak" not in common_facets:
        return False
    article_text = article_merge_context(article).lower()
    event_text = event_merge_context(event).lower()
    battery_terms = ["battery", "capacity", "mah", "电池", "容量", "毫安时"]
    if score_terms(article_text, battery_terms) <= 0 or score_terms(event_text, battery_terms) <= 0:
        return False
    if not (iphone_product_identity_anchors(article_text) & iphone_product_identity_anchors(event_text)):
        return False
    article_capacities = iphone_battery_capacity_signatures(article_text)
    event_capacities = iphone_battery_capacity_signatures(event_text)
    return bool(article_capacities & event_capacities)


def same_apple_device_battery_regulation_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "apple-device-battery-regulation" not in common_facets:
        return False
    article_text = article_merge_context(article).lower()
    event_text = event_merge_context(event).lower()
    article_products = hardware_product_families_from_text(article_text)
    event_products = hardware_product_families_from_text(event_text)
    if article_products and event_products and not (article_products & event_products):
        return False
    if not regions_compatible(article, event):
        return False
    article_years = set(re.findall(r"(?<!\d)20\d{2}(?!\d)", article_text))
    event_years = set(re.findall(r"(?<!\d)20\d{2}(?!\d)", event_text))
    if article_years and event_years and not (article_years & event_years):
        return False
    eu_terms = ["european union", "eu", "europe", "欧盟", "欧洲"]
    return score_terms(article_text, eu_terms) > 0 and score_terms(event_text, eu_terms) > 0


def iphone_product_identity_anchors(text: str) -> set[str]:
    lower = text.lower()
    anchors = {
        f"iphone-{match.group(1)}"
        for match in re.finditer(r"(?<![a-z0-9])iphone\s*(\d{1,2})(?!\d)", lower)
    }
    if score_terms(
        lower,
        [
            "foldable iphone",
            "folding iphone",
            "iphone fold",
            "iphone ultra",
            "折叠屏 iphone",
            "折叠 iphone",
            "折叠屏iphone",
            "折叠iphone",
            "首款折叠屏",
            "首款折叠手机",
        ],
    ) > 0:
        anchors.add("foldable-iphone")
    return anchors


def iphone_battery_capacity_signatures(text: str) -> set[str]:
    normalized = text.lower().replace(",", "")
    return {
        match.group(1)
        for match in re.finditer(r"(?<!\d)(\d{3,5})\s*(?:mah|毫安时)(?![a-z])", normalized)
    }


def same_foldable_iphone_render_leak_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "foldable-iphone-render-leak" not in common_facets:
        return False
    article_text = article_merge_context(article).lower()
    event_text = event_merge_context(event).lower()
    if "foldable-iphone" not in iphone_product_identity_anchors(article_text):
        return False
    if "foldable-iphone" not in iphone_product_identity_anchors(event_text):
        return False
    artifact_terms = ["mockup", "dummy", "prototype", "机模", "样机", "模型"]
    if score_terms(article_text, artifact_terms) <= 0 or score_terms(event_text, artifact_terms) <= 0:
        return False
    color_groups = [
        ["white", "白色"],
        ["black", "黑色"],
        ["silver", "银色"],
        ["gold", "金色"],
        ["blue", "蓝色"],
    ]
    return any(score_terms(article_text, terms) > 0 and score_terms(event_text, terms) > 0 for terms in color_groups)


def iphone_production_metric_signatures(text: str) -> set[str]:
    lower = text.lower()
    signatures = {
        match.group(1)
        for match in re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", lower)
    }
    fraction_groups = {
        "one-third": ["one-third", "one third", "a third", "1/3", "三分之一"],
        "one-quarter": ["one-quarter", "one quarter", "a quarter", "1/4", "四分之一"],
        "one-half": ["one-half", "one half", "a half", "1/2", "二分之一", "一半"],
    }
    for signature, terms in fraction_groups.items():
        if score_terms(lower, terms) > 0:
            signatures.add(signature)
    return signatures


def same_iphone_production_forecast_event(article: Article, event: Event, shared: set[str]) -> bool:
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if "iphone-production-forecast" not in common_facets:
        return False
    article_text = article_merge_context(article).lower()
    event_text = event_merge_context(event).lower()
    if not (iphone_product_identity_anchors(article_text) & iphone_product_identity_anchors(event_text)):
        return False
    production_actions = [
        "cut production",
        "production cut",
        "reduce production",
        "reduced production",
        "capacity reduction",
        "demand forecast",
        "slash",
        "slashes",
        "减产",
        "削减产能",
        "暂停产能",
        "下调需求",
        "下调产量",
    ]
    if score_terms(article_text, production_actions) <= 0 or score_terms(event_text, production_actions) <= 0:
        return False
    return bool(iphone_production_metric_signatures(article_text) & iphone_production_metric_signatures(event_text))


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


def service_content_facets_for_merge(facets: set[str]) -> set[str]:
    service_facets = effective_topic_facets(facets) & SERVICE_CONTENT_TOPIC_FACETS
    detail_facets = service_facets & SERVICE_CONTENT_DETAIL_TOPIC_FACETS
    return detail_facets or service_facets


def article_service_topic_facets(article: Article) -> set[str]:
    return service_content_facets_for_merge(article_primary_facets(article))


def event_service_topic_facets(event: Event) -> set[str]:
    return service_content_facets_for_merge(event_primary_facets(event))


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
    if same_apple_market_share_report_event(article, event, shared):
        return True
    if article_health_research != event_health_research:
        common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
        if not (common_facets & {"apple-watch-band-sensor-rumor", "airpods-firmware-update", "airpods-firmware"}):
            return False
    if article_health_research and event_health_research:
        if (HEALTH_RESEARCH_DATA_TOKENS & shared) and (HEALTH_RESEARCH_CONTEXT_TOKENS & shared):
            return True
    if same_hardware_company_context_event(article, event, shared):
        return True
    if same_apple_chip_tariff_exemption_event(article, event):
        return True
    if not event_kind_compatible(article, event):
        return False
    if not relevance_tier_compatible(article, event):
        return False
    if same_iphone_physical_dimension_rumor_event(article, event, shared):
        return True
    if same_foldable_iphone_render_leak_event(article, event, shared):
        return True
    if same_iphone_production_forecast_event(article, event, shared):
        return True
    if same_foldable_iphone_launch_timing_event(article, event, shared):
        return True
    if same_apple_stock_target_analyst_event(article, event, shared):
        return True
    if same_apple_memory_supplier_sourcing_event(article, event, shared):
        return True
    if not regions_compatible(article, event):
        return False
    if same_apple_device_battery_regulation_event(article, event, shared):
        return True
    if not foldable_iphone_panel_and_production_contexts_compatible(article, event):
        return False
    if conflicting_os_point_release_internal_testing_platforms(article, event, shared):
        return False
    if same_apple_product_data_leak_event(article, event, shared):
        return True
    if same_apple_m6_chip_roadmap_event(article, event, shared):
        return True
    if same_iphone_logic_board_leak_event(article, event, shared):
        return True
    if same_iphone_battery_capacity_event(article, event, shared):
        return True
    if same_os_point_release_internal_testing_event(article, event, shared):
        return True
    if same_apple_service_card_payment_restore_event(article, event, shared):
        return True
    if same_apple_market_share_report_event(article, event, shared):
        return True
    if same_apple_broadcom_chip_supply_deal_event(article, event, shared):
        return True
    if same_ios_signing_status_event(article, event, shared):
        return True
    if same_airpods_firmware_event(article, event, shared):
        return True
    if same_os_release_event(article, event):
        return True
    if same_apple_legal_proceeding_event(article, event, shared):
        return True
    if not topic_facets_compatible(article, event, shared, similarity):
        return False
    common_facets = effective_topic_facets(article_primary_facets(article)) & effective_topic_facets(event_primary_facets(event))
    if common_facets & EXACT_SHARED_EVENT_TOPIC_FACETS:
        return True
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
    if same_hide_my_email_vulnerability_event(article, event, shared):
        return True
    if same_safari_mcp_server_event(article, event, shared):
        return True
    if same_russia_fas_app_preinstall_regulation_event(article, event, shared):
        return True
    if same_foldable_iphone_panel_market_report(article, event, shared):
        return True
    if same_iphone_photography_awards_event(article, event, shared):
        return True
    if same_camera_airpods_code_clue_event(article, event, shared):
        return True
    if same_camera_airpods_development_suspension_event(article, event, shared):
        return True
    if same_apple_watch_band_sensor_event(article, event, shared):
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
    if "final-cut-camera-update" in facets:
        keys.add(("final-cut-camera-update", ()))
    for facet in sorted(facets & IPHONE_HARDWARE_RUMOR_TOPIC_FACETS):
        keys.add((facet, ()))
    title_scoped_roadmap_facets = event_title_scoped_hardware_product_roadmap_facets(event)
    if "ipad-product-roadmap" in facets and "ipad-product-roadmap" in title_scoped_roadmap_facets:
        anchors = summary_article.tokens & {"ipad", "ipad-pro", "m6", "m7", "spring", "2027", "新款", "春季", "芯片"}
        if len(anchors) >= 2:
            keys.add(("ipad-product-roadmap", ()))
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


def events_same_iphone_physical_dimension_rumor(left: Event, right: Event) -> bool:
    left_context = event_merge_context(left).lower()
    right_context = event_merge_context(right).lower()
    if not is_iphone_physical_dimension_rumor_story(left.title, left_context):
        return False
    if not is_iphone_physical_dimension_rumor_story(right.title, right_context):
        return False
    shared_products = iphone_physical_dimension_product_families(left_context) & iphone_physical_dimension_product_families(right_context)
    if not shared_products:
        return False
    left_tokens = set().union(*(article.tokens for article in left.articles))
    right_tokens = set().union(*(article.tokens for article in right.articles))
    shared = left_tokens & right_tokens
    dimension_anchors = {
        "thicker",
        "thickness",
        "camera",
        "bump",
        "plateau",
        "housing",
        "backplate",
        "aluminum",
        "2mm",
        "millimeters",
        "fixed",
        "focus",
        "weibo",
        "增厚",
        "厚度",
        "变厚",
        "机身",
        "后摄",
        "摄像头",
        "相机",
        "铝合金",
    }
    return bool(shared & dimension_anchors) or (
        score_terms(left_context, ["2mm", "2 mm", "9.9", "10.9", "增厚", "厚度"]) > 0
        and score_terms(right_context, ["2mm", "2 mm", "9.9", "10.9", "增厚", "厚度"]) > 0
    )


def events_same_foldable_iphone_launch_timing(left: Event, right: Event) -> bool:
    left_context = event_merge_context(left).lower()
    right_context = event_merge_context(right).lower()
    if not any(is_foldable_iphone_launch_timing_story(item.title, article_merge_context(item)) for item in left.articles):
        return False
    if not any(is_foldable_iphone_launch_timing_story(item.title, article_merge_context(item)) for item in right.articles):
        return False
    left_tokens = set().union(*(article.tokens for article in left.articles))
    right_tokens = set().union(*(article.tokens for article in right.articles))
    shared = left_tokens & right_tokens
    timing_anchors = {
        "launch",
        "release",
        "preorder",
        "preorders",
        "delayed",
        "delay",
        "september",
        "q4",
        "发售",
        "发布",
        "预购",
        "延期",
        "推迟",
        "交付",
    }
    return bool(shared & timing_anchors) or (
        score_terms(left_context, ["september", "9 月", "九月", "fourth quarter", "q4", "第四季度", "延期", "正常交付"]) > 0
        and score_terms(right_context, ["september", "9 月", "九月", "fourth quarter", "q4", "第四季度", "延期", "正常交付"]) > 0
    )


def events_same_apple_stock_target_analyst(left: Event, right: Event) -> bool:
    left_context = event_merge_context(left).lower()
    right_context = event_merge_context(right).lower()
    if not is_apple_stock_target_analyst_story(left.title, left_context):
        return False
    if not is_apple_stock_target_analyst_story(right.title, right_context):
        return False
    left_tokens = set().union(*(article.tokens for article in left.articles))
    right_tokens = set().union(*(article.tokens for article in right.articles))
    shared = left_tokens & right_tokens
    return bool(shared & {"morgan", "jpmorgan", "aapl", "stock", "target", "345", "price", "目标价", "股价"})


def events_should_merge(left: Event, right: Event) -> bool:
    left_has_retail = any(article.event_kind == "retail_store" for article in left.articles)
    right_has_retail = any(article.event_kind == "retail_store" for article in right.articles)
    if left_has_retail != right_has_retail:
        return False
    if "weak" in {left.relevance_tier, right.relevance_tier} and left.relevance_tier != right.relevance_tier:
        return False
    if events_same_apple_stock_target_analyst(left, right):
        return True
    if not event_title_hardware_product_families_compatible(left, right):
        return False
    if not foldable_iphone_panel_and_production_events_compatible(left, right):
        return False
    if events_same_foldable_iphone_launch_timing(left, right):
        return True
    if events_same_iphone_physical_dimension_rumor(left, right):
        return True
    left_splittable_facets = event_splittable_topic_facets(left)
    right_splittable_facets = event_splittable_topic_facets(right)
    if not splittable_topic_facets_compatible(left_splittable_facets, right_splittable_facets):
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
                core_event = event_from_article_group(event, [*non_weak_articles, *weak_same_topic])
                core_events = split_mixed_topic_event(core_event)
                return [
                    *core_events,
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
        title_scoped_roadmap_facets = title_scoped_hardware_product_roadmap_facets(article.title)
        if title_scoped_roadmap_facets and title_scoped_roadmap_facets <= facets:
            facets = title_scoped_roadmap_facets
        if not facets:
            unassigned.append(article)
            continue
        compatible_key: tuple[str, ...] | None = None
        for key in groups:
            if splittable_topic_facets_compatible(facets, set(key)):
                compatible_key = key
                break
        groups.setdefault(compatible_key or tuple(sorted(facets)), []).append(article)

    if len(groups) < 2:
        return [event]
    shared_group_facets = set.intersection(*(set(key) for key in groups)) if groups else set()
    if shared_group_facets & NO_SPLIT_SHARED_CORE_TOPIC_FACETS:
        groups_have_specific_facets = any(set(key) - NO_SPLIT_SHARED_CORE_TOPIC_FACETS for key in groups)
        if not groups_have_specific_facets:
            return [event]
        group_keys = [set(key) for key in groups]
        if all(
            splittable_topic_facets_compatible(left_key, right_key)
            for index, left_key in enumerate(group_keys)
            for right_key in group_keys[index + 1 :]
        ):
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

    selected_detail_candidates = select_detail_candidates(
        deduped_candidates,
        sources_by_name,
        args.max_detail_pages,
        window_start_utc,
        now_utc,
    )
    for candidate in selected_detail_candidates:
        if candidate.source in sources_by_name:
            diagnostics["source_detail_selection_counts"][candidate.source] = (
                diagnostics["source_detail_selection_counts"].get(candidate.source, 0) + 1
            )
    detail_page_texts = fetch_detail_page_texts(selected_detail_candidates, cache_dir, diagnostics)

    articles: list[Article] = []
    for candidate, page_text in zip(selected_detail_candidates, detail_page_texts):
        source = sources_by_name.get(candidate.source)
        if source is None:
            continue
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
            summary = safe_combine_detail_and_discovery_summary(title, summary, candidate.summary)
        for article_title, article_summary, article_key_facts in roundup_article_variants(
            candidate.title,
            title,
            summary,
            key_facts,
        ):
            variant_context = safe_context_for_detail_article(
                is_roundup,
                article_title,
                article_summary,
                candidate.context,
            )
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
            token_base = (
                article_summary[:700]
                if is_roundup
                else safe_discovery_text_for_detail(article_title, article_summary, candidate.summary)
                or article_summary[:700]
            )
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
