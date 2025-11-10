from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from utils.helpers import logger
from .hashtag_parser import HashtagParser

@dataclass
class TopPost:
    id: str
    type: str
    shortCode: str
    caption: str
    hashtags: List[str]
    mentions: List[str]
    url: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class PostCollector:
    """
    Extracts top (or recent) posts for a given hashtag from the same
    JSON payload used by HashtagParser.
    """

    def __init__(self, parser: HashtagParser) -> None:
        self.parser = parser

    @staticmethod
    def _extract_json_from_html(html: str) -> Optional[Dict[str, Any]]:
        # Reuse HashtagParser's JSON extraction to keep behavior consistent.
        from .hashtag_parser import HashtagParser as HP

        return HP._extract_json_from_html(html)  # type: ignore[attr-defined]

    @staticmethod
    def _extract_hashtag_node(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from .hashtag_parser import HashtagParser as HP

        return HP._extract_hashtag_node(payload)  # type: ignore[attr-defined]

    @staticmethod
    def _parse_caption(edge: Dict[str, Any]) -> str:
        node = edge.get("node", {})
        edge_caption = node.get("edge_media_to_caption") or {}
        edges = edge_caption.get("edges") or []
        if edges:
            text = (edges[0].get("node") or {}).get("text") or ""
            return text
        return ""

    @staticmethod
    def _parse_hashtags_and_mentions(caption: str) -> (List[str], List[str]):
        words = caption.split()
        hashes: List[str] = []
        mentions: List[str] = []
        for word in words:
            if word.startswith("#") and len(word) > 1:
                hashes.append(word.strip("#").strip())
            elif word.startswith("@") and len(word) > 1:
                mentions.append(word.strip("@").strip())
        return hashes, mentions

    def _parse_top_posts_from_node(self, node: Dict[str, Any]) -> List[TopPost]:
        """
        Instagram commonly exposes top posts for a hashtag via
        node['edge_hashtag_to_top_posts']['edges'].
        """
        posts: List[TopPost] = []

        top_posts_data = node.get("edge_hashtag_to_top_posts") or {}
        edges = top_posts_data.get("edges") or []

        for edge in edges:
            try:
                node_data = edge.get("node", {})
                post_id = str(node_data.get("id") or "")
                if not post_id:
                    continue

                typename = node_data.get("__typename") or "Post"
                short_code = node_data.get("shortcode") or ""
                caption = self._parse_caption(edge)
                hashtags, mentions = self._parse_hashtags_and_mentions(caption)

                display_url = node_data.get("display_url") or ""
                permalink = f"{self.parser.base_url}/p/{short_code}/" if short_code else ""

                posts.append(
                    TopPost(
                        id=post_id,
                        type=typename,
                        shortCode=short_code,
                        caption=caption,
                        hashtags=hashtags,
                        mentions=mentions,
                        url=permalink or display_url,
                    )
                )
            except Exception as exc:
                logger.debug("Failed to parse top post edge: %s", exc)

        return posts

    def _fallback_from_html_cards(self, html: str) -> List[TopPost]:
        """
        Very rough HTML fallback: look for <a> tags to individual posts,
        synthesize minimal TopPost records.
        """
        soup = BeautifulSoup(html, "html.parser")
        posts: List[TopPost] = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("/p/"):
                continue

            short_code = href.split("/")[2] if len(href.split("/")) > 2 else ""
            url = f"{self.parser.base_url}{href}"
            caption = a.get("aria-label") or a.get("title") or ""
            hashtags, mentions = self._parse_hashtags_and_mentions(caption)

            posts.append(
                TopPost(
                    id=short_code or url,
                    type="Post",
                    shortCode=short_code,
                    caption=caption,
                    hashtags=hashtags,
                    mentions=mentions,
                    url=url,
                )
            )

            if len(posts) >= 12:
                break

        return posts

    def collect_top_posts(self, hashtag: str) -> List[TopPost]:
        """
        Public API: returns a list of TopPost for a given hashtag.
        Always returns a list, possibly empty.
        """
        html = self.parser.fetch_hashtag_page(hashtag)
        if html is None:
            logger.info(
                "No HTML available for hashtag %s, returning empty topPosts.", hashtag
            )
            return []

        payload = self._extract_json_from_html(html)
        if payload:
            node = self._extract_hashtag_node(payload)
            if node:
                posts = self._parse_top_posts_from_node(node)
                if posts:
                    logger.debug(
                        "Parsed %s top posts for hashtag %s using JSON.",
                        len(posts),
                        hashtag,
                    )
                    return posts

        # If we get here, structured JSON parsing didn't work; try HTML cards.
        logger.info(
            "Falling back to HTML-based extraction for top posts of hashtag %s.",
            hashtag,
        )
        return self._fallback_from_html_cards(html)