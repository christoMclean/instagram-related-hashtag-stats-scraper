from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from utils.helpers import logger
from .hashtag_parser import HashtagParser

@dataclass
class RelatedTag:
    name: str
    media_count: int

class RelationsMapper:
    """
    Responsible for turning Instagram's "related tags" data into a richer
    structure of frequent / average / rare groupings, both literal and
    semantically related.
    """

    def __init__(self, parser: HashtagParser) -> None:
        self.parser = parser

    @staticmethod
    def _extract_json_from_html(html: str) -> Optional[Dict[str, Any]]:
        from .hashtag_parser import HashtagParser as HP

        return HP._extract_json_from_html(html)  # type: ignore[attr-defined]

    @staticmethod
    def _extract_hashtag_node(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from .hashtag_parser import HashtagParser as HP

        return HP._extract_hashtag_node(payload)  # type: ignore[attr-defined]

    @staticmethod
    def _collect_related_tags(node: Dict[str, Any]) -> List[RelatedTag]:
        """
        Instagram may expose related tags via one or more collections.
        We normalize them into a simple list with media_count.
        """
        related: List[RelatedTag] = []

        # Common pattern (not officially documented):
        # node['edge_hashtag_to_related_tags']['edges']
        related_data = node.get("edge_hashtag_to_related_tags") or {}
        edges = related_data.get("edges") or []

        for edge in edges:
            try:
                tag_node = edge.get("node") or {}
                name = tag_node.get("name")
                media_info = tag_node.get("edge_hashtag_to_media") or {}
                media_count = int(media_info.get("count") or 0)
                if name:
                    related.append(RelatedTag(name=name, media_count=media_count))
            except Exception as exc:
                logger.debug("Failed to parse related tag edge: %s", exc)

        return related

    @staticmethod
    def _bucketize_related_tags(
        tags: List[RelatedTag],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Split related tags into frequent, average, rare buckets based on
        relative media_count thresholds.
        """
        if not tags:
            return {
                "related": [],
                "frequent": [],
                "average": [],
                "rare": [],
                "relatedFrequent": [],
                "relatedAverage": [],
                "relatedRare": [],
            }

        sorted_tags = sorted(tags, key=lambda t: t.media_count, reverse=True)
        counts = [t.media_count for t in sorted_tags]
        max_count = max(counts) or 1

        frequent_threshold = max_count * 0.6
        rare_threshold = max_count * 0.2

        frequent: List[Dict[str, Any]] = []
        average: List[Dict[str, Any]] = []
        rare: List[Dict[str, Any]] = []

        for t in sorted_tags:
            entry = {"hash": f"#{t.name}", "info": t.media_count}
            if t.media_count >= frequent_threshold:
                frequent.append(entry)
            elif t.media_count <= rare_threshold:
                rare.append(entry)
            else:
                average.append(entry)

        # The "related" field is a flat list combining all buckets but with
        # human-readable info.
        related_flat: List[Dict[str, Any]] = []
        for t in sorted_tags:
            related_flat.append(
                {
                    "hash": f"#{t.name}",
                    "info": t.media_count,
                }
            )

        # For now, we treat semantic vs literal as the same pool. In a more
        # advanced setup, this is where an embedding model or external
        # semantic index would plug in.
        return {
            "related": related_flat,
            "frequent": frequent,
            "average": average,
            "rare": rare,
            "relatedFrequent": frequent,
            "relatedAverage": average,
            "relatedRare": rare,
        }

    def map_relations(self, hashtag: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Public API: best-effort mapping of related hashtags into buckets.
        Returns a dict keyed by:
          - related
          - frequent
          - average
          - rare
          - relatedFrequent
          - relatedAverage
          - relatedRare
        """
        html = self.parser.fetch_hashtag_page(hashtag)
        if html is None:
            logger.info(
                "No HTML available for hashtag %s, skipping relation mapping.",
                hashtag,
            )
            return self._bucketize_related_tags([])

        payload = self._extract_json_from_html(html)
        if not payload:
            logger.info(
                "No JSON payload available for hashtag %s, skipping relation mapping.",
                hashtag,
            )
            return self._bucketize_related_tags([])

        node = self._extract_hashtag_node(payload)
        if not node:
            logger.info(
                "No hashtag node found for %s, skipping relation mapping.", hashtag
            )
            return self._bucketize_related_tags([])

        related_tags = self._collect_related_tags(node)
        logger.debug(
            "Collected %s raw related tags for hashtag %s.",
            len(related_tags),
            hashtag,
        )
        return self._bucketize_related_tags(related_tags)