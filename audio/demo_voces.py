#!/usr/bin/env python3
"""Genera muestras de voz para elegir estilo. Solo para la rama demo-voz."""

import asyncio
from pathlib import Path
import sys

import edge_tts
from imageio_ffmpeg import get_ffmpeg_exe

sys.path.insert(0, str(Path(__file__).parent))
import radio  # noqa: E402

TEXTO = """Son las siete de la tarde en Madrid y esto es Cierre de Mercados. Europa ya ha bajado la persiana. Wall Street lleva tres horas y media en juego.

El titular del día. El Banco Central Europeo deja los tipos donde estaban, y el mercado lo celebra sin aspavientos. El Ibex treinta y cinco cierra con una subida del cero coma ocho por ciento.

Vamos con tu cartera. Nvidia sube un dos por ciento a media sesión. Y eso llega directo a tu Fidelity World, donde pesa casi un tres por ciento.

Esta noche, ojo a los resultados de Microsoft tras el cierre americano. Hasta aquí el cierre. Mañana, más."""

MUESTRAS = [
    # nombre,              voz,                   ritmo,  tono,   estilo
    ("0_actual_referencia", "es-ES-AlvaroNeural", "+5%",  "+0Hz", None),
    ("A_alvaro_FM80",       "es-ES-AlvaroNeural", "+12%", "-5Hz", "fm"),
    ("B_alvaro_AM80",       "es-ES-AlvaroNeural", "+12%", "-5Hz", "am"),
    ("C_jorge_FM80",        "es-MX-JorgeNeural",  "+10%", "-4Hz", "fm"),
]


async def main() -> None:
    voces = await edge_tts.list_voices()
    print("Voces masculinas en espanol:",
          sorted(v["ShortName"] for v in voces
                 if v["Locale"].startswith("es-") and v["Gender"] == "Male"))

    salida = Path("muestras")
    salida.mkdir(exist_ok=True)
    ffmpeg = get_ffmpeg_exe()
    for nombre, voz, ritmo, tono, estilo in MUESTRAS:
        crudo = salida / f"{nombre}_crudo.mp3"
        await edge_tts.Communicate(TEXTO, voz, rate=ritmo, pitch=tono).save(str(crudo))
        final = salida / f"{nombre}.mp3"
        if estilo:
            radio.ambientar(crudo, final, ffmpeg=ffmpeg, estilo=estilo)
            crudo.unlink()
        else:
            crudo.rename(final)
        print("ok", final)


if __name__ == "__main__":
    asyncio.run(main())
