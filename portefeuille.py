# -*- coding: utf-8 -*-
"""Mon portefeuille : lu dans le secret GitHub PORTEFEUILLE (jamais dans un fichier public).

Format (une ligne par position) :
    TICKER;QUANTITE;PRIX_ACHAT_UNITAIRE[;TYPE]
    LIQUIDITES;MONTANT
Exemple :
    CW8.PA;3;512.40
    MC.PA;2;610
    BTC-USD;0.01;58000;Crypto
    LIQUIDITES;1500
Le prix d'achat est dans la devise du titre (euros pour Paris, dollars pour les actions américaines…).
"""

import os

CIBLE = {"Actions": 0.75, "Obligations": 0.20, "Or et matières premières": 0.05}


def lire():
    brut = os.environ.get("PORTEFEUILLE", "").strip()
    lignes, liquidites = [], 0.0
    for l in brut.replace(",", ".").replace("\r", "").split("\n"):
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        p = [x.strip() for x in l.split(";")]
        try:
            if p[0].upper() in ("LIQUIDITES", "LIQUIDITÉS", "CASH"):
                liquidites += float(p[1])
                continue
            lignes.append({"ticker": p[0].upper(), "quantite": float(p[1]), "prix_achat": float(p[2]),
                           "type": p[3] if len(p) > 3 and p[3] else None})
        except (IndexError, ValueError):
            print(f"[portefeuille] ligne ignorée (format attendu TICKER;QUANTITE;PRIX) : {l}", flush=True)
    return lignes, liquidites


def famille(r):
    t = r.get("type", "")
    if t == "Obligations":
        return "Obligations"
    if t in ("Matières premières",):
        return "Or et matières premières"
    if t == "Crypto":
        return "Crypto"
    return "Actions"


def construire(positions, analyses, conversion_eur):
    """positions : lignes lues ; analyses : {ticker: résultat d'analyse} ; conversion_eur(montant, devise) -> €."""
    _, liquidites = lire()
    lignes, total = [], liquidites
    for p in positions:
        r = analyses.get(p["ticker"])
        if not r:
            continue
        valeur_dev = r["prix"] * p["quantite"]
        valeur = conversion_eur(valeur_dev, r.get("devise") or "EUR") or valeur_dev
        cout = conversion_eur(p["prix_achat"] * p["quantite"], r.get("devise") or "EUR") or p["prix_achat"] * p["quantite"]
        lignes.append({"r": r, "quantite": p["quantite"], "prix_achat": p["prix_achat"], "valeur": valeur, "cout": cout,
                       "gain": valeur - cout, "gain_pct": (valeur / cout - 1) if cout else 0.0})
        total += valeur
    if not lignes:
        return None
    investi = sum(l["cout"] for l in lignes)
    valeur_titres = sum(l["valeur"] for l in lignes)
    for l in lignes:
        l["poids"] = l["valeur"] / total if total else 0
    repartition = {}
    for l in lignes:
        f = famille(l["r"])
        repartition[f] = repartition.get(f, 0) + l["valeur"] / total
    if liquidites:
        repartition["Liquidités"] = liquidites / total
    pays, secteurs = {}, {}
    for l in lignes:
        pays[l["r"].get("pays_siege") or l["r"].get("pays") or "Autre / ETF"] = pays.get(l["r"].get("pays_siege") or l["r"].get("pays") or "Autre / ETF", 0) + l["poids"]
        secteurs[l["r"].get("secteur") or "Non classé"] = secteurs.get(l["r"].get("secteur") or "Non classé", 0) + l["poids"]
    conseils = []
    for l in sorted(lignes, key=lambda l: -l["poids"]):
        r = l["r"]
        if l["poids"] > 0.15 and r["type"] == "Action":
            conseils.append(f"{r['nom']} pèse {l['poids']:.0%} de ton portefeuille : c'est beaucoup pour une seule action, pense à alléger.")
        if r["signal_lt"] in ("ALLÉGER", "VENDRE"):
            conseils.append(f"{r['nom']} est passé à « {r['signal_lt'].lower()} » sur le long terme : regarde la fiche pour comprendre pourquoi.")
        if r["prix"] <= r["stop"]:
            conseils.append(f"{r['nom']} est passé sous son seuil de protection ({r['stop']:.2f}) : à surveiller de près.")
        if r["type"] == "Crypto" and l["poids"] > 0.10:
            conseils.append(f"Les cryptos ({r['nom']}) dépassent 10 % de ton portefeuille : risque très élevé.")
    for f, cible in CIBLE.items():
        ecart = repartition.get(f, 0) - cible
        if abs(ecart) > 0.10:
            conseils.append(f"{f} : {repartition.get(f, 0):.0%} de ton portefeuille pour une cible d'environ {cible:.0%}. "
                            + ("Tu pourrais renforcer cette partie." if ecart < 0 else "Tu pourrais alléger cette partie."))
    if not conseils:
        conseils.append("Ton portefeuille est bien équilibré par rapport à ta cible. Rien d'urgent à faire.")
    return {"lignes": sorted(lignes, key=lambda l: -l["valeur"]), "total": total, "investi": investi,
            "valeur_titres": valeur_titres, "liquidites": liquidites, "gain": valeur_titres - investi,
            "gain_pct": (valeur_titres / investi - 1) if investi else 0.0, "repartition": repartition,
            "pays": dict(sorted(pays.items(), key=lambda x: -x[1])), "secteurs": dict(sorted(secteurs.items(), key=lambda x: -x[1])),
            "conseils": conseils}
