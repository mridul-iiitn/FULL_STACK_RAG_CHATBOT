from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import psycopg2
from PyPDF2 import PdfReader
import google.generativeai as genai
import sys
import tempfile
from dotenv import load_dotenv
load_dotenv()

# ----------------------------
# Config (SECURE VERSION)
# ----------------------------
DB_URI = os.getenv("DB_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not set.")
    sys.exit(1)
if not DB_URI:
    print("ERROR: DB_URI environment variable not set.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# ----------------------------
# Database connection
# ----------------------------
conn = None
try:
    print("Connecting to the database...")
    conn = psycopg2.connect(DB_URI)
    cur = conn.cursor()
    print("Database connection successful.")

    # --- AUTOMATIC DATABASE SETUP ---
    print("Ensuring 'documents' table exists...")
    setup_query = """
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        file_name VARCHAR(255),
        chunk_text TEXT,
        embedding VECTOR(768)
    );
    """
    cur.execute(setup_query)
    conn.commit()
    print("Database is ready.")
    # --- END OF AUTOMATIC SETUP ---

except psycopg2.OperationalError as e:
    print(f"FATAL: Could not connect to the database: {e}")
    print("Please check your DB_URI environment variable and database status.")
    sys.exit(1)

# ----------------------------
# Flask setup
# ----------------------------
app = Flask(__name__)
# CORS FIX HERE: More specific CORS configuration
CORS(app, resources={r"/*": {"origins": "*"}})


# ----------------------------
# Helpers (UPDATED CHUNKING LOGIC)
# ----------------------------
def text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    return "\n".join([p.extract_text() or "" for p in reader.pages])

def sliding_window_chunker(text, chunk_size=800, overlap=200):
    """The original chunking function, now renamed."""
    tokens = text.split()
    chunks = []
    i = 0
    while i < len(tokens):
        chunk = tokens[i:i+chunk_size]
        chunks.append(" ".join(chunk))
        i += chunk_size - overlap
    return chunks

def smart_chunker(text, chunk_size=800, overlap=200):
    """
    A new, content-aware chunker that respects paragraph boundaries.
    """
    final_chunks = []
    paragraphs = text.split('\n\n')
    
    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            continue # Ignore empty paragraphs

        # If the paragraph is smaller than the chunk size, treat it as a whole chunk
        if len(para_stripped.split()) <= chunk_size:
            final_chunks.append(para_stripped)
        # If the paragraph is too long, use the sliding window chunker on it
        else:
            sub_chunks = sliding_window_chunker(para_stripped, chunk_size=chunk_size, overlap=overlap)
            final_chunks.extend(sub_chunks)
            
    return final_chunks

def embed_texts(texts):
    """Generate embeddings using Gemini's embedding model."""
    try:
        result = genai.embed_content(model="models/embedding-001", content=texts, task_type="retrieval_document")
        return result['embedding']
    except Exception as e:
        print(f"Error embedding texts: {e}")
        return [[] for _ in texts]


# ----------------------------
# Routes
# ----------------------------
@app.route("/upload", methods=["POST"])
def upload():
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

    # UPDATED to use the new smart_chunker
    chunks = smart_chunker(text)
    embeddings = embed_texts(chunks)

    if not all(embeddings):
        return jsonify({"error": "Failed to generate embeddings."}), 500

    for chunk, emb in zip(chunks, embeddings):
        emb_str = str(list(emb))
        cur.execute(
            "INSERT INTO documents (file_name, chunk_text, embedding) VALUES (%s, %s, %s)",
            (fname, chunk, emb_str)
        )
    conn.commit()

    return jsonify({"message": "uploaded", "chunks_added": len(chunks)})

@app.route("/query", methods=["POST"])
def query():
    data = request.json
    q = data.get("question", "")
    k = int(data.get("k", 4))
    if not q:
        return jsonify({"error": "no question"}), 400

    q_emb = genai.embed_content(
        model="models/embedding-001", content=q, task_type="retrieval_query"
    )['embedding']
    q_emb_str = str(list(q_emb))

    cur.execute(
        "SELECT chunk_text FROM documents ORDER BY embedding <-> %s::vector LIMIT %s",
        (q_emb_str, k)
    )
    rows = cur.fetchall()
    context = "\n".join([r[0] for r in rows])

    system_prompt = "You are a humble helpful assistant..."
    user_prompt = f"Context:\n{context}\n\nQuestion: {q}"

    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content([system_prompt, user_prompt])
    answer = resp.text
    
    return jsonify({"answer": answer, "sources": [r[0] for r in rows]})

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True)
