-- Supabase Setup for RAGFlow Slim
-- Run this in your Supabase SQL Editor
--
-- This is the initial setup script. After running this, also run:
-- - supabase_enable_rls.sql (for security hardening)

-- Create extensions schema for better security isolation
CREATE SCHEMA IF NOT EXISTS extensions;

-- Enable pgvector extension in extensions schema (recommended)
-- If you need it in public schema for compatibility, use:
-- CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- Create documents table with vector embeddings
CREATE TABLE IF NOT EXISTS documents (
  id BIGSERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  embedding vector(1536),  -- Adjust dimension based on your embedding model
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for metadata queries
CREATE INDEX IF NOT EXISTS documents_metadata_idx ON documents USING gin(metadata);

-- Create index for created_at for sorting
CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents(created_at DESC);

-- Create RPC function for vector similarity search with secure search_path
-- Note: This will be recreated with enhanced security in supabase_enable_rls.sql
CREATE OR REPLACE FUNCTION public.match_documents(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.0,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id bigint,
  text text,
  metadata jsonb,
  embedding vector,
  similarity float
)
LANGUAGE SQL 
STABLE
SECURITY DEFINER
SET search_path = public, extensions, pg_catalog
AS $$
  SELECT
    documents.id,
    documents.text,
    documents.metadata,
    documents.embedding,
    1 - (documents.embedding <=> query_embedding) AS similarity
  FROM public.documents
  WHERE 1 - (documents.embedding <=> query_embedding) > match_threshold
  ORDER BY documents.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Create trigger function to update updated_at timestamp with secure search_path
-- Note: This will be recreated with enhanced security in supabase_enable_rls.sql
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    NEW.updated_at = pg_catalog.timezone('utc'::text, pg_catalog.now());
    RETURN NEW;
END;
$$;

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust based on your Supabase roles)
-- For service role (used by the API)
GRANT ALL ON documents TO service_role;
GRANT EXECUTE ON FUNCTION match_documents TO service_role;

-- For authenticated users (if you want to expose this via Supabase client)
GRANT SELECT, INSERT ON documents TO authenticated;
GRANT EXECUTE ON FUNCTION match_documents TO authenticated;

-- Optional: Create crawl_jobs table for Crawl4AI integration
CREATE TABLE IF NOT EXISTS crawl_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
  config JSONB DEFAULT '{}'::jsonb,
  result JSONB DEFAULT '{}'::jsonb,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS crawl_jobs_status_idx ON crawl_jobs(status);
CREATE INDEX IF NOT EXISTS crawl_jobs_created_at_idx ON crawl_jobs(created_at DESC);

CREATE TRIGGER update_crawl_jobs_updated_at BEFORE UPDATE ON crawl_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

GRANT ALL ON crawl_jobs TO service_role;
GRANT SELECT, INSERT ON crawl_jobs TO authenticated;
