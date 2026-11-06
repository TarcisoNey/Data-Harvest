
import sqlite3
from pathlib import Path

# Banco gerado pelo pipeline ETL da Sprint 2
RAIZ = Path(__file__).resolve().parent
BANCO = RAIZ / "data" / "sprint2_etl.db"

if not BANCO.is_file():
    raise FileNotFoundError(
        f"Banco não encontrado: {BANCO}\n"
        "Execute primeiro o pipeline ETL."
    )

# Abrir o banco sem criar arquivos novos
conexao = sqlite3.connect(
    BANCO.as_uri() + "?mode=ro",
    uri=True
)

try:
    tabelas = conexao.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()

    print("REGISTROS DO BANCO SQLITE\n")

    for (nome,) in tabelas:
        nome_sql = nome.replace('"', '""')
        quantidade = conexao.execute(
            f'SELECT COUNT(*) FROM "{nome_sql}"'
        ).fetchone()[0]

        print(f"{nome}: {quantidade} registros")

    erros = conexao.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    integridade = conexao.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    print("\nErros de chaves estrangeiras:", erros)
    print("Integridade do banco:", integridade)

finally:
    conexao.close()
