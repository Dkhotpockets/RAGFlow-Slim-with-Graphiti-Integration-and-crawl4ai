-- Fix setup: Only add missing components

-- Ensure pgvector extension is enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Check if documents table needs the embedding column
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'documents' AND column_name = 'embedding'
    ) THEN
        ALTER TABLE documents ADD COLUMN embedding vector(1536);
    END IF;
END $$;

-- Create index for vector similarity search (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'documents_embedding_idx'
    ) THEN
        CREATE INDEX documents_embedding_idx ON documents
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    END IF;
END $$;

-- Create index for metadata queries (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'documents_metadata_idx'
    ) THEN
        CREATE INDEX documents_metadata_idx ON documents USING gin(metadata);
    END IF;
END $$;

-- Create index for created_at (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'documents_created_at_idx'
    ) THEN
        CREATE INDEX documents_created_at_idx ON documents(created_at DESC);
    END IF;
END $$;

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
  WHERE 1 - (embedding <=> query_embedding) > match_threshold
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Grant permissions
GRANT ALL ON documents TO service_role;
GRANT EXECUTE ON FUNCTION match_documents TO service_role;
GRANT SELECT, INSERT ON documents TO authenticated;
GRANT EXECUTE ON FUNCTION match_documents TO authenticated;
