"""
Valida as chaves primárias e estrangeiras do schema SQLite (sql/schema_sqlite.sql)
contra o modelo relacional de src/database.py.

Cria um banco em memória, aplica o schema, carrega o CSV limpo do Downtime com
o mesmo código do ETL (src/etl_sqlite.py) e executa:
  1. Checagem estrutural (PKs, FKs, NOT NULL, UNIQUE, índices) via PRAGMAs;
  2. Conferência da carga contra o CSV + PRAGMA foreign_key_check;
  3. Testes negativos: operações que DEVEM ser rejeitadas pelo banco;
  4. Cascatas (ON UPDATE CASCADE).

Uso (na raiz do repositório):
    python sql/validate_schema.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import etl_sqlite as etl  # noqa: E402

# tabela -> (PK, {coluna_fk: (tabela_ref, coluna_ref)})
EXPECTED = {
    "assembly_lines": (["id"], {}),
    "machines": (["id"], {"assembly_line_id": ("assembly_lines", "id")}),
    "machine_downtime_logs": (["id"], {"machine_id": ("machines", "id")}),
}

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'OK ' if ok else 'ERRO'}] {name}" + (f" — {detail}" if detail else ""))


def must_fail(conn, name, sql, params=()):
    conn.execute("SAVEPOINT t")
    try:
        conn.execute(sql, params)
        check(name, False, "o banco aceitou uma operação inválida")
    except sqlite3.IntegrityError as e:
        check(name, True, f"rejeitado: {e}")
    finally:
        conn.execute("ROLLBACK TO t")
        conn.execute("RELEASE t")


def count(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def main():
    conn = sqlite3.connect(":memory:")
    etl.preparar_banco(conn, ":memory:")

    print("\n1) Estrutura")
    check("foreign_keys ativado", count(conn, "PRAGMA foreign_keys") == 1)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                         "AND name NOT LIKE 'sqlite_%'")}
    check("tabelas = modelo de src/database.py", tables == set(EXPECTED), str(sorted(tables)))
    for table, (pk, fks) in EXPECTED.items():
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        got_pk = [c[1] for c in sorted(cols, key=lambda c: c[5]) if c[5] > 0]
        check(f"{table}: PK {pk}", got_pk == pk, "" if got_pk == pk else f"encontrado {got_pk}")
        got_fks = {r[3]: (r[2], r[4]) for r in conn.execute(f"PRAGMA foreign_key_list({table})")}
        if fks or got_fks:
            check(f"{table}: FKs {fks}", got_fks == fks, "" if got_fks == fks else f"encontrado {got_fks}")
        notnull = {c[1]: c[3] for c in cols}
        indexed = {
            c[2]
            for i in conn.execute(f"PRAGMA index_list({table})")
            for c in conn.execute(f"PRAGMA index_info({i[1]})")
        }
        for col in fks:
            check(f"{table}.{col} NOT NULL e indexada", notnull[col] == 1 and col in indexed)
    uniques = [
        [c[2] for c in conn.execute(f"PRAGMA index_info({i[1]})")]
        for i in conn.execute("PRAGMA index_list(assembly_lines)") if i[2]
    ]
    check("assembly_lines.name UNIQUE", ["name"] in uniques)

    print(f"\n2) Carga de {etl.CSV_DOWNTIME.relative_to(ROOT)}")
    linhas, maquinas, logs = etl.preparar_downtime(etl.CSV_DOWNTIME)
    etl.carregar(conn, linhas, maquinas, logs)
    counts = {t: count(conn, f"SELECT COUNT(*) FROM {t}") for t in EXPECTED}
    print("  " + ", ".join(f"{t}={n}" for t, n in counts.items()))
    check("todas as linhas do CSV carregadas", counts["machine_downtime_logs"] == len(logs))
    check("uma máquina por linha de montagem no CSV", counts["machines"] == len(maquinas))
    falhas_csv = sum(1 for log in logs if log[-1] == "Machine_Failure")
    falhas_db = count(conn, "SELECT COUNT(*) FROM machine_downtime_logs "
                            "WHERE downtime_status = 'Machine_Failure'")
    check("total de falhas confere com o CSV", falhas_db == falhas_csv, f"{falhas_db}")
    orphans = conn.execute("PRAGMA foreign_key_check").fetchall()
    check("PRAGMA foreign_key_check sem órfãos", not orphans, f"{len(orphans)} violações" if orphans else "")
    check("PRAGMA integrity_check", count(conn, "PRAGMA integrity_check") == "ok")
    joined = count(conn, """
        SELECT COUNT(*) FROM machine_downtime_logs l
        JOIN machines m ON m.id = l.machine_id
        JOIN assembly_lines a ON a.id = m.assembly_line_id
    """)
    check("JOIN logs→machines→assembly_lines preserva todos os registros", joined == len(logs))
    check("carga de novo não duplica (idempotente)", etl.carregar(conn, linhas, maquinas, logs) == 0)

    print("\n3) Testes negativos (devem ser rejeitados)")
    maquina = maquinas[0][0]
    must_fail(conn, "PK duplicada em assembly_lines",
              "INSERT INTO assembly_lines (id, name) VALUES (1, 'Outra')")
    must_fail(conn, "name duplicado em assembly_lines",
              "INSERT INTO assembly_lines (name) VALUES (?)", (linhas[0],))
    must_fail(conn, "PK duplicada em machines",
              "INSERT INTO machines (id, assembly_line_id) VALUES (?, 1)", (maquina,))
    must_fail(conn, "machine com linha inexistente",
              "INSERT INTO machines (id, assembly_line_id) VALUES ('X-999', 999)")
    must_fail(conn, "machine sem linha (NULL)",
              "INSERT INTO machines (id, assembly_line_id) VALUES ('X-998', NULL)")
    must_fail(conn, "log de máquina inexistente",
              "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
              "VALUES ('X-999', '2022-01-01', 'Machine_Failure')")
    must_fail(conn, "log sem máquina (NULL)",
              "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
              "VALUES (NULL, '2022-01-01', 'Machine_Failure')")
    must_fail(conn, "downtime_status fora do domínio",
              "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
              "VALUES (?, '2022-01-01', 'talvez')", (maquina,))
    must_fail(conn, "DELETE de linha com máquinas (RESTRICT)",
              "DELETE FROM assembly_lines WHERE id = 1")
    must_fail(conn, "DELETE de máquina com logs (RESTRICT)",
              "DELETE FROM machines WHERE id = ?", (maquina,))

    print("\n4) Cascatas")
    conn.execute("SAVEPOINT c")
    conn.execute("UPDATE machines SET id = 'RENOMEADA' WHERE id = ?", (maquina,))
    n = count(conn, "SELECT COUNT(*) FROM machine_downtime_logs WHERE machine_id = 'RENOMEADA'")
    check("UPDATE do id da máquina propaga para os logs (CASCADE)", n > 0, f"{n} logs")
    conn.execute("ROLLBACK TO c")
    conn.execute("RELEASE c")
    conn.close()

    ok = all(results)
    print(f"\n{sum(results)}/{len(results)} verificações passaram — {'SCHEMA VÁLIDO' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
