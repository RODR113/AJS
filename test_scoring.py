from scoring import match_points as mp, bonus_points
from fpp import parse_calendar, parse_standings, parse_scorers
from bs4 import BeautifulSoup as B


def test_match_points():
    assert mp((2, 1), (2, 1)) == 3
    assert mp((2, 0), (4, 2)) == 2      # exemplo das regras
    assert mp((1, 0), (3, 1)) == 1
    assert mp((1, 1), (2, 2)) == 2      # empate com diferença 0
    assert mp((1, 1), (2, 1)) == 0
    assert mp((2, 1), (1, 2)) == 0
    assert mp((0, 3), (1, 0)) == 0


def test_bonus():
    st = [(1, "A", 5, 2), (2, "B", 3, 2), (3, "C", 9, 2)]
    pick = {"ranking": ["A", "C", "B"], "scorer": "joão  silva", "defense": "B"}
    assert bonus_points(pick, st, [("João Silva", 4), ("X", 2)]) == 3 + 5 + 5


def test_parsers():
    cal = B("""<table><tr><td>1ª Jornada</td><td></td></tr>
    <tr><td>367</td><td>2026-10-24      21:00</td><td><a>APAC Tojal</a></td><td>-</td><td><a>S. Alenquer B</a></td><td>3 - 2</td></tr>
    <tr><td>368</td><td>2026-10-24 18:00</td><td>X</td><td>-</td><td>Y</td><td></td></tr></table>""", "html.parser")
    g = parse_calendar(cal)
    assert g[0]["hg"] == 3 and g[0]["ag"] == 2 and g[0]["rnd"] == 1 and g[1]["hg"] is None
    s = B("<table><tr><td>1</td><td>Equipa A</td>" + "<td>0</td>" * 8 + "</tr></table>", "html.parser")
    assert parse_standings(s)[0]["team"] == "A"
    assert parse_scorers(B("<table><tr><th>Jogador</th><th>Equipa</th><th>Golos</th></tr><tr><td>Zé</td><td>A</td><td>4</td></tr></table>", "html.parser"))[0]["goals"] == 4
    assert parse_scorers(B("<table><tr><th>Jogador</th><th>Equipa</th><th>Golos</th></tr></table>", "html.parser")) == []
