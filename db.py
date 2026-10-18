import os, secrets, types
from collections import Counter
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine, text

TZ = ZoneInfo("Europe/Lisbon")
INITIAL_ROUND = 3  # apostas iniciais fecham no 1.º jogo desta jornada


def now() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


SCHEMA = [
    "CREATE TABLE IF NOT EXISTS players (token TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL)",
    "CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, rnd INTEGER, kickoff TEXT, home TEXT, away TEXT, home_goals INTEGER, away_goals INTEGER)",
    "CREATE TABLE IF NOT EXISTS predictions (token TEXT, match_id INTEGER, h INTEGER, a INTEGER, updated TEXT, PRIMARY KEY (token, match_id))",
    "CREATE TABLE IF NOT EXISTS initial_picks (token TEXT PRIMARY KEY, scorer TEXT, defense TEXT, ranking TEXT, updated TEXT)",
    "CREATE TABLE IF NOT EXISTS standings (pos INTEGER, team TEXT, p INTEGER, j INTEGER, v INTEGER, e INTEGER, d INTEGER, gm INTEGER, gs INTEGER, dg INTEGER)",
    "CREATE TABLE IF NOT EXISTS scorers (player TEXT, team TEXT, goals INTEGER)",
    "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)",
]


def get_engine(url=None):
    url = url or os.environ.get("DATABASE_URL") or "sqlite:///liga.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)


def init(eng):
    with eng.begin() as c:
        for s in SCHEMA:
            c.execute(text(s))


def upsert(conn, table, keys: dict, values: dict):
    sets = ", ".join(f"{c}=:{c}" for c in values)
    where = " AND ".join(f"{c}=:{c}" for c in keys)
    r = conn.execute(text(f"UPDATE {table} SET {sets} WHERE {where}"), {**keys, **values})
    if r.rowcount == 0:
        cols = {**keys, **values}
        conn.execute(text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"), cols)


def df(eng, sql, **params):
    with eng.connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def meta_get(eng, k):
    r = df(eng, "SELECT v FROM meta WHERE k=:k", k=k)
    return None if r.empty else r.v.iloc[0]


def meta_set(conn, k, v):
    upsert(conn, "meta", {"k": k}, {"v": v})


# ---------- jogadores ----------
def players(eng):
    return df(eng, "SELECT token, name FROM players ORDER BY name")


def get_player(eng, token):
    r = df(eng, "SELECT token, name FROM players WHERE token=:t", t=token)
    return None if r.empty else types.SimpleNamespace(token=r.token.iloc[0], name=r.name.iloc[0])


def add_player(eng, name):
    tok = secrets.token_urlsafe(8)
    with eng.begin() as c:
        c.execute(text("INSERT INTO players (token, name) VALUES (:t, :n)"), {"t": tok, "n": name.strip()})
    return tok


def new_token(eng, old):
    new = secrets.token_urlsafe(8)
    with eng.begin() as c:
        for t in ("players", "predictions", "initial_picks"):
            c.execute(text(f"UPDATE {t} SET token=:n WHERE token=:o"), {"n": new, "o": old})
    return new


# ---------- jogos e prazos ----------
def round_deadline(kickoffs):
    """Sexta-feira às 23h00 anterior ao dia em que se joga a maioria dos jogos da jornada."""
    cnt = Counter(k.date() for k in kickoffs)
    ref = max(cnt, key=lambda d: (cnt[d], -d.toordinal()))
    back = (ref.weekday() - 4) % 7
    return datetime.combine(ref - timedelta(days=back), time(23, 0))


def matches(eng):
    d = df(eng, "SELECT * FROM matches ORDER BY kickoff, id")
    if d.empty:
        return d
    d["kickoff"] = pd.to_datetime(d["kickoff"])
    dl = {r: pd.Timestamp(round_deadline(list(g.kickoff))) for r, g in d.groupby("rnd")}
    d["deadline"] = pd.to_datetime(d["rnd"].map(dl))
    d["lock"] = d[["kickoff", "deadline"]].min(axis=1)  # fecha ao apito ou na sexta, o que vier primeiro
    n = pd.Timestamp(now())
    d["started"] = d["kickoff"] <= n
    d["locked"] = d["lock"] <= n
    return d


def initial_deadline(eng):
    m = matches(eng)
    r = m[m.rnd == INITIAL_ROUND] if not m.empty else m
    return None if r.empty else r.kickoff.min().to_pydatetime()


def team_list(eng):
    m = df(eng, "SELECT home, away FROM matches")
    return sorted(set(m.home) | set(m.away))


def save_result(eng, match_id, hg, ag):
    with eng.begin() as c:
        c.execute(text("UPDATE matches SET home_goals=:h, away_goals=:a WHERE id=:i"), {"h": hg, "a": ag, "i": match_id})


# ---------- palpites ----------
def all_predictions(eng):
    return df(eng, "SELECT token, match_id, h, a FROM predictions")


def save_prediction(eng, token, match_id, h, a):
    with eng.begin() as c:
        upsert(c, "predictions", {"token": token, "match_id": int(match_id)}, {"h": int(h), "a": int(a), "updated": now().isoformat(timespec="seconds")})


def initial_picks(eng):
    return df(eng, "SELECT * FROM initial_picks")


def save_initial(eng, token, scorer, defense, ranking_json):
    with eng.begin() as c:
        upsert(c, "initial_picks", {"token": token}, {"scorer": scorer, "defense": defense, "ranking": ranking_json, "updated": now().isoformat(timespec="seconds")})
