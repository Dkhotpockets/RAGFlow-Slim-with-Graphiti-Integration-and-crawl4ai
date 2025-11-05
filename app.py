from flask import Flask, request, jsonify
from flask_cors import CORS
import os, datetime, json, logging, asyncio
from werkzeug.exceptions import BadRequest


# Contributor Onboarding Notes:
# - All input/output operations are sanitized and path-safe
# - Document ingestion and retrieval logic is modular and ready for extension
import uuid
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None
from supabase_client import add_document_to_supabase, search_documents_supabase
from graphiti_client import (
    add_episode, 
    search_graph, 
    get_temporal_context,
    GRAPHITI_AVAILABLE
)
from crawl4ai_source import (
    CrawlJobManager,
    CrawlJobRequest,
    CrawlJobResponse,
    CrawlStatus
)
# - Output folder is consistent for audit and onboarding
# - Logging is enabled for production safety

app = Flask(__name__)

# Security: Restrict CORS to specific origins
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
CORS(app, resources={
    r"/*": {
        "origins": ALLOWED_ORIGINS,
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type", "X-API-KEY"]
    }
})

# Security: Set maximum upload size (50MB)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

OUTPUT_DIR = os.path.join(os.getcwd(), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize CrawlJobManager with Supabase client
from supabase_client import supabase as supabase_client
crawl_manager = CrawlJobManager(supabase_client)

# Configuration directory for bootstrap files (can be mounted as a Docker volume)
# Default is /data/application but can be overridden with the RAGFLOW_CONFIG_DIR env var.
CONFIG_DIR = os.getenv("RAGFLOW_CONFIG_DIR", "/data/application")

def _is_safe_path(base_dir: str, path: str) -> bool:
    """Ensure the resolved path is inside base_dir to avoid directory traversal."""
    try:
        base = os.path.abspath(base_dir)
        target = os.path.abspath(path)
        return os.path.commonpath([base]) == os.path.commonpath([base, target])
    except Exception:
        return False

def list_config_files(app_name: str | None = None) -> list:
    """List config files in CONFIG_DIR.

    If app_name is provided, prefer files in a subdirectory named after the app
    (e.g., /data/application/myapp/). Otherwise, return all files at top level.
    Returns a list of absolute paths.
    """
    files = []
    try:
        base = os.path.abspath(CONFIG_DIR)
        if not os.path.isdir(base):
            return []
        # If app-specific dir exists, prefer it
        if app_name:
            safe_app = os.path.basename(app_name)
            app_dir = os.path.join(base, safe_app)
            if os.path.isdir(app_dir):
                for entry in os.listdir(app_dir):
                    p = os.path.join(app_dir, entry)
                    if os.path.isfile(p) and _is_safe_path(base, p):
                        files.append(p)
                return sorted(files)
        # Fallback: top-level files
        for entry in os.listdir(base):
            p = os.path.join(base, entry)
            if os.path.isfile(p) and _is_safe_path(base, p):
                files.append(p)
        return sorted(files)
    except Exception as e:
        logging.error(f"Error listing config files: {e}")
        return []

def load_config_file(filename: str | None = None, app_name: str | None = None) -> dict:
    """Load one or more config files from CONFIG_DIR.

    If filename is provided, attempt to find that exact file (either in app subdir
    or top-level). If not provided, return a mapping of filename->content for all
    files found for the app (or top-level files).

    Returns a dict {relative_filename: content}.
    """
    base = os.path.abspath(CONFIG_DIR)
    if not os.path.isdir(base):
        return {}
    results = {}
    candidates = []
    try:
        # Build candidate list
        if app_name:
            safe_app = os.path.basename(app_name)
            app_dir = os.path.join(base, safe_app)
            if os.path.isdir(app_dir):
                for entry in os.listdir(app_dir):
                    candidates.append(os.path.join(app_dir, entry))
        # add top-level files too
        for entry in os.listdir(base):
            candidates.append(os.path.join(base, entry))

        # filter unique, safe, and files only
        seen = set()
        for p in sorted(set(candidates)):
            if not os.path.isfile(p):
                continue
            if not _is_safe_path(base, p):
                logging.warning(f"Skipping unsafe config path: {p}")
                continue
            rel = os.path.relpath(p, base)
            if filename and os.path.basename(rel) != filename:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    content = fh.read()
                results[rel] = content
            except Exception as e:
                logging.error(f"Failed to read config file {p}: {e}")
        return results
    except Exception as e:
        logging.error(f"Error loading config files: {e}")
        return {}

# Configure production logging
LOG_LEVEL = os.getenv("RAGFLOW_LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("RAGFLOW_LOG_FILE", "runtime.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s"
)

def log_output(filename, content):
    # Sanitize filename for contributor safety
    safe_filename = os.path.basename(filename)
    path = os.path.join(OUTPUT_DIR, safe_filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logging.info(f"Output written to {path}")
    except Exception as e:
        logging.error(f"Failed to write output: {e}")

# Security: Add security headers to all responses
@app.after_request
def set_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response

# Helper to determine the 'app' context from a request:
def get_app_context_from_request(req) -> str | None:
    # Priority: X-APP header -> JSON body 'app' -> query param 'app'
    app = req.headers.get("X-APP")
    if app:
        return app
    try:
        j = req.get_json(silent=True) or {}
        if isinstance(j, dict) and j.get("app"):
            return j.get("app")
    except Exception:
        pass
    app = req.args.get("app")
    return app

# Health check endpoint with LLM provider information
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint showing system status and LLM provider info."""
    try:
        from llm_provider import llm_config
        provider_info = llm_config.get_provider_info()
    except Exception as e:
        provider_info = {
            "provider": "unknown",
            "error": str(e)
        }
    
    return jsonify({
        "status": "healthy",
        "graphiti_available": GRAPHITI_AVAILABLE,
        "llm_provider": provider_info.get("provider", "unknown"),
        "llm_model": provider_info.get("llm_model", "unknown"),
        "embeddings_model": provider_info.get("embeddings_model", "unknown"),
        "neo4j_uri": os.getenv("NEO4J_URI", "not configured"),
        "supabase_configured": bool(os.getenv("SUPABASE_URL")),
        "crawl4ai_available": True,  # Crawl4AI is now integrated
        "timestamp": datetime.datetime.now().isoformat()
    })

# Debug endpoint to view loaded config for the current request's app context.
# This is API-key protected and contributor-friendly (read-only).
@app.route("/config", methods=["GET"])
def config_view():
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    app_ctx = get_app_context_from_request(request)
    filename = request.args.get("file")
    configs = load_config_file(filename=filename, app_name=app_ctx)
    if not configs:
        return jsonify({"configs": {}, "message": "No config files found for the provided context."})
    return jsonify({"configs": configs})

# Ollama embedding function (scaffold)
def get_embedding_ollama(text, model="nomic-embed-text"):
    """Get embeddings from Ollama API."""
    try:
        import requests
        ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
        response = requests.post(
            f"{ollama_host}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        logging.error(f"Ollama embedding error: {e}")
        # Fallback to fake embedding if Ollama fails
        return [hash(word) % 1000 for word in text.lower().split()][:128]


# API Key configuration - REQUIRED in production
FLASK_ENV = os.getenv("FLASK_ENV", "development")
API_KEY = os.getenv("RAGFLOW_API_KEY")

if API_KEY is None or API_KEY == "changeme" or API_KEY.endswith("change_me") or len(API_KEY) < 16:
    if FLASK_ENV == "production":
        logging.error("RAGFLOW_API_KEY must be set to a strong value (min 16 chars) in production mode")
        raise RuntimeError(
            "RAGFLOW_API_KEY must be set to a strong value in production. "
            "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    else:
        # Allow development mode with warning
        if API_KEY is None:
            logging.warning("RAGFLOW_API_KEY not set. Using default 'changeme' for development only.")
            API_KEY = "changeme"
        else:
            logging.warning(f"Using weak API key. This is INSECURE for production! Length: {len(API_KEY)}")
elif len(API_KEY) < 32:
    logging.warning(f"API key is short ({len(API_KEY)} chars). Recommend 32+ chars for security.")

RATE_LIMIT = 100  # requests per hour per IP
rate_limit_store = {}

def authenticate():
    key = request.headers.get("X-API-KEY")
    if key != API_KEY:
        return False
    return True

def rate_limit():
    ip = request.remote_addr
    now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
    if ip not in rate_limit_store or rate_limit_store[ip]["window"] != now:
        rate_limit_store[ip] = {"window": now, "count": 1}
    else:
        rate_limit_store[ip]["count"] += 1
    if rate_limit_store[ip]["count"] > RATE_LIMIT:
        return False
    return True


@app.route("/completion", methods=["POST"])
def completion():
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429
    try:
        data = request.get_json(force=True)
        prompt = str(data.get("prompt", "")).strip()
        model = str(data.get("model", "llama2")).strip()
        if not prompt:
            raise BadRequest("Prompt is required.")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        response = f"Mock response from {model} for prompt: {prompt}"
        log_output(f"completion_{timestamp}.txt", response)
        logging.info(f"Completion endpoint called with model={model}")
        return jsonify({"response": response})
    except BadRequest as e:
        logging.warning(f"Bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Internal error: {e}")
        return jsonify({"error": "Internal server error."}), 500

@app.route("/ingest", methods=["POST"])
def ingest():
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429
    try:
        if "file" not in request.files:
            raise BadRequest("No file part in request.")
        file = request.files["file"]
        filename = os.path.basename(file.filename or "uploaded_file")
        if not filename:
            raise BadRequest("No selected file.")
        ext = filename.lower().rsplit(".", 1)[-1]
        if ext == "txt":
            try:
                text = file.read().decode("utf-8")
            except UnicodeDecodeError:
                file.seek(0)
                text = file.read().decode("latin-1", errors="ignore")
        elif ext == "pdf":
            if PyPDF2 is None:
                raise BadRequest("PyPDF2 not installed. PDF support unavailable.")
            try:
                pdf = PyPDF2.PdfReader(file.stream)
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            except Exception as e:
                logging.error(f"PDF parsing error: {e}")
                raise BadRequest("Failed to parse PDF document.")
        else:
            raise BadRequest("Unsupported file type. Only .txt and .pdf allowed.")
        
        # Store in Supabase (vector store)
        embedding = get_embedding_ollama(text)
        response = add_document_to_supabase(text, metadata={"filename": filename}, embedding=embedding)
        
        # Also add to Graphiti knowledge graph for entity/relationship extraction
        graph_result = {}
        if GRAPHITI_AVAILABLE:
            try:
                episode_name = f"{filename}_{uuid.uuid4().hex[:8]}"
                logging.info(f"Adding episode to Graphiti: {episode_name}")
                graph_result = add_episode(
                    name=episode_name,
                    episode_body=text[:10000],  # Limit text size for graph processing
                    source_description=f"Document: {filename}",
                    episode_type="text"
                )
                logging.info(f"Added document to knowledge graph: {graph_result}")
            except Exception as e:
                logging.error(f"Graphiti error: {e}")
                import traceback
                logging.error(f"Graphiti traceback: {traceback.format_exc()}")
                graph_result = {"error": str(e)}
        
        logging.info(f"Ingested document {filename} via Supabase and Graphiti")
        return jsonify({
            "status": "success",
            "supabase_response": response,
            "graph_response": graph_result
        })
    except BadRequest as e:
        logging.warning(f"Bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Internal error: {e}")
        return jsonify({"error": "Internal server error."}), 500

@app.route("/retrieval", methods=["POST"])
def retrieval():
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429
    try:
        data = request.get_json(force=True)
        query = str(data.get("query", "")).strip()
        top_k = int(data.get("top_k", 3))
        metadata_filter = data.get("metadata", {})
        if not query:
            raise BadRequest("Query is required.")
        if top_k < 1 or top_k > 20:
            raise BadRequest("top_k must be between 1 and 20.")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        query_embedding = get_embedding_ollama(query)
        docs = search_documents_supabase(query_embedding, top_k=top_k)
        
        # Metadata filtering
        if metadata_filter:
            docs = [doc for doc in docs if all(doc.get("metadata", {}).get(k) == v for k, v in metadata_filter.items())]
        
        # Also search the knowledge graph for entities and relationships
        graph_results = []
        if GRAPHITI_AVAILABLE:
            graph_results = search_graph(query, num_results=5)
            logging.info(f"Graph search returned {len(graph_results)} results")
        
        results = [{
            "doc_id": doc.get("id", "unknown"),
            "filename": doc.get("metadata", {}).get("filename", "unknown"),
            "snippet": doc.get("text", "")[:200]
        } for doc in docs]
        
        log_output(f"retrieval_{timestamp}.json", json.dumps({
            "vector_results": results,
            "graph_results": graph_results
        }, indent=2))
        logging.info(f"Retrieval endpoint called with query='{query}' top_k={top_k}")
        return jsonify({
            "vector_results": results,
            "graph_results": graph_results
        })
    except BadRequest as e:
        logging.warning(f"Bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Internal error: {e}")
        return jsonify({"error": "Internal server error."}), 500


@app.route("/graph/search", methods=["POST"])
def graph_search():
    """Search the temporal knowledge graph for entities and relationships."""
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    if not GRAPHITI_AVAILABLE:
        return jsonify({"error": "Graphiti is not available. Install graphiti-core package."}), 503
    
    try:
        data = request.get_json(force=True)
        query = str(data.get("query", "")).strip()
        num_results = int(data.get("num_results", 10))
        center_node_uuid = data.get("center_node_uuid")
        
        if not query:
            raise BadRequest("Query is required.")
        if num_results < 1 or num_results > 50:
            raise BadRequest("num_results must be between 1 and 50.")
        
        results = search_graph(query, num_results=num_results, center_node_uuid=center_node_uuid)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_output(f"graph_search_{timestamp}.json", json.dumps(results, indent=2))
        
        logging.info(f"Graph search endpoint called with query='{query}'")
        return jsonify({"results": results, "count": len(results)})
    except BadRequest as e:
        logging.warning(f"Bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Internal error: {e}")
        return jsonify({"error": "Internal server error."}), 500


@app.route("/graph/temporal", methods=["POST"])
def graph_temporal():
    """Get temporal context for an entity across time."""
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    if not GRAPHITI_AVAILABLE:
        return jsonify({"error": "Graphiti is not available. Install graphiti-core package."}), 503
    
    try:
        data = request.get_json(force=True)
        entity_name = str(data.get("entity_name", "")).strip()
        start_time_str = data.get("start_time")
        end_time_str = data.get("end_time")
        
        if not entity_name:
            raise BadRequest("entity_name is required.")
        
        # Parse datetime strings if provided
        start_time = None
        end_time = None
        if start_time_str:
            try:
                start_time = datetime.datetime.fromisoformat(start_time_str)
            except ValueError:
                raise BadRequest("start_time must be in ISO format (YYYY-MM-DDTHH:MM:SS)")
        if end_time_str:
            try:
                end_time = datetime.datetime.fromisoformat(end_time_str)
            except ValueError:
                raise BadRequest("end_time must be in ISO format (YYYY-MM-DDTHH:MM:SS)")
        
        context = get_temporal_context(entity_name, start_time=start_time, end_time=end_time)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_output(f"temporal_context_{timestamp}.json", json.dumps(context, indent=2))
        
        logging.info(f"Temporal context endpoint called for entity='{entity_name}'")
        return jsonify(context)
    except BadRequest as e:
        logging.warning(f"Bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Internal error: {e}")
        return jsonify({"error": "Internal server error."}), 500


def is_safe_url(url: str) -> bool:
    """Validate URL is safe to crawl (prevent SSRF attacks)."""
    from urllib.parse import urlparse
    import ipaddress
    import socket
    
    try:
        parsed = urlparse(url)
        
        # Only allow http/https
        if parsed.scheme not in ['http', 'https']:
            return False
        
        # Must have hostname
        hostname = parsed.hostname
        if not hostname:
            return False
        
        # Block cloud metadata endpoints
        blocked_domains = ['169.254.169.254', 'metadata.google.internal', 'metadata.goog']
        if hostname in blocked_domains:
            return False
        
        # Allow testing domains (example.com, example[0-9].com, localhost for testing)
        if FLASK_ENV != "production" and (hostname.startswith('example') or hostname == 'localhost'):
            return True
        
        # Resolve to IP and check if internal
        try:
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            
            # Block private/loopback/link-local networks
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                return False
        except socket.gaierror:
            # DNS resolution failed
            return False
            
        return True
    except Exception as e:
        logging.error(f"URL validation error: {e}")
        return False


@app.route("/crawl", methods=["POST"])
def create_crawl_job():
    """Create a new crawl job for web content extraction."""
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        data = request.get_json(force=True)
        crawl_request = CrawlJobRequest.from_dict(data)

        # Security: Validate URL to prevent SSRF attacks
        if not is_safe_url(crawl_request.url):
            raise BadRequest("Invalid or unsafe URL. Only public HTTP/HTTPS URLs are allowed.")

        # Create the job
        job = asyncio.run(crawl_manager.create_job(crawl_request.url, crawl_request.to_config()))

        response = CrawlJobResponse.from_job(job)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_output(f"crawl_job_created_{timestamp}.json", json.dumps({
            "job_id": job.id,
            "url": job.url,
            "config": job.config.to_dict()
        }, indent=2))

        logging.info(f"Created crawl job {job.id} for URL: {job.url}")
        return jsonify(response.__dict__), 201

    except BadRequest as e:
        logging.warning(f"Bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Internal error creating crawl job: {e}")
        return jsonify({"error": "Internal server error."}), 500


@app.route("/crawl/<job_id>", methods=["GET"])
def get_crawl_job(job_id: str):
    """Get the status and results of a crawl job."""
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        job = asyncio.run(crawl_manager.get_job(job_id))
        if not job:
            return jsonify({"error": "Job not found"}), 404

        response = CrawlJobResponse.from_job(job)
        return jsonify(response.__dict__)

    except Exception as e:
        logging.error(f"Internal error retrieving crawl job {job_id}: {e}")
        return jsonify({"error": "Internal server error."}), 500


@app.route("/crawl", methods=["GET"])
def list_crawl_jobs():
    """List crawl jobs with optional filtering."""
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        status_filter = request.args.get("status")
        limit = int(request.args.get("limit", 50))

        if limit < 1 or limit > 100:
            raise BadRequest("limit must be between 1 and 100.")

        status = None
        if status_filter:
            try:
                status = CrawlStatus(status_filter.lower())
            except ValueError:
                raise BadRequest(f"Invalid status: {status_filter}. Must be one of: {[s.value for s in CrawlStatus]}")

        jobs = asyncio.run(crawl_manager.list_jobs(status=status, limit=limit))
        responses = [CrawlJobResponse.from_job(job).__dict__ for job in jobs]

        return jsonify({
            "jobs": responses,
            "count": len(responses)
        })

    except BadRequest as e:
        logging.warning(f"Bad request: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Internal error listing crawl jobs: {e}")
        return jsonify({"error": "Internal server error."}), 500


@app.route("/crawl/<job_id>/start", methods=["POST"])
def start_crawl_job(job_id: str):
    """Start execution of a pending crawl job."""
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        success = asyncio.run(crawl_manager.start_job(job_id))
        if not success:
            return jsonify({"error": "Failed to start job. It may not exist or not be in pending status."}), 400

        logging.info(f"Started crawl job {job_id}")
        return jsonify({"message": f"Job {job_id} started successfully"})

    except Exception as e:
        logging.error(f"Internal error starting crawl job {job_id}: {e}")
        return jsonify({"error": "Internal server error."}), 500


@app.route("/crawl/<job_id>/cancel", methods=["POST"])
def cancel_crawl_job(job_id: str):
    """Cancel a running or pending crawl job."""
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    if not rate_limit():
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        success = asyncio.run(crawl_manager.cancel_job(job_id))
        if not success:
            return jsonify({"error": "Failed to cancel job. It may not exist or not be cancellable."}), 400

        logging.info(f"Cancelled crawl job {job_id}")
        return jsonify({"message": f"Job {job_id} cancelled successfully"})

    except Exception as e:
        logging.error(f"Internal error cancelling crawl job {job_id}: {e}")
        return jsonify({"error": "Internal server error."}), 500


if __name__ == "__main__":
    # Production-ready: debug=False
    app.run(debug=False)
