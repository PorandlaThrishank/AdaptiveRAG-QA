import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
from werkzeug.utils import secure_filename

from adaptive_rag import AdaptiveRAG

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

rag_store = {}


def get_or_create_rag():
    user_id = session.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        session["user_id"] = user_id

    rag = rag_store.get(user_id)
    if rag is None:
        rag = AdaptiveRAG()
        rag_store[user_id] = rag
    return rag


def clear_user_rag():
    user_id = session.get("user_id")
    if user_id and user_id in rag_store:
        del rag_store[user_id]
    session.pop("user_id", None)


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/upload")
def upload():
    files = request.files.getlist("files")
    if not files or all(not f.filename for f in files):
        return jsonify({"error": "Select at least one PDF."}), 400

    paths = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": f"{file.filename} is not a PDF."}), 400

        filename = secure_filename(file.filename)
        path = UPLOAD_DIR / filename
        file.save(path)
        paths.append(str(path))

    try:
        rag = get_or_create_rag()
        chunks = rag.ingest_pdfs(paths)
        return jsonify(
            {
                "message": "Documents indexed successfully.",
                "files": len(paths),
                "chunks": chunks,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/ask")
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

    rag = rag_store.get(session.get("user_id"))
    if rag is None or rag.index is None or not rag.chunks:
        return jsonify({"error": "Please upload and index at least one PDF before asking a question."}), 400

    try:
        return jsonify(rag.answer(question))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/clear")
def clear_docs():
    clear_user_rag()
    return jsonify({"message": "Session data cleared."})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
