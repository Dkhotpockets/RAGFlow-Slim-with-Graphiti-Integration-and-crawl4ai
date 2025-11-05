-- Enable Row Level Security (RLS) on RAGFlow tables
-- Run this in your Supabase SQL Editor

-- Fix security warnings
-- 1. Move vector extension to extensions schema (if not already done)
CREATE SCHEMA IF NOT EXISTS extensions;
-- Note: If vector is already in public, you'll need to drop and recreate tables
-- For new installations, install vector in extensions schema:
-- CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- 2. Fix function search_path for security
-- Drop and recreate functions with explicit search_path

-- Fix match_documents function with explicit search_path
DROP FUNCTION IF EXISTS public.match_documents(vector, float, int);
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
LANGUAGE SQL STABLE
SET search_path = public, extensions
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

-- Fix update_updated_at_column function with explicit search_path
DROP FUNCTION IF EXISTS public.update_updated_at_column() CASCADE;
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$;

-- Recreate triggers after function update
DROP TRIGGER IF EXISTS update_documents_updated_at ON public.documents;
CREATE TRIGGER update_documents_updated_at 
BEFORE UPDATE ON public.documents
FOR EACH ROW 
EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_crawl_jobs_updated_at ON public.crawl_jobs;
CREATE TRIGGER update_crawl_jobs_updated_at 
BEFORE UPDATE ON public.crawl_jobs
FOR EACH ROW 
EXECUTE FUNCTION public.update_updated_at_column();

-- 3. Enable RLS on documents table
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

-- 4. Enable RLS on crawl_jobs table
ALTER TABLE public.crawl_jobs ENABLE ROW LEVEL SECURITY;

-- 5. Create policies for RLS
-- Create policy to allow service role full access to documents
CREATE POLICY "Service role has full access to documents"
ON public.documents
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Create policy to allow service role full access to crawl_jobs
CREATE POLICY "Service role has full access to crawl_jobs"
ON public.crawl_jobs
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Optional: If you want to allow authenticated users to read their own documents
-- Uncomment and modify based on your auth setup
-- CREATE POLICY "Users can read their own documents"
-- ON public.documents
-- FOR SELECT
-- TO authenticated
-- USING (auth.uid() = user_id);

-- Optional: If you want to allow authenticated users to manage their own crawl jobs
-- CREATE POLICY "Users can manage their own crawl jobs"
-- ON public.crawl_jobs
-- FOR ALL
-- TO authenticated
-- USING (auth.uid() = user_id)
-- WITH CHECK (auth.uid() = user_id);
