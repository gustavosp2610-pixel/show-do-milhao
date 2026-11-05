"""
Ponto de entrada principal (CLI) do jogo Show do Milhão e Handler Serverless (Vercel).
- No Terminal (`python main.py`): executa o menu interativo, partidas e reintento idempotente.
- Na Vercel (Serverless Runtime): exporta a classe `handler` exigida pelo builder Python da Vercel,
  exibindo uma página/API de status e o Ranking Top 10 sem quebrar o deploy do repositório compartilhado.
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
from typing import Any

from config import ConfigError, carregar_configuracao
from database import (
    DatabaseError,
    PerguntasInsuficientesError,
    SupabaseRepository,
)
from game_logic import (
    PartidaShowDoMilhao,
    ResultadoPartida,
    formatar_moeda,
    solicitar_apelido,
)


def persistir_com_reintento(
    repositorio: SupabaseRepository,
    resultado: ResultadoPartida,
    partidas_pendentes: list[ResultadoPartida],
) -> None:
    """
    Tenta salvar o resultado da partida no Supabase usando o mesmo UUID v4 gerado
    no início da partida (garantindo idempotência via upsert).
    Se falhar por queda de rede/timeout, mantém o registro em memória e pergunta
    ao jogador se deseja tentar reenviar imediatamente.
    """
    dados_payload = resultado.para_dicionario()

    while True:
        print(f"\n[*] Sincronizando partida (UUID: {resultado.id}) com o Supabase...")
        try:
            confirmado = repositorio.salvar_partida_idempotente(dados_payload)
            if confirmado:
                print("[✓] Sucesso! Partida salva e confirmada pelo banco de dados online.")
                if resultado in partidas_pendentes:
                    partidas_pendentes.remove(resultado)
                return
        except DatabaseError as erro:
            print(f"\n[!] Falha ao salvar partida no Supabase: {erro}")

        # Garante que a partida fique guardada em memória enquanto não for confirmada
        if resultado not in partidas_pendentes:
            partidas_pendentes.append(resultado)

        # Pergunta se o jogador quer tentar reenviar agora (usando o mesmo UUID)
        while True:
            try:
                opcao = (
                    input(
                        "\nDeseja tentar reenviar o resultado agora usando o mesmo UUID? (S/N): "
                    )
                    .strip()
                    .upper()
                )
            except EOFError:
                opcao = "N"

            if opcao in ("S", "SIM"):
                break
            if opcao in ("N", "NAO", "NÃO"):
                print(
                    "[i] O resultado permanece salvo na memória desta sessão "
                    f"(UUID: {resultado.id}). Você poderá reenviar pelo menu principal."
                )
                return
            print("[!] Entrada inválida. Digite S para Sim ou N para Não.")


def sincronizar_pendentes(
    repositorio: SupabaseRepository,
    partidas_pendentes: list[ResultadoPartida],
) -> None:
    """
    Tenta reenviar todas as partidas retidas na memória durante quedas de conexão.
    """
    if not partidas_pendentes:
        return

    print(
        f"\n[*] Existem {len(partidas_pendentes)} partida(s) pendente(s) na memória. "
        "Iniciando tentativa de reenvio idempotente..."
    )
    for partida in list(partidas_pendentes):
        persistir_com_reintento(repositorio, partida, partidas_pendentes)


def iniciar_fluxo_partida(
    repositorio: SupabaseRepository,
    partidas_pendentes: list[ResultadoPartida],
) -> None:
    """
    Orquestra a criação e execução de uma nova partida:
    1. Solicita apelido validado.
    2. Busca 18 perguntas no banco (9 titulares e 9 reservas) antes de iniciar o relógio.
    3. Executa a partida medindo o tempo exato de resposta.
    4. Persiste o resultado com garantia de idempotência.
    """
    apelido = solicitar_apelido()

    print("\n[*] Carregando perguntas do banco de dados...")
    try:
        perguntas = repositorio.buscar_perguntas_partida()
    except PerguntasInsuficientesError as erro_perguntas:
        print("\n" + "!" * 72)
        print(" [!] NÃO FOI POSSÍVEL INICIAR A PARTIDA (PERGUNTAS INSUFICIENTES)")
        print(f" Detalhe: {erro_perguntas}")
        print("!" * 72)
        return
    except DatabaseError as erro_db:
        print("\n" + "!" * 72)
        print(" [!] ERRO DE CONEXÃO COM O BANCO DE DADOS")
        print(f" Detalhe: {erro_db}")
        print("!" * 72)
        return

    partida = PartidaShowDoMilhao(
        jogo_id=repositorio.config.jogo_id,
        apelido=apelido,
        perguntas=perguntas,
    )
    resultado = partida.executar()
    persistir_com_reintento(repositorio, resultado, partidas_pendentes)
    # Só registra ajudas depois de confirmar a existência da partida.
    if resultado not in partidas_pendentes:
        try:
            repositorio.salvar_ajudas(partida.historico_ajudas)
        except DatabaseError as erro:
            print(f"[!] Histórico de ajudas não salvo: {erro}")


def exibir_ranking(repositorio: SupabaseRepository) -> None:
    """
    Consulta e exibe no terminal o Top 10 de partidas do jogo atual.
    """
    print("\n[*] Consultando Ranking Top 10 no Supabase...")
    try:
        registros: list[dict[str, Any]] = repositorio.consultar_ranking_top10()
    except DatabaseError as erro:
        print(f"\n[!] Erro ao consultar o ranking: {erro}")
        return

    print("\n" + "=" * 78)
    print(f"                     RANKING TOP 10 - SHOW DO MILHÃO (JOGO {repositorio.config.jogo_id})")
    print("=" * 78)

    if not registros:
        print("  Nenhuma partida registrada até o momento para este jogo.")
        print("=" * 78)
        return

    cabecalho = (
        f"{'POS':<5} | {'APELIDO':<18} | {'PRÊMIO GANHO':<17} | "
        f"{'ACERTOS':<7} | {'TEMPO (s)':<10} | {'STATUS'}"
    )
    print(cabecalho)
    print("-" * 78)

    for pos, item in enumerate(registros, start=1):
        apelido = str(item.get("apelido", "---"))[:18]
        valor = float(item.get("valor_ganho", 0.0))
        acertos = int(item.get("acertos", 0))
        tempo = float(item.get("tempo_segundos", 0.0))
        motivo = str(item.get("motivo_encerramento", "---")).capitalize()

        linha = (
            f"{f'{pos}º':<5} | {apelido:<18} | {formatar_moeda(valor):<17} | "
            f"{f'{acertos}/9':<7} | {f'{tempo:.2f}s':<10} | {motivo}"
        )
        print(linha)

    print("=" * 78)


def exibir_menu_principal(qtd_pendentes: int) -> None:
    """Exibe as opções do menu interativo no terminal."""
    print("\n" + "=" * 50)
    print("             SHOW DO MILHÃO - TERMINAL")
    print("=" * 50)
    print("  1. Iniciar Partida")
    print("  2. Consultar Ranking do Jogo (Top 10)")
    print("  3. Sair")
    if qtd_pendentes > 0:
        print(f"  4. Reenviar Partidas Pendentes na Memória ({qtd_pendentes})")
    print("=" * 50)


def main() -> None:
    """Fluxo principal da aplicação."""
    try:
        config = carregar_configuracao()
        repositorio = SupabaseRepository(config)
    except (ConfigError, DatabaseError) as erro_inicializacao:
        print("\n" + "!" * 72)
        print(" [!] ERRO DE CONFIGURAÇÃO / INICIALIZAÇÃO")
        print(f" {erro_inicializacao}")
        print("!" * 72)
        sys.exit(1)

    partidas_pendentes: list[ResultadoPartida] = []

    while True:
        exibir_menu_principal(len(partidas_pendentes))
        try:
            opcao = input("Escolha uma opção: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[!] Encerrando o programa...")
            opcao = "3"

        if opcao == "1":
            iniciar_fluxo_partida(repositorio, partidas_pendentes)
        elif opcao == "2":
            exibir_ranking(repositorio)
        elif opcao == "3":
            if partidas_pendentes:
                print(
                    f"\n[!] Atenção: Você possui {len(partidas_pendentes)} partida(s) "
                    "ainda não sincronizada(s) com o banco."
                )
                sincronizar_pendentes(repositorio, partidas_pendentes)
            print("\nObrigado por jogar o Show do Milhão! Até a próxima!\n")
            break
        elif opcao == "4" and len(partidas_pendentes) > 0:
            sincronizar_pendentes(repositorio, partidas_pendentes)
        else:
            print("\n[!] Opção inválida! Por favor, escolha uma opção válida do menu.")


class handler(BaseHTTPRequestHandler):
    """
    Entrypoint HTTP exigido pela Vercel quando `main.py` está na raiz do repositório.
    Permite que o build da Vercel passe sem erro (`PYTHON_ENTRYPOINT_NOT_FOUND`) e
    fornece um endpoint `/api/ranking` (JSON) ou visualização de status do módulo Python
    enquanto o front-end da equipe é integrado ao repositório.
    """

    def do_GET(self) -> None:  # noqa: N802 (nome exigido por BaseHTTPRequestHandler)
        ranking_dados: list[dict[str, Any]] = []
        status_msg = "Conectado ao Supabase"
        jogo_id_atual: int | str = "N/A"

        try:
            config = carregar_configuracao()
            jogo_id_atual = config.jogo_id
            repositorio = SupabaseRepository(config)
            ranking_dados = repositorio.consultar_ranking_top10()
        except (ConfigError, DatabaseError) as exc:
            status_msg = f"Aguardando configuração de variáveis de ambiente na Vercel ({exc})"

        # Se a requisição pedir JSON (útil para o site do seu amigo consumir se quiser)
        if self.path.startswith("/api/ranking") or "application/json" in self.headers.get("Accept", ""):
            corpo_json = json.dumps(
                {
                    "modulo": "Show do Milhão - Módulo Python",
                    "jogo_id": jogo_id_atual,
                    "status": status_msg,
                    "ranking_top10": ranking_dados,
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(corpo_json)
            return

        # Renderiza uma página HTML limpa de status e Ranking Top 10
        linhas_html = ""
        for pos, item in enumerate(ranking_dados, start=1):
            apelido = str(item.get("apelido", "---"))
            valor = formatar_moeda(float(item.get("valor_ganho", 0.0)))
            acertos = f"{int(item.get('acertos', 0))}/9"
            tempo = f"{float(item.get('tempo_segundos', 0.0)):.2f}s"
            motivo = str(item.get("motivo_encerramento", "---")).capitalize()
            linhas_html += (
                f"<tr><td>{pos}º</td><td>{apelido}</td><td>{valor}</td>"
                f"<td>{acertos}</td><td>{tempo}</td><td>{motivo}</td></tr>"
            )

        if not linhas_html:
            linhas_html = "<tr><td colspan='6'>Nenhuma partida encontrada ou variáveis de ambiente pendentes na Vercel.</td></tr>"

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Show do Milhão - Módulo Python & Ranking</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        .container {{ max-width: 860px; margin: 0 auto; background: #1e293b; padding: 2rem; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }}
        h1 {{ color: #fbbf24; margin-top: 0; }}
        .badge {{ display: inline-block; padding: 0.35rem 0.75rem; border-radius: 999px; background: #334155; font-size: 0.85rem; margin-bottom: 1.5rem; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ color: #fbbf24; font-weight: 600; }}
        code {{ background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; color: #38bdf8; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Show do Milhão — Integração Python + Supabase</h1>
        <div class="badge">Status: {status_msg} | Jogo ID: {jogo_id_atual}</div>
        <p>O módulo do jogo em Python está pronto. Para jogar pelo terminal localmente, execute <code>python main.py</code>.</p>
        <h2>Ranking Top 10 Atual</h2>
        <table>
            <thead>
                <tr><th>Pos</th><th>Apelido</th><th>Prêmio</th><th>Acertos</th><th>Tempo</th><th>Status</th></tr>
            </thead>
            <tbody>{linhas_html}</tbody>
        </table>
    </div>
</body>
</html>"""

        corpo_bytes = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo_bytes)


if __name__ == "__main__":
    main()

