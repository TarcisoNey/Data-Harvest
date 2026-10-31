import re
import sys
import unicodedata
from pathlib import Path
import matplotlib

# Configura o gerador de gráficos para salvar imagens direto em arquivo, sem abrir janelas na tela
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Lista com os nomes das colunas de sensores que só podem ter valores positivos (maiores que zero)
POSITIVE_ONLY = [
    "hydraulic_pressure",
    "coolant_pressure",
    "air_system_pressure",
    "spindle_speed",
    "voltage",
    "torque",
    "cutting",
    "spindle_vibration",
    "tool_vibration",
]

ROOT = Path(__file__).resolve().parents[2]


# Função que padroniza o nome de uma coluna para o formato "snake_case" (letras minúsculas e separadas por underline)
def to_snake(name):
    # Transforma o texto para um formato simples e remove acentos (ex: 'médio' vira 'medio')
    name = (
        unicodedata.normalize("NFKD", str(name))
        .encode("ascii", "ignore")
        .decode()
    )
    # Remove textos que estejam entre colchetes ou parênteses, como unidades de medida [bar] ou (rpm)
    name = re.sub(r"\[.*?\]|\(.*?\)", "", name)
    # Substitui qualquer caractere que não seja letra ou número por um underline (_) e deixa tudo em minúsculo
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


# Função responsável por limpar e corrigir toda a tabela de dados recebida
def clean(raw):
    # Renomeia os nomes de todas as colunas da tabela aplicando a função to_snake em cada um
    df = raw.rename(columns=to_snake)
    # Exibe no terminal a quantidade total de linhas que foram lidas da tabela
    print(f"{len(df)} linhas lidas")

    # P1: Converte a coluna de datas de texto simples para o formato oficial de data e hora do computador
    df["date"] = pd.to_datetime(
        df["date"], format="mixed", dayfirst=True, errors="coerce"
    )
    # Mostra no terminal quantas datas estavam erradas ou corrompidas e foram transformadas em nulas
    print(f"P1 datas invalidas removidas: {int(df['date'].isna().sum())}")
    # Elimina da tabela qualquer linha cuja data não pôde ser identificada
    df = df.dropna(subset=["date"])

    # P2: Guarda a quantidade atual de linhas para podermos comparar depois
    n = len(df)
    # Remove todas as linhas que sejam cópias idênticas de outra linha já existente
    df = df.drop_duplicates()
    # Exibe no terminal quantas linhas duplicadas foram jogadas fora
    print(f"P2 duplicatas removidas: {n - len(df)}")

    # P3: Seleciona apenas as colunas da lista POSITIVE_ONLY que realmente existem nesta tabela
    cols = [c for c in POSITIVE_ONLY if c in df.columns]
    # Conta e exibe no terminal quantos valores menores ou iguais a zero existiam nessas colunas
    print(
        f"P3 valores <= 0 tratados como nulos: {int((df[cols] <= 0).sum().sum())}"
    )
    # Mantém os valores se forem maiores que zero; se forem menores ou iguais, transforma em valor ausente (nulo)
    df[cols] = df[cols].where(df[cols] > 0)

    # P4: Descobre quais colunas guardam números (sensores e medições)
    sensors = list(df.select_dtypes("number").columns)
    # Exibe no terminal o total de informações que estão faltando nessas colunas numéricas
    print(f"P4 nulos imputados: {int(df[sensors].isna().sum().sum())}")
    # Calcula o valor do meio (mediana) de cada sensor agrupando individualmente por cada máquina
    medians = df.groupby("machine_id")[sensors].transform("median")
    # Preenche o valor ausente usando a mediana da própria máquina; se ainda assim faltar, usa a mediana de todas as máquinas juntas
    df[sensors] = df[sensors].fillna(medians).fillna(df[sensors].median())

    # Prepara a coluna que diz se a máquina parou, limpando espaços em branco e padronizando em texto minúsculo
    target = df["downtime"].astype("string").str.strip().str.lower()
    # Verifica quais linhas têm essa resposta preenchida de forma válida
    keep = target.notna()
    # Mantém na tabela apenas as linhas que possuem o status de parada preenchido
    df = df[keep].copy()
    # Cria uma nova coluna chamada 'falha': coloca 1 se a palavra NÃO começar com "no" (ou seja, houve falha) e 0 caso contrário
    df["falha"] = (~target[keep].str.startswith("no")).astype(int)
    # Retorna a tabela totalmente limpa e corrigida para quem chamou a função
    return df


# Função que resume os dados, criando estatísticas agrupadas por máquina e por linha de montagem
def summarize(df):
    # Descobre quais destas colunas de identificação existem na tabela recebida
    keys = [c for c in ("machine_id", "assembly_line_no") if c in df.columns]
    # Prepara o cálculo da média das medições para as colunas de torque, pressão hidráulica e corte (se existirem)
    extra = {
        f"{c}_media": (c, "mean")
        for c in ("torque", "hydraulic_pressure", "cutting")
        if c in df.columns
    }
    # Agrupa os dados e calcula: total de registros, total de falhas, porcentagem de falha e as médias extras
    return (
        df.groupby(keys)
        .agg(
            registros=("falha", "size"),
            falhas=("falha", "sum"),
            taxa_falha=("falha", "mean"),
            **extra,
        )
        .round(3)  # Arredonda todos os resultados numéricos para 3 casas decimais
        .reset_index()  # Transforma os grupos novamente em colunas normais de tabela
        .sort_values(
            "taxa_falha", ascending=False
        )  # Ordena a tabela da máquina que mais falha para a que menos falha
    )


# Função para gerar e salvar o gráfico comparativo de falhas
def chart(df, path):
    # Calcula a porcentagem média de falhas para cada máquina e ordena do maior para o menor
    rate = df.groupby("machine_id")["falha"].mean().sort_values(ascending=False)
    # Calcula a taxa média global de falhas considerando todas as máquinas juntas
    overall = df["falha"].mean()
    # Cria a estrutura da imagem do gráfico definindo seu tamanho (8 por 4.5 polegadas)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    # Desenha barras vermelhas (#c0392b) mostrando a porcentagem de falhas por máquina
    ax.bar(rate.index, rate.values * 100, color="#c0392b")
    # Desenha uma linha pontilhada cinza marcando onde fica a média geral de todas as máquinas juntas
    ax.axhline(
        overall * 100,
        color="gray",
        linestyle="--",
        label=f"media geral ({overall:.1%})",
    )
    # Percorre cada barra do gráfico para escrever o número percentual exato logo acima dela
    for i, v in enumerate(rate.values):
        ax.text(i, v * 100 + 0.5, f"{v:.1%}", ha="center")
    # Escreve o título no topo do gráfico indicando qual máquina teve o pior desempenho
    ax.set_title(
        f"{rate.index[0]} para com mais frequencia: {rate.iloc[0]:.1%} dos registros",
        fontsize=11,
    )
    # Define o texto do eixo vertical (Y)
    ax.set_ylabel("Registros com falha (%)")
    # Mostra a legenda que explica o significado da linha pontilhada
    ax.legend()
    # Inclina os nomes das máquinas no eixo horizontal em 15 graus para facilitar a leitura
    plt.xticks(rotation=15)
    # Ajusta os espaçamentos das bordas da imagem para não cortar nenhum texto
    fig.tight_layout()
    # Salva a imagem gerada no computador no caminho especificado com boa qualidade de resolução
    fig.savefig(path, dpi=150)
    # Fecha o gráfico para liberar espaço na memória do computador
    plt.close(fig)


# Função principal que controla toda a sequência de execução do script
def main():
    csv = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "data/raw/downtime/machine_downtime.csv"
    )
    out = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else ROOT / "data/processed/downtime"
    )
    # Cria a pasta de saída no computador caso ela ainda não exista
    out.mkdir(parents=True, exist_ok=True)
    # Lê o arquivo CSV informado e envia o conteúdo direto para a função de limpeza
    df = clean(pd.read_csv(csv))
    # Salva os dados limpos em um novo arquivo chamado "clean_downtime.csv" na pasta de saída
    df.to_csv(out / "clean_downtime.csv", index=False)
    # Gera o resumo estatístico chamando a função summarize
    summary = summarize(df)
    # Salva o resumo estatístico em um arquivo chamado "summary_downtime.csv"
    summary.to_csv(out / "summary_downtime.csv", index=False)
    # Cria e salva a imagem do gráfico chamando a função chart
    chart(df, out / "chart_downtime.png")
    # Imprime o resumo final em formato de texto diretamente na tela do terminal
    print(summary.to_string(index=False))


# Garante que a função principal 'main' só será executada se este arquivo for rodado diretamente no terminal
if __name__ == "__main__":
    main()