"""
Content deduplication utilities for Crawl4AI integration.

This module provides utilities for detecting and preventing duplicate
content from being stored, using content hashing and similarity analysis.
"""

import hashlib
import logging
from typing import Optional
from dataclasses import dataclass
from difflib import SequenceMatcher

from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class ContentFingerprint:
    """Fingerprint of crawled content for deduplication."""
    content_hash: str
    url_hash: str
    title_hash: Optional[str]
    similarity_threshold: float = 0.85


class ContentDeduplicator:
    """
    Handles content deduplication using multiple strategies:
    - Exact hash matching
    - URL-based deduplication
    - Content similarity analysis
    """

    def __init__(self, supabase_client: Client, similarity_threshold: float = 0.85):
        """
        Initialize the deduplicator.

        Args:
            supabase_client: Supabase client for database operations
            similarity_threshold: Threshold for content similarity (0.0-1.0)
        """
        self.supabase = supabase_client
        self.similarity_threshold = similarity_threshold

    def generate_content_hash(self, content: str) -> str:
        """
        Generate SHA-256 hash of content for exact deduplication.

        Args:
            content: Content to hash

        Returns:
            SHA-256 hash string
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def generate_url_hash(self, url: str) -> str:
        """
        Generate hash of normalized URL.

        Args:
            url: URL to hash

        Returns:
            SHA-256 hash string
        """
        # Normalize URL for consistent hashing
        normalized_url = self._normalize_url(url)
        return hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()

    def generate_title_hash(self, title: str) -> Optional[str]:
        """
        Generate hash of title for deduplication.

        Args:
            title: Title to hash

        Returns:
            SHA-256 hash string or None if title is empty
        """
        if not title or not title.strip():
            return None
        return hashlib.sha256(title.strip().lower().encode('utf-8')).hexdigest()

    def create_fingerprint(self, url: str, content: str, title: Optional[str] = None) -> ContentFingerprint:
        """
        Create a content fingerprint for deduplication checking.

        Args:
            url: Source URL
            content: Content text
            title: Optional title

        Returns:
            ContentFingerprint object
        """
        return ContentFingerprint(
            content_hash=self.generate_content_hash(content),
            url_hash=self.generate_url_hash(url),
            title_hash=self.generate_title_hash(title) if title else None,
            similarity_threshold=self.similarity_threshold,
        )

    async def is_duplicate(self, fingerprint: ContentFingerprint) -> bool:
        """
        Check if content is a duplicate based on fingerprint.

        Args:
            fingerprint: Content fingerprint to check

        Returns:
            True if duplicate found, False otherwise
        """
        try:
            # Check exact content hash first (fastest)
            if await self._check_exact_hash(fingerprint.content_hash):
                logger.debug(f"Exact content hash match: {fingerprint.content_hash}")
                return True

            # Check URL hash (good for same URL recrawls)
            if await self._check_url_hash(fingerprint.url_hash):
                logger.debug(f"URL hash match: {fingerprint.url_hash}")
                return True

            # Check title hash if available (good for similar content)
            if fingerprint.title_hash and await self._check_title_hash(fingerprint.title_hash):
                logger.debug(f"Title hash match: {fingerprint.title_hash}")
                return True

            # Check content similarity (slowest, most comprehensive)
            if await self._check_similarity(fingerprint):
                logger.debug(f"Content similarity match for: {fingerprint.content_hash}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking for duplicates: {e}")
            # On error, allow content (fail open)
            return False

    async def _check_exact_hash(self, content_hash: str) -> bool:
        """Check for exact content hash match."""
        try:
            response = self.supabase.table("crawl_content").select("id").eq("content_hash", content_hash).limit(1).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking exact hash: {e}")
            return False

    async def _check_url_hash(self, url_hash: str) -> bool:
        """Check for URL hash match."""
        try:
            response = self.supabase.table("crawl_content").select("id").eq("url_hash", url_hash).limit(1).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking URL hash: {e}")
            return False

    async def _check_title_hash(self, title_hash: str) -> bool:
        """Check for title hash match."""
        try:
            response = self.supabase.table("crawl_content").select("id").eq("title_hash", title_hash).limit(1).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking title hash: {e}")
            return False

    async def _check_similarity(self, fingerprint: ContentFingerprint) -> bool:
        """
        Check content similarity against existing content.

        This is a more expensive operation that compares content
        against recent crawls to find similar content.
        """
        try:
            # Get recent content for comparison (last 1000 entries)
            response = self.supabase.table("crawl_content").select("content").order("extracted_at", desc=True).limit(1000).execute()

            if not response.data:
                return False

            # Extract content from results
            existing_content = []
            for row in response.data:
                # Note: In a real implementation, you'd want to store processed content
                # For now, we'll use a simplified approach
                if row.get("content"):
                    existing_content.append(row["content"])

            # Check similarity against each existing content
            for existing in existing_content:
                if self._calculate_similarity(fingerprint.content_hash, existing) >= fingerprint.similarity_threshold:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking similarity: {e}")
            return False

    def _calculate_similarity(self, content1: str, content2: str) -> float:
        """
        Calculate similarity ratio between two content strings.

        Args:
            content1: First content string
            content2: Second content string

        Returns:
            Similarity ratio (0.0-1.0)
        """
        # For simplicity, use sequence matcher
        # In production, you might want more sophisticated similarity measures
        return SequenceMatcher(None, content1, content2).ratio()

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for consistent hashing.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL string
        """
        # Remove common tracking parameters
        import urllib.parse
        parsed = urllib.parse.urlparse(url)

        # Remove query parameters that don't affect content
        ignore_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid'}
        query_params = urllib.parse.parse_qs(parsed.query)
        filtered_params = {k: v for k, v in query_params.items() if k not in ignore_params}

        # Reconstruct URL
        parsed = parsed._replace(query=urllib.parse.urlencode(filtered_params, doseq=True))

        # Remove trailing slash
        normalized = urllib.parse.urlunparse(parsed).rstrip('/')

        return normalized.lower()

    async def get_duplicate_stats(self) -> dict:
        """
        Get statistics about duplicate content detection.

        Returns:
            Dictionary with duplicate statistics
        """
        try:
            # Count total content
            total_response = self.supabase.table("crawl_content").select("id", count="exact").execute()
            total_count = total_response.count or 0

            # Count unique content hashes
            unique_response = self.supabase.table("crawl_content").select("content_hash").execute()
            unique_hashes = set(row["content_hash"] for row in unique_response.data)
            unique_count = len(unique_hashes)

            # Count unique URLs
            unique_url_response = self.supabase.table("crawl_content").select("url_hash").execute()
            unique_url_hashes = set(row["url_hash"] for row in unique_url_response.data)
            unique_url_count = len(unique_url_hashes)

            return {
                "total_content": total_count,
                "unique_content": unique_count,
                "unique_urls": unique_url_count,
                "duplicate_content": total_count - unique_count,
                "duplicate_urls": total_count - unique_url_count,
            }

        except Exception as e:
            logger.error(f"Error getting duplicate stats: {e}")
            return {
                "total_content": 0,
                "unique_content": 0,
                "unique_urls": 0,
                "duplicate_content": 0,
                "duplicate_urls": 0,
            }