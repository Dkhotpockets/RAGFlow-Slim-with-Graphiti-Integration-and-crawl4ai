"""
Rate limiting utilities for Crawl4AI integration.

This module provides rate limiting functionality to respect website
policies and prevent overwhelming target servers during crawling.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """Rate limiting rule for a domain."""
    requests_per_minute: int
    burst_limit: int = 0
    cooldown_seconds: float = 60.0


@dataclass
class DomainStats:
    """Statistics for domain rate limiting."""
    request_count: int = 0
    window_start: float = field(default_factory=time.time)
    last_request: float = 0.0
    cooldown_until: float = 0.0


class RateLimiter:
    """
    Rate limiter for crawl requests.

    Implements domain-based rate limiting with configurable rules
    and automatic cooldown periods for rate-limited domains.
    """

    def __init__(self):
        """Initialize the rate limiter."""
        self._domain_stats: Dict[str, DomainStats] = {}
        self._default_rule = RateLimitRule(requests_per_minute=30, burst_limit=5)
        self._domain_rules: Dict[str, RateLimitRule] = {}

        # Pre-configured rules for common domains
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Setup default rate limiting rules for common domains."""
        # Conservative rules for major platforms
        self._domain_rules.update({
            "google.com": RateLimitRule(requests_per_minute=10, burst_limit=2),
            "github.com": RateLimitRule(requests_per_minute=15, burst_limit=3),
            "stackoverflow.com": RateLimitRule(requests_per_minute=20, burst_limit=3),
            "wikipedia.org": RateLimitRule(requests_per_minute=60, burst_limit=10),
            "reddit.com": RateLimitRule(requests_per_minute=10, burst_limit=2),
            "twitter.com": RateLimitRule(requests_per_minute=5, burst_limit=1),
            "facebook.com": RateLimitRule(requests_per_minute=5, burst_limit=1),
            "linkedin.com": RateLimitRule(requests_per_minute=5, burst_limit=1),
            "amazon.com": RateLimitRule(requests_per_minute=10, burst_limit=2),
            "youtube.com": RateLimitRule(requests_per_minute=5, burst_limit=1),
        })

    def set_domain_rule(self, domain: str, rule: RateLimitRule) -> None:
        """
        Set a custom rate limiting rule for a domain.

        Args:
            domain: Domain name (e.g., 'example.com')
            rule: Rate limiting rule to apply
        """
        self._domain_rules[domain.lower()] = rule
        logger.info(f"Set rate limit rule for {domain}: {rule.requests_per_minute} req/min, burst {rule.burst_limit}")

    def get_domain_rule(self, domain: str) -> RateLimitRule:
        """
        Get the rate limiting rule for a domain.

        Args:
            domain: Domain name

        Returns:
            RateLimitRule for the domain
        """
        return self._domain_rules.get(domain.lower(), self._default_rule)

    async def wait_if_needed(self, url: str) -> None:
        """
        Wait if necessary to respect rate limits for the given URL.

        Args:
            url: URL to check rate limits for
        """
        domain = self._extract_domain(url)
        if not domain:
            return

        rule = self.get_domain_rule(domain)
        stats = self._get_domain_stats(domain)

        current_time = time.time()

        # Check if in cooldown
        if current_time < stats.cooldown_until:
            wait_time = stats.cooldown_until - current_time
            logger.debug(f"Rate limited for {domain}, waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            return

        # Check if we need to wait for rate limit
        wait_time = self._calculate_wait_time(stats, rule, current_time)
        if wait_time > 0:
            logger.debug(f"Rate limiting {domain}, waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)

        # Update stats
        self._update_stats(stats, current_time)

    def _extract_domain(self, url: str) -> Optional[str]:
        """
        Extract domain from URL.

        Args:
            url: URL to extract domain from

        Returns:
            Domain name or None if invalid
        """
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return None
            # Remove www. prefix
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return None

    def _get_domain_stats(self, domain: str) -> DomainStats:
        """
        Get or create domain statistics.

        Args:
            domain: Domain name

        Returns:
            DomainStats object
        """
        if domain not in self._domain_stats:
            self._domain_stats[domain] = DomainStats()
        return self._domain_stats[domain]

    def _calculate_wait_time(self, stats: DomainStats, rule: RateLimitRule, current_time: float) -> float:
        """
        Calculate how long to wait before making a request.

        Args:
            stats: Current domain statistics
            rule: Rate limiting rule
            current_time: Current timestamp

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        # Reset window if needed
        window_duration = 60.0  # 1 minute window
        if current_time - stats.window_start >= window_duration:
            stats.request_count = 0
            stats.window_start = current_time

        # Check burst limit first
        if rule.burst_limit > 0 and stats.request_count >= rule.burst_limit:
            # Calculate time until next window
            time_to_next_window = window_duration - (current_time - stats.window_start)
            return max(0, time_to_next_window)

        # Check rate limit
        if stats.request_count >= rule.requests_per_minute:
            # Calculate time until next window
            time_to_next_window = window_duration - (current_time - stats.window_start)
            return max(0, time_to_next_window)

        # Check minimum interval between requests
        min_interval = 60.0 / rule.requests_per_minute
        time_since_last = current_time - stats.last_request
        if time_since_last < min_interval:
            return min_interval - time_since_last

        return 0.0

    def _update_stats(self, stats: DomainStats, current_time: float) -> None:
        """
        Update domain statistics after a request.

        Args:
            stats: Domain statistics to update
            current_time: Current timestamp
        """
        stats.request_count += 1
        stats.last_request = current_time

    def handle_rate_limit_response(self, url: str, status_code: int, retry_after: Optional[str] = None) -> None:
        """
        Handle rate limit response from server.

        Args:
            url: URL that was rate limited
            status_code: HTTP status code (e.g., 429)
            retry_after: Retry-After header value
        """
        domain = self._extract_domain(url)
        if not domain:
            return

        stats = self._get_domain_stats(domain)
        rule = self.get_domain_rule(domain)

        # Calculate cooldown based on response
        if retry_after:
            try:
                # Try parsing as seconds
                cooldown = float(retry_after)
            except ValueError:
                # Try parsing as HTTP date
                try:
                    from email.utils import parsedate_to_datetime
                    retry_date = parsedate_to_datetime(retry_after)
                    cooldown = (retry_date - datetime.now(retry_date.tzinfo)).total_seconds()
                except Exception:
                    cooldown = rule.cooldown_seconds
        else:
            cooldown = rule.cooldown_seconds

        stats.cooldown_until = time.time() + cooldown
        logger.warning(f"Rate limited by {domain} (status {status_code}), cooling down for {cooldown:.2f}s")

    def get_stats(self) -> Dict[str, dict]:
        """
        Get current rate limiting statistics.

        Returns:
            Dictionary of domain statistics
        """
        current_time = time.time()
        stats = {}

        for domain, domain_stats in self._domain_stats.items():
            rule = self.get_domain_rule(domain)
            stats[domain] = {
                "requests_this_window": domain_stats.request_count,
                "window_start": domain_stats.window_start,
                "last_request": domain_stats.last_request,
                "cooldown_until": domain_stats.cooldown_until,
                "is_cooling_down": current_time < domain_stats.cooldown_until,
                "rule": {
                    "requests_per_minute": rule.requests_per_minute,
                    "burst_limit": rule.burst_limit,
                    "cooldown_seconds": rule.cooldown_seconds,
                }
            }

        return stats

    def reset_domain(self, domain: str) -> None:
        """
        Reset rate limiting statistics for a domain.

        Args:
            domain: Domain to reset
        """
        if domain in self._domain_stats:
            del self._domain_stats[domain]
            logger.info(f"Reset rate limiting stats for {domain}")

    def reset_all(self) -> None:
        """Reset all rate limiting statistics."""
        self._domain_stats.clear()
        logger.info("Reset all rate limiting statistics")