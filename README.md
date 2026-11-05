# Show do Milhão — Python + Supabase + Site

Projeto escolar com três partes conectadas ao **mesmo banco Supabase**:

| Parte | Onde | O que faz |
|---|---|---|
| **Jogo em Python** | `main.py`, `game_logic.py`, `ajudas.py`, `database.py`, `config.py` | Jogo no terminal. Sorteia as perguntas do Supabase e grava o resultado em `partidas`. |
| **Banco Supabase** | `sql/schema.sql`, `sql/02_jogo_web.sql` | Perguntas, partidas, ajudas, prêmios e as funções que rodam o jogo do site. |
| **Site** | `site/` (GitHub Pages) | Jogo no navegador + ranking Top 10. |

As partidas do terminal e do site vão para a mesma tabela `partidas`, então **o ranking é um só**.

## Regras (iguais no terminal e no site)

Nove perguntas (3 fáceis, 3 médias e 3 difíceis), premiação substitutiva de R$ 1.000 até R$ 1.000.000. Ao errar ou parar, o jogador fica com o prêmio do último acerto. Ajudas:

- **Cartas:** uma vez por partida; elimina de 0 a 3 alternativas incorretas.
- **Universitários:** uma vez; três palpites (cada um acerta com 65% de chance).
- **Plateia:** uma vez; votação em porcentagem que soma 100%.
- **Pulos:** três por partida; troca a pergunta por outra do mesmo nível sem mudar o prêmio.

## Como tudo se conecta

```
 Terminal (Python) ──chave SECRETA──▶ Supabase ◀──chave PUBLICÁVEL── Site (navegador)
   lê perguntas, grava partidas          │            só lê o ranking e chama
                                          │            as funções web_* do jogo
                                   tabela partidas
                                   (ranking único)
```

- **Python** usa a chave secreta (`sb_secret_...`) no `.env`, que nunca vai para o GitHub.
- **Site** usa a chave publicável (`sb_publishable_...`) em `site/js/supabase.js`. Ela foi feita para ser pública: o banco só deixa essa chave **ler o ranking** e **chamar as funções do jogo**.
- O jogo do site roda **dentro do banco**: as funções `web_iniciar_partida`, `web_responder`, `web_usar_ajuda`, `web_parar` e `web_estado` sorteiam a pergunta, conferem a resposta e gravam o resultado. O gabarito nunca chega ao navegador, então não dá para colar pelo F12 nem inventar um resultado no ranking.

## Jogar no site

Abra <https://xxzre.github.io/jogo_show_do_milhao/>, vá em **Jogar**, digite um apelido e comece. Quando a partida acaba, o ranking atualiza sozinho. Para testar no computador: `python3 -m http.server 8000` na raiz e abra <http://localhost:8000/>.

## Rodar o jogo em Python

1. Instale as dependências: `python -m pip install -r requirements.txt`.
2. Copie `.env.example` para `.env`.
3. Preencha `SUPABASE_URL`, `SUPABASE_KEY` (chave **secreta**, em Supabase → Project Settings → API Keys) e `JOGO_ID=1`.
4. Rode `python main.py`.

Se puser a chave publicável no `.env` por engano, o programa avisa logo na abertura.

## Montar o banco do zero

No SQL Editor do Supabase, rode `sql/schema.sql` e depois `sql/02_jogo_web.sql`. Em seguida, cadastre as perguntas: pelo menos 6 por nível, porque o Python reserva 3 para os pulos. O projeto atual tem 8 por nível. As perguntas não ficam no GitHub porque o repositório é público e elas contêm o gabarito.

## Testes

```bash
python -m unittest discover -s tests -v
```

Os testes não dependem de rede nem de credenciais e rodam automaticamente no GitHub Actions.
