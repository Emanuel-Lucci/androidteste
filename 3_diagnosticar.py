"""Diagnóstico local compatível com a mesma pipeline usada pela API."""
import argparse
from pathlib import Path
import joblib

from audio_features import ENCODER_PATH, MODEL_PATH, extrair_features, validar_audio_filename

MENSAGENS = {
    "normal": "Máquina funcionando normalmente.",
    "rolamento_gasto": "Rolamento desgastado detectado! Agende substituição.",
    "correia_frouxa": "Correia frouxa detectada! Verifique a tensão.",
    "desbalanceamento": "Desbalanceamento detectado! Verifique o rotor.",
}


def diagnosticar(arquivo):
    validar_audio_filename(arquivo)
    if not MODEL_PATH.exists() or not ENCODER_PATH.exists():
        raise FileNotFoundError("Modelo não encontrado. Rode 2_treinar_modelo.py")
    modelo = joblib.load(MODEL_PATH)
    le = joblib.load(ENCODER_PATH)
    features = extrair_features(arquivo).reshape(1, -1)
    pred_idx = int(modelo.predict(features)[0])
    probs = modelo.predict_proba(features)[0]
    diagnostico = str(le.inverse_transform([pred_idx])[0])
    resultado = {
        "diagnostico": diagnostico,
        "confianca": float(probs[pred_idx]),
        "probabilidades": {str(classe): float(prob) for classe, prob in zip(le.classes_, probs)},
        "mensagem": MENSAGENS.get(diagnostico, f"Condição '{diagnostico}' detectada."),
    }
    print(f"Diagnóstico: {diagnostico.upper()} | Confiança: {resultado['confianca']:.1%}")
    print(resultado["mensagem"])
    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arquivo", required=True)
    args = parser.parse_args()
    if not Path(args.arquivo).exists():
        raise SystemExit(f"Arquivo não encontrado: {args.arquivo}")
    diagnosticar(args.arquivo)
