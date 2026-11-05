"""
Módulo de configuração do sistema.
Responsável por carregar variáveis de ambiente do arquivo .env e validar
as credenciais obrigatórias para conexão com o Supabase.
"""

import base64
import json
import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Carrega as variáveis definidas no arquivo .env (se existir)
load_dotenv()


class ConfigError(Exception):
    """Exceção lançada quando há erro ou ausência nas variáveis de ambiente."""
    pass


# Valores de exemplo do .env.example (contam como "não configurado").
CHAVES_DE_EXEMPLO = {
    "sua-anon-key-aqui",
    "sb_secret_COLOQUE_SUA_CHAVE_APENAS_NO_SERVIDOR",
}


def _chave_e_publica(chave: str) -> bool:
    """
    Diz se a chave é pública (publicável ou 'anon'). O jogo em Python precisa da
    chave SECRETA: com a pública o banco não deixa ler as perguntas nem gravar partidas.
    """
    if chave.startswith("sb_publishable_"):
        return True
    partes = chave.split(".")
    if len(partes) == 3:  # chave antiga em formato JWT: olha o campo "role"
        try:
            meio = partes[1] + "=" * (-len(partes[1]) % 4)
            return json.loads(base64.urlsafe_b64decode(meio)).get("role") == "anon"
        except (ValueError, json.JSONDecodeError):
            return False
    return False


@dataclass(frozen=True)
class AppConfig:
    """Estrutura imutável de configuração da aplicação."""
    supabase_url: str
    supabase_key: str
    jogo_id: int | str


def carregar_configuracao() -> AppConfig:
    """
    Lê e valida as variáveis de ambiente necessárias para execução do jogo.

    Returns:
        AppConfig: Objeto contendo SUPABASE_URL, SUPABASE_KEY e JOGO_ID validados.

    Raises:
        ConfigError: Se alguma variável obrigatória não estiver configurada ou for inválida.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_KEY", "").strip()
    jogo_id_raw = os.getenv("JOGO_ID", "").strip()

    campos_faltantes: list[str] = []

    if not supabase_url or supabase_url == "https://seu-projeto.supabase.co":
        campos_faltantes.append("SUPABASE_URL")
    if not supabase_key or supabase_key in CHAVES_DE_EXEMPLO:
        campos_faltantes.append("SUPABASE_KEY")
    if not jogo_id_raw:
        campos_faltantes.append("JOGO_ID")

    if campos_faltantes:
        raise ConfigError(
            f"Variáveis de ambiente ausentes ou não configuradas no arquivo .env: "
            f"{', '.join(campos_faltantes)}.\n"
            f"Dica: Copie o arquivo '.env.example' para '.env' e preencha com os dados do Supabase."
        )

    if not (supabase_url.startswith("http://") or supabase_url.startswith("https://")):
        raise ConfigError(
            f"SUPABASE_URL inválida ('{supabase_url}'). Deve iniciar com http:// ou https://."
        )

    if _chave_e_publica(supabase_key):
        raise ConfigError(
            "SUPABASE_KEY está com a chave PÚBLICA (sb_publishable_... ou anon). "
            "O jogo em Python precisa da chave SECRETA (sb_secret_...), que fica em "
            "Supabase → Project Settings → API Keys. A chave pública é só para o site."
        )

    # Converte JOGO_ID para inteiro caso seja numérico (ex: ID serial no banco),
    # ou mantém como string caso a equipe utilize UUID na tabela 'jogos'.
    jogo_id: int | str = int(jogo_id_raw) if jogo_id_raw.isdigit() else jogo_id_raw

    return AppConfig(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        jogo_id=jogo_id,
    )
