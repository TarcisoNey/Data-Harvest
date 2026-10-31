# PARA RODAR NO TERMINAL
# cd ai4i2020
# python pipeline_ai4i.py ai4i2020.csv output

# Biblioteca para encontrar e substituir padrões de texto (expressões regulares)
import re

# Biblioteca que permite interagir com o sistema operacional e ler argumentos passados no terminal
import sys

# Biblioteca para normalizar textos, removendo acentos e caracteres especiais
import unicodedata

# Ferramenta para gerir e manipular caminhos de pastas e arquivos no computador
from pathlib import Path

# Biblioteca utilizada para a criação de gráficos e visualização de dados
import matplotlib

# Configura o visualizador de gráficos para guardar as imagens em ficheiro sem abrir janelas na tela
matplotlib.use("Agg")

# Importa o módulo de desenho do matplotlib usando a sigla simplificada "plt"
import matplotlib.pyplot as plt

# Biblioteca principal para manipular, filtrar e analisar tabelas de dados, apelidada de "pd"
import pandas as pd

# Lista contendo os códigos dos 5 modos específicos de falha dos equipamentos
FAIL_MODES = ["twf", "hdf", "pwf", "osf", "rnf"]


# Função que padroniza os nomes das colunas da tabela para minúsculas separadas por underline (snake_case)
def to_snake(name):
    # Remove acentos e caracteres especiais do texto (ex: 'médio' transforma-se em 'medio')
    name = (
        unicodedata.normalize("NFKD", str(name))
        .encode("ascii", "ignore")
        .decode()
    )
    # Remove qualquer texto contido dentro de parênteses ou colchetes, como unidades de medida (ex: [K] ou (rpm))
    name = re.sub(r"\[.*?\]|\(.*?\)", "", name)
    # Substitui espaços e símbolos por underline (_) e converte todas as letras para minúsculas
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


# Função encarregada de fazer o tratamento, limpeza e organização dos dados brutos
def clean(raw):
    # Altera os nomes de todas as colunas da tabela aplicando a padronização criada na função to_snake
    df = raw.rename(columns=to_snake)
    # Mostra no terminal quantas linhas no total foram carregadas da tabela original
    print(f"{len(df)} linhas lidas")

    # P1: Identifica colunas de códigos de identificação simples que não serão usadas na análise
    ids = [c for c in ("udi", "product_id") if c in df.columns]
    # Remove essas colunas de identificadores da tabela