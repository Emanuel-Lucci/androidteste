"""
database.py — Banco SQLite para a Plataforma SoundML de Manutenção Preditiva
Executa direto: python database.py  →  cria soundml.db e dados demo
"""
import sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "soundml.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def uid():  return str(uuid.uuid4())
def now():  return datetime.now(timezone.utc).isoformat()
def hp(pw):
    """Hash seguro para novos usuários; hashes antigos são migrados no login."""
    import bcrypt
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
SCHEMA = """
-- ══════════════════════════════════════
--  1. EMPRESA
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS empresa (
    id        TEXT PRIMARY KEY,
    nome      TEXT NOT NULL,
    cnpj      TEXT NOT NULL UNIQUE,
    setor     TEXT,
    porte     TEXT CHECK(porte IN ('pequena','media','grande')),
    criado_em TEXT NOT NULL
);

-- ══════════════════════════════════════
--  2. USUARIO
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS usuario (
    id         TEXT PRIMARY KEY,
    empresa_id TEXT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil     TEXT NOT NULL CHECK(perfil IN ('admin','gestor','tecnico')),
    ativo      INTEGER NOT NULL DEFAULT 1,
    criado_em  TEXT NOT NULL
);

-- ══════════════════════════════════════
--  3. PLANTA
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS planta (
    id          TEXT PRIMARY KEY,
    empresa_id  TEXT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome        TEXT NOT NULL,
    localizacao TEXT,
    responsavel TEXT
);

-- ══════════════════════════════════════
--  4. MAQUINA
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS maquina (
    id            TEXT PRIMARY KEY,
    planta_id     TEXT NOT NULL REFERENCES planta(id) ON DELETE CASCADE,
    nome          TEXT NOT NULL,
    modelo        TEXT,
    fabricante    TEXT,
    numero_serie  TEXT,
    status        TEXT NOT NULL DEFAULT 'operando'
                  CHECK(status IN ('operando','em_alerta','em_manutencao','parado')),
    instalacao    TEXT,
    atualizado_em TEXT NOT NULL
);

-- ══════════════════════════════════════
--  5. CLASSE_AUDIO  (labels do modelo ML)
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS classe_audio (
    nome    TEXT PRIMARY KEY,
    descricao TEXT,
    icone   TEXT DEFAULT '📌',
    cor     TEXT DEFAULT '#00e5ff',
    mensagem TEXT,
    criado_em TEXT NOT NULL
);

-- ══════════════════════════════════════
--  6. AMOSTRA_AUDIO  (dataset de treino)
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS amostra_audio (
    id          TEXT PRIMARY KEY,
    nome        TEXT NOT NULL,
    classe      TEXT NOT NULL REFERENCES classe_audio(nome),
    maquina_id  TEXT REFERENCES maquina(id),
    caminho     TEXT,              -- path relativo dentro de /dataset/
    duracao     REAL,
    tamanho_kb  REAL,
    features    TEXT,              -- JSON: vetor numérico extraído pelo librosa
    notas       TEXT,
    criado_em   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_amostra_classe   ON amostra_audio(classe);
CREATE INDEX IF NOT EXISTS idx_amostra_maquina  ON amostra_audio(maquina_id);

-- ══════════════════════════════════════
--  7. MODELO_ML
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS modelo_ml (
    id             TEXT PRIMARY KEY,
    maquina_id     TEXT REFERENCES maquina(id),
    nome           TEXT NOT NULL,
    versao         TEXT NOT NULL,
    arquivo_pkl    TEXT NOT NULL,
    acuracia       REAL,
    n_estimators   INTEGER DEFAULT 200,
    n_mfcc         INTEGER DEFAULT 13,
    test_split     REAL    DEFAULT 0.2,
    random_state   INTEGER DEFAULT 42,
    classes_json   TEXT,           -- JSON: lista de classes usadas no treino
    amostras_treino INTEGER,
    ativo          INTEGER NOT NULL DEFAULT 0,
    treinado_em    TEXT NOT NULL
);

-- ══════════════════════════════════════
--  8. SENSOR
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS sensor (
    id             TEXT PRIMARY KEY,
    maquina_id     TEXT NOT NULL REFERENCES maquina(id) ON DELETE CASCADE,
    nome           TEXT NOT NULL,
    tipo           TEXT NOT NULL CHECK(tipo IN ('vibracao','temperatura','corrente','pressao','ruido')),
    unidade        TEXT NOT NULL,
    limiar_alerta  REAL,
    limiar_critico REAL,
    ativo          INTEGER NOT NULL DEFAULT 1,
    instalado_em   TEXT NOT NULL
);

-- ══════════════════════════════════════
--  9. ALERTA
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS alerta (
    id            TEXT PRIMARY KEY,
    sensor_id     TEXT NOT NULL REFERENCES sensor(id),
    modelo_ml_id  TEXT NOT NULL REFERENCES modelo_ml(id),
    severidade    TEXT NOT NULL CHECK(severidade IN ('aviso','critico','emergencia')),
    diagnostico   TEXT NOT NULL,
    confianca     REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'aberto'
                  CHECK(status IN ('aberto','em_analise','resolvido','falso_positivo')),
    gerado_em     TEXT NOT NULL,
    resolvido_em  TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerta_status ON alerta(status);

-- ══════════════════════════════════════
--  10. DIAGNOSTICO (histórico de análises)
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS diagnostico (
    id           TEXT PRIMARY KEY,
    arquivo      TEXT NOT NULL,
    diagnostico  TEXT NOT NULL,
    confianca    REAL NOT NULL,
    modelo_id    TEXT REFERENCES modelo_ml(id),
    modelo_nome  TEXT,
    probs_json   TEXT,             -- JSON: probabilidades por classe
    maquina_id   TEXT REFERENCES maquina(id),
    realizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_diag_data ON diagnostico(realizado_em);

-- ══════════════════════════════════════
--  11. ORDEM_SERVICO
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS ordem_servico (
    id          TEXT PRIMARY KEY,
    alerta_id   TEXT REFERENCES alerta(id),
    tecnico_id  TEXT REFERENCES usuario(id),
    gestor_id   TEXT REFERENCES usuario(id),
    descricao   TEXT NOT NULL,
    prioridade  TEXT NOT NULL CHECK(prioridade IN ('baixa','media','alta','urgente')),
    status      TEXT NOT NULL DEFAULT 'aberta'
                CHECK(status IN ('aberta','atribuida','em_execucao','concluida','cancelada')),
    aberta_em   TEXT NOT NULL,
    fechada_em  TEXT
);

-- ══════════════════════════════════════
--  12. HISTORICO_OS
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS historico_os (
    id            TEXT PRIMARY KEY,
    os_id         TEXT NOT NULL REFERENCES ordem_servico(id),
    usuario_id    TEXT NOT NULL REFERENCES usuario(id),
    acao          TEXT NOT NULL,
    observacao    TEXT,
    registrado_em TEXT NOT NULL
);
"""


def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)
    print(f"[DB] Banco criado/verificado: {DB_PATH}")


def seed_demo():
    with get_conn() as c:
        if c.execute("SELECT COUNT(*) FROM empresa").fetchone()[0] > 0:
            print("[DB] Dados demo já existem, pulando seed.")
            return

        # ── Empresa
        eid = uid()
        c.execute("INSERT INTO empresa VALUES (?,?,?,?,?,?)",
                  (eid,"Metalúrgica São Paulo Ltda.","12.345.678/0001-90","Metalurgia","grande",now()))

        # ── Usuários
        adm = uid(); ges = uid(); tec = uid()
        c.executemany("INSERT INTO usuario VALUES (?,?,?,?,?,?,?,?)", [
            (adm,eid,"Admin Sistema",  "admin@metalsp.com",  hp("admin123"), "admin",  1,now()),
            (ges,eid,"Carlos Mendes",  "carlos@metalsp.com", hp("gestor123"),"gestor", 1,now()),
            (tec,eid,"Diego Ferreira", "diego@metalsp.com",  hp("tec123"),   "tecnico",1,now()),
        ])

        # ── Planta
        pid = uid()
        c.execute("INSERT INTO planta VALUES (?,?,?,?,?)",
                  (pid,eid,"Unidade Guarulhos","Av. Guarulhos, 1500 — SP","Carlos Mendes"))

        # ── Máquinas
        m1=uid(); m2=uid()
        c.executemany("INSERT INTO maquina VALUES (?,?,?,?,?,?,?,?,?)",[
            (m1,pid,"Torno CNC #3",  "Romi GL 240","Romi", "SN-2021-0312","operando",  "2021-03-12",now()),
            (m2,pid,"Compressor A-12","Atlas GA 75","Atlas","SN-2019-0811","em_alerta", "2019-08-11",now()),
        ])

        # ── Classes de áudio
        c.executemany("INSERT INTO classe_audio VALUES (?,?,?,?,?,?)",[
            ("normal",          "Máquina operando normalmente",        "✅","#39d98a","Máquina funcionando normalmente.",now()),
            ("rolamento_gasto", "Rolamento com desgaste avançado",     "⚠️","#ffa940","Rolamento desgastado! Agende substituição.",now()),
            ("correia_frouxa",  "Correia com tensão abaixo do ideal",  "⚠️","#7c5cfc","Correia frouxa! Verifique a tensão.",now()),
            ("desbalanceamento","Desbalanceamento no rotor",            "🔴","#ff4d6d","Desbalanceamento detectado! Verifique o rotor.",now()),
        ])

        # ── Amostras demo
        import json, random
        for classe in ["normal","rolamento_gasto","correia_frouxa","desbalanceamento"]:
            for i in range(3):
                feats = [round(random.gauss(0,5),4) for _ in range(40)]
                c.execute("INSERT INTO amostra_audio VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (uid(),f"{classe}_{i+1:03d}.wav",classe,m1,
                     f"dataset/{classe}/{classe}_{i+1:03d}.wav",
                     round(random.uniform(2,5),2), round(random.uniform(50,200),1),
                     json.dumps(feats),"amostra demo",now()))

        # ── Modelo demo
        import json
        ml=uid()
        c.execute("INSERT INTO modelo_ml VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (ml,m1,"RandomForest Torno CNC#3","1.0.0",
                   "modelos/modelo_torno_v1.pkl",0.923,200,13,0.2,42,
                   json.dumps(["normal","rolamento_gasto","correia_frouxa","desbalanceamento"]),
                   12,1,now()))

        # ── Sensor
        s1=uid()
        c.execute("INSERT INTO sensor VALUES (?,?,?,?,?,?,?,?,?)",
                  (s1,m1,"Acelerômetro Frontal","vibracao","m/s²",3.5,7.0,1,now()))

        # ── Alerta
        al=uid()
        c.execute("INSERT INTO alerta VALUES (?,?,?,?,?,?,?,?,?)",
                  (al,s1,ml,"critico","rolamento_gasto",0.87,"aberto",now(),None))

        # ── OS
        os=uid()
        c.execute("INSERT INTO ordem_servico VALUES (?,?,?,?,?,?,?,?,?)",
                  (os,al,tec,ges,
                   "Substituir rolamento frontal do Torno CNC #3.",
                   "alta","atribuida",now(),None))

        # ── Histórico OS
        c.executemany("INSERT INTO historico_os VALUES (?,?,?,?,?,?)",[
            (uid(),os,ges,"criacao",   "OS criada pelo sistema preditivo.",now()),
            (uid(),os,ges,"atribuicao","Técnico Diego Ferreira atribuído.",now()),
        ])

        # ── Diagnósticos demo
        for diag in ["normal","rolamento_gasto","desbalanceamento"]:
            c.execute("INSERT INTO diagnostico VALUES (?,?,?,?,?,?,?,?,?)",
                (uid(),f"audio_{diag}.wav",diag,
                 round(random.uniform(0.7,0.97),3),ml,
                 "RandomForest Torno CNC#3",None,m1,now()))

    print("[DB] Dados de demonstração inseridos.")


if __name__ == "__main__":
    init_db()
    seed_demo()
    print("[DB] Pronto!")
