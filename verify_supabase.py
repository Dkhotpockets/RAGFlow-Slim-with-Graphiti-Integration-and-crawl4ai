"""
Verify and fix Supabase setup for RAGFlow
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("🔍 Checking Supabase connection...")
print(f"URL: {url}")

# SQL to check current schema
check_schema_sql = """
SELECT 
    table_name,
    column_name, 
    data_type,
    character_maximum_length
FROM information_schema.columns 
WHERE table_schema = 'public' 
    AND table_name IN ('documents', 'crawl_jobs')
ORDER BY table_name, ordinal_position;
"""

# SQL to check if pgvector is enabled
check_vector_sql = """
SELECT * FROM pg_extension WHERE extname = 'vector';
"""

# Complete setup SQL
complete_setup_sql = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create documents table with all necessary columns
CREATE TABLE IF NOT EXISTS documents (
  id BIGSERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  embedding vector(1536),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Add embedding column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'documents' AND column_name = 'embedding'
    ) THEN
        ALTER TABLE documents ADD COLUMN embedding vector(1536);
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Could not add embedding column: %', SQLERRM;
END $$;

-- Drop existing index if it has wrong type
DROP INDEX IF EXISTS documents_embedding_idx;

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for metadata queries
CREATE INDEX IF NOT EXISTS documents_metadata_idx ON documents USING gin(metadata);

-- Create index for created_at for sorting
CREATE INDEX IF NOT EXISTS documents_created_at_idx ON documents(created_at DESC);

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
DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL ON documents TO service_role;
GRANT USAGE, SELECT ON SEQUENCE documents_id_seq TO service_role;
GRANT EXECUTE ON FUNCTION match_documents TO service_role;
GRANT SELECT, INSERT, UPDATE ON documents TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE documents_id_seq TO authenticated;
GRANT EXECUTE ON FUNCTION match_documents TO authenticated;

-- Create crawl_jobs table
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

-- Create indexes for crawl_jobs
CREATE INDEX IF NOT EXISTS crawl_jobs_status_idx ON crawl_jobs(status);
CREATE INDEX IF NOT EXISTS crawl_jobs_created_at_idx ON crawl_jobs(created_at DESC);

-- Create trigger on crawl_jobs
DROP TRIGGER IF EXISTS update_crawl_jobs_updated_at ON crawl_jobs;
CREATE TRIGGER update_crawl_jobs_updated_at BEFORE UPDATE ON crawl_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions on crawl_jobs
GRANT ALL ON crawl_jobs TO service_role;
GRANT SELECT, INSERT, UPDATE ON crawl_jobs TO authenticated;
"""

try:
    print("\n1️⃣ Checking pgvector extension...")
    result = supabase.rpc('sql', {'query': check_vector_sql}).execute()
    print("✅ pgvector check query executed")
    
    print("\n2️⃣ Checking current schema...")
    result = supabase.rpc('sql', {'query': check_schema_sql}).execute()
    print("✅ Schema check query executed")
    
    print("\n3️⃣ Applying complete setup SQL...")
    # Execute the complete setup using Supabase's execute method
    print("⚠️  Note: Execute the complete_setup_sql manually in Supabase SQL Editor")
    print("Go to: https://app.supabase.com/project/ilgsekabtgymxwgxbkok/sql")
    
    # Save the SQL to a file for manual execution
    with open('complete_setup.sql', 'w') as f:
        f.write(complete_setup_sql)
    print("✅ SQL saved to complete_setup.sql")
    
    print("\n4️⃣ Testing basic connection...")
    # Try a simple query
    result = supabase.table('documents').select('*').limit(1).execute()
    print(f"✅ Successfully queried documents table (found {len(result.data)} rows)")
    
    result = supabase.table('crawl_jobs').select('*').limit(1).execute()
    print(f"✅ Successfully queried crawl_jobs table (found {len(result.data)} rows)")
    
    print("\n✅ Supabase connection verified!")
    print("\n📋 Next steps:")
    print("1. Open Supabase SQL Editor: https://app.supabase.com/project/ilgsekabtgymxwgxbkok/sql")
    print("2. Copy and run the SQL from complete_setup.sql")
    print("3. Run this script again to verify")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\n📋 Manual Setup Required:")
    print("1. Go to: https://app.supabase.com/project/ilgsekabtgymxwgxbkok/sql")
    print("2. Run the SQL from complete_setup.sql")
    print("   The file has been created in the current directory")
