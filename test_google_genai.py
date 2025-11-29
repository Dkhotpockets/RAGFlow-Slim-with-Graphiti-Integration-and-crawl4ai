#!/usr/bin/env python3
import os
import pytest

def test_google_genai_import():
    """Test that google-genai can be imported and used (if API key is set)."""
    print(f"GOOGLE_API_KEY: {os.getenv('GOOGLE_API_KEY', 'NOT SET')}")
    print(f"OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY', 'NOT SET')}")

    try:
        from google import genai
        print("✅ google-genai imported")

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set, skipping google-genai test")
            return

        print(f"Using API key: {api_key[:20]}...")

        client = genai.Client(api_key=api_key)
        print(f"✅ genai.Client created: {client}")

        # Try to use it
        response = client.models.list()
        print(f"✅ Models available: {[m.name for m in response[:3]]}")

    except ModuleNotFoundError as e:
        print(f"⚠️ Optional dependency missing: {e}. Skipping google-genai test.")
        pytest.skip(f"Optional dependency missing: {e}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        pytest.fail(f"google-genai test failed with exception: {e}")
