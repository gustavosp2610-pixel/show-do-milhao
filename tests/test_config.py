"""Testes da validação do .env (sem rede e sem credenciais reais)."""
import base64
import json
import os
import sys
import types
import unittest
from unittest.mock import patch

# O CI não instala dependências: simula o python-dotenv para importar config.py.
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *a, **k: None))

from config import ConfigError, carregar_configuracao  # noqa: E402


def jwt_falso(role: str) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{corpo}.assinatura"


def ambiente(chave: str) -> dict:
    return {"SUPABASE_URL": "https://exemplo.supabase.co", "SUPABASE_KEY": chave, "JOGO_ID": "1"}


class TesteConfiguracao(unittest.TestCase):
    def test_chave_secreta_aceita(self):
        with patch.dict(os.environ, ambiente("sb_secret_abc123"), clear=True):
            config = carregar_configuracao()
        self.assertEqual(config.jogo_id, 1)

    def test_service_role_antiga_aceita(self):
        with patch.dict(os.environ, ambiente(jwt_falso("service_role")), clear=True):
            self.assertEqual(carregar_configuracao().supabase_key, jwt_falso("service_role"))

    def test_chave_publicavel_recusada(self):
        with patch.dict(os.environ, ambiente("sb_publishable_abc123"), clear=True):
            with self.assertRaisesRegex(ConfigError, "SECRETA"):
                carregar_configuracao()

    def test_chave_anon_antiga_recusada(self):
        with patch.dict(os.environ, ambiente(jwt_falso("anon")), clear=True):
            with self.assertRaisesRegex(ConfigError, "SECRETA"):
                carregar_configuracao()

    def test_valor_de_exemplo_conta_como_vazio(self):
        chave = "sb_secret_COLOQUE_SUA_CHAVE_APENAS_NO_SERVIDOR"
        with patch.dict(os.environ, ambiente(chave), clear=True):
            with self.assertRaisesRegex(ConfigError, "SUPABASE_KEY"):
                carregar_configuracao()


if __name__ == "__main__":
    unittest.main()
