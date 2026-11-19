# -*- coding: utf-8 -*-
"""Cryptomonnaies : sélection automatique parmi les 250 premières (CoinGecko, gratuit), pas seulement les plus grosses."""

import json
import re
import urllib.request

STABLES = {"usdt", "usdc", "dai", "fdusd", "tusd", "usde", "pyusd", "usdd", "busd", "usds", "frax", "gusd", "lusd",
           "usdp", "eurc", "eurs", "usd0", "susde", "usdy", "rlusd", "usdtb", "usdf", "usdg", "bfusd", "usd1", "xaut", "paxg"}
EMBALLES = re.compile(r"^(w|st|wst|we|cb|r|m|bs|ez|os|sw|jito|b|lst)?(btc|eth|sol|bnb|avax|matic|pol)$|^(steth|weeth|reth|cbeth|wbeth|meth|ezeth|rseth|jitosol|msol|bnsol|lbtc|solvbtc|tbtc|cbbtc|wbtc|weth|clbtc)$")


def log(m):
    print(f"[crypto] {m}", flush=True)


def marche_coingecko():
    url = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1"
           "&price_change_percentage=7d,30d,1y")
    req = urllib.request.Request(url, headers={"User-Agent": "SignalBourse/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def selection(garder=18):
    """Retourne des entrées prêtes à analyser (ticker Yahoo « XXX-USD »), triées par potentiel préliminaire."""
    try:
        data = marche_coingecko()
    except Exception as ex:
        log(f"CoinGecko indisponible : {ex}")
        return []
    candidats = []
    for c in data:
        sym = (c.get("symbol") or "").lower()
        if sym in STABLES or EMBALLES.match(sym) or not c.get("market_cap"):
            continue
        rang = c.get("market_cap_rank") or 999
        vol, cap = c.get("total_volume") or 0, c.get("market_cap") or 1
        p30 = (c.get("price_change_percentage_30d_in_currency") or 0) / 100
        p1a = c.get("price_change_percentage_1y_in_currency")
        p1a = p1a / 100 if p1a is not None else 0
        ath = (c.get("ath_change_percentage") or 0) / 100
        s = 0.0
        s += 0.25 if 10 <= rang <= 150 else 0.1 if rang < 10 else 0.0       # pas forcément les plus grosses
        s += min(vol / cap, 0.3)                                            # échanges suffisants
        s += max(-0.4, min(p30, 0.6)) * 0.6                                 # reprise récente
        s += max(-0.3, min(p1a, 1.0)) * 0.2
        if -0.85 < ath < -0.40 and p30 > 0:                                 # loin du record mais repart
            s += 0.2
        if p30 > 1.0:                                                       # emballement : prudence
            s -= 0.3
        candidats.append({"ticker": f"{sym.upper()}-USD", "nom": c.get("name", sym.upper()), "type": "Crypto",
                          "theme": f"Rang n°{rang} mondial", "rang": rang, "recherche": f"{c.get('name')} crypto",
                          "ath_ecart": ath, "score_prelim": s})
    candidats.sort(key=lambda x: -x["score_prelim"])
    base = [x for x in candidats if x["ticker"] in ("BTC-USD", "ETH-USD")]
    autres = [x for x in candidats if x["ticker"] not in ("BTC-USD", "ETH-USD")][:garder * 2]
    log(f"{len(candidats)} cryptos éligibles, {len(autres)} présélectionnées")
    return base + autres
