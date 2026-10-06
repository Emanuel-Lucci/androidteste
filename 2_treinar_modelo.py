"""Treina o modelo SoundML usando WAV ou MP3 capturados no mesmo cenário do app."""
from pathlib import Path
import glob
import joblib
import librosa
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from audio_features import MODELS_DIR, SAMPLE_RATE, extrair_features

PASTA_DATASET = Path(__file__).resolve().parent / "dataset"
ARQUIVO_MODELO = MODELS_DIR / "modelo_v1.pkl"
ARQUIVO_ENCODER = MODELS_DIR / "classes_v1.pkl"
EXTENSOES = ("*.wav", "*.WAV", "*.mp3", "*.MP3")


def main():
    print("=" * 50)
    print("  TREINAMENTO DO DETECTOR DE ANOMALIAS")
    print("=" * 50)
    X, y_labels = [], []
    for pasta_classe in sorted(p for p in PASTA_DATASET.iterdir() if p.is_dir()) if PASTA_DATASET.exists() else []:
        arquivos = sorted(sum((glob.glob(str(pasta_classe / ext)) for ext in EXTENSOES), []))
        if not arquivos:
            print(f"Classe '{pasta_classe.name}' sem .wav/.mp3, pulando...")
            continue
        print(f"\nClasse: {pasta_classe.name} ({len(arquivos)} arquivos)")
        for arquivo in arquivos:
            try:
                X.append(extrair_features(arquivo))
                y_labels.append(pasta_classe.name)
                print(f"   {Path(arquivo).name}")
            except Exception as exc:
                print(f"   Erro em {arquivo}: {exc}")

    if len(set(y_labels)) < 2:
        raise SystemExit("É preciso ter pelo menos 2 classes com áudio válido.")
    if min(y_labels.count(label) for label in set(y_labels)) < 2:
        raise SystemExit("Cada classe precisa de pelo menos 2 amostras para a divisão treino/teste.")

    le = LabelEncoder()
    y_encoded = le.fit_transform(y_labels)
    X = np.asarray(X)
    test_size = max(len(le.classes_), int(round(len(X) * 0.2)))
    if len(X) - test_size < len(le.classes_):
        test_size = len(le.classes_)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=test_size, random_state=42, stratify=y_encoded
    )
    modelo = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    modelo.fit(X_train, y_train)
    acuracia = accuracy_score(y_test, modelo.predict(X_test)) * 100
    print(f"\nAcurácia no teste: {acuracia:.1f}%")
    print(classification_report(y_test, modelo.predict(X_test), target_names=le.classes_, zero_division=0))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, ARQUIVO_MODELO)
    joblib.dump(le, ARQUIVO_ENCODER)
    print(f"Modelo salvo em: {ARQUIVO_MODELO}")
    print(f"Classes salvas em: {ARQUIVO_ENCODER}")


if __name__ == "__main__":
    main()
