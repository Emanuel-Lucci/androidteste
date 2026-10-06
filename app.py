"""
app.py — API REST Flask · SoundML Manutenção Preditiva
Uso: python app.py  →  http://localhost:5000
"""
from flask import Flask, request, jsonify, send_from_directory, g
from database import get_conn, uid, now, init_db, seed_demo
from auth import hash_password, verify_password, is_legacy_hash, issue_token, require_auth
from audio_features import ENCODER_PATH, MODEL_PATH, extrair_features, validar_audio_filename
import sqlite3, json, os
import joblib
from pathlib import Path

app  = Flask(__name__, static_folder=str(Path(__file__).parent))
ROOT = Path(__file__).parent

# ── CORS ──────────────────────────────────────────────────────────────────────
@app.after_request
def _cors(r):
    r.headers.update({
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    })
    return r
@app.route("/api/<path:p>", methods=["OPTIONS"])
def _opt(p): return "", 204

# ── helpers ───────────────────────────────────────────────────────────────────
def ok(data=None, **kw):   return jsonify({"ok": True,  "data": data, **kw})
def err(msg, code=400):    return jsonify({"ok": False, "error": msg}), code
def rows(rs):              return [dict(r) for r in rs]
def row(r):                return dict(r) if r else None
def body():                return request.json or {}
def req(*fields):
    d = body()
    for f in fields:
        if not d.get(f) and d.get(f) != 0:
            return None, err(f"Campo '{f}' é obrigatório")
    return d, None

def patch_sql(table, pk, data, allowed):
    fields, vals = [], []
    for f in allowed:
        if f in data:
            fields.append(f"{f}=?")
            vals.append(data[f])
    if not fields:
        return False, err("Nenhum campo para atualizar")
    vals.append(pk)
    with get_conn() as c:
        c.execute(f"UPDATE {table} SET {','.join(fields)} WHERE id=?", vals)
    return True, None

# ═══════════════════════════════════════════════════════════════════════════════
#  SERVE FILES
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return send_from_directory(str(ROOT), "index.html")

@app.route("/<path:fname>")
def static_files(fname):
    return send_from_directory(str(ROOT), fname)

# ═══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/dashboard")
def dashboard():
    with get_conn() as c:
        def cnt(sql, p=()): return c.execute(sql,p).fetchone()[0]
        return ok({
            "amostras":       cnt("SELECT COUNT(*) FROM amostra_audio"),
            "classes":        cnt("SELECT COUNT(*) FROM classe_audio"),
            "modelos":        cnt("SELECT COUNT(*) FROM modelo_ml"),
            "diagnosticos":   cnt("SELECT COUNT(*) FROM diagnostico"),
            "alertas_abertos":cnt("SELECT COUNT(*) FROM alerta WHERE status='aberto'"),
            "os_abertas":     cnt("SELECT COUNT(*) FROM ordem_servico WHERE status NOT IN ('concluida','cancelada')"),
            "maquinas":       cnt("SELECT COUNT(*) FROM maquina"),
            "dist_classes": rows(c.execute(
                "SELECT classe, COUNT(*) as total FROM amostra_audio GROUP BY classe")),
            "ultimos_diagnosticos": rows(c.execute(
                "SELECT * FROM diagnostico ORDER BY realizado_em DESC LIMIT 6")),
            "modelo_ativo": row(c.execute(
                "SELECT * FROM modelo_ml WHERE ativo=1 ORDER BY treinado_em DESC LIMIT 1").fetchone()),
            "alertas_por_status": rows(c.execute(
                "SELECT status, COUNT(*) as total FROM alerta GROUP BY status")),
        })

# ═══════════════════════════════════════════════════════════════════════════════
#  EMPRESA
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/empresa")
def list_empresas():
    with get_conn() as c:
        return ok(rows(c.execute(
            "SELECT e.*, (SELECT COUNT(*) FROM planta WHERE empresa_id=e.id) as n_plantas,"
            "(SELECT COUNT(*) FROM usuario WHERE empresa_id=e.id) as n_usuarios "
            "FROM empresa e ORDER BY e.nome")))

@app.route("/api/empresa", methods=["POST"])
def create_empresa():
    d, e = req("nome","cnpj"); 
    if e: return e
    eid = uid()
    try:
        with get_conn() as c:
            c.execute("INSERT INTO empresa VALUES (?,?,?,?,?,?)",
                (eid,d["nome"].strip(),d["cnpj"].strip(),d.get("setor",""),d.get("porte",""),now()))
    except sqlite3.IntegrityError: return err("CNPJ já cadastrado")
    return ok({"id":eid}), 201

@app.route("/api/empresa/<eid>", methods=["PUT"])
def update_empresa(eid):
    ok2, e = patch_sql("empresa", eid, body(), ["nome","cnpj","setor","porte"])
    return e if e else ok()

@app.route("/api/empresa/<eid>", methods=["DELETE"])
def delete_empresa(eid):
    with get_conn() as c: c.execute("DELETE FROM empresa WHERE id=?", (eid,))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  USUARIO
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/usuario")
def list_usuarios():
    eid = request.args.get("empresa_id")
    sql = ("SELECT u.id,u.nome,u.email,u.perfil,u.ativo,u.criado_em,e.nome as empresa_nome "
           "FROM usuario u JOIN empresa e ON e.id=u.empresa_id")
    p = ()
    if eid: sql += " WHERE u.empresa_id=?"; p = (eid,)
    sql += " ORDER BY u.nome"
    with get_conn() as c: return ok(rows(c.execute(sql,p)))

@app.route("/api/usuario", methods=["POST"])
def create_usuario():
    d, e = req("nome","email","senha","empresa_id","perfil")
    if e: return e
    uid2 = uid()
    try:
        with get_conn() as c:
            c.execute("INSERT INTO usuario VALUES (?,?,?,?,?,?,?,?)",
                (uid2,d["empresa_id"],d["nome"].strip(),d["email"].lower().strip(),
                 hash_password(d["senha"]),d["perfil"],1,now()))
    except sqlite3.IntegrityError: return err("E-mail já cadastrado")
    return ok({"id":uid2}), 201

@app.route("/api/usuario/<uid2>", methods=["PUT"])
def update_usuario(uid2):
    d = body(); fields, vals = [], []
    for f in ["nome","email","perfil","ativo","empresa_id"]:
        if f in d: fields.append(f"{f}=?"); vals.append(d[f])
    if d.get("senha"):
        fields.append("senha_hash=?"); vals.append(hash_password(d["senha"]))
    if not fields: return err("Nada para atualizar")
    vals.append(uid2)
    with get_conn() as c: c.execute(f"UPDATE usuario SET {','.join(fields)} WHERE id=?", vals)
    return ok()

@app.route("/api/usuario/<uid2>", methods=["DELETE"])
def delete_usuario(uid2):
    with get_conn() as c: c.execute("UPDATE usuario SET ativo=0 WHERE id=?", (uid2,))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  PLANTA
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/planta")
def list_plantas():
    eid = request.args.get("empresa_id")
    sql = ("SELECT p.*,e.nome as empresa_nome,"
           "(SELECT COUNT(*) FROM maquina WHERE planta_id=p.id) as n_maquinas "
           "FROM planta p JOIN empresa e ON e.id=p.empresa_id")
    p = ()
    if eid: sql += " WHERE p.empresa_id=?"; p = (eid,)
    with get_conn() as c: return ok(rows(c.execute(sql+" ORDER BY p.nome",p)))

@app.route("/api/planta", methods=["POST"])
def create_planta():
    d, e = req("nome","empresa_id")
    if e: return e
    pid = uid()
    with get_conn() as c:
        c.execute("INSERT INTO planta VALUES (?,?,?,?,?)",
            (pid,d["empresa_id"],d["nome"].strip(),d.get("localizacao",""),d.get("responsavel","")))
    return ok({"id":pid}), 201

@app.route("/api/planta/<pid>", methods=["PUT"])
def update_planta(pid):
    ok2, e = patch_sql("planta", pid, body(), ["nome","localizacao","responsavel","empresa_id"])
    return e if e else ok()

@app.route("/api/planta/<pid>", methods=["DELETE"])
def delete_planta(pid):
    with get_conn() as c: c.execute("DELETE FROM planta WHERE id=?", (pid,))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  MAQUINA
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/maquina")
def list_maquinas():
    pid = request.args.get("planta_id")
    sql = ("SELECT m.*,p.nome as planta_nome,e.nome as empresa_nome,"
           "(SELECT COUNT(*) FROM sensor WHERE maquina_id=m.id) as n_sensores "
           "FROM maquina m JOIN planta p ON p.id=m.planta_id JOIN empresa e ON e.id=p.empresa_id")
    p = ()
    if pid: sql += " WHERE m.planta_id=?"; p = (pid,)
    with get_conn() as c: return ok(rows(c.execute(sql+" ORDER BY m.nome",p)))

@app.route("/api/maquina", methods=["POST"])
def create_maquina():
    d, e = req("nome","planta_id")
    if e: return e
    mid = uid()
    with get_conn() as c:
        c.execute("INSERT INTO maquina VALUES (?,?,?,?,?,?,?,?,?)",
            (mid,d["planta_id"],d["nome"].strip(),d.get("modelo",""),d.get("fabricante",""),
             d.get("numero_serie",""),d.get("status","operando"),d.get("instalacao",""),now()))
    return ok({"id":mid}), 201

@app.route("/api/maquina/<mid>", methods=["PUT"])
def update_maquina(mid):
    d = body(); d["atualizado_em"] = now()
    ok2, e = patch_sql("maquina", mid, d,
        ["nome","modelo","fabricante","numero_serie","status","instalacao","planta_id","atualizado_em"])
    return e if e else ok()

@app.route("/api/maquina/<mid>", methods=["DELETE"])
def delete_maquina(mid):
    with get_conn() as c: c.execute("DELETE FROM maquina WHERE id=?", (mid,))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  CLASSE AUDIO
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/classe")
def list_classes():
    with get_conn() as c:
        return ok(rows(c.execute(
            "SELECT ca.*,(SELECT COUNT(*) FROM amostra_audio WHERE classe=ca.nome) as n_amostras "
            "FROM classe_audio ca ORDER BY ca.nome")))

@app.route("/api/classe", methods=["POST"])
def create_classe():
    d, e = req("nome")
    if e: return e
    try:
        with get_conn() as c:
            c.execute("INSERT INTO classe_audio VALUES (?,?,?,?,?,?)",
                (d["nome"].strip(),d.get("descricao",""),d.get("icone","📌"),
                 d.get("cor","#00e5ff"),d.get("mensagem",""),now()))
    except sqlite3.IntegrityError: return err("Classe já existe")
    return ok({"nome":d["nome"]}), 201

@app.route("/api/classe/<nome>", methods=["PUT"])
def update_classe(nome):
    d = body(); fields, vals = [], []
    for f in ["descricao","icone","cor","mensagem"]:
        if f in d: fields.append(f"{f}=?"); vals.append(d[f])
    if not fields: return err("Nada para atualizar")
    vals.append(nome)
    with get_conn() as c: c.execute(f"UPDATE classe_audio SET {','.join(fields)} WHERE nome=?", vals)
    return ok()

@app.route("/api/classe/<nome>", methods=["DELETE"])
def delete_classe(nome):
    with get_conn() as c: c.execute("DELETE FROM classe_audio WHERE nome=?", (nome,))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  AMOSTRA AUDIO
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/amostra")
def list_amostras():
    classe = request.args.get("classe")
    mid    = request.args.get("maquina_id")
    sql    = ("SELECT a.*,ca.icone,ca.cor FROM amostra_audio a "
              "LEFT JOIN classe_audio ca ON ca.nome=a.classe WHERE 1=1")
    p = []
    if classe: sql += " AND a.classe=?"; p.append(classe)
    if mid:    sql += " AND a.maquina_id=?"; p.append(mid)
    sql += " ORDER BY a.criado_em DESC LIMIT 500"
    with get_conn() as c: return ok(rows(c.execute(sql,p)))

@app.route("/api/amostra", methods=["POST"])
def create_amostra():
    d, e = req("nome","classe")
    if e: return e
    aid = uid()
    with get_conn() as c:
        c.execute("INSERT INTO amostra_audio VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid,d["nome"].strip(),d["classe"],d.get("maquina_id"),
             d.get("caminho",""),d.get("duracao"),d.get("tamanho_kb"),
             json.dumps(d["features"]) if d.get("features") else None,
             d.get("notas",""),now()))
    return ok({"id":aid}), 201

@app.route("/api/amostra/batch", methods=["POST"])
def batch_amostras():
    """Insere múltiplas amostras de uma vez (importação em lote do site)."""
    d = body()
    items = d.get("amostras",[])
    if not items: return err("Lista vazia")
    ids = []
    with get_conn() as c:
        for a in items:
            aid = uid()
            c.execute("INSERT INTO amostra_audio VALUES (?,?,?,?,?,?,?,?,?,?)",
                (aid,a.get("nome","audio.wav"),a["classe"],a.get("maquina_id"),
                 a.get("caminho",""),a.get("duracao"),a.get("tamanho_kb"),
                 json.dumps(a["features"]) if a.get("features") else None,
                 a.get("notas",""),now()))
            ids.append(aid)
    return ok({"ids":ids, "total":len(ids)}), 201

@app.route("/api/amostra/<aid>", methods=["DELETE"])
def delete_amostra(aid):
    with get_conn() as c: c.execute("DELETE FROM amostra_audio WHERE id=?", (aid,))
    return ok()

@app.route("/api/amostra/clear", methods=["DELETE"])
def clear_amostras():
    with get_conn() as c: c.execute("DELETE FROM amostra_audio")
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  MODELO ML
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/modelo")
def list_modelos():
    with get_conn() as c:
        return ok(rows(c.execute(
            "SELECT ml.*,m.nome as maquina_nome FROM modelo_ml ml "
            "LEFT JOIN maquina m ON m.id=ml.maquina_id ORDER BY ml.treinado_em DESC")))

@app.route("/api/modelo", methods=["POST"])
def create_modelo():
    d, e = req("nome","versao","arquivo_pkl")
    if e: return e
    mid = uid()
    # desativa modelo anterior
    with get_conn() as c:
        c.execute("UPDATE modelo_ml SET ativo=0 WHERE maquina_id=?", (d.get("maquina_id"),))
        c.execute("INSERT INTO modelo_ml VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid,d.get("maquina_id"),d["nome"].strip(),d["versao"],d["arquivo_pkl"],
             d.get("acuracia"),d.get("n_estimators",200),d.get("n_mfcc",13),
             d.get("test_split",0.2),d.get("random_state",42),
             json.dumps(d["classes"]) if d.get("classes") else None,
             d.get("amostras_treino"),1,now()))
    return ok({"id":mid}), 201

@app.route("/api/modelo/<mid>", methods=["PUT"])
def update_modelo(mid):
    d = body()
    if d.get("ativo") == 1:
        with get_conn() as c:
            c.execute("UPDATE modelo_ml SET ativo=0")
    ok2, e = patch_sql("modelo_ml", mid, d,
        ["nome","versao","arquivo_pkl","acuracia","ativo","maquina_id"])
    return e if e else ok()

@app.route("/api/modelo/<mid>", methods=["DELETE"])
def delete_modelo(mid):
    with get_conn() as c: c.execute("DELETE FROM modelo_ml WHERE id=?", (mid,))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTICO
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/diagnostico")
def list_diagnosticos():
    with get_conn() as c:
        return ok(rows(c.execute(
            "SELECT d.*,m.nome as maquina_nome FROM diagnostico d "
            "LEFT JOIN maquina m ON m.id=d.maquina_id "
            "ORDER BY d.realizado_em DESC LIMIT 200")))

@app.route("/api/diagnostico", methods=["POST"])
def create_diagnostico():
    d, e = req("arquivo","diagnostico","confianca")
    if e: return e
    did = uid()
    with get_conn() as c:
        c.execute("INSERT INTO diagnostico VALUES (?,?,?,?,?,?,?,?,?)",
            (did,d["arquivo"],d["diagnostico"],float(d["confianca"]),
             d.get("modelo_id"),d.get("modelo_nome",""),
             json.dumps(d["probs"]) if d.get("probs") else None,
             d.get("maquina_id"),now()))
    return ok({"id":did}), 201

@app.route("/api/diagnostico/clear", methods=["DELETE"])
def clear_diagnosticos():
    with get_conn() as c: c.execute("DELETE FROM diagnostico")
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  SENSOR
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/sensor")
def list_sensores():
    mid = request.args.get("maquina_id")
    sql = "SELECT s.*,m.nome as maquina_nome FROM sensor s JOIN maquina m ON m.id=s.maquina_id"
    p = ()
    if mid: sql += " WHERE s.maquina_id=?"; p = (mid,)
    with get_conn() as c: return ok(rows(c.execute(sql+" ORDER BY s.nome",p)))

@app.route("/api/sensor", methods=["POST"])
def create_sensor():
    d, e = req("nome","maquina_id","tipo","unidade")
    if e: return e
    sid = uid()
    with get_conn() as c:
        c.execute("INSERT INTO sensor VALUES (?,?,?,?,?,?,?,?,?)",
            (sid,d["maquina_id"],d["nome"],d["tipo"],d["unidade"],
             d.get("limiar_alerta"),d.get("limiar_critico"),1,now()))
    return ok({"id":sid}), 201

@app.route("/api/sensor/<sid>", methods=["PUT"])
def update_sensor(sid):
    ok2, e = patch_sql("sensor", sid, body(),
        ["nome","tipo","unidade","limiar_alerta","limiar_critico","ativo"])
    return e if e else ok()

@app.route("/api/sensor/<sid>", methods=["DELETE"])
def delete_sensor(sid):
    with get_conn() as c: c.execute("DELETE FROM sensor WHERE id=?", (sid,))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  ALERTA
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/alerta")
def list_alertas():
    status = request.args.get("status")
    sql = ("SELECT a.*,s.nome as sensor_nome,m.nome as maquina_nome,ml.nome as modelo_nome "
           "FROM alerta a JOIN sensor s ON s.id=a.sensor_id "
           "JOIN maquina m ON m.id=s.maquina_id JOIN modelo_ml ml ON ml.id=a.modelo_ml_id")
    p = ()
    if status: sql += " WHERE a.status=?"; p = (status,)
    with get_conn() as c: return ok(rows(c.execute(sql+" ORDER BY a.gerado_em DESC LIMIT 100",p)))

@app.route("/api/alerta", methods=["POST"])
def create_alerta():
    d, e = req("sensor_id","modelo_ml_id","severidade","diagnostico","confianca")
    if e: return e
    aid = uid()
    with get_conn() as c:
        c.execute("INSERT INTO alerta VALUES (?,?,?,?,?,?,?,?,?)",
            (aid,d["sensor_id"],d["modelo_ml_id"],d["severidade"],
             d["diagnostico"],float(d["confianca"]),"aberto",now(),None))
    return ok({"id":aid}), 201

@app.route("/api/alerta/<aid>", methods=["PUT"])
def update_alerta(aid):
    d = body()
    if d.get("status") in ("resolvido","falso_positivo"):
        d["resolvido_em"] = now()
    ok2, e = patch_sql("alerta", aid, d, ["status","resolvido_em"])
    return e if e else ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  ORDEM DE SERVIÇO
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/os")
def list_os():
    with get_conn() as c:
        return ok(rows(c.execute(
            "SELECT os.*,a.diagnostico,a.severidade,m.nome as maquina_nome,"
            "t.nome as tecnico_nome,g.nome as gestor_nome "
            "FROM ordem_servico os JOIN alerta a ON a.id=os.alerta_id "
            "JOIN sensor s ON s.id=a.sensor_id JOIN maquina m ON m.id=s.maquina_id "
            "LEFT JOIN usuario t ON t.id=os.tecnico_id "
            "JOIN usuario g ON g.id=os.gestor_id "
            "ORDER BY os.aberta_em DESC LIMIT 100")))

@app.route("/api/os", methods=["POST"])
def create_os():
    d, e = req("alerta_id","gestor_id","descricao","prioridade")
    if e: return e
    osid = uid()
    with get_conn() as c:
        c.execute("INSERT INTO ordem_servico VALUES (?,?,?,?,?,?,?,?,?)",
            (osid,d["alerta_id"],d.get("tecnico_id"),d["gestor_id"],
             d["descricao"],d["prioridade"],"aberta",now(),None))
        c.execute("INSERT INTO historico_os VALUES (?,?,?,?,?,?)",
            (uid(),osid,d["gestor_id"],"criacao","OS criada.",now()))
    return ok({"id":osid}), 201

@app.route("/api/os/<osid>", methods=["PUT"])
def update_os(osid):
    d = body()
    if d.get("status") in ("concluida","cancelada"): d["fechada_em"] = now()
    ok2, e = patch_sql("ordem_servico", osid, d,
        ["status","tecnico_id","prioridade","descricao","fechada_em"])
    if not ok2: return e
    if d.get("status") and d.get("usuario_id"):
        with get_conn() as c:
            c.execute("INSERT INTO historico_os VALUES (?,?,?,?,?,?)",
                (uid(),osid,d["usuario_id"],d.get("acao","atualizacao"),
                 d.get("observacao",""),now()))
    return ok()

# ═══════════════════════════════════════════════════════════════════════════════
#  SELECTS (dropdowns)
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/sel/empresas")
def sel_emp():
    with get_conn() as c: return ok(rows(c.execute("SELECT id,nome FROM empresa ORDER BY nome")))

@app.route("/api/sel/plantas")
def sel_pla():
    eid = request.args.get("empresa_id")
    sql = "SELECT p.id,p.nome,e.nome as empresa FROM planta p JOIN empresa e ON e.id=p.empresa_id"
    p = ()
    if eid: sql+=" WHERE p.empresa_id=?"; p=(eid,)
    with get_conn() as c: return ok(rows(c.execute(sql+" ORDER BY p.nome",p)))

@app.route("/api/sel/maquinas")
def sel_maq():
    pid = request.args.get("planta_id")
    sql = "SELECT id,nome FROM maquina"
    p = ()
    if pid: sql+=" WHERE planta_id=?"; p=(pid,)
    with get_conn() as c: return ok(rows(c.execute(sql+" ORDER BY nome",p)))

@app.route("/api/sel/usuarios")
def sel_usr():
    perfil = request.args.get("perfil")
    sql = "SELECT id,nome,perfil FROM usuario WHERE ativo=1"
    p = ()
    if perfil: sql+=" AND perfil=?"; p=(perfil,)
    with get_conn() as c: return ok(rows(c.execute(sql+" ORDER BY nome",p)))

@app.route("/api/sel/modelos")
def sel_mod():
    with get_conn() as c:
        return ok(rows(c.execute("SELECT id,nome,versao,ativo FROM modelo_ml ORDER BY treinado_em DESC")))

@app.route("/api/sel/classes")
def sel_cls():
    with get_conn() as c:
        return ok(rows(c.execute("SELECT nome,icone,cor,mensagem FROM classe_audio ORDER BY nome")))

# ═══════════════════════════════════════════════════════════════════════════════
#  API MÓVEL — autenticação e inferência de áudio
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/auth/login", methods=["POST"])
def login():
    d, e = req("email", "senha")
    if e: return e
    with get_conn() as c:
        user = c.execute("SELECT * FROM usuario WHERE lower(email)=lower(?) AND ativo=1", (d["email"].strip(),)).fetchone()
        if not user or not verify_password(d["senha"], user["senha_hash"]):
            return err("E-mail ou senha inválidos", 401)
        if is_legacy_hash(user["senha_hash"]):
            c.execute("UPDATE usuario SET senha_hash=? WHERE id=?", (hash_password(d["senha"]), user["id"]))
    return ok({"token": issue_token(user), "usuario": {
        "id": user["id"], "nome": user["nome"], "email": user["email"],
        "perfil": user["perfil"], "empresa_id": user["empresa_id"]
    }})


@app.route("/api/auth/me")
@require_auth
def me():
    with get_conn() as c:
        user = c.execute("SELECT id,nome,email,perfil,empresa_id FROM usuario WHERE id=? AND ativo=1", (g.auth["sub"],)).fetchone()
    return ok(row(user)) if user else err("Usuário não encontrado", 401)


@app.route("/api/diagnosticar", methods=["POST"])
@require_auth
def diagnosticar_upload():
    """Recebe WAV/MP3 do Android, classifica e grava o histórico da empresa."""
    upload = request.files.get("arquivo") or request.files.get("file")
    if not upload or not upload.filename:
        return err("Envie o áudio no campo multipart 'arquivo'")
    try:
        validar_audio_filename(upload.filename)
    except ValueError as exc:
        return err(str(exc), 415)

    maquina_id = request.form.get("maquina_id")
    with get_conn() as c:
        sql = ("SELECT ml.* FROM modelo_ml ml "
               "LEFT JOIN maquina m ON m.id=ml.maquina_id "
               "LEFT JOIN planta p ON p.id=m.planta_id "
               "WHERE ml.ativo=1 AND (p.empresa_id=? OR p.empresa_id IS NULL)")
        params = [g.auth["empresa_id"]]
        if maquina_id:
            sql += " AND ml.maquina_id=?"; params.append(maquina_id)
        modelo_reg = c.execute(sql + " ORDER BY ml.treinado_em DESC LIMIT 1", params).fetchone()
    if not modelo_reg:
        return err("Nenhum modelo ativo disponível para esta empresa/máquina", 404)

    model_path = ROOT / modelo_reg["arquivo_pkl"]
    encoder_path = model_path.parent / "classes_v1.pkl"
    if not model_path.exists() or not encoder_path.exists():
        # Permite o registro legado, mas mantém o diretório canônico como fallback.
        model_path, encoder_path = MODEL_PATH, ENCODER_PATH
    if not model_path.exists() or not encoder_path.exists():
        return err("Arquivo do modelo ativo não encontrado no servidor", 503)

    temp_dir = ROOT / "uploads"; temp_dir.mkdir(exist_ok=True)
    temp_path = temp_dir / f"{uid()}{validar_audio_filename(upload.filename)}"
    try:
        upload.save(temp_path)
        modelo = joblib.load(model_path); encoder = joblib.load(encoder_path)
        features = extrair_features(temp_path).reshape(1, -1)
        pred_idx = int(modelo.predict(features)[0])
        probs = modelo.predict_proba(features)[0]
        diagnostico = str(encoder.inverse_transform([pred_idx])[0])
        probabilidades = {str(classe): float(prob) for classe, prob in zip(encoder.classes_, probs)}
        did = uid()
        with get_conn() as c:
            c.execute("INSERT INTO diagnostico VALUES (?,?,?,?,?,?,?,?,?)", (
                did, upload.filename, diagnostico, float(probs[pred_idx]), modelo_reg["id"],
                modelo_reg["nome"], json.dumps(probabilidades), maquina_id, now()))
        return ok({"id": did, "diagnostico": diagnostico,
                   "confianca": float(probs[pred_idx]),
                   "probabilidades": probabilidades,
                   "modelo": {"id": modelo_reg["id"], "nome": modelo_reg["nome"], "versao": modelo_reg["versao"]}})
    except Exception as exc:
        app.logger.exception("Falha no diagnóstico")
        return err(f"Não foi possível processar o áudio: {exc}", 422)
    finally:
        temp_path.unlink(missing_ok=True)


@app.route("/api/mobile/diagnosticos")
@require_auth
def mobile_diagnosticos():
    with get_conn() as c:
        registros = c.execute(
            "SELECT d.* FROM diagnostico d "
            "LEFT JOIN maquina m ON m.id=d.maquina_id "
            "LEFT JOIN planta p ON p.id=m.planta_id "
            "WHERE d.maquina_id IS NULL OR p.empresa_id=? "
            "ORDER BY d.realizado_em DESC LIMIT 100", (g.auth["empresa_id"],)).fetchall()
    return ok(rows(registros))

# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    seed_demo()
    print("\n  ✅  API:    http://localhost:5000/api/dashboard")
    print("  🌐  Painel: http://localhost:5000/\n")
    app.run(debug=True, port=5000, use_reloader=False)
