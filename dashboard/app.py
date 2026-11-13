"""Interface do Dashboard Industrial — Data Harvest.

Monta o layout inspirado no Figma, lê o CSV limpo do Downtime e apresenta os
resultados calculados em metricas.py. Plotly exibe os gráficos interativos.
O painel da direita conversa com o agente RAG de src/agente (Gemini), que
cruza o banco SQL com os manuais indexados no ChromaDB.

Execução (na raiz do repositório):
    python -m streamlit run dashboard/app.py
"""
import hashlib
import json
import re
import sys
from html import escape
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Permite importar metricas.py e o pacote src.agente de qualquer pasta.
APP_DIR = Path(__file__).resolve().parent
RAIZ = APP_DIR.parent
for caminho in (str(APP_DIR), str(RAIZ)):
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

from metricas import (SENSORS, LIFT_RISCO, by_machine, filter_data, monthly, read_csv, risk_bands,  # noqa: E402
                      sensor_differences, sensor_monthly, strongest_signal, summary)

# Fonte de dados: o PostgreSQL do projeto (carregado por src/etl.py). Se o
# banco estiver fora do ar, usa o CSV limpo gerado por src/downtime.py.
CSV_PADRAO = RAIZ / 'data' / 'processed' / 'downtime' / 'clean_downtime.csv'
SQL_LEITURAS = """
SELECT l.date::date AS date, l.machine_id, a.name AS assembly_line_no,
       l.hydraulic_pressure, l.coolant_pressure, l.air_system_pressure,
       l.coolant_temperature, l.hydraulic_oil_temperature, l.spindle_bearing_temperature,
       l.spindle_vibration, l.tool_vibration, l.spindle_speed, l.voltage, l.torque, l.cutting,
       l.downtime_status AS downtime
FROM machine_downtime_logs l
JOIN machines m ON m.id = l.machine_id
JOIN assembly_lines a ON a.id = m.assembly_line_id
ORDER BY l.id
"""


@st.cache_data(ttl=300, show_spinner='Carregando dados do banco…')
def carregar_dados():
    """Devolve (bytes do CSV, descrição da fonte, aviso ou None).

    Os dados do banco são convertidos para CSV para passar pela mesma leitura
    e validação de metricas.read_csv, seja qual for a origem.
    """
    try:
        from src.database import get_conn

        conn = get_conn(somente_leitura=True)
        try:
            with conn.cursor() as cur:
                cur.execute(SQL_LEITURAS)
                df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
        finally:
            conn.close()
        if df.empty:
            raise RuntimeError('o banco está vazio. Rode: python src/etl.py')
        return df.to_csv(index=False).encode(), 'PostgreSQL', None
    except Exception as erro:
        if CSV_PADRAO.is_file():
            return CSV_PADRAO.read_bytes(), 'CSV local', f'Banco indisponível ({erro}). Mostrando o CSV local.'
        return None, None, f'Banco indisponível ({erro}) e CSV local não encontrado.'

st.set_page_config(page_title='Dashboard Industrial • Data Harvest', page_icon=':material/precision_manufacturing:',
                   layout='wide', initial_sidebar_state='collapsed')

# Paleta pedida: verde e amarelo, no estilo John Deere. O verde identifica o
# produto e a interface (cabeçalho, botões, foco). Nos gráficos, o amarelo com
# contorno escuro marca FALHA, como fita de sinalização de fábrica, e o sálvia
# apagado marca "sem falha", que fica em segundo plano.
GREEN, YELLOW = '#367C2B', '#FFDD00'
INK, MUTED, GRID, SAGE = '#1F2D1C', '#5A6B52', '#E3E9DC', '#C9D6BF'
FONT = '"Source Sans", "Source Sans Pro", sans-serif'
MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
st.html(Path(__file__).with_name('dashboard.css'))


def num(valor, casas=0):
    """Número no formato brasileiro: 1.265 / 50,6."""
    return f'{valor:,.{casas}f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def pct(valor, casas=1):
    return f'{num(valor, casas)}%' if valor is not None and pd.notna(valor) else '—'


def nome_maquina(machine_id):
    """'Makino-L1-Unit1-2013' -> 'Makino L1 (2013)'."""
    m = re.match(r'Makino-(L\d+)-Unit\d+-(\d{4})$', str(machine_id))
    return f'Makino {m.group(1)} ({m.group(2)})' if m else str(machine_id)


def unidade(sensor):
    m = re.search(r'\(([^)]*)\)\s*$', SENSORS[sensor])
    return m.group(1) if m else ''


def sem_unidade(sensor):
    return re.sub(r'\s*\([^)]*\)\s*$', '', SENSORS[sensor])


def chart(fig, height=250, key=None, topo=None):
    """Aplica o mesmo estilo a todos os gráficos Plotly e os exibe no painel."""
    fig.update_layout(
        height=height, margin={'l': 4, 'r': 8, 't': topo if topo is not None else (30 if len(fig.data) > 1 else 8), 'b': 4},
        paper_bgcolor='white', plot_bgcolor='white', separators=',.',
        font={'family': FONT, 'color': MUTED, 'size': 12},
        legend={'orientation': 'h', 'y': 1.0, 'yanchor': 'bottom', 'x': 0, 'xanchor': 'left',
                'font': {'size': 12, 'color': INK}},
        hoverlabel={'bgcolor': 'white', 'font': {'family': FONT, 'color': INK}, 'bordercolor': GRID},
        bargap=0.28,
    )
    fig.update_xaxes(showgrid=False, automargin=True, linecolor=GRID, tickfont={'size': 11})
    fig.update_yaxes(gridcolor=GRID, zeroline=False, automargin=True, tickfont={'size': 11})
    st.plotly_chart(fig, width='stretch', key=key, theme=None, config={'displayModeBar': False})


def section_heading(title, subtitle=None):
    """Título do painel e, opcionalmente, uma frase dizendo como lê-lo."""
    sub = f'<p>{escape(subtitle)}</p>' if subtitle else ''
    st.html(f'<header class="section-heading"><h2>{escape(title)}</h2>{sub}</header>')


SUGESTOES = [
    'Compare as taxas de falha das máquinas.',
    'Como as falhas evoluíram por mês?',
    'Pressão hidráulica baixa: quantas falhas e o que fazer?',
    'Qual máquina mais precisa de manutenção agora?',
]


@st.cache_resource(show_spinner=False)
def carregar_agente():
    """Cria o agente uma vez por sessão do servidor.

    Devolve (agente, None) ou (None, mensagem de erro) quando falta a chave
    do LLM, o banco PostgreSQL ou alguma dependência.
    """
    try:
        from src.agente import AgenteRAG
        return AgenteRAG(), None
    except Exception as erro:  # sem GEMINI_API_KEY, sem banco, etc.
        return None, str(erro)


def chat_panel():
    """Chat com o agente RAG: perguntas sugeridas, histórico e campo de envio."""
    with st.container(key='assistant'):
        section_heading('Assistente de manutenção', 'Responde com os dados das máquinas e os manuais')
        agente, erro = carregar_agente()
        historico = st.session_state.setdefault('chat', [])

        if agente is None:
            if 'GEMINI_API_KEY' in erro:
                erro = ('Coloque a chave do Google AI Studio em GEMINI_API_KEY, no arquivo .env, '
                        'e reinicie o dashboard. Os gráficos funcionam sem ela.')
            st.html('<div class="bubble aviso"><strong>Assistente desligado</strong>'
                    f'<p>{escape(erro)}</p></div>')
        elif not historico:
            st.html('<div class="bubble"><p>Pergunte sobre falhas, sensores ou o que fazer em cada máquina. '
                    'Cada resposta mostra as consultas e os trechos de manual usados.</p></div>')

        with st.container(key='messages'):
            for papel, texto, *extra in historico:
                with st.chat_message(papel, avatar=':material/person:' if papel == 'user' else ':material/smart_toy:'):
                    st.markdown(texto)
                    if extra and extra[0]:
                        mostrar_passos(extra[0], extra[1] if len(extra) > 1 else None)

        pergunta = None
        if agente is not None and not historico:
            st.html('<p class="assistant-label">Para começar</p>')
            for i, texto in enumerate(SUGESTOES):
                if st.button(texto, key=f'sugestao_{i}', width='stretch'):
                    pergunta = texto

        with st.container(key='composer'):
            with st.form('pergunta', clear_on_submit=True, border=False):
                field, send = st.columns([2.1, 1], gap='small', vertical_alignment='center')
                digitada = field.text_input('Sua pergunta', placeholder='Sua pergunta',
                                            disabled=agente is None, label_visibility='collapsed')
                enviada = send.form_submit_button('Enviar', type='primary', disabled=agente is None,
                                                  width='stretch')
            if historico and st.button('Limpar conversa', key='limpar', type='tertiary'):
                st.session_state.chat = []
                st.rerun()
        if enviada and digitada.strip():
            pergunta = digitada.strip()

        if pergunta:
            historico.append(('user', pergunta, []))
            with st.spinner('Consultando dados e manuais…'):
                try:
                    r = agente.perguntar(pergunta)
                    resposta, passos, tempos = r.texto or '_(sem resposta)_', r.passos, r.resumo_tempos()
                except Exception as exc:  # erro de rede, cota da API, etc.
                    resposta, passos, tempos = f'Não consegui responder agora: `{exc}`', [], None
            historico.append(('assistant', resposta, passos, tempos))
            st.rerun()


def mostrar_passos(passos, tempos=None):
    """Mostra as consultas SQL e os trechos de manual que embasaram a resposta."""
    consultas = [p for p in passos if p['ferramenta'] == 'consultar_banco']
    buscas = [p for p in passos if p['ferramenta'] == 'buscar_manuais']
    def contar(n, um, varios):
        return f'{n} {um if n == 1 else varios}'

    with st.expander(f"Como cheguei nessa resposta: {contar(len(consultas), 'consulta', 'consultas')} ao banco, "
                     f"{contar(len(buscas), 'busca', 'buscas')} nos manuais"):
        for p in consultas:
            try:
                sql = json.loads(p['argumentos']).get('sql', p['argumentos'])
            except (json.JSONDecodeError, AttributeError):
                sql = p['argumentos']
            st.code(sql, language='sql', wrap_lines=True)
            res = p['resultado']
            if 'erro' in res:
                st.caption(f"Erro (o agente corrigiu e tentou de novo): {res['erro']}")
            elif res.get('linhas'):
                st.dataframe(pd.DataFrame(res['linhas'], columns=res['colunas']).head(10),
                             hide_index=True, width='stretch')
        if tempos:
            st.caption(f'Tempo: {tempos}.')
        trechos = {}
        for p in buscas:
            for t in p['resultado'].get('trechos', []):
                trechos.setdefault(t['id'], t['fonte'])
        if trechos:
            st.markdown('**Trechos consultados:**\n' + '\n'.join(
                f'- `{i}` — {escape(f)}' for i, f in trechos.items()))

def linha_sinal(sinal):
    """Aviso de uma linha: a faixa de sensor onde as falhas mais se concentram."""
    if sinal is None:
        return
    u = unidade(sinal['sensor'])
    nb = ' '  # espaço que não quebra: o número fica junto da unidade
    faixa = f"{num(sinal['inicio'], 2)} e {num(sinal['fim'], 2)}{nb + u if u else ''}"
    st.html(
        '<p class="sinal"><strong>Onde as falhas se concentram:</strong> '
        f'{escape(sem_unidade(sinal["sensor"]).lower())} entre {escape(faixa)}. '
        f'{pct(sinal["taxa"])} das {num(sinal["leituras"])} leituras nessa faixa terminaram em falha '
        f'(geral: {pct(sinal["geral"])}).</p>')


def cartoes_totais(total, falhas, taxa, maquinas):
    celulas = [('Total de registros', num(total)), ('Registros com falha', num(falhas)),
               ('Taxa de falhas', pct(taxa)), ('Máquinas analisadas', num(maquinas))]
    itens = ''.join(f'<div class="kpi"><p>{r}</p><strong>{v}</strong></div>' for r, v in celulas)
    st.html(f'<div class="kpis">{itens}</div>')


def grafico_mensal(filtered, start, end):
    m = monthly(filtered, start, end)
    rotulos = [f'{MESES[p.month - 1].capitalize()}/{p.year}' for p in m.index]
    dados = m[['registros', 'taxa']].to_numpy()
    fig = go.Figure()
    fig.add_bar(x=rotulos, y=m.falhas, name='Com falha', marker={'color': YELLOW, 'line': {'color': INK, 'width': 1}},
                customdata=dados, hovertemplate='%{x}<br>Com falha: %{y}<br>Registros: %{customdata[0]}<br>'
                                                'Taxa: %{customdata[1]:.1f}%<extra></extra>')
    fig.add_bar(x=rotulos, y=m.sem_falha, name='Sem falha', marker={'color': SAGE, 'line': {'color': '#9FB394', 'width': 1}},
                customdata=dados, hovertemplate='%{x}<br>Sem falha: %{y}<br>Registros: %{customdata[0]}<br>'
                                                'Taxa: %{customdata[1]:.1f}%<extra></extra>')
    fig.update_layout(barmode='group', legend={'x': 1, 'xanchor': 'right'})
    chart(fig, 200, key='mensal')
    pequenos = m[(m.registros > 0) & (m.registros < 10)]
    if not pequenos.empty:
        nomes = [f'{MESES[p.month - 1]}/{p.year}' for p in pequenos.index]
        lista = nomes[0] if len(nomes) == 1 else ', '.join(nomes[:-1]) + ' e ' + nomes[-1]
        st.caption(f'Amostra pequena (menos de 10 registros) em {lista}. Interprete as taxas com cautela.')


def grafico_maquinas(filtered, taxa_geral):
    dfm = by_machine(filtered).sort_values('taxa')
    nomes = [nome_maquina(m) for m in dfm.Machine_ID]
    textos = [f'{num(f)}/{num(c)} ({pct(t)})' if pd.notna(t) else 'sem classificação'
              for f, c, t in dfm[['falhas', 'classificados', 'taxa']].itertuples(index=False, name=None)]
    fig = go.Figure(go.Bar(
        x=dfm.taxa, y=nomes, orientation='h', marker={'color': YELLOW, 'line': {'color': INK, 'width': 1}},
        text=textos, textposition='inside', insidetextanchor='end', textfont={'color': INK, 'size': 12},
        customdata=dfm.Machine_ID, hovertemplate='%{customdata}<br>%{text}<extra></extra>'))
    if taxa_geral is not None:
        fig.add_vline(x=taxa_geral, line={'color': INK, 'width': 1, 'dash': 'dot'})
    fig.update_xaxes(range=[0, 100], ticksuffix='%', dtick=25, showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False, tickfont={'size': 12, 'color': INK})
    chart(fig, 200, key='maquinas')
    if taxa_geral is not None:
        st.caption(f'A linha pontilhada marca a taxa geral do recorte ({pct(taxa_geral)}).')


def painel_sensor(filtered, sensor, taxa_geral):
    section_heading(SENSORS[sensor], 'Valores no recorte atual')
    u = unidade(sensor)
    medias, por_mes, por_faixa = st.tabs(['Médias por situação', 'Evolução mensal', 'Taxa por faixa de valor'])
    with medias:
        grupos = [('Com falha', filtered.loc[filtered._failure.eq(True).fillna(False), sensor].dropna()),
                  ('Sem falha', filtered.loc[filtered._failure.eq(False).fillna(False), sensor].dropna())]
        valores = [g.mean() for _, g in grupos]
        fig = go.Figure(go.Bar(
            y=[n for n, _ in grupos], x=valores, orientation='h',
            marker={'color': [YELLOW, SAGE], 'line': {'color': [INK, '#9FB394'], 'width': 1}},
            text=[f'{num(v, 2)} {u}'.strip() if pd.notna(v) else 'sem leituras' for v in valores],
            textposition='inside', insidetextanchor='end', textfont={'color': INK, 'size': 12},
            customdata=[len(g) for _, g in grupos],
            hovertemplate='%{y}<br>Média: %{x:.2f}<br>Leituras: %{customdata}<extra></extra>'))
        fig.update_xaxes(rangemode='tozero', showgrid=True, gridcolor=GRID)
        fig.update_yaxes(showgrid=False, tickfont={'size': 12, 'color': INK})
        fig.update_layout(uirevision=sensor)
        chart(fig, 150, key='sensor_medias')
    with por_mes:
        trend = sensor_monthly(filtered, sensor, filtered.Date.min(), filtered.Date.max())
        if trend.leituras.sum() == 0:
            st.info('O sensor escolhido não tem leituras válidas neste recorte.')
        else:
            rotulos = [f'{MESES[p.month - 1].capitalize()}/{p.year}' for p in trend.index]
            fig = go.Figure(go.Scatter(
                x=rotulos, y=trend.media.tolist(), mode='lines+markers', connectgaps=False,
                line={'color': GREEN, 'width': 2}, marker={'color': GREEN, 'size': 6},
                customdata=trend.leituras.tolist(),
                hovertemplate='%{x}<br>Média: %{y:.2f} ' + u + '<br>Leituras: %{customdata}<extra></extra>'))
            fig.update_layout(uirevision=sensor)
            chart(fig, 150, key='sensor_mes')
    with por_faixa:
        faixas = risk_bands(filtered, sensor)
        if faixas.empty or taxa_geral is None:
            st.info('Para ver a taxa por faixa, o recorte precisa ter leituras com e sem falha.')
        else:
            casas = 0 if faixas.fim.max() >= 1000 else (1 if faixas.fim.max() >= 10 else 2)
            rotulos = [f'{num(a, casas)} a {num(b, casas)}' for a, b in zip(faixas.inicio, faixas.fim)]
            fig = go.Figure(go.Bar(
                x=rotulos, y=faixas.taxa,
                marker={'color': [YELLOW if r else SAGE for r in faixas.risco],
                        'line': {'color': [INK if r else '#9FB394' for r in faixas.risco], 'width': 1}},
                text=[pct(t, 0) for t in faixas.taxa], textposition='outside', textfont={'color': INK, 'size': 12},
                customdata=faixas[['leituras', 'falhas']].to_numpy(),
                hovertemplate='%{x} ' + u + '<br>%{customdata[1]} falhas em %{customdata[0]} leituras<extra></extra>'))
            fig.add_hline(y=taxa_geral, line={'color': INK, 'width': 1, 'dash': 'dot'})
            fig.update_yaxes(range=[0, 115], ticksuffix='%', dtick=50)
            chart(fig, 150, key='faixas')
            st.caption(f'Faixas em {u}, cada uma com um quinto das leituras. Em amarelo, taxa de falha pelo '
                       f'menos {num(LIFT_RISCO, 1)} vez a geral (linha pontilhada).')


def grafico_diferencas(filtered, sensors):
    section_heading('Maiores diferenças entre sensores', 'Variação da média com falha em relação à média sem falha')
    diffs = sensor_differences(filtered, sensors).head(4)
    if diffs.empty:
        st.info('A comparação precisa de leituras com e sem falha no recorte.')
        return
    nomes = [re.sub(r'\s*\([^)]*\)$', '', n) for n in diffs.sensor]
    fig = go.Figure(go.Bar(
        x=diffs.variacao.abs(), y=nomes, orientation='h', marker_color=GREEN,
        text=[f'{"+" if v > 0 else "−"}{num(abs(v), 1)}%' for v in diffs.variacao],
        textposition='inside', insidetextanchor='end', textfont={'color': 'white', 'size': 12},
        hovertemplate='%{y}: %{text}<extra></extra>'))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(autorange='reversed', showgrid=False, tickfont={'size': 12, 'color': INK})
    chart(fig, 176, key='diferencas')
    st.caption('Sinal negativo: a média é menor quando a máquina falha. Positivo: é maior.')


def linha_qualidade(filtered, sensors):
    ausentes = {s: int(filtered[s].isna().sum()) for s in sensors}
    total = sum(ausentes.values())
    if total == 0:
        texto = f'Qualidade dos dados: nenhum valor ausente nos {len(sensors)} sensores deste recorte.'
    else:
        piores = sorted((s for s in ausentes if ausentes[s]), key=ausentes.get, reverse=True)[:4]
        lista = ', '.join(f'{sem_unidade(s).lower()} ({num(ausentes[s])})' for s in piores)
        texto = f'Qualidade dos dados: {num(total)} valores ausentes no recorte, a maioria em {lista}.'
    st.html(f'<p class="qualidade">{escape(texto)}</p>')


def render_dashboard() -> None:
    payload, fonte, aviso = carregar_dados()
    cabecalho = st.empty()
    cabecalho.html('<div class="brand">Data Harvest</div><h1 class="dashboard-title">Dashboard Industrial</h1>')
    if aviso:
        st.warning(aviso)
    if payload is None:
        st.info('Para ver os dados, suba o banco com docker compose up -d db e rode python src/etl.py.')
        return
    try:
        df, sensors, report = read_csv(payload)
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        st.error(f'Não foi possível ler os dados: {exc}')
        return
    valid = df.Date.dropna()
    if valid.empty:
        st.error('Nenhuma data válida encontrada nos dados.')
        return
    if report['datas_invalidas'] or report['situacoes_invalidas']:
        st.warning(f"{report['datas_invalidas']} datas inválidas ficaram fora dos filtros e "
                   f"{report['situacoes_invalidas']} situações desconhecidas ficaram fora das taxas.")
    cabecalho.html('<div class="brand">Data Harvest</div><h1 class="dashboard-title">Dashboard Industrial</h1>'
                   f'<p class="fonte">Falhas, sensores e qualidade dos dados de {valid.min():%d/%m/%Y} a '
                   f'{valid.max():%d/%m/%Y}. Fonte: {escape(fonte)}.</p>')

    # A assinatura do conteúdo gera chaves novas quando a fonte muda, para não
    # reaproveitar seleções que não existem nos dados novos.
    fingerprint = hashlib.sha256(payload).hexdigest()[:12]
    with st.container(key='topbar'):
        f1, f2, f3, f4 = st.columns([1.25, 1, 1, 1.15], gap='small')
        period = f1.date_input('Período', (valid.min().date(), valid.max().date()), min_value=valid.min().date(),
                               max_value=valid.max().date(), format='DD/MM/YYYY', key='period_' + fingerprint)
        available = sorted(df.Machine_ID.unique())
        machine_key = 'machines_' + fingerprint
        escolhidas = st.session_state.get(machine_key, available)
        rotulo = ('Todas as máquinas' if len(escolhidas) == len(available)
                  else nome_maquina(escolhidas[0]) if len(escolhidas) == 1 else f'{len(escolhidas)} máquinas')
        with f2:
            st.html('<p class="filter-label">Máquina</p>')
            with st.popover(rotulo, width='stretch'):
                machines = st.multiselect('Máquinas', available, default=available, key=machine_key,
                                          format_func=nome_maquina)
        situation = f3.selectbox('Situação', ['Todos os registros', 'Com falha', 'Sem falha'],
                                 key='status_' + fingerprint)
        sensor = f4.selectbox('Sensor em análise', sensors, format_func=lambda s: SENSORS[s],
                              key='sensor_' + fingerprint)
    if not isinstance(period, tuple) or len(period) != 2:
        st.info('Escolha a data final do período.')
        return
    start, end = period
    filtered = filter_data(df, start, end, machines, situation)
    total, failures, rate, machine_count = summary(filtered)
    cartoes_totais(total, failures, rate, machine_count)
    if filtered.empty:
        st.info('Nenhuma leitura neste recorte. Amplie o período ou escolha outras máquinas.')
        return
    taxa_geral = rate if situation == 'Todos os registros' else None
    linha_sinal(strongest_signal(filtered, sensors) if taxa_geral is not None else None)

    esquerda, direita = st.columns([1.65, 1], gap='small')
    with esquerda, st.container(border=True, key='monthly'):
        section_heading('Falhas ao longo do tempo', 'Contagens mensais. Passe o cursor para ver o total e a taxa.')
        grafico_mensal(filtered, start, end)
    with direita, st.container(border=True, key='machines'):
        section_heading('Falhas por máquina', 'Falhas e taxa no recorte selecionado')
        grafico_maquinas(filtered, taxa_geral)

    esquerda, direita = st.columns(2, gap='small')
    with esquerda, st.container(border=True, key='comparison'):
        painel_sensor(filtered, sensor, taxa_geral)
    with direita, st.container(border=True, key='differences'):
        grafico_diferencas(filtered, sensors)

    linha_qualidade(filtered, sensors)


# O dashboard ocupa a área principal e o assistente fica no painel da direita.
# O chat é desenhado antes da leitura dos dados para continuar visível mesmo
# quando o banco está fora do ar ou um filtro não encontra registros.
dashboard, assistant = st.columns([3.55, 1], gap='medium')
with assistant:
    chat_panel()
with dashboard:
    render_dashboard()
