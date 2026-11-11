"""Interface do Dashboard Industrial — Data Harvest.

Monta o layout inspirado no Figma, recebe o CSV e apresenta os resultados
calculados em data.py. Plotly exibe os gráficos interativos. O painel de chat é apenas visual, sem lógica de IA.
"""
# EXECUCÇÃO: cd .\dashboard
# EXECUCÇÃO: python -m streamlit run app.py
# TEM QUE RODAR PELO TERMINAL


import hashlib
from html import escape
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from data import SENSORS, read_csv, filter_data, summary, monthly, by_machine, sensor_monthly, sensor_differences

# A página larga acomoda os gráficos à esquerda e o chat à direita.
st.set_page_config(page_title='Data Harvest • Dashboard Industrial', page_icon='◈', layout='wide', initial_sidebar_state='collapsed')
# Paleta solicitada: verde principal e amarelo de destaque, no estilo John Deere.
# Fundos claros e textos verde-escuros mantêm o contraste nos cartões.
GREEN, YELLOW = '#367C2B', '#FFDD00'
INK, MUTED, GRID = '#1F2D1C', '#58684F', '#E5ECDD'
# Complementa o tema de .streamlit/config.toml com cartões, tipografia e cores
# da referência. Em telas menores, permite que as colunas quebrem de linha.
st.html(Path(__file__).with_name('dashboard.css'))

def chart(fig, height=170, key=None):
    """Aplica o mesmo estilo a todos os gráficos Plotly e os exibe no cartão."""
    titled_x = bool(fig.layout.xaxis.title.text)
    fig.update_layout(height=height, margin={'l': 8, 'r': 8, 't': 24 if len(fig.data) > 1 else 6, 'b': 40 if titled_x else 22},
                    paper_bgcolor='white', plot_bgcolor='white',
                    font={'color': MUTED, 'size': 11}, legend={'orientation': 'h', 'y': 1.01, 'yanchor': 'bottom', 'x': 1, 'xanchor': 'right'},
                    hoverlabel={'bgcolor': 'white','font_color': INK}, colorway=[GREEN, YELLOW])
    # O contorno verde mantém a borda das barras amarelas visível no fundo branco.
    fig.update_traces(marker_line_color=GREEN,marker_line_width=0.7,selector={'type': 'bar'})
    fig.update_xaxes(showgrid=False, automargin=True, title_standoff=8)
    fig.update_layout(barcornerradius=4)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, automargin=True, title_standoff=8)
    st.plotly_chart(fig, width='stretch', key=key, theme=None, config={'displayModeBar':False})

def section_heading(title, subtitle):
    """Mantém título e legenda no mesmo bloco com espaçamento explícito."""
    st.html(f'<header class="section-heading"><h2>{escape(title)}</h2><p>{escape(subtitle)}</p></header>')


def chat_panel():
    """Desenha o espaço reservado ao chat, com campo e envio desativados.

    As sugestões são textos estáticos: nenhuma mensagem é processada,
    nenhuma resposta é gerada e nenhum serviço de IA é chamado.
    """
    with st.container(key='assistant'):
        section_heading('✦ Assistente IA', 'Explore seus dados em linguagem natural')
        st.html('<div class="bubble"><strong>Assistente Industrial</strong><p>Espaço reservado para conversar sobre falhas, sensores e máquinas.</p></div>')
        st.html('<p class="assistant-label">Perguntas sugeridas</p>')
        for text in ['Compare as taxas das máquinas.', 'Como as falhas evoluíram por mês?', 'Quais sensores mais diferem?', 'Quais colunas têm dados ausentes?', 'Posso calcular as horas paradas?']:
            st.html(f'<div class="suggestion">{escape(text)}</div>')
        with st.container(key='composer'):
            st.caption('Prévia do assistente')
            field, send = st.columns([4, 1], gap='small', vertical_alignment='center')
            field.text_input('Sua pergunta', placeholder='Pergunte sobre os dados…', disabled=True, label_visibility='collapsed')
            send.button('➤', help='Enviar pergunta', disabled=True, width='stretch')

def fmt(n: int) -> str:
    return f'{n:,}'.replace(',', '.')


def render_dashboard() -> None:
    st.html('<div class="brand">Data Harvest</div><h1 class="dashboard-title">Dashboard Industrial</h1>')
    description = st.empty()
    with st.container(key='topbar'):
        filters = st.container(key='filters')
    path = Path(__file__).with_name('clean_downtime.csv')
    payload = path.read_bytes() if path.is_file() else None
    if payload is None:
        # Sem fonte de dados, mostra um estado vazio em vez de números fictícios.
        st.info('Coloque o arquivo clean_downtime.csv na pasta do app.py para exibir o dashboard.')
        for col, label in zip(st.columns(4, gap="small"), ['Total de registros', 'Registros com falha', 'Taxa de falhas', 'Máquinas analisadas']):
            col.metric(label, '—')
        return
    # data.py valida e padroniza o CSV, devolvendo os registros, a lista de
    # sensores reconhecidos e o relatório de qualidade da fonte completa.
    try:
        df, sensors, report = read_csv(payload)
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        st.error(f'Não foi possível carregar o arquivo: {exc}')
        return
    # Somente datas válidas definem o intervalo disponível no filtro de período.
    valid = df.Date.dropna()
    if valid.empty:
        st.error('Nenhuma data válida encontrada na coluna Date.')
        return
    if report['datas_invalidas'] or report['situacoes_invalidas']:
        st.warning(f"{report['datas_invalidas']} datas inválidas (excluídas dos filtros) e {report['situacoes_invalidas']} situações desconhecidas (fora do denominador das taxas).")
    # Streamlit executa este arquivo novamente a cada mudança de filtro.
    # A assinatura do conteúdo cria chaves diferentes ao trocar de CSV, evitando
    # reaproveitar seleções de uma fonte anterior que não existam na nova fonte.
    description.caption(f"Falhas, sensores e qualidade dos dados • {valid.min():%d/%m/%Y} a {valid.max():%d/%m/%Y}")
    with filters:
        fingerprint = hashlib.sha256(payload).hexdigest()[:12]
        f1,f2,f3,f4 = st.columns([1.25,1,1,1.15], gap="small")
        period = f1.date_input('Período', (valid.min().date(), valid.max().date()), min_value=valid.min().date(), max_value=valid.max().date(), format='DD/MM/YYYY', key='period_'+fingerprint)
        available_machines = sorted(df.Machine_ID.unique())
        machine_key = 'machines_' + fingerprint
        selected_machines = st.session_state.get(machine_key, available_machines)
        if len(selected_machines) == len(available_machines):
            machine_label = 'Todas as máquinas'
        elif len(selected_machines) == 1:
            machine_label = '1 máquina'
        else:
            machine_label = f'{len(selected_machines)} máquinas'
        with f2:
            st.html('<p class="filter-label">Máquina</p>')
            with st.popover(machine_label, width='stretch'):
                machines = st.multiselect('Máquinas selecionadas', available_machines, default=available_machines, key=machine_key)
        situation = f3.selectbox('Situação', ['Todos os registros', 'Com falha', 'Sem falha'], key='status_'+fingerprint)
        sensor = f4.selectbox('Sensor em análise', sensors, format_func=lambda s:SENSORS[s], disabled=not sensors,
            help='Atualiza as médias por situação e a evolução mensal do sensor.', key='sensor_'+fingerprint)
    if not isinstance(period, tuple) or len(period) != 2:
        st.info('Selecione o início e o fim do período.')
        return
    start,end = period
    filtered = filter_data(df, start, end, machines, situation)
    # Os quatro KPIs são recalculados com o recorte; nenhum valor da imagem
    # é fixado no código. A formatação usa ponto de milhar e vírgula decimal.
    total, failures, rate, machine_count = summary(filtered)
    for col,label,value in zip(st.columns(4, gap="small"), ['Total de registros', 'Registros com falha', 'Taxa de falhas', 'Máquinas analisadas'], [fmt(total),fmt(failures), f'{rate:.1f}%'.replace('.',',') if rate is not None else '—',fmt(machine_count)]):
        col.metric(label,value)
    unavailable = {sensor_name: int(filtered[sensor_name].isna().sum()) for sensor_name in sensors}
    if filtered.empty:
        # Interrompe a montagem dos gráficos quando a seleção não tem dados.
        st.info('Nenhum registro encontrado. Ajuste o período, as máquinas ou a situação.')
        return
    # Primeira linha: evolução mensal e comparação entre máquinas.
    left,right = st.columns([1.65,1])
    with left, st.container(border=True, key="monthly"):
        section_heading('Falhas ao longo do tempo', 'Contagens mensais • passe o cursor para ver o tamanho da amostra')
        # monthly inclui os meses sem registros. O hover mostra o tamanho da
        # amostra e a taxa, para contextualizar a contagem de cada barra.
        m = monthly(filtered,start,end)
        labels = [f'{["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"][p.month-1]}/{p.year}' for p in m.index]
        fig = go.Figure()
        for field,label,color in [('falhas','Com falha',GREEN),('sem_falha','Sem falha',YELLOW)]:
            fig.add_bar(x=labels,y=m[field],name=label,marker_color=color,customdata=m[['registros','classificados','taxa']].to_numpy(), hovertemplate='%{x}<br>'+label+': %{y}<br>Registros: %{customdata[0]}<br>Classificados: %{customdata[1]}<br>Taxa: %{customdata[2]:.1f}%<extra></extra>')
        chart(fig)
        # Destaca amostras pequenas, nas quais percentuais podem ser enganosos.
        small = m[(m.registros>0)&(m.registros<10)]
        if not small.empty:
            st.caption('Amostra pequena (<10 registros): '+', '.join(str(p) for p in small.index)+'. Interprete as taxas com cautela.')
    with right, st.container(border=True, key="machines"):
        section_heading('Falhas por máquina', 'Contagem e taxa no recorte selecionado')
        # Cada máquina tem seu próprio denominador de registros classificados;
        # os rótulos mostram falhas / classificados junto da taxa percentual.
        machines_df = by_machine(filtered)
        machine_counts = machines_df[['falhas', 'classificados', 'taxa']]
        machine_labels = [
            f'{int(failures)}/{int(classified)} • {rate:.1f}%' if pd.notna(rate) else 'Sem classificação'
            for failures, classified, rate in machine_counts.itertuples(index=False, name=None)
        ]
        fig=go.Figure(go.Bar(x=machines_df.taxa,y=machines_df.Machine_ID,orientation='h',marker_color=GREEN,
            insidetextfont={'color': 'white'},outsidetextfont={'color': INK},
            text=machine_labels,textposition='auto',customdata=machines_df[['falhas','classificados']].to_numpy(),hovertemplate='%{y}<br>Taxa: %{x:.1f}%<br>Falhas: %{customdata[0]} / %{customdata[1]}<extra></extra>'))
        fig.update_xaxes(range=[0,100],ticksuffix='%')
        chart(fig)
    # Segunda linha: médias do sensor escolhido e ranking calculado entre sensores.
    left,right=st.columns(2)
    with left, st.container(border=True, key="comparison"):
        section_heading(SENSORS[sensor] if sensor is not None else 'Leituras dos sensores', 'Valores no recorte atual')
        if sensor:
            comparison_tab, trend_tab = st.tabs(['Médias por situação', 'Evolução mensal'])
            with comparison_tab:
                # Separa os grupos sem preencher leituras ausentes. O título do
                # eixo identifica a grandeza e a unidade que mudam com o seletor.
                groups = [(name, filtered.loc[filtered._failure.eq(flag).fillna(False),sensor].dropna()) for flag,name in [(True,'Com falha'),(False,'Sem falha')]]
                means=[values.mean() for _,values in groups]
                # Texto branco no verde e escuro no amarelo para manter a leitura.
                fig=go.Figure(go.Bar(y=[name for name,_ in groups],x=means,orientation='h',marker_color=[GREEN,YELLOW],insidetextfont={'color': ['white',INK]},outsidetextfont={'color': INK},text=[f'{v:.2f}' if pd.notna(v) else 'Sem leituras' for v in means],textposition='auto',customdata=[len(v) for _,v in groups],hovertemplate='%{y}<br>Média: %{x:.2f}<br>Leituras válidas: %{customdata}<extra></extra>'))
                # Redefine a escala ao trocar de sensor, inclusive após aplicar
                # zoom. Leituras de pressão e torque usam unidades diferentes.
                fig.update_layout(xaxis_title=SENSORS[sensor], uirevision=sensor)
                fig.update_xaxes(rangemode='tozero')
                chart(fig,120,key='sensor_comparison')
            with trend_tab:
                # A série acompanha o sensor escolhido e os filtros do recorte.
                # connectgaps=False mantém lacunas nos meses sem leituras.
                trend = sensor_monthly(filtered,sensor,start,end)
                if trend.leituras.sum() == 0:
                    st.info('O sensor selecionado não tem leituras válidas neste recorte.')
                else:
                    fig=go.Figure(go.Scatter(x=trend.index.astype(str).tolist(),y=trend.media.tolist(),mode='lines+markers',
                        name=SENSORS[sensor],line={'color': GREEN},marker={'color': GREEN,'line': {'color': YELLOW,'width': 1.5},'size': 7},connectgaps=False,customdata=trend.leituras.tolist(),
                        hovertemplate='%{x}<br>Média: %{y:.2f}<br>Leituras válidas: %{customdata}<extra></extra>'))
                    fig.update_layout(yaxis_title=SENSORS[sensor],xaxis_title='Mês',uirevision=sensor)
                    chart(fig,120,key='sensor_monthly')
        else:
            st.info('Nenhuma coluna de sensor reconhecida.')
    with right, st.container(border=True, key="differences"):
        section_heading('Maiores diferenças entre sensores', 'Variação percentual • com falha vs. sem falha')
        # O cálculo ordena por diferença percentual absoluta e mantém o sinal:
        # negativo indica média menor nos registros com falha; positivo, maior.
        diffs=sensor_differences(filtered,sensors).head(4)
        if diffs.empty:
            st.info('A comparação exige leituras nos dois grupos e média sem falha diferente de zero.')
        else:
            fig = go.Figure(go.Bar(
                x=diffs.variacao.abs(), y=diffs.sensor, orientation='h',
                marker_color=[GREEN if value < 0 else YELLOW for value in diffs.variacao],
                text=[f'{value:+.1f}%'.replace('.', ',') for value in diffs.variacao],
                textposition='auto', hovertemplate='%{y}<br>%{text}<extra></extra>',
            ))
            fig.update_xaxes(visible=False)
            fig.update_yaxes(autorange='reversed', showgrid=False)
            chart(fig, 132, key='sensor_differences')
    # Qualidade calculada do recorte atual, sem copiar o total da imagem.
    # O CSV limpo incluído tem zero ausentes; outros arquivos podem ter mais.
    with st.container(border=True, key='quality'):
        a,b=st.columns([1,3])
        a.metric('Qualidade dos dados',fmt(sum(unavailable.values())), help='Leituras vazias ou não numéricas no recorte.')
        with b:
            highest = sorted(unavailable, key=unavailable.__getitem__, reverse=True)[:4]
            for column, name in zip(st.columns(4), highest):
                column.metric(SENSORS[name], f'{fmt(unavailable[name])} ausentes')


# Mantém a proporção entre o dashboard principal e o painel lateral direito.
# O chat é desenhado antes da leitura dos dados para continuar visível mesmo
# quando não há CSV ou quando um filtro não encontra registros.
dashboard, assistant = st.columns([3.55, 1], gap='medium')
with assistant:
    chat_panel()
with dashboard:
    render_dashboard()
