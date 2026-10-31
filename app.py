"""
Lecture Notes Summarizer & MCQ Generator
----------------------------------------
A Streamlit app that turns lecture notes (PDF, DOCX, TXT or pasted text) into:
  * a short summary and important key points
  * beginner-friendly explanations of the key topics (with examples)
  * multiple-choice questions (MCQs) for self-testing

No API keys required. The text analysis runs locally in plain Python and the
only external call is the free, open Wikipedia REST API (optional) which is
used to add plain-English background for key terms.
"""

import io
import random
import re
from collections import Counter
from urllib.parse import quote

import requests
import streamlit as st
from docx import Document
from pypdf import PdfReader

# --------------------------------------------------------------------------- #
# Page setup
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Lecture Notes Summarizer & MCQ Generator",
    page_icon="📚",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem;}
    .card {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        background: rgba(128,128,128,0.06);
    }
    .chip {
        display: inline-block;
        padding: 0.2rem 0.7rem;
        margin: 0.15rem 0.2rem 0.15rem 0;
        border-radius: 999px;
        font-size: 0.85rem;
        background: rgba(76,120,255,0.15);
        border: 1px solid rgba(76,120,255,0.35);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
STOPWORDS = set(
    """
    a about above after again against all also am an and any are as at be because
    been before being below between both but by can could did do does doing down
    during each few for from further had has have having he her here hers him his
    how i if in into is it its itself just let me more most my no nor not of off on
    once only or other our ours out over own same she should so some such than that
    the their theirs them then there these they this those through to too under
    until up very was we were what when where which while who whom why will with
    would you your yours yourself one two three may might must shall using used use
    like get got many much thus hence however therefore etc eg ie also often
    place places take takes taken make makes made convert converts produce produces allow allows
    need needs affect affects green large small tiny new good great different various several
    include includes including contain contains called based part parts type types way ways
    """.split()
)

BAD_TERM_START = {
    "this", "that", "it", "there", "these", "those", "which", "here",
    "he", "she", "they", "we", "you", "what", "who",
}

DEF_RE = re.compile(
    r"^(?:an?\s+|the\s+)?([A-Za-z][A-Za-z0-9\-\s]{1,40}?)\s+"
    r"(?:is defined as|is known as|is called|refers to|stands for|means|is|are)\s+"
    r"(.{15,})$",
    re.IGNORECASE,
)

EXAMPLE_CUES = ("for example", "for instance", "e.g.", "such as", "consider ", "imagine ")


# --------------------------------------------------------------------------- #
# File reading & text cleaning
# --------------------------------------------------------------------------- #
def extract_text(uploaded_file) -> str:
    """Read text from an uploaded PDF, DOCX or TXT file."""
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    return data.decode("utf-8", errors="ignore")


def clean_text(raw: str) -> str:
    """Normalise whitespace, bullets and line breaks so sentences can be split."""
    raw = raw.replace("\r", "\n")
    raw = re.sub(r"-\n(?=[a-z])", "", raw)  # re-join hyphenated line breaks
    lines = []
    for line in raw.split("\n"):
        line = re.sub(r"^[\s\-\*\u2022\u25CF\u25AA>]+", "", line).strip()
        line = re.sub(r"^\d+[\.\)]\s+", "", line)
        if not line:
            continue
        words = line.split()
        if len(words) < 4:  # likely a heading or page number
            continue
        if line[-1] not in ".!?":
            line += "."
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def split_sentences(text: str):
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\(])', text)
    sentences = []
    for p in parts:
        n_words = len(p.split())
        if 6 <= n_words <= 60:
            sentences.append(p.strip())
    return sentences


def tokenize(sentence: str):
    words = re.findall(r"[a-zA-Z][a-zA-Z\-']{2,}", sentence.lower())
    return [w for w in words if w not in STOPWORDS]


def display(term: str) -> str:
    """Title-case a term, keeping acronyms found in the notes (e.g. ATP) in capitals."""
    if any(c.isupper() for c in term):
        return term
    acronyms = st.session_state.get("acronyms", set())
    return " ".join(w.upper() if w in acronyms else w.capitalize() for w in term.split())


# --------------------------------------------------------------------------- #
# Core NLP (pure Python, no API keys)
# --------------------------------------------------------------------------- #
def find_definitions(sentences):
    """Find sentences shaped like 'X is ...' / 'X refers to ...'."""
    found, seen = [], set()
    for idx, s in enumerate(sentences):
        m = DEF_RE.match(s.strip())
        if not m:
            continue
        term = m.group(1).strip(" ,;:-").lower()
        words = term.split()
        if not words or len(words) > 4 or words[0] in BAD_TERM_START:
            continue
        if all(w in STOPWORDS for w in words) or term in seen:
            continue
        seen.add(term)
        found.append({"term": term, "definition": m.group(2).strip().rstrip("."), "sentence": s, "idx": idx})
    return found


def extract_keywords(sentences, definitions, limit=30):
    """Rank important single words and two-word phrases; defined terms come first."""
    uni, bi = Counter(), Counter()
    for s in sentences:
        words = re.findall(r"[a-zA-Z][a-zA-Z\-']*", s.lower())
        for w in words:
            if len(w) > 2 and w not in STOPWORDS:
                uni[w] += 1
        for a, b in zip(words, words[1:]):
            if len(a) > 2 and len(b) > 2 and a not in STOPWORDS and b not in STOPWORDS:
                bi[f"{a} {b}"] += 1

    keywords = [d["term"] for d in definitions]

    bigrams = [p for p, c in bi.most_common(limit) if c >= 2]
    in_bigrams = {w for p in bigrams for w in p.split()}
    scored = [(p, bi[p] * 1.5) for p in bigrams]
    scored += [(w, c) for w, c in uni.items() if c >= 2 and w not in in_bigrams]
    if len(scored) < 8:  # very short notes: relax the threshold
        scored += [(w, c) for w, c in uni.items() if w not in in_bigrams and (w, c) not in scored]
    scored.sort(key=lambda x: -x[1])

    for term, _ in scored:
        if term not in keywords and not any(term in k.split() for k in keywords):
            keywords.append(term)
        if len(keywords) >= limit:
            break
    return keywords


def rank_sentences(sentences, definitions):
    """Score sentences by the frequency of important words (extractive summary)."""
    freq = Counter(w for s in sentences for w in tokenize(s))
    if not freq:
        return []
    top = max(freq.values())
    def_idx = {d["idx"] for d in definitions}
    n = len(sentences)
    scored = []
    for i, s in enumerate(sentences):
        toks = tokenize(s)
        if not toks:
            continue
        score = sum(freq[t] / top for t in toks) / (len(toks) ** 0.8)
        if i in def_idx:
            score *= 1.3
        if i < max(2, int(n * 0.1)):
            score *= 1.1
        scored.append((score, i))
    scored.sort(reverse=True)
    return [i for _, i in scored]


def find_example(sentences, term, avoid_idx=None):
    """Find a sentence from the notes that gives an example involving the term."""
    pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    best = None
    for i, s in enumerate(sentences):
        if i == avoid_idx or not pattern.search(s):
            continue
        if any(cue in s.lower() for cue in EXAMPLE_CUES):
            return s
        best = best or s
    return best


@st.cache_data(ttl=86400, show_spinner=False)
def wiki_background(term: str):
    """Free, key-less plain-English background from the Wikipedia REST API."""
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(term.replace(" ", "_"))
        r = requests.get(url, headers={"User-Agent": "LectureNotesSummarizer/1.0 (educational project)"}, timeout=6)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("type") != "standard":
            return None
        sentences = re.split(r"(?<=[.!?])\s+", data.get("extract", ""))
        text = " ".join(sentences[:2]).strip()
        if not text:
            return None
        return {"text": text, "url": data.get("content_urls", {}).get("desktop", {}).get("page", "")}
    except (requests.RequestException, ValueError):
        return None


def build_concepts(sentences, definitions, keywords, use_wiki, limit=8):
    """Beginner-friendly explanation cards for the top key terms."""
    def_map = {d["term"]: d for d in definitions}
    concepts = []
    for term in keywords[:limit]:
        d = def_map.get(term)
        if d is None:
            for key, val in def_map.items():
                if term in key or key in term:
                    d = val
                    break
        example = find_example(sentences, term, avoid_idx=d["idx"] if d else None)
        concepts.append(
            {
                "term": display(term),
                "definition": d["sentence"] if d else None,
                "example": example,
                "wiki": wiki_background(term) if use_wiki else None,
            }
        )
    return concepts


def pick_distractors(correct, pool, avoid_text, rng, k=3):
    cw = len(correct.split())
    cands = [
        t
        for t in pool
        if t != correct
        and t not in correct
        and correct not in t
        and not re.search(r"\b" + re.escape(t) + r"\b", avoid_text.lower())
    ]
    rng.shuffle(cands)
    cands.sort(key=lambda t: abs(len(t.split()) - cw))
    return cands[:k] if len(cands) >= k else None


def make_mcqs(sentences, ranked_idx, definitions, keywords, n, seed):
    """Generate definition-match and fill-in-the-blank MCQs from the notes."""
    rng = random.Random(seed)
    questions, used = [], set()
    pool = keywords[:30]
    if len(pool) < 4:
        return questions

    # 1) Definition questions: "Which term is described by ...?"
    defs = definitions[:]
    rng.shuffle(defs)
    for d in defs:
        if len(questions) >= (n + 1) // 2:
            break
        text = re.sub(re.escape(d["term"]), "_____", d["definition"], flags=re.IGNORECASE)
        if len(text) > 260:
            text = text[:257].rsplit(" ", 1)[0] + "..."
        distractors = pick_distractors(d["term"], pool, d["definition"], rng)
        if not distractors:
            continue
        options = [d["term"]] + distractors
        rng.shuffle(options)
        questions.append(
            {
                "q": f"Which term is described by: “{text}”?",
                "options": [display(o) for o in options],
                "answer": options.index(d["term"]),
                "explain": d["sentence"],
            }
        )
        used.add(d["idx"])

    # 2) Fill-in-the-blank questions from the highest-ranked sentences
    candidates = [i for i in ranked_idx[: max(3 * n, 12)] if i not in used]
    rng.shuffle(candidates)
    for i in candidates:
        if len(questions) >= n:
            break
        s = sentences[i]
        if len(s) > 300:
            continue
        present = [k for k in pool if re.search(r"\b" + re.escape(k) + r"\b", s, re.IGNORECASE)]
        if not present:
            continue
        target = max(present, key=lambda k: (len(k.split()), len(k)))
        distractors = pick_distractors(target, pool, s, rng)
        if not distractors:
            continue
        blanked = re.sub(r"\b" + re.escape(target) + r"\b", "_____", s, flags=re.IGNORECASE)
        options = [target] + distractors
        rng.shuffle(options)
        questions.append(
            {
                "q": f"Fill in the blank: {blanked}",
                "options": [display(o) for o in options],
                "answer": options.index(target),
                "explain": s,
            }
        )
    rng.shuffle(questions)
    return questions[:n]


def analyze(text, n_points, n_mcq, use_wiki, seed):
    cleaned = clean_text(text)
    st.session_state["acronyms"] = {a.lower() for a in re.findall(r"\b[A-Z]{2,6}\b", cleaned)}
    sentences = split_sentences(cleaned)
    if len(sentences) < 5:
        return None
    definitions = find_definitions(sentences)
    keywords = extract_keywords(sentences, definitions)
    ranked = rank_sentences(sentences, definitions)

    n_points = min(n_points, len(sentences))
    key_idx = sorted(ranked[:n_points])
    summary_idx = sorted(ranked[: max(3, round(n_points * 0.5))])

    words = len(cleaned.split())
    return {
        "sentences": sentences,
        "ranked": ranked,
        "definitions": definitions,
        "keywords": keywords,
        "summary": " ".join(sentences[i] for i in summary_idx),
        "key_points": [sentences[i] for i in key_idx],
        "concepts": build_concepts(sentences, definitions, keywords, use_wiki),
        "mcqs": make_mcqs(sentences, ranked, definitions, keywords, n_mcq, seed),
        "words": words,
        "read_min": max(1, round(words / 200)),
        "n_mcq": n_mcq,
    }


def to_markdown(res):
    lines = ["# Study Notes", "", "## Summary", res["summary"], "", "## Important Points"]
    lines += [f"- {p}" for p in res["key_points"]]
    lines += ["", "## Key Terms", ", ".join(display(k) for k in res["keywords"][:15]), "", "## Beginner Explanations"]
    for c in res["concepts"]:
        lines.append(f"### {c['term']}")
        if c["definition"]:
            lines.append(f"- **In your notes:** {c['definition']}")
        if c["example"]:
            lines.append(f"- **Example:** {c['example']}")
        if c["wiki"]:
            lines.append(f"- **Plain-English background:** {c['wiki']['text']}")
        lines.append("")
    lines += ["## Practice MCQs"]
    letters = "ABCD"
    for i, q in enumerate(res["mcqs"], 1):
        lines.append(f"**Q{i}. {q['q']}**")
        lines += [f"- {letters[j]}. {o}" for j, o in enumerate(q["options"])]
        lines.append("")
    lines += ["## Answer Key"]
    for i, q in enumerate(res["mcqs"], 1):
        lines.append(f"{i}. {letters[q['answer']]} — {q['options'][q['answer']]}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
def render_quiz(res):
    mcqs = res["mcqs"]
    if not mcqs:
        st.warning("Not enough distinct key terms to build MCQs. Try longer or more detailed notes.")
        return

    with st.form("quiz_form"):
        for i, q in enumerate(mcqs):
            st.markdown(f"**Q{i + 1}. {q['q']}**")
            st.radio("Choose one", q["options"], index=None, key=f"quiz_{i}", label_visibility="collapsed")
            st.write("")
        submitted = st.form_submit_button("✅ Submit answers", type="primary")

    if submitted:
        score = 0
        for i, q in enumerate(mcqs):
            chosen = st.session_state.get(f"quiz_{i}")
            correct = q["options"][q["answer"]]
            if chosen == correct:
                score += 1
                st.success(f"Q{i + 1}: Correct — {correct}")
            else:
                st.error(f"Q{i + 1}: Your answer: {chosen or 'No answer'} | Correct answer: {correct}")
            st.caption(f"📖 From your notes: {q['explain']}")
        st.metric("Your score", f"{score} / {len(mcqs)}")

    if st.button("🔄 Generate a new set of questions"):
        st.session_state["seed"] = st.session_state.get("seed", 0) + 1
        for key in [k for k in st.session_state if k.startswith("quiz_")]:
            del st.session_state[key]
        res["mcqs"] = make_mcqs(
            res["sentences"], res["ranked"], res["definitions"], res["keywords"], res["n_mcq"], st.session_state["seed"]
        )
        st.rerun()


def main():
    st.title("📚 Lecture Notes Summarizer & MCQ Generator")
    st.caption(
        "Upload or paste your lecture notes to get a summary, important points, "
        "beginner-friendly explanations with examples, and practice MCQs. No API key needed."
    )

    with st.sidebar:
        st.header("⚙️ Settings")
        n_points = st.slider("Number of important points", 5, 20, 8)
        n_mcq = st.slider("Number of MCQs", 3, 15, 8)
        use_wiki = st.toggle("Add beginner background from Wikipedia", value=True)
        st.divider()
        st.markdown(
            "**Tips**\n\n- Use clear, complete sentences.\n- Notes with definitions "
            "(*“X is …”*) give better MCQs.\n- 300+ words works best."
        )

    tab_upload, tab_paste = st.tabs(["📄 Upload a file", "✍️ Paste text"])
    text = ""
    with tab_upload:
        uploaded = st.file_uploader("PDF, DOCX or TXT", type=["pdf", "docx", "txt"])
        if uploaded is not None:
            try:
                text = extract_text(uploaded)
            except Exception as exc:  # noqa: BLE001 - show a friendly message
                st.error(f"Could not read the file: {exc}")
    with tab_paste:
        pasted = st.text_area("Paste your lecture notes here", height=250)
        if pasted.strip():
            text = pasted

    if st.button("🚀 Generate study pack", type="primary", use_container_width=True):
        if len(text.split()) < 80:
            st.warning("Please provide at least ~80 words of notes.")
        else:
            for key in [k for k in st.session_state if k.startswith("quiz_")]:
                del st.session_state[key]
            st.session_state["seed"] = 0
            with st.spinner("Analyzing your notes..."):
                result = analyze(text, n_points, n_mcq, use_wiki, seed=0)
            if result is None:
                st.error("Couldn't find enough full sentences. Try pasting more detailed notes.")
            else:
                st.session_state["result"] = result

    res = st.session_state.get("result")
    if not res:
        st.info("👆 Add your notes and click **Generate study pack**.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Words analysed", f"{res['words']:,}")
    m2.metric("Reading time", f"{res['read_min']} min")
    m3.metric("Key terms found", len(res["keywords"]))
    m4.metric("MCQs created", len(res["mcqs"]))

    t_sum, t_learn, t_quiz, t_dl = st.tabs(["📝 Summary & Key Points", "🎓 Learn the Topics", "🧠 Quiz", "⬇️ Download"])

    with t_sum:
        left, right = st.columns([2, 1])
        with left:
            st.subheader("Summary")
            st.markdown(f'<div class="card">{res["summary"]}</div>', unsafe_allow_html=True)
            st.subheader("Important points")
            for p in res["key_points"]:
                st.markdown(f"- {p}")
        with right:
            st.subheader("Key terms")
            st.markdown(
                "".join(f'<span class="chip">{display(k)}</span>' for k in res["keywords"][:20]),
                unsafe_allow_html=True,
            )

    with t_learn:
        st.subheader("Topics explained for beginners")
        st.caption("Each card shows the definition from your notes, an example, and simple background.")
        if not res["concepts"]:
            st.info("No key topics detected.")
        for c in res["concepts"]:
            with st.expander(f"📌 {c['term']}", expanded=False):
                if c["definition"]:
                    st.markdown(f"**In your notes:** {c['definition']}")
                if c["example"]:
                    st.markdown(f"**Example / context:** {c['example']}")
                if c["wiki"]:
                    link = f" [Read more]({c['wiki']['url']})" if c["wiki"]["url"] else ""
                    st.markdown(f"**Plain-English background:** {c['wiki']['text']}{link}")
                    st.caption("Background comes from Wikipedia and is general; your notes are the main source.")
                if not (c["definition"] or c["example"] or c["wiki"]):
                    st.write("No extra details found for this term.")

    with t_quiz:
        st.subheader("Test yourself")
        render_quiz(res)

    with t_dl:
        st.subheader("Download your study notes")
        st.download_button(
            "⬇️ Download as Markdown",
            data=to_markdown(res),
            file_name="study_notes.md",
            mime="text/markdown",
        )
        with st.expander("Preview"):
            st.markdown(to_markdown(res))


if __name__ == "__main__":
    main()
