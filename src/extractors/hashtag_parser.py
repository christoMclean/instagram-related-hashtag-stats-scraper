from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from utils.helpers import logger, humanize_posts_count

@dataclass
class HashtagStats:
    name: str
    postsCount: int
    url: str
    posts: str
    postsPerDay: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class HashtagParser:
    """
    Responsible for fetching and parsing hashtag-level statistics
    from Instagram's public tag pages.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 10,
        max_retries: int = 3,
        sleep_between_requests: float = 1.0,
        user_agent: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep_between_requests = sleep_between_requests
        self.headers = {
            "User-Agent": user_agent
            or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _build_hashtag_url(self, hashtag: str) -> str:
        tag = hashtag.lstrip("#")
        return f"{self.base_url}/explore/tags/{tag}/"

    def fetch_hashtag_page(self, hashtag: str) -> Optional[str]:
        """
        Fetch the raw HTML for a hashtag page, with basic retry logic.
        """
        url = self._build_hashtag_url(hashtag)
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("GET %s (attempt %s/%s)", url, attempt, self.max_retries)
                response = requests.get(
                    url, headers=self.headers, timeout=self.timeout
                )
                if response.status_code == 200:
                    logger.debug("Received 200 for %s", url)
                    return response.text

                logger.warning(
                    "Non-200 response (%s) for %s: %s",
                    response.status_code,
                    url,
                    response.text[:200],
                )
            except Exception as exc:
                last_exc = exc
                logger.warning("Error fetching %s: %s", url, exc)

            time.sleep(self.sleep_between_requests)

        logger.error(
            "Failed to fetch hashtag page for %s after %s attempts. Last error: %s",
            hashtag,
            self.max_retries,
            last_exc,
        )
        return None

    @staticmethod
    def _extract_json_from_html(html: str) -> Optional[Dict[str, Any]]:
        """
        Instagram embeds JSON in one of several ways. This tries a few of the
        more common patterns and returns the best-effort JSON payload.
        """
        # window._sharedData pattern
        shared_data_match = re.search(
            r"window\._sharedData\s*=\s*(\{.*?\});</script>",
            html,
            re.DOTALL,
        )
        if shared_data_match:
            try:
                return json.loads(shared_data_match.group(1))
            except json.JSONDecodeError:
                logger.debug("Failed to decode window._sharedData payload.")

        # __additionalDataLoaded pattern
        additional_match = re.search(
            r"window\.__additionalDataLoaded\('.*?',\s*(\{.*?\})\);",
            html,
            re.DOTALL,
        )
        if additional_match:
            try:
                return json.loads(additional_match.group(1))
            except json.JSONDecodeError:
                logger.debug("Failed to decode __additionalDataLoaded payload.")

        # Fallback: attempt to locate <script type="application/ld+json">
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.text)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue

        logger.debug("No recognizable JSON payload found in hashtag page HTML.")
        return None

    @staticmethod
    def _extract_hashtag_node(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Try to locate the hashtag-level node inside the JSON payload.
        Different Instagram layouts nest it differently.
        """
        # Legacy layout: entry_data.TagPage[0].graphql.hashtag
        try:
            node = payload["entry_data"]["TagPage"][0]["graphql"]["hashtag"]
            if isinstance(node, dict):
                return node
        except Exception:
            pass

        # Some layouts place data directly under graphql.hashtag
        try:
            node = payload["graphql"]["hashtag"]
            if isinstance(node, dict):
                return node
        except Exception:
            pass

        # Fallback: no recognized node
        return None

    @staticmethod
    def _estimate_posts_per_day(posts_count: int) -> float:
        """
        Rough heuristic for posts per day given only a total count.
        We assume the hashtag has been "alive" for a few years.
        """
        if posts_count <= 0:
            return 0.0

        approximate_days = 5 * 365  # assume ~5 years of activity
        return round(posts_count / approximate_days, 2)

    def _parse_stats_from_node(
        self, hashtag: str, node: Dict[str, Any]
    ) -> HashtagStats:
        name = node.get("name") or hashtag.lstrip("#")
        media_info = node.get("edge_hashtag_to_media") or {}
        posts_count = int(media_info.get("count") or 0)

        url = self._build_hashtag_url(hashtag)
        posts_human = humanize_posts_count(posts_count)
        posts_per_day = self._estimate_posts_per_day(posts_count)

        logger.debug(
            "Parsed hashtag stats name=%s postsCount=%s postsPerDay=%s",
            name,
            posts_count,
            posts_per_day,
        )

        return HashtagStats(
            name=name,
            postsCount=posts_count,
            url=url,
            posts=posts_human,
            postsPerDay=posts_per_day,
        )

    def _fallback_minimal_stats(self, hashtag: str) -> HashtagStats:
        """
        When parsing fails, return a minimal stats structure so the pipeline
        still produces predictable output.
        """
        tag = hashtag.lstrip("#")
        url = self._build_hashtag_url(hashtag)
        logger.info(
            "Falling back to minimal stats for hashtag %s (no structured data found).",
            hashtag,
        )
        return HashtagStats(
            name=tag,
            postsCount=0,
            url=url,
            posts="0",
            postsPerDay=0.0,
        )

    def fetch_stats(self, hashtag: str) -> HashtagStats:
        """
        Main entry point for the rest of the application.
        Returns best-effort statistics for the given hashtag.
        """
        html = self.fetch_hashtag_page(hashtag)
        if html is None:
            return self._fallback_minimal_stats(hashtag)

        payload = self._extract_json_from_html(html)
        if not payload:
            return self._fallback_minimal_stats(hashtag)

        node = self._extract_hashtag_node(payload)
        if not node:
            return self._fallback_minimal_stats(hashtag)

        try:
            return self._parse_stats_from_node(hashtag, node)
        except Exception as exc:
            logger.error(
                "Error parsing stats for hashtag %s: %s", hashtag, exc, exc_info=True
            )
            return self._fallback_minimal_stats(hashtag)