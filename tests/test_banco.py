"""Confere o banco PostgreSQL carregado pelo ETL e as regras do schema.

Substitui o antigo teste.py e o sql/validate_schema.py (que eram do SQLite).
Os testes de restrição tentam operações que o banco DEVE recusar; cada uma
roda num SAVEPOINT desfeito, e a transação inteira é desfeita no fim.

Uso (na raiz, com o Postgres rodando):  python -m pytest tests/test_banco.py -v
"""
import psycopg2
import pytest

ESPERADO = {"assembly_lines": 3, "machines": 3, "machine_downtime_logs": 2500}
MAQUINA = "Makino-L1-Unit1-2013"


def _um(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def test_contagens_por_tabela(conn):
    assert {t: _um(conn, f"SELECT COUNT(*) FROM {t}") for t in ESPERADO} == ESPERADO


def test_falhas_por_linha_batem_com_o_csv(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT a.name, COUNT(*) FROM machine_downtime_logs l
                       JOIN machines m ON m.id = l.machine_id
                       JOIN assembly_lines a ON a.id = m.assembly_line_id
                       WHERE l.downtime_status = 'Machine_Failure' GROUP BY 1""")
        assert dict(cur.fetchall()) == {"Shopfloor-L1": 454, "Shopfloor-L2": 396, "Shopfloor-L3": 415}


def test_sem_registros_orfaos(conn):
    assert _um(conn, """SELECT COUNT(*) FROM machine_downtime_logs l
                        LEFT JOIN machines m ON m.id = l.machine_id WHERE m.id IS NULL""") == 0


@pytest.mark.parametrize("descricao, sql, params", [
    ("nome de linha duplicado (UNIQUE)",
     "INSERT INTO assembly_lines (name) VALUES ('Shopfloor-L1')", ()),
    ("máquina com linha inexistente (FK)",
     "INSERT INTO machines (id, assembly_line_id) VALUES ('X', 999)", ()),
    ("máquina sem linha (NOT NULL)",
     "INSERT INTO machines (id, assembly_line_id) VALUES ('X', NULL)", ()),
    ("log de máquina inexistente (FK)",
     "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
     "VALUES ('nao-existe', '2022-01-01', 'Machine_Failure')", ()),
    ("log sem máquina (NOT NULL)",
     "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
     "VALUES (NULL, '2022-01-01', 'Machine_Failure')", ()),
    ("log sem data (NOT NULL)",
     "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
     "VALUES (%s, NULL, 'Machine_Failure')", (MAQUINA,)),
    ("downtime_status fora do domínio (CHECK)",
     "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
     "VALUES (%s, '2022-01-01', 'talvez')", (MAQUINA,)),
    ("apagar linha que tem máquinas (RESTRICT)",
     "DELETE FROM assembly_lines WHERE name = 'Shopfloor-L1'", ()),
    ("apagar máquina que tem logs (RESTRICT)",
     "DELETE FROM machines WHERE id = %s", (MAQUINA,)),
])
def test_banco_recusa_operacao_invalida(conn, descricao, sql, params):
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT t")
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute(sql, params)
        cur.execute("ROLLBACK TO SAVEPOINT t")


def test_renomear_maquina_propaga_para_os_logs(conn):
    antes = _um(conn, "SELECT COUNT(*) FROM machine_downtime_logs WHERE machine_id = %s", (MAQUINA,))
    with conn.cursor() as cur:
        cur.execute("UPDATE machines SET id = 'RENOMEADA' WHERE id = %s", (MAQUINA,))
    assert _um(conn, "SELECT COUNT(*) FROM machine_downtime_logs WHERE machine_id = 'RENOMEADA'") == antes > 0


def test_schema_postgres_sql_esta_atualizado(banco):
    """sql/schema_postgres.sql é gerado de src/database.py; mudou o modelo, regenere."""
    from pathlib import Path

    arquivo = Path(__file__).resolve().parents[1] / "sql/schema_postgres.sql"
    assert arquivo.read_text(encoding="utf-8").strip() == banco.ddl().strip(), (
        "Rode: python src/database.py --ddl > sql/schema_postgres.sql")
