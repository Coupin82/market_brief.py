import yfinance as yf
import pandas as pd
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime

# --------- TICKERS ----------
tickers = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Russell 2000": "^RUT",
    "VIX": "^VIX",
    "Brent": "BZ=F",
    "Gold": "GC=F",
    "US10Y": "^TNX",
    "DXY": "DX-Y.NYB"
}

# --------- DOWNLOAD DATA ----------
data = {}

for name, ticker in tickers.items():
    df = yf.download(ticker, period="2d", interval="1d", progress=False)
    if len(df) >= 2:
        change = (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100
        data[name] = {
            "price": round(df["Close"].iloc[-1], 2),
            "change": round(change, 2)
        }
    else:
        data[name] = {"price": "N/A", "change": "N/A"}

# --------- SENTIMENT ----------
vix = data["VIX"]["price"]

if isinstance(vix, float):
    if vix < 15:
        sentiment = "🟢 Risk-On"
    elif vix < 20:
        sentiment = "🟡 Neutral"
    else:
        sentiment = "🔴 Risk-Off"
else:
    sentiment = "Unknown"

# --------- HTML EMAIL ----------
today = datetime.utcnow().strftime("%d %B %Y")

html = f"""
<h2>📊 Market Intelligence Brief</h2>
<p><b>Date:</b> {today}</p>

<h3>Market Pulse</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Asset</th><th>Price</th><th>Change %</th></tr>
<tr><td>S&P 500</td><td>{data["S&P 500"]["price"]}</td><td>{data["S&P 500"]["change"]}%</td></tr>
<tr><td>Nasdaq</td><td>{data["Nasdaq"]["price"]}</td><td>{data["Nasdaq"]["change"]}%</td></tr>
<tr><td>Russell 2000</td><td>{data["Russell 2000"]["price"]}</td><td>{data["Russell 2000"]["change"]}%</td></tr>
<tr><td>VIX</td><td>{data["VIX"]["price"]}</td><td>{data["VIX"]["change"]}%</td></tr>
<tr><td>Brent</td><td>{data["Brent"]["price"]}</td><td>{data["Brent"]["change"]}%</td></tr>
<tr><td>Gold</td><td>{data["Gold"]["price"]}</td><td>{data["Gold"]["change"]}%</td></tr>
<tr><td>US 10Y</td><td>{data["US10Y"]["price"]}</td><td>{data["US10Y"]["change"]}%</td></tr>
<tr><td>DXY</td><td>{data["DXY"]["price"]}</td><td>{data["DXY"]["change"]}%</td></tr>
</table>

<h3>Sentiment</h3>
<p>{sentiment}</p>

<h3>Conclusion</h3>
<p>
This automatic briefing summarizes overnight market conditions.
High VIX typically signals increased risk in equities,
while rising yields and oil prices can pressure growth assets.
</p>
"""

# --------- EMAIL CONFIG ----------
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
EMAIL_TO = os.environ["EMAIL_TO"]

msg = MIMEText(html, "html")
msg["Subject"] = "📊 Market Intelligence Brief"
msg["From"] = EMAIL_USER
msg["To"] = EMAIL_TO

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(EMAIL_USER, EMAIL_PASS)
server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
server.quit()

print("Email sent successfully")
