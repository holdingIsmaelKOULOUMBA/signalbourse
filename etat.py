# -*- coding: utf-8 -*-
"""Fichiers de données privés : stockés chiffrés dans le dépôt GitHub (public), avec une clé tirée du mot de passe du site.
Sans mot de passe (utilisation sur PC), les fichiers restent en clair."""

import base64
import hashlib
import os
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
FICHIERS = ["historique_signaux.csv", "derniers_signaux.json", "univers_auto.json", "fonds_13f.json",
            "selection.json", "calendrier_cache.json", "simulation_cache.json", "brvm_historique.csv", "fiches_cache.json"]
SEL = b"signalbourse-etat-v1"


def _cle():
    mdp = os.environ.get("SITE_PASSWORD")
    if not mdp:
        return None
    return hashlib.pbkdf2_hmac("sha256", mdp.encode(), SEL, 200000, dklen=32)


def ouvrir():
    """Au démarrage : déchiffre les fichiers .enc en fichiers de travail."""
    cle = _cle()
    if not cle:
        return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    for nom in FICHIERS:
        enc = DOSSIER / (nom + ".enc")
        if not enc.exists():
            continue
        brut = base64.b64decode(enc.read_bytes())
        try:
            (DOSSIER / nom).write_bytes(AESGCM(cle).decrypt(brut[:12], brut[12:], None))
        except Exception:
            print(f"[etat] impossible de déchiffrer {nom} (mot de passe changé ?) : fichier repris à zéro", flush=True)


def fermer():
    """À la fin : chiffre les fichiers de travail et supprime les versions en clair."""
    cle = _cle()
    if not cle:
        return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    for nom in FICHIERS:
        clair = DOSSIER / nom
        if not clair.exists():
            continue
        iv = os.urandom(12)
        (DOSSIER / (nom + ".enc")).write_bytes(base64.b64encode(iv + AESGCM(cle).encrypt(iv, clair.read_bytes(), None)))
        clair.unlink()
