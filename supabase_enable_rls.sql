-- Enable Row Level Security (RLS) on RAGFlow tables
-- Run this in your Supabase SQL Editor

-- Enable RLS on documents table
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

-- Enable RLS on crawl_jobs table
ALTER TABLE public.crawl_jobs ENABLE ROW LEVEL SECURITY;

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
