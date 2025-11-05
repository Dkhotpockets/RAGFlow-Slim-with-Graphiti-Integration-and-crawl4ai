# RAGFlow Slim Integration Guide

## Overview

RAGFlow Slim is a **microservice component** designed to be integrated into larger applications. It provides:
- Vector search capabilities (via Supabase)
- Knowledge graph extraction (via Graphiti + Neo4j)
- Web crawling (via Crawl4AI)
- Multi-provider LLM support

## Integration Patterns

### Pattern 1: Microservice (Recommended)

Run RAGFlow Slim as a separate service that your main application calls via REST API.

```
Your Application
    ↓ (HTTP/REST)
RAGFlow Slim Service (port 5000)
    ├→ Your Supabase Instance
    ├→ Neo4j (for knowledge graph)
    └→ LLM Providers
```

**Advantages**:
- Independent scaling
- Language-agnostic integration
- Easy to update/deploy separately

### Pattern 2: Library Import

Import RAGFlow Slim modules directly into your Python application.

```python
from ragflow_slim.graphiti_client import search_graph, add_episode
from ragflow_slim.supabase_client import search_documents_supabase
from ragflow_slim.llm_provider import llm_config
```

**Advantages**:
- Lower latency (no HTTP overhead)
- Direct access to functionality
- Shared resources

## Microservice Integration

### 1. Configuration for Integration

Since your main app already has Supabase, configure RAGFlow Slim to use the same instance:

**.env** (in RAGFlow Slim):
```bash
# Use your existing Supabase instance
SUPABASE_URL=${YOUR_APP_SUPABASE_URL}
SUPABASE_KEY=${YOUR_APP_SUPABASE_SERVICE_KEY}

# RAGFlow-specific services
NEO4J_URI=bolt://ragflow-neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=${STRONG_PASSWORD}

# LLM Provider (shared or separate)
GOOGLE_API_KEY=${YOUR_APP_GOOGLE_KEY}  # or use separate key

# RAGFlow API authentication
RAGFLOW_API_KEY=${STRONG_API_KEY}
```

### 2. Supabase Schema Setup

RAGFlow Slim needs these tables in your Supabase database:

```sql
-- Option 1: Use a separate schema for RAGFlow
CREATE SCHEMA IF NOT EXISTS ragflow;

-- Create tables in ragflow schema
CREATE TABLE IF NOT EXISTS ragflow.documents (
  id BIGSERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  embedding vector(1536),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- OR Option 2: Use a prefix in the default schema
CREATE TABLE IF NOT EXISTS ragflow_documents (
  -- same structure as above
);
```

**Recommended**: Use a separate schema to avoid conflicts with your app's tables.

### 3. Docker Compose Integration

Add RAGFlow Slim services to your existing `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # Your existing application services...
  your-app:
    # ... your app config
    environment:
      - RAGFLOW_URL=http://ragflow-server:5000
      - RAGFLOW_API_KEY=${RAGFLOW_API_KEY}

  # RAGFlow Slim services
  ragflow-server:
    build: ./ragflow-slim
    container_name: ragflow-server
    ports:
      - "5000:5000"  # or internal only if behind API gateway
    environment:
      # Point to your Supabase
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_KEY=${SUPABASE_KEY}
      # RAGFlow-specific services
      - NEO4J_URI=bolt://ragflow-neo4j:7687
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - RAGFLOW_API_KEY=${RAGFLOW_API_KEY}
    depends_on:
      - ragflow-neo4j

  ragflow-neo4j:
    image: neo4j:5.18.0
    container_name: ragflow-neo4j
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
      - NEO4J_PLUGINS=["apoc", "graph-data-science"]
    volumes:
      - ragflow-neo4j-data:/data

volumes:
  ragflow-neo4j-data:
```

### 4. API Integration from Your Application

#### Example: Node.js/TypeScript

```typescript
// services/ragflow.service.ts
import axios from 'axios';

export class RAGFlowService {
  private baseUrl: string;
  private apiKey: string;

  constructor() {
    this.baseUrl = process.env.RAGFLOW_URL || 'http://localhost:5000';
    this.apiKey = process.env.RAGFLOW_API_KEY || '';
  }

  async ingestDocument(file: File, metadata?: Record<string, any>) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await axios.post(`${this.baseUrl}/ingest`, formData, {
      headers: {
        'X-API-KEY': this.apiKey,
        'Content-Type': 'multipart/form-data',
      },
    });

    return response.data;
  }

  async searchDocuments(query: string, topK: number = 5) {
    const response = await axios.post(
      `${this.baseUrl}/retrieval`,
      { query, top_k: topK },
      {
        headers: {
          'X-API-KEY': this.apiKey,
          'Content-Type': 'application/json',
        },
      }
    );

    return response.data;
  }

  async searchGraph(query: string, numResults: number = 10) {
    const response = await axios.post(
      `${this.baseUrl}/graph/search`,
      { query, num_results: numResults },
      {
        headers: {
          'X-API-KEY': this.apiKey,
          'Content-Type': 'application/json',
        },
      }
    );

    return response.data;
  }

  async crawlWebsite(url: string) {
    const response = await axios.post(
      `${this.baseUrl}/crawl`,
      { url },
      {
        headers: {
          'X-API-KEY': this.apiKey,
          'Content-Type': 'application/json',
        },
      }
    );

    return response.data;
  }
}
```

#### Example: Python

```python
# services/ragflow_client.py
import requests
from typing import Optional, Dict, List

class RAGFlowClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-API-KEY': api_key,
            'Content-Type': 'application/json'
        }

    def ingest_document(self, file_path: str, metadata: Optional[Dict] = None):
        with open(file_path, 'rb') as f:
            files = {'file': f}
            headers = {'X-API-KEY': self.api_key}
            response = requests.post(
                f'{self.base_url}/ingest',
                files=files,
                headers=headers
            )
            response.raise_for_status()
            return response.json()

    def search_documents(self, query: str, top_k: int = 5):
        response = requests.post(
            f'{self.base_url}/retrieval',
            json={'query': query, 'top_k': top_k},
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def search_graph(self, query: str, num_results: int = 10):
        response = requests.post(
            f'{self.base_url}/graph/search',
            json={'query': query, 'num_results': num_results},
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
```

### 5. Shared Resource Considerations

#### Supabase Connection Pooling
Since both your app and RAGFlow Slim connect to the same Supabase instance:

```python
# In your .env, consider connection limits
# Supabase free tier: 60 connections max
# Your app: ~20 connections
# RAGFlow: ~10 connections
# Leave headroom: ~30 connections
```

#### Rate Limiting
Configure RAGFlow Slim to respect your overall API rate limits:

```python
# In app.py, adjust rate limits based on your app's usage
RATE_LIMIT = int(os.getenv("RAGFLOW_RATE_LIMIT", "100"))  # per hour per IP
```

### 6. Authentication & Authorization

#### Option 1: Service-to-Service Authentication
Your app authenticates to RAGFlow with a service API key:

```bash
# In your app's .env
RAGFLOW_API_KEY=<strong-service-key>
```

#### Option 2: Pass-through Authentication
Forward user authentication from your app to RAGFlow:

```python
# In your app
headers = {
    'X-API-KEY': RAGFLOW_SERVICE_KEY,
    'X-USER-ID': current_user.id,  # Forward user context
}
```

Then in RAGFlow's `app.py`, you can access:
```python
user_id = request.headers.get("X-USER-ID")
```

### 7. Monitoring & Logging

#### Centralized Logging
Configure RAGFlow to log to your app's logging system:

```yaml
# docker-compose.yml
ragflow-server:
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"
      labels: "service=ragflow"
```

#### Health Checks
Monitor RAGFlow health from your app:

```typescript
// health-check.service.ts
async checkRAGFlowHealth() {
  try {
    const response = await axios.get(`${this.ragflowUrl}/health`);
    return {
      status: 'healthy',
      details: response.data
    };
  } catch (error) {
    return {
      status: 'unhealthy',
      error: error.message
    };
  }
}
```

## Library Import Integration

If you prefer to import RAGFlow Slim directly into your Python application:

### 1. Install as Package

```bash
# In your app's directory
pip install -e ../ragflow-slim
```

### 2. Import and Use

```python
# your_app/services/knowledge_service.py
from graphiti_client import search_graph, add_episode
from supabase_client import search_documents_supabase
import os

# Configure environment variables
os.environ['NEO4J_URI'] = 'bolt://localhost:7687'
os.environ['NEO4J_PASSWORD'] = 'your-password'

class KnowledgeService:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def search_knowledge(self, query: str):
        # Use your existing Supabase client
        vector_results = search_documents_supabase(query_embedding, top_k=5)

        # Use RAGFlow's graph search
        graph_results = search_graph(query, num_results=5)

        return {
            'vector': vector_results,
            'graph': graph_results
        }
```

## Best Practices for Integration

### 1. Environment Isolation
Keep RAGFlow's configuration separate:

```
your-app/
  .env              # Your app's config
  docker-compose.yml
  services/
    ragflow-slim/   # RAGFlow as submodule or separate service
      .env          # RAGFlow-specific config
      docker-compose.yml
```

### 2. API Versioning
If RAGFlow Slim API changes, version the endpoints:

```python
# In app.py
@app.route("/api/v1/retrieval", methods=["POST"])
def retrieval_v1():
    # current implementation

@app.route("/api/v2/retrieval", methods=["POST"])
def retrieval_v2():
    # future enhanced implementation
```

### 3. Error Handling
Gracefully handle RAGFlow service failures:

```typescript
async function searchWithRAGFlow(query: string) {
  try {
    return await ragflowService.searchDocuments(query);
  } catch (error) {
    logger.error('RAGFlow search failed', error);
    // Fallback to direct Supabase search
    return await supabaseService.search(query);
  }
}
```

### 4. Caching
Cache RAGFlow responses to reduce load:

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def cached_graph_search(query: str, num_results: int):
    return search_graph(query, num_results)
```

## Minimal Configuration

For a quick integration, you only need:

1. **Share Supabase credentials** (your app → RAGFlow)
2. **Run Neo4j container** (for RAGFlow's knowledge graph)
3. **Set RAGFLOW_API_KEY** (for authentication)
4. **Configure LLM provider** (Google/OpenAI/Ollama)

That's it! RAGFlow Slim will use your existing Supabase and add knowledge graph capabilities.

## Example: Next.js App Integration

```typescript
// app/api/search/route.ts
import { RAGFlowService } from '@/services/ragflow';

export async function POST(request: Request) {
  const { query } = await request.json();

  const ragflow = new RAGFlowService();

  // Get hybrid results from RAGFlow
  const results = await ragflow.searchDocuments(query);

  return Response.json({
    vectorResults: results.vector_results,
    graphResults: results.graph_results,
  });
}
```

## Troubleshooting

### Issue: RAGFlow can't connect to Supabase
**Solution**: Ensure RAGFlow container can reach Supabase. If using Docker networks:

```yaml
networks:
  shared-network:
    external: true

services:
  ragflow-server:
    networks:
      - shared-network
```

### Issue: Duplicate Supabase tables
**Solution**: Use schema isolation (see "Supabase Schema Setup" above)

### Issue: Neo4j out of memory
**Solution**: Adjust memory limits based on your data size:

```yaml
ragflow-neo4j:
  environment:
    - NEO4J_dbms_memory_heap_max__size=4G  # Increase from 2G
```

## Support

## 🔒 Secret Management & Best Practices

### Environment Variables & .env Usage
- **Never commit real credentials**: Always use `.env.example` as a template. Real secrets go in your local `.env`, which is gitignored.
- **.env is in .gitignore**: The project `.gitignore` ensures `.env`, `.env.local`, and all environment-specific files are never committed.
- **Regenerate credentials if exposed**: If secrets are ever committed, immediately rotate them and follow the removal steps in `SECURITY_FIXES.md`.
- **Use strong, unique values**: Generate API keys and passwords using the provided Python commands in `SECURITY_SETUP.md`.
- **Rotate credentials regularly**: Change all secrets every 90 days or if compromise is suspected.

### Contributor Checklist (Preventing Secret Exposure)
- [ ] Never commit `.env` or real credentials
- [ ] Use `.env.example` for templates only
- [ ] Confirm `.env` is in `.gitignore` before pushing
- [ ] Rotate and update credentials after onboarding/offboarding
- [ ] Review `SECURITY_SETUP.md` and `SECURITY_FIXES.md` before contributing
- [ ] Use pre-commit hooks or secret scanning tools (e.g., [git-secrets](https://github.com/awslabs/git-secrets))

### Further Reading
- [SECURITY_SETUP.md](SECURITY_SETUP.md): Full security setup and credential management
- [SECURITY_FIXES.md](SECURITY_FIXES.md): Incident response and credential rotation
- [REVIEW_SUMMARY.md](REVIEW_SUMMARY.md): Security review and validation

**Following these practices is mandatory for all contributors.**

For integration questions, see:
- **CLAUDE.md** - AI assistant guide
- **README.md** - General overview
- **SECURITY_SETUP.md** - Security configuration

---

**Integration Pattern**: Microservice
**Deployment Model**: Docker Compose
**Shared Resources**: Supabase (from your app)
**Dedicated Resources**: Neo4j (for knowledge graph)
