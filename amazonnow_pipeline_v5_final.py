"""
AmazonNow Dashboard Pipeline — v5
Fixes:
- City screenshot captures ONLY that city's section
- Dark/Light theme toggle
- Shadowfax branding colors throughout
- BTS% and BTO% with correct city-level formula (AC col filter)
- Added BTO count column (raw count)
- FOD fixed: DAU Base A=date AND I=date (same date = new rider)
- Horizontal scroll fix for wide table
- Live vs Shared city subtotals with AS=Live/Shared filter
- Fascinating visual design with Shadowfax teal
"""

import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

KEY_FILE      = 'amazonnow-dashboard-4499c556ed67.json'
SHEET_URL     = 'https://docs.google.com/spreadsheets/d/1OA7vbJ9Ngps78-YSeDZcZ7iQaEPheyJwSSHCtKl7JzY'
BASE_DUMP_TAB = 'Base Dump'
DAU_BASE_TAB  = 'DAU Base'
OUTPUT_HTML   = 'amazonnow_dashboard_live.html'
TODAY         = date.today()
YESTERDAY     = TODAY - timedelta(days=1)

# ── CONNECT ──────────────────────────────
print("[1/5] Connecting...")
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/drive.readonly']
creds  = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
sheet  = client.open_by_url(SHEET_URL)

print("[2/5] Loading Base Dump...")
base_raw = sheet.worksheet(BASE_DUMP_TAB).get_all_values()
base_df  = pd.DataFrame(base_raw[1:], columns=base_raw[0])
print(f"      {len(base_df)} rows")

print("[3/5] Loading DAU Base...")
dau_raw = sheet.worksheet(DAU_BASE_TAB).get_all_values()
dau_df  = pd.DataFrame(dau_raw[1:], columns=dau_raw[0])
print(f"      {len(dau_df)} rows | cols: {list(dau_df.columns[:10])}")

# ── COLUMN MAPPING ────────────────────────
C     = 'Hub_name'
G     = 'order_status'
H     = 'current_order_status'
I_COL = 'rider_id'
M     = 'creation_Date'
N     = 'creation_time'
O_COL = 'Accept_time'
Q     = 'Picked_Time'
R_COL = 'CX_doorstep_time'
W     = 'Creation_to_Accept'
AC    = 'City_name'
AG    = 'Breach'
AH    = 'BAGS_PACKED_READY_FOR_PICKUP'
AI    = 'LM'
AQ    = 'Delay'
AS_COL= 'Live/Non-Live'
AX    = 'Return Delay'

DAU_DATE  = dau_df.columns[0]   # A
DAU_CITY  = dau_df.columns[1]   # B
DAU_HUB   = dau_df.columns[2]   # C
DAU_RIDER = dau_df.columns[3]   # D
DAU_HRS   = dau_df.columns[6]   # G
DAU_FOD   = dau_df.columns[8]   # I — fod date
DAU_LIVE  = dau_df.columns[9]   # J

# ── DATE PARSE ───────────────────────────
base_df['_date'] = pd.to_datetime(base_df[M], errors='coerce', dayfirst=False).dt.date
dau_df['_date']  = pd.to_datetime(dau_df[DAU_DATE], errors='coerce', dayfirst=False).dt.date
dau_df[DAU_HRS]  = pd.to_numeric(dau_df[DAU_HRS], errors='coerce').fillna(0)
dau_df['_fod_date'] = pd.to_datetime(dau_df[DAU_FOD], errors='coerce', dayfirst=False).dt.date

for col in [N, O_COL, Q, R_COL, AH]:
    base_df[col] = pd.to_datetime(base_df[col], errors='coerce', dayfirst=False)
base_df[W]  = pd.to_numeric(base_df[W],  errors='coerce')
base_df[AI] = pd.to_numeric(base_df[AI], errors='coerce')

avail = sorted(base_df['_date'].dropna().unique())
print(f"      Dates available: {avail[-5:]}")
if TODAY not in avail:
    TODAY     = avail[-1] if avail else YESTERDAY
    YESTERDAY = avail[-2] if len(avail) >= 2 else TODAY - timedelta(days=1)
    print(f"      Shifted: TODAY={TODAY}, YESTERDAY={YESTERDAY}")

print(f"\n[4/5] Calculating metrics...")

# ── METRIC CALC ──────────────────────────
def calc_metrics(d, dau_sub, report_date):
    opd       = len(d)
    del_df    = d[d[H] == 'DELIVERED']
    del_count = len(del_df)
    dau       = d[I_COL].nunique()
    login_gt35 = dau_sub[dau_sub[DAU_HRS] > 3.5][DAU_RIDER].nunique()

    # OR2A p75 — (Accept - creation)*1440, 0-120min
    try:
        or2a = ((d[O_COL]-d[N]).dt.total_seconds()/60).dropna()
        or2a = or2a[(or2a>=0)&(or2a<=120)]
        or2a_p75 = round(float(np.percentile(or2a,75)),2) if len(or2a)>0 else 0.0
    except: or2a_p75 = 0.0

    # S2P p75
    try:
        s2p = ((d[Q]-d[AH]).dt.total_seconds()/60).dropna()
        s2p = s2p[s2p>0]
        s2p_p75 = round(float(np.percentile(s2p,75)),2) if len(s2p)>0 else 0.0
    except: s2p_p75 = 0.0

    # Cr->Pack (order_status==4)
    try:
        d4 = d[pd.to_numeric(d[G],errors='coerce')==4]
        ctp = ((d4[AH]-d4[N]).dt.total_seconds()/60).dropna()
        ctp = ctp[(ctp>=0)&(ctp<=120)]
        avg_crpack = round(float(ctp.mean()),2) if len(ctp)>0 else 0.0
    except: avg_crpack = 0.0

    # Cr->Geo (order_status==4)
    try:
        ctg = ((d4[R_COL]-d4[N]).dt.total_seconds()/60).dropna()
        ctg = ctg[(ctg>=0)&(ctg<=120)]
        avg_crgeo = round(float(ctg.mean()),2) if len(ctg)>0 else 0.0
    except: avg_crgeo = 0.0

    # DPH
    total_hrs = dau_sub[DAU_HRS].sum()
    dph = round(opd/total_hrs,2) if total_hrs>0 else 0.0

    # Avg LM
    lm_vals = d[AI].dropna()
    avg_lm = round(float(lm_vals.mean()),2) if len(lm_vals)>0 else 0.0

    # OTP+3
    breach_del = len(del_df[del_df[AG]=='Breach'])
    otp3 = round((del_count-breach_del)/del_count*100,2) if del_count>0 else 0.0

    # Store/Rider delay using AQ col
    sd_n = len(d[(d[H]=='DELIVERED')&(d[AG]=='Breach')&(d[AQ].str.strip().str.lower()=='store_delay')])
    rd_n = len(d[(d[H]=='DELIVERED')&(d[AG]=='Breach')&(d[AQ].str.strip().str.lower()=='rider_delay')])
    store_delay  = round(sd_n/del_count*100,2) if del_count>0 else 0.0
    rider_delay  = round(rd_n/del_count*100,2) if del_count>0 else 0.0

    # Breach count
    breach_count = len(d[d[AG]=='Breach'])

    # BTS% = COUNTIFS(AX="Delay", AC=city/C=hub, M=date) / OPD
    bts_n   = len(d[d[AX].astype(str).str.strip().str.lower()=='delay'])
    bts_pct = round(bts_n/opd*100,2) if opd>0 else 0.0

    # BTO count = COUNTIFS(M=date, G=24, C/AC=filter)
    bto_n   = len(d[pd.to_numeric(d[G],errors='coerce')==24])
    bto_pct = round(bto_n/opd*100,2) if opd>0 else 0.0

    # DSR
    dsr_n = len(d[~d[H].isin(['CANCELLED','RTSD'])])
    dsr   = round(dsr_n/opd*100,2) if opd>0 else 0.0

    # FOD — DAU Base A=report_date AND I=report_date for this hub/city
    # =COUNTIFS(DAU!C=hub, DAU!A=date, DAU!I=date)
    fod = int(len(dau_sub[
        (dau_sub['_date'] == report_date) &
        (dau_sub['_fod_date'] == report_date)
    ]))

    return dict(opd=opd, delivered=del_count, dau=dau, login=login_gt35,
                or2a=or2a_p75, s2p=s2p_p75, crpack=avg_crpack, crgeo=avg_crgeo,
                dph=dph, lm=avg_lm, otp3=otp3, sd=store_delay, rd=rider_delay,
                breach=breach_count, bts=bts_pct, bto_n=bto_n, bto=bto_pct,
                dsr=dsr, fod=fod)

def build_all(report_date):
    df      = base_df[base_df['_date']==report_date].copy()
    dau_day = dau_df[dau_df['_date']==report_date].copy()
    print(f"      [{report_date}] rows={len(df)}, dau={len(dau_day)}")
    if len(df)==0: return None

    # Non-live
    nonlive_dau = dau_day[dau_day[DAU_LIVE].str.strip().str.lower().str.contains('non',na=False)]
    nonlive_hubs=[]
    for hub,grp in nonlive_dau.groupby(DAU_HUB):
        fod = int(len(grp[(grp['_date']==report_date)&(grp['_fod_date']==report_date)]))
        nonlive_hubs.append({'hub':hub,'city':grp[DAU_CITY].iloc[0] if len(grp)>0 else '',
            'dau':grp[DAU_RIDER].nunique(),'login':grp[grp[DAU_HRS]>3.5][DAU_RIDER].nunique(),
            'avg_hrs':round(grp[DAU_HRS].mean(),1),'fod':fod})
    nonlive_hubs.sort(key=lambda x:(x['city'],x['hub']))

    # Hub results
    results=[]
    for hub in sorted(df[C].unique()):
        hdf = df[df[C]==hub]
        hdau= dau_day[dau_day[DAU_HUB]==hub]
        m   = calc_metrics(hdf, hdau, report_date)
        m['hub']  = hub
        m['city'] = hdf[AC].iloc[0] if AC in hdf.columns and len(hdf)>0 else 'Unknown'
        ls = hdf[AS_COL].str.strip().str.lower() if AS_COL in hdf.columns else pd.Series(['live'])
        m['store_type'] = 'Shared' if ls.str.contains('shared',na=False).any() else 'Live'
        results.append(m)
    results.sort(key=lambda x:(x['city'],x['store_type'],x['hub']))
    for i,r in enumerate(results): r['sl']=i+1

    # City subtotals — directly from df filtered by city (and optionally AS col)
    def city_sub(city, store_type_filter=None):
        cdf = df[df[AC]==city] if AC in df.columns else df
        if store_type_filter=='Live':
            cdf = cdf[~cdf[AS_COL].str.strip().str.lower().str.contains('shared',na=False)]
        elif store_type_filter=='Shared':
            cdf = cdf[cdf[AS_COL].str.strip().str.lower().str.contains('shared',na=False)]
        cdau = dau_day[dau_day[DAU_CITY]==city] if DAU_CITY in dau_day.columns else dau_day
        if store_type_filter=='Live':
            cdau = cdau[~cdau[DAU_LIVE].str.strip().str.lower().str.contains('shared',na=False) &
                        ~cdau[DAU_LIVE].str.strip().str.lower().str.contains('non',na=False)]
        elif store_type_filter=='Shared':
            cdau = cdau[cdau[DAU_LIVE].str.strip().str.lower().str.contains('shared',na=False)]
        return calc_metrics(cdf, cdau, report_date) if len(cdf)>0 else None

    cities = sorted(set(r['city'] for r in results))
    ct_all    = {c: city_sub(c)          for c in cities}
    ct_live   = {c: city_sub(c,'Live')   for c in cities}
    ct_shared = {c: city_sub(c,'Shared') for c in cities}

    # Grand totals
    live_df   = df[~df[AS_COL].str.strip().str.lower().str.contains('shared',na=False)] if AS_COL in df.columns else df
    shared_df = df[df[AS_COL].str.strip().str.lower().str.contains('shared',na=False)] if AS_COL in df.columns else pd.DataFrame()
    live_dau  = dau_day[~dau_day[DAU_LIVE].str.strip().str.lower().str.contains('shared|non',na=False,regex=True)]
    sh_dau    = dau_day[dau_day[DAU_LIVE].str.strip().str.lower().str.contains('shared',na=False)]
    all_dau   = dau_day[~dau_day[DAU_LIVE].str.strip().str.lower().str.contains('non',na=False)]

    gt_all    = calc_metrics(df,        all_dau,  report_date)
    gt_live   = calc_metrics(live_df,   live_dau, report_date)
    gt_shared = calc_metrics(shared_df, sh_dau,   report_date) if len(shared_df)>0 else {k:0 for k in gt_all}
    gt_comb   = gt_all

    live_res   = [r for r in results if r['store_type']=='Live']
    shared_res = [r for r in results if r['store_type']=='Shared']

    return dict(results=results, live_res=live_res, shared_res=shared_res,
                nonlive_hubs=nonlive_hubs, cities=cities,
                ct_all=ct_all, ct_live=ct_live, ct_shared=ct_shared,
                gt_all=gt_all, gt_live=gt_live, gt_shared=gt_shared, gt_comb=gt_comb,
                report_date=report_date)

D_TODAY = build_all(TODAY)
D_YEST  = build_all(YESTERDAY)

print(f"\n[5/5] Generating HTML...")

# ── RAG ──────────────────────────────────
def rag_otp(v):
    if v>=95: return 'vg'
    if v>=90: return 'va'
    if v>=85: return 'vlr'
    return 'vr'
def rag_delay(v):
    return 'vg' if v<2 else ('va' if v<=5 else 'vr')
def rag_or2a(v): return 'vr' if v>0.5 else 'vg'
def rag_s2p(v):  return 'vr' if v>0.75 else 'vg'
def status_pill(r):
    if r['otp3']<85 or r['rd']>5:  return '<span class="pill r">alert</span>'
    if r['otp3']<90 or r['rd']>2:  return '<span class="pill a">watch</span>'
    return '<span class="pill g">good</span>'

CITY_COLORS={'Mumbai':'#3b82f6','Pune':'#8b5cf6','Chennai':'#10b981',
    'Hyderabad':'#f59e0b','Gurgaon':'#ef4444','Delhi':'#06b6d4',
    'Meerut':'#ec4899','Faridabad':'#f97316','Jaipur':'#84cc16',
    'Bengaluru':'#a855f7','Chandigarh':'#14b8a6','Unknown':'#6b7a99'}

def hs(hub): return hub.split('_ANow_')[0].replace('_',' ') if '_ANow_' in hub else hub

TABLE_HEAD='''<thead><tr>
  <th>#</th><th>Hub</th><th>OPD</th><th>Del</th><th>DAU</th><th>Login&gt;3.5h</th>
  <th>OR2A p75</th><th>S2P p75</th><th>Cr→Pack</th><th>Cr→Geo</th><th>DPH</th><th>Avg LM</th>
  <th>OTP+3</th><th>Store Dly%</th><th>Rider Dly%</th><th>Breach</th>
  <th>BTS%</th><th>BTO</th><th>BTO%</th><th>DSR</th><th>FOD</th><th>Status</th>
</tr></thead>'''

def hub_tr(r):
    return f'''<tr>
  <td>{r["sl"]}</td><td class="hub-name" title="{r["hub"]}">{hs(r["hub"])}</td>
  <td>{r["opd"]}</td><td>{r["delivered"]}</td><td>{r["dau"]}</td><td>{r["login"]}</td>
  <td class="{rag_or2a(r["or2a"])}">{r["or2a"]:.2f}</td>
  <td class="{rag_s2p(r["s2p"])}">{r["s2p"]:.2f}</td>
  <td class="{'va' if r['crpack']>3 else ''}">{r["crpack"]:.2f}</td>
  <td>{r["crgeo"]:.2f}</td><td>{r["dph"]:.2f}</td><td>{r["lm"]:.2f}</td>
  <td class="{rag_otp(r["otp3"])}">{r["otp3"]:.1f}%</td>
  <td class="{rag_delay(r["sd"])}">{r["sd"]:.1f}%</td>
  <td class="{rag_delay(r["rd"])}">{r["rd"]:.1f}%</td>
  <td class="{'va' if r['breach']>5 else ''}">{r["breach"]}</td>
  <td class="{'va' if r['bts']>20 else ''}">{r["bts"]:.1f}%</td>
  <td class="{'va' if r['bto_n']>5 else ''}">{r["bto_n"]}</td>
  <td class="{'va' if r['bto']>5 else ''}">{r["bto"]:.1f}%</td>
  <td class="{'va' if r['dsr']<97 else ''}">{r["dsr"]:.1f}%</td>
  <td class="{'va' if r['fod']>3 else ''}">{r["fod"]}</td>
  <td>{status_pill(r)}</td>
</tr>'''

def sub_tr(label, m, cls='city-sub'):
    if not m: return ''
    return f'''<tr class="{cls}">
  <td colspan="2" class="sub-label">{label} — Subtotal</td>
  <td>{m["opd"]:,}</td><td>{m["delivered"]:,}</td><td>{m["dau"]}</td><td>{m["login"]}</td>
  <td class="{rag_or2a(m["or2a"])}">{m["or2a"]:.2f}</td>
  <td class="{rag_s2p(m["s2p"])}">{m["s2p"]:.2f}</td>
  <td class="{'va' if m['crpack']>3 else ''}">{m["crpack"]:.2f}</td>
  <td>{m["crgeo"]:.2f}</td><td>{m["dph"]:.2f}</td><td>{m["lm"]:.2f}</td>
  <td class="{rag_otp(m["otp3"])}">{m["otp3"]:.1f}%</td>
  <td class="{rag_delay(m["sd"])}">{m["sd"]:.1f}%</td>
  <td class="{rag_delay(m["rd"])}">{m["rd"]:.1f}%</td>
  <td>{m["breach"]}</td>
  <td class="{'va' if m['bts']>20 else ''}">{m["bts"]:.1f}%</td>
  <td>{m["bto_n"]}</td>
  <td class="{'va' if m['bto']>5 else ''}">{m["bto"]:.1f}%</td>
  <td class="{'va' if m['dsr']<97 else 'vg'}">{m["dsr"]:.1f}%</td>
  <td>{m["fod"]}</td><td>—</td>
</tr>'''

def grand_tr(label, m, cls='grand-total'):
    return f'''<tr class="{cls}">
  <td colspan="2" class="grand-label">{label}</td>
  <td>{m["opd"]:,}</td><td>{m["delivered"]:,}</td><td>{m["dau"]}</td><td>{m["login"]}</td>
  <td class="{rag_or2a(m["or2a"])}">{m["or2a"]:.2f}</td>
  <td class="{rag_s2p(m["s2p"])}">{m["s2p"]:.2f}</td>
  <td class="{'va' if m['crpack']>3 else ''}">{m["crpack"]:.2f}</td>
  <td>{m["crgeo"]:.2f}</td><td>{m["dph"]:.2f}</td><td>{m["lm"]:.2f}</td>
  <td class="{rag_otp(m["otp3"])}">{m["otp3"]:.1f}%</td>
  <td class="{rag_delay(m["sd"])}">{m["sd"]:.1f}%</td>
  <td class="{rag_delay(m["rd"])}">{m["rd"]:.1f}%</td>
  <td>{m["breach"]}</td>
  <td class="{'va' if m['bts']>20 else ''}">{m["bts"]:.1f}%</td>
  <td>{m["bto_n"]}</td>
  <td class="{'va' if m['bto']>5 else ''}">{m["bto"]:.1f}%</td>
  <td class="{'va' if m['dsr']<97 else 'vg'}">{m["dsr"]:.1f}%</td>
  <td>{m["fod"]}</td><td>—</td>
</tr>'''

def build_tab1_html(D, tab_prefix):
    if not D: return '<div style="padding:40px;text-align:center;color:#6b7a99">No data available</div>'
    rows=''
    for city in D['cities']:
        col = CITY_COLORS.get(city,'#6b7a99')
        city_r = [r for r in D['results'] if r['city']==city]
        cid = f"{tab_prefix}_{city.lower().replace(' ','_')}"
        rows += f'''<tr class="city-hdr" id="{cid}">
  <td colspan="22" style="color:{col}">
    <div class="city-hdr-inner">
      <span class="city-dot" style="background:{col}"></span>
      <span class="city-name-lbl">{city}</span>
      <button class="share-btn" onclick="captureCity('{cid}','{city}')">📸 {city}</button>
    </div>
  </td></tr>'''
        for r in city_r: rows += hub_tr(r)
        m = D['ct_all'].get(city)
        if m: rows += sub_tr(city, m)
    rows += grand_tr('Grand Total — All Stores', D['gt_all'])

    # Flags
    rf = sorted([r for r in D['results'] if r['rd']>5],key=lambda x:-x['rd'])
    rf_html = ''.join(f'<div class="flag-row"><div><div class="fhub">{hs(r["hub"])}</div><div class="fcity">{r["city"]} · {r["store_type"]}</div></div><div class="fval vr">{r["rd"]:.1f}%</div></div>' for r in rf) or '<div class="no-flag">✓ No hubs flagged</div>'
    sf = sorted([r for r in D['results'] if r['sd']>10],key=lambda x:-x['sd'])
    sf_html = ''.join(f'<div class="flag-row"><div><div class="fhub">{hs(r["hub"])}</div><div class="fcity">{r["city"]}</div></div><div class="fval va">{r["sd"]:.1f}%</div></div>' for r in sf) or '<div class="no-flag">✓ No hubs flagged</div>'

    nl=D['nonlive_hubs']
    nl_rows=''.join(f'<tr><td>{i+1}</td><td title="{h["hub"]}">{hs(h["hub"])}</td><td>{h["city"]}</td><td>{h["dau"]}</td><td>{h["login"]}</td><td>{h["avg_hrs"]}</td><td>{h["fod"]}</td></tr>' for i,h in enumerate(nl)) or '<tr><td colspan="7" class="empty-row">No non-live stores today</td></tr>'
    nl_id=f"{tab_prefix}_nonlive"
    g=D['gt_all']
    oc='green' if g['otp3']>=95 else ('amber' if g['otp3']>=90 else 'red')
    rc='green' if g['rd']<2 else ('amber' if g['rd']<=5 else 'red')
    dc='green' if g['dsr']>=98 else 'amber'
    ds=D['report_date'].strftime('%d %b %Y')

    return f'''
<div class="krow">
  <div class="kc teal"><div class="kl">Total OPD</div><div class="kv teal">{g["opd"]:,}</div><div class="ks">{ds}</div></div>
  <div class="kc teal"><div class="kl">Delivered</div><div class="kv teal">{g["delivered"]:,}</div></div>
  <div class="kc teal"><div class="kl">DAU</div><div class="kv teal">{g["dau"]:,}</div><div class="ks">{g["login"]:,} &gt;3.5h</div></div>
  <div class="kc {oc}"><div class="kl">OTP +3 min</div><div class="kv {oc}">{g["otp3"]:.2f}%</div></div>
  <div class="kc {dc}"><div class="kl">DSR</div><div class="kv {dc}">{g["dsr"]:.2f}%</div></div>
  <div class="kc {rc}"><div class="kl">Rider Delay</div><div class="kv {rc}">{g["rd"]:.2f}%</div><div class="ks">our accountability</div></div>
  <div class="kc red"><div class="kl">Store Delay</div><div class="kv">{g["sd"]:.2f}%</div><div class="ks">not ours</div></div>
</div>
<div class="flags-row">
  <div class="fc"><div class="ft"><span class="fdot" style="background:var(--am)"></span>High rider delay (&gt;5%)</div>{rf_html}</div>
  <div class="fc"><div class="ft"><span class="fdot" style="background:var(--rd)"></span>High store delay (&gt;10%) — FYI</div>{sf_html}</div>
</div>
<div class="slbl">All cities — hub level with city subtotals</div>
<div class="table-scroll-wrap">
  <div class="table-header-bar">
    <span class="th-title">Hub Performance</span>
    <span class="th-meta">{len(D["results"])} hubs · {ds}</span>
  </div>
  <div class="tscroll"><table>{TABLE_HEAD}<tbody>{rows}</tbody></table></div>
</div>
<div class="slbl">Non-live stores &nbsp;<button class="share-btn" onclick="captureEl('{nl_id}','nonlive_{tab_prefix}')">📸 Non-live</button></div>
<div class="table-scroll-wrap" id="{nl_id}">
  <table><thead><tr><th>#</th><th>Hub</th><th>City</th><th>DAU</th><th>Login&gt;3.5h</th><th>Avg hrs</th><th>FOD</th></tr></thead>
  <tbody>{nl_rows}</tbody></table>
</div>'''

def build_tab2_html(D, tab_prefix):
    if not D: return '<div style="padding:40px;text-align:center;color:#6b7a99">No data available</div>'

    def section(res, ct, gt, store_type, grand_cls):
        emoji='🟢' if store_type=='Live' else '🟣'
        bdr='rgba(0,176,155,0.3)' if store_type=='Live' else 'rgba(139,92,246,0.3)'
        rows=f'''<tr class="section-hdr" style="--section-color:{bdr}">
  <td colspan="22"><span class="section-title">{emoji} {store_type.upper()} STORES</span>
  <button class="share-btn" onclick="captureEl('{tab_prefix}_{store_type.lower()}_tbl','{store_type}_{tab_prefix}')">📸 {store_type} Full</button>
  </td></tr>'''
        cities = sorted(set(r['city'] for r in res))
        for city in cities:
            col=CITY_COLORS.get(city,'#6b7a99')
            city_r=[r for r in res if r['city']==city]
            cid=f"{tab_prefix}_{store_type.lower()}_{city.lower().replace(' ','_')}"
            rows+=f'''<tr class="city-hdr" id="{cid}">
  <td colspan="22" style="color:{col}">
    <div class="city-hdr-inner">
      <span class="city-dot" style="background:{col}"></span>
      <span class="city-name-lbl">{city}</span>
      <button class="share-btn" onclick="captureCity('{cid}','{city}_{store_type}')">📸 {city}</button>
    </div>
  </td></tr>'''
            for r in city_r: rows+=hub_tr(r)
            m=ct.get(city)
            if m: rows+=sub_tr(city,m)
        rows+=grand_tr(f'{store_type} Grand Total',gt,cls=grand_cls)
        return rows

    live_rows   = section(D['live_res'],   D['ct_live'],   D['gt_live'],   'Live',   'live-grand')
    shared_rows = section(D['shared_res'], D['ct_shared'], D['gt_shared'], 'Shared', 'shared-grand')
    comb_row    = grand_tr('Combined Grand Total (Live + Shared)', D['gt_comb'], cls='grand-total')

    gl=D['gt_live']; gs=D['gt_shared']
    ol='green' if gl['otp3']>=95 else ('amber' if gl['otp3']>=90 else 'red')
    os_='green' if gs['otp3']>=95 else ('amber' if gs['otp3']>=90 else 'red')
    ds=D['report_date'].strftime('%d %b %Y')

    return f'''
<div class="krow-2col">
  <div class="kc live-card">
    <div class="card-type-label live-label">🟢 Live Stores — {len(D["live_res"])} hubs</div>
    <div class="mini-kpis">
      <div><div class="kl">OPD</div><div class="kv teal">{gl["opd"]:,}</div></div>
      <div><div class="kl">OTP+3</div><div class="kv {ol}">{gl["otp3"]:.1f}%</div></div>
      <div><div class="kl">Rider Dly</div><div class="kv {rag_delay(gl["rd"])}">{gl["rd"]:.1f}%</div></div>
      <div><div class="kl">DSR</div><div class="kv {'vg' if gl['dsr']>=98 else 'va'}">{gl["dsr"]:.1f}%</div></div>
      <div><div class="kl">Breach</div><div class="kv va">{gl["breach"]}</div></div>
      <div><div class="kl">FOD</div><div class="kv">{gl["fod"]}</div></div>
    </div>
  </div>
  <div class="kc shared-card">
    <div class="card-type-label shared-label">🟣 Shared Stores — {len(D["shared_res"])} hubs</div>
    <div class="mini-kpis">
      <div><div class="kl">OPD</div><div class="kv teal">{gs["opd"]:,}</div></div>
      <div><div class="kl">OTP+3</div><div class="kv {os_}">{gs["otp3"]:.1f}%</div></div>
      <div><div class="kl">Rider Dly</div><div class="kv {rag_delay(gs["rd"])}">{gs["rd"]:.1f}%</div></div>
      <div><div class="kl">DSR</div><div class="kv {'vg' if gs['dsr']>=98 else 'va'}">{gs["dsr"]:.1f}%</div></div>
      <div><div class="kl">Breach</div><div class="kv va">{gs["breach"]}</div></div>
      <div><div class="kl">FOD</div><div class="kv">{gs["fod"]}</div></div>
    </div>
  </div>
</div>
<div class="slbl">Live + Shared hub detail · {ds}</div>
<div class="table-scroll-wrap" id="{tab_prefix}_ls_full">
  <div class="table-header-bar">
    <span class="th-title">Live vs Shared Performance</span>
    <span class="th-meta">{len(D["live_res"])} live · {len(D["shared_res"])} shared · {ds}</span>
    <button class="share-btn" onclick="captureEl('{tab_prefix}_ls_full','liveshared_{tab_prefix}')">📸 Full Report</button>
  </div>
  <div class="tscroll" id="{tab_prefix}_live_tbl"><table>{TABLE_HEAD}<tbody>{live_rows}{shared_rows}{comb_row}</tbody></table></div>
</div>'''

# ── BUILD ALL 4 TABS ─────────────────────
t1 = build_tab1_html(D_TODAY, 't1')
t2 = build_tab2_html(D_TODAY, 't2')
t3 = build_tab1_html(D_YEST,  't3')
t4 = build_tab2_html(D_YEST,  't4')

today_str = TODAY.strftime('%d %b %Y')
yest_str  = YESTERDAY.strftime('%d %b %Y')
gen_time  = datetime.now().strftime('%H:%M IST')

SFX_SVG = '''<svg width="150" height="40" viewBox="0 0 150 40" xmlns="http://www.w3.org/2000/svg">
  <polygon points="3,20 13,4 20,4 10,20 20,36 13,36" fill="#00B09B"/>
  <polygon points="11,20 21,4 29,4 19,20 29,36 21,36" fill="#27D4A0" opacity="0.85"/>
  <text x="36" y="26" font-family="'IBM Plex Sans',Arial,sans-serif" font-weight="700" font-size="15.5" fill="currentColor" letter-spacing="0.5">SHADOWFAX</text>
  <text x="36" y="36" font-family="'IBM Plex Sans',Arial,sans-serif" font-size="8" fill="#6b7a99" letter-spacing="0.3">Think ahead.</text>
</svg>'''

HTML = f'''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="600">
<title>AmazonNow Dashboard — {today_str}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ── THEMES ── */
[data-theme="dark"]{{
  --bg:#070c18;--s:#0f1623;--s2:#162030;--b:rgba(255,255,255,0.06);--b2:rgba(255,255,255,0.11);
  --t:#dde4f0;--m:#5a6a88;--logo-color:#e8edf5;
  --row-hover:rgba(0,176,155,0.04);--sub-bg:rgba(255,255,255,0.025);--city-bg:rgba(0,176,155,0.04);
}}
[data-theme="light"]{{
  --bg:#f0f4f8;--s:#ffffff;--s2:#f7fafc;--b:rgba(0,0,0,0.08);--b2:rgba(0,0,0,0.13);
  --t:#1a2235;--m:#6b7a99;--logo-color:#1a2235;
  --row-hover:rgba(0,176,155,0.06);--sub-bg:rgba(0,0,0,0.03);--city-bg:rgba(0,176,155,0.05);
}}
:root{{
  --acc:#00B09B;--gn:#00B09B;--am:#f59e0b;--rd:#ef4444;--lrd:#f97316;
  --gn-bg:rgba(0,176,155,0.13);--am-bg:rgba(245,158,11,0.13);
  --rd-bg:rgba(239,68,68,0.13);--lrd-bg:rgba(249,115,22,0.13);
  --gn-t:#00d4b8;--am-t:#fbbf24;--rd-t:#f87171;--lrd-t:#fb923c;
  --shadow:0 1px 3px rgba(0,0,0,0.3);
}}

*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--t);font-family:'IBM Plex Sans',sans-serif;font-size:13px;transition:background .3s,color .3s}}
a{{color:inherit}}

/* ── HEADER ── */
.hdr{{
  background:var(--s);
  border-bottom:2px solid var(--acc);
  padding:10px 24px;
  display:flex;align-items:center;justify-content:space-between;
  box-shadow:0 2px 12px rgba(0,176,155,0.15);
  position:sticky;top:0;z-index:100;
}}
.brand{{display:flex;align-items:center;gap:14px}}
.sfx-logo{{color:var(--logo-color)}}
.brand-div{{width:1px;height:34px;background:var(--b2)}}
.brand-text .title{{font-size:13px;font-weight:600;color:var(--t)}}
.brand-text .sub{{font-size:10px;color:var(--m)}}
.hmeta{{display:flex;align-items:center;gap:16px}}
.mi{{text-align:right}}
.ml{{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px}}
.mv{{font-size:13px;font-weight:600;font-family:'IBM Plex Mono',monospace}}
.live-badge{{
  background:linear-gradient(135deg,rgba(0,176,155,0.2),rgba(39,212,160,0.1));
  color:var(--gn-t);border:1px solid rgba(0,176,155,0.4);
  padding:5px 14px;border-radius:20px;font-size:11px;font-weight:700;
  letter-spacing:0.06em;animation:livepulse 2s infinite;
}}
@keyframes livepulse{{0%,100%{{box-shadow:0 0 0 0 rgba(0,176,155,0.3)}}50%{{box-shadow:0 0 0 5px rgba(0,176,155,0)}}}}
.hdr-actions{{display:flex;align-items:center;gap:8px}}
.theme-btn{{
  background:var(--s2);border:1px solid var(--b2);color:var(--t);
  padding:5px 12px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;
  font-family:'IBM Plex Sans',sans-serif;transition:all .2s;
}}
.theme-btn:hover{{background:var(--acc);color:#fff;border-color:var(--acc)}}
.refresh-note{{font-size:9px;color:var(--m);text-align:right;margin-top:1px}}

/* ── TABS ── */
.tab-bar{{
  display:flex;padding:0 24px;background:var(--s);
  border-bottom:1px solid var(--b2);gap:0;overflow-x:auto;
}}
.tab-btn{{
  padding:10px 18px;font-size:12px;font-weight:600;color:var(--m);
  cursor:pointer;border:none;background:none;border-bottom:3px solid transparent;
  transition:all .2s;white-space:nowrap;font-family:'IBM Plex Sans',sans-serif;
}}
.tab-btn.active{{color:var(--gn-t);border-bottom-color:var(--acc)}}
.tab-btn:hover:not(.active){{color:var(--t);background:var(--row-hover)}}
.tab-btn.d1.active{{color:#c4b5fd;border-bottom-color:#8b5cf6}}
.tab-content{{display:none}}.tab-content.active{{display:block}}

/* ── MAIN ── */
.main{{padding:16px 24px 24px}}

/* ── KPI CARDS ── */
.krow{{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;margin-bottom:14px}}
.krow-2col{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}}
.kc{{
  background:var(--s);border:1px solid var(--b);border-radius:10px;
  padding:13px 15px;position:relative;overflow:hidden;
  box-shadow:var(--shadow);transition:transform .15s;
}}
.kc:hover{{transform:translateY(-1px)}}
.kc::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:10px 10px 0 0}}
.kc.teal::before{{background:linear-gradient(90deg,var(--acc),#27D4A0)}}
.kc.green::before{{background:var(--gn)}}
.kc.amber::before{{background:var(--am)}}
.kc.red::before{{background:var(--rd)}}
.kl{{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:5px}}
.kv{{font-size:21px;font-weight:700;font-family:'IBM Plex Mono',monospace;line-height:1}}
.kv.green{{color:var(--gn-t)}}.kv.amber{{color:var(--am-t)}}.kv.red{{color:var(--rd-t)}}.kv.teal{{color:#3ee8ce}}
.ks{{font-size:10px;color:var(--m);margin-top:3px}}
.live-card{{border-color:rgba(0,176,155,0.3)!important}}
.live-card::before{{background:linear-gradient(90deg,var(--acc),#27D4A0)!important}}
.shared-card{{border-color:rgba(139,92,246,0.3)!important}}
.shared-card::before{{background:linear-gradient(90deg,#8b5cf6,#a78bfa)!important}}
.card-type-label{{font-size:12px;font-weight:700;margin-bottom:10px}}
.live-label{{color:var(--gn-t)}}.shared-label{{color:#c4b5fd}}
.mini-kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}}

/* ── SECTION LABEL ── */
.slbl{{
  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;
  color:var(--m);margin-bottom:8px;display:flex;align-items:center;gap:8px;
}}
.slbl::after{{content:'';flex:1;height:1px;background:var(--b2)}}

/* ── FLAGS ── */
.flags-row{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}}
.fc{{background:var(--s);border:1px solid var(--b);border-radius:10px;padding:12px 14px;box-shadow:var(--shadow)}}
.ft{{font-size:11px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.fdot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.flag-row{{display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--b);font-size:11px}}
.flag-row:last-child{{border-bottom:none}}
.fhub{{color:var(--t);max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}}
.fcity{{color:var(--m);font-size:10px}}
.fval{{font-family:'IBM Plex Mono',monospace;font-size:12px}}
.no-flag{{font-size:11px;color:var(--gn-t);padding:4px 0}}

/* ── TABLE ── */
.table-scroll-wrap{{
  background:var(--s);border:1px solid var(--b);border-radius:10px;
  overflow:hidden;margin-bottom:14px;box-shadow:var(--shadow);
}}
.table-header-bar{{
  padding:10px 16px;border-bottom:1px solid var(--b2);
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;
}}
.th-title{{font-size:13px;font-weight:600}}
.th-meta{{font-size:11px;color:var(--m)}}
.tscroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{width:max-content;min-width:100%;border-collapse:collapse}}
thead th{{
  padding:8px 10px;text-align:right;font-size:10px;font-weight:700;
  text-transform:uppercase;letter-spacing:0.04em;color:var(--m);
  background:var(--s2);border-bottom:1px solid var(--b2);
  border-right:1px solid var(--b);
  white-space:nowrap;position:sticky;top:0;
}}
thead th:last-child{{border-right:none}}
thead th:first-child,thead th:nth-child(2){{text-align:left;position:sticky;left:0;z-index:2;background:var(--s2)}}
thead th:nth-child(2){{left:36px}}
tbody tr{{border-bottom:1px solid var(--b);transition:background .1s}}
tbody tr:hover{{background:var(--row-hover)}}
tr.city-hdr{{background:var(--city-bg);border-top:1px solid rgba(0,176,155,0.15)}}
tr.city-hdr td{{padding:7px 14px;font-family:'IBM Plex Sans',sans-serif}}
.city-hdr-inner{{display:flex;align-items:center;gap:8px}}
.city-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.city-name-lbl{{font-size:12px;font-weight:700;letter-spacing:0.04em;flex:1}}
tr.city-sub{{background:var(--sub-bg)}}
tr.city-sub td{{color:var(--m);font-size:11px}}
.sub-label{{font-style:italic;font-family:'IBM Plex Sans',sans-serif!important;font-size:11px!important}}
tr.section-hdr{{background:linear-gradient(90deg,rgba(0,0,0,0.1),transparent);border-top:2px solid var(--section-color,rgba(0,176,155,0.3))}}
tr.section-hdr td{{padding:10px 16px;font-family:'IBM Plex Sans',sans-serif}}
.section-title{{font-size:13px;font-weight:700;letter-spacing:0.04em}}
tr.grand-total{{background:linear-gradient(90deg,rgba(0,176,155,0.1),rgba(0,176,155,0.05));border-top:2px solid rgba(0,176,155,0.4)}}
tr.grand-total td{{font-weight:700;font-size:12px}}
.grand-label{{font-family:'IBM Plex Sans',sans-serif!important;font-size:12px!important;font-weight:700!important}}
tr.live-grand{{background:rgba(16,185,129,0.07);border-top:2px solid rgba(16,185,129,0.3)}}
tr.live-grand td{{font-weight:600;color:var(--gn-t)}}
tr.shared-grand{{background:rgba(139,92,246,0.07);border-top:2px solid rgba(139,92,246,0.3)}}
tr.shared-grand td{{font-weight:600;color:#c4b5fd}}
td{{padding:6px 10px;text-align:right;font-size:11px;font-family:'IBM Plex Mono',monospace;white-space:nowrap;border-right:1px solid var(--b)}}
td:last-child{{border-right:none}}
td:first-child{{text-align:left;font-family:'IBM Plex Sans',sans-serif;color:var(--m);padding-left:16px;position:sticky;left:0;background:var(--s);z-index:1}}
td:nth-child(2){{text-align:left;font-family:'IBM Plex Sans',sans-serif;max-width:160px;overflow:hidden;text-overflow:ellipsis;position:sticky;left:36px;background:var(--s);z-index:1}}
.hub-name{{font-weight:500;color:var(--t)!important}}
tr:hover td:first-child,tr:hover td:nth-child(2){{background:var(--s2)}}

/* VALUE COLORS */
.vg{{color:var(--gn-t)}}.va{{color:var(--am-t)}}.vr{{color:var(--rd-t)}}.vlr{{color:var(--lrd-t)}}.vd{{color:var(--m)}}

/* PILLS */
.pill{{display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;font-family:'IBM Plex Sans',sans-serif}}
.g{{background:var(--gn-bg);color:var(--gn-t)}}.a{{background:var(--am-bg);color:var(--am-t)}}.r{{background:var(--rd-bg);color:var(--rd-t)}}
.empty-row{{text-align:center;color:var(--m);padding:16px!important;font-family:'IBM Plex Sans',sans-serif!important}}

/* SHARE BUTTON */
.share-btn{{
  background:rgba(0,176,155,0.12);color:var(--gn-t);
  border:1px solid rgba(0,176,155,0.3);padding:3px 10px;border-radius:5px;
  font-size:10px;font-weight:700;cursor:pointer;font-family:'IBM Plex Sans',sans-serif;
  transition:all .2s;white-space:nowrap;
}}
.share-btn:hover{{background:rgba(0,176,155,0.25);border-color:var(--acc)}}
.share-btn:active{{transform:scale(0.97)}}

/* D-1 BANNER */
.d1-banner{{
  background:linear-gradient(90deg,rgba(139,92,246,0.1),rgba(139,92,246,0.05));
  border:1px solid rgba(139,92,246,0.3);border-radius:8px;
  padding:10px 16px;margin-bottom:14px;font-size:12px;color:#c4b5fd;font-weight:600;
}}

/* SCREENSHOT OVERLAY */
#ss-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:9999;align-items:center;justify-content:center;flex-direction:column;gap:14px}}
#ss-overlay.show{{display:flex}}
#ss-img{{max-width:92vw;max-height:76vh;border-radius:10px;border:1px solid rgba(0,176,155,0.3);box-shadow:0 0 40px rgba(0,0,0,0.5)}}
.ov-btns{{display:flex;gap:10px;flex-wrap:wrap;justify-content:center}}
.ov-btn{{padding:10px 22px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;border:none;font-family:'IBM Plex Sans',sans-serif;transition:all .2s}}
.ov-btn:hover{{transform:translateY(-1px)}}
.btn-wa{{background:#25D366;color:#fff}}
.btn-dl{{background:var(--acc);color:#fff}}
.btn-cl{{background:rgba(255,255,255,0.12);color:var(--t)}}
.ov-hint{{font-size:11px;color:#6b7a99}}

/* FOOTER */
.footer{{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 0;border-top:1px solid var(--b);
  font-size:10px;color:var(--m);flex-wrap:wrap;gap:6px;margin-top:4px;
}}
.leg{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.lc-g{{color:var(--gn-t)}}.lc-a{{color:var(--am-t)}}.lc-lr{{color:var(--lrd-t)}}.lc-r{{color:var(--rd-t)}}

/* SCROLLBAR */
.tscroll::-webkit-scrollbar{{height:5px}}
.tscroll::-webkit-scrollbar-track{{background:var(--s2)}}
.tscroll::-webkit-scrollbar-thumb{{background:rgba(0,176,155,0.4);border-radius:3px}}
</style>
</head>
<body>

<!-- HEADER -->
<div class="hdr">
  <div class="brand">
    <div class="sfx-logo">{SFX_SVG}</div>
    <div class="brand-div"></div>
    <div class="brand-text">
      <div class="title">AmazonNow Live Stores Performance</div>
      <div class="sub">Operations Dashboard · Shadowfax</div>
    </div>
  </div>
  <div class="hdr-actions">
    <div class="hmeta">
      <div class="mi"><div class="ml">Updated</div><div class="mv">{gen_time}</div><div class="refresh-note">Auto-refresh 10 min</div></div>
      <div class="mi"><div class="ml">Today</div><div class="mv">{today_str}</div></div>
      <div class="mi"><div class="ml">D-1</div><div class="mv">{yest_str}</div></div>
    </div>
    <button class="theme-btn" onclick="toggleTheme()" id="theme-toggle">☀️ Light</button>
    <div class="live-badge">● LIVE</div>
  </div>
</div>

<!-- TAB BAR -->
<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('t1',this)">📊 Today — All Cities</button>
  <button class="tab-btn" onclick="switchTab('t2',this)">🏪 Today — Live vs Shared</button>
  <button class="tab-btn d1" onclick="switchTab('t3',this)">📅 D-1 — All Cities</button>
  <button class="tab-btn d1" onclick="switchTab('t4',this)">📅 D-1 — Live vs Shared</button>
</div>

<div id="t1" class="tab-content active"><div class="main">
{t1}
<div class="footer"><div class="leg"><span>OTP+3:</span><span class="lc-g">■≥95%</span><span class="lc-a">■90-95%</span><span class="lc-lr">■85-90%</span><span class="lc-r">■&lt;85%</span><span style="margin:0 8px">|</span><span>Delay:</span><span class="lc-g">■&lt;2%</span><span class="lc-a">■2-5%</span><span class="lc-r">■&gt;5%</span></div><div>Shadowfax · Base Dump + DAU Base · {today_str} · {gen_time}</div></div>
</div></div>

<div id="t2" class="tab-content"><div class="main">
{t2}
<div class="footer"><div class="leg"><span>OTP+3:</span><span class="lc-g">■≥95%</span><span class="lc-a">■90-95%</span><span class="lc-lr">■85-90%</span><span class="lc-r">■&lt;85%</span></div><div>Shadowfax · {today_str} · {gen_time}</div></div>
</div></div>

<div id="t3" class="tab-content"><div class="main">
<div class="d1-banner">📅 D-1 Report — {yest_str} (Previous Day — Final Data)</div>
{t3}
<div class="footer"><div class="leg"><span>OTP+3:</span><span class="lc-g">■≥95%</span><span class="lc-a">■90-95%</span><span class="lc-lr">■85-90%</span><span class="lc-r">■&lt;85%</span></div><div>Shadowfax D-1 · {yest_str}</div></div>
</div></div>

<div id="t4" class="tab-content"><div class="main">
<div class="d1-banner">📅 D-1 Report — {yest_str} (Previous Day — Final Data)</div>
{t4}
<div class="footer"><div class="leg"><span>OTP+3:</span><span class="lc-g">■≥95%</span><span class="lc-a">■90-95%</span><span class="lc-lr">■85-90%</span><span class="lc-r">■&lt;85%</span></div><div>Shadowfax D-1 · {yest_str}</div></div>
</div></div>

<!-- SCREENSHOT OVERLAY -->
<div id="ss-overlay">
  <img id="ss-img" src="" alt="Screenshot preview">
  <div class="ov-btns">
    <button class="ov-btn btn-wa" onclick="shareWA()">📱 Share on WhatsApp</button>
    <button class="ov-btn btn-dl" onclick="dlImg()">⬇️ Download PNG</button>
    <button class="ov-btn btn-cl" onclick="closeOv()">✕ Close</button>
  </div>
  <div class="ov-hint">Tip: Download the PNG → attach on WhatsApp Web or email</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script>
// Tab switching
function switchTab(id,btn){{
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}}

// Theme
function toggleTheme(){{
  const html=document.documentElement;
  const isDark=html.getAttribute('data-theme')==='dark';
  html.setAttribute('data-theme',isDark?'light':'dark');
  document.getElementById('theme-toggle').textContent=isDark?'🌙 Dark':'☀️ Light';
}}

// Capture a full section (Live/Shared table, non-live, etc.)
let _imgUrl='';

/* ── SHARED UTILITIES ── */
function _brandHdr(txtC,borderC){{
  const ts=new Date().toLocaleString('en-IN',{{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'short'}});
  return `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid #00B09B;font-family:Arial,sans-serif">
    <div style="display:flex;align-items:center;gap:12px">
      <svg width="130" height="34" viewBox="0 0 150 40" xmlns="http://www.w3.org/2000/svg">
        <polygon points="3,20 13,4 20,4 10,20 20,36 13,36" fill="#00B09B"/>
        <polygon points="11,20 21,4 29,4 19,20 29,36 21,36" fill="#27D4A0" opacity="0.85"/>
        <text x="36" y="26" font-family="Arial,sans-serif" font-weight="700" font-size="15" fill="${{txtC}}" letter-spacing="0.5">SHADOWFAX</text>
        <text x="36" y="35" font-family="Arial,sans-serif" font-size="8" fill="#888">Think ahead.</text>
      </svg>
      <div style="width:1px;height:30px;background:${{borderC}}"></div>
      <div>
        <div style="font-size:14px;font-weight:700;color:${{txtC}}">AmazonNow · Live Stores Performance</div>
        <div style="font-size:10px;color:#888;margin-top:2px">Operations Dashboard · Shadowfax</div>
      </div>
    </div>
    <div style="text-align:right">
      <div style="font-size:10px;color:#888">Generated</div>
      <div style="font-size:13px;font-weight:600;font-family:monospace;color:${{txtC}}">${{ts}}</div>
    </div>
  </div>`;
}}

function _legend(){{
  return `<div style="margin-top:12px;font-size:10px;color:#888;display:flex;justify-content:space-between;font-family:Arial,sans-serif">
    <span>OTP+3: <span style="color:#00d4b8">■≥95%</span> <span style="color:#fbbf24">■90-95%</span> <span style="color:#fb923c">■85-90%</span> <span style="color:#f87171">■&lt;85%</span></span>
    <span>Delay: <span style="color:#00d4b8">■&lt;2%</span> <span style="color:#fbbf24">■2-5%</span> <span style="color:#f87171">■&gt;5%</span> · Shadowfax Ops</span>
  </div>`;
}}

/* Build a full styled table HTML, resolving all CSS class colors to inline styles */
function _buildTable(theadEl, rows, isDark){{
  const bg      = isDark?'#0a0f1e':'#ffffff';
  const txtC    = isDark?'#dde4f0':'#1a2235';
  const muteC   = isDark?'#5a6a88':'#6b7a99';
  const borderC = isDark?'rgba(255,255,255,0.1)':'rgba(0,0,0,0.12)';
  const colBorderC = isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.07)';
  const hdrBg   = isDark?'#141e30':'#e8f0f8';
  const subBg   = isDark?'rgba(255,255,255,0.04)':'rgba(0,0,0,0.035)';
  const cityBg  = isDark?'rgba(0,176,155,0.09)':'rgba(0,176,155,0.07)';
  const altBg   = isDark?'rgba(255,255,255,0.02)':'rgba(0,0,0,0.02)';

  // Get column count from thead
  const colCount=theadEl.querySelectorAll('th').length;

  let h=`<table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:11px;table-layout:auto">
  <thead><tr>`;
  theadEl.querySelectorAll('th').forEach((th,i)=>{{
    const al=i<=1?'left':'right';
    const isFirstCol=i===0;
    const isHubCol=i===1;
    // First col (#) narrow, hub col wider
    const minW=isFirstCol?'30px':isHubCol?'160px':'60px';
    h+=`<th style="padding:8px 10px;text-align:${{al}};font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:${{muteC}};background:${{hdrBg}};border-bottom:2px solid #00B09B;border-right:1px solid ${{colBorderC}};white-space:nowrap;min-width:${{minW}}">${{th.textContent.trim()}}</th>`;
  }});
  h+=`</tr></thead><tbody>`;

  rows.forEach((row,idx)=>{{
    let rowBg=idx%2===0?bg:altBg;
    let topBorder='';
    let rowTextC=txtC;

    if(row.classList.contains('city-hdr'))        {{ rowBg=cityBg; topBorder='border-top:1px solid rgba(0,176,155,0.3);'; }}
    else if(row.classList.contains('city-sub'))   {{ rowBg=subBg; topBorder='border-top:1px dashed rgba(0,176,155,0.2);'; }}
    else if(row.classList.contains('section-hdr')){{ rowBg=isDark?'rgba(0,176,155,0.12)':'rgba(0,176,155,0.09)'; topBorder='border-top:2px solid rgba(0,176,155,0.5);'; }}
    else if(row.classList.contains('grand-total')){{ rowBg=isDark?'rgba(0,176,155,0.15)':'rgba(0,176,155,0.1)'; topBorder='border-top:2px solid #00B09B;'; }}
    else if(row.classList.contains('live-grand')) {{ rowBg=isDark?'rgba(16,185,129,0.12)':'rgba(16,185,129,0.08)'; topBorder='border-top:2px solid rgba(16,185,129,0.6);'; rowTextC='#00d4b8'; }}
    else if(row.classList.contains('shared-grand')){{ rowBg=isDark?'rgba(139,92,246,0.12)':'rgba(139,92,246,0.08)'; topBorder='border-top:2px solid rgba(139,92,246,0.6);'; rowTextC='#c4b5fd'; }}

    const isBold=(row.classList.contains('grand-total')||row.classList.contains('live-grand')||row.classList.contains('shared-grand'));
    const isSub=row.classList.contains('city-sub');
    const fw=isBold?'700':isSub?'600':'400';

    h+=`<tr style="background:${{rowBg}};${{topBorder}}">`;

    const cells=row.querySelectorAll('td');
    cells.forEach((td,i)=>{{
      // Resolve color — class takes priority
      let color=rowTextC;
      if(row.classList.contains('city-hdr')) color='#00d4b8';
      else if(td.classList.contains('vg'))  color='#00d4b8';
      else if(td.classList.contains('va'))  color='#fbbf24';
      else if(td.classList.contains('vr'))  color='#f87171';
      else if(td.classList.contains('vlr')) color='#fb923c';
      else if(td.classList.contains('vd'))  color=muteC;
      else if(i===0) color=muteC;
      else if(i===1) color=txtC; // hub name always readable

      // Override if row-level color set
      if(row.classList.contains('live-grand'))    color='#00d4b8';
      if(row.classList.contains('shared-grand'))  color='#c4b5fd';

      const al=i<=1?'left':'right';
      const pl=i===0?'12px':'10px';
      // Hub column: use sans-serif; numbers: monospace
      const ff=i<=1?'Arial,sans-serif':"'Courier New',monospace";
      const isLast=(i===cells.length-1);
      const colBorder=isLast?'':'border-right:1px solid '+colBorderC+';';

      // Get text content properly — use innerText equivalent
      let cellText=td.innerText||td.textContent||'';
      // But for cells with pills (status), rebuild from innerHTML
      let cellHTML=td.innerHTML
        .replace(/<button[^>]*class="share-btn"[^>]*>[\s\S]*?<\/button>/gi,'')
        .replace(/class="pill g"[^>]*/g,'style="display:inline-block;padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;background:rgba(0,176,155,0.25);color:#00d4b8;font-family:Arial"')
        .replace(/class="pill a"[^>]*/g,'style="display:inline-block;padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;background:rgba(245,158,11,0.25);color:#fbbf24;font-family:Arial"')
        .replace(/class="pill r"[^>]*/g,'style="display:inline-block;padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;background:rgba(239,68,68,0.25);color:#f87171;font-family:Arial"')
        .replace(/ class="[^"]*"/g,'')
        .replace(/ style="[^"]*display:inline-flex[^"]*"/g,''); // remove flex from city-hdr spans

      // For city header row, just show the text cleanly
      if(row.classList.contains('city-hdr') && i===0) cellHTML='';

      h+=`<td style="padding:6px ${{pl}};text-align:${{al}};color:${{color}};font-weight:${{fw}};border-bottom:1px solid ${{borderC}};${{colBorder}}white-space:nowrap;font-family:${{ff}}">${{cellHTML}}</td>`;
    }});
    h+=`</tr>`;
  }});
  h+=`</tbody></table>`;
  return h;
}}

/* ── CAPTURE CITY (horizontal, only that city) ── */
function captureCity(cityHdrId, filename){{
  const hdr=document.getElementById(cityHdrId);
  if(!hdr){{alert('City not found: '+cityHdrId);return;}}
  const btn=event.currentTarget;
  const orig=btn.textContent;
  btn.textContent='⏳...';btn.disabled=true;

  const isDark=document.documentElement.getAttribute('data-theme')==='dark';
  const bg=isDark?'#070c18':'#f0f4f8';
  const txtC=isDark?'#dde4f0':'#1a2235';
  const borderC=isDark?'rgba(255,255,255,0.08)':'rgba(0,0,0,0.1)';

  const rows=[hdr];
  let next=hdr.nextElementSibling;
  const stopAt=['city-hdr','section-hdr','grand-total','live-grand','shared-grand'];
  while(next && !stopAt.some(c=>next.classList.contains(c))){{ rows.push(next); next=next.nextElementSibling; }}
  if(next && next.classList.contains('city-sub')) rows.push(next);

  const origThead=hdr.closest('table').querySelector('thead');
  const cityName=hdr.querySelector('.city-name-lbl')?hdr.querySelector('.city-name-lbl').textContent.trim():filename.split('_')[0];

  const tableHTML=_buildTable(origThead,rows,isDark);

  const wrap=document.createElement('div');
  wrap.style.cssText=`position:fixed;left:-9999px;top:0;padding:24px 28px;background:${{bg}};border-radius:14px;min-width:1500px;font-family:Arial,sans-serif`;
  wrap.innerHTML=
    _brandHdr(txtC,borderC)+
    `<div style="font-size:16px;font-weight:800;color:#00d4b8;margin-bottom:12px;letter-spacing:0.04em;display:flex;align-items:center;gap:8px">
      <span style="width:10px;height:10px;border-radius:50%;background:#00d4b8;display:inline-block"></span>
      ${{cityName}} — Hub Performance
    </div>`+
    tableHTML+_legend();

  document.body.appendChild(wrap);
  requestAnimationFrame(()=>requestAnimationFrame(()=>{{
    html2canvas(wrap,{{backgroundColor:bg,scale:2,useCORS:true,logging:false,
      width:wrap.scrollWidth,height:wrap.scrollHeight,windowWidth:wrap.scrollWidth+50}})
    .then(c=>{{
      document.body.removeChild(wrap);
      _imgUrl=c.toDataURL('image/png');
      document.getElementById('ss-img').src=_imgUrl;
      document.getElementById('ss-overlay').classList.add('show');
      btn.textContent=orig;btn.disabled=false;
      window._dlName='sfx_'+cityName.replace(/\s/g,'_')+'_'+filename+'.png';
    }}).catch(e=>{{if(document.body.contains(wrap))document.body.removeChild(wrap);alert(e.message);btn.textContent=orig;btn.disabled=false;}});
  }}));
}}

/* ── CAPTURE LIVE/SHARED SECTION (landscape, all rows) ── */
function captureEl(elId, filename){{
  const el=document.getElementById(elId);
  if(!el){{alert('Element not found: '+elId);return;}}
  const btn=event.currentTarget;
  const orig=btn.textContent;
  btn.textContent='⏳...';btn.disabled=true;

  const isDark=document.documentElement.getAttribute('data-theme')==='dark';
  const bg=isDark?'#070c18':'#f0f4f8';
  const txtC=isDark?'#dde4f0':'#1a2235';
  const borderC=isDark?'rgba(255,255,255,0.08)':'rgba(0,0,0,0.1)';

  const tbl=el.querySelector('table');
  const origThead=tbl?tbl.querySelector('thead'):null;
  const allRows=tbl?Array.from(tbl.querySelectorAll('tbody tr')):[];

  const wrap=document.createElement('div');
  wrap.style.cssText=`position:fixed;left:-9999px;top:0;padding:24px 28px;background:${{bg}};border-radius:14px;min-width:1600px;font-family:Arial,sans-serif`;

  if(tbl && origThead && allRows.length>0){{
    wrap.innerHTML=_brandHdr(txtC,borderC)+_buildTable(origThead,allRows,isDark)+_legend();
  }} else {{
    const clone=el.cloneNode(true);
    clone.querySelectorAll('.share-btn').forEach(b=>b.remove());
    const frag=document.createElement('div');
    frag.innerHTML=_brandHdr(txtC,borderC);
    wrap.appendChild(frag.firstElementChild);
    wrap.appendChild(clone);
  }}

  document.body.appendChild(wrap);
  requestAnimationFrame(()=>requestAnimationFrame(()=>{{
    html2canvas(wrap,{{backgroundColor:bg,scale:2,useCORS:true,logging:false,
      width:wrap.scrollWidth,height:wrap.scrollHeight,windowWidth:wrap.scrollWidth+50}})
    .then(c=>{{
      document.body.removeChild(wrap);
      _imgUrl=c.toDataURL('image/png');
      document.getElementById('ss-img').src=_imgUrl;
      document.getElementById('ss-overlay').classList.add('show');
      btn.textContent=orig;btn.disabled=false;
      window._dlName='sfx_'+filename+'.png';
    }}).catch(e=>{{if(document.body.contains(wrap))document.body.removeChild(wrap);alert(e.message);btn.textContent=orig;btn.disabled=false;}});
  }}));
}}

function dlImg(){{
  const a=document.createElement('a');
  a.href=_imgUrl;a.download=window._dlName||'sfx_report.png';a.click();
}}
function shareWA(){{dlImg();setTimeout(()=>window.open('https://web.whatsapp.com','_blank'),600);}}
function closeOv(){{document.getElementById('ss-overlay').classList.remove('show');}}
document.getElementById('ss-overlay').addEventListener('click',e=>{{if(e.target===e.currentTarget)closeOv();}});
</script>
</body>
</html>'''

with open(OUTPUT_HTML,'w',encoding='utf-8') as f:
    f.write(HTML)

print(f"\n{'='*55}")
if D_TODAY:
    print(f"✅ TODAY  ({TODAY}): {len(D_TODAY['results'])} hubs, OPD={D_TODAY['gt_all']['opd']:,}, OTP3={D_TODAY['gt_all']['otp3']:.1f}%")
    print(f"   Live: {len(D_TODAY['live_res'])} | Shared: {len(D_TODAY['shared_res'])} | Non-live: {len(D_TODAY['nonlive_hubs'])}")
if D_YEST:
    print(f"✅ D-1    ({YESTERDAY}): {len(D_YEST['results'])} hubs, OPD={D_YEST['gt_all']['opd']:,}, OTP3={D_YEST['gt_all']['otp3']:.1f}%")
print(f"   Dashboard: {OUTPUT_HTML}")
print(f"{'='*55}")
