import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

USER = os.getenv("POSTGRES_USER", "postgres")
PASSWORD = os.getenv("POSTGRES_PASSWORD", "hash3006")
HOST = "localhost"
PORT = os.getenv("DB_PORT", "5432")
DB = os.getenv("POSTGRES_DB", "data_harvest_db")

# Monta a DSN string pura em bytes e decodifica explicitamente em utf-8 
# para isolar de qualquer caractere especial do Windows (como o 'ç' do usuário)
dsn_raw = f"dbname={DB} user={USER} password={PASSWORD} host={HOST} port={PORT}"
dsn_safe = dsn_raw.encode('utf-8', errors='ignore').decode('utf-8')

import psycopg2

def get_conn():
    return psycopg2.connect(dsn_safe)

engine = create_engine("postgresql+psycopg2://", creator=get_conn)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Definição das Tabelas
class AssemblyLine(Base):
    __tablename__ = "assembly_lines"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

class Machine(Base):
    __tablename__ = "machines"
    
    id = Column(String, primary_key=True, index=True)
    assembly_line_id = Column(Integer, ForeignKey("assembly_lines.id"))

class MachineDowntimeLog(Base):
    __tablename__ = "machine_downtime_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    machine_id = Column(String, ForeignKey("machines.id"))
    date = Column(DateTime)
    hydraulic_pressure = Column(Float)
    coolant_pressure = Column(Float)
    air_system_pressure = Column(Float)
    coolant_temperature = Column(Float)
    hydraulic_oil_temperature = Column(Float)
    spindle_bearing_temperature = Column(Float)
    spindle_vibration = Column(Float)
    tool_vibration = Column(Float)
    spindle_speed = Column(Float)
    voltage = Column(Float)
    torque = Column(Float)
    cutting = Column(Float)
    downtime_status = Column(String)

def init_db():
    """Cria as tabelas no banco de dados se elas não existirem"""
    Base.metadata.create_all(bind=engine)
    print("Banco de dados e tabelas criados com sucesso!")

if __name__ == "__main__":
    init_db()