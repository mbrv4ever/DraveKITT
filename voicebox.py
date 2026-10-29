# -*- coding: utf-8 -*-
"""voicebox.py - het KITT voice-box dashboard (Dravenlock-interpretatie).

Tekent het middenstuk: drie kolommen rode segmentbalkjes (equalizer/VU) die
meebewegen met de spraak-amplitude, met een groene NORMAL-knop + klein groen
indicatortje, en labelknoppen links (ALT, OIL PRESS, OIL TEMP, EGT, FUEL) en
rechts (AUX, SAT COMM, ACC, RADAR, MPI).

Geen echte Knight Rider-logo's of -audio: dit is een eigen look-and-feel.
Dit is NIET de scanner op de motorkap, maar de voice box in het dashboard.
"""
from __future__ import annotations

import math
import random

import pygame

# kleuren
BLACK = (8, 8, 10)
PANEL = (16, 16, 19)
SEG_ON = (236, 46, 30)
SEG_TOP = (250, 90, 60)
SEG_OFF = (46, 12, 10)
AMBER = (206, 198, 120)
GOLD = (212, 175, 90)
AMBER_OFF = (120, 114, 64)
REDBTN = (206, 64, 52)
REDBTN_OFF = (110, 40, 34)
GREEN = (78, 206, 92)
GREEN_OFF = (24, 56, 30)
DARKTXT = (18, 14, 10)
MUTE = (120, 120, 128)

LEFT = [("TIJD", "amber"), ("ACCU", "amber"), ("SYSTEEM", "red"),
        ("GRAP", "red"), ("WEER", "red")]
RIGHT = [("HERHAAL", "amber"), ("NIEUWS", "amber"), ("NIEUW", "red"),
         ("SCAN", "red"), ("HULP", "red")]

SEGS = 16
COL_W = 30
COL_GAP = 16
SEG_H = 12
SEG_GAP = 4


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class KittPanel:
    def __init__(self):
        self.col = [0.0, 0.0, 0.0]      # gladgestreken hoogte per kolom
        self.scales = [0.74, 1.0, 0.78]  # middelste kolom het hoogst
        self.buttons = {}               # label -> pygame.Rect (voor klikken)

    def draw(self, surf, level, state, t, highlight=None):
        self.buttons = {}
        surf.fill(BLACK)
        W, H = surf.get_size()
        cx = W // 2
        total = 3 * COL_W + 2 * COL_GAP
        x0 = cx - total // 2
        top = 64
        col_h = SEGS * (SEG_H + SEG_GAP)

        # donkere behuizing achter de kolommen
        pad = 18
        pygame.draw.rect(surf, PANEL, (x0 - pad, top - pad, total + 2 * pad, col_h + 2 * pad + 80),
                         border_radius=14)

        # --- de drie VU-kolommen ---
        for c in range(3):
            # per kolom een eigen, levendige beweging rond het basisniveau
            wobble = 0.10 * math.sin(t * 9 + c * 1.7) + 0.06 * random.random()
            base = level * self.scales[c]
            target = clamp(base + (wobble if level > 0.02 else 0.0), 0.0, 1.0)
            self.col[c] += (target - self.col[c]) * 0.55
            lit = int(round(self.col[c] * SEGS))
            colx = x0 + c * (COL_W + COL_GAP)
            for s in range(SEGS):
                yy = top + (SEGS - 1 - s) * (SEG_H + SEG_GAP)
                if s < lit:
                    color = SEG_TOP if s >= lit - 1 else SEG_ON
                else:
                    color = SEG_OFF
                pygame.draw.rect(surf, color, (colx, yy, COL_W, SEG_H), border_radius=2)

        # --- NORMAL-knop + klein groen indicatortje eronder ---
        ny = top + col_h + 18
        ind_w = 22
        ind = clamp(self.col[1], 0.0, 1.0)
        ind_lit = int(round(ind * 5))
        for s in range(5):
            yy = ny + (4 - s) * 8
            col = GREEN if s < ind_lit else GREEN_OFF
            pygame.draw.rect(surf, col, (x0 + 2, yy, ind_w, 6), border_radius=2)
        self._button(surf, (x0 + ind_w + 12, ny, total - ind_w - 12, 34), "NORMAL", GREEN, big=False)

        # --- labelknoppen links en rechts ---
        bw, bh, gap = 104, 46, 14
        bx_left = x0 - 30 - bw
        bx_right = x0 + total + 30
        bt = top - 6
        for i, (lbl, kind) in enumerate(LEFT):
            self._label_btn(surf, (bx_left, bt + i * (bh + gap), bw, bh), lbl, kind, highlight)
        for i, (lbl, kind) in enumerate(RIGHT):
            self._label_btn(surf, (bx_right, bt + i * (bh + gap), bw, bh), lbl, kind, highlight)

        # subtiele titel boven
        f = pygame.font.Font(None, 26)
        img = f.render("IGNITION", True, (150, 40, 30))
        surf.blit(img, img.get_rect(center=(cx, 30)))

    def _label_btn(self, surf, rect, label, kind, highlight=None):
        face = AMBER if kind == "amber" else REDBTN
        if highlight == label:
            face = mixc(face, (255, 255, 255), 0.5)   # oplichten bij indrukken
        self.buttons[label] = pygame.Rect(rect)
        self._button(surf, rect, label, face, big=True)

    def _button(self, surf, rect, label, face, big=True):
        x, y, w, h = rect
        r = pygame.Rect(x, y, w, h)
        # bevel: donkere rand + lichte bovenkant
        pygame.draw.rect(surf, (0, 0, 0), r.inflate(6, 6), border_radius=8)
        pygame.draw.rect(surf, mixc(face, (0, 0, 0), 0.35), r, border_radius=8)
        inner = r.inflate(-6, -6)
        pygame.draw.rect(surf, face, inner, border_radius=6)
        pygame.draw.rect(surf, mixc(face, (255, 255, 255), 0.35),
                         (inner.x, inner.y, inner.w, max(4, inner.h // 3)), border_radius=6)
        f = pygame.font.Font(None, 24 if big else 28)
        # label kan twee woorden zijn -> eventueel over twee regels
        if " " in label and big and f.size(label)[0] > inner.w - 8:
            a, b = label.split(" ", 1)
            i1 = f.render(a, True, DARKTXT)
            i2 = f.render(b, True, DARKTXT)
            surf.blit(i1, i1.get_rect(center=(r.centerx, r.centery - 9)))
            surf.blit(i2, i2.get_rect(center=(r.centerx, r.centery + 9)))
        else:
            img = f.render(label, True, DARKTXT)
            surf.blit(img, img.get_rect(center=r.center))


def mixc(c1, c2, x):
    return (int(c1[0] + (c2[0] - c1[0]) * x),
            int(c1[1] + (c2[1] - c1[1]) * x),
            int(c1[2] + (c2[2] - c1[2]) * x))
