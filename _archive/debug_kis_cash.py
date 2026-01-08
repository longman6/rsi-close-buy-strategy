from src.kis_client import KISClient
import json

kis = KISClient()
# Manually run the request logic from get_buyable_cash to see full output
path = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
tr_id = "VTTC8908R" if kis.is_mock else "TTTC8908R"

params = {
    "CANO": kis.account_no,
    "ACNT_PRDT_CD": "01",
    "PDNO": "005930", 
    "ORD_UNPR": "0",
    "ORD_DVSN": "01",
    "CMA_EVLU_AMT_ICLD_YN": "Y",
    "OVRS_ICLD_YN": "N"
}

res = kis._send_request("GET", path, tr_id, params=params)
if res and res.status_code == 200:
    data = res.json()
    print(json.dumps(data['output'], indent=4, ensure_ascii=False))
else:
    print("Error")
