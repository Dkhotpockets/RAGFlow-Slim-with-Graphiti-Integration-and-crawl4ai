#!/usr/bin/env python3"""#!/usr/bin/env python3

"""Test Supabase connection and setup"""

Simple test to verify Supabase is working with RAGFlow"""Test Supabase connection and setup"""

import os

from supabase import create_client, Client"""

from dotenv import load_dotenv

import numpy as npimport osimport os



load_dotenv()from supabase import create_client, Clientfrom dotenv import load_dotenv



url = os.environ.get("SUPABASE_URL")from dotenv import load_dotenvfrom supabase import create_client, Client

key = os.environ.get("SUPABASE_KEY")

import numpy as np

print("🔍 Testing Supabase connection...")

print(f"URL: {url}\n")# Load environment variables



try:load_dotenv()load_dotenv()

    supabase = create_client(url, key)

    

    # Test 1: Check documents table

    print("1️⃣ Testing documents table...")# Initialize Supabase clientSUPABASE_URL = os.getenv("SUPABASE_URL")

    result = supabase.table('documents').select('*').limit(1).execute()

    print(f"✅ Documents table accessible (rows: {len(result.data)})")url: str = os.environ.get("SUPABASE_URL")SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    

    # Test 2: Check crawl_jobs tablekey: str = os.environ.get("SUPABASE_KEY")

    print("\n2️⃣ Testing crawl_jobs table...")

    result = supabase.table('crawl_jobs').select('*').limit(1).execute()print(f"Testing Supabase connection...")

    print(f"✅ Crawl_jobs table accessible (rows: {len(result.data)})")

    print("🔍 Testing Supabase connection...")print(f"URL: {SUPABASE_URL}")

    # Test 3: Insert a test document

    print("\n3️⃣ Testing document insertion...")print(f"URL: {url}\n")print(f"Key: {SUPABASE_KEY[:20]}..." if SUPABASE_KEY else "Key: Not found")

    test_doc = {

        'text': 'Test document for RAGFlow verification',

        'metadata': {'source': 'test', 'type': 'verification'}

    }try:try:

    result = supabase.table('documents').insert(test_doc).execute()

    doc_id = result.data[0]['id']    supabase: Client = create_client(url, key)    # Create Supabase client

    print(f"✅ Successfully inserted test document (ID: {doc_id})")

            supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Test 4: Insert test document with embedding

    print("\n4️⃣ Testing document with embedding...")    # Test 1: Check documents table    print("✅ Supabase client created successfully!")

    test_embedding = np.random.rand(1536).tolist()

    test_doc_with_emb = {    print("1️⃣ Testing documents table...")    

        'text': 'Test document with embedding',

        'metadata': {'source': 'test', 'has_embedding': True},    result = supabase.table('documents').select('*').limit(1).execute()    # Try to list tables

        'embedding': test_embedding

    }    print(f"✅ Documents table accessible (rows: {len(result.data)})")    response = supabase.table("documents").select("*").limit(1).execute()

    result = supabase.table('documents').insert(test_doc_with_emb).execute()

    emb_doc_id = result.data[0]['id']        print(f"✅ Successfully connected to Supabase!")

    print(f"✅ Successfully inserted document with embedding (ID: {emb_doc_id})")

        # Test 2: Check crawl_jobs table    print(f"   Documents table exists with {len(response.data)} records (showing max 1)")

    # Test 5: Test vector search function

    print("\n5️⃣ Testing vector similarity search...")    print("\n2️⃣ Testing crawl_jobs table...")    

    query_embedding = np.random.rand(1536).tolist()

    result = supabase.rpc('match_documents', {    result = supabase.table('crawl_jobs').select('*').limit(1).execute()except Exception as e:

        'query_embedding': query_embedding,

        'match_threshold': 0.0,    print(f"✅ Crawl_jobs table accessible (rows: {len(result.data)})")    print(f"❌ Error connecting to Supabase: {e}")

        'match_count': 5

    }).execute()        print("\nThis might mean:")

    print(f"✅ Vector search working (found {len(result.data)} results)")

        # Test 3: Insert a test document    print("1. The 'documents' table doesn't exist yet (we'll create it)")

    # Test 6: Create a crawl job

    print("\n6️⃣ Testing crawl job creation...")    print("\n3️⃣ Testing document insertion...")    print("2. There's a network issue")

    test_job = {

        'url': 'https://example.com',    test_doc = {    print("3. The credentials are incorrect")

        'status': 'pending',

        'config': {'max_depth': 1, 'timeout': 30}        'text': 'Test document for RAGFlow verification',

    }        'metadata': {'source': 'test', 'type': 'verification'}

    result = supabase.table('crawl_jobs').insert(test_job).execute()    }

    job_id = result.data[0]['id']    result = supabase.table('documents').insert(test_doc).execute()

    print(f"✅ Successfully created crawl job (ID: {job_id})")    doc_id = result.data[0]['id']

        print(f"✅ Successfully inserted test document (ID: {doc_id})")

    # Test 7: Update crawl job status    

    print("\n7️⃣ Testing crawl job update...")    # Test 4: Insert test document with embedding

    result = supabase.table('crawl_jobs').update({    print("\n4️⃣ Testing document with embedding...")

        'status': 'completed',    test_embedding = np.random.rand(1536).tolist()  # Random 1536-dim vector

        'result': {'pages_crawled': 5, 'documents_created': 3}    test_doc_with_emb = {

    }).eq('id', job_id).execute()        'text': 'Test document with embedding',

    print(f"✅ Successfully updated crawl job")        'metadata': {'source': 'test', 'has_embedding': True},

            'embedding': test_embedding

    # Cleanup test data    }

    print("\n🧹 Cleaning up test data...")    result = supabase.table('documents').insert(test_doc_with_emb).execute()

    supabase.table('documents').delete().eq('id', doc_id).execute()    emb_doc_id = result.data[0]['id']

    supabase.table('documents').delete().eq('id', emb_doc_id).execute()    print(f"✅ Successfully inserted document with embedding (ID: {emb_doc_id})")

    supabase.table('crawl_jobs').delete().eq('id', job_id).execute()    

    print("✅ Test data cleaned up")    # Test 5: Test vector search function

        print("\n5️⃣ Testing vector similarity search...")

    print("\n" + "="*50)    query_embedding = np.random.rand(1536).tolist()

    print("🎉 ALL TESTS PASSED!")    result = supabase.rpc('match_documents', {

    print("="*50)        'query_embedding': query_embedding,

    print("\n✅ Supabase is fully configured and functional")        'match_threshold': 0.0,

    print("✅ RAGFlow is ready to use")        'match_count': 5

        }).execute()

except Exception as e:    print(f"✅ Vector search working (found {len(result.data)} results)")

    print(f"\n❌ Error: {e}")    

    import traceback    # Test 6: Create a crawl job

    traceback.print_exc()    print("\n6️⃣ Testing crawl job creation...")

    test_job = {
        'url': 'https://example.com',
        'status': 'pending',
        'config': {'max_depth': 1, 'timeout': 30}
    }
    result = supabase.table('crawl_jobs').insert(test_job).execute()
    job_id = result.data[0]['id']
    print(f"✅ Successfully created crawl job (ID: {job_id})")
    
    # Test 7: Update crawl job status
    print("\n7️⃣ Testing crawl job update...")
    result = supabase.table('crawl_jobs').update({
        'status': 'completed',
        'result': {'pages_crawled': 5, 'documents_created': 3}
    }).eq('id', job_id).execute()
    print(f"✅ Successfully updated crawl job")
    
    # Cleanup test data
    print("\n🧹 Cleaning up test data...")
    supabase.table('documents').delete().eq('id', doc_id).execute()
    supabase.table('documents').delete().eq('id', emb_doc_id).execute()
    supabase.table('crawl_jobs').delete().eq('id', job_id).execute()
    print("✅ Test data cleaned up")
    
    print("\n" + "="*50)
    print("🎉 ALL TESTS PASSED!")
    print("="*50)
    print("\n✅ Supabase is fully configured and functional for RAGFlow")
    print("✅ Ready to run the main application")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\n📋 Setup Instructions:")
    print("1. Go to: https://app.supabase.com/project/ilgsekabtgymxwgxbkok/sql")
    print("2. Copy all contents from: complete_supabase_setup.sql")
    print("3. Paste and run in the SQL Editor")
    print("4. Run this test script again: python test_supabase.py")
