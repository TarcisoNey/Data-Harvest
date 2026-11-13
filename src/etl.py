"""Pipeline ETL - Data Harvest (conjunto Downtime) -> PostgreSQL.

Lê o CSV limpo do Downtime (gerado por src/downtime.py), valida os dados e
carrega no PostgreSQL, nas tabelas definidas em src/database.py:

    assembly_lines (1) ──< machines (1) ──< machine_downtime_logs (N)

A carga é idempotente: rodar de novo com o mesmo CSV não duplica registros,
e um CSV diferente do que já está no banco cancela a carga sem sobrescrever
(use --recriar para apagar e carregar de novo).

Uso (na raiz do repositório, com o Postgres do docker compose rodando):
    python src/etl.py                 # cria as tabelas se preciso e carrega
    python src/etl.py --recriar       # apaga as tabelas e carrega do zero
    python src/etl.py --csv OUTRO.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import (STATUS_VALIDOS, AssemblyLine, Base, Machine,  # noqa: E402
                      MachineDowntimeLog, descricao_conexao, engine)

CSV_DOWNTIME = RAIZ / "data/processed/downtime/clean_downtime.csv"
SENSORES = [
    "hydraulic_pressure", "coolant_pressure", "air_system_pressure",
    "coolant_temperature", "hydraulic_oil_temperature",
    "spindle_bearing_temperature", "spindle_vibration", "tool_vibration",
    "spindle_speed", "voltage", "torque", "cutting",
]
COLUNAS_LOG = ["machine_id", "date", *SENSORES, "downtime_status"]


# ---------------------------------------------------------------------------
# Extração e validação
# ---------------------------------------------------------------------------
def ler_csv(caminho):
    if not caminho.is_file():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}. Rode antes o pipeline: python src/downtime.py"
        )
    df = pd.read_csv(caminho, encoding="utf-8-sig")
    if df.empty:
        raise ValueError(f"CSV vazio: {caminho}")
    print(f"Lido {caminho.name}: {len(df)} linhas")
    return df


def preparar_downtime(caminho):
    """Valida o CSV e devolve (linhas de montagem, máquinas, logs)."""
    df = ler_csv(Path(caminho))

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

    invalidos = set(df["downtime"]) - set(STATUS_VALIDOS)
    if invalidos:
        raise ValueError(f"Downtime: status inválidos: {sorted(invalidos)}")

    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.normalize()
    for coluna in SENSORES:
        df[coluna] = pd.to_numeric(df[coluna], errors="raise").astype(float)

    pares = df[["machine_id", "assembly_line_no"]].drop_duplicates().sort_values("machine_id")
    if pares["machine_id"].duplicated().any():
        raise ValueError("Downtime: mesma máquina vinculada a linhas diferentes")

    df = df.rename(columns={"downtime": "downtime_status"})
    logs = [
        {**r, "date": r["date"].to_pydatetime()}
        for r in df[COLUNAS_LOG].to_dict("records")
    ]
    maquinas = list(pares.itertuples(index=False, name=None))
    linhas = sorted(set(pares["assembly_line_no"]))
    return linhas, maquinas, logs


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def _chave(log):
    """Representação comparável de um log (para conferir CSV x banco)."""
    return tuple(log[c].date() if c == "date" else log[c] for c in COLUNAS_LOG)


def carregar(linhas, maquinas, logs, recriar=False):
    """Carrega os dados já validados numa transação. Devolve o nº de logs novos."""
    if recriar:
        Base.metadata.drop_all(bind=engine)
        print("Tabelas apagadas.")
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(insert(AssemblyLine).on_conflict_do_nothing(index_elements=["name"]),
                     [{"name": n} for n in linhas])
        ids_linhas = dict(conn.execute(select(AssemblyLine.name, AssemblyLine.id)).all())

        conn.execute(insert(Machine).on_conflict_do_nothing(index_elements=["id"]),
                     [{"id": m, "assembly_line_id": ids_linhas[l]} for m, l in maquinas])
        mapa = dict(conn.execute(
            select(Machine.id, AssemblyLine.name).join(AssemblyLine)).all())
        if any(mapa.get(m) != l for m, l in maquinas):
            raise ValueError("Downtime: máquina já existe vinculada a outra linha")

        existentes = conn.execute(
            select(*[MachineDowntimeLog.__table__.c[c] for c in COLUNAS_LOG])
            .order_by(MachineDowntimeLog.id)
        ).mappings().all()
        if existentes:
            if [_chave(e) for e in existentes] != [_chave(l) for l in logs]:
                raise ValueError(
                    "machine_downtime_logs: dados existentes diferentes do CSV. A carga foi "
                    "cancelada para evitar duplicação ou sobrescrita. Use --recriar."
                )
            return 0
        conn.execute(insert(MachineDowntimeLog), logs)
        return len(logs)


def verificar_integridade():
    """Conta registros órfãos (FK quebrada). O Postgres impede, mas confere."""
    with engine.connect() as conn:
        orfaos = conn.execute(text(
            "SELECT (SELECT COUNT(*) FROM machines m LEFT JOIN assembly_lines a "
            "        ON a.id = m.assembly_line_id WHERE a.id IS NULL) + "
            "       (SELECT COUNT(*) FROM machine_downtime_logs l LEFT JOIN machines m "
            "        ON m.id = l.machine_id WHERE m.id IS NULL)")).scalar()
        contagens = {t.__tablename__: conn.execute(select(func.count()).select_from(t)).scalar()
                     for t in (AssemblyLine, Machine, MachineDowntimeLog)}
    return orfaos, contagens


def executar(caminho_csv=CSV_DOWNTIME, recriar=False):
    linhas, maquinas, logs = preparar_downtime(caminho_csv)
    novos = carregar(linhas, maquinas, logs, recriar)
    orfaos, contagens = verificar_integridade()
    if orfaos:
        raise ValueError(f"PostgreSQL: {orfaos} registros com chave estrangeira quebrada")

    print("\nCarga ETL concluída com sucesso!")
    for tabela, qtd in sorted(contagens.items()):
        print(f"{tabela}: {qtd}")
    print(f"Novos logs de Downtime: {novos}")
    print("Integridade do PostgreSQL: OK")
    print(f"Banco: {descricao_conexao()}")
    return novos


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=CSV_DOWNTIME)
    parser.add_argument("--recriar", action="store_true",
                        help="apaga e recria as tabelas antes de carregar")
    args = parser.parse_args()
    executar(args.csv, args.recriar)


if __name__ == "__main__":
    main()
