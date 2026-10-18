# Liga de Palpites · CN 2.ª Divisão Sul (hóquei em patins)

Site em Streamlit. Lê calendário, classificação e marcadores de hp.fpp.pt (de 2 em 2 horas),
cada jogador entra com um link pessoal (`?p=codigo`) e não há passwords.

## Pôr online (grátis)
1. **Base de dados:** cria um projeto em supabase.com → *Connect* → copia a *connection string* (Session pooler).
2. **Código:** põe esta pasta num repositório do GitHub.
3. **Site:** em share.streamlit.io cria uma app a apontar para `app.py` e, em *Secrets*, cola:
   ```toml
   DATABASE_URL = "postgresql://...a string do Supabase..."
   ADMIN_KEY = "uma-chave-tua"
   APP_URL = "https://o-teu-site.streamlit.app"
   ```
4. Abre o site → **Admin** → mete a chave → adiciona os amigos → copia o link de cada um e manda por WhatsApp.

## Testar no teu PC
```bash
pip install -r requirements.txt
streamlit run app.py        # usa SQLite local (liga.db) se não houver DATABASE_URL
pytest                      # testa pontuação e leitura das páginas
```

## Regras implementadas
- Cada jogo fecha ao apito inicial **ou** na sexta às 23h00 anterior à jornada, o que vier primeiro.
- Palpites dos outros só aparecem depois do apito inicial desse jogo.
- 3 pts exato · 2 pts mesma diferença de golos (inclui empates) · 1 pt só o vencedor · 0 caso contrário.
- Apostas iniciais fecham no 1.º jogo da 3.ª jornada (`INITIAL_ROUND` em `db.py`).
- Fim do campeonato: no Admin, marca "Campeonato terminado" → soma 3 pts por posição certa, 5 melhor marcador, 5 defesa menos batida (calculados a partir dos dados da FPP).
- Desempate na tabela da liga: mais resultados exatos.
