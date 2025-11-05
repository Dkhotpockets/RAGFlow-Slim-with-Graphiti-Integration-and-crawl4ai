-- Complete Supabase Setup for RAGFlow Slim
-- Run this in Supabase SQL Editor: https://app.supabase.com/project/ilgsekabtgymxwgxbkok/sql

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop existing documents table to recreate properly
DROP TABLE IF EXISTS documents CASCADE;

-- Create documents table with all necessary columns
CREATE TABLE documents (
  id BIGSERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  embedding vector(1536),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create index for vector similarity search
CREATE INDEX documents_embedding_idx ON documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for metadata queries
CREATE INDEX documents_metadata_idx ON documents USING gin(metadata);

-- Create index for created_at for sorting
CREATE INDEX documents_created_at_idx ON documents(created_at DESC);

-- Create RPC function for vector similarity search
CREATE OR REPLACE FUNCTION match_documents(
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
LANGUAGE SQL STABLE
AS $$
  SELECT
    id,
    text,
    metadata,
    embedding,
    1 - (embedding <=> query_embedding) AS similarity
  FROM documents
  WHERE embedding IS NOT NULL
    AND 1 - (embedding <=> query_embedding) > match_threshold
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Create trigger function for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger on documents
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions for documents
GRANT ALL ON documents TO service_role;
GRANT USAGE, SELECT ON SEQUENCE documents_id_seq TO service_role;
GRANT EXECUTE ON FUNCTION match_documents TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE documents_id_seq TO authenticated;
GRANT EXECUTE ON FUNCTION match_documents TO authenticated;

-- Drop existing crawl_jobs table to recreate properly
DROP TABLE IF EXISTS crawl_jobs CASCADE;

-- Create crawl_jobs table
CREATE TABLE crawl_jobs (
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

-- Create indexes for crawl_jobs
CREATE INDEX crawl_jobs_status_idx ON crawl_jobs(status);
CREATE INDEX crawl_jobs_created_at_idx ON crawl_jobs(created_at DESC);
CREATE INDEX crawl_jobs_url_idx ON crawl_jobs(url);

-- Create trigger on crawl_jobs
CREATE TRIGGER update_crawl_jobs_updated_at BEFORE UPDATE ON crawl_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions on crawl_jobs
GRANT ALL ON crawl_jobs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON crawl_jobs TO authenticated;

-- Verify setup
SELECT 'Setup complete!' as status;
SELECT 'Tables created:' as info;
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name IN ('documents', 'crawl_jobs');
