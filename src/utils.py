from datetime import datetime
import pytz

def get_now_kst():
    """Get current time in KST (Asia/Seoul)"""
    return datetime.now(pytz.timezone('Asia/Seoul'))
