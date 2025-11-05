-- Enable Row Level Security (RLS) on RAGFlow tables
-- Run this in your Supabase SQL Editor
--
-- This script addresses Supabase Database Linter warnings:
-- - 0011: function_search_path_mutable
-- - 0013: rls_disabled_in_public  
-- - 0014: extension_in_public
--
-- Professional implementation following PostgreSQL security best practices

-- ============================================================================
-- PART 1: Extension Schema Management (Lint 0014)
-- ============================================================================
-- Move pgvector extension to dedicated schema to isolate it from public schema
-- This prevents potential security issues with search_path manipulation

CREATE SCHEMA IF NOT EXISTS extensions;

-- Note: If vector extension is already in public schema, you need to:
-- 1. Create a new extension in the extensions schema
-- 2. Migrate existing data (if any)
-- For existing installations with data, contact Supabase support
-- For new installations, run: CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- ============================================================================
-- PART 2: Function Security - Fixed search_path (Lint 0011)
-- ============================================================================
-- PostgreSQL functions without explicit search_path are vulnerable to 
-- search_path hijacking attacks. Setting search_path explicitly prevents
-- malicious users from creating identically-named objects in their schema
-- to intercept function calls.

-- Fix match_documents function with explicit, immutable search_path
-- This function performs vector similarity search on documents
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
LANGUAGE SQL 
STABLE
SECURITY DEFINER
SET search_path = public, pg_catalog
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

-- Set proper ownership and permissions
ALTER FUNCTION public.match_documents(vector, float, int) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.match_documents(vector, float, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.match_documents(vector, float, int) TO service_role;
GRANT EXECUTE ON FUNCTION public.match_documents(vector, float, int) TO authenticated;

-- Fix update_updated_at_column trigger function with explicit search_path
-- This function automatically updates the updated_at timestamp on row updates
DROP FUNCTION IF EXISTS public.update_updated_at_column() CASCADE;
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    -- Use qualified function name to prevent search_path exploitation
    NEW.updated_at = pg_catalog.timezone('utc'::text, pg_catalog.now());
    RETURN NEW;
END;
$$;

-- Set proper ownership and permissions
ALTER FUNCTION public.update_updated_at_column() OWNER TO postgres;
REVOKE ALL ON FUNCTION public.update_updated_at_column() FROM PUBLIC;

-- Recreate triggers after function update
-- Triggers must be recreated because we used CASCADE when dropping the function
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

-- ============================================================================
-- PART 3: Row Level Security (RLS) Implementation (Lint 0013)
-- ============================================================================
-- RLS prevents unauthorized data access via PostgREST API
-- Without RLS, anyone with the anon key can read/write all data

-- Enable RLS on documents table
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

-- Enable RLS on crawl_jobs table  
ALTER TABLE public.crawl_jobs ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- PART 4: RLS Policies - Service Role Access
-- ============================================================================
-- Service role policies allow backend services to operate without restrictions
-- The service_role key should NEVER be exposed to clients

-- Drop existing policies if they exist (for idempotent script execution)
DROP POLICY IF EXISTS "Service role has full access to documents" ON public.documents;
DROP POLICY IF EXISTS "Service role has full access to crawl_jobs" ON public.crawl_jobs;

-- Create policy to allow service role full access to documents
CREATE POLICY "Service role has full access to documents"
ON public.documents
AS PERMISSIVE
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Create policy to allow service role full access to crawl_jobs
CREATE POLICY "Service role has full access to crawl_jobs"
ON public.crawl_jobs
AS PERMISSIVE
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- ============================================================================
-- PART 5: Grant necessary table permissions
-- ============================================================================
-- Ensure proper permissions are set for the service role
GRANT ALL ON public.documents TO service_role;
GRANT ALL ON public.crawl_jobs TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- ============================================================================
-- PART 6: Optional User-Level Access Policies
-- ============================================================================
-- Uncomment these if you want to allow authenticated users direct access
-- Note: This requires adding a user_id column to your tables

-- Example: Allow authenticated users to read their own documents
-- ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
-- CREATE INDEX IF NOT EXISTS documents_user_id_idx ON public.documents(user_id);
-- 
-- CREATE POLICY "Users can read their own documents"
-- ON public.documents
-- AS PERMISSIVE
-- FOR SELECT
-- TO authenticated
-- USING (auth.uid() = user_id);
--
-- CREATE POLICY "Users can insert their own documents"
-- ON public.documents
-- AS PERMISSIVE  
-- FOR INSERT
-- TO authenticated
-- WITH CHECK (auth.uid() = user_id);

-- Example: Allow authenticated users to manage their own crawl jobs
-- ALTER TABLE public.crawl_jobs ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
-- CREATE INDEX IF NOT EXISTS crawl_jobs_user_id_idx ON public.crawl_jobs(user_id);
--
-- CREATE POLICY "Users can manage their own crawl jobs"
-- ON public.crawl_jobs
-- AS PERMISSIVE
-- FOR ALL
-- TO authenticated
-- USING (auth.uid() = user_id)
-- WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Run these queries to verify the security configuration is correct

-- Verify RLS is enabled
-- SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('documents', 'crawl_jobs');

-- Verify policies exist
-- SELECT schemaname, tablename, policyname, permissive, roles, cmd FROM pg_policies WHERE tablename IN ('documents', 'crawl_jobs');

-- Verify function search_path is set
-- SELECT proname, prosecdef, proconfig FROM pg_proc WHERE proname IN ('match_documents', 'update_updated_at_column');

-- ============================================================================
-- NOTES
-- ============================================================================
-- 1. This script is idempotent - safe to run multiple times
-- 2. Service role key must be kept secret and only used server-side
-- 3. For user-facing applications, implement proper RLS policies with user_id
-- 4. Monitor pg_stat_statements for query performance after implementing RLS
-- 5. Test RLS policies thoroughly before deploying to production
-- 6. Consider using pgaudit extension for auditing RLS policy violations
