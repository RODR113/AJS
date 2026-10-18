"""Regras de pontuação da liga. Funções puras, fáceis de testar."""
import unicodedata


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def match_points(pred, real) -> int:
    """pred/real = (golos_casa, golos_fora).
    3 = exato | 2 = mesma diferença de golos (inclui empates) | 1 = só o vencedor | 0 = falhou."""
    (ph, pa), (rh, ra) = pred, real
    if (ph, pa) == (rh, ra):
        return 3
    if ph - pa == rh - ra:
        return 2
    sign = lambda x: (x > 0) - (x < 0)
    if sign(ph - pa) == sign(rh - ra) and sign(rh - ra) != 0:
        return 1
    return 0


def bonus_points(pick: dict, standings: list, scorers: list) -> int:
    """Pontuação final (fim do campeonato).
    pick = {"ranking": [equipas 1.º..último], "scorer": str, "defense": str}
    standings = [(pos, equipa, golos_sofridos, jogos)]; scorers = [(jogador, golos)]"""
    pts = 0
    real_pos = {team: pos for pos, team, _, _ in standings}
    for i, team in enumerate(pick.get("ranking") or [], start=1):
        if real_pos.get(team) == i:
            pts += 3
    if scorers:
        top = max(g for _, g in scorers)
        if top > 0 and norm(pick.get("scorer")) in {norm(p) for p, g in scorers if g == top}:
            pts += 5
    if standings and max(j for *_, j in standings) > 0:
        best = min(gs for _, _, gs, _ in standings)
        if pick.get("defense") in {t for _, t, gs, _ in standings if gs == best}:
            pts += 5
    return pts
