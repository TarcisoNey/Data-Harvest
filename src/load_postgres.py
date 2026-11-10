"""
Carrega o CSV limpo do Downtime no PostgreSQL, nas tabelas de src/database.py:

    assembly_lines (1) ──< machines (1) ──< machine_downtime_logs (N)

Usa a mesma validação do ETL SQLite (src/etl_sqlite.py) e a conexão do .env
(POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DB_PORT).

Uso (na raiz do repositório, com o container do docker-compose rodando):
    python src/load_postgres.py             # carrega se as tabelas estiverem vazias
    python src/load_postgres.py --recriar   # apaga e recria as tabelas antes
"""
import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import func, insert, select

from database import AssemblyLine, Base, Machine, MachineDowntimeLog, SessionLocal, engine
from etl_sqlite import COLUNAS_LOG, CSV_DOWNTIME, preparar_downtime


def carregar(caminho_csv=CSV_DOWNTIME, recriar=False):
    linhas, maquinas, logs = preparar_downtime(Path(caminho_csv))

    if recriar:
        Base.metadata.drop_all(bind=engine)
        print("Tabelas apagadas.")
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session, session.begin():
        existentes = session.scalar(select(func.count()).select_from(MachineDowntimeLog))
        if existentes:
            if existentes == len(logs):
                print(f"Banco já carregado ({existentes} logs). Nada a fazer. "
                      "Use --recriar para carregar de novo.")
                return
            raise SystemExit(
                f"machine_downtime_logs já tem {existentes} registros e o CSV tem {len(logs)}. "
                "Use --recriar para apagar e carregar de novo."
            )

        session.execute(insert(AssemblyLine), [{"name": nome} for nome in linhas])
        ids_linhas = dict(session.execute(select(AssemblyLine.name, AssemblyLine.id)).all())
        session.execute(
            insert(Machine),
            [{"id": m, "assembly_line_id": ids_linhas[linha]} for m, linha in maquinas],
        )

        registros = [dict(zip(COLUNAS_LOG, log)) for log in logs]
        for r in registros:
            r["date"] = pd.Timestamp(r["date"]).to_pydatetime()
        session.execute(insert(MachineDowntimeLog), registros)

    with SessionLocal() as session:
        for modelo in (AssemblyLine, Machine, MachineDowntimeLog):
            qtd = session.scalar(select(func.count()).select_from(modelo))
            print(f"{modelo.__tablename__}: {qtd}")
    print("Carga no PostgreSQL concluída.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=CSV_DOWNTIME)
    parser.add_argument("--recriar", action="store_true",
                        help="apaga e recria as tabelas antes de carregar")
    args = parser.parse_args()
    carregar(args.csv, args.recriar)


if __name__ == "__main__":
    main()
