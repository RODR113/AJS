import json, os
import pandas as pd
import streamlit as st

import db, fpp, scoring

st.set_page_config(page_title="Liga de Palpites · 2.ª Div. Sul", page_icon="🏒", layout="wide")


def secret(k, default=None):
    try:
        return st.secrets[k]
    except Exception:
        return os.environ.get(k, default)


@st.cache_resource
def get_eng():
    e = db.get_engine(secret("DATABASE_URL"))
    db.init(e)
    return e


@st.cache_resource(ttl=7200)  # volta a ler a FPP no máximo de 2 em 2 horas
def sync_job():
    try:
        fpp.sync_all(get_eng())
        return None
    except Exception as ex:
        return str(ex)


def fmt_dt(d):
    return pd.Timestamp(d).strftime("%a %d/%m %H:%M")


# ------------------------------------------------------------------ palpites
def page_picks(eng, player):
    st.header("Os meus palpites")
    m = db.matches(eng)
    if m.empty:
        st.info("Ainda não há jogos carregados.")
        return
    rounds = sorted(int(r) for r in m.rnd.unique())
    open_r = [r for r in rounds if not m[m.rnd == r].locked.all()]
    r = st.selectbox("Jornada", rounds, index=rounds.index(open_r[0] if open_r else rounds[-1]), format_func=lambda x: f"{x}ª jornada")
    mm = m[m.rnd == r].sort_values("kickoff")
    st.caption(f"Prazo: {fmt_dt(mm.deadline.iloc[0])} (cada jogo fecha ao apito inicial, se for antes).")
    mine = {int(x.match_id): (int(x.h), int(x.a)) for x in db.all_predictions(eng).query("token == @player.token").itertuples()}
    with st.form(f"round{r}"):
        vals = {}
        for g in mm.itertuples():
            c = st.columns([3, 1, 1, 3, 3])
            old = mine.get(g.id, (None, None))
            c[0].markdown(f"<div style='text-align:right;padding-top:.5rem'><b>{g.home}</b></div>", unsafe_allow_html=True)
            h = c[1].number_input("c", 0, 99, old[0], 1, key=f"h{g.id}", disabled=bool(g.locked), label_visibility="collapsed")
            a = c[2].number_input("f", 0, 99, old[1], 1, key=f"a{g.id}", disabled=bool(g.locked), label_visibility="collapsed")
            c[3].markdown(f"<div style='padding-top:.5rem'><b>{g.away}</b></div>", unsafe_allow_html=True)
            if not pd.isna(g.home_goals):
                real = (int(g.home_goals), int(g.away_goals))
                pts = scoring.match_points(old, real) if old[0] is not None else 0
                c[4].markdown(f"Resultado **{real[0]}-{real[1]}** · {pts} pts")
            else:
                c[4].caption(("🔒 fechado · " if g.locked else "") + fmt_dt(g.kickoff))
            vals[g.id] = (h, a)
        if st.form_submit_button("Guardar palpites", type="primary"):
            fresh = db.matches(eng).set_index("id")  # volta a verificar a hora no servidor
            saved = skipped = 0
            for mid, (h, a) in vals.items():
                if h is None or a is None:
                    continue
                if fresh.loc[mid, "locked"]:
                    skipped += 1
                    continue
                db.save_prediction(eng, player.token, mid, h, a)
                saved += 1
            if saved:
                st.success(f"{saved} palpite(s) guardado(s).")
            else:
                st.warning("Nada guardado.")
            if skipped:
                st.warning(f"{skipped} jogo(s) já estavam fechados e foram ignorados.")


def page_initial(eng, player):
    st.header("Apostas iniciais")
    teams = db.team_list(eng)
    if not teams:
        st.info("Ainda não há equipas carregadas.")
        return
    dl = db.initial_deadline(eng)
    closed = dl is not None and db.now() >= dl
    if dl:
        st.caption(f"Prazo: início da {db.INITIAL_ROUND}.ª jornada ({fmt_dt(dl)}).")
    picks = db.initial_picks(eng)
    mine = picks[picks.token == player.token]
    old = mine.iloc[0] if not mine.empty else None
    old_rank = json.loads(old.ranking) if old is not None and old.ranking else [None] * len(teams)
    if st.session_state.get("rk_owner") != player.token:  # preenche uma vez com o que já foi guardado
        st.session_state["rk_owner"] = player.token
        for i in range(len(teams)):
            cur = old_rank[i] if i < len(old_rank) and old_rank[i] in teams else None
            st.session_state[f"rk{i}"] = cur
    scorer = st.text_input("Melhor marcador (nome do jogador)", old.scorer if old is not None else "", disabled=closed, key="scorer_in")
    defense = st.selectbox("Defesa menos batida", teams, index=teams.index(old.defense) if old is not None and old.defense in teams else None, disabled=closed, key="defense_in")
    st.markdown("**Classificação final (1.º ao último)** · cada equipa só pode aparecer numa posição")
    cols = st.columns(2)
    for i in range(len(teams)):
        taken = {st.session_state.get(f"rk{j}") for j in range(len(teams)) if j != i} - {None}
        cols[i % 2].selectbox(f"{i + 1}.º", [t for t in teams if t not in taken], index=None, key=f"rk{i}", disabled=closed)
    rank = [st.session_state.get(f"rk{i}") for i in range(len(teams))]
    if st.button("Guardar apostas", type="primary", disabled=closed):
        if db.initial_deadline(eng) and db.now() >= db.initial_deadline(eng):
            st.error("O prazo já terminou.")
        elif None in rank or len(set(rank)) != len(teams):
            st.error("Preenche todas as posições sem repetir equipas.")
        elif not scorer.strip() or defense is None:
            st.error("Falta o melhor marcador ou a defesa menos batida.")
        else:
            db.save_initial(eng, player.token, scorer.strip(), defense, json.dumps(rank))
            st.success("Apostas guardadas.")
    if closed and not picks.empty:
        st.subheader("Apostas de todos")
        names = db.players(eng).set_index("token").name
        t = pd.DataFrame({"Jogador": picks.token.map(names), "Marcador": picks.scorer, "Defesa": picks.defense,
                          **{f"{i + 1}.º": [json.loads(r)[i] for r in picks.ranking] for i in range(len(teams))}})
        st.dataframe(t, hide_index=True, width="stretch")


# ---------------------------------------------------------------- consulta
def page_round_view(eng, player):
    st.header("Palpites da jornada")
    st.caption("Os palpites de cada jogo aparecem a toda a gente assim que o jogo fecha (sexta às 23h00 ou apito inicial, o que vier primeiro).")
    m, pl, preds = db.matches(eng), db.players(eng), db.all_predictions(eng)
    if m.empty or pl.empty:
        st.info("Ainda sem jogos ou jogadores.")
        return
    rounds = sorted(int(r) for r in m.rnd.unique())
    started = [r for r in rounds if m[m.rnd == r].locked.any()]
    r = st.selectbox("Jornada", rounds, index=rounds.index(started[-1] if started else rounds[0]), format_func=lambda x: f"{x}ª jornada")
    lookup = {(x.token, x.match_id): (x.h, x.a) for x in preds.itertuples()}
    rows = []
    for p in pl.itertuples():
        row = {"Jogador": p.name}
        for g in m[m.rnd == r].sort_values("kickoff").itertuples():
            pick = lookup.get((p.token, g.id))
            own = player is not None and p.token == player.token
            if pick and (g.locked or own):
                txt = f"{pick[0]}-{pick[1]}"
                if not pd.isna(g.home_goals):
                    txt += f" ({scoring.match_points(pick, (int(g.home_goals), int(g.away_goals)))})"
            else:
                txt = "🔒 enviado" if pick else "— falta"
            row[f"{g.home} – {g.away}" + (f"\n{int(g.home_goals)}-{int(g.away_goals)}" if not pd.isna(g.home_goals) else "")] = txt
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def league_table(eng):
    pl, m, preds = db.players(eng), db.matches(eng), db.all_predictions(eng)
    if pl.empty:
        return pd.DataFrame()
    rows = {t: {"Jogador": n} for t, n in zip(pl.token, pl.name)}
    total, exact, bonus = ({t: 0 for t in rows} for _ in range(3))
    if not m.empty and not preds.empty:
        d = preds.merge(m.dropna(subset=["home_goals", "away_goals"]), left_on="match_id", right_on="id")
        for x in d.itertuples():
            pts = scoring.match_points((x.h, x.a), (int(x.home_goals), int(x.away_goals)))
            col = f"J{int(x.rnd)}"
            rows[x.token][col] = rows[x.token].get(col, 0) + pts
            total[x.token] += pts
            exact[x.token] += int(pts == 3)
    if db.meta_get(eng, "season_finished") == "1":
        sd = db.df(eng, "SELECT pos, team, gs, j FROM standings")
        sc = db.df(eng, "SELECT player, goals FROM scorers")
        for x in db.initial_picks(eng).itertuples():
            if x.token in bonus:
                bonus[x.token] = scoring.bonus_points(
                    {"ranking": json.loads(x.ranking or "[]"), "scorer": x.scorer, "defense": x.defense},
                    list(sd.itertuples(index=False, name=None)), list(sc.itertuples(index=False, name=None)))
    out = pd.DataFrame(rows.values())
    rcols = sorted([c for c in out.columns if c.startswith("J") and c != "Jogador"], key=lambda c: int(c[1:]))
    out[rcols] = out[rcols].fillna(0).astype(int)
    tokens = list(rows)
    out["Jogos"], out["Bónus"], out["Exatos"] = [total[t] for t in tokens], [bonus[t] for t in tokens], [exact[t] for t in tokens]
    out["Total"] = out["Jogos"] + out["Bónus"]
    finished = db.meta_get(eng, "season_finished") == "1"
    out = out.rename(columns={"Jogos": "Pts palpites"})
    cols = ["Jogador", "Total"] + (["Pts palpites", "Bónus"] if finished else []) + ["Exatos"] + rcols
    out = out[cols].sort_values(["Total", "Exatos"], ascending=False)
    out.insert(0, "#", range(1, len(out) + 1))
    return out


def page_league(eng):
    st.header("🏆 Classificação da liga")
    t = league_table(eng)
    if t.empty:
        st.info("Ainda não há jogadores.")
    else:
        st.dataframe(t, hide_index=True, width="stretch")
        st.caption("Jx = pontos nessa jornada · Exatos = resultados certos (desempate) · No fim do campeonato aparecem também os pontos dos palpites e o bónus.")


def page_standings(eng):
    st.header("📊 Classificação do campeonato")
    d = db.df(eng, "SELECT pos, team, p, j, v, e, d, gm, gs, dg FROM standings ORDER BY pos")
    if d.empty:
        st.info("Sem dados da FPP ainda.")
        return
    d.columns = ["#", "Equipa", "P", "J", "V", "E", "D", "GM", "GS", "DG"]
    st.dataframe(d, hide_index=True, width="stretch")


def page_scorers(eng):
    st.header("🥅 Marcadores")
    d = db.df(eng, "SELECT player, team, goals FROM scorers ORDER BY goals DESC, player")
    if d.empty:
        st.info("Ainda não há marcadores (a lista só aparece depois dos primeiros golos).")
        return
    d.columns = ["Jogador", "Equipa", "Golos"]
    st.dataframe(d, hide_index=True, width="stretch")


# --------------------------------------------------------------------- admin
def page_admin(eng):
    st.header("🔧 Admin")
    key = secret("ADMIN_KEY")
    if not key:
        st.warning("Define ADMIN_KEY nos secrets para usares esta página.")
        return
    if st.text_input("Chave de admin", type="password") != key:
        return
    base = secret("APP_URL", "https://o-teu-site.streamlit.app").rstrip("/")
    st.subheader("Jogadores e links")
    with st.form("newplayer", clear_on_submit=True):
        name = st.text_input("Novo jogador")
        if st.form_submit_button("Adicionar") and name.strip():
            try:
                db.add_player(eng, name)
            except Exception:
                st.error("Esse nome já existe.")
    for p in db.players(eng).itertuples():
        c = st.columns([1, 4, 1])
        c[0].write(p.name)
        c[1].code(f"{base}/?p={p.token}", language=None)
        if c[2].button("Novo link", key=f"nt{p.token}"):
            db.new_token(eng, p.token)
            st.rerun()
    st.subheader("Resultado manual")
    m = db.matches(eng)
    if not m.empty:
        opts = {f"{g.rnd}ª · {g.home} – {g.away}": g.id for g in m.itertuples()}
        sel = st.selectbox("Jogo", list(opts))
        c = st.columns(3)
        hg, ag = c[0].number_input("Casa", 0, 99, 0), c[1].number_input("Fora", 0, 99, 0)
        if c[2].button("Guardar resultado"):
            db.save_result(eng, opts[sel], hg, ag)
            st.success("Guardado.")
    st.subheader("Estado")
    fin = st.checkbox("Campeonato terminado (ativa os pontos finais)", db.meta_get(eng, "season_finished") == "1")
    if st.button("Guardar estado"):
        with eng.begin() as c:
            db.meta_set(c, "season_finished", "1" if fin else "0")
        st.success("Guardado.")
    st.write(f"Última leitura da FPP: {db.meta_get(eng, 'last_sync') or 'nunca'}")
    if st.button("Testar leitura dos marcadores"):
        try:
            st.json(fpp.debug_scorers())
        except Exception as ex:
            st.error(str(ex))
    if st.button("Atualizar da FPP agora"):
        sync_job.clear()
        st.rerun()


# ---------------------------------------------------------------------- main
eng = get_eng()
err = sync_job()
token = st.query_params.get("p")
player = db.get_player(eng, token) if token else None

st.sidebar.title("🏒 Liga de Palpites")
st.sidebar.caption("CN 2.ª Divisão Sul · 2026/27")
pages = {}
if player:
    st.sidebar.success(f"Olá, {player.name}")
    pages["Os meus palpites"] = lambda: page_picks(eng, player)
    pages["Apostas iniciais"] = lambda: page_initial(eng, player)
else:
    st.sidebar.info("Modo leitura. Para palpitar usa o teu link pessoal.")
pages["Palpites da jornada"] = lambda: page_round_view(eng, player)
pages["Liga"] = lambda: page_league(eng)
pages["Classificação FPP"] = lambda: page_standings(eng)
pages["Marcadores"] = lambda: page_scorers(eng)
pages["Admin"] = lambda: page_admin(eng)
if err:
    st.sidebar.warning(f"Não consegui ler a FPP: {err}")
pages[st.sidebar.radio("Menu", list(pages))]()
