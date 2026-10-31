"""Lê calendário, classificação e marcadores de hp.fpp.pt e guarda na base de dados."""
import re
import requests
from bs4 import BeautifulSoup
from sqlalchemy import text

import db

BASE, COMP = "https://hp.fpp.pt", 495
HEADERS = {"User-Agent": "liga-palpites-amigos/1.0 (uso pessoal, poucos pedidos)"}


def _get(path):
    r = requests.get(BASE + path, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def _cells(tr):
    return [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in tr.find_all(["td", "th"])]


def _team(s):
    return re.sub(r"^Equipa\s+", "", s).strip()


def parse_calendar(soup):
    rnd, out = None, []
    for tr in soup.find_all("tr"):
        c = _cells(tr)
        if not c:
            continue
        m = re.match(r"(\d+)\s*[ªº]?\s*Jornada", c[0])
        if m:
            rnd = int(m.group(1))
            continue
        if rnd is None or len(c) < 5 or not c[0].isdigit():
            continue
        d = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})", c[1])
        if not d:
            continue
        res = re.search(r"(\d+)\s*[-–xX]\s*(\d+)", " ".join([c[3]] + c[5:]))
        out.append(dict(id=int(c[0]), rnd=rnd, kickoff=f"{d.group(1)} {d.group(2).zfill(5)}",
                        home=_team(c[2]), away=_team(c[4]),
                        hg=int(res.group(1)) if res else None, ag=int(res.group(2)) if res else None))
    return out


def parse_standings(soup):
    out = []
    for tr in soup.find_all("tr"):
        c = _cells(tr)
        if len(c) >= 10 and c[0].isdigit() and all(re.fullmatch(r"-?\d+", x) for x in c[2:10]):
            vals = dict(zip(["p", "j", "v", "e", "d", "gm", "gs", "dg"], map(int, c[2:10])))
            out.append(dict(pos=int(c[0]), team=_team(c[1]), **vals))
    return out


def _scorers_from_text(soup):
    """A página de marcadores não usa tabela: lê os textos pela ordem (posição, jogador, equipa, golos)."""
    toks = [re.sub(r"\s+", " ", t).strip() for t in soup.stripped_strings]
    toks = [t for t in toks if t]
    if "Golos" in toks:
        toks = toks[toks.index("Golos") + 1:]
    else:
        return []
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("Resultados divulgados"):
            break
        m = re.match(r"^\d+\s+(.+)$", t)  # posição e nome no mesmo texto
        if m and i + 2 < len(toks) and toks[i + 2].isdigit():
            out.append(dict(player=m.group(1), team=_team(toks[i + 1]), goals=int(toks[i + 2])))
            i += 3
        elif t.isdigit() and i + 3 < len(toks) and toks[i + 3].isdigit():
            out.append(dict(player=toks[i + 1], team=_team(toks[i + 2]), goals=int(toks[i + 3])))
            i += 4
        else:
            i += 1
    return out


def _scorers_from_table(soup):
    out = []
    for tr in soup.find_all("tr"):
        c = [x for x in _cells(tr) if x]
        if len(c) >= 4 and c[0].isdigit():
            c = c[1:]
        if len(c) >= 3 and re.fullmatch(r"\d+", c[-1]) and not c[0].isdigit():
            out.append(dict(player=c[0], team=_team(c[-2]), goals=int(c[-1])))
    return out


def parse_scorers(soup):
    return _scorers_from_text(soup) or _scorers_from_table(soup)


def sync_all(eng):
    cal = parse_calendar(_get(f"/Competicao/{COMP}"))
    if not cal:
        raise RuntimeError("calendário vazio (a FPP mudou a página?)")
    stand = parse_standings(_get(f"/Classificacao/{COMP}"))
    scor = parse_scorers(_get(f"/Marcadores/{COMP}"))
    with eng.begin() as c:
        for g in cal:
            vals = dict(rnd=g["rnd"], kickoff=g["kickoff"], home=g["home"], away=g["away"])
            if g["hg"] is not None:  # só sobrepõe resultados quando a FPP já os tem
                vals.update(home_goals=g["hg"], away_goals=g["ag"])
            db.upsert(c, "matches", {"id": g["id"]}, vals)
        if stand:
            c.execute(text("DELETE FROM standings"))
            c.execute(text("INSERT INTO standings (pos, team, p, j, v, e, d, gm, gs, dg) VALUES (:pos,:team,:p,:j,:v,:e,:d,:gm,:gs,:dg)"), stand)
        c.execute(text("DELETE FROM scorers"))
        if scor:
            c.execute(text("INSERT INTO scorers (player, team, goals) VALUES (:player,:team,:goals)"), scor)
        db.meta_set(c, "last_sync", db.now().isoformat(timespec="seconds"))
    return len(cal), len(stand), len(scor)
    
