"""Testes dos cálculos do dashboard (dashboard/metricas.py).

Uso (na raiz):
    python -m pytest tests/test_metricas.py -v
    # ou, sem pytest:
    python tests/test_metricas.py
"""
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dashboard"))

import metricas as m  # noqa: E402

CSV = RAIZ / "data/processed/downtime/clean_downtime.csv"


def _dados():
    return m.read_csv(CSV.read_bytes())


def test_le_csv_limpo_e_reconhece_todos_os_sensores():
    df, sensores, relatorio = _dados()
    assert len(df) == 2500
    assert len(sensores) == 12
    assert relatorio["datas_invalidas"] == 0 and relatorio["situacoes_invalidas"] == 0


def test_resumo_bate_com_o_banco():
    df, _, _ = _dados()
    total, falhas, taxa, maquinas = m.summary(df)
    assert (total, falhas, maquinas) == (2500, 1265, 3)
    assert round(taxa, 1) == 50.6


def test_filtro_por_maquina_e_situacao():
    df, _, _ = _dados()
    recorte = m.filter_data(df, date(2021, 1, 1), date(2023, 1, 1),
                            ["Makino-L1-Unit1-2013"], "Com falha")
    assert len(recorte) == 454
    assert recorte.Machine_ID.unique().tolist() == ["Makino-L1-Unit1-2013"]


def test_le_csv_bruto_com_cabecalhos_originais():
    df, sensores, _ = m.read_csv((RAIZ / "data/raw/downtime/machine_downtime.csv").read_bytes())
    assert len(df) == 2500 and len(sensores) >= 9


def test_csv_sem_coluna_obrigatoria_da_erro():
    try:
        m.read_csv(b"Machine_ID,Torque\nM1,10\n")
    except ValueError as erro:
        assert "Date" in str(erro)
    else:
        raise AssertionError("deveria recusar CSV sem Date/Downtime")


def test_diferencas_entre_sensores_ordenadas_por_modulo():
    df, sensores, _ = _dados()
    diffs = m.sensor_differences(df, sensores)
    assert diffs.iloc[0]["sensor"] == "Pressão hidráulica (bar)"
    assert diffs.variacao.abs().is_monotonic_decreasing


def test_faixas_de_risco_batem_com_os_relatorios():
    """94,8% de falha na faixa mais baixa de pressão hidráulica (o mesmo de src/relatorios.py)."""
    df, _, _ = _dados()
    faixas = m.risk_bands(df, "Hydraulic_Pressure(bar)")
    assert len(faixas) == 5 and faixas.leituras.sum() == 2500
    assert round(faixas.taxa.iloc[0], 1) == 94.8 and bool(faixas.risco.iloc[0])
    assert faixas.risco.sum() == 1


def test_sinal_mais_forte_e_sem_sinal_quando_todas_falham():
    df, sensores, _ = _dados()
    sinal = m.strongest_signal(df, sensores)
    assert sinal["sensor"] == "Coolant_Pressure(bar)" and round(sinal["taxa"]) == 100
    assert round(sinal["geral"], 1) == 50.6
    so_falhas = df[df._failure.eq(True).fillna(False)]
    assert m.strongest_signal(so_falhas, sensores) is None


if __name__ == "__main__":
    testes = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for t in testes:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(testes)} testes passaram.")
