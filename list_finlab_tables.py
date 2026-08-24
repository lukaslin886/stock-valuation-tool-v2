import finlab
import os
import json
from dotenv import load_dotenv

def list_datasets():
    load_dotenv()
    token = os.getenv('FINLAB_API_TOKEN')
    finlab.login(token)
    
    try:
        # FinLab internal API access might vary by version
        # Let's try to get common tables available for free users
        print("Checking common free tables...")
        test_keys = [
            'price:收盤價',
            'financial_statement:綜合損益表',
            'financial_statement:資產負債表',
            'financial_statement:現金流量表',
            'taiwan_stock_info',
            'taiwan_stock_financial_info'
        ]
        
        for k in test_keys:
            try:
                finlab.data.get(k)
                print(f"[YES] {k}")
            except:
                print(f"[ NO] {k}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_datasets()
