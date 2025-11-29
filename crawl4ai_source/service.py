"""
Crawl4AI Service Implementation for RAGFlow Slim

This module provides the core crawling service that uses Crawl4AI to extract
content from web pages and return structured results.
"""

import hashlib
import time
from typing import Optional
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from .models import CrawlConfig, CrawlResult


class CrawlService:
    """
    Service for crawling web pages using Crawl4AI.

    Provides async methods for crawling URLs with configurable parameters,
    content extraction, and result processing.
    """

    def __init__(self):
        """Initialize the crawl service."""
        self._crawler: Optional[AsyncWebCrawler] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()

    async def start(self) -> None:
        """Start the crawler service."""
        if self._crawler is None:
            # Configure browser for headless operation
            browser_config = BrowserConfig(
                headless=True,
                # Additional browser config can be added here
            )
            self._crawler = AsyncWebCrawler(config=browser_config)

    async def stop(self) -> None:
        """Stop the crawler service."""
        if self._crawler is not None:
            await self._crawler.close()
            self._crawler = None

    async def crawl_url(self, url: str, config: CrawlConfig) -> CrawlResult:
        """
        Crawl a URL and extract content using Crawl4AI.

        Args:
            url: The URL to crawl
            config: Crawling configuration parameters

        Returns:
            CrawlResult containing extracted content and metadata

        Raises:
            Exception: If crawling fails
        """
        if self._crawler is None:
            raise RuntimeError("Crawler service not started. Use async context manager or call start() first.")

        start_time = time.time()

        try:
            # Configure the crawl run
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,  # Don't use cache for fresh content
                # Set timeout
                # Note: Crawl4AI uses different timeout configuration
                # We'll handle timeout at the service level
            )

            # Perform the crawl
            result = await self._crawler.arun(
                url=url,
                config=run_config,
            )

            crawl_time = time.time() - start_time

            # Extract content and metadata
            content = ""
            if hasattr(result, 'markdown') and result.markdown:
                content = result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown)
            elif hasattr(result, 'markdown_v2') and result.markdown_v2:
                content = result.markdown_v2.raw_markdown if hasattr(result.markdown_v2, 'raw_markdown') else str(result.markdown_v2)
            else:
                # Fallback to HTML content
                content = result.html if hasattr(result, 'html') and result.html else ""
            title = self._extract_title(result)
            metadata = self._extract_metadata(result, config)
            links = self._extract_links(result)

            # Generate content hash for deduplication
            content_hash = self._generate_content_hash(content)

            # Create result object
            crawl_result = CrawlResult(
                url=result.url or url,  # Use final URL if redirected
                title=title,
                content=content,
                metadata=metadata,
                links=links,
                content_hash=content_hash,
                content_size=len(content.encode('utf-8')),
                crawl_time=crawl_time,
            )

            return crawl_result

        except Exception as e:
            crawl_time = time.time() - start_time
            # Create a minimal result for failed crawls
            crawl_result = CrawlResult(
                url=url,
                content="",
                content_size=0,
                crawl_time=crawl_time,
                metadata={"error": str(e)},
            )
            raise e

    def _extract_title(self, result) -> Optional[str]:
        """Extract page title from crawl result."""
        try:
            # Try to get title from various sources
            if hasattr(result, 'metadata') and result.metadata:
                return result.metadata.get('title')

            # Fallback: extract from HTML if available
            if hasattr(result, 'html') and result.html:
                # Simple title extraction (could be improved)
                import re
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', result.html, re.IGNORECASE)
                if title_match:
                    return title_match.group(1).strip()

            return None
        except Exception:
            return None

    def _extract_metadata(self, result, config: CrawlConfig) -> dict:
        """Extract metadata from crawl result."""
        metadata = {}

        try:
            if config.extract_metadata and hasattr(result, 'metadata'):
                # Copy relevant metadata
                result_meta = result.metadata or {}
                metadata.update({
                    'title': result_meta.get('title'),
                    'description': result_meta.get('description'),
                    'keywords': result_meta.get('keywords'),
                    'author': result_meta.get('author'),
                    'language': result_meta.get('language'),
                    'content_type': result_meta.get('content_type'),
                })

            # Add crawl configuration info
            metadata['crawl_config'] = {
                'max_depth': config.max_depth,
                'timeout_seconds': config.timeout_seconds,
                'respect_robots': config.respect_robots,
                'user_agent': config.user_agent,
            }

            # Add URL information
            parsed_url = urlparse(result.url or "")
            metadata['domain'] = parsed_url.netloc
            metadata['scheme'] = parsed_url.scheme

        except Exception as e:
            metadata['extraction_error'] = str(e)

        return metadata

    def _extract_links(self, result) -> list[str]:
        """Extract links from crawl result."""
        links = []

        try:
            if hasattr(result, 'links') and result.links:
                # result.links might be a list of link objects or strings
                if isinstance(result.links, list):
                    for link in result.links:
                        if isinstance(link, str):
                            links.append(link)
                        elif isinstance(link, dict) and 'href' in link:
                            links.append(link['href'])

            # Remove duplicates and filter
            links = list(set(links))
            # Could add filtering for internal/external links here

        except Exception as e:
            # Log link extraction failures but don't fail the crawl
            import logging
            logging.debug(f"Failed to extract links: {e}")

        return links

    def _generate_content_hash(self, content: str) -> str:
        """Generate SHA256 hash of content for deduplication."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    async def health_check(self) -> bool:
        """Check if the crawler service is healthy."""
        try:
            if self._crawler is None:
                return False

            # Simple health check - try to get crawler info
            # This is a basic check; could be enhanced
            return True
        except Exception:
            return False