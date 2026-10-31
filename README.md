# 📚 Lecture Notes Summarizer & MCQ Generator

A Streamlit web app that turns lecture notes (PDF, DOCX, TXT or pasted text) into a
study pack:

- **Summary** and **important key points**
- **Beginner-friendly explanations** of the main topics, with examples
- **Practice MCQs** with instant scoring and explanations
- **Downloadable** study notes (Markdown) including an answer key

## ✨ No API keys needed

- Summaries, key points and MCQs are generated locally with plain Python (no AI
  API, no tokens, no credit card).
- Optional beginner background uses the free, open
  [Wikipedia REST API](https://en.wikipedia.org/api/rest_v1/) (no key). Turn it off in the sidebar if you prefer.

## 🧠 How it works

1. **Clean & split** the text into sentences.
2. **Find definitions** (patterns like "X is ...", "X refers to ...").
3. **Rank keywords** (single words and two-word phrases) by frequency.
4. **Score sentences** by how many important words they contain, then pick the top ones for the summary and key points.
5. **Build MCQs**:
   - *Definition match:* "Which term is described by ...?"
   - *Fill in the blank:* a key sentence with a key term removed
   - Wrong options come from other key terms in your notes.
6. **Explain topics:** each key term shows the definition from your notes, an example sentence, and a short Wikipedia background.

## ⚠️ Limitations

This is an *extractive* approach: it selects and reorganises sentences from your notes
rather than rewriting them like a large language model. For best results use notes
written in complete sentences, include definitions ("X is ..."), and provide at least
300 words. Scanned PDFs (images) can't be read without OCR.

## 🗂 Project structure

```
.
├── app.py
├── requirements.txt
└── README.md
```

## 💻 Run locally

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 🚀 Deploy on Streamlit Community Cloud

1. Create a new **public GitHub repository** and upload `app.py`, `requirements.txt` and `README.md`.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **Create app** → choose your repository, branch `main`, and main file `app.py`.
4. Click **Deploy**. No secrets or environment variables are required.

## 🛠 Tech stack

Python · Streamlit · pypdf · python-docx · Requests · Wikipedia REST API

## 📄 License

MIT — free to use for learning and personal projects.
