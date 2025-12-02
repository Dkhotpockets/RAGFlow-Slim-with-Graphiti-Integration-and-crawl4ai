#!/usr/bin/env python3
import os
import logging
import pytest

logging.basicConfig(level=logging.DEBUG)


def test_geminiclient_import():
    """Test that GeminiClient can be imported and initialized (if API key is set)."""
    print("=" * 60)
    print("Testing GeminiClient initialization")
    print("=" * 60)

    print(f"\n1. Environment variables:")
    print(f"  GOOGLE_API_KEY: {os.getenv('GOOGLE_API_KEY', 'NOT SET')[:20] if os.getenv('GOOGLE_API_KEY') else 'NOT SET'}...")
    print(f"  OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY', 'NOT SET')}")

    try:
        print(f"\n2. Importing GeminiClient...")
        from graphiti_core.llm_client.gemini_client import GeminiClient
        print("   ✅ GeminiClient imported")

        print(f"\n3. Importing LLMConfig...")
        from graphiti_core.llm_client import LLMConfig
        print("   ✅ LLMConfig imported")

        # Check if API key is available
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set, skipping GeminiClient initialization test")
            return

        print(f"\n4. Creating LLMConfig...")
        llm_config = LLMConfig(
            api_key=api_key,
            model="gemini-1.5-flash"
        )
        print(f"   ✅ LLMConfig created: {llm_config}")

        print(f"\n5. Creating GeminiClient...")
        client = GeminiClient(config=llm_config)
        print(f"   ✅ GeminiClient created: {client}")
        print("   SUCCESS!")

    except ModuleNotFoundError as e:
        print(f"   ⚠️ Optional dependency missing: {e}. Skipping GeminiClient initialization tests.")
        pytest.skip(f"Optional dependency missing: {e}")

    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}")
        print(f"   Message: {e}")
        import traceback
        print("\n   Full traceback:")
        traceback.print_exc()
        pytest.fail(f"GeminiClient initialization failed with exception: {e}")
