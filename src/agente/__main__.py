"""Uso (na raiz do repositório):

    python -m src.agente "Qual máquina teve mais falhas com pressão hidráulica abaixo de 70 bar e o que o manual recomenda?"
    python -m src.agente            # modo interativo
    python -m src.agente -v "..."   # mostra as chamadas de ferramenta
"""
import argparse

from .agente import AgenteRAG


def main():
    p = argparse.ArgumentParser(description="Agente RAG do Data Harvest")
    p.add_argument("pergunta", nargs="*", help="pergunta (vazio = modo interativo)")
    p.add_argument("-v", "--verbose", action="store_true", help="mostra as ferramentas chamadas")
    args = p.parse_args()

    agente = AgenteRAG()
    print(f"[agente] {agente.config.provedor}: {agente.config.llm_model} "
          f"(raciocínio: {agente.config.llm_reasoning_effort or 'padrão da API'}) | retriever: {agente.retriever.nome}")

    if args.pergunta:
        r = agente.perguntar(" ".join(args.pergunta), verbose=args.verbose)
        print(r.texto)
        if args.verbose:
            print(f"\n[{r.resumo_tempos()}]")
        return

    print("Digite sua pergunta (ou 'sair').")
    while True:
        try:
            pergunta = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if pergunta.lower() in {"sair", "exit", "quit"}:
            break
        if pergunta:
            r = agente.perguntar(pergunta, verbose=args.verbose)
            print(r.texto)
            if args.verbose:
                print(f"\n[{r.resumo_tempos()}]")


if __name__ == "__main__":
    main()
