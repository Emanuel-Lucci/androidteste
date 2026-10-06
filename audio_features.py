"""Utilitários compartilhados entre treino, diagnóstico e API."""
from pathlib import Path
import librosa
import numpy as np

SAMPLE_RATE = 22_050
ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "modelos"
MODEL_PATH = MODELS_DIR / "modelo_v1.pkl"
ENCODER_PATH = MODELS_DIR / "classes_v1.pkl"
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3"}


def extrair_features(arquivo_or_array, sr=SAMPLE_RATE):
    """Gera o vetor de features usado em treino e inferência."""
    if isinstance(arquivo_or_array, (str, Path)):
        y, loaded_sr = librosa.load(str(arquivo_or_array), sr=sr, mono=True)
        sr = loaded_sr
    else:
        y = np.asarray(arquivo_or_array, dtype=np.float32)
        if y.ndim != 1:
            y = np.mean(y, axis=1)
    if y.size == 0:
        raise ValueError("Áudio vazio")

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    return np.concatenate([
        np.mean(mfcc, axis=1),
        np.std(mfcc, axis=1),
        [
            np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)),
            np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)),
            np.mean(librosa.feature.zero_crossing_rate(y=y)),
            np.mean(librosa.feature.rms(y=y)),
            np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)),
        ],
        np.mean(contrast, axis=1),
    ]).astype(np.float32)


def validar_audio_filename(filename):
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError("Formato não suportado. Envie um arquivo .wav ou .mp3")
    return ext
