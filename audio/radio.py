"""
Ambientacion de "emisora financiera de los 80" para el briefing.

Toma la locucion ya sintetizada y la convierte en un programa de radio:
sintonia de entrada con la voz entrando sobre la cola, tratamiento de
emisora (EQ, compresion fuerte, saturacion de cinta, un punto de sala),
soplido de cinta muy bajo y sintonia de cierre.

Solo usa ffmpeg (el binario de imageio-ffmpeg en el Action).
"""

from pathlib import Path
import subprocess

AQUI = Path(__file__).parent
INTRO = AQUI / "sintonia_intro.wav"
CIERRE = AQUI / "sintonia_cierre.wav"

# Segundo de la sintonia en el que entra la voz (sobre la cola del golpe final)
ENTRADA_VOZ_MS = 3400

CADENAS = {
    # FM de los 80: graves con cuerpo, presencia marcada, compresion de emisora.
    # Es el estilo pensado para escuchar 5-6 minutos sin cansar.
    "fm": (
        "highpass=f=80,lowpass=f=11000,"
        "equalizer=f=140:t=q:w=1:g=3,"
        "equalizer=f=2800:t=q:w=1.2:g=3.5,"
        "equalizer=f=7500:t=q:w=1:g=-2,"
        "acompressor=threshold=-22dB:ratio=5:attack=4:release=120:makeup=5,"
        "asoftclip=type=tanh,"
        "aecho=0.85:0.6:18:0.07"
    ),
    # AM de transistor: banda estrecha y mas saturacion. Muy "de epoca",
    # pero cansa en audios largos.
    "am": (
        "highpass=f=300,lowpass=f=3600,"
        "equalizer=f=1500:t=q:w=1:g=4,"
        "acompressor=threshold=-26dB:ratio=8:attack=2:release=80:makeup=7,"
        "asoftclip=type=atan,"
        "aecho=0.8:0.5:14:0.06"
    ),
}

SOPLIDO = {"fm": 0.0025, "am": 0.006}  # amplitud del ruido rosa de cinta


def ambientar(voz: Path, salida: Path, ffmpeg: str = "ffmpeg",
              estilo: str = "fm", bitrate_k: int = 64) -> None:
    """voz (mp3/wav) -> salida (mp3) con sintonia y tratamiento de emisora."""
    cadena = CADENAS[estilo]
    filtro = (
        f"[1:a]aresample=44100,aformat=channel_layouts=mono,{cadena},"
        f"adelay={ENTRADA_VOZ_MS}[voz];"
        f"[0:a]aformat=channel_layouts=mono,volume=0.8[intro];"
        f"[intro][voz]amix=inputs=2:duration=longest:normalize=0[cuerpo];"
        f"[2:a]aformat=channel_layouts=mono,volume=0.8,adelay=350[cierre];"
        f"[cuerpo][cierre]concat=n=2:v=0:a=1[prog];"
        f"anoisesrc=color=pink:amplitude={SOPLIDO[estilo]}:sample_rate=44100,"
        f"aformat=channel_layouts=mono[cinta];"
        f"[prog][cinta]amix=inputs=2:duration=first:normalize=0,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    )
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error",
         "-i", str(INTRO), "-i", str(voz), "-i", str(CIERRE),
         "-filter_complex", filtro, "-map", "[out]",
         "-ac", "1", "-ar", "44100", "-b:a", f"{bitrate_k}k", str(salida)],
        check=True,
    )
