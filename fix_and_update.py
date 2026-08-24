"""Fix SSL cert issue and run stock update"""
import os, sys
os.environ['SSL_CERT_FILE'] = 'C:/Users/林皇辰/AppData/Local/hermes/hermes-agent/venv/Lib/site-packages/certifi/cacert.pem'
os.environ['REQUESTS_CA_BUNDLE'] = 'C:/Users/林皇辰/AppData/Local/hermes/hermes-agent/venv/Lib/site-packages/certifi/cacert.pem'

sys.path.insert(0, 'app')
from market_scanner import MarketScanner

ms = MarketScanner()
# Update only price data (skip finlab since it already ran)
token = open('.env').read().split('FINLAB_API_TOKEN=')[1].split('\n')[0].strip()
result = ms.update_market_snapshot_finlab(token)
print(f'Update result: {result}')
