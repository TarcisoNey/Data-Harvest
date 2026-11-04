"""
Valida as chaves primárias e estrangeiras do schema SQLite (sql/schema_sqlite.sql).

Cria um banco em memória, aplica o schema, carrega os CSVs brutos com o mesmo
código de src/load_sqlite.py e executa:
  1. Checagem estrutural (PKs, FKs, NOT NULL, índices) via PRAGMAs;
  2. Conferência da carga contra os CSVs + PRAGMA foreign_key_check;
  3. Testes negativos: operações que DEVEM ser rejeitadas pelo banco.

Uso (na raiz do repositório):
    python sql/validate_schema.py
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import load_sqlite as loader  # noqa: E402

# tabela -> (PK, {coluna_fk: (tabela_ref, coluna_ref)})
EXPECTED = {
    # AI4I 2020
    "product_types": (["code"], {}),
    "failure_modes": (["code"], {}),
    "process_readings": (["udi"], {"product_type_code": ("product_types", "code")}),
    "reading_failure_modes": (
        ["reading_udi", "failure_mode_code"],
        {"reading_udi": ("process_readings", "udi"),
         "failure_mode_code": ("failure_modes", "code")},
    ),
    # Downtime (src/database.py)
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
    loader.apply_schema(conn)

    print("1) Estrutura")
    check("foreign_keys ativado", count(conn, "PRAGMA foreign_keys") == 1)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                         "AND name NOT LIKE 'sqlite_%'")}
    check("tabelas esperadas", tables == set(EXPECTED), f"{len(tables)} tabelas")
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
            in_pk = col in pk
            check(f"{table}.{col} NOT NULL e indexada",
                  (notnull[col] == 1 or in_pk) and (col in indexed or pk[0] == col))

    print("\n2) Carga dos CSVs brutos")
    loader.load_ai4i(conn)
    loader.load_downtime(conn)
    ai4i = pd.read_csv(loader.AI4I_CSV, encoding="utf-8-sig")
    modes = ai4i[loader.AI4I_MODES]

    check("process_readings = linhas do AI4I",
          count(conn, "SELECT COUNT(*) FROM process_readings") == len(ai4i), f"{len(ai4i)}")
    check("reading_failure_modes = soma das colunas de modo",
          count(conn, "SELECT COUNT(*) FROM reading_failure_modes") == int(modes.values.sum()),
          f"{int(modes.values.sum())}")
    db_modes = dict(conn.execute("SELECT failure_mode_code, COUNT(*) FROM reading_failure_modes GROUP BY 1"))
    check("contagem por modo de falha confere", db_modes == {m: int(modes[m].sum()) for m in loader.AI4I_MODES},
          str(db_modes))
    db_fail = count(conn, "SELECT SUM(machine_failure) FROM process_readings")
    check("total de machine_failure confere", db_fail == int(ai4i["Machine failure"].sum()), f"{db_fail}")
    check("prefixo do product_id = tipo do produto",
          count(conn, "SELECT COUNT(*) FROM process_readings WHERE substr(product_id,1,1) <> product_type_code") == 0)
    check("machine_downtime_logs = 2500 linhas",
          count(conn, "SELECT COUNT(*) FROM machine_downtime_logs") == 2500)
    orphans = conn.execute("PRAGMA foreign_key_check").fetchall()
    check("PRAGMA foreign_key_check sem órfãos", not orphans, f"{len(orphans)} violações" if orphans else "")
    check("PRAGMA integrity_check", conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok")

    print("\n3) Testes negativos (devem ser rejeitados)")
    # AI4I
    must_fail(conn, "udi duplicado", "INSERT INTO process_readings SELECT * FROM process_readings LIMIT 1")
    must_fail(conn, "product_id duplicado",
              "INSERT INTO process_readings (udi, product_id, product_type_code, air_temperature, "
              "process_temperature, rotational_speed, torque, tool_wear, machine_failure) "
              "VALUES (99999, 'M14860', 'M', 300, 310, 1500, 40, 0, 0)")
    must_fail(conn, "leitura com tipo inexistente",
              "INSERT INTO process_readings (udi, product_id, product_type_code, air_temperature, "
              "process_temperature, rotational_speed, torque, tool_wear, machine_failure) "
              "VALUES (99999, 'X1', 'X', 300, 310, 1500, 40, 0, 0)")
    must_fail(conn, "machine_failure fora de 0/1",
              "INSERT INTO process_readings (udi, product_id, product_type_code, air_temperature, "
              "process_temperature, rotational_speed, torque, tool_wear, machine_failure) "
              "VALUES (99999, 'L1', 'L', 300, 310, 1500, 40, 0, 2)")
    must_fail(conn, "modo de falha em leitura inexistente",
              "INSERT INTO reading_failure_modes VALUES (99999, 'TWF')")
    must_fail(conn, "modo de falha inexistente",
              "INSERT INTO reading_failure_modes VALUES (1, 'XYZ')")
    udi_twf = count(conn, "SELECT reading_udi FROM reading_failure_modes WHERE failure_mode_code='TWF' LIMIT 1")
    must_fail(conn, "mesmo modo duas vezes na mesma leitura (PK composta)",
              "INSERT INTO reading_failure_modes VALUES (?, 'TWF')", (udi_twf,))
    must_fail(conn, "DELETE de tipo com leituras (RESTRICT)", "DELETE FROM product_types WHERE code='L'")
    must_fail(conn, "DELETE de modo em uso (RESTRICT)", "DELETE FROM failure_modes WHERE code='TWF'")
    # Downtime
    must_fail(conn, "assembly_lines.name duplicado", "INSERT INTO assembly_lines (name) VALUES ('Shopfloor-L1')")
    must_fail(conn, "machine com linha inexistente",
              "INSERT INTO machines (id, assembly_line_id) VALUES ('X-999', 999)")
    must_fail(conn, "log de máquina inexistente",
              "INSERT INTO machine_downtime_logs (machine_id, date, downtime_status) "
              "VALUES ('X-999', '2022-01-01', 'Machine_Failure')")
    must_fail(conn, "DELETE de máquina com logs (RESTRICT)",
              "DELETE FROM machines WHERE id = 'Makino-L1-Unit1-2013'")

    print("\n4) Cascatas")
    conn.execute("SAVEPOINT c")
    conn.execute("DELETE FROM process_readings WHERE udi = ?", (udi_twf,))
    check("DELETE de leitura apaga seus modos de falha (CASCADE)",
          count(conn, "SELECT COUNT(*) FROM reading_failure_modes WHERE reading_udi = ?", (udi_twf,)) == 0)
    conn.execute("UPDATE machines SET id = 'RENOMEADA' WHERE id = 'Makino-L1-Unit1-2013'")
    n = count(conn, "SELECT COUNT(*) FROM machine_downtime_logs WHERE machine_id = 'RENOMEADA'")
    check("UPDATE do id da máquina propaga para os logs (CASCADE)", n > 0, f"{n} logs")
    conn.execute("ROLLBACK TO c")
    conn.execute("RELEASE c")

    ok = all(results)
    print(f"\n{sum(results)}/{len(results)} verificações passaram — {'SCHEMA VÁLIDO' if ok else 'HÁ FALHAS'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
