# -*- coding: utf-8 -*-
"""BRVM (Bourse régionale d'Abidjan, 8 pays d'Afrique de l'Ouest) : cours du jour lus sur le site officiel,
historique construit jour après jour pour calculer des tendances."""

import datetime as dt
import html
import re
import urllib.request
from pathlib import Path

import pandas as pd

DOSSIER = Path(__file__).resolve().parent
HISTO = DOSSIER / "brvm_historique.csv"
URLS = ["https://www.brvm.org/fr/cours-actions/0", "https://www.brvm.org/fr/cours-actions/-1", "https://www.brvm.org/en/cours-actions/0"]


def log(m):
    print(f"[brvm] {m}", flush=True)


def _nombre(t):
    t = (t or "").replace("\xa0", "").replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def cours_du_jour():
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
          "Accept-Language": "fr-FR,fr;q=0.9"}
    for url in URLS:
        try:
            page = urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=30).read().decode("utf-8", "ignore")
        except Exception as ex:
            log(f"{url} : {ex}")
            continue
        lignes = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            cel = [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            cel = [" ".join(c.split()) for c in cel]
            if len(cel) < 5:
                continue
            sym = cel[0]
            if not re.fullmatch(r"[A-Z]{3,6}", sym):
                continue
            nums = [_nombre(c) for c in cel[2:]]
            vals = [n for n in nums if n is not None]
            if len(vals) < 3:
                continue
            # colonnes habituelles : Symbole, Nom, Volume, Cours veille, Cours ouverture, Cours clôture, Variation (%)
            cloture = nums[3] if len(nums) > 3 and nums[3] else vals[-2]
            variation = nums[-1] if nums[-1] is not None else 0.0
            lignes.append({"symbole": sym, "nom": cel[1].title(), "cours": cloture, "variation_jour": variation / 100})
        if lignes:
            log(f"{len(lignes)} titres lus sur {url}")
            return lignes
        log(f"aucun tableau lisible sur {url}")
    return []


def analyse():
    """Cours du jour + tendances calculées sur l'historique accumulé."""
    jour = cours_du_jour()
    if not jour:
        return {"titres": [], "message": "Site de la BRVM inaccessible pour le moment."}
    aujourd_hui = dt.date.today().isoformat()
    df_new = pd.DataFrame(jour).assign(date=aujourd_hui)
    if HISTO.exists():
        h = pd.read_csv(HISTO)
        h = h[h["date"] != aujourd_hui]
        h = pd.concat([h, df_new[["date", "symbole", "nom", "cours"]]], ignore_index=True)
    else:
        h = df_new[["date", "symbole", "nom", "cours"]]
    h.to_csv(HISTO, index=False)
    titres = []
    for r in jour:
        serie = h[h["symbole"] == r["symbole"]].sort_values("date")["cours"].astype(float).reset_index(drop=True)
        def perf(n):
            return float(serie.iloc[-1] / serie.iloc[-1 - n] - 1) if len(serie) > n and serie.iloc[-1 - n] else None
        tendance = None
        if len(serie) >= 20:
            m20 = serie.tail(20).mean()
            tendance = "hausse" if serie.iloc[-1] > m20 * 1.01 else "baisse" if serie.iloc[-1] < m20 * 0.99 else "stable"
        titres.append(r | {"perf_1sem": perf(5), "perf_1mois": perf(21), "tendance": tendance, "nb_jours": len(serie)})
    titres.sort(key=lambda t: -(t["perf_1mois"] if t["perf_1mois"] is not None else t["variation_jour"]))
    jours = int(h["date"].nunique())
    return {"titres": titres, "jours": jours,
            "message": "" if jours >= 20 else f"Historique en construction ({jours} jour(s)) : les tendances apparaîtront après environ 20 séances."}
