"""Testes do ETL (src/etl.py): validação do CSV e idempotência da carga.

Uso (na raiz):  python -m pytest tests/test_etl.py -v
"""
import pandas as pd
import pytest

import etl


def test_csv_sem_coluna_obrigatoria_e_recusado(tmp_path):
    df = pd.read_csv(etl.CSV_DOWNTIME).drop(columns=["torque"])
    caminho = tmp_path / "sem_torque.csv"
    df.to_csv(caminho, index=False)
    with pytest.raises(ValueError, match="torque"):
        etl.preparar_downtime(caminho)


def test_status_invalido_e_recusado(tmp_path):
    df = pd.read_csv(etl.CSV_DOWNTIME)
    df.loc[0, "downtime"] = "Talvez"
    caminho = tmp_path / "status.csv"
    df.to_csv(caminho, index=False)
    with pytest.raises(ValueError, match="status inválidos"):
        etl.preparar_downtime(caminho)


def test_rodar_de_novo_nao_duplica(banco):
    assert etl.executar() == 0
    _, contagens = etl.verificar_integridade()
    assert contagens["machine_downtime_logs"] == 2500


def test_csv_diferente_do_banco_cancela_sem_sobrescrever(banco, tmp_path):
    df = pd.read_csv(etl.CSV_DOWNTIME)
    df.loc[0, "torque"] += 1
    caminho = tmp_path / "alterado.csv"
    df.to_csv(caminho, index=False)
    with pytest.raises(ValueError, match="diferentes do CSV"):
        etl.executar(caminho)
    _, contagens = etl.verificar_integridade()
    assert contagens["machine_downtime_logs"] == 2500
