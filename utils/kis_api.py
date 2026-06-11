import requests
import json
import os
import time
from datetime import datetime

class KISApi:
    def __init__(self, app_key=None, app_secret=None):
        # 환경변수 로드 (python-dotenv가 없을 경우를 대비해 수동 파싱)
        if os.path.exists('.env'):
            with open('.env', 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
                        
        self.app_key = (app_key or os.getenv("KIS_APP_KEY", "")).strip()
        self.app_secret = (app_secret or os.getenv("KIS_APP_SECRET", "")).strip()
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = ""
        self.token_expiry = 0
        
        # Try to load token from environment or a cache file if needed
        # In a real scenario, we might want to cache this to a file to avoid generating it on every restart
        self._load_token()

    def _load_token(self):
        """Loads token from a local file to avoid frequent re-issuance"""
        token_file = "kis_token.json"
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    data = json.load(f)
                    if data.get("app_key") == self.app_key and time.time() < data.get("expiry", 0):
                        self.access_token = data.get("access_token")
                        self.token_expiry = data.get("expiry")
            except:
                pass

    def _save_token(self):
        """Saves token to a local file"""
        token_file = "kis_token.json"
        try:
            with open(token_file, "w") as f:
                json.dump({
                    "app_key": self.app_key,
                    "access_token": self.access_token,
                    "expiry": self.token_expiry
                }, f)
        except:
            pass

    def get_token(self):
        if not self.app_key or not self.app_secret:
            return None
            
        # Check if token is still valid (add 1 min buffer)
        if self.access_token and time.time() < self.token_expiry - 60:
            return self.access_token

        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body))
            if res.status_code != 200 and "EGW00103" in res.text and "vts" not in self.base_url:
                # Try virtual investment URL if real fails with invalid appkey
                self.base_url = "https://openapivts.koreainvestment.com:29443"
                url = f"{self.base_url}/oauth2/tokenP"
                res = requests.post(url, headers=headers, data=json.dumps(body))
                
            if res.status_code == 200:
                data = res.json()
                self.access_token = data.get("access_token")
                expires_in = data.get("expires_in", 86400)
                self.token_expiry = time.time() + expires_in
                self._save_token()
                return self.access_token
            else:
                print(f"Token Error: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"Error getting KIS token: {e}")
        return None

    def get_investor_trend(self, stock_code):
        token = self.get_token()
        if not token:
            return None

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010900",
            "custtype": "P"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            print(f"Error getting investor trend: {e}")
        return None
