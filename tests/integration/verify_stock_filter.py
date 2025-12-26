from src.kis_client import KISClient
import logging

logging.basicConfig(level=logging.INFO)

def verify():
    kis = KISClient()
    
    # 1. Test Fadu (440110) - Should be Dangerous (Code 58)
    print("Checking Fadu (440110)...")
    is_danger, reason = kis.check_dangerous_stock("440110")
    print(f"Result: Dangerous={is_danger}, Reason={reason}")
    if is_danger:
        print("✅ PASS: Fadu correctly flagged.")
    else:
        print("❌ FAIL: Fadu NOT flagged.")

    # 2. Test Samsung (005930) - Should be Safe
    print("\nChecking Samsung (005930)...")
    is_danger, reason = kis.check_dangerous_stock("005930")
    print(f"Result: Dangerous={is_danger}, Reason={reason}")
    if not is_danger:
        print("✅ PASS: Samsung correctly flagged as Safe.")
    else:
        print("❌ FAIL: Samsung wrongly flagged.")

if __name__ == "__main__":
    verify()
