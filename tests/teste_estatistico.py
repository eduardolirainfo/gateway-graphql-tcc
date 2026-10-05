"""Teste-t pareado (REST x GraphQL/DataLoader) por carga, a partir dos CSVs
do Locust em tests/results.

Usa os mesmos runs que sustentam a Tabela 1 (ver tests/consolidar_tabela1.py):
3 repetições para 10/50/100 usuários, 4 repetições para 200. Compara, para
cada carga, a latência média (Average Response Time) de cada execução de
"REST: Agregação Completa do Cliente" com a de "GraphQL: DataLoader" na
mesma execução (run) -- daí o teste ser pareado (scipy.stats.ttest_rel).

Requer scipy (pip install scipy).

Uso: python tests/teste_estatistico.py
"""
import csv
from pathlib import Path

from scipy import stats

RESULTS = Path(__file__).parent / "results"
RUNS = {10: (1, 2, 3), 50: (1, 2, 3), 100: (1, 2, 3), 200: (4, 5, 6, 7)}


def ler_media(prefixo: str, run: int, usuarios: int, nome: str) -> float:
    arquivo = RESULTS / f"v2_{prefixo}_run{run}_{usuarios}users_stats.csv"
    with arquivo.open(encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            if linha["Name"] == nome:
                return float(linha["Average Response Time"])
    raise KeyError(f"{nome!r} ausente em {arquivo.name}")


def main() -> None:
    print(f"{'Carga':>6} | {'n':>2} | {'media REST':>10} | {'media DL':>9} | "
          f"{'dif. media':>10} | {'t':>7} | {'p-valor':>8} | signif. (5%)?")
    for usuarios, runs in RUNS.items():
        rest = [ler_media("restc", r, usuarios, "REST: Agregação Completa do Cliente") for r in runs]
        dl = [ler_media("dl", r, usuarios, "GraphQL: DataLoader") for r in runs]
        t, p = stats.ttest_rel(rest, dl)
        media_rest = sum(rest) / len(rest)
        media_dl = sum(dl) / len(dl)
        sig = "sim" if p < 0.05 else "nao"
        print(f"{usuarios:>6} | {len(runs):>2} | {media_rest:>10.2f} | {media_dl:>9.2f} | "
              f"{media_rest - media_dl:>10.2f} | {t:>7.3f} | {p:>8.4f} | {sig}")


if __name__ == "__main__":
    main()
