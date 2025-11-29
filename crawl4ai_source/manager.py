"""
Crawl4AI Job Manager for RAGFlow Slim

This module provides the CrawlJobManager class that handles the lifecycle
of crawl jobs, including persistence, queuing, and execution management.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

from supabase import Client

from .models import CrawlJob, CrawlStatus, CrawlConfig, CrawlResult
from .service import CrawlService

# Import Graphiti integration
try:
    from graphiti_client import add_episode_async, GRAPHITI_AVAILABLE
    add_episode = add_episode_async  # Use async version
except ImportError:
    GRAPHITI_AVAILABLE = False
    add_episode = None
    logging.warning("Graphiti integration not available. Entity extraction will be disabled.")

# Import Supabase document storage
try:
    from supabase_client import add_document_to_supabase
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    add_document_to_supabase = None
    logging.warning("Supabase client not available. Vector storage will be disabled.")

# Import embedding function
try:
    from app import get_embedding_ollama
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    get_embedding_ollama = None
    logging.warning("Embedding function not available. Vector embeddings will be disabled.")

logger = logging.getLogger(__name__)


class CrawlJobManager:
    """
    Manager for crawl job lifecycle and persistence.

    Handles creating, updating, and executing crawl jobs with proper
    persistence to Supabase and integration with the CrawlService.
    """

    def __init__(self, supabase_client: Client, max_concurrent_jobs: int = 5):
        """
        Initialize the job manager.

        Args:
            supabase_client: Supabase client for database operations
            max_concurrent_jobs: Maximum number of concurrent crawl jobs
        """
        self.supabase = supabase_client
        self.max_concurrent_jobs = max_concurrent_jobs
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_jobs)
        self._active_jobs: Dict[str, asyncio.Task] = {}
        self._crawl_service: Optional[CrawlService] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()

    async def start(self) -> None:
        """Start the job manager and crawl service."""
        self._crawl_service = CrawlService()
        await self._crawl_service.start()

        # Resume any pending jobs from database
        await self._resume_pending_jobs()

    async def stop(self) -> None:
        """Stop the job manager and cleanup resources."""
        # Cancel all active jobs
        for task in self._active_jobs.values():
            if not task.done():
                task.cancel()

        # Wait for active jobs to complete/cancel
        if self._active_jobs:
            await asyncio.gather(*self._active_jobs.values(), return_exceptions=True)

        # Stop crawl service
        if self._crawl_service:
            await self._crawl_service.stop()

        # Shutdown executor
        self._executor.shutdown(wait=True)

    async def create_job(self, url: str, config: CrawlConfig) -> CrawlJob:
        """
        Create a new crawl job.

        Args:
            url: URL to crawl
            config: Crawling configuration

        Returns:
            Created CrawlJob object
        """
        job = CrawlJob(url=url, config=config)

        # Persist to database
        await self._persist_job(job)

        logger.info(f"Created crawl job {job.id} for URL: {url}")
        return job

    async def get_job(self, job_id: str) -> Optional[CrawlJob]:
        """
        Get a job by ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            CrawlJob object if found, None otherwise
        """
        try:
            response = self.supabase.table("crawl_jobs").select("*").eq("id", job_id).execute()

            if not response.data:
                return None

            job_data = response.data[0]
            return self._job_from_db_row(job_data)

        except Exception as e:
            logger.error(f"Error retrieving job {job_id}: {e}")
            return None

    async def list_jobs(self, status: Optional[CrawlStatus] = None, limit: int = 50) -> List[CrawlJob]:
        """
        List crawl jobs with optional filtering.

        Args:
            status: Filter by job status
            limit: Maximum number of jobs to return

        Returns:
            List of CrawlJob objects
        """
        try:
            query = self.supabase.table("crawl_jobs").select("*").order("created_at", desc=True).limit(limit)

            if status:
                query = query.eq("status", status.value)

            response = query.execute()
            return [self._job_from_db_row(row) for row in response.data]

        except Exception as e:
            logger.error(f"Error listing jobs: {e}")
            return []

    async def start_job(self, job_id: str) -> bool:
        """
        Start execution of a crawl job.

        Args:
            job_id: ID of job to start

        Returns:
            True if job was started successfully, False otherwise
        """
        job = await self.get_job(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found")
            return False

        if job.status != CrawlStatus.PENDING:
            logger.warning(f"Job {job_id} is not in pending status (current: {job.status.value})")
            return False

        # Check concurrent job limit
        if len(self._active_jobs) >= self.max_concurrent_jobs:
            logger.warning(f"Maximum concurrent jobs ({self.max_concurrent_jobs}) reached")
            return False

        # Start the job execution
        task = asyncio.create_task(self._execute_job(job))
        self._active_jobs[job_id] = task

        logger.info(f"Started execution of job {job_id}")
        return True

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running crawl job.

        Args:
            job_id: ID of job to cancel

        Returns:
            True if job was cancelled successfully, False otherwise
        """
        job = await self.get_job(job_id)
        if not job:
            return False

        if job.status not in [CrawlStatus.PENDING, CrawlStatus.RUNNING]:
            return False

        # Cancel the task if it's running
        if job_id in self._active_jobs:
            task = self._active_jobs[job_id]
            if not task.done():
                task.cancel()
            del self._active_jobs[job_id]

        # Update job status
        job.mark_cancelled()
        await self._persist_job(job)

        logger.info(f"Cancelled job {job_id}")
        return True

    async def _execute_job(self, job: CrawlJob) -> None:
        """
        Execute a crawl job.

        Args:
            job: Job to execute
        """
        try:
            # Mark job as running
            job.mark_running()
            await self._persist_job(job)

            # Execute the crawl
            if not self._crawl_service:
                raise RuntimeError("Crawl service not available")

            result = await self._crawl_service.crawl_url(job.url, job.config)

            # Store the result in database
            await self._persist_crawl_result(job.id, result)

            # Mark job as completed
            job.mark_completed(result)
            await self._persist_job(job)

            # Integrate with downstream systems (Graphiti and Supabase)
            await self._integrate_with_downstream(job, result)

            logger.info(f"Completed job {job.id} successfully")

        except asyncio.CancelledError:
            # Job was cancelled
            job.mark_cancelled()
            await self._persist_job(job)
            logger.info(f"Job {job.id} was cancelled")

        except Exception as e:
            # Job failed
            error_message = str(e)
            job.mark_failed(error_message)
            await self._persist_job(job)
            logger.error(f"Job {job.id} failed: {error_message}")

        finally:
            # Remove from active jobs
            self._active_jobs.pop(job.id, None)

    async def _integrate_with_downstream(self, job: CrawlJob, result: CrawlResult) -> None:
        """
        Integrate crawled content with downstream systems (Graphiti and Supabase).

        Args:
            job: The completed crawl job
            result: The crawl result with content
        """
        # Integrate with Supabase vector storage
        await self._integrate_with_supabase(job, result)

        # Integrate with Graphiti for entity extraction
        await self._integrate_with_graphiti(job, result)

    async def _integrate_with_supabase(self, job: CrawlJob, result: CrawlResult) -> None:
        """
        Store crawled content in Supabase vector storage for semantic search.

        Args:
            job: The completed crawl job
            result: The crawl result with content
        """
        if not SUPABASE_AVAILABLE or not add_document_to_supabase or not EMBEDDING_AVAILABLE or not get_embedding_ollama:
            logger.debug("Supabase vector storage not available, skipping")
            return

        try:
            # Generate embedding for the crawled content
            embedding = get_embedding_ollama(result.content)

            # Create metadata for the crawled content
            metadata = {
                "source_url": result.url,
                "crawl_job_id": job.id,
                "title": result.title or "Crawled Content",
                "content_hash": result.content_hash,
                "extracted_at": result.extracted_at.isoformat(),
                "content_size": result.content_size,
            }

            # Store in Supabase vector storage
            add_document_to_supabase(result.content, metadata=metadata, embedding=embedding)

            logger.info(f"Successfully stored crawled content from {result.url} in Supabase vector storage")

        except Exception as e:
            logger.error(f"Error storing content in Supabase: {e}")
            # Don't fail the job if Supabase storage fails

    async def _integrate_with_graphiti(self, job: CrawlJob, result: CrawlResult) -> None:
        """
        Integrate crawled content with Graphiti for entity extraction.

        Args:
            job: The completed crawl job
            result: The crawl result with content
        """
        if not GRAPHITI_AVAILABLE or not add_episode:
            logger.debug("Graphiti not available, skipping entity extraction")
            return

        try:
            # Create a unique episode name based on job ID and URL
            episode_name = f"crawl_{job.id}_{hash(result.url) % 10000}"

            # Use the crawled content for entity extraction
            episode_body = result.content[:10000]  # Limit content size for Graphiti processing

            # Create source description
            source_description = f"Crawled content from {result.url}"

            # Add to Graphiti knowledge graph
            graph_result = await add_episode(
                name=episode_name,
                episode_body=episode_body,
                source_description=source_description,
                reference_time=result.extracted_at
            )

            if graph_result.get("status") == "success":
                logger.info(f"Successfully added crawled content from {result.url} to knowledge graph")
            else:
                logger.warning(f"Failed to add content to Graphiti: {graph_result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Error integrating with Graphiti: {e}")
            # Don't fail the job if Graphiti integration fails

    async def _resume_pending_jobs(self) -> None:
        """Resume any pending or running jobs from the database."""
        try:
            # Get jobs that should be running
            response = self.supabase.table("crawl_jobs").select("*").in_("status", ["pending", "running"]).execute()

            for row in response.data:
                job = self._job_from_db_row(row)

                # Only resume if not already active
                if job.id not in self._active_jobs:
                    if job.status == CrawlStatus.RUNNING:
                        # Job was running when service stopped, restart it
                        await self.start_job(job.id)
                    # Pending jobs stay pending

        except Exception as e:
            logger.error(f"Error resuming pending jobs: {e}")

    async def _persist_job(self, job: CrawlJob) -> None:
        """
        Persist a job to the database.

        Args:
            job: Job to persist
        """
        job_data = {
            "id": job.id,
            "url": job.url,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "config": json.dumps(job.config.to_dict()),
            "result": json.dumps(job.result.to_dict()) if job.result else None,
            "error_message": job.error_message,
        }

        # Upsert the job
        self.supabase.table("crawl_jobs").upsert(job_data).execute()

    async def _persist_crawl_result(self, job_id: str, result: CrawlResult) -> None:
        """
        Persist crawl result content to the database.

        Args:
            job_id: ID of the job that produced the result
            result: Crawl result to persist
        """
        content_data = {
            "id": result.content_hash,  # Use hash as ID for deduplication
            "job_id": job_id,
            "url": result.url,
            "title": result.title,
            "content_hash": result.content_hash,
            "content_size": result.content_size,
            "extracted_at": result.extracted_at.isoformat(),
        }

        # Insert content (ignore if hash already exists due to unique constraint)
        try:
            self.supabase.table("crawl_content").insert(content_data).execute()
        except Exception as e:
            # If it's a duplicate hash, that's fine - content already exists
            if "duplicate key" not in str(e).lower():
                logger.error(f"Error persisting crawl content: {e}")
                raise

    def _job_from_db_row(self, row: dict) -> CrawlJob:
        """
        Convert database row to CrawlJob object.

        Args:
            row: Database row data

        Returns:
            CrawlJob object
        """
        config = CrawlConfig.from_dict(json.loads(row["config"])) if row.get("config") else CrawlConfig()
        result = CrawlResult.from_dict(json.loads(row["result"])) if row.get("result") else None

        return CrawlJob(
            id=row["id"],
            url=row["url"],
            status=CrawlStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row.get("completed_at") else None,
            config=config,
            result=result,
            error_message=row.get("error_message"),
        )