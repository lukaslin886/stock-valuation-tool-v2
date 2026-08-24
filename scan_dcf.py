"""
台股 DCF 估值掃描 — 使用 yfinance
直接使用已安裝的 Hermes venv 套件
"""
import yfinance as yf
import numpy as np
import sys

# 台股50候選
STOCKS = [
    ("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科"),
    ("2412", "中華電"), ("2882", "國泰金"), ("2881", "富邦金"),
    ("2886", "兆豐金"), ("2891", "中信金"), ("2885", "元大金"),
    ("2884", "玉山金"), ("2890", "永豐金"), ("2887", "台新金"),
    ("1301", "台塑"), ("1303", "南亞"), ("2308", "台達電"),
    ("2002", "中鋼"), ("2603", "長榮"), ("2609", "陽明"),
    ("3008", "大立光"), ("2357", "華碩"), ("2382", "廣達"),
    ("2303", "聯電"), ("3711", "日月光"), ("3034", "聯詠"),
    ("2379", "瑞昱"), ("3231", "緯創"), ("2301", "光寶科"),
    ("4938", "和碩"), ("1216", "統一"), ("2207", "和泰車"),
    ("2912", "統一超"), ("1326", "台化"), ("1101", "台泥"),
    ("5880", "合庫金"), ("2892", "第一金"), ("2883", "開發金"),
    ("1590", "亞德客-KY"), ("9910", "豐泰"), ("2474", "可成"),
    ("2105", "正新"), ("3706", "神達"), ("2395", "研華"),
    ("5347", "世界"), ("6415", "矽力-KY"), ("2812", "台中銀"),
]

def get_eps(ticker):
    try:
        info = ticker.info
        eps = info.get("trailingEps") or info.get("forwardEps")
        if eps and eps > 0:
            return eps
    except:
        pass
    return None

def estimate_dcf(eps, g=0.10, years=5, tg=0.03, dr=0.10):
    if not eps or eps <= 0:
        return None, None, None
    cf_l = [eps * (1.05)**y / (1+dr)**y for y in range(1, years+1)]
    cf_m = [eps * (1.10)**y / (1+dr)**y for y in range(1, years+1)]
    cf_h = [eps * (1.15)**y / (1+dr)**y for y in range(1, years+1)]
    tv_l = cf_l[-1] * (1+tg) / (dr-tg) / (1+dr)**years
    tv_m = cf_m[-1] * (1+tg) / (dr-tg) / (1+dr)**years
    tv_h = cf_h[-1] * (1+tg) / (dr-tg) / (1+dr)**years
    return sum(cf_l)+tv_l, sum(cf_m)+tv_m, sum(cf_h)+tv_h

results = []
print("掃描台股50 中，請稍候...")
print("=" * 75)

for code, name in STOCKS:
    try:
        tk = yf.Ticker(f"{code}.TW")
        hist = tk.history(period="6mo")
        if hist.empty:
            tk = yf.Ticker(f"{code}.TWO")
            hist = tk.history(period="6mo")
        if hist.empty:
            continue

        price = hist["Close"].iloc[-1]
        eps = get_eps(tk)
        if not eps:
            continue

        dcf_l, dcf_m, dcf_h = estimate_dcf(eps)
        upside = (dcf_m - price) / price
        h52 = hist["Close"].max()
        l52 = hist["Close"].min()
        pe = price / eps if eps else 0

        results.append((code, name, price, eps, pe, dcf_l, dcf_m, dcf_h, upside, h52, l52))
        print(f"  {code} {name:6s}  價={price:>7.1f}  EPS={eps:>5.2f}  PE={pe:>5.1f}  DCF={dcf_m:>7.0f} 潛力={upside:>+6.1%}")
    except Exception as e:
        pass

if not results:
    print("\n⚠ 無法取得數據，可能為網路問題")
    sys.exit(0)

results.sort(key=lambda r: r[8], reverse=True)

print("\n" + "=" * 75)
print("📊 DCF 估值結果（中性預估，漲幅排序）")
print("=" * 75)
print(f"{'代碼':>5} {'名稱':<7} {'股價':>7} {'EPS':>6} {'PE':>5} {'DCF低':>7} {'DCF中':>7} {'DCF高':>7} {'潛力':>7}  {'52高':>7} {'52低':>7}")
print("-" * 75)
for code, name, price, eps, pe, dcf_l, dcf_m, dcf_h, upside, h52, l52 in results:
    flag = "🟢" if upside > 0.20 else ("🟡" if upside > 0.05 else "⚪")
    print(f"{code:>5} {name:<7} {price:>7.1f} {eps:>6.2f} {pe:>5.1f} {dcf_l:>7.0f} {dcf_m:>7.0f} {dcf_h:>7.0f} {upside:>+6.1%}  {h52:>7.1f} {l52:>7.1f} {flag}")

print("\n" + "=" * 75)

# 買進建議
buys = [r for r in results if r[8] > 0.20]
watches = [r for r in results if 0.05 < r[8] <= 0.20]

print(f"\n🟢 買進建議（潛力 > 20%）— {len(buys)} 檔")
if buys:
    for r in buys:
        print(f"  🟢 {r[0]} {r[1]} — 股價 {r[2]:.1f} / DCF {r[6]:.0f} / 潛在漲幅 {r[8]:+.1%}")
else:
    print("  目前無顯著低估標的")

print(f"\n🟡 觀察清單（潛力 5%~20%）— {len(watches)} 檔")
if watches:
    for r in watches:
        print(f"  🟡 {r[0]} {r[1]} — 股價 {r[2]:.1f} / DCF {r[6]:.0f} / 潛在漲幅 {r[8]:+.1%}")
else:
    print("  無")
