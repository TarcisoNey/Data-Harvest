"""
Relatórios analíticos, diagnósticos e recomendações de manutenção - Downtime.

Lê o banco (PostgreSQL por padrão, via src/database.py) e gera:
  - data/processed/relatorios/relatorio_downtime.md   relatório para leitura
  - data/processed/relatorios/documentos_rag.jsonl   documentos para o banco
    vetorial (ChromaDB): um JSON por linha com "id", "text" e "metadata"

Análises:
  1. Visão geral por linha de montagem e máquina (taxa de falha, período)
  2. Falhas por mês
  3. Perfil dos sensores: média com falha x sem falha
  4. Zonas de risco: taxa de falha por faixa (quintil) de cada sensor
  5. Diagnósticos: superaquecimento, torque alto/baixo, pressão hidráulica baixa
  6. Recomendações por máquina, a partir das leituras mais recentes

As zonas de risco e as recomendações são heurísticas baseadas na frequência
histórica de falhas em cada faixa de valores. Não são um modelo preditivo
treinado e devem ser lidas como apoio ao diagnóstico.

Uso (na raiz do repositório):
    python src/relatorios.py                                  # PostgreSQL do .env
    python src/relatorios.py --url sqlite:///data/sprint2_etl.db
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SAIDA = ROOT / "data/processed/relatorios"
FALHA = "Machine_Failure"

# coluna -> (nome em português, unidade, artigo)
SENSORES = {
    "hydraulic_pressure": ("pressão hidráulica", "bar", "a"),
    "coolant_pressure": ("pressão do coolant", "bar", "a"),
    "air_system_pressure": ("pressão do sistema de ar", "bar", "a"),
    "coolant_temperature": ("temperatura do coolant", "°C", "a"),
    "hydraulic_oil_temperature": ("temperatura do óleo hidráulico", "°C", "a"),
    "spindle_bearing_temperature": ("temperatura do rolamento do spindle", "°C", "a"),
    "spindle_vibration": ("vibração do spindle", "µm", "a"),
    "tool_vibration": ("vibração da ferramenta", "µm", "a"),
    "spindle_speed": ("rotação do spindle", "RPM", "a"),
    "voltage": ("tensão", "V", "a"),
    "torque": ("torque", "Nm", "o"),
    "cutting": ("força de corte", "kN", "a"),
}
TEMPERATURAS = ["coolant_temperature", "hydraulic_oil_temperature", "spindle_bearing_temperature"]

# Ações sugeridas quando a leitura está numa zona de risco nos extremos
ACOES = {
    ("hydraulic_pressure", "baixa"): "inspecionar bomba hidráulica, vazamentos, filtros e nível de óleo",
    ("hydraulic_pressure", "alta"): "verificar válvulas de alívio e possíveis obstruções no circuito hidráulico",
    ("coolant_pressure", "baixa"): "checar bomba e filtros do sistema de coolant",
    ("coolant_pressure", "alta"): "verificar obstrução de bicos e mangueiras do coolant",
    ("coolant_temperature", "alta"): "verificar trocador de calor, nível e concentração do coolant",
    ("hydraulic_oil_temperature", "alta"): "verificar resfriamento e viscosidade do óleo hidráulico",
    ("spindle_bearing_temperature", "alta"): "verificar lubrificação e pré-carga dos rolamentos do spindle",
    ("spindle_vibration", "alta"): "verificar balanceamento do spindle e estado dos rolamentos",
    ("tool_vibration", "alta"): "verificar fixação e desgaste da ferramenta",
    ("torque", "alta"): "revisar parâmetros de corte, desgaste da ferramenta e fixação da peça",
    ("torque", "baixa"): "investigar perda de carga: ferramenta quebrada, escorregamento ou falha no acionamento",
    ("spindle_speed", "alta"): "conferir a rotação programada e o controle do acionamento do spindle",
    ("spindle_speed", "baixa"): "conferir a rotação programada e possíveis travamentos no spindle",
    ("cutting", "alta"): "força de corte elevada: verificar desgaste da ferramenta, avanço e profundidade de corte",
    ("cutting", "baixa"): "força de corte baixa: verificar se a ferramenta está danificada ou sem contato com a peça",
    ("voltage", "alta"): "verificar a alimentação elétrica e o quadro de comando",
    ("voltage", "baixa"): "verificar quedas de tensão na alimentação elétrica",
}

# Critérios das zonas de risco
N_FAIXAS = 5          # quintis
LIFT_RISCO = 1.4      # taxa da faixa >= 1,4x a taxa geral
TAXA_SEGURA = 0.20    # taxa da faixa <= 20%
SUPORTE_MIN = 50      # leituras mínimas na faixa
PERCENTIL_ALTO = 0.90
PERCENTIL_BAIXO = 0.10

# ---------------------------------------------------------------------------
# Consultas SQL (portáveis entre PostgreSQL e SQLite)
# ---------------------------------------------------------------------------
SQL_BASE = text(f"""
    SELECT l.id, l.machine_id, a.name AS assembly_line, l.date,
           {', '.join('l.' + c for c in SENSORES)},
           l.downtime_status
    FROM machine_downtime_logs l
    JOIN machines m ON m.id = l.machine_id
    JOIN assembly_lines a ON a.id = m.assembly_line_id
""")

SQL_VISAO_GERAL = text("""
    SELECT a.name AS assembly_line,
           m.id AS machine_id,
           COUNT(*) AS registros,
           SUM(CASE WHEN l.downtime_status = :falha THEN 1 ELSE 0 END) AS falhas,
           MIN(l.date) AS inicio,
           MAX(l.date) AS fim
    FROM machine_downtime_logs l
    JOIN machines m ON m.id = l.machine_id
    JOIN assembly_lines a ON a.id = m.assembly_line_id
    GROUP BY a.name, m.id
    ORDER BY a.name, m.id
""")

SQL_PERFIL = text(f"""
    SELECT {', '.join(
        f"AVG(CASE WHEN downtime_status = :falha THEN {c} END) AS {c}__falha, "
        f"AVG(CASE WHEN downtime_status <> :falha THEN {c} END) AS {c}__normal"
        for c in SENSORES)}
    FROM machine_downtime_logs
""")


def sql_acima_abaixo(coluna, operador):
    """Leituras acima/abaixo de um limite, por máquina, e quantas terminaram em falha."""
    if coluna not in SENSORES or operador not in (">", "<"):
        raise ValueError(f"coluna/operador inválido: {coluna} {operador}")
    return text(f"""
        SELECT l.machine_id,
               COUNT(*) AS leituras,
               SUM(CASE WHEN l.downtime_status = :falha THEN 1 ELSE 0 END) AS falhas
        FROM machine_downtime_logs l
        WHERE l.{coluna} {operador} :limite
        GROUP BY l.machine_id
        ORDER BY l.machine_id
    """)


# ---------------------------------------------------------------------------
# Análises
# ---------------------------------------------------------------------------
def fmt(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(valor):
    return f"{fmt(100 * valor, 1)}%"


def carregar_base(conn):
    df = pd.read_sql(SQL_BASE, conn)
    df["date"] = pd.to_datetime(df["date"])
    df["falha"] = (df["downtime_status"] == FALHA).astype(int)
    return df.sort_values(["date", "id"]).reset_index(drop=True)


def visao_geral(conn):
    df = pd.read_sql(SQL_VISAO_GERAL, conn, params={"falha": FALHA})
    df["taxa_falha"] = df["falhas"] / df["registros"]
    df["inicio"] = pd.to_datetime(df["inicio"]).dt.date
    df["fim"] = pd.to_datetime(df["fim"]).dt.date
    return df


def falhas_por_mes(base):
    mes = base["date"].dt.to_period("M").astype(str)
    return (base.groupby([mes.rename("mes"), "machine_id"])["falha"]
                .agg(registros="size", falhas="sum").reset_index())


def perfil_sensores(conn):
    linha = pd.read_sql(SQL_PERFIL, conn, params={"falha": FALHA}).iloc[0]
    df = pd.DataFrame({
        "sensor": list(SENSORES),
        "media_falha": [linha[f"{c}__falha"] for c in SENSORES],
        "media_normal": [linha[f"{c}__normal"] for c in SENSORES],
    })
    df["diferenca_pct"] = (df["media_falha"] - df["media_normal"]) / df["media_normal"]
    return df.sort_values("diferenca_pct", key=abs, ascending=False).reset_index(drop=True)


def zonas_de_risco(base):
    """Taxa de falha por quintil de cada sensor, classificada como risco/segura/neutra."""
    taxa_geral = base["falha"].mean()
    linhas = []
    for c in SENSORES:
        faixas = pd.qcut(base[c], N_FAIXAS, duplicates="drop")
        grupos = base.groupby(faixas, observed=True)["falha"].agg(leituras="size", taxa="mean")
        n = len(grupos)
        for i, (faixa, g) in enumerate(grupos.iterrows()):
            if i == 0:
                posicao = "baixa"
            elif i == n - 1:
                posicao = "alta"
            else:
                posicao = "intermediária"
            if g.leituras >= SUPORTE_MIN and g.taxa >= LIFT_RISCO * taxa_geral:
                classe = "risco"
            elif g.leituras >= SUPORTE_MIN and g.taxa <= TAXA_SEGURA:
                classe = "segura"
            else:
                classe = "neutra"
            linhas.append({
                "sensor": c, "faixa_idx": i, "posicao": posicao,
                "de": faixa.left, "ate": faixa.right,
                "leituras": int(g.leituras), "taxa_falha": g.taxa,
                "lift": g.taxa / taxa_geral, "classe": classe,
            })
    return pd.DataFrame(linhas)


def atribuir_faixas(base, zonas):
    """Para cada leitura, a taxa histórica de falha da faixa de cada sensor."""
    taxas = pd.DataFrame(index=base.index)
    for c, z in zonas.groupby("sensor"):
        bordas = [-float("inf"), *z["ate"].iloc[:-1], float("inf")]
        idx = pd.cut(base[c], bordas, labels=False)
        taxas[c] = z.set_index("faixa_idx").loc[idx, "taxa_falha"].to_numpy()
    return taxas


def diagnostico_limite(conn, base, coluna, operador, percentil):
    limite = base[coluna].quantile(percentil)
    df = pd.read_sql(sql_acima_abaixo(coluna, operador), conn,
                     params={"falha": FALHA, "limite": float(limite)})
    df["taxa_falha"] = df["falhas"] / df["leituras"]
    return limite, df


def diagnosticos(conn, base):
    casos = [("superaquecimento", c, ">", PERCENTIL_ALTO) for c in TEMPERATURAS] + [
        ("torque elevado", "torque", ">", PERCENTIL_ALTO),
        ("torque baixo", "torque", "<", PERCENTIL_BAIXO),
        ("pressão hidráulica baixa", "hydraulic_pressure", "<", PERCENTIL_BAIXO),
    ]
    resultado = []
    for tema, coluna, op, p in casos:
        limite, df = diagnostico_limite(conn, base, coluna, op, p)
        resultado.append({"tema": tema, "sensor": coluna, "operador": op, "percentil": p,
                          "limite": limite, "por_maquina": df})
    return resultado


def recomendacoes(base, zonas, ultimas):
    """Risco estimado e ações por máquina a partir das últimas leituras."""
    sensores_uteis = sorted(zonas.loc[zonas["classe"] == "risco", "sensor"].unique())
    taxas = atribuir_faixas(base, zonas)[sensores_uteis]
    base = base.assign(risco_estimado=taxas.mean(axis=1))
    zonas_idx = zonas.set_index(["sensor", "faixa_idx"])

    # Quanto o risco estimado separa falhas de não falhas no histórico (in-sample)
    separacao = (base.loc[base.falha == 1, "risco_estimado"].mean()
                 - base.loc[base.falha == 0, "risco_estimado"].mean())

    saida = []
    for maquina, g in base.groupby("machine_id"):
        recentes = g.tail(ultimas)
        alertas = []
        for c in sensores_uteis:
            bordas = [-float("inf"), *zonas.loc[zonas.sensor == c, "ate"].iloc[:-1], float("inf")]
            idx = pd.cut(recentes[c], bordas, labels=False)
            em_risco = idx[[zonas_idx.loc[(c, i), "classe"] == "risco" for i in idx]]
            if len(em_risco) == 0:
                continue
            faixa = zonas_idx.loc[(c, em_risco.mode().iloc[0])]
            alertas.append({
                "sensor": c, "leituras_em_risco": len(em_risco), "posicao": faixa["posicao"],
                "de": faixa["de"], "ate": faixa["ate"], "taxa_falha": faixa["taxa_falha"],
                "acao": ACOES.get((c, faixa["posicao"]),
                                  f"acompanhar {o_a(c)} e comparar com a faixa usual da máquina"),
            })
        alertas.sort(key=lambda a: (a["leituras_em_risco"], a["taxa_falha"]), reverse=True)
        risco = recentes["risco_estimado"].mean()
        nivel = "alto" if risco >= 0.65 else "moderado" if risco >= 0.45 else "baixo"
        saida.append({
            "machine_id": maquina, "assembly_line": g["assembly_line"].iloc[0],
            "leituras_analisadas": len(recentes),
            "periodo": (recentes["date"].min().date(), recentes["date"].max().date()),
            "falhas_recentes": int(recentes["falha"].sum()),
            "risco_estimado": risco, "nivel": nivel, "alertas": alertas,
        })
    return saida, sensores_uteis, separacao


# ---------------------------------------------------------------------------
# Textos: relatório Markdown e documentos para o RAG
# ---------------------------------------------------------------------------
def nome(c):
    return SENSORES[c][0]


def o_a(c):
    """'o torque', 'a pressão hidráulica'"""
    return f"{SENSORES[c][2]} {nome(c)}"


def pelo(c):
    return f"{'pelo' if SENSORES[c][2] == 'o' else 'pela'} {nome(c)}"


def plural(n, singular, plural_):
    return f"{n} {singular if n == 1 else plural_}"


def comparar(taxa, taxa_geral):
    if taxa > taxa_geral * 1.1:
        return f"maior que a taxa geral de {pct(taxa_geral)}"
    if taxa < taxa_geral * 0.9:
        return f"menor que a taxa geral de {pct(taxa_geral)}"
    return f"parecida com a taxa geral de {pct(taxa_geral)}"


def faixa_txt(c, de, ate):
    return f"{fmt(de)} a {fmt(ate)} {SENSORES[c][1]}"


def gerar_documentos(geral, mensal, perfil, zonas, diags, recs, sensores_uteis, separacao, base):
    docs = []
    taxa_geral = base["falha"].mean()
    periodo = f"de {base['date'].min().date()} a {base['date'].max().date()}"

    def add(doc_id, tipo, texto, **meta):
        meta = {"tipo": tipo, "fonte": "machine_downtime_logs", **meta}
        docs.append({"id": doc_id, "text": texto.strip(),
                     "metadata": {k: v for k, v in meta.items() if v is not None}})

    # Visão geral
    linhas = "; ".join(
        f"{r.machine_id} ({r.assembly_line}): {r.registros} leituras, {r.falhas} falhas, "
        f"taxa de {pct(r.taxa_falha)}" for r in geral.itertuples())
    pior = geral.sort_values("taxa_falha", ascending=False).iloc[0]
    add("visao_geral", "visao_geral", f"""
Visão geral do conjunto Downtime: {len(base)} leituras de sensores de {geral.machine_id.nunique()}
máquinas em {geral.assembly_line.nunique()} linhas de montagem, {periodo}. Ao todo,
{int(base.falha.sum())} leituras ({pct(taxa_geral)}) terminaram em falha de máquina (Machine_Failure).
Por máquina: {linhas}. A máquina com maior taxa de falha é {pior.machine_id}
({pct(pior.taxa_falha)}).""")

    # Falhas por mês
    por_mes = mensal.groupby("mes")[["registros", "falhas"]].sum()
    pico = por_mes["falhas"].idxmax()
    meses = "; ".join(f"{m}: {plural(int(r.falhas), 'falha', 'falhas')} em "
                      f"{plural(int(r.registros), 'leitura', 'leituras')}"
                      for m, r in por_mes.iterrows())
    add("falhas_por_mes", "serie_temporal", f"""
Falhas por mês no conjunto Downtime: {meses}. O mês com mais falhas foi {pico}
({int(por_mes.loc[pico, 'falhas'])} falhas). Os meses com poucas leituras têm taxas pouco
confiáveis.""")

    # Perfil dos sensores
    itens = "; ".join(
        f"{nome(r.sensor)}: {fmt(r.media_falha)} com falha x {fmt(r.media_normal)} sem falha "
        f"({'+' if r.diferenca_pct >= 0 else ''}{pct(r.diferenca_pct)})"
        for r in perfil.itertuples())
    add("perfil_sensores", "perfil_sensores", f"""
Comparação das médias dos sensores entre leituras com falha e sem falha, ordenada pela maior
diferença: {itens}. Diferenças pequenas indicam que o sensor, sozinho, não distingue as falhas.""")

    # Um documento por sensor (zonas de risco)
    for c in SENSORES:
        z = zonas[zonas.sensor == c]
        faixas = "; ".join(f"{faixa_txt(c, r.de, r.ate)}: {pct(r.taxa_falha)} de falha "
                           f"({r.leituras} leituras)" for r in z.itertuples())
        risco = z[z.classe == "risco"]
        seguras = z[z.classe == "segura"]
        if len(risco):
            conclusao = ("Faixas de risco (taxa de falha pelo menos 1,4 vez a geral de "
                         f"{pct(taxa_geral)}): " + "; ".join(
                             f"{r.posicao} ({faixa_txt(c, r.de, r.ate)}, {pct(r.taxa_falha)})"
                             for r in risco.itertuples()) + ".")
        else:
            conclusao = (f"Nenhuma faixa tem taxa de falha muito acima da geral ({pct(taxa_geral)}): "
                         f"{o_a(c)} {'sozinho' if SENSORES[c][2] == 'o' else 'sozinha'} não é um bom "
                         "indicador de falha neste conjunto.")
        if len(seguras):
            conclusao += " Faixas com poucas falhas: " + "; ".join(
                f"{faixa_txt(c, r.de, r.ate)} ({pct(r.taxa_falha)})" for r in seguras.itertuples()) + "."
        add(f"sensor_{c}", "zona_de_risco", f"""
Sensor {nome(c)} ({c}, em {SENSORES[c][1]}). Taxa de falha por faixa de valores (quintis):
{faixas}. {conclusao}""", sensor=c, indicador_de_falha=bool(len(risco)))

    # Diagnósticos temáticos
    for d in diags:
        df = d["por_maquina"]
        lado = "acima" if d["operador"] == ">" else "abaixo"
        total_l, total_f = int(df.leituras.sum()), int(df.falhas.sum())
        taxa = total_f / total_l if total_l else 0
        maquinas = "; ".join(f"{r.machine_id}: {r.leituras} leituras, {pct(r.taxa_falha)} de falha"
                             for r in df.itertuples())
        if taxa > taxa_geral * 1.1:
            leitura = "Essa condição está associada a mais falhas do que o normal."
        elif taxa < taxa_geral * 0.9:
            leitura = "Nessa condição as falhas são menos frequentes do que o normal."
        else:
            leitura = "Essa condição, sozinha, não muda a chance de falha."
        add(f"diagnostico_{d['tema'].replace(' ', '_')}_{d['sensor']}", "diagnostico", f"""
Diagnóstico de {d['tema']} {pelo(d['sensor'])}: leituras {lado} de
{fmt(d['limite'])} {SENSORES[d['sensor']][1]} (percentil {int(d['percentil'] * 100)} do histórico).
Foram {total_l} leituras nessa condição, com {plural(total_f, 'falha', 'falhas')} ({pct(taxa)}),
taxa {comparar(taxa, taxa_geral)}. {leitura} Por máquina: {maquinas}.""",
            sensor=d["sensor"], tema=d["tema"])

    # Recomendações por máquina
    for r in recs:
        if r["alertas"]:
            alertas = "\n".join(
                f"- {nome(a['sensor']).capitalize()} na faixa {a['posicao']} ({faixa_txt(a['sensor'], a['de'], a['ate'])}) "
                f"em {a['leituras_em_risco']} das {r['leituras_analisadas']} leituras recentes; historicamente "
                f"{pct(a['taxa_falha'])} das leituras nessa faixa terminaram em falha. Ação sugerida: {a['acao']}."
                for a in r["alertas"][:4])
        else:
            alertas = "Nenhum sensor ficou em faixa de risco nas leituras recentes."
        add(f"recomendacao_{r['machine_id']}", "recomendacao", f"""
Recomendação de manutenção para a máquina {r['machine_id']} ({r['assembly_line']}), com base nas
{r['leituras_analisadas']} leituras mais recentes ({r['periodo'][0]} a {r['periodo'][1]}): risco
estimado {r['nivel']} ({pct(r['risco_estimado'])}), com {plural(r['falhas_recentes'], 'falha registrada', 'falhas registradas')}
nesse intervalo. Sensores em faixa de risco:
{alertas}
Nota: o risco estimado é a média das taxas históricas de falha das faixas em
que cada sensor indicador ({', '.join(nome(s) for s in sensores_uteis)}) se encontra; é uma
heurística baseada em frequência, não um modelo treinado.""",
            machine_id=r["machine_id"], assembly_line=r["assembly_line"],
            nivel_risco=r["nivel"], risco_estimado=round(float(r["risco_estimado"]), 4))

    # Metodologia (ajuda o RAG a explicar de onde vêm os números)
    add("metodologia", "metodologia", f"""
Metodologia dos relatórios do Downtime: cada sensor foi dividido em {N_FAIXAS} faixas com o mesmo
número de leituras (quintis). Uma faixa é de risco quando tem pelo menos {SUPORTE_MIN} leituras e taxa
de falha pelo menos {fmt(LIFT_RISCO, 1)} vez a taxa geral ({pct(taxa_geral)}); é segura quando a taxa
é de no máximo {pct(TAXA_SEGURA)}. Os diagnósticos de superaquecimento e torque usam os percentis
{int(PERCENTIL_ALTO * 100)} e {int(PERCENTIL_BAIXO * 100)} do histórico como limites. No próprio
histórico, o risco estimado médio das leituras com falha é {fmt(100 * separacao, 1)} pontos
percentuais maior que o das leituras sem falha; como é medido nos mesmos dados usados para
definir as faixas, esse número é otimista.""")
    return docs


def normalizar(texto):
    """Junta as quebras de linha do código em parágrafos, mantendo itens de lista."""
    saida, atual = [], []
    for linha in texto.strip().splitlines():
        linha = " ".join(linha.split())
        if linha.startswith(("- ", "Nota:")):
            if atual:
                saida.append(" ".join(atual))
                atual = []
            if linha.startswith("Nota:"):
                atual = [linha]
            else:
                saida.append(linha)
        else:
            atual.append(linha)
            if linha.endswith(":"):
                saida.append(" ".join(atual))
                atual = []
    if atual:
        saida.append(" ".join(atual))
    return "\n".join(saida)


def gerar_markdown(docs):
    titulos = {
        "visao_geral": "Visão geral", "serie_temporal": "Falhas por mês",
        "perfil_sensores": "Perfil dos sensores", "zona_de_risco": "Zonas de risco por sensor",
        "diagnostico": "Diagnósticos", "recomendacao": "Recomendações por máquina",
        "metodologia": "Metodologia",
    }
    partes = ["# Relatório de manutenção preditiva - Downtime\n"]
    for tipo, titulo in titulos.items():
        do_tipo = [d for d in docs if d["metadata"]["tipo"] == tipo]
        if do_tipo:
            partes.append(f"## {titulo}\n")
            partes += [d["text"].replace("\nNota:", "\n\nNota:") + "\n" for d in do_tipo]
    return "\n".join(partes)


def gerar(engine, saida=SAIDA, ultimas=20):
    with engine.connect() as conn:
        base = carregar_base(conn)
        if base.empty:
            raise SystemExit("machine_downtime_logs está vazia. Carregue os dados antes.")
        geral = visao_geral(conn)
        perfil = perfil_sensores(conn)
        diags = diagnosticos(conn, base)
    mensal = falhas_por_mes(base)
    zonas = zonas_de_risco(base)
    recs, sensores_uteis, separacao = recomendacoes(base, zonas, ultimas)

    docs = gerar_documentos(geral, mensal, perfil, zonas, diags, recs, sensores_uteis, separacao, base)
    for d in docs:
        d["text"] = normalizar(d["text"])

    saida.mkdir(parents=True, exist_ok=True)
    (saida / "relatorio_downtime.md").write_text(gerar_markdown(docs), encoding="utf-8")
    with open(saida / "documentos_rag.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"{len(base)} leituras analisadas; {len(docs)} documentos gerados em {saida}")
    for r in recs:
        principais = ", ".join(nome(a["sensor"]) for a in r["alertas"][:3]) or "nenhum alerta"
        print(f"  {r['machine_id']}: risco {r['nivel']} ({pct(r['risco_estimado'])}) - {principais}")
    return docs


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="URL SQLAlchemy do banco (padrão: PostgreSQL do .env)")
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--ultimas", type=int, default=20,
                        help="leituras mais recentes por máquina usadas nas recomendações")
    args = parser.parse_args()
    if args.url:
        engine = create_engine(args.url)
    else:
        from database import engine
    gerar(engine, args.saida, args.ultimas)


if __name__ == "__main__":
    main()
