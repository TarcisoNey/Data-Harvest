"""Conexão com o PostgreSQL e modelos das tabelas do conjunto Downtime.

Este arquivo é a ÚNICA definição do schema do projeto:

    assembly_lines (1) ──< machines (1) ──< machine_downtime_logs (N)

A conexão vem do .env da raiz do repositório (veja .env.example):
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DB_HOST e DB_PORT.

Uso:
    python src/database.py          # cria as tabelas, se ainda não existirem
    python src/database.py --ddl    # imprime o SQL (CREATE TABLE) do schema
"""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import (CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String,
                        create_engine)
from sqlalchemy.orm import declarative_base, sessionmaker

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

USER = os.getenv("POSTGRES_USER", "postgres")
PASSWORD = os.getenv("POSTGRES_PASSWORD")
HOST = os.getenv("DB_HOST", "localhost")
PORT = os.getenv("DB_PORT", "5432")
DB = os.getenv("POSTGRES_DB", "data_harvest_db")

STATUS_VALIDOS = ("Machine_Failure", "No_Machine_Failure")


def descricao_conexao():
    return f"postgresql://{USER}@{HOST}:{PORT}/{DB}"


def get_conn(somente_leitura=False):
    if not PASSWORD:
        raise RuntimeError("POSTGRES_PASSWORD não definida. Copie .env.example para .env e preencha.")
    # Parâmetros separados (em vez de uma string DSN) aceitam senhas com
    # espaços ou caracteres especiais. client_encoding fixo evita erros de
    # decodificação no Windows em português (ex.: usuário com 'ç').
    try:
        conn = psycopg2.connect(dbname=DB, user=USER, password=PASSWORD, host=HOST, port=PORT,
                                client_encoding="UTF8", connect_timeout=5)
    except psycopg2.OperationalError as erro:
        raise RuntimeError(
            f"Não foi possível conectar ao PostgreSQL em {HOST}:{PORT}/{DB}. "
            "O banco está rodando? Suba com: docker compose up -d db"
        ) from erro
    if somente_leitura:
        conn.set_session(readonly=True, autocommit=True)
    return conn


engine = create_engine("postgresql+psycopg2://", creator=get_conn)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AssemblyLine(Base):
    __tablename__ = "assembly_lines"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)


class Machine(Base):
    __tablename__ = "machines"

    id = Column(String, primary_key=True)
    assembly_line_id = Column(
        Integer,
        ForeignKey("assembly_lines.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False, index=True,
    )


class MachineDowntimeLog(Base):
    __tablename__ = "machine_downtime_logs"
    __table_args__ = (
        CheckConstraint(f"downtime_status IN {STATUS_VALIDOS}", name="ck_logs_downtime_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    machine_id = Column(
        String,
        ForeignKey("machines.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    date = Column(DateTime, nullable=False, index=True)
    hydraulic_pressure = Column(Float)           # bar
    coolant_pressure = Column(Float)             # bar
    air_system_pressure = Column(Float)          # bar
    coolant_temperature = Column(Float)          # °C
    hydraulic_oil_temperature = Column(Float)    # °C
    spindle_bearing_temperature = Column(Float)  # °C
    spindle_vibration = Column(Float)            # µm
    tool_vibration = Column(Float)               # µm
    spindle_speed = Column(Float)                # RPM
    voltage = Column(Float)                      # V
    torque = Column(Float)                       # Nm
    cutting = Column(Float)                      # kN
    downtime_status = Column(String, nullable=False)


def init_db():
    """Cria as tabelas no banco de dados se elas não existirem"""
    Base.metadata.create_all(bind=engine)
    print("Banco de dados e tabelas criados com sucesso!")


def ddl():
    """SQL de criação do schema (o mesmo que create_all executa no Postgres)."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable

    partes = ["-- Gerado por: python src/database.py --ddl > sql/schema_postgres.sql",
              "-- Não edite à mão: o schema é definido em src/database.py.", ""]
    for tabela in Base.metadata.sorted_tables:  # ordem de dependência (FKs)
        partes.append(str(CreateTable(tabela).compile(dialect=postgresql.dialect())).strip() + ";")
        for indice in sorted(tabela.indexes, key=lambda i: i.name):
            partes.append(str(CreateIndex(indice).compile(dialect=postgresql.dialect())) + ";")
        partes.append("")
    return "\n".join(partes)


if __name__ == "__main__":
    import sys

    if "--ddl" in sys.argv:
        print(ddl())
    else:
        init_db()
