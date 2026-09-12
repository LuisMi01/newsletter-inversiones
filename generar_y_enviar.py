#!/usr/bin/env python3
"""
Sintetiza el guion diario como MP3 y lo envia por correo.

Cadena: edge-tts (principal) -> Piper (respaldo local) -> SMTP Gmail.

Uso:
    python generar_y_enviar.py --guion guion.txt --titulares titulares.txt

Variables de entorno necesarias:
    GMAIL_USER           direccion remitente y destinataria
    GMAIL_APP_PASSWORD   contrasena de aplicacion de 16 caracteres

Dependencias (se instalan solas en el contenedor):
    pip install edge-tts piper-tts imageio-ffmpeg
"""

import argparse
import asyncio
import os
import smtplib
import subprocess
import sys
import tempfile
from datetime import date
from email.message import EmailMessage
from pathlib import Path

# --- Configuracion -----------------------------------------------------------

VOZ_EDGE = "es-ES-AlvaroNeural"
RITMO = "+5%"          # ligeramente por encima del natural, se escucha mejor de fondo
MODELO_PIPER = Path("voces/es_ES-davefx-medium.onnx")
MAX_CHARS = 3000       # troceo por parrafos para no abrir sesiones websocket largas
BITRATE = 48           # kbps, mono: ~2 MB para 5-6 minutos


# --- Sintesis ----------------------------------------------------------------

def trocear(texto: str, maximo: int = MAX_CHARS) -> list[str]:
    """Parte el guion en bloques por parrafos sin cortar frases."""
    trozos, actual = [], ""
    for parrafo in texto.split("\n\n"):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        if len(actual) + len(parrafo) + 2 > maximo and actual:
            trozos.append(actual)
            actual = parrafo
        else:
            actual = f"{actual}\n\n{parrafo}" if actual else parrafo
    if actual:
        trozos.append(actual)
    return trozos


async def _edge(texto: str, destino: Path) -> None:
    import edge_tts
    partes = []
    for i, trozo in enumerate(trocear(texto)):
        parcial = destino.with_suffix(f".{i:02d}.mp3")
        await edge_tts.Communicate(trozo, VOZ_EDGE, rate=RITMO).save(str(parcial))
        partes.append(parcial)
    # El formato por defecto de edge-tts ya es MP3 mono 48 kbps,
    # asi que basta concatenar los bytes: mismo codec y mismos parametros.
    with destino.open("wb") as salida:
        for parte in partes:
            salida.write(parte.read_bytes())
            parte.unlink()


def sintetizar_edge(texto: str, destino: Path) -> None:
    asyncio.run(_edge(texto, destino))
    if not destino.exists() or destino.stat().st_size < 10_000:
        raise RuntimeError("edge-tts devolvio un fichero vacio o truncado")


def sintetizar_piper(texto: str, destino: Path) -> None:
    """Respaldo local: no depende de ningun servicio externo."""
    import wave
    from piper import PiperVoice

    if not MODELO_PIPER.exists():
        raise FileNotFoundError(f"Falta el modelo de voz en {MODELO_PIPER}")

    voz = PiperVoice.load(str(MODELO_PIPER), config_path=f"{MODELO_PIPER}.json")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    with wave.open(str(wav_path), "wb") as wav:
        voz.synthesize_wav(texto, wav)

    from imageio_ffmpeg import get_ffmpeg_exe
    subprocess.run(
        [get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(wav_path),
         "-ac", "1", "-b:a", f"{BITRATE}k", str(destino)],
        check=True,
    )
    wav_path.unlink(missing_ok=True)


def sintetizar(texto: str, destino: Path) -> str:
    """Devuelve el motor que acabo funcionando."""
    try:
        sintetizar_edge(texto, destino)
        return "edge"
    except Exception as err:                      # noqa: BLE001
        print(f"[aviso] edge-tts fallo ({err}); pasando a Piper", file=sys.stderr)
        sintetizar_piper(texto, destino)
        return "piper"


# --- Envio -------------------------------------------------------------------

def duracion_min(mp3: Path) -> int:
    """Estimacion por tamano: fiable con bitrate constante."""
    segundos = mp3.stat().st_size * 8 / (BITRATE * 1000)
    return max(1, round(segundos / 60))


def enviar(mp3: Path, titulares: list[str], motor: str) -> None:
    usuario = os.environ["GMAIL_USER"]
    clave = os.environ["GMAIL_APP_PASSWORD"]
    hoy = date.today()
    minutos = duracion_min(mp3)

    cuerpo = [f"Briefing del {hoy.strftime('%d/%m/%Y')} — {minutos} min de audio.", ""]
    cuerpo += [f"- {t}" for t in titulares]
    if motor == "piper":
        cuerpo += ["", "(Generado con la voz de respaldo: edge-tts no respondio.)"]

    msg = EmailMessage()
    msg["From"] = usuario
    msg["To"] = usuario
    msg["Subject"] = f"Briefing {hoy.strftime('%d/%m')} — {minutos} min"
    msg.set_content("\n".join(cuerpo))
    msg.add_attachment(
        mp3.read_bytes(),
        maintype="audio",
        subtype="mpeg",
        filename=f"briefing-{hoy.isoformat()}.mp3",
    )

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as smtp:
        smtp.starttls()
        smtp.login(usuario, clave)
        smtp.send_message(msg)


def enviar_solo_texto(guion: str, motivo: str) -> None:
    """Ultimo recurso: si no hay audio, que al menos llegue el contenido."""
    usuario = os.environ["GMAIL_USER"]
    clave = os.environ["GMAIL_APP_PASSWORD"]
    hoy = date.today()

    msg = EmailMessage()
    msg["From"] = usuario
    msg["To"] = usuario
    msg["Subject"] = f"Briefing {hoy.strftime('%d/%m')} — SIN AUDIO"
    msg.set_content(f"No se pudo generar el audio.\nMotivo: {motivo}\n\n{guion}")

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as smtp:
        smtp.starttls()
        smtp.login(usuario, clave)
        smtp.send_message(msg)


# --- Entrada -----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guion", default="guion.txt")
    parser.add_argument("--titulares", default="titulares.txt")
    parser.add_argument("--salida", default="briefing.mp3")
    args = parser.parse_args()

    guion = Path(args.guion).read_text(encoding="utf-8").strip()
    if len(guion) < 500:
        print("[error] el guion esta vacio o es sospechosamente corto", file=sys.stderr)
        return 1

    titulares = [
        linea.strip(" -\t")
        for linea in Path(args.titulares).read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ][:3]

    mp3 = Path(args.salida)
    try:
        motor = sintetizar(guion, mp3)
    except Exception as err:                      # noqa: BLE001
        print(f"[error] ningun motor de voz funciono: {err}", file=sys.stderr)
        enviar_solo_texto(guion, str(err))
        return 1

    enviar(mp3, titulares, motor)
    print(f"Enviado: {mp3.name} ({mp3.stat().st_size // 1024} KB, motor={motor})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
