"""
Multi-provider LLM configuration for RAGFlow Slim
Supports: OpenAI, Google AI (Gemini), Ollama
"""
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LLMConfig:
    """Centralized LLM provider configuration."""
    
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "auto")  # auto, openai, google, ollama
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
        
        # Model configurations
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.google_model = os.getenv("GOOGLE_MODEL", "gemini-1.5-flash")
        
        # Auto-detect if provider is set to "auto"
        if self.provider == "auto":
            self.provider = self._detect_provider()
    
    def _detect_provider(self) -> str:
        """Auto-detect which LLM provider to use based on available credentials."""
        # Priority order: Ollama (local) > Google AI > OpenAI
        
        # Check Ollama (local, no auth needed)
        try:
            import requests
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=2)
            if response.status_code == 200:
                logger.info("✅ Detected Ollama running locally")
                return "ollama"
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
        
        # Check Google AI
        if self.google_api_key:
            logger.info("✅ Detected Google API key")
            return "google"
        
        # Check OpenAI
        if self.openai_api_key:
            logger.info("✅ Detected OpenAI API key")
            return "openai"
        
        # Default to Ollama with warning
        logger.warning("⚠️  No LLM provider detected. Defaulting to Ollama. Install Ollama or set API keys.")
        return "ollama"
    
    def get_graphiti_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration for Graphiti."""
        if self.provider == "ollama":
            return {
                "llm_provider": "ollama",
                "llm_config": {
                    "base_url": self.ollama_host,
                    "model": self.ollama_model
                }
            }
        elif self.provider == "google":
            return {
                "llm_provider": "google",
                "llm_config": {
                    "api_key": self.google_api_key,
                    "model": self.google_model
                }
            }
        elif self.provider == "openai":
            return {
                "llm_provider": "openai",
                "llm_config": {
                    "api_key": self.openai_api_key,
                    "model": self.openai_model
                }
            }
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")
    
    def get_embeddings_config(self) -> Dict[str, Any]:
        """Get embeddings configuration."""
        # For embeddings, prefer order: Ollama > OpenAI > Google
        if self.provider == "ollama":
            return {
                "provider": "ollama",
                "base_url": self.ollama_host,
                "model": os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
            }
        elif self.provider == "openai" or self.openai_api_key:
            return {
                "provider": "openai",
                "api_key": self.openai_api_key,
                "model": "text-embedding-3-small"
            }
        elif self.provider == "google":
            return {
                "provider": "google",
                "api_key": self.google_api_key,
                "model": "text-embedding-004"
            }
        else:
            raise ValueError("No embeddings provider available")
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get current provider information for logging/debugging."""
        return {
            "provider": self.provider,
            "llm_model": self._get_current_model(),
            "embeddings_model": self._get_current_embed_model(),
            "ollama_host": self.ollama_host if self.provider == "ollama" else None
        }
    
    def _get_current_model(self) -> str:
        """Get the current LLM model name."""
        if self.provider == "ollama":
            return self.ollama_model
        elif self.provider == "google":
            return self.google_model
        elif self.provider == "openai":
            return self.openai_model
        return "unknown"
    
    def _get_current_embed_model(self) -> str:
        """Get the current embeddings model name."""
        if self.provider == "ollama":
            return os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        elif self.provider == "openai" or self.openai_api_key:
            return "text-embedding-3-small"
        elif self.provider == "google":
            return "text-embedding-004"
        return "unknown"


# Global configuration instance
llm_config = LLMConfig()

# Log the detected provider at startup
logger.info(f"🤖 LLM Provider: {llm_config.provider}")
logger.info(f"📊 Config: {llm_config.get_provider_info()}")
