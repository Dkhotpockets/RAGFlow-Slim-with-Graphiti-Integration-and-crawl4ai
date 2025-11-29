# Graphiti integration for Ragflow Slim
# Temporal knowledge graph client for entity and relationship extraction
import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    from graphiti_core import Graphiti
    from graphiti_core.llm_client import OpenAIClient, LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    
    # Try to import GeminiClient
    try:
        from graphiti_core.llm_client.gemini_client import GeminiClient
        GEMINI_AVAILABLE = True
    except ImportError:
        GEMINI_AVAILABLE = False
        GeminiClient = None
    
    # Try to import GeminiRerankerClient
    try:
        from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
        GEMINI_RERANKER_AVAILABLE = True
    except ImportError:
        GEMINI_RERANKER_AVAILABLE = False
        GeminiRerankerClient = None
    
    GRAPHITI_AVAILABLE = True
except ImportError as e:
    GRAPHITI_AVAILABLE = False
    GEMINI_AVAILABLE = False
    GEMINI_RERANKER_AVAILABLE = False
    GeminiClient = None
    GeminiRerankerClient = None
    logging.warning(f"graphiti_core not installed: {e}. Graph features will be disabled.")

try:
    from llm_provider import llm_config
    LLM_CONFIG_AVAILABLE = True
except ImportError:
    LLM_CONFIG_AVAILABLE = False
    logging.warning("llm_provider not available. Using default OpenAI configuration.")

# Neo4j connection settings
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "graphiti_password")

# Global Graphiti instance (initialized lazily)
_graphiti_instance: Optional[Any] = None


def get_graphiti_client() -> Optional[Any]:
    """Get or create the global Graphiti client instance with multi-provider LLM support."""
    logging.debug("get_graphiti_client() called")
    global _graphiti_instance
    
    if _graphiti_instance is not None:
        return _graphiti_instance
    
    if not GRAPHITI_AVAILABLE:
        logging.error("Graphiti is not available. Install graphiti-core package.")
        return None
    
    try:
        # Get LLM configuration
        if LLM_CONFIG_AVAILABLE:
            provider_config = llm_config.get_graphiti_llm_config()
            logging.info(f"Initializing Graphiti with {llm_config.provider} provider")
            
            # Create LLM client based on provider
            llm_client = None
            embedder_client = None
            reranker_client = None
            
            if llm_config.provider == "ollama":
                # Ollama has compatibility issues with Graphiti's structured outputs
                # Use OpenAI for LLM (required for entity extraction) and Ollama for embeddings
                logging.warning("Graphiti requires OpenAI's structured outputs for entity extraction.")
                logging.info("Using OpenAI for LLM client and Ollama for embedder to minimize costs.")

                # Check if OpenAI key is available
                openai_key = os.getenv("OPENAI_API_KEY")
                logging.info(f"OpenAI key present: {bool(openai_key)}")
                if not openai_key:
                    logging.error("OpenAI API key required for Graphiti LLM client")
                    llm_client = None
                else:
                    llm_client_config = LLMConfig(
                        api_key=openai_key,
                        model="gpt-4o-mini"  # Use cost-effective model that supports structured outputs
                    )
                    llm_client = OpenAIClient(config=llm_client_config)
                
                # Configure Ollama embedder with OpenAI-compatible API endpoint
                embedder_config = OpenAIEmbedderConfig(
                    api_key="ollama",  # Dummy key for Ollama
                    base_url="http://host.docker.internal:11434/v1",  # OpenAI-compatible API endpoint
                    embedding_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
                )
                embedder_client = OpenAIEmbedder(config=embedder_config)
                
            elif llm_config.provider == "google":
                # Use Google Gemini for LLM client
                logging.info("Using Google Gemini for entity extraction and reranking")

                llm_client = None
                reranker_client = None

                if not GEMINI_AVAILABLE or GeminiClient is None:
                    logging.error("GeminiClient not available. Try: pip install graphiti-core[google-genai]")
                else:
                    google_key = os.getenv("GOOGLE_API_KEY")
                    if not google_key:
                        logging.error("Google API key required for Gemini LLM client")
                    else:
                        try:
                            llm_client_config = LLMConfig(
                                api_key=google_key,
                                model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")  # Cost-effective Gemini model
                            )
                            llm_client = GeminiClient(config=llm_client_config)
                            logging.info("Gemini client initialized successfully")
                        except Exception as e:
                            logging.error(f"Failed to initialize Gemini client: {e}")
                
                # Initialize GeminiRerankerClient for cross-encoding
                if GEMINI_RERANKER_AVAILABLE and GeminiRerankerClient is not None:
                    google_key = os.getenv("GOOGLE_API_KEY")
                    if google_key:
                        try:
                            reranker_config = LLMConfig(
                                api_key=google_key,
                                model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
                            )
                            reranker_client = GeminiRerankerClient(config=reranker_config)
                            logging.info("Gemini reranker client initialized successfully")
                        except Exception as e:
                            logging.warning(f"Failed to initialize Gemini reranker client: {e}")
                            reranker_client = None
                else:
                    logging.warning("GeminiRerankerClient not available, falling back to default reranker")
                
                # Use Ollama for embeddings (optional, can use Google embeddings too)
                embedder_config = OpenAIEmbedderConfig(
                    api_key="ollama",
                    base_url="http://host.docker.internal:11434/v1",
                    embedding_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
                )
                embedder_client = OpenAIEmbedder(config=embedder_config)
                
            elif llm_config.provider == "openai":
                llm_client_config = LLMConfig(
                    api_key=provider_config["llm_config"]["api_key"],
                    model=provider_config["llm_config"]["model"]
                )
                llm_client = OpenAIClient(config=llm_client_config)
                
                # Use default OpenAI embedder for OpenAI
                embedder_config = OpenAIEmbedderConfig(
                    api_key=provider_config["llm_config"]["api_key"]
                )
                embedder_client = OpenAIEmbedder(config=embedder_config)
            
            # Initialize Graphiti with custom LLM client, embedder, and reranker
            graphiti_kwargs = {
                "uri": NEO4J_URI,
                "user": NEO4J_USER,
                "password": NEO4J_PASSWORD,
                "llm_client": llm_client,
                "embedder": embedder_client
            }
            # Add reranker if available
            if reranker_client is not None:
                graphiti_kwargs["cross_encoder"] = reranker_client
            
            _graphiti_instance = Graphiti(**graphiti_kwargs)
        else:
            # Fallback to default OpenAI configuration
            logging.warning("Using default OpenAI configuration")
            _graphiti_instance = Graphiti(
                uri=NEO4J_URI,
                user=NEO4J_USER,
                password=NEO4J_PASSWORD
            )

        logging.info(f"Graphiti client initialized with Neo4j at {NEO4J_URI}")

        # Note: Database schema will be initialized on first episode addition
    except Exception as e:
        logging.error(f"Failed to initialize Graphiti client: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return None
    
    return _graphiti_instance


async def add_episode_async(
    name: str,
    episode_body: str,
    source_description: str,
    reference_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Add an episode (document/event) to the temporal knowledge graph.
    
    Args:
        name: Unique name/identifier for the episode
        episode_body: The actual text content to extract entities/relationships from
        source_description: Description of the source (e.g., "PDF document from finance team")
        reference_time: Timestamp for temporal tracking (defaults to now)
    
    Returns:
        Dict with status and episode details
    """
    client = get_graphiti_client()
    if not client:
        return {"error": "Graphiti client not available"}
    
    try:
        # Initialize database schema on first use (idempotent operation)
        logging.info("Attempting to initialize Graphiti database schema...")
        try:
            await client.build_indices_and_constraints()
            logging.info("Graphiti database schema initialized")
        except Exception as schema_e:
            logging.warning(f"Schema initialization failed (may already exist): {schema_e}")
        
        # Add episode to graph
        await client.add_episode(
            name=name,
            episode_body=episode_body,
            source_description=source_description,
            reference_time=reference_time or datetime.now()
        )
        
        logging.info(f"Added episode '{name}' to knowledge graph")
        return {
            "status": "success",
            "episode_name": name,
            "timestamp": (reference_time or datetime.now()).isoformat()
        }
    except Exception as e:
        logging.error(f"Failed to add episode to Graphiti: {e}")
        return {"error": str(e)}


def add_episode(
    name: str,
    episode_body: str,
    source_description: str,
    reference_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Synchronous wrapper for add_episode_async."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            add_episode_async(name, episode_body, source_description, reference_time)
        )
        return result
    finally:
        loop.close()


async def search_graph_async(
    query: str,
    num_results: int = 10,
    center_node_uuid: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search the temporal knowledge graph.
    
    Args:
        query: Natural language query
        num_results: Maximum number of results to return
        center_node_uuid: Optional UUID to center search around specific node
    
    Returns:
        List of relevant entities and relationships from the graph
    """
    client = get_graphiti_client()
    if not client:
        return [{"error": "Graphiti client not available"}]
    
    try:
        results = await client.search(
            query=query,
            num_results=num_results,
            center_node_uuid=center_node_uuid
        )
        
        logging.info(f"Graph search for '{query}' returned {len(results)} results")
        return results
    except Exception as e:
        logging.error(f"Graph search failed: {e}")
        return [{"error": str(e)}]


def search_graph(
    query: str,
    num_results: int = 10,
    center_node_uuid: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for search_graph_async."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(
            search_graph_async(query, num_results, center_node_uuid)
        )
        return results
    finally:
        loop.close()


async def get_temporal_context_async(
    entity_name: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get temporal context for an entity within a time range.
    
    Args:
        entity_name: Name of the entity to track
        start_time: Start of time range (optional)
        end_time: End of time range (optional)
    
    Returns:
        Dict with entity history and relationships over time
    """
    client = get_graphiti_client()
    if not client:
        return {"error": "Graphiti client not available"}
    
    try:
        # Search for the entity
        search_results = await client.search(
            query=entity_name,
            num_results=5
        )
        
        # Build temporal context
        context = {
            "entity": entity_name,
            "time_range": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None
            },
            "results": search_results
        }
        
        logging.info(f"Retrieved temporal context for entity '{entity_name}'")
        return context
    except Exception as e:
        logging.error(f"Failed to get temporal context: {e}")
        return {"error": str(e)}


def get_temporal_context(
    entity_name: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """Synchronous wrapper for get_temporal_context_async."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            get_temporal_context_async(entity_name, start_time, end_time)
        )
        return result
    finally:
        loop.close()


def close_graphiti_client():
    """Close the Graphiti client connection."""
    global _graphiti_instance
    if _graphiti_instance:
        try:
            # Graphiti cleanup if needed
            _graphiti_instance = None
            logging.info("Graphiti client closed")
        except Exception as e:
            logging.error(f"Error closing Graphiti client: {e}")
