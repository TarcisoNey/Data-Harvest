"""Testes do agente RAG que não precisam de chave de API.

O LLM é substituído por um cliente falso com respostas roteirizadas, então
dá para validar a ferramenta SQL, o retriever e o loop de function calling.

Os testes que consultam o banco usam o PostgreSQL de teste (veja conftest.py).

Uso (na raiz):  python -m pytest tests/test_agente.py -v
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.agente.agente import AgenteRAG  # noqa: E402
from src.agente.config import Config  # noqa: E402
from src.agente.ferramenta_sql import FerramentaSQL  # noqa: E402
from src.agente.retriever import RetrieverLocal  # noqa: E402

CONFIG = Config()


# -- ferramenta SQL ------------------------------------------------------
def test_sql_select_funciona(banco):
    sql = FerramentaSQL()
    r = sql("SELECT COUNT(*) AS total FROM machine_downtime_logs")
    assert r["colunas"] == ["total"] and r["linhas"][0][0] > 0


def test_sql_bloqueia_escrita(banco):
    sql = FerramentaSQL()
    for comando in [
        "DELETE FROM machines",
        "DROP TABLE machines",
        "SELECT 1; DELETE FROM machines",
        "UPDATE machines SET id = 'x'",
        "PRAGMA foreign_keys = OFF",
    ]:
        assert "erro" in sql(comando), comando
    assert sql("SELECT COUNT(*) FROM machines")["linhas"][0][0] == 3  # nada foi apagado


def test_sql_bloqueia_funcoes_administrativas_e_escrita_disfarcada(banco):
    sql = FerramentaSQL()
    for comando in [
        "SELECT set_config('default_transaction_read_only', 'off', false)",
        "WITH x AS (DELETE FROM machines RETURNING *) SELECT * FROM x",
        "SELECT pg_terminate_backend(1)",
    ]:
        assert "erro" in sql(comando), comando


def test_sessao_do_agente_e_somente_leitura(banco):
    """Mesmo sem a validação de texto, a conexão do agente não consegue escrever."""
    import psycopg2

    conn = banco.get_conn(somente_leitura=True)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM machine_downtime_logs")
                raise AssertionError("a sessão deveria ser somente leitura")
            except psycopg2.errors.ReadOnlySqlTransaction:
                pass
    finally:
        conn.close()


def test_sql_consulta_lenta_e_cancelada(banco):
    r = FerramentaSQL(timeout_ms=500)("SELECT pg_sleep(3)")
    assert "timeout" in r["erro"]


def test_sql_corta_resultado_grande(banco):
    r = FerramentaSQL(max_linhas=10)("SELECT * FROM machine_downtime_logs")
    assert r["total_linhas"] == 10 and "aviso" in r


def test_sql_erro_de_sintaxe_vira_mensagem(banco):
    r = FerramentaSQL()("SELECT coluna_que_nao_existe FROM machines")
    assert "erro" in r


# -- retriever ------------------------------------------------------------
def test_retriever_local_acha_trecho_relevante():
    ret = RetrieverLocal(CONFIG.documentos_fallback)
    trechos = ret.buscar("pressão hidráulica baixa", k=3)
    assert trechos and "hidráulica" in trechos[0].texto.lower()


def test_fonte_legivel_sem_metadados():
    from src.agente.retriever import _fonte

    assert _fonte("relatorio_downtime.md_chunk_3", None) == "relatorio_downtime.md (trecho 3)"
    assert _fonte("x", {"fonte": "manual.md", "secao": "Hidráulica", "pagina": 2}) == "manual.md - Hidráulica, p. 2"


def test_hibrido_combina_chroma_e_bm25():
    """O BM25 resgata o documento certo mesmo quando a busca semântica erra."""
    from src.agente.retriever import RetrieverHibrido, Trecho, carregar_documentos

    docs = carregar_documentos(CONFIG.documentos_fallback)

    class ChromaFalso:  # semântica "ruim": devolve sempre os mesmos documentos
        def todos_documentos(self):
            return docs

        def buscar(self, consulta, k):
            return [Trecho(i, t, f, 0.5) for i, t, f in docs[:k]]

    ret = RetrieverHibrido(ChromaFalso())
    ids = [t.id for t in ret.buscar("diagnóstico de torque baixo", 4)]
    assert "diagnostico_torque_baixo_torque" in ids


# -- loop do agente com LLM falso ----------------------------------------
def _chamada(id_, nome, args):
    return NS(id=id_, function=NS(name=nome, arguments=json.dumps(args)))


class LLMFalso:
    """Devolve, em ordem, as mensagens roteirizadas e guarda o que recebeu."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.recebido = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.recebido.append(kwargs["messages"])
        return NS(choices=[NS(message=self.roteiro.pop(0))])


def test_agente_cruza_sql_e_manual(banco):
    llm = LLMFalso([
        NS(content=None, tool_calls=[
            _chamada("c1", "consultar_banco",
                     {"sql": "SELECT COUNT(*) FROM machine_downtime_logs WHERE hydraulic_pressure < 71.64"}),
            _chamada("c2", "buscar_manuais", {"consulta": "pressão hidráulica baixa"}),
        ]),
        NS(content="Resposta final. Fontes: machine_downtime_logs, diagnóstico.", tool_calls=None),
    ])
    agente = AgenteRAG(config=CONFIG, cliente=llm,
                       retriever=RetrieverLocal(CONFIG.documentos_fallback))
    resp = agente.perguntar("pergunta de teste")

    assert resp.texto.startswith("Resposta final")
    assert [p["ferramenta"] for p in resp.passos] == ["consultar_banco", "buscar_manuais"]
    assert resp.passos[0]["resultado"]["linhas"][0][0] > 0
    # os resultados das ferramentas voltaram para o LLM como mensagens "tool"
    tools = [m for m in llm.recebido[1] if m["role"] == "tool"]
    assert {m["tool_call_id"] for m in tools} == {"c1", "c2"}


def test_agente_respeita_limite_de_passos(banco):
    cfg = Config()
    cfg.max_passos = 2
    loop = NS(content=None, tool_calls=[_chamada("x", "consultar_banco", {"sql": "SELECT 1"})])
    llm = LLMFalso([loop, loop, NS(content="parei", tool_calls=None)])
    agente = AgenteRAG(config=cfg, cliente=llm,
                       retriever=RetrieverLocal(cfg.documentos_fallback))
    resp = agente.perguntar("loop infinito?")
    assert resp.texto == "parei" and len(resp.passos) == 2


def test_thought_signature_do_gemini_volta_no_historico():
    from openai.types.chat import ChatCompletionMessage
    from src.agente.agente import _mensagem_assistente

    msg = ChatCompletionMessage.model_validate({
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "consultar_banco", "arguments": "{}"},
                        "extra_content": {"google": {"thought_signature": "abc"}}}],
    })
    dados = _mensagem_assistente(msg)
    assert dados["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "abc"


def test_config_usa_gemini_com_a_chave():
    import os
    antes = {k: os.environ.get(k) for k in ("GEMINI_API_KEY", "LLM_MODEL", "LLM_BASE_URL")}
    try:
        os.environ["GEMINI_API_KEY"] = "teste"
        os.environ.pop("LLM_MODEL", None)
        os.environ.pop("LLM_BASE_URL", None)
        cfg = Config()
        assert cfg.provedor == "gemini"
        assert "generativelanguage.googleapis.com" in cfg.llm_base_url
        assert cfg.llm_model.startswith("gemini")
    finally:
        for k, v in antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# -- latência: nível de raciocínio e tempos ----------------------------------
def test_gemini_padrao_e_flash_lite_sem_parametro_de_raciocinio(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "teste")
    for var in ("LLM_REASONING_EFFORT", "LLM_MODEL", "LLM_TEMPERATURE"):
        monkeypatch.delenv(var, raising=False)
    cfg = Config()
    assert cfg.llm_model == "gemini-3.5-flash-lite"
    assert cfg.llm_reasoning_effort is None      # o padrão do Flash-Lite (minimal) já é o mais rápido
    assert cfg.llm_temperature is None           # Gemini novo ignora temperature: não envia


def test_gemini_flash_maior_usa_raciocinio_low(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "teste")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.8-flash")
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    assert Config().llm_reasoning_effort == "low"
    monkeypatch.setenv("LLM_REASONING_EFFORT", "padrao")
    assert Config().llm_reasoning_effort is None
    monkeypatch.setenv("LLM_REASONING_EFFORT", "medium")
    assert Config().llm_reasoning_effort == "medium"


def test_openai_nao_envia_raciocinio_por_padrao(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    cfg = Config()
    assert cfg.provedor == "openai" and cfg.llm_reasoning_effort is None


class LLMComKwargs:
    """Guarda os parâmetros de cada chamada; opcionalmente recusa reasoning_effort."""

    def __init__(self, roteiro, recusar_raciocinio=False, indisponivel=()):
        self.roteiro, self.recusar = list(roteiro), recusar_raciocinio
        self.indisponivel = set(indisponivel)  # modelos que respondem 503
        self.chamadas = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        if self.recusar and "reasoning_effort" in kwargs:
            import httpx
            from openai import BadRequestError

            resp = httpx.Response(400, request=httpx.Request("POST", "http://x"))
            raise BadRequestError("Unknown parameter: reasoning_effort", response=resp, body=None)
        if kwargs["model"] in self.indisponivel:
            import httpx
            from openai import InternalServerError

            resp = httpx.Response(503, request=httpx.Request("POST", "http://x"))
            raise InternalServerError("The model is overloaded", response=resp, body=None)
        return NS(choices=[NS(message=self.roteiro.pop(0))])


def test_agente_envia_raciocinio_e_mede_tempos():
    cfg = Config()
    cfg.llm_reasoning_effort = "low"
    llm = LLMComKwargs([
        NS(content=None, tool_calls=[_chamada("b", "buscar_manuais", {"consulta": "torque baixo"})]),
        NS(content="ok", tool_calls=None),
    ])
    agente = AgenteRAG(config=cfg, cliente=llm, sql=lambda sql: {},
                       retriever=RetrieverLocal(cfg.documentos_fallback))
    r = agente.perguntar("teste")
    assert all(c["reasoning_effort"] == "low" for c in llm.chamadas)
    assert [t["etapa"] for t in r.tempos] == ["llm", "buscar_manuais", "llm"]
    assert "2 chamada(s) ao modelo" in r.resumo_tempos()


def test_modelo_que_recusa_raciocinio_tenta_de_novo_sem_ele():
    cfg = Config()
    cfg.llm_reasoning_effort = "low"
    llm = LLMComKwargs([NS(content="ok", tool_calls=None)], recusar_raciocinio=True)
    agente = AgenteRAG(config=cfg, cliente=llm, sql=lambda sql: {},
                       retriever=RetrieverLocal(cfg.documentos_fallback))
    assert agente.perguntar("teste").texto == "ok"
    assert "reasoning_effort" not in llm.chamadas[-1] and cfg.llm_reasoning_effort is None


def test_503_no_modelo_principal_usa_o_reserva():
    cfg = Config()
    cfg.llm_model, cfg.llm_model_reserva, cfg.llm_reasoning_effort = "gemini-3.8-flash", "gemini-3.5-flash-lite", "low"
    llm = LLMComKwargs([NS(content="ok", tool_calls=None)], indisponivel={"gemini-3.8-flash"})
    agente = AgenteRAG(config=cfg, cliente=llm, sql=lambda sql: {},
                       retriever=RetrieverLocal(cfg.documentos_fallback))
    assert agente.perguntar("teste").texto == "ok"
    assert llm.chamadas[-1]["model"] == "gemini-3.5-flash-lite"
    assert "reasoning_effort" not in llm.chamadas[-1]   # Flash-Lite: usa o padrão do modelo
    assert cfg.llm_model == "gemini-3.5-flash-lite"      # as próximas perguntas já vão direto no reserva


def test_503_sem_reserva_mostra_o_erro():
    import pytest
    from openai import InternalServerError

    cfg = Config()
    cfg.llm_model, cfg.llm_model_reserva = "gemini-3.8-flash", None
    llm = LLMComKwargs([], indisponivel={"gemini-3.8-flash"})
    agente = AgenteRAG(config=cfg, cliente=llm, sql=lambda sql: {},
                       retriever=RetrieverLocal(cfg.documentos_fallback))
    with pytest.raises(InternalServerError):
        agente.perguntar("teste")


def test_temperature_so_vai_se_configurada():
    cfg = Config()
    cfg.llm_temperature = None
    llm = LLMComKwargs([NS(content="ok", tool_calls=None), NS(content="ok", tool_calls=None)])
    agente = AgenteRAG(config=cfg, cliente=llm, sql=lambda sql: {},
                       retriever=RetrieverLocal(cfg.documentos_fallback))
    agente.perguntar("a")
    assert "temperature" not in llm.chamadas[-1]
    cfg.llm_temperature = 0.2
    agente.perguntar("b")
    assert llm.chamadas[-1]["temperature"] == 0.2
