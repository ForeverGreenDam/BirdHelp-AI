"""图片提供器 — 根据 slide image_query 搜索/下载/生成配图。

三级降级策略:
  1. Unsplash API 搜索 → 下载真实图片
  2. Pexels API 备选
  3. 纯色占位图（PIL 生成带文字标签的 PNG）

支持并发下载和本地缓存，避免重复请求同一 query。
"""

from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from config import settings
from utils.file import ensure_temp_dir

# ── 缓存目录 ──
_IMAGES_DIR: Path | None = None


def _images_dir() -> Path:
    """获取图片缓存目录（惰性创建）。"""
    global _IMAGES_DIR
    if _IMAGES_DIR is None:
        _IMAGES_DIR = ensure_temp_dir() / "ppt_images"
        _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return _IMAGES_DIR


# ── Unsplash 搜索 ──

UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"
UNSPLASH_DOWNLOAD_TIMEOUT = 15.0


async def _search_unsplash(query: str, per_page: int = 3) -> list[dict]:
    """通过 Unsplash API 搜索图片，返回图片信息列表。"""
    if not settings.ppt_unsplash_access_key:
        logger.debug("Unsplash API key not configured, skip")
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                UNSPLASH_SEARCH_URL,
                params={"query": query, "per_page": per_page},
                headers={"Authorization": f"Client-ID {settings.ppt_unsplash_access_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])
            logger.warning(f"Unsplash search failed: HTTP {resp.status_code}")
            return []
    except Exception as exc:
        logger.warning(f"Unsplash search error: {exc}")
        return []


# ── Pexels 搜索（降级备选） ──

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"


async def _search_pexels(query: str, per_page: int = 3) -> list[dict]:
    """通过 Pexels API 搜索图片，返回图片信息列表。"""
    if not settings.ppt_pexels_api_key:
        logger.debug("Pexels API key not configured, skip")
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                PEXELS_SEARCH_URL,
                params={"query": query, "per_page": per_page},
                headers={"Authorization": settings.ppt_pexels_api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("photos", [])
            logger.warning(f"Pexels search failed: HTTP {resp.status_code}")
            return []
    except Exception as exc:
        logger.warning(f"Pexels search error: {exc}")
        return []


# ── 图片下载 ──

async def _download_image(url: str, dest_path: Path) -> bool:
    """下载单张图片到指定路径，返回是否成功。"""
    try:
        async with httpx.AsyncClient(timeout=UNSPLASH_DOWNLOAD_TIMEOUT) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200:
                dest_path.write_bytes(resp.content)
                logger.debug(f"Image downloaded: {dest_path.name}")
                return True
    except Exception as exc:
        logger.warning(f"Image download failed from {url[:80]}: {exc}")
    return False


# ── 占位图生成（最终降级） ──

PLACEHOLDER_SIZE = (1280, 720)  # 16:9，足够 PPT 使用


def _generate_placeholder(query: str, dest_path: Path, theme_hex: str = "1A3C6E") -> bool:
    """生成带文字标签的纯色占位图，永远成功（最终降级方案）。"""
    try:
        # 由 query 哈希决定底色，保证同一 query 占位图一致
        h = hashlib.md5(query.encode()).hexdigest()  # noqa: S324 (非安全用途，仅需确定性)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        # 降低饱和度，使占位图看起来更柔和
        r = (r + 200) // 2
        g = (g + 200) // 2
        b = (b + 200) // 2

        img = Image.new("RGB", PLACEHOLDER_SIZE, (r, g, b))
        draw = ImageDraw.Draw(img)

        # 绘制文字标签
        label_lines = _wrap_text(query, max_width=30)
        # 尝试用系统字体
        font = None
        for font_name in ["msyh.ttc", "simhei.ttf", "arial.ttf", "DejaVuSans.ttf"]:
            try:
                font = ImageFont.truetype(font_name, 36)
                break
            except (OSError, IOError):
                continue
        if font is None:
            font = ImageFont.load_default()

        # 居中绘制文字
        line_height = 50
        total_h = len(label_lines) * line_height
        start_y = (PLACEHOLDER_SIZE[1] - total_h) // 2
        for i, line in enumerate(label_lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (PLACEHOLDER_SIZE[0] - text_w) // 2
            y = start_y + i * line_height
            draw.text((x, y), line, fill=(255, 255, 255), font=font)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest_path, "PNG")
        logger.info(f"Placeholder image generated: {dest_path.name} for '{query[:40]}'")
        return True
    except Exception as exc:
        logger.error(f"Placeholder generation failed for '{query}': {exc}")
        # 创建一个最小的 1px 图片兜底
        img = Image.new("RGB", (100, 100), (200, 200, 200))
        img.save(dest_path, "PNG")
        return True


def _wrap_text(text: str, max_width: int = 30) -> list[str]:
    """简单按宽度折行。"""
    if len(text) <= max_width:
        return [text]
    lines = []
    current = ""
    for char in text:
        if len(current) >= max_width:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines if lines else [text]


# ── 主入口 ──

async def fetch_images_for_slides(
    slides: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """根据 slides JSON 搜索并下载图片，返回 页面标识 -> 本地路径列表 的映射。

    Args:
        slides: LLM 输出的 slides 列表，每项含 image_query / page_number 字段

    Returns:
        {"slide_01": ["/tmp/birdhelp/ppt_images/slide-01-main.jpg"], ...}
        仅返回有 image_query 且 strategy 为 MEDIA_REQUIRED 或 AUTO 的页面
    """
    # 收集需要图片的页面
    image_tasks: list[dict] = []
    for slide in slides:
        query = slide.get("image_query", "").strip()
        if not query:
            continue
        page_key = f"slide_{slide.get('page_number', 0):02d}"
        image_tasks.append({
            "page_key": page_key,
            "query": query,
            "slide_index": slide.get("page_number", 0),
        })

    if not image_tasks:
        logger.info("No image queries found in slides")
        return {}

    # 并发处理所有图片任务（最多 4 路并发）
    semaphore = asyncio.Semaphore(4)
    results: dict[str, list[str]] = {}

    async def _process_one(task: dict) -> None:
        async with semaphore:
            path = await _fetch_single_image(task["query"], task["page_key"])
            if path:
                results[task["page_key"]] = [str(path)]

    await asyncio.gather(*[_process_one(t) for t in image_tasks])
    logger.info(f"Image fetch complete: {len(results)}/{len(image_tasks)} slides got images")
    return results


async def _fetch_single_image(query: str, page_key: str) -> Path | None:
    """为单个 query 获取一张图片：Unsplash → Pexels → 占位图。"""
    cache_name = f"{page_key}-{_query_hash(query)}.jpg"
    dest = _images_dir() / cache_name

    # 命中缓存则直接返回
    if dest.exists():
        logger.debug(f"Image cache hit: {dest.name}")
        return dest

    # 1. 尝试 Unsplash
    unsplash_results = await _search_unsplash(query)
    if unsplash_results:
        img_url = unsplash_results[0].get("urls", {}).get("regular", "")
        if img_url and await _download_image(img_url, dest):
            return dest

    # 2. 降级 Pexels
    pexels_results = await _search_pexels(query)
    if pexels_results:
        img_url = pexels_results[0].get("src", {}).get("large", "")
        if img_url and await _download_image(img_url, dest):
            return dest

    # 3. 最终降级：生成纯色占位图
    placeholder_path = _images_dir() / f"{page_key}-placeholder.png"
    if _generate_placeholder(query, placeholder_path):
        return placeholder_path

    return None


def _query_hash(query: str) -> str:
    """对 query 取哈希摘要，用于缓存文件名。"""
    return hashlib.md5(query.encode()).hexdigest()[:12]  # noqa: S324 (非安全用途)


def get_image_for_slide(
    images_map: dict[str, list[str]],
    slide_index: int,
) -> list[str]:
    """从图片映射中按页面索引查找图片路径列表。"""
    key = f"slide_{slide_index:02d}"
    return images_map.get(key, [])
