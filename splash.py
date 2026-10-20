# -*- coding: utf-8 -*-
"""splash.py - opstart-splashscherm met het Dravenlock-logo.

Toont het logo + een laadtekst tot de app klaar is. Zo zie je bij het opstarten
(en tijdens het laden/downloaden van het model) een net scherm in plaats van een
zwart venster of een console. Gedeeld door de Drave-apps.
"""
from __future__ import annotations

import os
import sys
import time

import pygame


def resource_path(rel):
    """Vind een bestand zowel los (dev) als in de PyInstaller-build (onedir/onefile)."""
    cands = []
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        cands.append(os.path.join(mp, rel))
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(here, rel))
    cands.append(os.path.join(here, "..", rel))   # gedeelde assets-map naast de app
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[-1]


def load_logo():
    # transparante versie (logo_t.png) heeft de voorkeur: geen zwart vierkant
    names = ("logo_t.png", os.path.join("assets", "logo_t.png"),
             "logo.png", os.path.join("assets", "logo.png"))
    for name in names:
        try:
            p = resource_path(name)
            if os.path.exists(p):
                return pygame.image.load(p)
        except Exception:
            pass
    return None


def set_window_icon():
    """Zet het venster-/taakbalk-icoon op het logo (indien aanwezig)."""
    try:
        img = load_logo()
        if img is not None:
            pygame.display.set_icon(img)
    except Exception:
        pass


def run_splash(screen, clock, title, status_fn=None, is_ready=None,
               min_seconds=1.4, max_seconds=600.0, bg=(8, 8, 10)):
    """Toon het splashscherm tot (min_seconds verstreken EN is_ready() True) of
    tot max_seconds. status_fn() mag een laadtekst teruggeven (bv. 'Model laden')."""
    W, H = screen.get_size()
    logo = load_logo()
    if logo is not None:
        try:
            logo = logo.convert_alpha()
        except Exception:
            pass
        target_h = int(H * 0.58)
        if logo.get_height() > 0:
            scale = target_h / logo.get_height()
            logo = pygame.transform.smoothscale(
                logo, (max(1, int(logo.get_width() * scale)), target_h))
    f_title = pygame.font.Font(None, max(40, int(H * 0.11)))
    f_sub = pygame.font.Font(None, max(22, int(H * 0.05)))
    t0 = time.time()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
        el = time.time() - t0
        ready = (is_ready is None) or bool(is_ready())
        done = (el >= min_seconds and ready) or (el >= max_seconds)
        screen.fill(bg)
        y = int(H * 0.12)
        if logo is not None:
            screen.blit(logo, ((W - logo.get_width()) // 2, y))
            y += logo.get_height() + 14
        else:
            y = int(H * 0.40)
        ts = f_title.render(title, True, (235, 235, 240))
        screen.blit(ts, ((W - ts.get_width()) // 2, y))
        # statustekst + animatie-puntjes
        msg = ""
        if status_fn is not None:
            try:
                msg = status_fn() or ""
            except Exception:
                msg = ""
        if not msg:
            msg = "Laden"
        dots = "." * (1 + int(el * 2) % 3)
        ss = f_sub.render(msg + dots, True, (150, 150, 160))
        screen.blit(ss, ((W - ss.get_width()) // 2, H - int(H * 0.13)))
        pygame.display.flip()
        clock.tick(60)
        if done:
            return
