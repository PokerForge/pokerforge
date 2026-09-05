"""
Poker Dashboard — PyQt6 Edition with Population Tab
=====================================================
SETUP: pip install PyQt6 pyqtgraph psycopg2-binary
RUN:   python poker_dashboard.py
"""

import sys
import os
import json
import psycopg2
from datetime import date, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTabWidget, QTableWidget, QTableWidgetItem, QComboBox,
    QFrame, QGridLayout, QHeaderView, QPushButton, QProgressBar,
    QSplitter, QLineEdit, QScrollArea, QTextEdit, QSizePolicy, QDialog,
    QGraphicsOpacityEffect, QGraphicsBlurEffect, QToolTip, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QCursor
import pyqtgraph as pg

# ─── DB CONFIG ────────────────────────────────────────────────────────────────
DB = dict(host="localhost", port=5432, dbname="PT4 DB",
          user="postgres", password="dbpass")

# ─── CARD DECODING ────────────────────────────────────────────────────────────
# Encoding confirmed against a known hand: code 1-52,
# suit = (code-1)//13 (0=Clubs,1=Diamonds,2=Hearts,3=Spades), rank = (code-1)%13 (0=2..12=Ace)
_RANKS=['2','3','4','5','6','7','8','9','T','J','Q','K','A']
_SUITS=['♣','♦','♥','♠']
_SUIT_COLOR={'♣':'#8b949e','♦':'#f85149','♥':'#f85149','♠':'#e6edf3'}

def decode_card(code):
    if not code: return None
    idx=code-1
    return _RANKS[idx%13]+_SUITS[idx//13]

def decode_board(c1,c2,c3,c4,c5):
    cards=[decode_card(c) for c in (c1,c2,c3,c4,c5) if c]
    return cards  # list of strings like ['K♦','T♣','4♣','A♠','3♥']

_SUIT_COLOR_CUSTOM={'♥':'#f85149','♠':'#e6edf3','♦':'#4a9eff','♣':'#3fb950'}

def board_html(cards):
    if not cards: return "Preflop only"
    spans=[]
    for c in cards:
        suit=c[-1]
        color=_SUIT_COLOR_CUSTOM.get(suit,'#e6edf3')
        spans.append(f"<span style='color:{color};'>{c}</span>")
    return '&nbsp;&nbsp;'.join(spans)

# Hand-history text uses SUIT-then-RANK notation (e.g. 'DK'=King of Diamonds,
# 'C10'=Ten of Clubs, 'SA'=Ace of Spades) — different from the numeric board
# decoder above. Converts to our display convention (rank+suit symbol, e.g. 'K♦').
_HH_SUIT_MAP={'C':'♣','D':'♦','H':'♥','S':'♠'}
def hh_card_to_display(code):
    if not code: return None
    suit_letter=code[0]; rank_part=code[1:]
    suit=_HH_SUIT_MAP.get(suit_letter,'?')
    rank='T' if rank_part=='10' else rank_part
    return rank+suit

# ─── HAND HISTORY PARSER ───────────────────────────────────────────────────────
# Tested against real sample hands (raises, calls, all-ins, showdowns) with
# zero unmatched lines before being wired into the app.
import re as _re

def parse_hand_history(text):
    lines=[l.strip() for l in text.strip().split('\n') if l.strip()]
    result={'header':{},'seats':[],'button_seat':None,'posts':[],
            'hole_cards':{},'streets':{},'summary':{}}

    header_re=_re.compile(
        r"GAME #(?P<gid>\d+).*?(?P<gametype>Texas Hold'em|Omaha).*?NL\s+£(?P<sb>[\d.]+)/£(?P<bb>[\d.]+)\s+"
        r"(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>[\d:]+)/(?P<tz>\w+)")
    table_info_re=_re.compile(r"^Table Info: Size: (?P<size>\d+), Blinds: (?P<blinds>[\d./]+)$")
    table_name_re=_re.compile(r"^Table (?P<name>.+?), (?P<tableid>\d+)$")
    seat_re=_re.compile(r"Seat (?P<seat>\d+): (?P<name>.+?) \(£(?P<stack>[\d.]+) in chips\)(?P<dealer>\s+DEALER)?")
    post_re=_re.compile(r"^(?P<name>.+?): Post (?P<type>SB|BB) £(?P<amt>[\d.]+)$")
    dealt_re=_re.compile(r"^Dealt to (?P<name>.+?) \[(?P<c1>\w+) (?P<c2>\w+)\]$")
    street_hdr_re=_re.compile(r"^\*\*\* (?P<street>FLOP|TURN|RIVER) \*\*\* \[(?P<cards>.+?)\]$")
    action_re=_re.compile(
        r"^(?P<name>.+?): (?P<action>Fold|Check|Call|Bet|Raise \(NF\)|Raise|Allin)(?:\s+£(?P<amt>[\d.]+))?$")
    summary_start_re=_re.compile(r"^\*\*\* SUMMARY \*\*\*$")
    total_pot_re=_re.compile(r"^Total pot £(?P<pot>[\d.]+)(?:\s+Rake £(?P<rake>[\d.]+))?$")
    shows_re=_re.compile(r"^(?P<name>.+?): Shows \[(?P<c1>\w+) (?P<c2>\w+)\] (?P<desc>.+)$")
    wins_re=_re.compile(r"^(?P<name>.+?): wins £(?P<amt>[\d.]+)$")
    uncalled_re=_re.compile(r"^Uncalled bet \(£(?P<amt>[\d.]+)\) returned to (?P<name>.+?)$")

    current_street='PREFLOP'
    result['streets']['PREFLOP']={'board':[],'actions':[]}
    in_summary=False
    unmatched=[]

    for line in lines:
        if line=='*** HOLE CARDS ***': continue
        if summary_start_re.match(line):
            in_summary=True; continue
        if not in_summary:
            m=header_re.search(line)
            if m: result['header']=m.groupdict(); continue
            m=table_info_re.match(line)
            if m:
                result['header']['table_size']=int(m['size'])
                result['header']['blinds_str']=m['blinds']; continue
            m=table_name_re.match(line)
            if m:
                result['header']['table_name']=m['name']
                result['header']['table_id']=m['tableid']; continue
            m=seat_re.match(line)
            if m:
                seat={'seat':int(m['seat']),'name':m['name'],'stack':float(m['stack'])}
                result['seats'].append(seat)
                if m['dealer']: result['button_seat']=int(m['seat'])
                continue
            m=post_re.match(line)
            if m:
                result['posts'].append({'name':m['name'],'type':m['type'],'amount':float(m['amt'])})
                continue
            m=dealt_re.match(line)
            if m:
                result['hole_cards'][m['name']]=[m['c1'],m['c2']]; continue
            m=street_hdr_re.match(line)
            if m:
                current_street=m['street']
                result['streets'][current_street]={'board':m['cards'].split(),'actions':[]}
                continue
            m=uncalled_re.match(line)
            if m:
                result['streets'][current_street]['actions'].append(
                    {'name':m['name'],'action':'UNCALLED_RETURN','amount':float(m['amt'])})
                continue
            m=action_re.match(line)
            if m:
                result['streets'][current_street]['actions'].append({
                    'name':m['name'],'action':m['action'].replace(' (NF)',''),
                    'amount':float(m['amt']) if m['amt'] else None})
                continue
            unmatched.append(('preflop/action section',line))
        else:
            m=total_pot_re.match(line)
            if m:
                result['summary']['total_pot']=float(m['pot'])
                result['summary']['rake']=float(m['rake']) if m['rake'] else 0.0
                continue
            m=shows_re.match(line)
            if m:
                result['summary'].setdefault('shows',[]).append(
                    {'name':m['name'],'cards':[m['c1'],m['c2']],'desc':m['desc']})
                continue
            m=wins_re.match(line)
            if m:
                result['summary'].setdefault('wins',[]).append(
                    {'name':m['name'],'amount':float(m['amt'])})
                continue
            unmatched.append(('summary section',line))

    result['unmatched']=unmatched
    return result


def build_replay_events(parsed):
    """Flatten a parsed hand into an ordered list of replay events."""
    events=[]
    for p in parsed['posts']:
        events.append({'kind':'post','name':p['name'],'amount':p['amount'],
                        'text':f"{p['name']} posts {p['type']} £{p['amount']:.2f}"})
    for name,cards in parsed['hole_cards'].items():
        disp=[hh_card_to_display(c) for c in cards]
        events.append({'kind':'deal','name':name,'cards':disp,
                        'text':f"Dealt to {name}: {' '.join(disp)}"})
    for street in ['PREFLOP','FLOP','TURN','RIVER']:
        data=parsed['streets'].get(street)
        if not data: continue
        if street!='PREFLOP':
            disp=[hh_card_to_display(c) for c in data['board']]
            events.append({'kind':'street','street':street,'cards':disp,
                            'text':f"*** {street} *** {' '.join(disp)}"})
        for a in data['actions']:
            if a['action']=='UNCALLED_RETURN':
                events.append({'kind':'uncalled','name':a['name'],'amount':a['amount'],
                                'text':f"Uncalled bet £{a['amount']:.2f} returned to {a['name']}"})
            else:
                amt_txt=f" £{a['amount']:.2f}" if a['amount'] is not None else ""
                events.append({'kind':'action','name':a['name'],'action':a['action'],
                                'amount':a['amount'],
                                'text':f"{a['name']}: {a['action']}{amt_txt}"})
    for s in parsed['summary'].get('shows',[]):
        disp=[hh_card_to_display(c) for c in s['cards']]
        events.append({'kind':'show','name':s['name'],'cards':disp,'desc':s['desc'],
                        'text':f"{s['name']} shows {' '.join(disp)} — {s['desc']}"})
    for w in parsed['summary'].get('wins',[]):
        events.append({'kind':'win','name':w['name'],'amount':w['amount'],
                        'text':f"{w['name']} wins £{w['amount']:.2f}"})
    return events

# ─── THEME ────────────────────────────────────────────────────────────────────
BG      = "#0d1117"
BG2     = "#161b22"
BG3     = "#21262d"
ACCENT  = "#1f6feb"
ACCENT2 = "#388bfd"
GREEN   = "#3fb950"
RED     = "#f85149"
ORANGE  = "#d29922"
YELLOW  = "#e3b341"
TEXT    = "#e6edf3"
DIM     = "#8b949e"
BORDER  = "#30363d"

STYLE = f"""
QMainWindow, QWidget {{ background:{BG}; color:{TEXT}; font-family:'Segoe UI',Arial; font-size:13px; }}
QTabWidget::pane {{ border:1px solid {BORDER}; background:{BG2}; border-radius:6px; }}
QTabBar::tab {{ background:{BG3}; color:{DIM}; padding:10px 24px; border:1px solid {BORDER};
    border-bottom:none; border-radius:6px 6px 0 0; margin-right:2px; font-size:13px; font-weight:500; }}
QTabBar::tab:selected {{ background:{BG2}; color:{TEXT}; border-bottom:2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ background:{BG2}; color:{TEXT}; }}
QComboBox {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    padding:6px 12px; font-size:13px; min-width:130px; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox QAbstractItemView {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER};
    selection-background-color:{ACCENT}; }}
QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:6px;
    padding:8px 20px; font-size:13px; font-weight:600; }}
QPushButton:hover {{ background:{ACCENT2}; }}
QTableWidget {{ background:{BG2}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    gridline-color:{BORDER}; font-size:12px; alternate-background-color:{BG3}; }}
QTableWidget::item {{ padding:6px 12px; border-bottom:1px solid {BORDER}; }}
QTableWidget::item:selected {{ background:{ACCENT}; color:white; }}
QHeaderView::section {{ background:{BG3}; color:{DIM}; border:none; border-bottom:1px solid {BORDER};
    padding:8px 12px; font-size:12px; font-weight:600; }}
QScrollBar:vertical {{ background:{BG}; width:8px; border-radius:4px; }}
QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:4px; min-height:30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
QFrame#card {{ background:{BG2}; border:1px solid {BORDER}; border-radius:8px; }}
QProgressBar {{ background:{BG3}; border:1px solid {BORDER}; border-radius:4px; color:transparent; }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:4px; }}
QLineEdit {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    padding:6px 12px; font-size:13px; }}
QTextEdit {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    padding:8px; font-size:12px; }}
QSplitter::handle {{ background:{BORDER}; }}
"""

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def lbl(text, size=13, color=TEXT, bold=False, dim=False):
    l = QLabel(text)
    c = DIM if dim else color
    w = "700" if bold else "400"
    l.setStyleSheet(f"color:{c};font-size:{size}px;font-weight:{w};background:transparent;border:none;")
    return l

def date_range(period):
    today = date.today()
    if period == "Today":       return today, today
    if period == "Yesterday":   y=today-timedelta(1); return y,y
    if period == "This Week":   return today-timedelta((today.weekday()+1)%7), today
    if period == "This Month":  return date(today.year,today.month,1), today
    if period == "Last Month":
        f=date(today.year,today.month,1)-timedelta(1); return date(f.year,f.month,1),f
    if period == "This Year":   return date(today.year,1,1), today
    if period == "Last Year":   return date(today.year-1,1,1), date(today.year-1,12,31)
    return date(today.year,1,1), today

def filter_hands(all_hands, d_from, d_to, id_limit=None):
    return [h for h in all_hands
            if d_from <= h['d'] <= d_to
            and (id_limit is None or h['id_limit'] == id_limit)]

def calc_stats(hands):
    if not hands: return None
    n=len(hands); profit=sum(h['profit'] for h in hands)
    bb100=round(100*sum(h['profit']/h['bb_conv'] for h in hands if h['bb_conv'])/n,2) if n else 0
    ev_bb100=round(100*sum(h['ev_profit']/h['bb_conv'] for h in hands if h['bb_conv'])/n,2) if n else 0
    def pct(n,d): return round(100*n/d,2) if d else 0
    return dict(
        n=n, profit=round(profit,2), bb100=bb100, ev_bb100=ev_bb100,
        vpip=pct(sum(h['vpip'] for h in hands),n-sum(h['walk'] for h in hands)),
        pfr=pct(sum(h['pfr_n'] for h in hands),sum(h['pfr_d'] for h in hands)),
        threebet=pct(sum(h['tb_n'] for h in hands),sum(h['tb_d'] for h in hands)),
        fold3bet=pct(sum(h['f3_n'] for h in hands),sum(h['f3_d'] for h in hands)),
        fourbet=pct(sum(h['fb_n'] for h in hands),sum(h['fb_d'] for h in hands)),
        fold4bet=pct(sum(h['f4_n'] for h in hands),sum(h['fb_d'] for h in hands)),
        wtsd=pct(sum(h['sd'] for h in hands),sum(h['saw_f'] for h in hands)),
        wsd=pct(sum(h['sd_won'] for h in hands),sum(h['sd'] for h in hands)),
        wwsf=pct(sum(h['saw_f_won'] for h in hands),sum(h['saw_f'] for h in hands)),
    )

def calc_sessions(hands):
    from collections import defaultdict
    sess=defaultdict(lambda:{'hands':[],'stake':'','ts':[]})
    for h in hands:
        k=(h['d'],h['id_limit']); sess[k]['hands'].append(h)
        sess[k]['stake']=h['stake']; sess[k]['ts'].append(h['ts'])
    result=[]
    for (d,_),v in sorted(sess.items(),reverse=True):
        hs=v['hands']; profit=sum(x['profit'] for x in hs)
        bb_c=sum(x['bb_conv'] for x in hs)
        bb100=round(profit/bb_c*100,2) if bb_c else 0
        ts=v['ts']; hours=round((max(ts)-min(ts)).total_seconds()/3600,2) if len(ts)>1 else 0
        result.append((d,v['stake'],len(hs),round(profit,2),bb100,hours))
    return result

def calc_graph(hands):
    """Per-hand cumulative series (not per-date) so 'Hands' is a meaningful
    x-axis, split the same way the villain profile graph is: Total,
    Showdown-only, Non-Showdown-only, and EV-adjusted."""
    ordered=sorted(hands, key=lambda h: h['ts'])
    xs=[]; total=[]; sd=[]; nonsd=[]; ev=[]
    run_t=run_sd=run_nsd=run_ev=0.0
    for i,h in enumerate(ordered):
        run_t+=h['profit']
        if h['sd']: run_sd+=h['profit']
        else: run_nsd+=h['profit']
        run_ev+=h.get('ev_profit',h['profit'])
        xs.append(i+1)
        total.append(round(run_t,2)); sd.append(round(run_sd,2))
        nonsd.append(round(run_nsd,2)); ev.append(round(run_ev,2))
    return xs,total,sd,nonsd,ev

def classify_player(vpip, pfr, threebet, wtsd):
    """Classify villain into player type"""
    if vpip is None: return "Unknown", DIM
    aggr = pfr/vpip*100 if vpip else 0
    if vpip < 15:                          return "Nit 🧊",        "#88c0d0"
    if vpip < 22 and aggr > 70:            return "Tight Reg 🎯",  ACCENT2
    if 22 <= vpip <= 28 and aggr >= 65:    return "Winning Reg ⚡", GREEN
    if vpip > 35 and aggr < 50:            return "Calling Station 📞", ORANGE
    if vpip > 30 and pfr > 25:             return "LAG 🔥",         RED
    if vpip > 30:                          return "Fish 🐟",        "#f08c00"
    if vpip > 28 and aggr < 55:            return "Passive Reg 😴", DIM
    return "Reg 🃏", ACCENT2

def generate_leaks(stats):
    """Generate exploit notes based on villain stats"""
    leaks = []
    v = stats
    if not v: return leaks

    vpip=v.get('vpip',0) or 0; pfr=v.get('pfr',0) or 0
    tb=v.get('threebet',0) or 0; f3=v.get('fold3bet',0) or 0
    fb=v.get('fourbet',0) or 0; f4=v.get('fold4bet',0) or 0
    wtsd=v.get('wtsd',0) or 0; wsd=v.get('wsd',0) or 0
    fcbet=v.get('fold_fcbet',0) or 0

    # 3Bet leaks
    if tb < 4:
        leaks.append(("🔴","Extremely low 3Bet","Their 3bets are always premium hands. Fold everything but AA/KK/AK vs their 3bets."))
    elif tb < 7:
        leaks.append(("🟠","Low 3Bet","Steal aggressively — they rarely push back preflop."))
    if f3 > 70:
        leaks.append(("🔴","Over-folds to 3Bets","3Bet them relentlessly from any position. They give up too easily."))
    elif f3 > 60:
        leaks.append(("🟠","Folds too much to 3Bets","Increase 3Bet frequency — they're not defending enough."))
    if f3 < 40:
        leaks.append(("🔵","Defends vs 3Bets well","Tighten your 3Bet range — only 3Bet for value vs this player."))

    # 4Bet leaks
    if fb > 12:
        leaks.append(("🔴","Over-4Bets","They're bluffing 4Bets — call wider or 5Bet shove with your bluff catchers."))
    if f4 > 65:
        leaks.append(("🔴","Folds to 4Bets","4Bet bluff them frequently — they can't handle the pressure."))

    # Postflop leaks
    if fcbet > 60:
        leaks.append(("🔴","Folds to CBets","CBet wide vs this player — they give up too often on the flop."))
    elif fcbet > 50:
        leaks.append(("🟠","Above average fold to CBet","Slightly increase CBet frequency vs this player."))
    if fcbet and fcbet < 35:
        leaks.append(("🔵","Calls CBets wide","Only CBet for value — they float too much. Check back marginal hands."))

    # WTSD leaks
    if wtsd > 36:
        leaks.append(("🔴","Goes to showdown too often","Value bet relentlessly — they can't fold. Never bluff this player."))
    elif wtsd > 30:
        leaks.append(("🟠","Slightly high WTSD","Lean towards value bets. Bluffs are less profitable vs this player."))
    if wtsd < 22:
        leaks.append(("🔴","Over-folds on later streets","Bluff rivers and turns — they give up too easily postflop."))

    # W$SD leaks
    if wsd < 45:
        leaks.append(("🔴","Loses at showdown","They go to showdown with weak hands — bluff catch and thin value bet."))

    # VPIP leaks
    if vpip > 40:
        leaks.append(("🔴","Extremely loose preflop","They play too many hands — their range is weak. Value bet thinly."))
    elif vpip > 30:
        leaks.append(("🟠","Loose preflop","Their range is wider than average — exploit with strong hands."))

    if not leaks:
        leaks.append(("🟢","No major leaks detected","This appears to be a solid player. Play closer to GTO vs them."))

    return leaks

# ─── BACKGROUND LOADERS ───────────────────────────────────────────────────────

class DataLoader(QThread):
    progress = pyqtSignal(int, str)
    done     = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, hero):
        super().__init__(); self.hero=hero

    def run(self):
        try:
            conn=psycopg2.connect(**DB); cur=conn.cursor()
            self.progress.emit(10,"Loading hand data...")
            cur.execute("""
                SELECT chs.date_played::date,cl.id_limit,cl.limit_name,cl.amt_bb,
                    chps.amt_won*chps.val_curr_conv,cl.amt_bb*chps.val_curr_conv,
                    CASE WHEN flg_vpip THEN 1 ELSE 0 END,
                    CASE WHEN cnt_p_raise>0 THEN 1 ELSE 0 END,
                    CASE WHEN la_p.action LIKE '__%%'
                        OR (la_p.action LIKE '_' AND amt_before>(cl.amt_bb+amt_ante)
                            AND amt_p_raise_facing<(amt_before-(amt_blind+amt_ante))
                            AND (flg_p_open_opp OR cnt_p_face_limpers>0 OR flg_p_3bet_opp OR flg_p_4bet_opp))
                        THEN 1 ELSE 0 END,
                    CASE WHEN flg_p_3bet THEN 1 ELSE 0 END,
                    CASE WHEN flg_p_3bet_opp THEN 1 ELSE 0 END,
                    CASE WHEN flg_p_fold AND flg_p_3bet_def_opp THEN 1 ELSE 0 END,
                    CASE WHEN flg_p_3bet_def_opp THEN 1 ELSE 0 END,
                    CASE WHEN flg_p_4bet THEN 1 ELSE 0 END,
                    CASE WHEN flg_p_4bet_opp THEN 1 ELSE 0 END,
                    CASE WHEN flg_p_fold AND flg_p_4bet_opp THEN 1 ELSE 0 END,
                    CASE WHEN flg_showdown THEN 1 ELSE 0 END,
                    CASE WHEN flg_f_saw THEN 1 ELSE 0 END,
                    CASE WHEN flg_showdown AND flg_won_hand THEN 1 ELSE 0 END,
                    chs.date_played,
                    CASE WHEN la_p.action='' THEN 1 ELSE 0 END,
                    chps.amt_expected_won*chps.val_curr_conv,
                    CASE WHEN flg_f_saw AND flg_won_hand THEN 1 ELSE 0 END
                FROM cash_hand_player_statistics chps
                JOIN cash_hand_summary chs ON chps.id_hand=chs.id_hand
                JOIN player p ON chps.id_player=p.id_player
                JOIN cash_limit cl ON chs.id_limit=cl.id_limit
                LEFT JOIN lookup_actions la_p ON chps.id_action_p=la_p.id_action
                WHERE p.player_name=%s
                ORDER BY chs.date_played
            """, (self.hero,))
            rows=cur.fetchall()
            self.progress.emit(70,"Processing hand data...")
            hands=[dict(d=r[0],id_limit=r[1],stake=r[2],amt_bb=float(r[3]),
                        profit=float(r[4]),bb_conv=float(r[5]),
                        vpip=r[6],pfr_n=r[7],pfr_d=r[8],tb_n=r[9],tb_d=r[10],
                        f3_n=r[11],f3_d=r[12],fb_n=r[13],fb_d=r[14],f4_n=r[15],
                        sd=r[16],saw_f=r[17],sd_won=r[18],ts=r[19],walk=r[20],
                        ev_profit=float(r[21]) if r[21] is not None else float(r[4]),
                        saw_f_won=r[22]) for r in rows]

            self.progress.emit(85,"Loading villain list...")
            # Store per-hand villain data: (villain_name, date, hero_profit_this_hand)
            # hero profit = what hero won in hands where this villain was seated
            cur.execute("""
                SELECT
                    p2.player_name,
                    chs.date_played::date,
                    hero.amt_won * hero.val_curr_conv AS hero_profit,
                    CASE WHEN vil.flg_vpip THEN 1 ELSE 0 END,
                    CASE WHEN vil.cnt_p_raise>0 THEN 1 ELSE 0 END,
                    CASE WHEN la_p.action LIKE '__%%'
                        OR (la_p.action LIKE '_' AND vil.amt_before>(cl.amt_bb+vil.amt_ante)
                            AND vil.amt_p_raise_facing<(vil.amt_before-(vil.amt_blind+vil.amt_ante))
                            AND (vil.flg_p_open_opp OR vil.cnt_p_face_limpers>0 OR vil.flg_p_3bet_opp OR vil.flg_p_4bet_opp))
                        THEN 1 ELSE 0 END,
                    CASE WHEN vil.flg_p_3bet THEN 1 ELSE 0 END,
                    CASE WHEN vil.flg_p_3bet_opp THEN 1 ELSE 0 END,
                    CASE WHEN vil.flg_showdown THEN 1 ELSE 0 END,
                    CASE WHEN vil.flg_f_saw THEN 1 ELSE 0 END,
                    CASE WHEN la_p.action='' THEN 1 ELSE 0 END
                FROM cash_hand_summary chs
                JOIN cash_hand_player_statistics hero ON hero.id_hand=chs.id_hand
                JOIN player hp ON hero.id_player=hp.id_player AND hp.player_name=%s
                JOIN cash_hand_player_statistics vil ON vil.id_hand=chs.id_hand
                JOIN player p2 ON vil.id_player=p2.id_player AND p2.player_name != %s
                JOIN cash_limit cl ON chs.id_limit=cl.id_limit
                LEFT JOIN lookup_actions la_p ON vil.id_action_p=la_p.id_action
            """, (self.hero, self.hero))
            raw_villains=cur.fetchall()
            villains=raw_villains
            cur.close(); conn.close()
            self.progress.emit(95,"Almost done...")
            self.done.emit({'hands':hands,'villains':villains})
        except Exception as e:
            self.error.emit(str(e))


class OverviewTab(QWidget):
    def __init__(self):
        super().__init__()
        lay=QVBoxLayout(self); lay.setContentsMargins(20,20,20,20); lay.setSpacing(16)

        lay.addWidget(lbl("PROFIT",size=11,dim=True))

        self.plot=pg.PlotWidget(); self.plot.setMinimumHeight(240)
        self.plot.setBackground(BG2)
        self.plot.showGrid(x=True,y=True,alpha=0.15)
        pi=self.plot.getPlotItem()
        pi.hideAxis('left')
        pi.showAxis('right')
        pi.getAxis('right').linkToView(pi.vb)
        pi.getAxis('right').setLabel('Profit ($)')
        pi.getAxis('bottom').setLabel('Hands')
        pi.vb.setMouseEnabled(x=False, y=False)  # lock: no scroll/drag zoom or pan
        pi.setMenuEnabled(False)
        self.plot.setMouseTracking(False)
        zero_line=pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color="#8b949e", width=1.2))
        pi.addItem(zero_line)

        self.c_total=self.plot.plot(pen=pg.mkPen(color=GREEN,width=2.5))
        self.c_sd   =self.plot.plot(pen=pg.mkPen(color=ACCENT2,width=1.5))
        self.c_nsd  =self.plot.plot(pen=pg.mkPen(color=RED,width=1.5))
        self.c_ev   =self.plot.plot(pen=pg.mkPen(color=YELLOW,width=1.5))
        lay.addWidget(self.plot)

        # Legend row with checkboxes so lines can be hidden before screenshotting
        legend_row=QHBoxLayout(); legend_row.setSpacing(18)
        self._line_checks={}
        legend_defs=[("Total",self.c_total,GREEN),("Showdown",self.c_sd,ACCENT2),
                     ("Non-Showdown",self.c_nsd,RED),("EV",self.c_ev,YELLOW)]
        for name,curve,color in legend_defs:
            cb=QCheckBox(name)
            cb.setChecked(True)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(f"""
                QCheckBox {{ color:{color}; font-size:11px; font-weight:600; spacing:6px; }}
                QCheckBox::indicator {{
                    width:12px; height:12px; border-radius:3px;
                    border:1.5px solid {color}; background:{BG3};
                }}
                QCheckBox::indicator:checked {{ background:{color}; }}
            """)
            cb.toggled.connect(lambda checked,c=curve: c.setVisible(checked))
            self._line_checks[name]=cb
            legend_row.addWidget(cb)
        legend_row.addStretch()
        legend_w=QWidget(); legend_w.setLayout(legend_row)
        lay.addWidget(legend_w)

        lay.addWidget(lbl("STATS",size=11,dim=True))
        grid_w=QWidget(); self.grid=QGridLayout(grid_w)
        self.grid.setContentsMargins(0,0,0,0); self.grid.setSpacing(10)
        lay.addWidget(grid_w)
        lay.addStretch()

        self.defs=[
            ("Hands","n",None,None),("Profit ($)","profit",None,None),
            ("Win Rate bb/100","bb100",None,None),("EV bb/100","ev_bb100",None,None),
            ("VPIP %","vpip",22,26),("PFR %","pfr",17,21),("3Bet %","threebet",8,10),
            ("Fold to Preflop 3Bet %","fold3bet",50,60),("4Bet %","fourbet",2,4),
            ("Fold 4Bet %","fold4bet",45,55),
            ("WTSD %","wtsd",26,32),("WWSF %","wwsf",38,46),("W$SD %","wsd",50,56),
        ]
        self.cards={}
        for i,(title,key,lo,hi) in enumerate(self.defs):
            card=QFrame(); card.setObjectName("card")
            cl=QVBoxLayout(card); cl.setContentsMargins(10,8,10,8); cl.setSpacing(2)
            cl.addWidget(lbl(title,size=10,dim=True))
            val_lbl=lbl("—",size=16,bold=True)
            cl.addWidget(val_lbl)
            self.cards[key]=val_lbl
            self.grid.addWidget(card,i//6,i%6)

    def refresh(self, stats, graph):
        if not stats:
            for v in self.cards.values(): v.setText("—")
            self.c_total.setData([],[]); self.c_sd.setData([],[])
            self.c_nsd.setData([],[]); self.c_ev.setData([],[])
            return
        for title,key,lo,hi in self.defs:
            v=stats.get(key)
            if v is None:
                self.cards[key].setText("—"); continue
            if key=="n":
                txt=f"{int(v):,}"; col=TEXT
            elif key=="profit":
                txt=f"${v:+,.2f}"; col=GREEN if v>=0 else RED
            elif key=="bb100" or key=="ev_bb100":
                txt=f"{v:+.2f}"; col=GREEN if v>=0 else RED
            else:
                fv=float(v); m=(hi-lo)*0.5
                if lo<=fv<=hi:            col=GREEN
                elif (lo-m)<=fv<=(hi+m): col=ORANGE
                else:                     col=RED
                txt=f"{v}%"
            self.cards[key].setText(txt)
            self.cards[key].setStyleSheet(f"color:{col};font-size:16px;font-weight:700;background:transparent;border:none;")

        xs,total,sd,nonsd,ev=graph
        if xs:
            self.c_total.setData(xs,total,pen=pg.mkPen(color=GREEN,width=2.5))
            self.c_sd.setData(xs,sd)
            self.c_nsd.setData(xs,nonsd)
            self.c_ev.setData(xs,ev)
            self.plot.getPlotItem().vb.setXRange(xs[0], xs[-1], padding=0)
        else:
            self.c_total.setData([],[]); self.c_sd.setData([],[])
            self.c_nsd.setData([],[]); self.c_ev.setData([],[])


class SessionsTab(QWidget):
    def __init__(self):
        super().__init__()
        lay=QVBoxLayout(self); lay.setContentsMargins(20,20,20,20); lay.setSpacing(12)
        lay.addWidget(lbl("SESSIONS",size=11,dim=True))
        self.table=QTableWidget()
        cols=["Date","Stakes","Hands","Profit ($)","BB/100","Hours","Running Total"]
        self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table)

    def refresh(self, sessions):
        self.table.setRowCount(0)
        running=0.0
        for s in sessions:
            d,stake,hands,profit,bb100,hours=s
            running+=profit
            r=self.table.rowCount(); self.table.insertRow(r)
            vals=[
                (str(d),None),(stake,None),(f"{hands:,}",None),
                (f"${profit:+,.2f}",GREEN if profit>=0 else RED),
                (f"{bb100:+.2f}",GREEN if bb100>=0 else RED),
                (f"{hours:.1f}h",None),
                (f"${running:+,.2f}",GREEN if running>=0 else RED),
            ]
            for c,(val,col) in enumerate(vals):
                item=QTableWidgetItem(val); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col: item.setForeground(QColor(col))
                self.table.setItem(r,c,item)
            self.table.setRowHeight(r,32)


class VillainLoader(QThread):
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, hero, villain_name, d_from, d_to):
        super().__init__()
        self.hero=hero; self.villain=villain_name
        self.d_from=d_from; self.d_to=d_to

    def run(self):
        try:
            conn=psycopg2.connect(**DB); cur=conn.cursor()

            # Full villain stats
            # Villain own stats (all time for larger sample)
            cur.execute("""
                SELECT
                    COUNT(*) as hands,
                    ROUND(100.0*SUM(chps.amt_won/NULLIF(cl.amt_bb,0))/
                        NULLIF(COUNT(*),0),2),
                    ROUND(100.0*SUM(chps.amt_expected_won/NULLIF(cl.amt_bb,0))/
                        NULLIF(COUNT(*),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_vpip THEN 1 ELSE 0 END)/
                        NULLIF(COUNT(*)-SUM(CASE WHEN la_p.action='' THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN cnt_p_raise>0 THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN la_p.action LIKE '__%%'
                            OR (la_p.action LIKE '_' AND amt_before>(cl.amt_bb+amt_ante)
                                AND amt_p_raise_facing<(amt_before-(amt_blind+amt_ante))
                                AND (flg_p_open_opp OR cnt_p_face_limpers>0 OR flg_p_3bet_opp OR flg_p_4bet_opp))
                            THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_p_3bet THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_p_3bet_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_p_fold AND flg_p_3bet_def_opp THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_p_3bet_def_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_p_4bet THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_p_4bet_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_p_fold AND flg_p_4bet_opp THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_p_4bet_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_showdown THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_f_saw THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_showdown AND flg_won_hand THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_showdown THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_f_cbet AND flg_f_cbet_opp THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_f_cbet_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_f_saw AND flg_won_hand THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_f_saw THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_f_fold AND flg_f_cbet_def_opp THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_f_cbet_def_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_f_check_raise THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_f_cbet_def_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_f_fold AND flg_f_cbet AND flg_f_face_raise THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_f_cbet AND flg_f_face_raise THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN (la_p.action='C' OR la_p.action='CC')
                        AND flg_p_face_raise AND flg_f_bet
                        AND char_length(chs.str_aggressors_p)=2
                        AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_p from 2 for 1)::int>chps.position)
                             OR (chs.cnt_players=2 AND flg_f_has_position))
                        THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN (la_p.action='C' OR la_p.action='CC')
                        AND flg_p_face_raise AND flg_f_open_opp
                        AND char_length(chs.str_aggressors_p)=2
                        AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_p from 2 for 1)::int>chps.position)
                             OR (chs.cnt_players=2 AND flg_f_has_position))
                        THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN NOT flg_p_face_raise AND la_p.action LIKE '%%R'
                        AND flg_f_open_opp AND amt_f_bet_facing>0
                        AND substring(la_f.action from 1 for 2) = 'XF'
                        THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN NOT flg_p_face_raise AND la_p.action LIKE '%%R'
                        AND flg_f_open_opp AND flg_f_check AND amt_f_bet_facing>0
                        THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_t_cbet AND flg_t_cbet_opp THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_t_cbet_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_t_fold AND flg_t_cbet_def_opp THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_t_cbet_def_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_t_check_raise THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_t_cbet_def_opp THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_t_fold AND flg_t_cbet AND flg_t_face_raise THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_t_cbet AND flg_t_face_raise THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN flg_t_bet
                        AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R%%'
                        AND flg_p_face_raise
                        AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                             OR (chs.cnt_players=2 AND flg_blind_b))
                        THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN flg_t_open_opp
                        AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R%%'
                        AND flg_p_face_raise
                        AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                             OR (chs.cnt_players=2 AND flg_blind_b))
                        THEN 1 ELSE 0 END),0),2),
                    ROUND(100.0*SUM(CASE WHEN amt_t_bet_facing>0
                        AND flg_f_cbet_opp AND la_f.action = 'X'
                        AND NOT flg_t_open_opp AND la_t.action = 'F'
                        THEN 1 ELSE 0 END)/
                        NULLIF(SUM(CASE WHEN amt_t_bet_facing>0
                        AND flg_f_cbet_opp AND la_f.action = 'X'
                        AND NOT flg_t_open_opp
                        THEN 1 ELSE 0 END),0),2)
                FROM cash_hand_player_statistics chps
                LEFT JOIN lookup_actions la_f ON chps.id_action_f=la_f.id_action
                LEFT JOIN lookup_actions la_p ON chps.id_action_p=la_p.id_action
                LEFT JOIN lookup_actions la_t ON chps.id_action_t=la_t.id_action
                LEFT JOIN lookup_actions la_r ON chps.id_action_r=la_r.id_action
                JOIN cash_hand_summary chs ON chps.id_hand=chs.id_hand
                JOIN player p ON chps.id_player=p.id_player
                JOIN cash_limit cl ON chs.id_limit=cl.id_limit
                WHERE p.player_name=%s
                AND chs.date_played::date BETWEEN %s AND %s
            """, (self.villain, self.d_from, self.d_to))
            vstats=cur.fetchone()

            # Hero profit vs villain — graph data
            # Per-hand data — villain's own results + hero's profit vs them
            cur.execute("""
                SELECT
                    ROW_NUMBER() OVER (ORDER BY chs.date_played)                       AS hand_num,
                    ROUND((vil.amt_won * vil.val_curr_conv)::numeric, 4)               AS vil_profit,
                    ROUND((CASE WHEN vil.flg_showdown
                        THEN vil.amt_won*vil.val_curr_conv ELSE 0 END)::numeric, 4)    AS vil_sd,
                    ROUND((CASE WHEN NOT vil.flg_showdown
                        THEN vil.amt_won*vil.val_curr_conv ELSE 0 END)::numeric, 4)    AS vil_nsd,
                    ROUND((vil.amt_expected_won * vil.val_curr_conv)::numeric, 4)      AS vil_ev,
                    ROUND((hero.amt_won * hero.val_curr_conv)::numeric, 4)             AS hero_profit
                FROM cash_hand_summary chs
                JOIN cash_hand_player_statistics hero ON hero.id_hand=chs.id_hand
                JOIN player hp ON hero.id_player=hp.id_player AND hp.player_name=%s
                JOIN cash_hand_player_statistics vil ON vil.id_hand=chs.id_hand
                JOIN player vp ON vil.id_player=vp.id_player AND vp.player_name=%s
                WHERE chs.date_played::date BETWEEN %s AND %s
                ORDER BY chs.date_played
            """, (self.hero, self.villain, self.d_from, self.d_to))
            graph=cur.fetchall()
            cur.close(); conn.close()

            self.done.emit({'vstats':vstats,'graph':graph})
        except Exception as e:
            self.error.emit(str(e))


class HeroStatsLoader(QThread):
    """Computes every stat in STAT_REGISTRY in a single query pass, always -
    which stats get displayed is a UI-layer choice (see settings), not a
    query-layer one, so toggling visibility never needs a new query."""
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, hero, d_from, d_to, id_limit=None):
        super().__init__()
        self.hero=hero; self.d_from=d_from; self.d_to=d_to; self.id_limit=id_limit

    def run(self):
        try:
            conn=psycopg2.connect(**DB); cur=conn.cursor()
            stakes_clause = "AND cl.id_limit=%s" if self.id_limit is not None else ""
            params=[self.hero, self.d_from, self.d_to]
            if self.id_limit is not None: params.append(self.id_limit)
            select_parts = ["COUNT(*) as hands"] + [f"ROUND({s['sql']},2)" for s in STAT_REGISTRY]
            cur.execute(f"""
                SELECT {", ".join(select_parts)}
                FROM cash_hand_player_statistics chps
                LEFT JOIN lookup_actions la_f ON chps.id_action_f=la_f.id_action
                LEFT JOIN lookup_actions la_p ON chps.id_action_p=la_p.id_action
                LEFT JOIN lookup_actions la_t ON chps.id_action_t=la_t.id_action
                LEFT JOIN lookup_actions la_r ON chps.id_action_r=la_r.id_action
                JOIN cash_hand_summary chs ON chps.id_hand=chs.id_hand
                JOIN player p ON chps.id_player=p.id_player
                JOIN cash_limit cl ON chs.id_limit=cl.id_limit
                WHERE p.player_name=%s
                AND chs.date_played::date BETWEEN %s AND %s
                {stakes_clause}
            """, tuple(params))
            row=cur.fetchone()
            cur.close(); conn.close()
            if not row or row[0] is None:
                self.done.emit({'hands': 0, 'values': {}})
                return
            values={STAT_REGISTRY[i]['id']: row[i+1] for i in range(len(STAT_REGISTRY))}
            self.done.emit({'hands': int(row[0]), 'values': values})
        except Exception as e:
            self.error.emit(str(e))


class StatsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self._last_data = None  # cached {'hands':N,'values':{id:val}} so toggling visibility needs no re-query

        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)

        header=QHBoxLayout(); header.setContentsMargins(20,16,20,0)
        header.addWidget(lbl("YOUR STATS",size=11,dim=True))
        header.addStretch()
        self.customize_btn=QPushButton("Customize Stats")
        self.customize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.customize_btn.setStyleSheet(
            f"QPushButton{{background:{BG3};border:1px solid {BORDER};border-radius:5px;"
            f"color:{TEXT};font-size:11px;padding:5px 12px;}}"
            f"QPushButton:hover{{background:#30363d;}}")
        self.customize_btn.clicked.connect(self._open_customize_dialog)
        header.addWidget(self.customize_btn)
        header_w=QWidget(); header_w.setLayout(header)
        outer.addWidget(header_w)

        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner=QWidget()
        self.lay=QVBoxLayout(inner); self.lay.setContentsMargins(20,12,20,20); self.lay.setSpacing(16)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        self.status_lbl=lbl("Loading your stats...",dim=True)
        self.lay.addWidget(self.status_lbl)
        self.loader=None
        self._active_loaders=[]  # keep running QThreads referenced so Python doesn't GC them mid-flight
        self._load_gen=0  # only the most recently requested load's result gets applied

    def load(self, hero, d_from, d_to, id_limit):
        self.status_lbl.setText("Loading your stats..."); self.status_lbl.show()
        self._load_gen+=1
        my_gen=self._load_gen
        loader=HeroStatsLoader(hero, d_from, d_to, id_limit)
        self._active_loaders.append(loader)
        def _cleanup(l=loader):
            if l in self._active_loaders: self._active_loaders.remove(l)
        loader.done.connect(lambda data,g=my_gen: self._on_loaded(data,g))
        loader.error.connect(lambda e: self.status_lbl.setText(f"Error: {e}"))
        loader.finished.connect(_cleanup)
        self.loader=loader
        loader.start()

    def _clear_layout(self):
        while self.lay.count():
            item=self.lay.takeAt(0)
            w=item.widget()
            if w: w.deleteLater()

    def _make_stat_card(self, stat, sval):
        card=QFrame(); card.setObjectName("card")
        cl=QVBoxLayout(card); cl.setContentsMargins(10,8,10,8); cl.setSpacing(2)
        cl.addWidget(lbl(stat['label'],size=10,dim=True))
        if sval is not None:
            fv=float(sval)
            if stat['kind']=="rate":
                vc=GREEN if fv>=0 else RED
                vl=lbl(f"{fv:+.2f}",size=16,bold=True)
            elif stat['lo'] is None or stat['hi'] is None:
                vc="#d8dee9"
                vl=lbl(f"{sval}%",size=16,bold=True)
            else:
                lo,hi=stat['lo'],stat['hi']; m=(hi-lo)*0.5
                if lo<=fv<=hi:            vc=GREEN
                elif (lo-m)<=fv<=(hi+m): vc=ORANGE
                else:                     vc=RED
                vl=lbl(f"{sval}%",size=16,bold=True)
            vl.setStyleSheet(f"color:{vc};font-size:16px;font-weight:700;background:transparent;border:none;")
            cl.addWidget(vl)
        else:
            cl.addWidget(lbl("—",size=16,bold=True))
        return card

    def _on_loaded(self, data, gen):
        if gen != self._load_gen:
            return  # a newer load has since been requested; ignore this stale result
        self._last_data = data
        self._render()

    def _render(self):
        self._clear_layout()
        data = self._last_data
        if not data or not data.get('hands'):
            self.lay.addWidget(lbl("No hands in this period/stakes selection.",dim=True))
            self.lay.addStretch()
            return

        hands=data['hands']; values=data['values']
        visible=set(self.settings.get('visible_stats', []))

        for category in STAT_CATEGORIES:
            stats_in_cat=[s for s in STAT_REGISTRY if s['category']==category and s['id'] in visible]
            if not stats_in_cat: continue
            self.lay.addWidget(lbl(category.upper(),size=11,dim=True))
            grid_w=QWidget(); grid=QGridLayout(grid_w)
            grid.setContentsMargins(0,0,0,0); grid.setSpacing(10)
            for i,stat in enumerate(stats_in_cat):
                grid.addWidget(self._make_stat_card(stat, values.get(stat['id'])), i//6, i%6)
            self.lay.addWidget(grid_w)

        if not any(s['id'] in visible for s in STAT_REGISTRY):
            self.lay.addWidget(lbl("No stats selected — click Customize Stats to choose some.",dim=True))

        self.lay.addWidget(lbl(f"{hands:,} hands in this selection",size=10,dim=True))
        self.lay.addStretch()

    def _open_customize_dialog(self):
        dlg=StatPickerDialog(self.settings.get('visible_stats', []), parent=self)
        if dlg.exec():
            self.settings['visible_stats']=dlg.get_selected_ids()
            save_settings(self.settings)
            self._render()


class CollapsibleSection(QWidget):
    """A header you can click to expand/collapse the checkboxes beneath it,
    so a long category list doesn't dominate the whole dialog. Starts
    collapsed so opening the dialog shows a clean list of section names
    rather than a wall of a hundred checkboxes."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._expanded=False
        self._title=title
        lay=QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)

        self.header_btn=QPushButton(f"▸  {title.upper()}")
        self.header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;color:{DIM};"
            f"font-size:11px;font-weight:600;text-align:left;padding:4px 0px;}}"
            f"QPushButton:hover{{color:{TEXT};}}")
        self.header_btn.clicked.connect(self._toggle)
        lay.addWidget(self.header_btn)

        self.body=QWidget()
        self.body_lay=QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(12,0,0,4); self.body_lay.setSpacing(6)
        self.body.setVisible(False)
        lay.addWidget(self.body)

    def _toggle(self):
        self._expanded = not self._expanded
        self.body.setVisible(self._expanded)
        arrow = "▾" if self._expanded else "▸"
        self.header_btn.setText(f"{arrow}  {self._title.upper()}")

    def add_widget(self, w):
        self.body_lay.addWidget(w)


class StatPickerDialog(QDialog):
    def __init__(self, current_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Stats")
        self.resize(440,600)
        self._checkboxes={}
        lay=QVBoxLayout(self)
        lay.addWidget(lbl("Choose which stats appear on your Stats tab. Click a section header to collapse it.",dim=True))

        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        inner=QWidget(); inner_lay=QVBoxLayout(inner); inner_lay.setSpacing(6)
        current_set=set(current_ids)
        for category in STAT_CATEGORIES:
            stats_in_cat=[s for s in STAT_REGISTRY if s['category']==category]
            if not stats_in_cat: continue
            section=CollapsibleSection(category)
            for stat in stats_in_cat:
                cb=QCheckBox(stat['label'])
                cb.setChecked(stat['id'] in current_set)
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                cb.setStyleSheet(f"""
                    QCheckBox {{ color:{TEXT}; font-size:12px; spacing:8px; padding:2px 0px; }}
                    QCheckBox::indicator {{
                        width:16px; height:16px; border-radius:4px;
                        border:1.5px solid {BORDER}; background:{BG3};
                    }}
                    QCheckBox::indicator:hover {{ border-color:{ACCENT2}; }}
                    QCheckBox::indicator:checked {{
                        border-color:{ACCENT2}; background:{ACCENT2};
                        image:none;
                    }}
                """)
                self._checkboxes[stat['id']]=cb
                section.add_widget(cb)
            inner_lay.addWidget(section)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll)

        btn_row=QHBoxLayout()
        select_all=QPushButton("Select All"); select_none=QPushButton("Select None")
        select_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self._checkboxes.values()])
        select_none.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checkboxes.values()])
        btn_row.addWidget(select_all); btn_row.addWidget(select_none); btn_row.addStretch()
        lay.addLayout(btn_row)

        save_row=QHBoxLayout()
        cancel_btn=QPushButton("Cancel"); save_btn=QPushButton("Save")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.accept)
        save_row.addStretch(); save_row.addWidget(cancel_btn); save_row.addWidget(save_btn)
        lay.addLayout(save_row)

    def get_selected_ids(self):
        return [sid for sid,cb in self._checkboxes.items() if cb.isChecked()]


# ─── STAT REGISTRY ─────────────────────────────────────────────────────────────
# Single source of truth for every stat the backend knows how to compute.
# Each entry: id (stable key for settings), label, category, kind ("pct" or
# "rate"), sql (the expression that goes inside ROUND(<sql>,2)), and lo/hi
# population range for color-coding (None when we don't have a benchmark).
# "default" controls whether it's shown out of the box before the user
# customizes their selection.
STAT_REGISTRY = [
    dict(id="bb100", label="BB/100", category="Overall", kind="rate",
         sql="100.0*SUM(chps.amt_won/NULLIF(cl.amt_bb,0))/NULLIF(COUNT(*),0)",
         lo=None, hi=None, default=True),
    dict(id="ev_bb100", label="EV BB/100", category="Overall", kind="rate",
         sql="100.0*SUM(chps.amt_expected_won/NULLIF(cl.amt_bb,0))/NULLIF(COUNT(*),0)",
         lo=None, hi=None, default=True),
    dict(id="vpip", label="VPIP", category="Preflop", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_vpip THEN 1 ELSE 0 END)/"
             "NULLIF(COUNT(*)-SUM(CASE WHEN la_p.action='' THEN 1 ELSE 0 END),0)",
         lo=22, hi=26, default=True),
    dict(id="pfr", label="PFR", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN cnt_p_raise>0 THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN la_p.action LIKE '__%%'
             OR (la_p.action LIKE '_' AND amt_before>(cl.amt_bb+amt_ante)
                 AND amt_p_raise_facing<(amt_before-(amt_blind+amt_ante))
                 AND (flg_p_open_opp OR cnt_p_face_limpers>0 OR flg_p_3bet_opp OR flg_p_4bet_opp))
             THEN 1 ELSE 0 END),0)""",
         lo=17, hi=21, default=True),
    dict(id="threebet", label="3Bet", category="Preflop", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_p_3bet THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_p_3bet_opp THEN 1 ELSE 0 END),0)",
         lo=8, hi=10, default=True),
    dict(id="fold_3bet", label="Fold 3Bet", category="Preflop", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_p_fold AND flg_p_3bet_def_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_p_3bet_def_opp THEN 1 ELSE 0 END),0)",
         lo=50, hi=60, default=True),
    dict(id="fourbet", label="4Bet", category="Preflop", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_p_4bet THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_p_4bet_opp THEN 1 ELSE 0 END),0)",
         lo=2, hi=4, default=True),
    dict(id="fold_4bet", label="Fold 4Bet", category="Preflop", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_p_fold AND flg_p_4bet_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_p_4bet_opp THEN 1 ELSE 0 END),0)",
         lo=45, hi=55, default=True),
    dict(id="cbet_flop", label="Cbet Flop", category="Flop", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_f_cbet AND flg_f_cbet_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_f_cbet_opp THEN 1 ELSE 0 END),0)",
         lo=55, hi=65, default=True),
    dict(id="fold_flop_cbet", label="Fold to Flop Cbet", category="Flop", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_f_fold AND flg_f_cbet_def_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_f_cbet_def_opp THEN 1 ELSE 0 END),0)",
         lo=45, hi=55, default=True),
    dict(id="xr_flop", label="XR Flop", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_f_check_raise THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_check AND (cnt_f_raise>0 OR cnt_f_call>0 OR flg_f_fold)
             AND ((amt_f_bet_facing>0 AND amt_f_effective_stack>amt_f_bet_facing)
                  OR flg_f_3bet_opp OR flg_f_4bet_opp)
             THEN 1 ELSE 0 END),0)""",
         lo=8, hi=12, default=True),
    dict(id="fold_xr_flop", label="Fold to Flop Check Raise", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN substring(la_f.action from 2 for 1)='F' AND flg_f_bet AND flg_f_face_raise
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_f from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_s))
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_bet AND flg_f_face_raise
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_f from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_s))
             THEN 1 ELSE 0 END),0)""",
         lo=55, hi=65, default=True),
    dict(id="float_flop", label="Float Flop", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN (la_p.action='C' OR la_p.action='CC')
             AND flg_p_face_raise AND flg_f_bet
             AND char_length(chs.str_aggressors_p)=2
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_p from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_f_has_position))
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN (la_p.action='C' OR la_p.action='CC')
             AND flg_p_face_raise AND flg_f_open_opp
             AND char_length(chs.str_aggressors_p)=2
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_p from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_f_has_position))
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=True),
    dict(id="fold_vs_float", label="Fold vs Float", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN NOT flg_p_face_raise AND la_p.action LIKE '%%R'
             AND flg_f_open_opp AND amt_f_bet_facing>0
             AND substring(la_f.action from 1 for 2) = 'XF'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN NOT flg_p_face_raise AND la_p.action LIKE '%%R'
             AND flg_f_open_opp AND flg_f_check AND amt_f_bet_facing>0
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=True),
    dict(id="cbet_turn", label="Cbet Turn", category="Turn", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_t_cbet AND flg_t_cbet_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_t_cbet_opp THEN 1 ELSE 0 END),0)",
         lo=50, hi=60, default=True),
    dict(id="fold_turn_cbet", label="Fold to Turn Cbet", category="Turn", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_t_fold AND flg_t_cbet_def_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_t_cbet_def_opp THEN 1 ELSE 0 END),0)",
         lo=45, hi=55, default=True),
    dict(id="xr_turn", label="XR Turn", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_check_raise THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_check AND (cnt_t_raise>0 OR cnt_t_call>0 OR flg_t_fold)
             AND ((amt_t_bet_facing>0 AND amt_t_effective_stack>amt_t_bet_facing)
                  OR flg_t_3bet_opp OR flg_t_4bet_opp)
             THEN 1 ELSE 0 END),0)""",
         lo=6, hi=10, default=True),
    dict(id="fold_xr_turn", label="Fold to Turn Check Raise", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN substring(la_t.action from 2 for 1)='F' AND flg_t_bet AND flg_t_face_raise
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_t from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_s))
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_bet AND flg_t_face_raise
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_t from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_s))
             THEN 1 ELSE 0 END),0)""",
         lo=55, hi=65, default=True),
    dict(id="probe_turn", label="Probe Turn", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_bet
             AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R%%'
             AND flg_p_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_open_opp
             AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R%%'
             AND flg_p_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=True),
    dict(id="fold_probe_turn", label="Fold to Probe Turn", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_t_bet_facing>0
             AND flg_f_cbet_opp AND la_f.action = 'X'
             AND NOT flg_t_open_opp AND la_t.action = 'F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN amt_t_bet_facing>0
             AND flg_f_cbet_opp AND la_f.action = 'X'
             AND NOT flg_t_open_opp
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=True),
    dict(id="cbet_river", label="Cbet River", category="River", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_r_cbet AND flg_r_cbet_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_r_cbet_opp THEN 1 ELSE 0 END),0)",
         lo=None, hi=None, default=True),
    dict(id="fold_river_cbet", label="Fold to River Cbet", category="River", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_r_fold AND flg_r_cbet_def_opp THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_r_cbet_def_opp THEN 1 ELSE 0 END),0)",
         lo=None, hi=None, default=True),
    dict(id="xr_river", label="XR River", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_r_check_raise THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_check AND (cnt_r_raise>0 OR cnt_r_call>0 OR flg_r_fold)
             AND ((amt_r_bet_facing>0 AND amt_r_effective_stack>amt_r_bet_facing)
                  OR flg_r_3bet_opp OR flg_r_4bet_opp)
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=True),
    dict(id="fold_xr_river", label="Fold to River Check Raise", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN substring(la_r.action from 2 for 1)='F' AND flg_r_bet AND flg_r_face_raise
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_r from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_s))
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_bet AND flg_r_face_raise
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_r from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_s))
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=True),
    dict(id="wtsd", label="WTSD", category="Overall", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_showdown THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_f_saw THEN 1 ELSE 0 END),0)",
         lo=26, hi=32, default=True),
    dict(id="wsd", label="W$SD", category="Overall", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_showdown AND flg_won_hand THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_showdown THEN 1 ELSE 0 END),0)",
         lo=50, hi=56, default=True),
    dict(id="wwsf", label="WWSF", category="Overall", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_f_saw AND flg_won_hand THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_f_saw THEN 1 ELSE 0 END),0)",
         lo=38, hi=46, default=True),

    # ── Overall: additional ──
    dict(id="stdev_bb100", label="StdDev BB/100", category="Overall", kind="rate",
         sql="STDDEV_POP(chps.amt_won/NULLIF(cl.amt_bb,0))*100",
         lo=None, hi=None, default=False),
    dict(id="win_pct", label="Win %", category="Overall", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_won_hand THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0)",
         lo=None, hi=None, default=False),
    dict(id="total_af", label="Total AF", category="Overall", kind="rate",
         sql="""SUM(CASE WHEN flg_f_bet THEN 1 ELSE 0 END + CASE WHEN flg_t_bet THEN 1 ELSE 0 END
             + CASE WHEN flg_r_bet THEN 1 ELSE 0 END + cnt_f_raise + cnt_t_raise + cnt_r_raise)/
             NULLIF(SUM(cnt_f_call+cnt_t_call+cnt_r_call),0)""",
         lo=None, hi=None, default=False),
    dict(id="total_afq", label="Total AFq", category="Overall", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_f_bet THEN 1 ELSE 0 END + CASE WHEN flg_t_bet THEN 1 ELSE 0 END
             + CASE WHEN flg_r_bet THEN 1 ELSE 0 END + cnt_f_raise + cnt_t_raise + cnt_r_raise)/
             NULLIF(SUM(cnt_f_call+cnt_t_call+cnt_r_call
             + CASE WHEN flg_f_fold THEN 1 ELSE 0 END + CASE WHEN flg_t_fold THEN 1 ELSE 0 END
             + CASE WHEN flg_r_fold THEN 1 ELSE 0 END
             + CASE WHEN flg_f_bet THEN 1 ELSE 0 END + CASE WHEN flg_t_bet THEN 1 ELSE 0 END
             + CASE WHEN flg_r_bet THEN 1 ELSE 0 END + cnt_f_raise + cnt_t_raise + cnt_r_raise),0)""",
         lo=None, hi=None, default=False),
    dict(id="wsd_nonsmall", label="WSD (non-small)", category="Overall", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_showdown AND flg_won_hand AND amt_bet_ttl>5*cl.amt_bb THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_showdown AND amt_bet_ttl>5*cl.amt_bb THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="wsd_after_river_call", label="WSD After River Call", category="Overall", kind="pct",
         sql="""100.0*SUM(CASE WHEN cnt_r_call>0 AND flg_won_hand AND flg_showdown THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN cnt_r_call>0 AND flg_showdown THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="wsdwrt", label="Won Showdown When Raised Turn", category="Overall", kind="pct",
         sql="""100.0*SUM(CASE WHEN cnt_t_raise>0 AND flg_showdown AND flg_won_hand THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN cnt_t_raise>0 AND flg_showdown THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="wsdwrr", label="Won Showdown When Raised River", category="Overall", kind="pct",
         sql="""100.0*SUM(CASE WHEN cnt_r_raise>0 AND flg_showdown AND flg_won_hand THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN cnt_r_raise>0 AND flg_showdown THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="pfr_vpip_ratio", label="PFR/VPIP Ratio", category="Overall", kind="rate",
         sql="""SUM(CASE WHEN cnt_p_raise>0 THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_vpip THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="float_total", label="Float Total", category="Other", kind="pct",
         sql="""100.0*SUM(CASE WHEN (la_p.action='C' OR la_p.action='CC') AND flg_p_face_raise AND flg_f_bet
             AND char_length(chs.str_aggressors_p)=2
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_p from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_f_has_position))
             THEN 1 ELSE 0 END + CASE WHEN flg_t_float THEN 1 ELSE 0 END
             + CASE WHEN flg_r_float THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN (la_p.action='C' OR la_p.action='CC') AND flg_p_face_raise AND flg_f_open_opp
             AND char_length(chs.str_aggressors_p)=2
             AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_p from 2 for 1)::int>chps.position)
                  OR (chs.cnt_players=2 AND flg_f_has_position))
             THEN 1 ELSE 0 END + CASE WHEN flg_t_float_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_r_float_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),

    # ── Preflop: additional ──
    dict(id="steal_success", label="Steal Success", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_steal_att AND NOT flg_f_saw AND NOT flg_p_face_raise THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_steal_att THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_first_in", label="Raise First In", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_first_raise AND flg_p_open_opp THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_open_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="preflop_squeeze", label="Squeeze Preflop", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_squeeze THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_squeeze_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_pf_squeeze", label="Raise vs Squeeze", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_squeeze_def_opp AND enum_p_squeeze_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_squeeze_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="preflop_limp", label="Limp Preflop", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_limp THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN ((NOT flg_p_face_raise) OR flg_p_limp OR flg_p_first_raise)
             AND NOT (flg_blind_b OR flg_blind_db) THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="preflop_limp_raise", label="Limp Raise Preflop", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_limp AND la_p.action LIKE 'CR%%' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_limp AND flg_p_face_raise
             AND (flg_p_3bet_opp OR flg_p_4bet_opp) THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="preflop_limp_fold", label="Limp Fold Preflop", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_limp AND la_p.action='CF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_limp AND flg_p_face_raise THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="preflop_limp_call", label="Limp Call Preflop", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_limp AND la_p.action LIKE 'CC%%' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_limp AND flg_p_face_raise THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="limp_with_previous_limpers", label="Limp With Previous Limpers", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN NOT flg_p_open AND flg_p_limp THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN cnt_p_face_limpers>0 AND NOT (flg_blind_b OR flg_blind_db)
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_steal", label="Fold to Steal", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_blind_def_opp AND la_p.action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_blind_def_opp THEN 1 ELSE 0 END),0)""",
         lo=55, hi=65, default=False),
    dict(id="fold_to_lp_steal", label="Fold to LP Steal", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_blind_def_opp AND la_p.action='F'
             AND chs.str_aggressors_p NOT LIKE '89%%' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_blind_def_opp AND chs.str_aggressors_p NOT LIKE '89%%'
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_vs_btn_open", label="Fold vs BTN Open", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN la_p.action='F' AND chs.str_aggressors_p LIKE '80%%'
             AND chs.str_actors_p LIKE '0%%' AND amt_p_2bet_facing>0 THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN chs.str_aggressors_p LIKE '80%%' AND chs.str_actors_p LIKE '0%%'
             AND amt_p_2bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_vs_co_open", label="Fold vs CO Open", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN la_p.action='F' AND chs.str_aggressors_p LIKE '81%%'
             AND chs.str_actors_p LIKE '1%%' AND amt_p_2bet_facing>0 THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN chs.str_aggressors_p LIKE '81%%' AND chs.str_actors_p LIKE '1%%'
             AND amt_p_2bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_3bet", label="Fold to PF 3Bet", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_p_3bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_3bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_3bet_after_raise", label="Fold to PF 3Bet After Raise", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_p_3bet_action='F' AND flg_p_first_raise THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_3bet_def_opp AND flg_p_first_raise THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_3bet_after_raise_ip", label="Fold to PF 3Bet After Raise (IP)", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN char_length(chs.str_aggressors_p)>=3 AND enum_p_3bet_action='F'
             AND flg_p_first_raise AND substring(chs.str_aggressors_p from 3 for 1)::int>chps.position
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN char_length(chs.str_aggressors_p)>=3 AND flg_p_3bet_def_opp
             AND flg_p_first_raise AND substring(chs.str_aggressors_p from 3 for 1)::int>chps.position
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_3bet_after_raise_oop", label="Fold to PF 3Bet After Raise (OOP)", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN char_length(chs.str_aggressors_p)>=3 AND enum_p_3bet_action='F'
             AND flg_p_first_raise AND substring(chs.str_aggressors_p from 3 for 1)::int<chps.position
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN char_length(chs.str_aggressors_p)>=3 AND flg_p_3bet_def_opp
             AND flg_p_first_raise AND substring(chs.str_aggressors_p from 3 for 1)::int<chps.position
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_3bet_after_steal", label="Fold to PF 3Bet After Steal", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_steal_att AND flg_p_3bet_def_opp AND enum_p_3bet_action='F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_steal_att AND flg_p_3bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_4bet", label="Fold to PF 4Bet", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_p_4bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_4bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_4bet_after_3bet", label="Fold to PF 4Bet After 3Bet", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_3bet AND enum_p_4bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_3bet AND flg_p_4bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_pf_squeeze", label="Fold to PF Squeeze", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_p_squeeze_def_opp AND enum_p_squeeze_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_squeeze_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_any_pf_raise", label="Fold to Any PF Raise", category="Preflop", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_p_2bet_facing>0
             AND ((flg_p_limp AND la_p.action='CF') OR (NOT flg_p_limp AND la_p.action SIMILAR TO '(XF|F)'))
             THEN 1 ELSE 0 END + CASE WHEN enum_p_3bet_action='F' THEN 1 ELSE 0 END
             + CASE WHEN enum_p_4bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN amt_p_2bet_facing>0 THEN 1 ELSE 0 END
             + CASE WHEN flg_p_3bet_def_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_p_4bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),

    # ── Flop: additional ──
    dict(id="flop_af", label="Flop AF", category="Flop", kind="rate",
         sql="""SUM(CASE WHEN flg_f_bet THEN 1 ELSE 0 END+cnt_f_raise)/NULLIF(SUM(cnt_f_call),0)""",
         lo=None, hi=None, default=False),
    dict(id="flop_afq", label="Flop AFq", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_f_bet THEN 1 ELSE 0 END+cnt_f_raise)/
             NULLIF(SUM(cnt_f_call+CASE WHEN flg_f_fold THEN 1 ELSE 0 END
             +CASE WHEN flg_f_bet THEN 1 ELSE 0 END+cnt_f_raise),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_f_bet", label="Fold to Flop Bet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_f_bet_facing>0 AND la_f.action SIMILAR TO '(F|XF)%%'
             THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN amt_f_bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_f_cbet_named", label="Fold to F CBet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_f_cbet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_cbet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=45, hi=55, default=False),
    dict(id="fold_to_f_cbet_3bet", label="Fold to F CBet (3Bet+ Pot)", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN (flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND enum_f_cbet_action='F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN (flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND flg_f_cbet_def_opp
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_f_cbet_non3bet", label="Fold to F CBet (non-3Bet Pot)", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN NOT(flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND enum_f_cbet_action='F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN NOT(flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND flg_f_cbet_def_opp
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_f_2bet", label="Fold to Flop 2Bet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_f_2bet_facing>0
             AND ((amt_f_bet_facing=0 AND la_f.action SIMILAR TO '(F|XF|BF)%%')
                  OR (amt_f_bet_facing>0 AND la_f.action SIMILAR TO '(XCF|CF)'))
             THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN amt_f_2bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_f_3bet", label="Fold to Flop 3Bet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_f_3bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_3bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_f_4bet", label="Fold to Flop 4Bet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_f_4bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_4bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_f_donk_bet", label="Fold to Flop Donk Bet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_f_donk_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_donk_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_f_cbet", label="Raise F CBet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_f_cbet_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_cbet_def_opp AND amt_f_effective_stack>amt_f_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_f_donk_bet", label="Raise F Donk Bet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_f_donk_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_donk_def_opp AND amt_f_effective_stack>amt_f_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_f_cbet", label="Fold to Raise After F CBet", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_f_cbet AND la_f.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_cbet AND flg_f_face_raise THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_f_donk", label="Fold to Raise After F Donk", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_f_donk AND la_f.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_f_donk AND la_f.action LIKE 'B_%%' THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="delayed_cbet_turn", label="Delayed Cbet Turn", category="Flop", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_bet AND flg_f_cbet_opp AND la_f.action LIKE 'X' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_open_opp AND flg_f_cbet_opp AND la_f.action LIKE 'X'
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),

    # ── Turn: additional ──
    dict(id="turn_af", label="Turn AF", category="Turn", kind="rate",
         sql="""SUM(CASE WHEN flg_t_bet THEN 1 ELSE 0 END+cnt_t_raise)/NULLIF(SUM(cnt_t_call),0)""",
         lo=None, hi=None, default=False),
    dict(id="turn_afq", label="Turn AFq", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_bet THEN 1 ELSE 0 END+cnt_t_raise)/
             NULLIF(SUM(cnt_t_call+CASE WHEN flg_t_fold THEN 1 ELSE 0 END
             +CASE WHEN flg_t_bet THEN 1 ELSE 0 END+cnt_t_raise),0)""",
         lo=None, hi=None, default=False),
    dict(id="turn_saw_pct", label="Turn Saw %", category="Turn", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_t_saw THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_f_saw THEN 1 ELSE 0 END),0)",
         lo=None, hi=None, default=False),
    dict(id="float_turn", label="Float Turn", category="Turn", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_t_float THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_t_float_opp THEN 1 ELSE 0 END),0)",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_bet", label="Fold to Turn Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_t_bet_facing>0 AND la_t.action SIMILAR TO '(F|XF)%%'
             THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN amt_t_bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_cbet_named", label="Fold to T CBet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_cbet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_cbet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=45, hi=55, default=False),
    dict(id="fold_to_t_cbet_3bet", label="Fold to T CBet (3Bet+ Pot)", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN (flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND enum_t_cbet_action='F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN (flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND flg_t_cbet_def_opp
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_cbet_non3bet", label="Fold to T CBet (non-3Bet Pot)", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN NOT(flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND enum_t_cbet_action='F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN NOT(flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND flg_t_cbet_def_opp
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_2bet", label="Fold to Turn 2Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_t_2bet_facing>0
             AND ((amt_t_bet_facing=0 AND la_t.action SIMILAR TO '(F|XF|BF)%%')
                  OR (amt_t_bet_facing>0 AND la_t.action SIMILAR TO '(XCF|CF)'))
             THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN amt_t_2bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_3bet", label="Fold to Turn 3Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_3bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_3bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_4bet", label="Fold to Turn 4Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_4bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_4bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_donk_bet", label="Fold to Turn Donk Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_donk_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_donk_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_t_float_bet", label="Fold to Turn Float Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_float_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_float_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_t_cbet", label="Raise T CBet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_cbet_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_cbet_def_opp AND amt_t_effective_stack>amt_t_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_t_donk_bet", label="Raise T Donk Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_donk_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_donk_def_opp AND amt_t_effective_stack>amt_t_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_t_float_bet", label="Raise T Float Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_t_float_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_float_def_opp AND amt_t_effective_stack>amt_t_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_t_probe_bet", label="Raise T Probe Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_t_bet_facing>0 AND flg_f_cbet_opp AND la_f.action='X'
             AND NOT flg_t_open_opp AND la_t.action LIKE 'R%%' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN amt_t_bet_facing>0 AND flg_f_cbet_opp AND la_f.action='X'
             AND NOT flg_t_open_opp AND amt_t_effective_stack>amt_t_bet_facing THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_t_cbet", label="Fold to Raise After T CBet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_cbet AND la_t.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_cbet AND flg_t_face_raise THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_t_donk", label="Fold to Raise After T Donk", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_donk AND la_t.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_donk AND la_t.action LIKE 'B_%%' THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_t_float_bet", label="Fold to Raise After T Float Bet", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_float AND la_t.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_float AND la_t.action LIKE 'B_%%' THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_t_probe", label="Fold to Raise After T Probe", category="Turn", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_bet AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             AND la_t.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_bet AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             AND la_t.action LIKE 'B_%%' THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),

    # ── River: additional ──
    dict(id="river_af", label="River AF", category="River", kind="rate",
         sql="""SUM(CASE WHEN flg_r_bet THEN 1 ELSE 0 END+cnt_r_raise)/NULLIF(SUM(cnt_r_call),0)""",
         lo=None, hi=None, default=False),
    dict(id="river_afq", label="River AFq", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_r_bet THEN 1 ELSE 0 END+cnt_r_raise)/
             NULLIF(SUM(cnt_r_call+CASE WHEN flg_r_fold THEN 1 ELSE 0 END
             +CASE WHEN flg_r_bet THEN 1 ELSE 0 END+cnt_r_raise),0)""",
         lo=None, hi=None, default=False),
    dict(id="river_saw_pct", label="River Saw %", category="River", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_r_saw THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_t_saw THEN 1 ELSE 0 END),0)",
         lo=None, hi=None, default=False),
    dict(id="float_river", label="Float River", category="River", kind="pct",
         sql="100.0*SUM(CASE WHEN flg_r_float THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN flg_r_float_opp THEN 1 ELSE 0 END),0)",
         lo=None, hi=None, default=False),
    dict(id="probe_river", label="Probe River", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_r_bet AND la_t.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise AND enum_f_cbet_action='C'
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_open_opp AND la_t.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise AND enum_f_cbet_action='C'
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_probe_river", label="Fold to Probe River", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_r_bet_facing>0 AND flg_t_cbet_opp AND la_t.action='X'
             AND NOT flg_r_open_opp AND la_r.action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN amt_r_bet_facing>0 AND flg_t_cbet_opp AND la_t.action='X'
             AND NOT flg_r_open_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_bet", label="Fold to River Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_r_bet_facing>0 AND la_r.action SIMILAR TO '(F|XF)%%'
             THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN amt_r_bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_cbet_named", label="Fold to R CBet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_cbet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_cbet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_cbet_3bet", label="Fold to R CBet (3Bet+ Pot)", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN (flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND enum_r_cbet_action='F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN (flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND flg_r_cbet_def_opp
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_cbet_non3bet", label="Fold to R CBet (non-3Bet Pot)", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN NOT(flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND enum_r_cbet_action='F'
             THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN NOT(flg_p_3bet_def_opp OR flg_p_4bet_def_opp) AND flg_r_cbet_def_opp
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_2bet", label="Fold to River 2Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_r_2bet_facing>0
             AND ((amt_r_bet_facing=0 AND la_r.action SIMILAR TO '(F|XF|BF)%%')
                  OR (amt_r_bet_facing>0 AND la_r.action SIMILAR TO '(XCF|CF)'))
             THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN amt_r_2bet_facing>0 THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_3bet", label="Fold to River 3Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_3bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_3bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_4bet", label="Fold to River 4Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_4bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_4bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_donk_bet", label="Fold to River Donk Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_donk_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_donk_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_r_float_bet", label="Fold to River Float Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_float_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_float_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_r_cbet", label="Raise R CBet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_cbet_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_cbet_def_opp AND amt_r_effective_stack>amt_r_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_r_donk_bet", label="Raise R Donk Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_donk_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_donk_def_opp AND amt_r_effective_stack>amt_r_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_r_float_bet", label="Raise R Float Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_r_float_action='R' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_float_def_opp AND amt_r_effective_stack>amt_r_bet_facing
             THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="raise_r_probe_bet", label="Raise R Probe Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN amt_r_bet_facing>0 AND flg_t_cbet_opp AND la_t.action='X'
             AND NOT flg_r_open_opp AND la_r.action LIKE 'R%%' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN amt_r_bet_facing>0 AND flg_t_cbet_opp AND la_t.action='X'
             AND NOT flg_r_open_opp AND amt_r_effective_stack>amt_r_bet_facing THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_r_cbet", label="Fold to Raise After R CBet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_r_cbet AND la_r.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_cbet AND flg_r_face_raise THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_r_donk", label="Fold to Raise After R Donk", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_r_donk AND la_r.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_donk AND la_r.action LIKE 'B_%%' THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_r_float_bet", label="Fold to Raise After R Float Bet", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_r_float AND la_r.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_float AND la_r.action LIKE 'B_%%' THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_raise_after_r_probe", label="Fold to Raise After R Probe", category="River", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_r_bet AND la_t.action LIKE 'X' AND enum_f_cbet_action='C'
             AND NOT flg_f_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             AND la_r.action='BF' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_r_bet AND la_t.action LIKE 'X' AND enum_f_cbet_action='C'
             AND NOT flg_f_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b))
             AND la_r.action LIKE 'B_%%' THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),

    # ── Other: comprehensive/aggregate ──
    dict(id="probe_total", label="Probe Total", category="Other", kind="pct",
         sql="""100.0*SUM(CASE WHEN flg_t_bet AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b)) THEN 1 ELSE 0 END
             + CASE WHEN flg_r_bet AND la_t.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise AND enum_f_cbet_action='C'
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b)) THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_t_open_opp AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b)) THEN 1 ELSE 0 END
             + CASE WHEN flg_r_open_opp AND la_t.action LIKE 'X' AND la_p.action NOT LIKE '%%R'
             AND flg_p_face_raise AND enum_f_cbet_action='C'
             AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
                  OR (chs.cnt_players=2 AND flg_blind_b)) THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_3bet_total", label="Fold to 3Bet (All Streets)", category="Other", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_p_3bet_action='F' THEN 1 ELSE 0 END
             + CASE WHEN enum_f_3bet_action='F' THEN 1 ELSE 0 END
             + CASE WHEN enum_t_3bet_action='F' THEN 1 ELSE 0 END
             + CASE WHEN enum_r_3bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_3bet_def_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_f_3bet_def_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_t_3bet_def_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_r_3bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
    dict(id="fold_to_4bet_total", label="Fold to 4Bet (All Streets)", category="Other", kind="pct",
         sql="""100.0*SUM(CASE WHEN enum_p_4bet_action='F' THEN 1 ELSE 0 END
             + CASE WHEN enum_f_4bet_action='F' THEN 1 ELSE 0 END
             + CASE WHEN enum_t_4bet_action='F' THEN 1 ELSE 0 END
             + CASE WHEN enum_r_4bet_action='F' THEN 1 ELSE 0 END)/
             NULLIF(SUM(CASE WHEN flg_p_4bet_def_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_f_4bet_def_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_t_4bet_def_opp THEN 1 ELSE 0 END
             + CASE WHEN flg_r_4bet_def_opp THEN 1 ELSE 0 END),0)""",
         lo=None, hi=None, default=False),
]
STAT_REGISTRY_BY_ID = {s['id']: s for s in STAT_REGISTRY}
STAT_CATEGORIES = ["Overall", "Preflop", "Flop", "Turn", "River", "Other"]

# ─── SETTINGS PERSISTENCE ──────────────────────────────────────────────────────
def _settings_path():
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "poker_dashboard_settings.json")

def load_settings():
    path = _settings_path()
    defaults = {"visible_stats": [s['id'] for s in STAT_REGISTRY if s['default']]}
    if not os.path.exists(path):
        return defaults
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if "visible_stats" not in data or not isinstance(data["visible_stats"], list):
            return defaults
        # Drop any stale ids no longer in the registry, keep everything else
        data["visible_stats"] = [i for i in data["visible_stats"] if i in STAT_REGISTRY_BY_ID]
        return data
    except Exception:
        return defaults

def save_settings(settings):
    path = _settings_path()
    try:
        with open(path, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass  # best-effort; app continues to work with in-memory selection either way


# ─── HAND LIST (stat drill-down) ──────────────────────────────────────────────

# Maps each clickable stat name to the exact numerator condition used for
# that stat's percentage in the villain profile query (same SQL fragments,
# each already confirmed against PT4's own formulas where applicable).
STAT_HAND_CONDITIONS = {
    "VPIP": "flg_vpip",
    "PFR": "flg_p_first_raise",
    "3Bet": "flg_p_3bet",
    "Fold 3Bet": "flg_p_fold AND flg_p_3bet_def_opp",
    "4Bet": "flg_p_4bet",
    "Fold 4Bet": "flg_p_fold AND flg_p_4bet_opp",
    "WTSD": "flg_showdown",
    "W$SD": "flg_showdown AND flg_won_hand",
    "WWSF": "flg_f_saw AND flg_won_hand",
    "Cbet Flop": "flg_f_cbet AND flg_f_cbet_opp",
    "Fold to Flop Cbet": "flg_f_fold AND flg_f_cbet_def_opp",
    "XR Flop": "flg_f_check_raise",
    "Fold to XR": "flg_f_fold AND flg_f_cbet AND flg_f_face_raise",
    "Float Flop": """(la_p.action='C' OR la_p.action='CC')
        AND flg_p_face_raise AND flg_f_bet
        AND char_length(chs.str_aggressors_p)=2
        AND ((chs.cnt_players>2 AND substring(chs.str_aggressors_p from 2 for 1)::int>chps.position)
             OR (chs.cnt_players=2 AND flg_f_has_position))""",
    "Fold vs Float": """NOT flg_p_face_raise AND la_p.action LIKE '%%R'
        AND flg_f_open_opp AND amt_f_bet_facing>0
        AND substring(la_f.action from 1 for 2) = 'XF'""",
    "Cbet Turn": "flg_t_cbet AND flg_t_cbet_opp",
    "Fold to Turn Cbet": "flg_t_fold AND flg_t_cbet_def_opp",
    "XR Turn": "flg_t_check_raise",
    "Fold to Turn XR": "flg_t_fold AND flg_t_cbet AND flg_t_face_raise",
    "Probe Turn": """flg_t_bet
        AND la_f.action LIKE 'X' AND la_p.action NOT LIKE '%%R%%'
        AND flg_p_face_raise
        AND ((chs.cnt_players>=3 AND chps.val_p_raise_aggressor_pos<chps.position)
             OR (chs.cnt_players=2 AND flg_blind_b))""",
    "Fold to Probe Turn": """amt_t_bet_facing>0
        AND flg_f_cbet_opp AND la_f.action = 'X'
        AND NOT flg_t_open_opp AND la_t.action = 'F'""",
    "Cbet River": "flg_r_cbet AND flg_r_cbet_opp",
    "Fold to River Cbet": "flg_r_fold AND flg_r_cbet_def_opp",
    "XR River": "flg_r_check_raise",
    "Fold to River XR": "flg_r_fold AND flg_r_cbet AND flg_r_face_raise",
}

class HandListLoader(QThread):
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, villain, condition_sql, d_from, d_to):
        super().__init__()
        self.villain=villain; self.condition_sql=condition_sql
        self.d_from=d_from; self.d_to=d_to

    def run(self):
        try:
            conn=psycopg2.connect(**DB); cur=conn.cursor()
            cur.execute(f"""
                SELECT chs.id_hand, chs.date_played, cl.limit_name,
                    chs.card_1, chs.card_2, chs.card_3, chs.card_4, chs.card_5,
                    chps.amt_won*chps.val_curr_conv
                FROM cash_hand_player_statistics chps
                LEFT JOIN lookup_actions la_f ON chps.id_action_f=la_f.id_action
                LEFT JOIN lookup_actions la_p ON chps.id_action_p=la_p.id_action
                LEFT JOIN lookup_actions la_t ON chps.id_action_t=la_t.id_action
                LEFT JOIN lookup_actions la_r ON chps.id_action_r=la_r.id_action
                JOIN cash_hand_summary chs ON chps.id_hand=chs.id_hand
                JOIN player p ON chps.id_player=p.id_player
                JOIN cash_limit cl ON chs.id_limit=cl.id_limit
                WHERE p.player_name=%s
                AND chs.date_played::date BETWEEN %s AND %s
                AND ({self.condition_sql})
                ORDER BY chs.date_played DESC
                LIMIT 300
            """, (self.villain, self.d_from, self.d_to))
            rows=cur.fetchall()
            cur.close(); conn.close()
            self.done.emit(rows)
        except Exception as e:
            self.error.emit(str(e))


class ClickableFrame(QFrame):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class HandListDialog(QDialog):
    def __init__(self, stat_name, villain, condition_sql, d_from, d_to, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{stat_name} — hands for {villain}")
        self.resize(560,480)
        lay=QVBoxLayout(self)
        self.status=lbl(f"Loading hands...",dim=True)
        lay.addWidget(self.status)

        self.table=QTableWidget()
        cols=["Date","Stakes","Board","Villain Profit"]
        self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._open_replay)
        lay.addWidget(self.table)
        lay.addWidget(lbl("Double-click a hand to watch the replay",size=10,dim=True))

        self.loader=HandListLoader(villain, condition_sql, d_from, d_to)
        self.loader.done.connect(self._on_loaded)
        self.loader.error.connect(lambda e: self.status.setText(f"Error: {e}"))
        self.loader.start()

    def _on_loaded(self, rows):
        self.status.setText(f"{len(rows)} hand(s) found (most recent 300 shown max)")
        self.table.setRowCount(0)
        self._row_hand_ids=[]
        for r in rows:
            id_hand, dt, stakes, c1,c2,c3,c4,c5, profit = r
            board=decode_board(c1,c2,c3,c4,c5)
            row=self.table.rowCount(); self.table.insertRow(row)
            self._row_hand_ids.append(id_hand)
            vals=[dt.strftime("%Y-%m-%d %H:%M"), stakes, None,
                  f"${float(profit or 0):+,.2f}"]
            for c,val in enumerate(vals):
                if c==2:
                    board_lbl=QLabel(board_html(board))
                    board_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    board_lbl.setStyleSheet("background:transparent;border:none;font-size:13px;")
                    self.table.setCellWidget(row,c,board_lbl)
                    continue
                item=QTableWidgetItem(val); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c==3: item.setForeground(QColor(GREEN if float(profit or 0)>=0 else RED))
                self.table.setItem(row,c,item)
            self.table.setRowHeight(row,30)

    def _open_replay(self, row, col):
        if row<0 or row>=len(getattr(self,'_row_hand_ids',[])): return
        id_hand=self._row_hand_ids[row]
        dlg=HandReplayerDialog(id_hand, parent=self)
        dlg.exec()


# ─── HAND REPLAYER ─────────────────────────────────────────────────────────────

class HandHistoryLoader(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, id_hand):
        super().__init__()
        self.id_hand=id_hand

    def run(self):
        try:
            conn=psycopg2.connect(**DB); cur=conn.cursor()
            cur.execute("SELECT history FROM cash_hand_histories WHERE id_hand=%s", (self.id_hand,))
            row=cur.fetchone()
            cur.close(); conn.close()
            if row:
                self.done.emit(row[0])
            else:
                self.error.emit("No raw history found for this hand")
        except Exception as e:
            self.error.emit(str(e))


def compute_positions(seats, button_seat):
    """Assign standard position names (BTN, SB, BB, UTG, MP, CO) based on seat
    order relative to the button — not from 'Post SB/BB' text, since dead/missed
    blind posts (a player posting a blind out of their normal position) would
    otherwise mislabel that seat's actual position for the hand."""
    ordered=sorted(seats, key=lambda s: s['seat'])
    n=len(ordered)
    if n==0: return {}
    btn_idx=next((i for i,s in enumerate(ordered) if s['seat']==button_seat), 0)
    rotated=ordered[btn_idx:]+ordered[:btn_idx]
    templates={
        2:['BTN/SB','BB'], 3:['BTN','SB','BB'], 4:['BTN','SB','BB','CO'],
        5:['BTN','SB','BB','UTG','CO'], 6:['BTN','SB','BB','UTG','MP','CO'],
    }
    template=templates.get(n, ['BTN','SB','BB']+[f'MP{i+1}' for i in range(max(n-4,0))]+(['CO'] if n>3 else []))
    return {s['name']: (template[i] if i<len(template) else f"P{i+1}") for i,s in enumerate(rotated)}

_POS_COLOR={'BTN':'#e3b341','BTN/SB':'#e3b341','SB':'#388bfd','BB':'#f85149'}

class SeatWidget(QFrame):
    def __init__(self, name, stack, position=None):
        super().__init__()
        self.setObjectName("seat")
        self._base_style=f"background:{BG3};border:2px solid {BORDER};border-radius:8px;"
        self.setStyleSheet(self._base_style)
        lay=QVBoxLayout(self); lay.setContentsMargins(8,6,8,6); lay.setSpacing(1)
        top_row=QHBoxLayout(); top_row.setSpacing(4)
        self.name_lbl=lbl(name,size=11,bold=True)
        top_row.addWidget(self.name_lbl)
        if position:
            pos_color=_POS_COLOR.get(position,'#8b949e')
            pos_lbl=lbl(position,size=9,bold=True)
            pos_lbl.setStyleSheet(f"color:{pos_color};font-size:9px;font-weight:700;"
                                   f"background:transparent;border:1px solid {pos_color};"
                                   f"border-radius:4px;padding:0px 4px;")
            top_row.addWidget(pos_lbl)
        top_row.addStretch()
        lay.addLayout(top_row)
        self.stack_lbl=lbl(f"£{stack:.2f}",size=10,dim=True)
        self.status_lbl=lbl("",size=10)
        self.status_lbl.setStyleSheet(f"background:transparent;border:none;color:{DIM};")
        lay.addWidget(self.stack_lbl); lay.addWidget(self.status_lbl)
        self.setFixedSize(140,66)
        self._opacity=QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(1.0)

    def set_active(self, active):
        if active:
            self.setStyleSheet(f"background:{BG3};border:2px solid {ACCENT2};border-radius:8px;")
        else:
            self.setStyleSheet(self._base_style)

    def set_folded(self, folded):
        self._opacity.setOpacity(0.35 if folded else 1.0)

    def set_status(self, text, color=None):
        self.status_lbl.setText(text)
        c=color or DIM
        self.status_lbl.setStyleSheet(f"background:transparent;border:none;color:{c};")

    def set_winner(self, amount):
        self.setStyleSheet(f"background:{BG3};border:2px solid {GREEN};border-radius:8px;")
        self.set_status(f"WINS £{amount:.2f}", GREEN)


class TableOvalWidget(QWidget):
    def __init__(self, seats, positions=None):
        super().__init__()
        self.setMinimumSize(560,340)
        self.seat_widgets={}
        self._seat_order=[s['name'] for s in seats]
        positions=positions or {}
        for s in seats:
            sw=SeatWidget(s['name'], s['stack'], positions.get(s['name']))
            sw.setParent(self)
            self.seat_widgets[s['name']]=sw
        self._reposition()

    def resizeEvent(self, event):
        self._reposition()
        super().resizeEvent(event)

    def _reposition(self):
        import math
        w=max(self.width(),560); h=max(self.height(),340)
        cx,cy=w/2,h/2
        rx,ry=w/2-80,h/2-55
        n=max(len(self._seat_order),1)
        for i,name in enumerate(self._seat_order):
            angle=math.pi/2+2*math.pi*i/n
            x=cx+rx*math.cos(angle)-65
            y=cy+ry*math.sin(angle)-33
            self.seat_widgets[name].move(int(x),int(y))

    def paintEvent(self, event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w=self.width(); h=self.height()
        margin=95
        painter.setBrush(QBrush(QColor("#1a4d2e")))
        painter.setPen(QPen(QColor(BORDER),3))
        painter.drawEllipse(margin,margin,max(w-2*margin,10),max(h-2*margin,10))


class HandReplayerDialog(QDialog):
    def __init__(self, id_hand, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Hand Replay — #{id_hand}")
        self.resize(720,660)
        self.id_hand=id_hand
        self.events=[]; self.idx=-1; self.playing=False
        self.table_widget=None

        self.timer=QTimer(self)
        self.timer.timeout.connect(self._step_forward)

        lay=QVBoxLayout(self)
        self.status=lbl("Loading hand...",dim=True)
        lay.addWidget(self.status)

        self.table_container=QWidget()
        self.table_container_lay=QVBoxLayout(self.table_container)
        self.table_container_lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.table_container,1)

        self.pot_lbl=lbl("",size=13,bold=True)
        self.pot_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.pot_lbl)

        self.board_lbl=QLabel("")
        self.board_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.board_lbl.setStyleSheet("font-size:20px;background:transparent;border:none;")
        lay.addWidget(self.board_lbl)

        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(110)
        lay.addWidget(self.log)

        ctrl=QHBoxLayout()
        self.btn_prev=QPushButton("⏮ Prev")
        self.btn_playpause=QPushButton("⏸ Pause")
        self.btn_next=QPushButton("Next ⏭")
        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_playpause.clicked.connect(self._toggle_play)
        self.btn_next.clicked.connect(self._on_next)
        ctrl.addWidget(self.btn_prev); ctrl.addWidget(self.btn_playpause); ctrl.addWidget(self.btn_next)
        lay.addLayout(ctrl)

        self.loader=HandHistoryLoader(id_hand)
        self.loader.done.connect(self._on_history_loaded)
        self.loader.error.connect(lambda e: self.status.setText(f"Error: {e}"))
        self.loader.start()

    def _on_history_loaded(self, text):
        self.status.hide()
        parsed=parse_hand_history(text)
        if parsed['unmatched']:
            # Don't silently guess — surface it so a genuinely new format gets noticed, not misplayed.
            self.status.show()
            self.status.setText(f"Warning: {len(parsed['unmatched'])} line(s) in this hand's "
                                 f"history weren't recognized — replay may be incomplete.")
        self.parsed=parsed
        self.events=build_replay_events(parsed)
        positions=compute_positions(parsed['seats'], parsed['button_seat'])
        self.table_widget=TableOvalWidget(parsed['seats'], positions)
        self.table_container_lay.addWidget(self.table_widget)
        self.idx=-1
        self._render_state()
        if self.events:
            self.playing=True
            self.timer.start(1400)

    def _toggle_play(self):
        self.playing=not self.playing
        if self.playing:
            self.timer.start(1400)
            self.btn_playpause.setText("⏸ Pause")
        else:
            self.timer.stop()
            self.btn_playpause.setText("▶ Play")

    def _on_prev(self):
        self.playing=False; self.timer.stop(); self.btn_playpause.setText("▶ Play")
        if self.idx>-1:
            self.idx-=1
            self._render_state()

    def _on_next(self):
        self.playing=False; self.timer.stop(); self.btn_playpause.setText("▶ Play")
        self._step_forward()

    def _step_forward(self):
        if self.idx+1<len(self.events):
            self.idx+=1
            self._render_state()
        else:
            self.timer.stop(); self.playing=False
            self.btn_playpause.setText("▶ Play")

    def _render_state(self):
        if not self.table_widget: return
        board=[]; pot=0.0; folded=set(); log_lines=[]
        current=self.events[self.idx] if self.idx>=0 else None
        for e in self.events[:self.idx+1]:
            log_lines.append(e['text'])
            if e['kind']=='post':
                pot+=e['amount']
            elif e['kind']=='action':
                if e['action']=='Fold': folded.add(e['name'])
                elif e['amount'] is not None: pot+=e['amount']
            elif e['kind']=='uncalled':
                pot-=e['amount']
            elif e['kind']=='street':
                board=e['cards']

        for name,sw in self.table_widget.seat_widgets.items():
            is_current=bool(current and current.get('name')==name and current['kind'] in ('action','post'))
            sw.set_active(is_current)
            sw.set_folded(name in folded)
            if name not in folded and (not current or current.get('name')!=name):
                pass  # leave last-set status as-is between that seat's own events

        if current and current['kind'] in ('action','post','uncalled'):
            sw=self.table_widget.seat_widgets.get(current['name'])
            if sw:
                label=current['text'].split(': ',1)[-1] if ': ' in current['text'] else current['text']
                sw.set_status(label, RED if current.get('action')=='Fold' else TEXT)
        if current and current['kind']=='win':
            sw=self.table_widget.seat_widgets.get(current['name'])
            if sw: sw.set_winner(current['amount'])
        if current and current['kind']=='show':
            sw=self.table_widget.seat_widgets.get(current['name'])
            if sw: sw.set_status(' '.join(current['cards'])+" — "+current['desc'], "#d8dee9")

        self.pot_lbl.setText(f"Pot: £{pot:.2f}")
        self.board_lbl.setText(board_html(board) if board else "")
        self.log.setPlainText('\n'.join(log_lines))
        sb=self.log.verticalScrollBar(); sb.setValue(sb.maximum())


# ─── VILLAIN PROFILE ──────────────────────────────────────────────────────────

class VillainProfile(QWidget):
    def __init__(self, hero, get_dates_fn):
        super().__init__()
        self.hero=hero; self.get_dates=get_dates_fn; self.loader=None; self._pop_tab=None
        lay=QVBoxLayout(self); lay.setContentsMargins(16,16,16,16); lay.setSpacing(12)

        # Placeholder
        self.placeholder=lbl("← Select a villain to view their profile",size=14,dim=True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.placeholder,alignment=Qt.AlignmentFlag.AlignCenter)

        # Content (hidden until villain selected)
        self.content=QWidget(); self.content.hide()
        clay=QVBoxLayout(self.content); clay.setContentsMargins(0,0,0,0); clay.setSpacing(12)

        # Header row
        self.name_lbl=lbl("",size=18,bold=True)
        self.type_lbl=lbl("",size=13)
        self.hands_lbl=lbl("",dim=True)
        self._name_blurred=False
        self.eye_btn=QPushButton("Hide")
        self.eye_btn.setFixedSize(48,24)
        self.eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eye_btn.setToolTip("Blur villain name")
        self.eye_btn.setStyleSheet(
            f"QPushButton{{background:{BG3};border:1px solid {BORDER};border-radius:5px;"
            f"font-size:10px;color:{DIM};padding:0px;}}"
            f"QPushButton:hover{{background:#30363d;color:{TEXT};}}")
        self.eye_btn.clicked.connect(self._toggle_name_blur)
        hdr=QHBoxLayout()
        hdr.addWidget(self.name_lbl); hdr.addWidget(self.eye_btn); hdr.addWidget(self.type_lbl)
        hdr.addStretch(); hdr.addWidget(self.hands_lbl)
        clay.addLayout(hdr)

        # Graph
        gcard=QFrame(); gcard.setObjectName("card")
        gl=QVBoxLayout(gcard); gl.setContentsMargins(12,12,12,12)
        gl.addWidget(lbl("VILLAIN RESULTS  (Purple = Your profit vs them)",size=11,dim=True))
        self.plot=pg.PlotWidget(); self.plot.setMinimumHeight(160)
        self.plot.showGrid(x=False,y=True,alpha=0.15)
        pi=self.plot.getPlotItem()
        pi.hideAxis('bottom'); self.plot.setBackground(BG2)
        pi.vb.setMouseEnabled(x=False, y=False)  # lock: no scroll/drag zoom or pan
        pi.setMenuEnabled(False)
        zero_line=pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color="#8b949e", width=1.2))
        pi.addItem(zero_line)
        self.c_total=self.plot.plot(pen=pg.mkPen(color=GREEN,  width=2.5), name="Villain Total")
        self.c_sd   =self.plot.plot(pen=pg.mkPen(color=ACCENT2, width=1.5, style=Qt.PenStyle.DashLine), name="Showdown")
        self.c_nsd  =self.plot.plot(pen=pg.mkPen(color=RED,     width=1.5, style=Qt.PenStyle.DashLine), name="Non-Showdown")
        self.c_ev   =self.plot.plot(pen=pg.mkPen(color=YELLOW,  width=1.5, style=Qt.PenStyle.DotLine),  name="EV")
        self.c_hero =self.plot.plot(pen=pg.mkPen(color="#b48ead",width=2,  style=Qt.PenStyle.DashLine), name="My Profit vs")
        self.plot.addLegend(offset=(10,10))
        gl.addWidget(self.plot); clay.addWidget(gcard)

        # Stats grid
        stats_frame=QFrame(); stats_frame.setObjectName("card")
        sfl=QVBoxLayout(stats_frame); sfl.setContentsMargins(12,12,12,12); sfl.setSpacing(8)
        sfl.addWidget(lbl("VILLAIN STATS",size=11,dim=True))
        self.stats_grid=QGridLayout(); self.stats_grid.setSpacing(6)
        sfl.addLayout(self.stats_grid); clay.addWidget(stats_frame)

        # Leaks
        leaks_frame=QFrame(); leaks_frame.setObjectName("card")
        lfl=QVBoxLayout(leaks_frame); lfl.setContentsMargins(12,12,12,12); lfl.setSpacing(8)
        lfl.addWidget(lbl("🎯  EXPLOIT NOTES",size=11,dim=True))
        self.leaks_lay=QVBoxLayout(); self.leaks_lay.setSpacing(6)
        lfl.addLayout(self.leaks_lay); clay.addWidget(leaks_frame)

        # Notes
        notes_frame=QFrame(); notes_frame.setObjectName("card")
        nfl=QVBoxLayout(notes_frame); nfl.setContentsMargins(12,12,12,12); nfl.setSpacing(6)
        nfl.addWidget(lbl("📝  MY NOTES",size=11,dim=True))
        self.notes=QTextEdit(); self.notes.setPlaceholderText("Add your own notes about this player...")
        self.notes.setMaximumHeight(80); nfl.addWidget(self.notes); clay.addWidget(notes_frame)

        lay.addWidget(self.content)
        self.loading_lbl=lbl("Loading...",dim=True)
        self.loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_lbl.hide(); lay.addWidget(self.loading_lbl)

    def _toggle_name_blur(self):
        self._name_blurred = not self._name_blurred
        if self._name_blurred:
            effect=QGraphicsBlurEffect()
            effect.setBlurRadius(10)
            self.name_lbl.setGraphicsEffect(effect)
            self.eye_btn.setText("Show")
            self.eye_btn.setToolTip("Reveal villain name")
        else:
            self.name_lbl.setGraphicsEffect(None)
            self.eye_btn.setText("Hide")
            self.eye_btn.setToolTip("Blur villain name")

    def load_villain(self, name, hands, profit):
        self.placeholder.hide(); self.content.hide()
        self.loading_lbl.setText(f"Loading profile for {name}..."); self.loading_lbl.show()
        d_from, d_to = self.get_dates()
        self._current_villain=name; self._current_d_from=d_from; self._current_d_to=d_to
        self._load_gen=getattr(self,'_load_gen',0)+1
        my_gen=self._load_gen
        if not hasattr(self,'_active_loaders'): self._active_loaders=[]
        loader=VillainLoader(self.hero, name, d_from, d_to)
        self._active_loaders.append(loader)
        def _cleanup(l=loader):
            if l in self._active_loaders: self._active_loaders.remove(l)
        loader.done.connect(lambda data,g=my_gen: self._on_loaded(data, name, hands, profit, g))
        loader.error.connect(lambda e: self.loading_lbl.setText(f"Error: {e}"))
        loader.finished.connect(_cleanup)
        self.loader=loader
        loader.start()

    def _on_loaded(self, data, name, hands, profit, gen):
        if gen != self._load_gen:
            return  # a newer load has since been requested; ignore this stale result
        self.loading_lbl.hide()
        vstats=data['vstats']; graph=data['graph']

        if vstats and vstats[0]:
            vn=int(vstats[0]); bb100=vstats[1]; ev_bb100=vstats[2]
            vpip=vstats[3]; pfr=vstats[4]
            tb=vstats[5]; f3=vstats[6]; fb=vstats[7]; f4=vstats[8]
            wtsd=vstats[9]; wsd=vstats[10]; fcbet=vstats[11]; wwsf=vstats[12]
            fold_fcbet=vstats[13]; xr_flop=vstats[14]; fold_xr=vstats[15]
            float_flop=vstats[16]; fold_floatflop=vstats[17]
            tcbet=vstats[18]; fold_tcbet=vstats[19]; xr_turn=vstats[20]
            fold_xrturn=vstats[21]; float_turn=vstats[22]; fold_floatturn=vstats[23]
        else:
            vn=hands; bb100=ev_bb100=None
            vpip=pfr=tb=f3=fb=f4=wtsd=wsd=fcbet=wwsf=None
            fold_fcbet=xr_flop=fold_xr=float_flop=fold_floatflop=None
            tcbet=fold_tcbet=xr_turn=fold_xrturn=float_turn=fold_floatturn=None

        vil_profit=float(sum(r[1] or 0 for r in graph)) if graph else 0.0

        ptype, pcolor = classify_player(vpip,pfr,tb,wtsd)
        self.name_lbl.setText(name)
        self.type_lbl.setText(ptype)
        self.type_lbl.setStyleSheet(f"color:{pcolor};font-size:13px;font-weight:600;background:transparent;border:none;")
        col=GREEN if vil_profit>=0 else RED
        hero_col=GREEN if profit>=0 else RED
        self.hands_lbl.setText(
            f"{vn:,} hands  ·  "
            f"Villain: <span style='color:{col}'>${vil_profit:+,.2f}</span>  ·  "
            f"vs Me: <span style='color:{hero_col}'>${profit:+,.2f}</span>")
        self.hands_lbl.setTextFormat(Qt.TextFormat.RichText)

        # Graph
        if graph:
            xs=list(range(len(graph)))
            def cumul(col_idx):
                running=0; out=[]
                for r in graph: running+=float(r[col_idx] or 0); out.append(round(running,2))
                return out
            t=cumul(1); sd=cumul(2); nsd=cumul(3); ev=cumul(4)
            col=GREEN if t[-1]>=0 else RED
            self.c_total.setData(xs,t,pen=pg.mkPen(color=col,width=2.5))
            self.c_sd.setData(xs,sd)
            self.c_nsd.setData(xs,nsd)
            self.c_ev.setData(xs,ev)

        # Stats grid
        for i in reversed(range(self.stats_grid.count())):
            self.stats_grid.itemAt(i).widget().deleteLater()

        stat_defs=[
            ("BB/100",bb100,None,None,"rate"),("EV BB/100",ev_bb100,None,None,"rate"),
            ("VPIP",vpip,22,26,"pct"),("PFR",pfr,17,21,"pct"),
            ("3Bet",tb,8,10,"pct"),("Fold 3Bet",f3,50,60,"pct"),
            ("Cbet Flop",fcbet,55,65,"pct"),("Fold to Flop Cbet",fold_fcbet,45,55,"pct"),
            ("XR Flop",xr_flop,8,12,"pct"),("Fold to XR",fold_xr,55,65,"pct"),
            ("Float Flop",float_flop,None,None,"pct"),("Fold vs Float",fold_floatflop,None,None,"pct"),
            ("Cbet Turn",tcbet,50,60,"pct"),("Fold to Turn Cbet",fold_tcbet,45,55,"pct"),
            ("XR Turn",xr_turn,6,10,"pct"),("Fold to Turn XR",fold_xrturn,55,65,"pct"),
            ("Probe Turn",float_turn,None,None,"pct"),("Fold to Probe Turn",fold_floatturn,None,None,"pct"),
            ("4Bet",fb,2,4,"pct"),("Fold 4Bet",f4,45,55,"pct"),
            ("WTSD",wtsd,26,32,"pct"),("W$SD",wsd,50,56,"pct"),
            ("WWSF",wwsf,38,46,"pct"),
        ]
        pop_avgs={"VPIP":24,"PFR":19,"3Bet":9,"Fold 3Bet":55,
                  "Cbet Flop":60,"Fold to Flop Cbet":50,"XR Flop":10,"Fold to XR":60,
                  "Cbet Turn":55,"Fold to Turn Cbet":50,"XR Turn":8,"Fold to Turn XR":60,
                  "4Bet":3,"Fold 4Bet":50,"WTSD":29,"W$SD":53,"WWSF":42}

        for i,sdef in enumerate(stat_defs):
            sname,sval,lo,hi,kind=sdef
            row=i//6; col_i=i%6
            clickable = sval is not None and sname in STAT_HAND_CONDITIONS
            card = ClickableFrame() if clickable else QFrame()
            card.setObjectName("card")
            if clickable:
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.setToolTip(f"Click to see hands where this happened")
                card.clicked.connect(lambda checked=False, sn=sname: self._show_hand_list(sn))
            cl=QVBoxLayout(card); cl.setContentsMargins(10,8,10,8); cl.setSpacing(2)
            cl.addWidget(lbl(sname,size=10,dim=True))
            if sval is not None:
                fv=float(sval)
                if kind=="rate":
                    vc=GREEN if fv>=0 else RED
                    vl=lbl(f"{fv:+.2f}",size=16,bold=True)
                elif lo is None or hi is None:
                    vc="#d8dee9"
                    vl=lbl(f"{sval}%",size=16,bold=True)
                else:
                    m=(hi-lo)*0.5
                    if lo<=fv<=hi:             vc=GREEN
                    elif (lo-m)<=fv<=(hi+m):  vc=ORANGE
                    else:                      vc=RED
                    vl=lbl(f"{sval}%",size=16,bold=True)
                vl.setStyleSheet(f"color:{vc};font-size:16px;font-weight:700;background:transparent;border:none;")
                cl.addWidget(vl)
                pop=pop_avgs.get(sname)
                if pop: cl.addWidget(lbl(f"Pop avg: {pop}%",size=9,dim=True))
            else:
                cl.addWidget(lbl("—",size=16,bold=True))
            self.stats_grid.addWidget(card,row,col_i)

        # Leaks
        for i in reversed(range(self.leaks_lay.count())):
            w=self.leaks_lay.itemAt(i).widget()
            if w: w.deleteLater()

        vstats_dict=dict(vpip=vpip,pfr=pfr,threebet=tb,fold3bet=f3,
                         fourbet=fb,fold4bet=f4,wtsd=wtsd,wsd=wsd,fold_fcbet=fcbet)
        leaks=generate_leaks(vstats_dict)
        for icon,title,desc in leaks:
            row_w=QFrame(); row_w.setStyleSheet(f"background:{BG3};border-radius:6px;border:none;")
            rl=QVBoxLayout(row_w); rl.setContentsMargins(12,8,12,8); rl.setSpacing(2)
            rl.addWidget(lbl(f"{icon}  {title}",size=12,bold=True))
            rl.addWidget(lbl(desc,size=11,dim=True))
            self.leaks_lay.addWidget(row_w)

        # Cache stats for type filter
        if self._pop_tab is not None:
            self._pop_tab._vstats_cache[name] = dict(
                vpip=float(vpip or 0), pfr=float(pfr or 0),
                threebet=float(tb or 0), wtsd=float(wtsd or 0)
            )
        self.content.show()

    def _show_hand_list(self, stat_name):
        condition = STAT_HAND_CONDITIONS.get(stat_name)
        if not condition: return
        villain = getattr(self, '_current_villain', None)
        d_from = getattr(self, '_current_d_from', None)
        d_to = getattr(self, '_current_d_to', None)
        if not villain or not d_from or not d_to: return
        dlg = HandListDialog(stat_name, villain, condition, d_from, d_to, parent=self)
        dlg.exec()


class PopulationTab(QWidget):
    def __init__(self, hero, get_dates_fn):
        super().__init__()
        self.hero=hero; self.get_dates=get_dates_fn
        self.all_villains=[]; self.filtered_villains=[]; self._vstats_cache={}; self.d_from=date.today(); self.d_to=date.today()
        self._selected_villain=None
        self._sort_col=None; self._sort_asc=False
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        splitter=QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)

        # Left — villain list
        left=QWidget(); left.setMinimumWidth(320)
        ll=QVBoxLayout(left); ll.setContentsMargins(20,20,8,20); ll.setSpacing(10)
        ll.addWidget(lbl("VILLAIN POOL",size=11,dim=True))

        self.search=QLineEdit(); self.search.setPlaceholderText("🔍  Search player name...")
        self.search.textChanged.connect(lambda t: self._filter())
        ll.addWidget(self.search)

        # Filter row
        frow=QHBoxLayout(); frow.setSpacing(8)
        self.type_cb=QComboBox()
        self.type_cb.addItems(["All Players","Fish 🐟","Regs 🎯","Nits 🧊","LAG 🔥","Calling Station 📞"])
        self.type_cb.currentTextChanged.connect(self._filter)
        frow.addWidget(self.type_cb)

        self.minhand_cb=QComboBox()
        self.minhand_cb.addItems(["Min 1 hand","Min 10 hands","Min 50 hands","Min 100 hands","Min 200 hands"])
        self.minhand_cb.currentTextChanged.connect(self._filter)
        frow.addWidget(self.minhand_cb)
        ll.addLayout(frow)

        self.table=QTableWidget()
        cols=["Player","Hands","VPIP","PFR","3Bet","WTSD","Profit vs"]
        self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels(cols)
        header=self.table.horizontalHeader()
        # Interactive lets the user drag any column border to resize it, like Excel.
        for c in range(len(cols)):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0,150); self.table.setColumnWidth(1,70)
        self.table.setColumnWidth(2,70); self.table.setColumnWidth(3,70)
        self.table.setColumnWidth(4,70); self.table.setColumnWidth(5,70)
        self.table.setColumnWidth(6,90)
        header.setStretchLastSection(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.cellClicked.connect(self._on_select)
        ll.addWidget(self.table)
        splitter.addWidget(left)

        # Right — profile
        right=QScrollArea(); right.setWidgetResizable(True)
        right.setStyleSheet("border:none;")
        self.profile=VillainProfile(hero,get_dates_fn)
        self.profile._pop_tab=self
        right.setWidget(self.profile)
        splitter.addWidget(right)

        splitter.setStretchFactor(0,0)
        splitter.setStretchFactor(1,1)
        splitter.setSizes([480,700])
        outer.addWidget(splitter)

    def refresh(self, villain_cache, d_from, d_to):
        self.d_from=d_from; self.d_to=d_to
        self.all_villains=villain_cache
        # Filter to only villains with hands in date range
        from collections import defaultdict
        filtered=defaultdict(lambda:{'hands':0,'profit':0.0,'vpip':0,'pfr_n':0,'pfr_d':0,
                                      'tb_n':0,'tb_d':0,'sd':0,'saw_f':0,'walk':0})
        for name, hand_date, profit, vpip, pfr_n, pfr_d, tb_n, tb_d, sd, saw_f, walk in villain_cache:
            if d_from <= hand_date <= d_to:
                f=filtered[name]
                f['hands']+=1; f['profit']+=float(profit or 0)
                f['vpip']+=vpip; f['pfr_n']+=pfr_n; f['pfr_d']+=pfr_d
                f['tb_n']+=tb_n; f['tb_d']+=tb_d
                f['sd']+=sd; f['saw_f']+=saw_f; f['walk']+=walk
        # Only show villains with 1+ hands in period
        def pct(n,d): return round(100*n/d,2) if d else None
        result=[(name, v['hands'], round(v['profit'],2),
                 pct(v['vpip'],v['hands']-v['walk']), pct(v['pfr_n'],v['pfr_d']),
                 pct(v['tb_n'],v['tb_d']), pct(v['sd'],v['saw_f']))
                for name, v in sorted(filtered.items(), key=lambda x: -x[1]['hands'])
                if v['hands'] >= 1]
        self.filtered_villains=result
        self._populate(result)
        # If a villain is currently selected, reload their profile for the new period
        # (otherwise the right-side panel would silently keep showing the old period's data)
        if self._selected_villain:
            match=next((v for v in result if v[0]==self._selected_villain), None)
            if match:
                self.profile.load_villain(match[0], int(match[1]), float(match[2] or 0))
            else:
                self._selected_villain=None

    def _populate(self, villains):
        self.table.setRowCount(0)
        for v in villains:
            name,hands,profit=v[0],int(v[1]),float(v[2] or 0)
            vpip,pfr,tb,wtsd=v[3],v[4],v[5],v[6]
            def fmt(x): return f"{x}%" if x is not None else "—"
            r=self.table.rowCount(); self.table.insertRow(r)
            for c,(val,col) in enumerate([
                (name,None),(f"{hands:,}",None),
                (fmt(vpip),None),(fmt(pfr),None),(fmt(tb),None),(fmt(wtsd),None),
                (f"${profit:+,.2f}",GREEN if profit>=0 else RED)
            ]):
                item=QTableWidgetItem(val)
                if c==0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
                    item.setToolTip(name)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col: item.setForeground(QColor(col))
                self.table.setItem(r,c,item)
            self.table.setRowHeight(r,34)

    def _filter(self, text=None):
        if text is None: text=self.search.text()
        source=getattr(self,'filtered_villains',[])
        if not source:
            return

        min_map={"Min 1 hand":1,"Min 10 hands":10,"Min 50 hands":50,
                 "Min 100 hands":100,"Min 200 hands":200}
        min_h=min_map.get(self.minhand_cb.currentText(),1)
        type_sel=self.type_cb.currentText()

        filtered=[]
        for v in source:
            name,hands,profit=v[0],v[1],v[2]
            if text and text.lower() not in name.lower():
                continue
            if hands < min_h:
                continue
            # Type filter — use cached stats if available, else include
            if type_sel != "All Players":
                vstats=self._vstats_cache.get(name)
                if vstats is not None:
                    vpip=float(vstats.get('vpip') or 0)
                    pfr=float(vstats.get('pfr') or 0)
                    tb=float(vstats.get('threebet') or 0)
                    wtsd=float(vstats.get('wtsd') or 0)
                    ptype,_=classify_player(vpip,pfr,tb,wtsd)
                    type_map={
                        "Fish 🐟":       lambda p: "Fish" in p,
                        "Regs 🎯":       lambda p: "Reg" in p,
                        "Nits 🧊":       lambda p: "Nit" in p,
                        "LAG 🔥":        lambda p: "LAG" in p,
                        "Calling Station 📞": lambda p: "Calling" in p,
                    }
                    checker=type_map.get(type_sel)
                    if checker and not checker(ptype):
                        continue
                # No cached stats — include by default so list isn't empty
            filtered.append(v)
        filtered=self._apply_sort(filtered)
        self._populate(filtered)

    def _on_header_clicked(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = False  # first click on a new column: high to low
        order = Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(col, order)
        self._filter()

    def _apply_sort(self, data):
        if self._sort_col is None or not data:
            return data
        # table col -> index within each villain tuple (name,hands,profit,vpip,pfr,tb,wtsd)
        idx_map={0:0, 1:1, 2:3, 3:4, 4:5, 5:6, 6:2}
        idx=idx_map.get(self._sort_col)
        if idx is None: return data
        is_str=(self._sort_col==0)
        if is_str:
            return sorted(data, key=lambda v: (v[idx] or '').lower(), reverse=not self._sort_asc)
        with_val=[v for v in data if v[idx] is not None]
        none_val=[v for v in data if v[idx] is None]
        with_val.sort(key=lambda v: v[idx], reverse=not self._sort_asc)
        return with_val + none_val

    def _on_select(self, row, col):
        name_item=self.table.item(row,0)
        if not name_item: return
        name=name_item.text()
        # Find hands and profit from cache
        source=getattr(self,'filtered_villains',self.all_villains)
        for v in source:
            if v[0]==name:
                self._selected_villain=name
                self.profile.load_villain(name,int(v[1]),float(v[2] or 0))
                break


# ─── LOADING SCREEN ───────────────────────────────────────────────────────────

class LoadingWidget(QWidget):
    def __init__(self):
        super().__init__()
        lay=QVBoxLayout(self); lay.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.setSpacing(20)
        lay.addWidget(lbl("🃏  Poker Dashboard",size=28,bold=True),
                      alignment=Qt.AlignmentFlag.AlignCenter)
        self.status=lbl("Connecting to PT4...",size=14,dim=True)
        lay.addWidget(self.status,alignment=Qt.AlignmentFlag.AlignCenter)
        self.bar=QProgressBar(); self.bar.setFixedWidth(400); self.bar.setFixedHeight(6)
        self.bar.setRange(0,100); lay.addWidget(self.bar,alignment=Qt.AlignmentFlag.AlignCenter)

    def update(self,pct,msg):
        self.bar.setValue(pct); self.status.setText(msg)


# ─── MAIN WINDOW ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Poker Dashboard"); self.setMinimumSize(1300,800)
        self.all_hands=[]; self.villain_cache=[]; self.hero="—"
        self.stakes_map=[("All Stakes",None)]
        self.stack=QWidget(); self.setCentralWidget(self.stack)
        self.main_lay=QVBoxLayout(self.stack)
        self.main_lay.setContentsMargins(0,0,0,0); self.main_lay.setSpacing(0)
        self.loading=LoadingWidget(); self.main_lay.addWidget(self.loading)
        self._start_load()

    def _start_load(self):
        try:
            conn=psycopg2.connect(**DB)
            self.hero=self._get_hero(conn)
            self.stakes_map=self._get_stakes(conn)
            conn.close()
        except Exception as e:
            self.loading.status.setText(f"❌ Could not connect: {e}"); return
        self.loader=DataLoader(self.hero)
        self.loader.progress.connect(self._on_progress)
        self.loader.done.connect(self._on_loaded)
        self.loader.error.connect(lambda e: self.loading.status.setText(f"❌ {e}"))
        self.loader.start()

    def _get_hero(self,conn):
        cur=conn.cursor()
        cur.execute("""SELECT p.player_name FROM cash_hand_player_statistics chps
            JOIN player p ON chps.id_player=p.id_player
            GROUP BY p.player_name ORDER BY COUNT(*) DESC LIMIT 1""")
        row=cur.fetchone(); cur.close(); return row[0] if row else "Hero"

    def _get_stakes(self,conn):
        cur=conn.cursor()
        cur.execute("""SELECT DISTINCT cl.id_limit,cl.limit_name,cl.amt_bb
            FROM cash_limit cl JOIN cash_hand_summary chs ON cl.id_limit=chs.id_limit
            WHERE cl.flg_nl=True ORDER BY cl.amt_bb""")
        rows=cur.fetchall(); cur.close()
        return [("All Stakes",None)]+[(r[1],r[0]) for r in rows]

    def _on_progress(self,pct,msg): self.loading.update(pct,msg)

    def _on_loaded(self,data):
        self.all_hands=data['hands']; self.villain_cache=data['villains']
        self.loading.update(100,"Done!"); self._build_main_ui()

    def _get_dates(self):
        return date_range(self.period_cb.currentText())

    def _build_main_ui(self):
        self.main_lay.removeWidget(self.loading); self.loading.deleteLater()
        # Header
        header=QFrame()
        header.setStyleSheet(f"background:{BG2};border-bottom:1px solid {BORDER};")
        header.setFixedHeight(60)
        hl=QHBoxLayout(header); hl.setContentsMargins(24,0,24,0)
        hl.addWidget(lbl("🃏  Poker Dashboard",size=17,bold=True)); hl.addStretch()
        hl.addWidget(lbl(f"● Connected  |  Hero: {self.hero}  |  {len(self.all_hands):,} hands loaded",
                         size=12,color=GREEN))
        self.main_lay.addWidget(header)
        # Filter bar
        fbar=QFrame()
        fbar.setStyleSheet(f"background:{BG};border-bottom:1px solid {BORDER};")
        fbar.setFixedHeight(52)
        fl=QHBoxLayout(fbar); fl.setContentsMargins(24,0,24,0); fl.setSpacing(12)
        fl.addWidget(lbl("Period",dim=True))
        self.period_cb=QComboBox()
        self.period_cb.addItems(["Today","Yesterday","This Week","This Month",
                                  "Last Month","This Year","Last Year"])
        self.period_cb.setCurrentText("This Month")
        self.period_cb.currentTextChanged.connect(self.refresh)
        fl.addWidget(self.period_cb)
        fl.addSpacing(8); fl.addWidget(lbl("Stakes",dim=True))
        self.stakes_cb=QComboBox()
        for lt,_ in self.stakes_map: self.stakes_cb.addItem(lt)
        self.stakes_cb.currentTextChanged.connect(self.refresh)
        fl.addWidget(self.stakes_cb)
        fl.addStretch()
        self.info_lbl=lbl("",dim=True); fl.addWidget(self.info_lbl)
        self.main_lay.addWidget(fbar)
        # Tabs
        self.tabs=QTabWidget()
        self.tab_ov   =OverviewTab()
        self.tab_sess =SessionsTab()
        self.tab_stats=StatsTab()
        self.tab_pop  =PopulationTab(self.hero,self._get_dates)
        self.tabs.addTab(self.tab_ov,   "  Overview  ")
        self.tabs.addTab(self.tab_sess, "  Sessions  ")
        self.tabs.addTab(self.tab_stats,"  Stats  ")
        self.tabs.addTab(self.tab_pop,  "  Population  ")
        wrap=QWidget(); wl=QVBoxLayout(wrap)
        wl.setContentsMargins(16,12,16,16); wl.addWidget(self.tabs)
        self.main_lay.addWidget(wrap)
        self.refresh()

    def _get_limit(self):
        sel=self.stakes_cb.currentText()
        for lt,il in self.stakes_map:
            if lt==sel: return il
        return None

    def _update_stakes_for_period(self, d_from, d_to):
        """Update stakes dropdown to only show stakes played in selected period"""
        # Find which id_limits appear in the filtered hands
        active_limits = set(h['id_limit'] for h in self.all_hands
                           if d_from <= h['d'] <= d_to)
        # Rebuild stakes dropdown preserving current selection
        current = self.stakes_cb.currentText()
        self.stakes_cb.blockSignals(True)
        self.stakes_cb.clear()
        self.stakes_cb.addItem("All Stakes")
        for label_txt, id_limit in self.stakes_map[1:]:  # skip "All Stakes"
            if id_limit in active_limits:
                self.stakes_cb.addItem(label_txt)
        # Restore selection if still valid, else reset to All Stakes
        idx = self.stakes_cb.findText(current)
        self.stakes_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.stakes_cb.blockSignals(False)

    def refresh(self):
        if not self.all_hands: return
        d_from,d_to=date_range(self.period_cb.currentText())
        self._update_stakes_for_period(d_from, d_to)
        id_limit=self._get_limit()
        hands=filter_hands(self.all_hands,d_from,d_to,id_limit)
        stats=calc_stats(hands); sessions=calc_sessions(hands); graph=calc_graph(hands)
        self.info_lbl.setText(f"{len(hands):,} hands  ·  {d_from}  →  {d_to}")
        self.tab_ov.refresh(stats,graph)
        self.tab_sess.refresh(sessions)
        self.tab_stats.load(self.hero, d_from, d_to, id_limit)
        # Filter villain cache by date period
        self.tab_pop.refresh(self.villain_cache,d_from,d_to)


def main():
    app=QApplication(sys.argv); app.setStyleSheet(STYLE)
    win=MainWindow(); win.show(); sys.exit(app.exec())

if __name__=="__main__":
    main()
