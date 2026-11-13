"""Ferramenta do agente para consultar o banco do projeto (PostgreSQL).

O LLM escreve a consulta SQL e esta ferramenta executa com três travas:
  1. só aceita um único SELECT (ou WITH ... SELECT);
  2. a sessão do Postgres é aberta em modo READ ONLY, então mesmo um comando
     que escape da validação não consegue alterar nada;
  3. statement_timeout limita cada consulta a alguns segundos.
"""
import datetime as dt
import decimal
import re

DESCRICAO_SCHEMA = """\
Banco PostgreSQL do conjunto Downtime (leituras de sensores de máquinas CNC Makino).

assembly_lines(id INTEGER PK, name VARCHAR)          -- ex.: 'Shopfloor-L1'
machines(id VARCHAR PK, assembly_line_id INTEGER FK -> assembly_lines.id)
                                                     -- ex.: 'Makino-L1-Unit1-2013'
machine_downtime_logs(
    id INTEGER PK, machine_id VARCHAR FK -> machines.id,
    date TIMESTAMP,
    hydraulic_pressure FLOAT (bar), coolant_pressure FLOAT (bar),
    air_system_pressure FLOAT (bar), coolant_temperature FLOAT (°C),
    hydraulic_oil_temperature FLOAT (°C), spindle_bearing_temperature FLOAT (°C),
    spindle_vibration FLOAT (µm), tool_vibration FLOAT (µm),
    spindle_speed FLOAT (RPM), voltage FLOAT (V), torque FLOAT (Nm), cutting FLOAT (kN),
    downtime_status VARCHAR  -- 'Machine_Failure' ou 'No_Machine_Failure'
)
Datas vão de 2021-11-24 a 2022-07-03. Dicas de PostgreSQL: agrupe por mês com
to_char(date, 'YYYY-MM'); conte falhas com COUNT(*) FILTER (WHERE downtime_status =
'Machine_Failure'); para arredondar médias use ROUND(AVG(x)::numeric, 2)."""

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "consultar_banco",
        "description": (
            "Executa UMA consulta SQL SELECT (PostgreSQL) no banco de leituras de sensores "
            "e falhas das máquinas, e devolve as linhas. Use para números, contagens, "
            "médias, datas, valores de sensores e taxas de falha.\n\n" + DESCRICAO_SCHEMA
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "Consulta SELECT em PostgreSQL. Prefira agregações (COUNT, AVG...) a listar muitas linhas.",
                }
            },
            "required": ["sql"],
        },
    },
}

_PROIBIDAS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|merge|"
    r"call|do|vacuum|reindex|cluster|lock|set|reset|listen|notify|comment|security|"
    # funções administrativas: mudar configuração, derrubar conexões, ler arquivos
    r"set_config|pg_terminate_backend|pg_cancel_backend|pg_reload_conf|pg_read_file|"
    r"pg_read_binary_file|pg_ls_dir|pg_stat_file|lo_import|lo_export|dblink\w*)\b",
    re.IGNORECASE,
)


class ConsultaInvalida(ValueError):
    pass


def validar_sql(sql: str) -> str:
    """Devolve o SQL limpo ou levanta ConsultaInvalida se não for um SELECT único."""
    limpo = re.sub(r"--[^\n]*", " ", sql or "")      # comentários de linha
    limpo = re.sub(r"/\*.*?\*/", " ", limpo, flags=re.S)
    limpo = limpo.strip().rstrip(";").strip()
    if not limpo:
        raise ConsultaInvalida("Consulta vazia.")
    if ";" in limpo:
        raise ConsultaInvalida("Envie apenas uma consulta por vez.")
    if not re.match(r"^(select|with)\b", limpo, re.IGNORECASE):
        raise ConsultaInvalida("Só são permitidas consultas SELECT.")
    # ignora strings ('...') e nomes entre aspas ("...") ao procurar comandos proibidos
    sem_strings = re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", limpo)  # e "aliases" 
    if _PROIBIDAS.search(sem_strings):
        raise ConsultaInvalida("A consulta contém um comando que altera o banco ou a sessão.")
    return limpo


def _json(valor):
    """Converte tipos do Postgres em tipos que viram JSON de forma legível."""
    if isinstance(valor, decimal.Decimal):
        return float(valor)
    if isinstance(valor, dt.datetime):
        return valor.date().isoformat() if valor.time() == dt.time() else valor.isoformat(sep=" ")
    if isinstance(valor, dt.date):
        return valor.isoformat()
    return valor


class FerramentaSQL:
    def __init__(self, max_linhas: int = 50, timeout_ms: int = 10_000, conectar=None):
        if conectar is None:
            from .. import database

            conectar = database.get_conn
        self._conectar = conectar
        self.max_linhas = max_linhas
        self.timeout_ms = timeout_ms

    def __call__(self, sql: str) -> dict:
        import psycopg2

        try:
            consulta = validar_sql(sql)
            conn = self._conectar(somente_leitura=True)
            try:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = %s", (self.timeout_ms,))
                    cur.execute(consulta)
                    colunas = [c.name for c in cur.description or []]
                    linhas = cur.fetchmany(self.max_linhas + 1)
            finally:
                conn.close()
        except (ConsultaInvalida, psycopg2.Error) as erro:
            return {"erro": str(erro).strip(), "sql": sql}

        truncado = len(linhas) > self.max_linhas
        linhas = [[_json(v) for v in l] for l in linhas[: self.max_linhas]]
        resultado = {"colunas": colunas, "linhas": linhas, "total_linhas": len(linhas)}
        if truncado:
            resultado["aviso"] = (
                f"Resultado cortado em {self.max_linhas} linhas. Use agregação ou LIMIT."
            )
        return resultado
