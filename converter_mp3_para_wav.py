from pydub import AudioSegment
import glob, os

for mp3 in glob.glob("dataset/**/*.mp3", recursive=True):
    wav = mp3.replace(".mp3", ".wav")
    AudioSegment.from_mp3(mp3).export(wav, format="wav")
    print(f"✅ Convertido: {mp3} → {wav}")