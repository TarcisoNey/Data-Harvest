"""
Popula o banco SQLite a partir dos CSVs brutos, sem inserts manuais.

  - AI4I 2020: data/raw/ai4i2020/ai4i2020.csv
        -> process_readings + reading_failure_modes
           (product_types e failure_modes já vêm preenchidas pelo schema)
  - Downtime:  data/raw/downtime/machine_downtime.csv
        -> assembly_lines + machines + machine_downtime_logs
           (limpo com a mesma função clean() do pipeline src/downtime.py)

O schema (sql/schema_sqlite.sql) é reaplicado a cada execução, então o banco
é recriado do zero. Cada conjunto é carregado em uma transação: se algo falhar,
nada fica pela metade.

Uso (na raiz do repositório):
    python src/load_sqlite.py [saida.db]
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from downtime import clean as clean_downtime, to_snake

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "sql" / "schema_sqlite.sql"
AI4I_CSV = ROOT / "data/raw/ai4i2020/ai4i2020.csv"
DOWNTIME_CSV = ROOT / "data/raw/downtime/machine_downtime.csv"

AI4I_MODES = ["TWF", "HDF", "PWF", "OSF", "RNF"]
AI4I_COLS = [
    "udi", "product_id", "product_type_code", "air_temperature", "process_temperature",
    "rotational_speed", "torque", "tool_wear", "machine_failure",
]
DOWNTIME_SENSORS = [
    "hydraulic_pressure", "coolant_pressure", "air_system_pressure",
    "coolant_temperature", "hydraulic_oil_temperature", "spindle_bearing_temperature",
    "spindle_vibration", "tool_vibration", "spindle_speed", "voltage", "torque", "cutting",
]


def apply_schema(conn):
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")


def insert(conn, table, cols, rows):
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows
    )


def load_ai4i(conn, csv=AI4I_CSV):
    df = pd.read_csv(csv, encoding="utf-8-sig").rename(columns=to_snake)
    df = df.rename(columns={"type": "product_type_code"})
    print(f"AI4I: {len(df)} linhas lidas de {csv.name}")

    readings = df[AI4I_COLS].astype(object).itertuples(index=False, name=None)
    modes = df.melt(id_vars="udi", value_vars=[m.lower() for m in AI4I_MODES],
                    var_name="mode", value_name="flag")
    modes = modes[modes["flag"] == 1]
    mode_rows = [(int(u), m.upper()) for u, m in modes[["udi", "mode"]].itertuples(index=False)]

    with conn:
        insert(conn, "process_readings", AI4I_COLS, readings)
        insert(conn, "reading_failure_modes", ["reading_udi", "failure_mode_code"], mode_rows)


def load_downtime(conn, csv=DOWNTIME_CSV):
    print(f"Downtime: limpando {csv.name}")
    df = clean_downtime(pd.read_csv(csv))
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    pares = df[["machine_id", "assembly_line_no"]].drop_duplicates()
    if pares["machine_id"].duplicated().any():
        raise ValueError("Há máquina associada a mais de uma linha de montagem no CSV.")

    with conn:
        insert(conn, "assembly_lines", ["name"],
               [(n,) for n in sorted(pares["assembly_line_no"].unique())])
        line_id = dict(conn.execute("SELECT name, id FROM assembly_lines"))
        insert(conn, "machines", ["id", "assembly_line_id"],
               [(m, line_id[l]) for m, l in pares.sort_values("machine_id").itertuples(index=False)])
        cols = ["machine_id", "date", *DOWNTIME_SENSORS, "downtime_status"]
        logs = df.rename(columns={"downtime": "downtime_status"})[cols]
        insert(conn, "machine_downtime_logs", cols, logs.itertuples(index=False, name=None))


def build(conn):
    apply_schema(conn)
    load_ai4i(conn)
    load_downtime(conn)
    orfaos = conn.execute("PRAGMA foreign_key_check").fetchall()
    if orfaos:
        raise ValueError(f"{len(orfaos)} registros violam chaves estrangeiras.")


def main():
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/data_harvest.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        build(conn)
        print()
        for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                 "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            print(f"{t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} registros")
        print(f"\nBanco gerado em {db}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
