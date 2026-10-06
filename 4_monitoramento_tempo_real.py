# ============================================================
# BÔNUS — MONITORAMENTO EM TEMPO REAL (opcional)
# ============================================================
# Usa o microfone/sensor ao vivo e classifica continuamente.
# Instalar: pip install pyaudio librosa scikit-learn joblib numpy
#
# Uso:
#   python 4_monitoramento_tempo_real.py

import pyaudio
import numpy as np
import librosa
import joblib
import wave
import os
import time
import tempfile


ARQUIVO_MODELO  = "modelo_maquina.pkl"
ARQUIVO_ENCODER = "classes.pkl"
SAMPLE_RATE     = 22050
DURACAO_JANELA  = 3      # segundos por análise
CHUNK           = 1024
FORMATO         = pyaudio.paInt16


def gravar_janela(stream, duracao=DURACAO_JANELA):
    """Grava uma janela de áudio da entrada."""
    frames = []
    for _ in range(int(SAMPLE_RATE / CHUNK * duracao)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
    return b"".join(frames)


def bytes_para_array(raw_bytes):
    """Converte bytes de áudio para array numpy."""
    audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
    audio /= 32768.0  # Normaliza para [-1, 1]
    return audio


def extrair_features(y, sr=SAMPLE_RATE):
    mfcc      = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std  = np.std(mfcc, axis=1)
    centroid  = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
    rolloff   = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
    zcr       = np.mean(librosa.feature.zero_crossing_rate(y))
    rms       = np.mean(librosa.feature.rms(y=y))
    bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
    contrast  = np.mean(librosa.feature.spectral_contrast(y=y, sr=sr), axis=1)

    return np.concatenate([
        mfcc_mean, mfcc_std,
        [centroid, rolloff, zcr, rms, bandwidth],
        contrast
    ])


def main():
    if not os.path.exists(ARQUIVO_MODELO):
        print("Modelo não encontrado. Rode primeiro o script 2_treinar_modelo.py")
        return

    modelo = joblib.load(ARQUIVO_MODELO)
    le     = joblib.load(ARQUIVO_ENCODER)

    p = pyaudio.PyAudio()
    stream = p.open(
        format=FORMATO,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    print("\nMonitoramento em tempo real iniciado!")
    print(f"   Analisando a cada {DURACAO_JANELA} segundos...")
    print("   Pressione Ctrl+C para parar.\n")
    print("-" * 50)

    try:
        while True:
            raw = gravar_janela(stream)
            y   = bytes_para_array(raw)

            features    = extrair_features(y).reshape(1, -1)
            pred_idx    = modelo.predict(features)[0]
            probs       = modelo.predict_proba(features)[0]
            diagnostico = le.inverse_transform([pred_idx])[0]
            confianca   = probs[pred_idx] * 100

            hora = time.strftime("%H:%M:%S")

            if diagnostico == "normal":
                icone = "✅"
            else:
                icone = "⚠️ "

            print(f"[{hora}] {icone} {diagnostico.replace('_',' ').upper():<25} {confianca:.0f}% confiança")

    except KeyboardInterrupt:
        print("\n\nMonitoramento encerrado.")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    main()