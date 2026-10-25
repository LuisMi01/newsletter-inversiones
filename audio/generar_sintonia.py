#!/usr/bin/env python3
"""
Genera la sintonia original del briefing: un "station ID" de radio financiera
de los 80 (campanas FM, stab de metales sinteticos, teletipo de fondo).

Todo se sintetiza desde cero con numpy: no hay samples ni musica de terceros.

Uso:
    python audio/generar_sintonia.py      # escribe audio/sintonia_intro.wav y audio/sintonia_cierre.wav
"""

from pathlib import Path
import wave

import numpy as np

SR = 44_100
AQUI = Path(__file__).parent
rng = np.random.default_rng(1987)


def nota(n: str) -> float:
    """'C4' -> Hz."""
    nombres = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6,
               "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    nombre, octava = n[:-1], int(n[-1])
    midi = 12 * (octava + 1) + nombres[nombre]
    return 440.0 * 2 ** ((midi - 69) / 12)


def t(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur)) / SR


def adsr(n: int, a=0.005, d=0.15, s=0.6, r=0.2) -> np.ndarray:
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(0, n - a_n - d_n - r_n)
    env = np.concatenate([
        np.linspace(0, 1, a_n, endpoint=False),
        np.linspace(1, s, d_n, endpoint=False),
        np.full(s_n, s),
        np.linspace(s, 0, r_n),
    ])
    return env[:n] if len(env) >= n else np.pad(env, (0, n - len(env)))


def campana_fm(f: float, dur: float) -> np.ndarray:
    """Campana tipo DX7: portadora con moduladora inarmonica que decae."""
    x = t(dur)
    indice = 3.5 * np.exp(-x * 6)
    sen = np.sin(2 * np.pi * f * x + indice * np.sin(2 * np.pi * f * 3.5 * x))
    return sen * np.exp(-x * 3.2)


def sierra(f: float, x: np.ndarray) -> np.ndarray:
    return 2 * ((f * x) % 1.0) - 1


def lowpass(sig: np.ndarray, corte: np.ndarray | float) -> np.ndarray:
    """Filtro de un polo con frecuencia de corte variable (barrido de metales)."""
    corte = np.broadcast_to(corte, sig.shape)
    alfa = 1 - np.exp(-2 * np.pi * corte / SR)
    out = np.empty_like(sig)
    y = 0.0
    for i, (s, a) in enumerate(zip(sig, alfa)):
        y += a * (s - y)
        out[i] = y
    return out


def metales(freqs: list[float], dur: float) -> np.ndarray:
    """Stab de 'brass' sintetico: sierras desafinadas con barrido de filtro."""
    x = t(dur)
    mezcla = np.zeros_like(x)
    for f in freqs:
        for desafine in (-0.07, 0.0, 0.07):
            mezcla += sierra(f * 2 ** (desafine / 12), x)
    mezcla /= len(freqs) * 3
    barrido = 600 + 5200 * np.exp(-x * 5) + 900 * np.exp(-x * 0.8)
    mezcla = lowpass(lowpass(mezcla, barrido), barrido)
    return mezcla * adsr(len(x), a=0.012, d=0.35, s=0.45, r=min(0.9, dur * 0.5))


def bajo(f: float, dur: float) -> np.ndarray:
    x = t(dur)
    sig = np.sin(2 * np.pi * f * x) + 0.35 * np.sin(2 * np.pi * 2 * f * x)
    return sig * np.exp(-x * 2.2) * adsr(len(x), a=0.004, d=0.1, s=0.8, r=0.3)


def golpe(dur: float = 0.6) -> np.ndarray:
    """Golpe tipo timbal electronico para marcar el stab."""
    x = t(dur)
    f = 55 * (1 + 2.5 * np.exp(-x * 30))
    fase = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(fase) * np.exp(-x * 7) + 0.25 * rng.normal(size=len(x)) * np.exp(-x * 40)


def teletipo(dur: float, bpm: float = 120) -> np.ndarray:
    """Clicks mecanicos a semicorcheas, como una maquina de teletipo."""
    out = np.zeros(int(SR * dur))
    paso = int(SR * 60 / bpm / 4)
    click = rng.normal(size=int(0.012 * SR)) * np.exp(-np.arange(int(0.012 * SR)) / (0.0025 * SR))
    click = np.diff(np.concatenate([[0], click]))  # mas agudo, mas "tecla"
    for k, i in enumerate(range(0, len(out) - len(click), paso)):
        acento = 1.0 if k % 4 == 0 else 0.55 + 0.25 * rng.random()
        out[i:i + len(click)] += click * acento
    return out


def colocar(pista: np.ndarray, sonido: np.ndarray, en: float, gan: float = 1.0) -> None:
    i = int(en * SR)
    fin = min(len(pista), i + len(sonido))
    pista[i:fin] += gan * sonido[:fin - i]


def normalizar(sig: np.ndarray, pico_db: float = -1.0) -> np.ndarray:
    sig = np.tanh(sig * 1.4) / np.tanh(1.4)          # saturacion suave, color de cinta
    return sig / np.max(np.abs(sig)) * 10 ** (pico_db / 20)


def guardar(sig: np.ndarray, ruta: Path) -> None:
    datos = (np.clip(sig, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(datos.tobytes())


def intro() -> np.ndarray:
    """~5 s: arpegio de campanas sobre teletipo, stab final en Re mayor con 9a."""
    dur = 5.2
    pista = np.zeros(int(SR * dur))
    negra = 0.5  # 120 bpm

    colocar(pista, teletipo(2.1), 0.0, 0.18)
    for k, n in enumerate(["D5", "F#5", "A5", "D6", "E6", "A5"]):
        colocar(pista, campana_fm(nota(n), 1.4), k * negra / 2, 0.30)

    colocar(pista, bajo(nota("D2"), 0.9), 0.0, 0.35)
    colocar(pista, bajo(nota("A1"), 0.9), 1.0, 0.35)

    # Golpe final: Dmaj9 (D-F#-A-C#-E) con metales, bajo y timbal
    stab = 2.0
    colocar(pista, golpe(), stab, 0.55)
    colocar(pista, bajo(nota("D2"), 2.6), stab, 0.5)
    colocar(pista, metales([nota(n) for n in ["D3", "A3", "C#4", "E4", "F#4"]], 3.0), stab, 0.75)
    colocar(pista, campana_fm(nota("F#6"), 2.5), stab, 0.22)
    colocar(pista, campana_fm(nota("A6"), 2.5), stab + 0.25, 0.16)

    # Cola: fade para que entre la voz por encima
    cola = int(3.6 * SR)
    pista[cola:] *= np.linspace(1, 0, len(pista) - cola) ** 1.5
    return normalizar(pista)


def cierre() -> np.ndarray:
    """~3 s: dos stabs (Bm9 -> Dmaj9) y campana final."""
    dur = 3.4
    pista = np.zeros(int(SR * dur))
    colocar(pista, golpe(0.4), 0.0, 0.35)
    colocar(pista, metales([nota(n) for n in ["B2", "F#3", "A3", "C#4", "D4"]], 0.45), 0.0, 0.6)
    colocar(pista, golpe(), 0.5, 0.5)
    colocar(pista, bajo(nota("D2"), 2.4), 0.5, 0.45)
    colocar(pista, metales([nota(n) for n in ["D3", "A3", "C#4", "E4", "F#4"]], 2.6), 0.5, 0.75)
    colocar(pista, campana_fm(nota("D6"), 2.6), 0.75, 0.25)
    cola = int(2.2 * SR)
    pista[cola:] *= np.linspace(1, 0, len(pista) - cola) ** 1.5
    return normalizar(pista)


if __name__ == "__main__":
    guardar(intro(), AQUI / "sintonia_intro.wav")
    guardar(cierre(), AQUI / "sintonia_cierre.wav")
    print("Sintonia generada en", AQUI)
