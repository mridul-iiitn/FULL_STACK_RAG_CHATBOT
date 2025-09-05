from flask import Flask, request, jsonify, g
from flask_cors import CORS
import os
import psycopg2
from PyPDF2 import PdfReader
import google.generativeai as genai
import sys
import tempfile
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager

load_dotenv()

# ----------------------------
# Config
# ----------------------------
DB_URI = os.getenv("DB_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-fallback")

if not GEMINI_API_KEY or not DB_URI:
    print("ERROR: Environment variables not set.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# -----------------------------------------------
# --- Professional Database Connection Management ---
# -----------------------------------------------
def get_db():
    """Opens a new database connection for each request."""
    if 'db' not in g:
        g.db = psycopg2.connect(DB_URI)
    return g.db

def init_db(app_context):
    """Initializes the database schema if tables don't exist."""
    with app_context.app_context():
        db = get_db()
        cur = db.cursor()
        print("Ensuring database schema is up to date...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                file_name VARCHAR(255),
                chunk_text TEXT,
                embedding VECTOR(768),
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                sender VARCHAR(50) NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        db.commit()
        cur.close()
        print("Database is ready.")

# ----------------------------
# Flask setup
# ----------------------------
app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
CORS(app, resources={r"/*": {"origins": "*"}})

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

try:
    init_db(app)
except Exception as e:
    print(f"FATAL: Database initialization failed: {e}")
    sys.exit(1)

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# ----------------------------
# Helper Functions
# ----------------------------
def text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    return "\n".join([p.extract_text() or "" for p in reader.pages])

def sliding_window_chunker(text, chunk_size=800, overlap=200):
    tokens = text.split()
    chunks = []
    i = 0
    while i < len(tokens):
        chunk = tokens[i:i+chunk_size]
        chunks.append(" ".join(chunk))
        i += chunk_size - overlap
    return chunks

def smart_chunker(text, chunk_size=800, overlap=200):
    final_chunks = []
    paragraphs = text.split('\n\n')
    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            continue
        if len(para_stripped.split()) <= chunk_size:
            final_chunks.append(para_stripped)
        else:
            sub_chunks = sliding_window_chunker(para_stripped, chunk_size=chunk_size, overlap=overlap)
            final_chunks.extend(sub_chunks)
    return final_chunks

def embed_texts(texts):
    try:
        result = genai.embed_content(model="models/embedding-001", content=texts, task_type="retrieval_document")
        return result['embedding']
    except Exception as e:
        print(f"Error embedding texts: {e}")
        return [[] for _ in texts]

# ---------------------------------
# Authentication Routes
# ---------------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s)", (email, hashed_password))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({"error": "Email already exists"}), 409
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
    return jsonify({"message": "User registered successfully"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    if user and bcrypt.check_password_hash(user[1], password):
        user_id = user[0]
        access_token = create_access_token(identity=str(user_id))
        return jsonify(access_token=access_token)
    else:
        return jsonify({"error": "Invalid email or password"}), 401

# ---------------------------------
# Chat History Routes
# ---------------------------------
@app.route("/chats", methods=["POST"])
@jwt_required()
def start_chat():
    current_user_id = get_jwt_identity()
    data = request.json
    document_id = data.get("document_id")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO chats (user_id, document_id) VALUES (%s, %s) RETURNING id",
            (current_user_id, document_id)
        )
        chat_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error starting chat: {e}")
        return jsonify({"error": "Could not start a new chat session"}), 500
    finally:
        cur.close()
    return jsonify({"chat_id": chat_id}), 201

# ---------------------------------
# Core Application Routes
# ---------------------------------
@app.route("/upload", methods=["POST"])
@jwt_required()
def upload():
    current_user_id = get_jwt_identity()
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "no file"}), 400
    fname = file.filename
    temp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(temp_dir, fname)
    file.save(tmp_path)
    try:
        if fname.lower().endswith(".pdf"):
            text = text_from_pdf(tmp_path)
        else:
            with open(tmp_path, "r", encoding="utf-8") as f:
                text = f.read()
    except Exception as e:
        return jsonify({"error": f"Error reading file: {e}"}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    chunks = smart_chunker(text)
    embeddings = embed_texts(chunks)
    if not all(embeddings):
        return jsonify({"error": "Failed to generate embeddings."}), 500
    conn = get_db()
    cur = conn.cursor()
    try:
        for chunk, emb in zip(chunks, embeddings):
            emb_str = str(list(emb))
            cur.execute(
                "INSERT INTO documents (file_name, chunk_text, embedding, user_id) VALUES (%s, %s, %s, %s)",
                (fname, chunk, emb_str, current_user_id)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
    return jsonify({"message": "uploaded", "chunks_added": len(chunks)})

@app.route("/query", methods=["POST"])
@jwt_required()
def query():
    current_user_id = get_jwt_identity()
    data = request.json
    q = data.get("question", "")
    chat_id = data.get("chat_id")
    k = int(data.get("k", 4))
    if not q or not chat_id:
        return jsonify({"error": "question and chat_id are required"}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO messages (chat_id, sender, text) VALUES (%s, %s, %s)",
            (chat_id, "user", q)
        )
        q_emb = genai.embed_content(
            model="models/embedding-001", content=q, task_type="retrieval_query"
        )['embedding']
        q_emb_str = str(list(q_emb))
        cur.execute(
            "SELECT chunk_text FROM documents WHERE user_id = %s ORDER BY embedding <-> %s::vector LIMIT %s",
            (current_user_id, q_emb_str, k)
        )
        rows = cur.fetchall()
        context = "\n".join([r[0] for r in rows])
        system_prompt = "You are a humble helpful assistant..."
        user_prompt = f"Context:\n{context}\n\nQuestion: {q}"
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content([system_prompt, user_prompt])
        answer = resp.text
        cur.execute(
            "INSERT INTO messages (chat_id, sender, text) VALUES (%s, %s, %s)",
            (chat_id, "bot", answer)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
    return jsonify({"answer": answer, "sources": [r[0] for r in rows]})

# ---------------------------------
# --- NEW: Dashboard API Routes ---
# ---------------------------------
@app.route("/documents", methods=["GET"])
@jwt_required()
def get_documents():
    current_user_id = get_jwt_identity()
    conn = get_db()
    cur = conn.cursor()
    try:
        # We select distinct file names to avoid duplicates
        cur.execute(
            "SELECT DISTINCT file_name FROM documents WHERE user_id = %s",
            (current_user_id,)
        )
        documents = [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error fetching documents: {e}")
        return jsonify({"error": "Could not fetch documents"}), 500
    finally:
        cur.close()
    return jsonify(documents=documents)

@app.route("/chats", methods=["GET"])
@jwt_required()
def get_chats():
    current_user_id = get_jwt_identity()
    conn = get_db()
    cur = conn.cursor()
    try:
        # We can select chat IDs and creation times
        cur.execute(
            "SELECT id, created_at FROM chats WHERE user_id = %s ORDER BY created_at DESC",
            (current_user_id,)
        )
        # Formatting the data nicely for the frontend
        chats = [{"id": row[0], "created_at": row[1]} for row in cur.fetchall()]
    except Exception as e:
        print(f"Error fetching chats: {e}")
        return jsonify({"error": "Could not fetch chats"}), 500
    finally:
        cur.close()
    return jsonify(chats=chats)

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True)