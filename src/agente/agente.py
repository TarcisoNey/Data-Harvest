"""Agente RAG do Data Harvest: responde cruzando dados de sensores (SQL)
com os manuais técnicos (retriever), via function calling.

Fluxo de uma pergunta:
    1. o LLM recebe a pergunta + as duas ferramentas;
    2. decide chamar consultar_banco e/ou buscar_manuais (quantas vezes precisar);
    3. cada resultado volta para o LLM como mensagem "tool";
    4. quando não pede mais ferramentas, a resposta final é devolvida.
"""
import json
import time
from dataclasses import dataclass, field

from .config import Config, criar_cliente_llm
from .ferramenta_sql import TOOL_SCHEMA as TOOL_SQL, FerramentaSQL
from .retriever import TOOL_SCHEMA as TOOL_BUSCA, criar_retriever

PROMPT_SISTEMA = """\
Você é o assistente de manutenção do projeto Data Harvest. Responde perguntas
sobre as máquinas CNC das linhas de montagem cruzando duas fontes:

- consultar_banco: dados reais de sensores e falhas (SQL). Use para qualquer
  número: contagens, médias, máximos, datas, taxas de falha.
- buscar_manuais: manuais técnicos e relatórios de manutenção. Use para
  limites e faixas recomendadas, causas de falha, diagnósticos e ações.

Regras:
- Perguntas que pedem dado E orientação precisam das DUAS ferramentas. Nesse
  caso, chame as duas NA MESMA resposta (em paralelo), não uma de cada vez:
  cada rodada extra deixa a resposta mais lenta.
- Prefira uma consulta SQL agregada que já traga tudo o que precisa a várias
  consultas pequenas.
- Nunca invente números: todo valor da resposta vem de uma consulta.
- Se uma consulta der erro, corrija o SQL e tente de novo.
- Se as fontes não tiverem a informação, diga isso claramente.
- Responda em português, de forma objetiva, e termine com uma linha
  "Fontes:" citando as tabelas consultadas e os trechos de manual usados."""


@dataclass
class Resposta:
    texto: str
    passos: list[dict] = field(default_factory=list)  # chamadas de ferramenta feitas
    tempos: list[dict] = field(default_factory=list)  # duração de cada etapa (LLM e ferramentas)

    @property
    def tempo_total(self) -> float:
        return sum(t["segundos"] for t in self.tempos)

    def resumo_tempos(self) -> str:
        llm = [t["segundos"] for t in self.tempos if t["etapa"] == "llm"]
        ferramentas = sum(t["segundos"] for t in self.tempos if t["etapa"] != "llm")
        return (f"{self.tempo_total:.1f}s no total: {len(llm)} chamada(s) ao modelo "
                f"({' + '.join(f'{x:.1f}s' for x in llm)}) e {ferramentas:.2f}s nas ferramentas")


def _mensagem_assistente(msg) -> dict:
    """Devolve a mensagem do modelo para o histórico SEM perder campos extras.

    O Gemini 3 manda uma "thought signature" junto de cada chamada de
    ferramenta (em campos extras do tool_call) e exige recebê-la de volta na
    próxima requisição. Por isso a mensagem é reenviada como veio, em vez de
    ser remontada só com id/nome/argumentos.
    """
    if hasattr(msg, "model_dump"):
        dados = msg.model_dump(exclude_none=True)
        dados["role"] = "assistant"
        dados.setdefault("content", "")
        return dados
    return {  # objetos simples (ex.: o LLM falso dos testes)
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls
        ],
    }


class AgenteRAG:
    def __init__(self, config: Config | None = None, cliente=None, sql=None, retriever=None):
        self.config = config or Config()
        self.cliente = cliente or criar_cliente_llm(self.config)
        self.sql = sql or FerramentaSQL(self.config.max_linhas_sql)
        self.retriever = retriever or criar_retriever(self.config)
        self.ferramentas = [TOOL_SQL, TOOL_BUSCA]

    # -- ferramentas -------------------------------------------------------
    def _executar(self, nome: str, argumentos: str) -> dict:
        try:
            args = json.loads(argumentos or "{}")
        except json.JSONDecodeError:
            return {"erro": f"Argumentos inválidos (JSON): {argumentos}"}
        if nome == "consultar_banco":
            return self.sql(args.get("sql", ""))
        if nome == "buscar_manuais":
            trechos = self.retriever.buscar(args.get("consulta", ""), self.config.k_trechos)
            if not trechos:
                return {"trechos": [], "aviso": "Nenhum trecho encontrado."}
            return {"trechos": [t.como_dict() for t in trechos]}
        return {"erro": f"Ferramenta desconhecida: {nome}"}

    # -- loop do agente ----------------------------------------------------
    def _chamar_llm(self, mensagens, tempos, com_ferramentas=True):
        """Uma chamada ao modelo, cronometrada.

        - Erros temporários (429/5xx) já são repetidos pelo SDK (max_retries).
        - Se ainda assim o modelo estiver indisponível (503/429) e houver
          LLM_MODEL_RESERVA, troca para o reserva e segue com ele.
        - Se a API recusar o parâmetro de raciocínio, repete sem ele.
        """
        from openai import APIStatusError, BadRequestError

        def montar():
            kwargs = {"model": self.config.llm_model, "messages": mensagens}
            if self.config.llm_temperature is not None:
                kwargs["temperature"] = self.config.llm_temperature
            if com_ferramentas:
                kwargs["tools"] = self.ferramentas
            if self.config.llm_reasoning_effort:
                kwargs["reasoning_effort"] = self.config.llm_reasoning_effort
            return kwargs

        inicio = time.perf_counter()
        try:
            try:
                r = self.cliente.chat.completions.create(**montar())
            except BadRequestError as erro:
                if "reasoning" not in str(erro).lower() or not self.config.llm_reasoning_effort:
                    raise
                self.config.llm_reasoning_effort = None
                r = self.cliente.chat.completions.create(**montar())
        except APIStatusError as erro:
            reserva = self.config.llm_model_reserva
            if erro.status_code not in (429, 503) or not reserva or reserva == self.config.llm_model:
                raise
            print(f"[agente] {self.config.llm_model} indisponível ({erro.status_code}); usando {reserva}.")
            self.config.llm_model = reserva
            if "lite" in reserva:
                self.config.llm_reasoning_effort = None
            r = self.cliente.chat.completions.create(**montar())
        tempos.append({"etapa": "llm", "segundos": time.perf_counter() - inicio})
        return r.choices[0].message

    def perguntar(self, pergunta: str, verbose: bool = False) -> Resposta:
        mensagens = [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": pergunta},
        ]
        passos, tempos = [], []
        for _ in range(self.config.max_passos):
            msg = self._chamar_llm(mensagens, tempos)
            if verbose:
                print(f"  [modelo: {tempos[-1]['segundos']:.1f}s]")
            if not msg.tool_calls:
                return Resposta(msg.content or "", passos, tempos)

            mensagens.append(_mensagem_assistente(msg))
            for chamada in msg.tool_calls:
                inicio = time.perf_counter()
                resultado = self._executar(chamada.function.name, chamada.function.arguments)
                tempos.append({"etapa": chamada.function.name, "segundos": time.perf_counter() - inicio})
                passos.append({"ferramenta": chamada.function.name,
                               "argumentos": chamada.function.arguments,
                               "resultado": resultado})
                if verbose:
                    print(f"  -> {chamada.function.name}({chamada.function.arguments}) "
                          f"[{tempos[-1]['segundos'] * 1000:.0f} ms]")
                    if "erro" in resultado:
                        print(f"     erro: {resultado['erro']}")
                mensagens.append({
                    "role": "tool",
                    "tool_call_id": chamada.id,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                })

        # estourou o limite de passos: pede uma resposta com o que já tem
        mensagens.append({"role": "user", "content":
                          "Limite de consultas atingido. Responda com o que já foi encontrado."})
        msg = self._chamar_llm(mensagens, tempos, com_ferramentas=False)
        return Resposta(msg.content or "", passos, tempos)
