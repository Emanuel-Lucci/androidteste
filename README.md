# SoundML — Plataforma de Manutenção Preditiva
## Estrutura do Projeto

```
soundml/
├── app.py                  ← API REST Flask (backend)
├── database.py             ← Schema SQLite + seed demo
├── index.html              ← Painel web (SPA)
├── 2_treinar_modelo.py     ← Script de treino com librosa
├── 3_diagnosticar.py       ← Diagnóstico de arquivo .wav/.mp3
├── 4_monitoramento_tempo_real.py  ← Monitoramento via microfone
├── converter_mp3_para_wav.py      ← Conversão de áudios
├── requirements.txt
├── soundml.db              ← Banco SQLite (criado ao rodar)
├── dataset/                ← Áudios de treino por classe
│   ├── normal/
│   ├── rolamento_gasto/
│   ├── correia_frouxa/
│   └── desbalanceamento/
└── modelos/                ← Modelos .pkl treinados
```

## Como rodar

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Iniciar o servidor
```bash
python app.py
```
Acesse: http://localhost:5000

### 3. Fluxo completo

**Passo 1** — Abra o painel e vá em **Classes** para verificar/adicionar tipos de condição

**Passo 2** — Vá em **Amostras de Áudio**, arraste arquivos .mp3/.wav e classifique-os
- A pasta `dataset/` organiza os áudios por subpasta (uma por classe)
- O painel salva os metadados + features no banco `soundml.db`

**Passo 3** — Vá em **Treinar Modelo**, configure os parâmetros e clique em Iniciar
- O painel salva o resultado no banco
- O botão "Baixar script .py" gera o `2_treinar_modelo.py` configurado com suas classes

**Passo 4** — Use o script `.py` baixado para treinar o modelo REAL com librosa:
```bash
python 2_treinar_modelo.py
# gera: modelos/modelo_v1.pkl e modelos/classes_v1.pkl
```

**Passo 5** — Diagnóstico:
```bash
# Via script:
python 3_diagnosticar.py --arquivo minha_gravacao.wav

# Via painel web:
# Aba "Diagnosticar" → selecione o arquivo → clique Diagnosticar
```

**Passo 6** — Monitoramento contínuo (microfone):
```bash
python 4_monitoramento_tempo_real.py
```

## API REST

| Método | Endpoint               | Descrição                    |
|--------|------------------------|------------------------------|
| GET    | /api/dashboard         | Estatísticas gerais          |
| GET    | /api/amostra           | Lista amostras de áudio      |
| POST   | /api/amostra/batch     | Importa amostras em lote     |
| DELETE | /api/amostra/{id}      | Remove amostra               |
| GET    | /api/classe            | Lista classes/labels         |
| POST   | /api/classe            | Cria nova classe             |
| DELETE | /api/classe/{nome}     | Remove classe                |
| GET    | /api/modelo            | Lista modelos ML             |
| POST   | /api/modelo            | Registra modelo treinado     |
| PUT    | /api/modelo/{id}       | Atualiza / ativa modelo      |
| DELETE | /api/modelo/{id}       | Remove modelo                |
| GET    | /api/diagnostico       | Histórico de diagnósticos    |
| POST   | /api/diagnostico       | Registra diagnóstico         |
| DELETE | /api/diagnostico/clear | Limpa histórico              |
| GET    | /api/empresa           | Lista empresas               |
| GET    | /api/maquina           | Lista máquinas               |
| GET    | /api/sensor            | Lista sensores               |
| GET    | /api/alerta            | Lista alertas                |
| GET    | /api/os                | Lista ordens de serviço      |

## Aplicativo Android

O projeto Android está em `android/` e usa Kotlin + Jetpack Compose + Retrofit.

1. Configure `BASE_URL` em `android/app/src/main/java/br/com/soundml/app/Api.kt` com a URL HTTPS do servidor.
2. Abra a pasta `android/` no Android Studio e execute o app em um aparelho físico.
3. O botão de diagnóstico grava WAV PCM 16-bit mono a 22050 Hz e envia `multipart/form-data` para `POST /api/diagnosticar`.
4. O endpoint exige `Authorization: Bearer <JWT>`, verifica a `empresa_id` do usuário e grava o histórico.
5. `ContinuousMonitoringService` é a base do monitoramento em primeiro plano. FCM exige cadastrar um projeto Firebase e adicionar o `google-services.json` antes de publicar notificações remotas.

### Backend em produção

Defina `SOUNDML_JWT_SECRET` com uma chave aleatória de pelo menos 32 caracteres e execute com Gunicorn (`Procfile`) atrás de HTTPS. O banco SQLite é adequado para protótipo; para múltiplas empresas em produção, prefira PostgreSQL e mantenha todos os filtros por `empresa_id`.

## Banco de Dados (soundml.db)

12 tabelas SQLite:
- **empresa** — clientes da plataforma
- **usuario** — gestores e técnicos
- **planta** — unidades fabris
- **maquina** — equipamentos monitorados
- **classe_audio** — labels do modelo ML
- **amostra_audio** — dataset de treino (metadados + features)
- **modelo_ml** — modelos treinados e versionados
- **sensor** — dispositivos IoT
- **alerta** — anomalias detectadas
- **diagnostico** — histórico de análises
- **ordem_servico** — tarefas de manutenção
- **historico_os** — log imutável de ações
