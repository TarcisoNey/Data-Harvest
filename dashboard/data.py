"""Leitura, validação e cálculos usados pelo Dashboard Industrial.

As funções recebem dados e devolvem tabelas ou indicadores, sem depender
da interface Streamlit. Assim, os mesmos cálculos podem ser testados
separadamente. Este módulo não contém integração ou lógica de IA.
"""
from io import BytesIO
import re
import unicodedata
import numpy as np
import pandas as pd

# Relaciona os nomes internos das colunas aos rótulos em português e suas
# unidades. A leitura também reconhece os nomes sem unidades usados pelo ETL.
SENSORS = {
    'Hydraulic_Pressure(bar)': 'Pressão hidráulica (bar)',
    'Coolant_Pressure(bar)': 'Pressão de refrigeração (bar)',
    'Air_System_Pressure(bar)': 'Pressão de ar (bar)',
    'Coolant_Temperature': 'Temperatura de refrigeração',
    'Hydraulic_Oil_Temperature(°C)': 'Temperatura do óleo (°C)',
    'Spindle_Bearing_Temperature(°C)': 'Temperatura do rolamento (°C)',
    'Spindle_Vibration(µm)': 'Vibração do eixo (µm)',
    'Tool_Vibration(µm)': 'Vibração da ferramenta (µm)',
    'Spindle_Speed(RPM)': 'Rotação do eixo (RPM)',
    'Voltage(volts)': 'Tensão (V)',
    'Torque(Nm)': 'Torque (Nm)',
    'Cutting(kN)': 'Força de corte (kN)',
}

def normalized(value):
    """Remove acentos, espaços e pontuação para comparar nomes e situações.

    Por exemplo, Machine_ID e machine_id passam a ter a mesma chave.
    """
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower())

def read_csv(payload):
    """Lê os bytes do CSV e retorna (tabela, sensores presentes, relatório).

    Padroniza colunas, datas e situações; converte sensores para números.
    Valores inválidos ficam ausentes e são contabilizados para auditoria.
    O conteúdo do arquivo original não é alterado.
    """
    # Tenta UTF-8 e, se a codificação falhar, Windows-1252. sep=None permite
    # ao Pandas detectar separadores como vírgula e ponto e vírgula.
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            raw = pd.read_csv(BytesIO(payload), sep=None, engine='python', encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('Não foi possível reconhecer a codificação do CSV.')
    raw.columns = raw.columns.str.strip()
    if raw.columns.duplicated().any():
        raise ValueError('O CSV contém nomes de colunas duplicados.')
    # Converte tanto os cabeçalhos originais, com unidades, quanto os nomes
    # simplificados do clean_downtime.csv para os nomes internos do dashboard.
    aliases = {normalized(c): c for c in raw.columns}
    rename = {}
    for target in ('Date', 'Machine_ID', 'Downtime', *SENSORS):
        candidates = [normalized(target), normalized(re.sub(r'\(.*?\)', '', target))]
        for candidate in candidates:
            if candidate in aliases:
                rename[aliases[candidate]] = target
                break
    raw = raw.rename(columns=rename)
    # Data, máquina e situação são obrigatórias; sensores podem estar ausentes.
    missing = set(('Date', 'Machine_ID', 'Downtime')) - set(raw.columns)
    if missing:
        raise ValueError('Colunas obrigatórias ausentes: ' + ', '.join(sorted(missing)))
    df = raw.copy()
    # Preserva a interpretação ano-mês-dia do CSV limpo. Nos demais formatos,
    # prioriza dia/mês/ano, usado pelo conjunto Machine Downtime original.
    # errors='coerce' transforma datas inválidas em NaT para poder contá-las.
    dates = df['Date'].astype('string').str.strip()
    iso = dates.str.match(r'^\d{4}-\d{2}-\d{2}', na=False)
    df['Date'] = pd.NaT
    df.loc[iso, 'Date'] = pd.to_datetime(dates[iso], errors='coerce', format='mixed')
    df.loc[~iso, 'Date'] = pd.to_datetime(dates[~iso], errors='coerce', dayfirst=True, format='mixed')
    # _failure é um campo auxiliar: True = falha, False = sem falha,
    # pd.NA = situação desconhecida. O tipo boolean anulável preserva essa
    # diferença, evitando tratar registros desconhecidos como ausência de falha.
    mapping = {'machinedowntime': True, 'machinefailure': True, 'comfalha': True, 'falha': True, 'yes': True, 'true': True, '1': True, '10': True,
               'nomachine downtime': False, 'nomachinedowntime': False, 'nomachinefailure': False, 'semfalha': False, 'no': False, 'false': False, '0': False, '00': False}
    df['_failure'] = df['Downtime'].map(lambda x: mapping.get(normalized(x), pd.NA)).astype('boolean')
    df['Machine_ID'] = df['Machine_ID'].astype('string').str.strip().replace('', pd.NA).fillna('Não informada')
    sensors = [s for s in SENSORS if s in df]
    invalid = {}
    # Aceita vírgula decimal e converte texto inválido ou infinito em NaN.
    # Não preenche leituras: as médias usam somente os valores disponíveis.
    for s in sensors:
        original = df[s]
        df[s] = pd.to_numeric(original.astype('string').str.replace(',', '.', regex=False), errors='coerce').replace([np.inf, -np.inf], np.nan)
        invalid[s] = int((original.notna() & df[s].isna()).sum())
    # O relatório corresponde à fonte completa, antes dos filtros da tela.
    # Distingue células originalmente vazias de valores rejeitados na conversão.
    report = {'datas_invalidas': int(df.Date.isna().sum()), 'situacoes_invalidas': int(df._failure.isna().sum()),
              'ausentes_originais': {s: int(raw[s].isna().sum()) for s in sensors}, 'sensores_invalidos': invalid,
              'duplicados': int(raw.duplicated().sum())}
    return df, sensors, report

def filter_data(df, start, end, machines, situation):
    """Aplica período, máquinas e situação e devolve uma cópia do recorte."""
    # Usa o início do dia seguinte como limite exclusivo para incluir todo o
    # último dia selecionado, mesmo quando a coluna contém horários.
    mask = df.Date.ge(pd.Timestamp(start)) & df.Date.lt(pd.Timestamp(end) + pd.Timedelta(days=1)) & df.Machine_ID.isin(machines)
    if situation != 'Todos os registros':
        mask &= df._failure.eq(situation == 'Com falha').fillna(False)
    return df.loc[mask].copy()

def summary(df):
    """Retorna total, falhas, taxa percentual e quantidade de máquinas.

    A taxa usa apenas situações conhecidas. Sem registros classificados,
    retorna None para a interface exibir '—', evitando divisão por zero.
    """
    known = int(df._failure.notna().sum())
    failures = int(df._failure.sum())
    return len(df), failures, failures / known * 100 if known else None, df.Machine_ID.replace('Não informada', pd.NA).nunique()

def monthly(df, start, end):
    """Agrupa contagens e taxa por mês, incluindo meses vazios do período."""
    # size conta todas as linhas; count ignora situações desconhecidas; sum
    # conta os True (falhas). Meses sem classificação têm taxa indefinida.
    periods = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq='M')
    out = df.groupby(df.Date.dt.to_period('M')).agg(registros=('_failure', 'size'), classificados=('_failure', 'count'), falhas=('_failure', 'sum')).reindex(periods, fill_value=0)
    out['sem_falha'] = out.classificados - out.falhas
    out['taxa'] = out.falhas.div(out.classificados.replace(0, np.nan)).mul(100)
    return out

def by_machine(df):
    """Calcula contagens e taxa usando os classificados de cada máquina."""
    out = df.groupby('Machine_ID').agg(registros=('_failure', 'size'), classificados=('_failure', 'count'), falhas=('_failure', 'sum'))
    out['taxa'] = out.falhas.div(out.classificados.replace(0, np.nan)).mul(100)
    return out.reset_index()

def sensor_monthly(df, sensor, start, end):
    """Calcula a média e a quantidade de leituras válidas do sensor por mês.

    Usa o recorte já filtrado pela tela. Meses sem leituras mantêm a média
    ausente: uma lacuna no gráfico não deve ser apresentada como valor zero.
    """
    periods = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq='M')
    out = df.groupby(df.Date.dt.to_period('M'))[sensor].agg(media='mean', leituras='count').reindex(periods)
    out['leituras'] = out.leituras.fillna(0).astype(int)
    return out


def sensor_differences(df, sensors):
    """Ordena sensores pela diferença percentual absoluta entre as médias.

    O resultado mantém o sinal da variação: negativo significa média menor
    no grupo com falha. É uma comparação descritiva, não uma relação causal.
    """
    rows = []
    for s in sensors:
        yes = df.loc[df._failure.eq(True).fillna(False), s].mean()
        no = df.loc[df._failure.eq(False).fillna(False), s].mean()
        # Só compara quando há médias nos dois grupos e denominador não nulo.
        # |média sem falha| permite interpretar o sinal como aumento ou redução.
        if pd.notna(yes) and pd.notna(no) and no != 0:
            rows.append({'sensor': SENSORS[s], 'variacao': (yes-no)/abs(no)*100})
    return pd.DataFrame(rows, columns=['sensor', 'variacao']).sort_values('variacao', key=lambda s: s.abs(), ascending=False)
