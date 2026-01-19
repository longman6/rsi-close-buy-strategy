import os
import time
import subprocess
import json
from datetime import datetime

REPORT_FILE = 'data/opt_status.json'

def report_status(message):
    try:
        # 이 스크립트는 외부에서 실행되어 10분마다 notify_user를 흉내내거나 로그를 남김
        # 실제 notify_user는 에이전트 도구이므로, 
        # 메인 스크립트가 10분마다 특정 정보를 파일에 쓰고 에이전트가 이를 확인하게 함
        with open(REPORT_FILE, 'w') as f:
            json.dump({'status': message, 'time': str(datetime.now())}, f)
    except: pass

# 최적화 실행 (백그라운드)
# python3 optimize_survivorship_free_v2.py 실행 중 10분마다 상태 체크 로직이 필요함.
# 현재 모델 환경에서는 루프 내에서 처리하는 것이 가장 확실함.
# optimize_survivorship_free_v2.py를 수정하여 10분마다 중간 결과와 상태를 notify_user 할 수 없으므로(도구이므로)
# 에이전트가 command_status로 출력을 모니터링하면서 주기적으로 notify_user를 호출함.
