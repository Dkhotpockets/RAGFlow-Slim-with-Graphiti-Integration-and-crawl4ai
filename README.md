# RAGFlow Slim with Graphiti and Crawl4AI Integration

A lightweight, hybrid RAG (Retrieval-Augmented Generation) **microservice component** that adds:
- **Knowledge graph extraction** (temporal entity/relationship tracking)
- **Web crawling** (intelligent content extraction)
- **Multi-provider LLM support** (Google Gemini, OpenAI, Ollama)

**Designed to integrate with your existing application** - works with your Supabase instance and adds advanced RAG capabilities.

## 🎯 Overview

RAGFlow Slim is a **microservice component** designed to enhance your existing application with advanced RAG capabilities. It integrates seamlessly with your Supabase instance and provides:

- **Knowledge Graph**: Entity extraction, relationship mapping, and temporal tracking using Neo4j + Graphiti
- **Web Crawling**: Intelligent web scraping and content extraction using Crawl4AI
- **Vector Search**: Works with your existing Supabase instance for semantic search
- **Multi-Provider LLM Support**: Google Gemini, OpenAI, Ollama with auto-detection
- **RESTful API**: Clean endpoints for easy integration into any application

## 🔌 Integration Patterns

### Option 1: Microservice (Recommended)
Run RAGFlow Slim as a separate service and call it from your application via REST API.

```
Your Application → RAGFlow Slim API → Your Supabase + Neo4j
```

### Option 2: Direct Import
Import RAGFlow modules directly into your Python application for lower latency.

```python
from graphiti_client import search_graph, add_episode
from supabase_client import search_documents_supabase
```

**See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for detailed integration instructions.**

## 🚀 Quick Start for Integration

### Prerequisites

- Your application with Supabase already configured
- Docker and Docker Compose
- Python 3.11+ (for local development)
- API key for your preferred LLM provider (Google Gemini recommended)

### Integration Setup

1. **Add RAGFlow Slim to your project**

   ```bash
   # Option 1: As a Git submodule
   git submodule add https://github.com/Dkhotpockets/RAGFlow-Slim-with-Graphiti-Integration.git ragflow-slim

   # Option 2: Clone into services directory
   git clone https://github.com/Dkhotpockets/RAGFlow-Slim-with-Graphiti-Integration.git services/ragflow-slim
   ```

2. **Configure to use your Supabase**

   ```bash
   cd ragflow-slim
   cp .env.example .env
   ```

   Edit `.env`:
   ```bash
   # Use YOUR existing Supabase instance
   SUPABASE_URL=<your-app-supabase-url>
   SUPABASE_KEY=<your-app-supabase-service-key>

   # RAGFlow-specific configuration
   NEO4J_PASSWORD=<strong-password>
   GOOGLE_API_KEY=<your-google-api-key>
   RAGFLOW_API_KEY=<generate-strong-key>
   ```

3. **Run the Supabase setup** (one-time)

   Execute these SQL files in your Supabase SQL Editor:
   - `setup_supabase.sql` - Creates the necessary tables and functions
   - `supabase_enable_rls.sql` - Enables Row Level Security (required for production)

4. **Start RAGFlow services**

   ```bash
   docker-compose up -d
   ```

5. **Verify integration**

   ```bash
   curl http://localhost:5000/health
   ```

6. **Call from your application**

   ```typescript
   // In your app
   const response = await fetch('http://ragflow-server:5000/retrieval', {
     method: 'POST',
     headers: {
       'X-API-KEY': process.env.RAGFLOW_API_KEY,
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({ query: 'your search query' })
   });
   ```

**See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for complete integration instructions and code examples.**

### Local Development

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables**

   ```bash
   export SUPABASE_URL="your-supabase-url"
   export SUPABASE_KEY="your-supabase-key"
   export GOOGLE_API_KEY="your-google-api-key"
   # ... other required variables
   ```

3. **Run the application**

   ```bash
   python app.py
   ```

## 🏗️ Architecture

```text
Documents
    ↓
RAGFlow Slim with Graphiti Integration API
    ├─→ Supabase (Vector Store)
    │   └─→ Fast similarity search
    │
    └─→ Neo4j + Graphiti (Graph Store)
        └─→ Entity extraction, relationship mapping, temporal tracking
```

### Services

- **ragflow-server**: Main Flask API server
- **ragflow-mysql**: MySQL database for metadata
- **ragflow-redis**: Redis for caching
- **ragflow-minio**: MinIO for file storage
- **ragflow-es-01**: Elasticsearch for search indexing
- **ragflow-neo4j**: Neo4j graph database for knowledge graph

## 📡 API Endpoints

### Core Endpoints

- `GET /health` - Health check
- `GET /config` - List configuration files
- `POST /completion` - Generate text completions
- `POST /ingest` - Ingest documents (extracts entities and relationships)
- `POST /retrieval` - Retrieve documents (combines vector and graph results)

### Graph Endpoints

- `POST /graph/search` - Search the knowledge graph for entities/relationships
- `POST /graph/temporal` - Track how entities evolved over time

### Example Usage

```python
import requests

# Health check
response = requests.get("http://localhost:5000/health")
print(response.json())

# Ingest a document
data = {
    "content": "Your document content here...",
    "metadata": {"source": "example.txt"}
}
response = requests.post("http://localhost:5000/ingest", json=data)

# Retrieve documents
query = {"query": "What is machine learning?"}
response = requests.post("http://localhost:5000/retrieval", json=query)
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_KEY` | Supabase service role key | Yes |
| `NEO4J_URI` | Neo4j connection URI | Yes |
| `NEO4J_USER` | Neo4j username | Yes |
| `NEO4J_PASSWORD` | Neo4j password | Yes |
| `GOOGLE_API_KEY` | Google Gemini API key | For Gemini provider |
| `OLLAMA_HOST` | Ollama server URL | For Ollama provider |

### LLM Providers

The system supports multiple LLM providers:

- **Google Gemini**: Primary for entity extraction and general completions
- **Ollama**: Local LLM support for embeddings and completions
- **OpenAI**: Compatible with OpenAI API format

Configure the provider using `LLM_PROVIDER` environment variable.

## 🔧 Development

### Project Structure

```text
├── app.py                 # Main Flask application
├── graphiti_client.py     # Graphiti integration
├── supabase_client.py     # Supabase vector operations
├── llm_provider.py        # Multi-provider LLM client
├── crawl4ai_source/       # Crawl4AI crawling service
├── docker-compose.yml     # Service orchestration
├── requirements.txt       # Python dependencies
├── graphiti_source/       # Graphiti library
├── docker/               # Docker configuration
└── docs/                 # Documentation
```

### Testing

Run the test suite:

```bash
python -m pytest test_*.py
```

### Running contract/integration tests (CI)

Contract and integration tests that hit external services (Graphiti, Supabase,
LLM providers) are run conditionally in CI.

- Locally: run all tests including contract-marked ones:

```powershell
# Run contract/integration tests locally
pytest -q -m contract
```

- On GitHub Actions: trigger the `CI` workflow with `workflow_dispatch` and set
   the `run_contracts` input to `true` when you want the contract suite.

This avoids running long or environment-dependent tests on every push while
allowing a dedicated contract test run when desired.


### Adding New Features

1. Create a feature branch
2. Add tests for new functionality
3. Update documentation
4. Submit a pull request

## 📚 Documentation

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

- [Graphiti Integration Guide](GRAPHITI_INTEGRATION.md)
- [Graphiti Quick Start](GRAPHITI_QUICKSTART.md)
- [LLM Provider Setup](LLM_PROVIDER_GUIDE.md)
- [Migration Guide](MIGRATION_GUIDE.md)
- [Ollama Integration](OLLAMA_GUIDE.md)
- [Contributor Guide](CONTRIBUTOR_GUIDE.md)

## 🤝 Contributing

We welcome contributions!
See the [Contributor Guide](CONTRIBUTOR_GUIDE.md) for details on:

- Setting up a development environment
- Code standards and practices
- Submitting pull requests
- Reporting issues

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [RAGFlow](https://github.com/infiniflow/ragflow) - Original RAG system
- [Graphiti](https://github.com/getzep/graphiti) - Temporal knowledge graph library
- [Supabase](https://supabase.com) - Vector database and backend services
- [Neo4j](https://neo4j.com) - Graph database
