import finlab
import os
import pandas as pd
from dotenv import load_dotenv

def test_raw_data():
    load_dotenv()
    token = os.getenv('FINLAB_API_TOKEN')
    finlab.login(token)
    
    print("--- Diagnostic Start ---")
    
    # Try to get data by alternative ways or inspect the catalog
    try:
        from finlab import data
        # Let's try to use the English aliases if they exist in your version
        # Or try to get 'price:close' which sometimes works as an alias
        print("Testing 'price:close'...")
        try:
            df = data.get('price:close')
            print(f"SUCCESS: price:close found. Shape: {df.shape}")
        except:
            print("FAILED: price:close")

        # Check what's actually in data.catalog
        print("\nListing first 10 items in data.catalog:")
        try:
            # Depending on version, catalog might be here
            catalog = data.catalog()
            count = 0
            for item in catalog:
                print(f"- {item}")
                count += 1
                if count > 20: break
        except Exception as e:
            print(f"Could not read catalog: {e}")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    test_raw_data()
