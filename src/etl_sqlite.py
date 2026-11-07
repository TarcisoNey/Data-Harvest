"""Pipeline ETL - Data Harvest (conjunto Downtime).

Lê o CSV limpo do Downtime (gerado por src/downtime.py), valida os dados e
carrega no banco SQLite oficial, seguindo o schema de sql/schema_sqlite.sql:

    assembly_lines (1) ──< machines (1) ──< machine_downtime_logs (N)

A carga é idempotente: rodar de novo com o mesmo CSV não duplica registros,
e um CSV diferente do que já está no banco cancela a carga sem sobrescrever.

Uso (na raiz do repositório):
    python src/etl_sqlite.py [--downtime CSV] [--db BANCO]
"""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
CSV_DOWNTIME = RAIZ / "data/processed/downtime/clean_downtime.csv"
SCHEMA = RAIZ / "sql/schema_sqlite.sql"
BANCO = RAIZ / "data/sprint2_etl.db"

TABELAS_OFICIAIS = {"assembly_lines", "machines", "machine_downtime_logs"}
SENSORES = [
    "hydraulic_pressure", "coolant_pressure", "air_system_pressure",
    "coolant_temperature", "hydraulic_oil_temperature",
    "spindle_bearing_temperature", "spindle_vibration", "tool_vibration",
    "spindle_speed", "voltage", "torque", "cutting",
]
STATUS_VALIDOS = {"Machine_Failure", "No_Machine_Failure"}
COLUNAS_LOG = ["machine_id", "date", *SENSORES, "downtime_status"]


def ler_csv(caminho):
    if not caminho.is_file():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}. "
            "Rode antes o pipeline: python src/downtime.py"
        )
    df = pd.read_csv(caminho, encoding="utf-8-sig")
    if df.empty:
        raise ValueError(f"CSV vazio: {caminho}")
    print(f"Lido {caminho.name}: {len(df)} linhas")
    return df


def preparar_downtime(caminho):
    """Valida o CSV e devolve (linhas de montagem, máquinas, logs)."""
    df = ler_csv(caminho)

    obrigatorias = ["machine_id", "assembly_line_no", "date", *SENSORES, "downtime"]
    faltantes = sorted(set(obrigatorias) - set(df.columns))
    if faltantes:
        raise ValueError(f"Downtime: colunas ausentes: {faltantes}")
    if df[obrigatorias].isna().any().any():
        raise ValueError("Downtime: existem valores vazios")

    for coluna in ("machine_id", "assembly_line_no", "downtime"):
        df[coluna] = df[coluna].astype(str).str.strip()
    if df["machine_id"].eq("").any() or df["assembly_line_no"].eq("").any():
        raise ValueError("Downtime: identificador vazio")

    invalidos = set(df["downtime"]) - STATUS_VALIDOS
    if invalidos:
        raise ValueError(f"Downtime: status inválidos: {sorted(invalidos)}")

    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.strftime("%Y-%m-%d")
    for coluna in SENSORES:
        df[coluna] = pd.to_numeric(df[coluna], errors="raise").astype(float)

    pares = (
        df[["machine_id", "assembly_line_no"]]
        .drop_duplicates()
        .sort_values("machine_id")
    )
    if pares["machine_id"].duplicated().any():
        raise ValueError("Downtime: mesma máquina vinculada a linhas diferentes")

    df = df.rename(columns={"downtime": "downtime_status"})
    logs = list(df[COLUNAS_LOG].itertuples(index=False, name=None))
    maquinas = list(pares.itertuples(index=False, name=None))
    linhas = sorted(set(pares["assembly_line_no"]))
    return linhas, maquinas, logs


def preparar_banco(conn, caminho_banco):
    conn.execute("PRAGMA foreign_keys = ON")
    existentes = {
        nome for (nome,) in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if not existentes:
        # O schema possui DROP TABLE: só é aplicado em banco vazio.
        if not SCHEMA.is_file():
            raise FileNotFoundError(f"Schema não encontrado: {SCHEMA}")
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("PRAGMA foreign_keys = ON")
        print(f"Schema oficial criado em banco vazio: {caminho_banco}")
    elif existentes != TABELAS_OFICIAIS:
        raise ValueError(
            f"Banco já possui tabelas incompatíveis: {sorted(existentes)}. "
            "Ele não será apagado. Use um banco vazio ou o da carga anterior."
        )


def conferir_ou_inserir(conn, tabela, colunas, linhas, ordem):
    """Insere se a tabela estiver vazia; se não, exige que os dados sejam iguais."""
    linhas = list(linhas)
    colunas_sql = ", ".join(colunas)
    existentes = conn.execute(
        f"SELECT {colunas_sql} FROM {tabela} ORDER BY {ordem}"
    ).fetchall()
    if existentes:
        if existentes != linhas:
            raise ValueError(
                f"{tabela}: dados existentes diferentes do CSV. "
                "A carga foi cancelada para evitar duplicação ou sobrescrita."
            )
        return 0
    marcadores = ", ".join("?" for _ in colunas)
    conn.executemany(
        f"INSERT INTO {tabela} ({colunas_sql}) VALUES ({marcadores})", linhas
    )
    return len(linhas)


def carregar(conn, linhas, maquinas, logs):
    """Carrega os dados já validados em uma transação. Devolve o nº de logs novos."""
    with conn:
        for nome in linhas:
            conn.execute(
                "INSERT OR IGNORE INTO assembly_lines (name) VALUES (?)", (nome,)
            )
        ids_linhas = dict(conn.execute("SELECT name, id FROM assembly_lines"))

        for maquina, nome_linha in maquinas:
            conn.execute(
                "INSERT OR IGNORE INTO machines (id, assembly_line_id) VALUES (?, ?)",
                (maquina, ids_linhas[nome_linha]),
            )
        mapa_maquinas = dict(conn.execute(
            "SELECT machines.id, assembly_lines.name "
            "FROM machines JOIN assembly_lines "
            "ON machines.assembly_line_id = assembly_lines.id"
        ))
        if any(mapa_maquinas.get(m) != l for m, l in maquinas):
            raise ValueError("Downtime: máquina já existe vinculada a outra linha")

        novos_logs = conferir_ou_inserir(
            conn, "machine_downtime_logs", COLUNAS_LOG, logs, "id"
        )

        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite: existem violações de chaves estrangeiras")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite: falha na verificação de integridade")
    return novos_logs


def carregar_csv(caminho_downtime=CSV_DOWNTIME, caminho_banco=BANCO):
    linhas, maquinas, logs = preparar_downtime(Path(caminho_downtime))

    caminho_banco = Path(caminho_banco)
    caminho_banco.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(caminho_banco)) as conn:
        preparar_banco(conn, caminho_banco)
        novos_logs = carregar(conn, linhas, maquinas, logs)

        print("\nCarga ETL concluída com sucesso!")
        for tabela in sorted(TABELAS_OFICIAIS):
            qtd = conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            print(f"{tabela}: {qtd}")
        print(f"Novos logs de Downtime: {novos_logs}")
        print("Integridade do SQLite: OK")
        print(f"Banco: {caminho_banco}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downtime", type=Path, default=CSV_DOWNTIME)
    parser.add_argument("--db", type=Path, default=BANCO)
    args = parser.parse_args()
    carregar_csv(args.downtime, args.db)


if __name__ == "__main__":
    main()
