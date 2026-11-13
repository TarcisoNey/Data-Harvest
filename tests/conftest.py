"""Configuração dos testes.

Os testes que usam banco rodam num banco SEPARADO (padrão: data_harvest_test,
ou o nome em TEST_POSTGRES_DB), no mesmo servidor PostgreSQL do .env. Ele é
criado se não existir e recarregado do zero pelo ETL no início da sessão, então
o banco de trabalho (POSTGRES_DB) nunca é tocado.

Sem PostgreSQL rodando, os testes de banco são pulados (os demais rodam).
Suba o banco com:  docker compose up -d db
"""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
BANCO_TESTE = os.environ.get("TEST_POSTGRES_DB", "data_harvest_test")

# Precisa acontecer ANTES de qualquer import de src/database.py
# (o load_dotenv de lá não sobrescreve variáveis já definidas).
os.environ["POSTGRES_DB"] = BANCO_TESTE
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))


def _criar_banco_de_teste():
    import psycopg2
    from psycopg2 import sql

    import database

    conn = psycopg2.connect(dbname="postgres", user=database.USER, password=database.PASSWORD,
                            host=database.HOST, port=database.PORT, connect_timeout=5)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (BANCO_TESTE,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(BANCO_TESTE)))
    finally:
        conn.close()


@pytest.fixture(scope="session")
def banco():
    """Banco de teste criado e carregado pelo ETL. Pula se o Postgres não responder."""
    try:
        import database
        import etl

        if not database.PASSWORD:
            raise RuntimeError("POSTGRES_PASSWORD não definida (.env)")
        _criar_banco_de_teste()
        etl.executar(recriar=True)
    except Exception as erro:  # sem servidor, sem senha, sem permissão...
        pytest.skip(f"PostgreSQL indisponível para os testes ({erro}). "
                    "Suba com: docker compose up -d db")
    return database


@pytest.fixture
def conn(banco):
    """Conexão de escrita numa transação desfeita ao fim do teste."""
    c = banco.get_conn()
    try:
        yield c
    finally:
        c.rollback()
        c.close()
