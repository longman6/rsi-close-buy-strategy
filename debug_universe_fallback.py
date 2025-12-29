
import sys
import os
import logging
from unittest.mock import MagicMock

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_fallback():
    print("🧪 Testing KOSDAQ 150 Universe Fallback Logic...")
    
    # 1. Force PyKRX failure by mocking the module in sys.modules to raise ImportError/Exception
    # We set it to None, which causes ImportError on import
    sys.modules["pykrx"] = None
    
    try:
        # Import the function now
        from analyze_kosdaq150 import get_kosdaq150_universe
        
        # Run function
        print("   Running get_kosdaq150_universe() with PyKRX disabled...")
        universe = get_kosdaq150_universe()
        
        count = len(universe)
        print(f"   Result Count: {count}")
        
        # Verify content
        if count > 10:
            print("✅ Success! Fetched universe from file (fallback working).")
            print(f"   Sample: {universe[:3]}")
        else:
            print("❌ Failure! Returned list is too small (might have hit ultimate hardcoded fallback or empty).")
            print(f"   Content: {universe}")

    except Exception as e:
        print(f"❌ unexpected error during test: {e}")
    finally:
        # Cleanup
        if "pykrx" in sys.modules:
            del sys.modules["pykrx"]

if __name__ == "__main__":
    test_fallback()
