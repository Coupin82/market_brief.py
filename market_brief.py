import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import yfinance as yf
import pandas as pd


# =========================================================
# CONFIG
# =========================================================

ASSETS = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow Jones": "^DJI",
    "Russell 2000": "^RUT",
    "Europe Stoxx 600": "^STOXX",
    "Nikkei 225": "^N225",
    "VIX": "^VIX",
    "US 10Y": "^TNX",
    "Brent": "BZ=F",
    "Gold": "GC=F",
    "DXY": "DX-Y.NYB",
}

SECTOR_ETFS = {
    "Technology": "XLK",
    "Energy": "XLE",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

SMART_MONEY = {
    "SPY": "SPY",
    "Equal Weight S&P": "RSP",
    "QQQ": "QQQ",
    "Small Caps": "IWM",
}

MAJOR_STOCKS = {
    "NVIDIA": "NVDA",
    "Microsoft": "MSFT",
    "Apple": "AAPL",
    "Amazon": "AMZN",
    "Meta": "META",
    "Tesla": "TSLA",
    "Exxon": "XOM",
    "Novo Nordisk": "NVO",
}

EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
EMAIL_TO = os.environ["EMAIL_TO"]


# =========================================================
# HELPERS
# =========================================================

def safe_float(value, decimals=2):
    try:
        return round(float(value), decimals)
    except Exception:
        return None


def fmt_num(value, decimals=2, suffix=""):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.{decimals}f}{suffix}"


def fmt_pct(value):
    if value is None or pd.isna(value):
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def change_class(value):
    if value is None or pd.isna(value):
        return "neutral"
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return "neutral"


def fetch_last_two_closes(ticker):
    try:
        df = yf.download(
            ticker,
            period="7d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if df.empty or "Close" not in df.columns:
            return None, None, None

        close_series = df["Close"].dropna()
        if len(close_series) < 2:
            return None, None, None

        last_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2])
        pct_change = ((last_close - prev_close) / prev_close) * 100 if prev_close else None
        return safe_float(last_close), safe_float(prev_close), safe_float(pct_change)
    except Exception:
        return None, None, None


def fetch_asset_table(asset_dict):
    rows = []
    for name, ticker in asset_dict.items():
        last_close, prev_close, pct_change = fetch_last_two_closes(ticker)
        rows.append(
            {
                "name": name,
                "ticker": ticker,
                "price": last_close,
                "prev_close": prev_close,
                "change_pct": pct_change,
            }
        )
    return pd.DataFrame(rows)


def rank_changes(df, top_n=3, ascending=False):
    valid = df.dropna(subset=["change_pct"]).copy()
    valid = valid.sort_values("change_pct", ascending=ascending)
    return valid.head(top_n)


def market_sentiment(vix, spx_change, ndx_change, us10y_change, brent_change):
    score = 0

    if vix is not None:
        if vix < 15:
            score += 2
        elif vix < 20:
            score += 0
        elif vix < 25:
            score -= 2
        else:
            score -= 3

    for x in [spx_change, ndx_change]:
        if x is not None:
            if x > 1:
                score += 2
            elif x > 0:
                score += 1
            elif x < -1:
                score -= 2
            elif x < 0:
                score -= 1

    if us10y_change is not None:
        if us10y_change > 1:
            score -= 1
        elif us10y_change < -1:
            score += 1

    if brent_change is not None:
        if brent_change > 2:
            score -= 1
        elif brent_change < -2:
            score += 1

    if score >= 3:
        return "🟢 Risk-On", 8
    if score >= 0:
        return "🟡 Neutral", 5
    return "🔴 Risk-Off", 3


def risk_score(vix, us10y_change, brent_change, dxy_change):
    score = 0

    if vix is not None:
        if vix >= 25:
            score += 4
        elif vix >= 20:
            score += 3
        elif vix >= 15:
            score += 2
        else:
            score += 1

    for x in [us10y_change, brent_change, dxy_change]:
        if x is not None:
            if x > 2:
                score += 2
            elif x > 0.5:
                score += 1

    return min(score, 10)


def breadth_proxy_score(spy_change, rsp_change, qqq_change, iwm_change):
    score = 5

    if spy_change is not None and rsp_change is not None:
        if rsp_change >= spy_change:
            score += 2
        else:
            score -= 2

    if qqq_change is not None and iwm_change is not None:
        if iwm_change >= qqq_change:
            score += 2
        else:
            score -= 2

    return max(0, min(score, 10))


def smart_money_comment(spy_change, rsp_change, qqq_change, iwm_change):
    comments = []

    if spy_change is not None and rsp_change is not None:
        if rsp_change > spy_change:
            comments.append("Equal Weight supera al S&P → participación más sana")
        else:
            comments.append("Mega caps pesan más que el mercado amplio")

    if qqq_change is not None and iwm_change is not None:
        if iwm_change > qqq_change:
            comments.append("Small caps resisten mejor que tecnología")
        else:
            comments.append("Tecnología / mega caps resisten mejor que small caps")

    return comments


def tactical_radar(sector_df):
    valid = sector_df.dropna(subset=["change_pct"]).sort_values("change_pct", ascending=False)
    if valid.empty:
        return [], []

    winners = valid.head(3)["name"].tolist()
    losers = valid.tail(3)["name"].tolist()
    return winners, losers


def build_drivers(asset_df, sector_df, sentiment_label):
    drivers = []

    row_map = {row["name"]: row for _, row in asset_df.iterrows()}

    vix = row_map.get("VIX", {}).get("price")
    brent_change = row_map.get("Brent", {}).get("change_pct")
    us10y_change = row_map.get("US 10Y", {}).get("change_pct")
    dxy_change = row_map.get("DXY", {}).get("change_pct")
    spx_change = row_map.get("S&P 500", {}).get("change_pct")
    ndx_change = row_map.get("Nasdaq", {}).get("change_pct")

    if brent_change is not None:
        if brent_change > 2:
            drivers.append("El petróleo sube con fuerza y aumenta la presión inflacionaria")
        elif brent_change < -2:
            drivers.append("El petróleo cae y alivia presión sobre inflación y growth")

    if us10y_change is not None:
        if us10y_change > 1:
            drivers.append("El bono USA a 10 años repunta y presiona valoraciones")
        elif us10y_change < -1:
            drivers.append("Los yields bajan y apoyan activos de duración larga")

    if dxy_change is not None:
        if dxy_change > 0.5:
            drivers.append("El dólar gana fuerza y endurece condiciones financieras")
        elif dxy_change < -0.5:
            drivers.append("El dólar se relaja y favorece apetito por riesgo")

    if vix is not None:
        if vix >= 20:
            drivers.append("La volatilidad sigue alta y el mercado está sensible a noticias")
        elif vix < 15:
            drivers.append("La volatilidad sigue contenida y el mercado opera con calma")

    if spx_change is not None and ndx_change is not None:
        if ndx_change > spx_change + 0.5:
            drivers.append("Tecnología lidera frente al mercado amplio")
        elif spx_change > ndx_change + 0.5:
            drivers.append("La subida es menos dependiente de tecnología")

    if not drivers:
        drivers.append(f"Sesión de tono {sentiment_label.replace('🟢 ', '').replace('🟡 ', '').replace('🔴 ', '').lower()} sin un driver dominante claro")

    return drivers[:4]


def build_conclusion(sentiment_label, pulse_score, risk, breadth, winners, losers, smart_comments):
    lines = []

    if "Risk-On" in sentiment_label:
        lines.append("Mercado en modo Risk-On.")
    elif "Neutral" in sentiment_label:
        lines.append("Mercado en modo neutral, sin una dirección completamente clara.")
    else:
        lines.append("Mercado en modo Risk-Off.")

    if breadth >= 7:
        lines.append("La participación interna es saludable y la subida parece más amplia.")
    elif breadth <= 3:
        lines.append("La participación interna es débil y el movimiento parece concentrado.")
    else:
        lines.append("La amplitud del mercado es mixta.")

    if risk >= 7:
        lines.append("El bloque de riesgo sigue elevado y conviene prudencia táctica.")
    elif risk <= 3:
        lines.append("El bloque de riesgo es contenido.")
    else:
        lines.append("El nivel de riesgo es moderado.")

    if winners:
        lines.append(f"Fortaleza táctica en: {', '.join(winners[:2])}.")
    if losers:
        lines.append(f"Debilidad relativa en: {', '.join(losers[:2])}.")

    if smart_comments:
        lines.append(smart_comments[0] + ".")

    return " ".join(lines)


def html_table_from_df(df, title, columns):
    rows_html = ""
    for _, row in df.iterrows():
        rows_html += "<tr>"
        for col in columns:
            value = row[col]
            cls = ""
            if col == "change_pct":
                cls = change_class(value)
                value = fmt_pct(value)
            elif col == "price":
                value = fmt_num(value)
            rows_html += f'<td class="{cls}">{value}</td>'
        rows_html += "</tr>"

    return f"""
    <div class="card">
      <h3>{title}</h3>
      <table>
        <thead>
          <tr>
            {''.join(f"<th>{c}</th>" for c in columns)}
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
    """


# =========================================================
# DATA
# =========================================================

asset_df = fetch_asset_table(ASSETS)
sector_df = fetch_asset_table(SECTOR_ETFS)
smart_df = fetch_asset_table(SMART_MONEY)
stocks_df = fetch_asset_table(MAJOR_STOCKS)

asset_map = {row["name"]: row for _, row in asset_df.iterrows()}
smart_map = {row["name"]: row for _, row in smart_df.iterrows()}

spx_change = asset_map.get("S&P 500", {}).get("change_pct")
ndx_change = asset_map.get("Nasdaq", {}).get("change_pct")
vix_value = asset_map.get("VIX", {}).get("price")
us10y_change = asset_map.get("US 10Y", {}).get("change_pct")
brent_change = asset_map.get("Brent", {}).get("change_pct")
dxy_change = asset_map.get("DXY", {}).get("change_pct")

sentiment_label, pulse_score = market_sentiment(
    vix=vix_value,
    spx_change=spx_change,
    ndx_change=ndx_change,
    us10y_change=us10y_change,
    brent_change=brent_change,
)

risk = risk_score(
    vix=vix_value,
    us10y_change=us10y_change,
    brent_change=brent_change,
    dxy_change=dxy_change,
)

breadth = breadth_proxy_score(
    spy_change=smart_map.get("SPY", {}).get("change_pct"),
    rsp_change=smart_map.get("Equal Weight S&P", {}).get("change_pct"),
    qqq_change=smart_map.get("QQQ", {}).get("change_pct"),
    iwm_change=smart_map.get("Small Caps", {}).get("change_pct"),
)

drivers = build_drivers(asset_df, sector_df, sentiment_label)
smart_comments = smart_money_comment(
    spy_change=smart_map.get("SPY", {}).get("change_pct"),
    rsp_change=smart_map.get("Equal Weight S&P", {}).get("change_pct"),
    qqq_change=smart_map.get("QQQ", {}).get("change_pct"),
    iwm_change=smart_map.get("Small Caps", {}).get("change_pct"),
)

sector_winners_df = rank_changes(sector_df, top_n=3, ascending=False)
sector_losers_df = rank_changes(sector_df, top_n=3, ascending=True)
stock_winners_df = rank_changes(stocks_df, top_n=3, ascending=False)
stock_losers_df = rank_changes(stocks_df, top_n=3, ascending=True)

winners, losers = tactical_radar(sector_df)

conclusion = build_conclusion(
    sentiment_label=sentiment_label,
    pulse_score=pulse_score,
    risk=risk,
    breadth=breadth,
    winners=winners,
    losers=losers,
    smart_comments=smart_comments,
)

today = datetime.utcnow().strftime("%d %B %Y")
now_utc = datetime.utcnow().strftime("%H:%M UTC")


# =========================================================
# HTML
# =========================================================

summary_cards = f"""
<div class="summary-grid">
  <div class="summary-card">
    <div class="label">Sentimiento</div>
    <div class="value">{sentiment_label}</div>
  </div>
  <div class="summary-card">
    <div class="label">Market Pulse Score</div>
    <div class="value">{pulse_score}/10</div>
  </div>
  <div class="summary-card">
    <div class="label">Risk Score</div>
    <div class="value">{risk}/10</div>
  </div>
  <div class="summary-card">
    <div class="label">Breadth Proxy</div>
    <div class="value">{breadth}/10</div>
  </div>
</div>
"""

drivers_html = "".join([f"<li>{d}</li>" for d in drivers])
smart_html = "".join([f"<li>{s}</li>" for s in smart_comments])

market_pulse_df = asset_df[["name", "price", "change_pct"]].copy()
market_pulse_df.columns = ["Activo", "Precio", "Cambio %"]

sector_winners_html = html_table_from_df(
    sector_winners_df.rename(columns={"name": "Sector", "price": "Precio", "change_pct": "Cambio %"}),
    "Sectores ganadores",
    ["Sector", "Precio", "Cambio %"],
)

sector_losers_html = html_table_from_df(
    sector_losers_df.rename(columns={"name": "Sector", "price": "Precio", "change_pct": "Cambio %"}),
    "Sectores débiles",
    ["Sector", "Precio", "Cambio %"],
)

stock_winners_html = html_table_from_df(
    stock_winners_df.rename(columns={"name": "Acción", "price": "Precio", "change_pct": "Cambio %"}),
    "Acciones destacadas al alza",
    ["Acción", "Precio", "Cambio %"],
)

stock_losers_html = html_table_from_df(
    stock_losers_df.rename(columns={"name": "Acción", "price": "Precio", "change_pct": "Cambio %"}),
    "Acciones destacadas a la baja",
    ["Acción", "Precio", "Cambio %"],
)

market_rows = ""
for _, row in market_pulse_df.iterrows():
    market_rows += f"""
    <tr>
      <td>{row["Activo"]}</td>
      <td>{fmt_num(row["Precio"])}</td>
      <td class="{change_class(row["Cambio %"])}">{fmt_pct(row["Cambio %"])}</td>
    </tr>
    """

smart_rows = ""
for _, row in smart_df.iterrows():
    smart_rows += f"""
    <tr>
      <td>{row["name"]}</td>
      <td>{fmt_num(row["price"])}</td>
      <td class="{change_class(row["change_pct"])}">{fmt_pct(row["change_pct"])}</td>
    </tr>
    """

html = f"""
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      font-family: Arial, Helvetica, sans-serif;
      background: #f5f7fb;
      margin: 0;
      padding: 24px;
      color: #1f2937;
    }}
    .container {{
      max-width: 980px;
      margin: 0 auto;
      background: white;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 6px 20px rgba(0,0,0,0.08);
    }}
    .header {{
      background: #0f172a;
      color: white;
      padding: 28px 32px;
    }}
    .header h1 {{
      margin: 0 0 8px 0;
      font-size: 28px;
    }}
    .header p {{
      margin: 0;
      color: #cbd5e1;
      font-size: 14px;
    }}
    .content {{
      padding: 24px 24px 8px 24px;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .summary-card {{
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 16px;
    }}
    .summary-card .label {{
      font-size: 12px;
      text-transform: uppercase;
      color: #64748b;
      margin-bottom: 8px;
    }}
    .summary-card .value {{
      font-size: 22px;
      font-weight: bold;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 16px;
    }}
    h2 {{
      margin: 0 0 14px 0;
      font-size: 20px;
    }}
    h3 {{
      margin: 0 0 12px 0;
      font-size: 18px;
    }}
    p {{
      line-height: 1.5;
    }}
    ul {{
      padding-left: 20px;
      margin: 8px 0 0 0;
    }}
    li {{
      margin-bottom: 6px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th {{
      text-align: left;
      background: #f8fafc;
      padding: 10px;
      border-bottom: 1px solid #e5e7eb;
    }}
    td {{
      padding: 10px;
      border-bottom: 1px solid #eef2f7;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }}
    .pos {{
      color: #15803d;
      font-weight: bold;
    }}
    .neg {{
      color: #b91c1c;
      font-weight: bold;
    }}
    .neutral {{
      color: #475569;
      font-weight: bold;
    }}
    .footer {{
      padding: 0 24px 24px 24px;
      color: #64748b;
      font-size: 12px;
    }}
    @media (max-width: 800px) {{
      .summary-grid {{
        grid-template-columns: 1fr 1fr;
      }}
      .grid-2 {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📊 Market Intelligence Brief</h1>
      <p>{today} · {now_utc} · Último cierre disponible / snapshot reciente</p>
    </div>

    <div class="content">
      {summary_cards}

      <div class="card">
        <h3>Market Pulse</h3>
        <table>
          <thead>
            <tr>
              <th>Activo</th>
              <th>Precio</th>
              <th>Cambio %</th>
            </tr>
          </thead>
          <tbody>
            {market_rows}
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>Drivers del mercado</h3>
        <ul>
          {drivers_html}
        </ul>
      </div>

      <div class="card">
        <h3>Smart Money / amplitud proxy</h3>
        <table>
          <thead>
            <tr>
              <th>Indicador</th>
              <th>Precio</th>
              <th>Cambio %</th>
            </tr>
          </thead>
          <tbody>
            {smart_rows}
          </tbody>
        </table>
        <ul>
          {smart_html}
        </ul>
      </div>

      <div class="grid-2">
        {sector_winners_html}
        {sector_losers_html}
      </div>

      <div class="grid-2">
        {stock_winners_html}
        {stock_losers_html}
      </div>

      <div class="card">
        <h3>Radar táctico</h3>
        <p><b>Momentum:</b> {", ".join(winners) if winners else "N/A"}</p>
        <p><b>Debilidad:</b> {", ".join(losers) if losers else "N/A"}</p>
      </div>

      <div class="card">
        <h3>Conclusión táctica</h3>
        <p>{conclusion}</p>
      </div>
    </div>

    <div class="footer">
      Generado automáticamente con GitHub Actions. 
      Fuente principal de mercado: Yahoo Finance vía yfinance.
    </div>
  </div>
</body>
</html>
"""


# =========================================================
# EMAIL SEND
# =========================================================

msg = MIMEMultipart("alternative")
msg["Subject"] = "📊 Market Intelligence Brief"
msg["From"] = EMAIL_USER
msg["To"] = EMAIL_TO

msg.attach(MIMEText(html, "html"))

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(EMAIL_USER, EMAIL_PASS)
server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
server.quit()

print("Email sent successfully")
