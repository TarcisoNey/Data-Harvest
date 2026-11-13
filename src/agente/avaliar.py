"""Roda as perguntas complexas de teste (dados de sensores x manual) e salva
as respostas num relatório para revisão.

Uso (na raiz do repositório, com o LLM configurado no .env):
    python -m src.agente.avaliar
    python -m src.agente.avaliar --saida data/processed/avaliacao_agente.md

Para cada pergunta o relatório registra quais ferramentas foram usadas e
marca se o agente usou as duas fontes quando a pergunta pedia.
"""
import argparse
import time
from pathlib import Path

from .agente import AgenteRAG
from .config import RAIZ

# (pergunta, ferramentas esperadas)
PERGUNTAS = [
    (
        "Quantas leituras da máquina Makino-L1-Unit1-2013 ficaram na faixa de pressão "
        "hidráulica de maior risco segundo os relatórios, e quantas delas terminaram em falha?",
        {"consultar_banco", "buscar_manuais"},
    ),
    (
        "Em março de 2022, mês com mais falhas, qual sensor teve a média mais diferente "
        "entre leituras com e sem falha? O que o diagnóstico recomenda para esse caso?",
        {"consultar_banco", "buscar_manuais"},
    ),
    (
        "Qual máquina teve mais leituras com temperatura do coolant acima de 26,4 °C? "
        "Isso é considerado zona de risco? Que ação de manutenção é indicada?",
        {"consultar_banco", "buscar_manuais"},
    ),
    (
        "Compare as três linhas de montagem: taxa de falha e torque médio nas falhas. "
        "Alguma está na faixa de torque baixo descrita nos diagnósticos?",
        {"consultar_banco", "buscar_manuais"},
    ),
    (
        "A vibração do spindle ajuda a prever falhas? Confirme com os dados.",
        {"consultar_banco", "buscar_manuais"},
    ),
    (
        "Qual foi a última leitura com falha registrada e quais sensores dela estavam "
        "fora das faixas seguras descritas nos manuais?",
        {"consultar_banco", "buscar_manuais"},
    ),
    # controle: pergunta só de dados
    ("Quantas leituras existem por máquina?", {"consultar_banco"}),
    # controle: informação que não existe nas fontes
    ("Qual é o custo por hora de máquina parada?", set()),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--saida", default="data/processed/avaliacao_agente.md")
    args = p.parse_args()

    agente = AgenteRAG()
    linhas = [
        "# Avaliação do agente RAG",
        "",
        f"Modelo: `{agente.config.llm_model}` (raciocínio: {agente.config.llm_reasoning_effort or 'padrão'}) | "
        f"Retriever: `{agente.retriever.nome}` | "
        f"{time.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    ok = 0
    for n, (pergunta, esperadas) in enumerate(PERGUNTAS, 1):
        print(f"[{n}/{len(PERGUNTAS)}] {pergunta[:70]}...")
        try:
            resp = agente.perguntar(pergunta)
            texto, passos, tempos = resp.texto, resp.passos, resp.resumo_tempos()
        except Exception as erro:
            texto, passos, tempos = f"ERRO: {erro}", [], "-"
        usadas = {p["ferramenta"] for p in passos}
        erros_sql = sum(1 for p in passos if "erro" in p["resultado"])
        cobriu = esperadas <= usadas
        ok += cobriu
        linhas += [
            f"## {n}. {pergunta}",
            "",
            f"- Ferramentas esperadas: {', '.join(sorted(esperadas)) or 'nenhuma (sem dado nas fontes)'}",
            f"- Ferramentas usadas: {', '.join(p['ferramenta'] for p in passos) or 'nenhuma'}",
            f"- Usou as fontes esperadas: {'sim' if cobriu else 'NÃO'}"
            f" | consultas com erro: {erros_sql}",
            f"- Tempo: {tempos}",
            "",
            texto,
            "",
        ]
        for p_ in passos:
            if p_["ferramenta"] == "consultar_banco":
                linhas += ["<details><summary>SQL</summary>", "", "```", p_["argumentos"], "```", "</details>", ""]

    linhas.insert(4, f"**{ok}/{len(PERGUNTAS)} perguntas usaram as fontes esperadas.** "
                     "Revise as respostas: a cobertura de ferramentas não garante que o conteúdo está certo.\n")
    saida = Path(args.saida)
    saida = saida if saida.is_absolute() else RAIZ / saida
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text("\n".join(linhas), encoding="utf-8")
    print(f"\n{ok}/{len(PERGUNTAS)} usaram as fontes esperadas. Relatório: {saida}")


if __name__ == "__main__":
    main()
