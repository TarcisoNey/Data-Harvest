import re
import sys
import unicodedata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

FAIL_MODES = ["twf", "hdf", "pwf", "osf", "rnf"]
ROOT = Path(__file__).resolve().parents[2]


def to_snake(name):
    name = (
        unicodedata.normalize("NFKD", str(name))
        .encode("ascii", "ignore")
        .decode()
    )
    name = re.sub(r"\[.*?\]|\(.*?\)", "", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


def clean(raw):
    df = raw.rename(columns=to_snake)
    print(f"{len(df)} linhas lidas")

    ids = [column for column in ("udi", "product_id") if column in df.columns]
    df = df.drop(columns=ids)

    modes = [column for column in FAIL_MODES if column in df.columns]
    if "machine_failure" in df.columns and modes:
        reported_failure = df[modes].fillna(0).astype(bool).any(axis=1)
        df["rotulo_inconsistente"] = (
            df["machine_failure"].fillna(0).astype(bool) != reported_failure
        ).astype(int)
    else:
        df["rotulo_inconsistente"] = 0

    for column in ("air_temperature", "process_temperature"):
        if column in df.columns:
            df[f"{column}_c"] = (df[column] - 273.15).round(2)

    return df


def summarize(df):
    summary = (
        df.groupby("type")
        .agg(
            registros=("machine_failure", "size"),
            falhas=("machine_failure", "sum"),
            taxa_falha=("machine_failure", "mean"),
            desgaste_medio_min=("tool_wear", "mean"),
            torque_medio_nm=("torque", "mean"),
        )
        .round(3)
        .reset_index()
    )
    return summary.sort_values("taxa_falha", ascending=False)


def chart(summary, path):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    rates = summary.set_index("type")["taxa_falha"] * 100
    bars = ax.bar(rates.index, rates.values, color="#2980b9")
    ax.set_title("Taxa de falha por tipo de produto")
    ax.set_xlabel("Tipo de produto")
    ax.set_ylabel("Registros com falha (%)")

    for bar, rate in zip(bars, rates.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            rate,
            f"{rate:.1f}%",
            ha="center",
            va="bottom",
        )

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    csv = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "data/raw/ai4i2020/ai4i2020.csv"
    )
    out = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else ROOT / "data/processed/ai4i2020"
    )
    out.mkdir(parents=True, exist_ok=True)

    df = clean(pd.read_csv(csv))
    df.to_csv(out / "clean_ai4i.csv", index=False)
    summary = summarize(df)
    summary.to_csv(out / "summary_ai4i.csv", index=False)
    chart(summary, out / "chart_ai4i.png")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
