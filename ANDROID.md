# SoundML Android

Projeto Kotlin + Jetpack Compose que usa o microfone do celular e envia WAV PCM para a API Flask.

## Fluxo implementado

- Login em `POST /api/auth/login` com JWT.
- Gravação por `AudioRecord`: mono, PCM 16-bit, 22050 Hz, janela de 3 segundos.
- Diagnóstico em `POST /api/diagnosticar`, campo multipart `arquivo`.
- Monitoramento contínuo opcional como Foreground Service, com uma janela de 3 segundos por ciclo.
- Notificação persistente do serviço e alerta quando uma classe diferente de `normal` supera 75% de confiança.
- Backend filtra o modelo pela `empresa_id` presente no token.

## Configurar a API

Edite `android/app/build.gradle.kts` e substitua:

```kotlin
buildConfigField("String", "SOUNDML_API_URL", "\"https://SEU-DOMINIO.example/\"")
```

A URL deve ser HTTPS e terminar com `/`. Em desenvolvimento local, use o endereço acessível pelo aparelho/emulador, não `localhost` do celular.

## Compilar

1. Abra a pasta `android/` no Android Studio.
2. Aguarde o Gradle Sync.
3. Execute em aparelho físico ou emulador com microfone.
4. Gere o APK em **Build > Build APK(s)**.

Pela linha de comando, com Android SDK configurado:

```bash
cd android
./gradlew assembleDebug
```

O APK será gerado em `android/app/build/outputs/apk/debug/app-debug.apk`.

## Backend

Na raiz do projeto:

```bash
pip install -r requirements.txt
export SOUNDML_JWT_SECRET='uma-chave-secreta-forte'
python app.py
```

Antes de diagnosticar, é necessário treinar e registrar um modelo ativo no servidor. O modelo demo não representa acurácia de produção. Treine com gravações feitas no mesmo celular, distância e ambiente do uso real.

## Observações

- O serviço contínuo exige consentimento explícito e mantém uma notificação ativa.
- O Android deve conceder as permissões de microfone; em versões recentes, permita também notificações para visualizar alertas.
- O sandbox desta entrega não possui Android SDK, portanto a estrutura Gradle foi validada, mas o APK não pôde ser gerado aqui. No Android Studio, o SDK é instalado/configurado normalmente.
