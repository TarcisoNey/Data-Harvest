
import sqlite3

# Conectar ao banco criado pelo ETL
conexao = sqlite3.connect("data/data_harvest.db")

# Buscar as tabelas existentes
tabelas = conexao.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    AND name NOT LIKE 'sqlite_%'
    ORDER BY name
""").fetchall()

# Mostrar a quantidade de registros de cada tabela
for tabela in tabelas:
    nome = tabela[0]

    quantidade = conexao.execute(
        f'SELECT COUNT(*) FROM "{nome}"'
    ).fetchone()[0]

    print(nome, ":", quantidade, "registros")

conexao.close()
