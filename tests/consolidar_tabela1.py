"""Consolida a Tabela 1 do TCC a partir dos CSVs do Locust em tests/results.

Uso: python tests/consolidar_tabela1.py [--csv saida.csv]

Runs considerados (ver "Nota metodológica" do README):
  - 10, 50 e 100 usuários: v2_*_run1..3
  - 200 usuários: v2_*_run4..7 (runs 1-3 foram feitas antes de isolar o host e
    ficam só como registro histórico)
"""
import argparse
import csv
import statistics as st
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
CENARIOS = {
    "restc": "REST: Agregação Completa do Cliente",
    "nat": "GraphQL: Nativo (N+1)",
    "dl": "GraphQL: DataLoader",
}
RUNS = {10: (1, 2, 3), 50: (1, 2, 3), 100: (1, 2, 3), 200: (4, 5, 6, 7)}


def ler(prefixo: str, run: int, usuarios: int, nome: str) -> dict:
    arquivo = RESULTS / f"v2_{prefixo}_run{run}_{usuarios}users_stats.csv"
    with arquivo.open(encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            if linha["Name"] == nome:
                return linha
    raise KeyError(f"{nome!r} ausente em {arquivo.name}")


def consolidar() -> list[dict]:
    saida = []
    for usuarios, runs in RUNS.items():
        for prefixo, nome in CENARIOS.items():
            linhas = [ler(prefixo, r, usuarios, nome) for r in runs]
            medias = [float(x["Average Response Time"]) for x in linhas]
            media = lambda col: sum(float(x[col]) for x in linhas) / len(linhas)
            saida.append({
                "usuarios": usuarios,
                "cenario": nome,
                "runs": len(runs),
                "total_req": round(media("Request Count")),
                "rps": round(media("Requests/s"), 2),
                "lat_media_ms": round(st.mean(medias), 2),
                "lat_media_dp_ms": round(st.stdev(medias), 2),
                "lat_media_min_ms": round(min(medias), 2),
                "lat_media_max_ms": round(max(medias), 2),
                "p50_ms": round(media("50%"), 2),
                "p95_ms": round(media("95%"), 2),
                "falhas_media": round(media("Failure Count"), 2),
            })
    return saida


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="grava a tabela consolidada neste arquivo")
    args = parser.parse_args()

    tabela = consolidar()
    cols = list(tabela[0])
    print(" | ".join(cols))
    for linha in tabela:
        print(" | ".join(str(linha[c]) for c in cols))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(tabela)
