import os
import re
import tempfile
import traceback
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Research & Strategy Assistant",
    page_icon="🧠",
    layout="wide",
)

# ── Lazy / guarded imports ────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_heavy_deps():
    try:
        from langchain_community.document_loaders import (
            PyPDFLoader,
            TextLoader,
            Docx2txtLoader,
        )
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_community.vectorstores import Chroma
        from langchain_core.documents import Document
        from crewai import Agent, Task, Crew, Process

        return {
            "PyPDFLoader": PyPDFLoader,
            "TextLoader": TextLoader,
            "Docx2txtLoader": Docx2txtLoader,
            "RecursiveCharacterTextSplitter": RecursiveCharacterTextSplitter,
            "HuggingFaceEmbeddings": HuggingFaceEmbeddings,
            "Chroma": Chroma,
            "Document": Document,
            "Agent": Agent,
            "Task": Task,
            "Crew": Crew,
            "Process": Process,
        }
    except ImportError as e:
        return {"error": str(e)}


# ── Session-state defaults ────────────────────────────────────────────────────
def init_state():
    defaults = {
        "page": "input",
        "uploaded_files_data": [],
        "company_text": "",
        "retriever": None,
        "vectorstore": None,
        "results": None,
        "error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ── Helper: build RAG pipeline ────────────────────────────────────────────────
def build_rag(files_data: list, company_text: str, deps: dict):
    PyPDFLoader = deps["PyPDFLoader"]
    TextLoader = deps["TextLoader"]
    Docx2txtLoader = deps["Docx2txtLoader"]
    RecursiveCharacterTextSplitter = deps["RecursiveCharacterTextSplitter"]
    HuggingFaceEmbeddings = deps["HuggingFaceEmbeddings"]
    Chroma = deps["Chroma"]
    Document = deps["Document"]

    all_docs = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for filename, file_bytes in files_data:
            tmp_path = os.path.join(tmp_dir, filename)
            with open(tmp_path, "wb") as f:
                f.write(file_bytes)
            ext = Path(filename).suffix.lower()
            try:
                if ext == ".pdf":
                    loader = PyPDFLoader(tmp_path)
                elif ext == ".txt":
                    loader = TextLoader(tmp_path, encoding="utf-8")
                elif ext in (".docx", ".doc"):
                    loader = Docx2txtLoader(tmp_path)
                else:
                    st.warning(f"Unsupported file type: {filename}. Skipping.")
                    continue
                docs = loader.load()
                all_docs.extend(docs)
            except Exception as e:
                st.warning(f"Could not load {filename}: {e}")

    if company_text.strip():
        all_docs.append(Document(page_content=company_text.strip(), metadata={"source": "user_input"}))

    if not all_docs:
        raise ValueError("No content to process. Please upload files or enter a company description.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(all_docs)

    if not chunks:
        raise ValueError("Text splitting produced no chunks. Please check your input.")

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"token": os.environ.get("HF_TOKEN")},
    )

    import shutil
    chroma_dir = tempfile.mkdtemp()
    vectorstore = Chroma.from_documents(chunks, embeddings, persist_directory=chroma_dir)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
    st.session_state["vectorstore"] = vectorstore
    st.session_state["retriever"] = retriever
    st.session_state["chroma_dir"] = chroma_dir

    return retriever


# ── Helper: retrieve context ──────────────────────────────────────────────────
def retrieve_context(retriever, query: str) -> str:
    try:
        docs = retriever.invoke(query)
        return "\n\n".join(d.page_content for d in docs)
    except Exception:
        docs = retriever._get_relevant_documents(query)
        return "\n\n".join(d.page_content for d in docs)


# ── Helper: run CrewAI pipeline ───────────────────────────────────────────────
def run_crew(retriever, company_text: str, deps: dict) -> dict:
    Agent = deps["Agent"]
    Task = deps["Task"]
    Crew = deps["Crew"]
    Process = deps["Process"]

    groq_api_key = os.environ.get("GROQ_API_KEY")
    os.environ["GROQ_API_KEY"] = groq_api_key
    model = "groq/llama-3.3-70b-versatile"

    research_ctx = retrieve_context(retriever, "key business insights and main topics")
    analysis_ctx = retrieve_context(retriever, "business challenges problems gaps weaknesses")
    strategy_ctx = retrieve_context(retriever, "opportunities improvements recommendations growth")

    subject = company_text[:300] if company_text.strip() else "the uploaded documents"

    # ── Agents ────────────────────────────────────────────────────────────────
    research_agent = Agent(
        role="Senior Research Analyst",
        goal="Extract concise, scannable key insights from business documents.",
        backstory=(
            "You are an expert research analyst. You write short, punchy bullet points only. "
            "You never write paragraphs. Every insight is one clear sentence."
        ),
        llm=model,
        verbose=False,
        allow_delegation=False,
    )

    analysis_agent = Agent(
        role="Business Analysis Expert",
        goal="Identify and structure business pain points in a table-ready format.",
        backstory=(
            "You are a business analyst who outputs structured data only. "
            "You always format findings as: Problem | Impact | Priority. "
            "No paragraphs. No extra commentary."
        ),
        llm=model,
        verbose=False,
        allow_delegation=False,
    )

    strategy_agent = Agent(
        role="Strategic Consultant",
        goal="Produce concise, actionable strategy blocks with clear titles and bullet steps.",
        backstory=(
            "You are a management consultant who writes short, structured strategy cards. "
            "Each card has a title and 2-3 action bullet points. No paragraphs."
        ),
        llm=model,
        verbose=False,
        allow_delegation=False,
    )

    content_agent = Agent(
        role="Professional Content Writer",
        goal="Generate a short summary, a concise professional email, and a structured report.",
        backstory=(
            "You are a business writer who formats everything clearly with headings. "
            "You write concisely. Each deliverable is clearly separated."
        ),
        llm=model,
        verbose=False,
        allow_delegation=False,
    )

    # ── Tasks ─────────────────────────────────────────────────────────────────
    research_task = Task(
        description=(
            f"Business context: {subject}\n\n"
            f"DOCUMENT CONTEXT:\n{research_ctx}\n\n"
            "OUTPUT RULES (STRICT):\n"
            "- Output ONLY a bullet list of 5-7 key insights\n"
            "- Each bullet = one short sentence (max 15 words)\n"
            "- Start each line with '- '\n"
            "- NO headings, NO paragraphs, NO explanations\n"
            "- Only facts and insights from the context\n\n"
            "Example format:\n"
            "- Company operates in 3 markets with declining margins in two.\n"
            "- Customer churn rate is above industry average at 18%.\n"
            "- Product roadmap lacks mobile-first features despite 60% mobile users."
        ),
        expected_output="A bullet list of 5-7 concise key insights, one sentence each.",
        agent=research_agent,
    )

    analysis_task = Task(
        description=(
            f"DOCUMENT CONTEXT:\n{analysis_ctx}\n\n"
            "OUTPUT RULES (STRICT):\n"
            "- Identify exactly 5 business pain points\n"
            "- Format EACH pain point as follows (use this exact structure):\n\n"
            "PROBLEM: [short name of the problem]\n"
            "IMPACT: [one sentence on business impact]\n"
            "PRIORITY: [High / Medium / Low]\n"
            "---\n\n"
            "- NO paragraphs\n"
            "- NO extra commentary before or after\n"
            "- Repeat the block exactly 5 times"
        ),
        expected_output=(
            "5 structured pain point blocks, each with PROBLEM, IMPACT, and PRIORITY fields."
        ),
        agent=analysis_agent,
        context=[research_task],
    )

    strategy_task = Task(
        description=(
            f"DOCUMENT CONTEXT:\n{strategy_ctx}\n\n"
            "OUTPUT RULES (STRICT):\n"
            "- Provide exactly 5 strategy recommendations\n"
            "- Format EACH strategy as follows:\n\n"
            "FIX: [Short strategy title]\n"
            "- [Action step 1]\n"
            "- [Action step 2]\n"
            "- [Action step 3]\n"
            "OUTCOME: [One sentence on expected result]\n"
            "---\n\n"
            "- NO paragraphs\n"
            "- NO extra text before or after\n"
            "- Repeat the block exactly 5 times"
        ),
        expected_output=(
            "5 strategy blocks each with FIX title, 2-3 action bullets, and OUTCOME."
        ),
        agent=strategy_agent,
        context=[analysis_task],
    )

    content_task = Task(
        description=(
            "Using all prior agent outputs, produce THREE clearly separated deliverables.\n\n"
            "Use EXACTLY these section markers (copy them verbatim):\n\n"
            "===SUMMARY===\n"
            "- [Bullet point 1]\n"
            "- [Bullet point 2]\n"
            "- [Bullet point 3]\n"
            "- [Bullet point 4]\n"
            "- [Bullet point 5]\n\n"
            "===EMAIL===\n"
            "Subject: [Email subject line]\n\n"
            "Dear [Stakeholder],\n\n"
            "[Email body - max 120 words. Mention top findings and one clear call to action.]\n\n"
            "Best regards,\n"
            "[Your Name]\n\n"
            "===REPORT===\n"
            "## Executive Summary\n"
            "[2-3 sentences]\n\n"
            "## Key Findings\n"
            "[Bullet list, max 5 points]\n\n"
            "## Pain Points\n"
            "[Bullet list, max 5 points]\n\n"
            "## Strategic Recommendations\n"
            "[Bullet list, max 5 points]\n\n"
            "## Conclusion\n"
            "[2-3 sentences]\n\n"
            "RULES:\n"
            "- Use the exact section markers above\n"
            "- Keep each section concise\n"
            "- No repetition across sections"
        ),
        expected_output=(
            "Three deliverables separated by ===SUMMARY===, ===EMAIL===, and ===REPORT=== markers."
        ),
        agent=content_agent,
        context=[research_task, analysis_task, strategy_task],
    )

    # ── Crew ──────────────────────────────────────────────────────────────────
    crew = Crew(
        agents=[research_agent, analysis_agent, strategy_agent, content_agent],
        tasks=[research_task, analysis_task, strategy_task, content_task],
        process=Process.sequential,
        verbose=False,
    )

    crew.kickoff()

    def safe_output(task):
        try:
            return str(task.output.raw) if hasattr(task.output, "raw") else str(task.output)
        except Exception:
            return ""

    return {
        "research": safe_output(research_task),
        "analysis": safe_output(analysis_task),
        "strategy": safe_output(strategy_task),
        "content": safe_output(content_task),
    }


# ── Output parsers ────────────────────────────────────────────────────────────
def parse_pain_points(text: str) -> list:
    blocks = re.split(r"-{3,}", text)
    rows = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        problem = re.search(r"PROBLEM\s*:\s*(.+)", block, re.IGNORECASE)
        impact = re.search(r"IMPACT\s*:\s*(.+)", block, re.IGNORECASE)
        priority = re.search(r"PRIORITY\s*:\s*(.+)", block, re.IGNORECASE)
        if problem or impact or priority:
            rows.append({
                "Problem": problem.group(1).strip() if problem else "—",
                "Impact": impact.group(1).strip() if impact else "—",
                "Priority": priority.group(1).strip() if priority else "—",
            })
    return rows


def parse_strategies(text: str) -> list:
    blocks = re.split(r"-{3,}", text)
    strategies = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        fix_match = re.search(r"FIX\s*:\s*(.+)", block, re.IGNORECASE)
        outcome_match = re.search(r"OUTCOME\s*:\s*(.+)", block, re.IGNORECASE)
        bullets = re.findall(r"^[\-\*]\s+(.+)", block, re.MULTILINE)
        fix_title = fix_match.group(1).strip() if fix_match else ""
        outcome_text = outcome_match.group(1).strip() if outcome_match else ""
        bullets = [b for b in bullets if b != fix_title and b != outcome_text]
        if fix_match or bullets:
            strategies.append({
                "title": fix_title or "Strategy",
                "steps": bullets,
                "outcome": outcome_text,
            })
    return strategies


def parse_content_sections(text: str) -> dict:
    def extract(marker_start, marker_end=None):
        if marker_end:
            pattern = rf"==={marker_start}===\s*(.*?)\s*==={marker_end}==="
        else:
            pattern = rf"==={marker_start}===\s*(.*)"
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    return {
        "summary": extract("SUMMARY", "EMAIL"),
        "email": extract("EMAIL", "REPORT"),
        "report": extract("REPORT"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# INPUT PAGE
# ══════════════════════════════════════════════════════════════════════════════
def page_input():
    st.title("🧠 AI Research & Strategy Assistant")
    st.markdown(
        "Upload business documents **and/or** describe your company, "
        "then click **Analyse Business** to run the full AI pipeline."
    )
    st.divider()

    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        st.error("GROQ_API_KEY not found in environment. Please check your .env file.")
        return

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📁 Upload Documents")
        uploaded = st.file_uploader(
            "PDF, TXT, or DOCX",
            type=["pdf", "txt", "docx", "doc"],
            accept_multiple_files=True,
        )

    with col2:
        st.subheader("🏢 Company / Business Description")
        company_text = st.text_area(
            "Describe the company, products, market, and challenges:",
            height=200,
            placeholder=(
                "E.g. Acme Corp is a mid-size SaaS company focused on B2B project management. "
                "Key challenges include high churn, slow onboarding, and fierce competition..."
            ),
        )

    st.divider()
    run_btn = st.button("🚀 Analyse Business", type="primary", use_container_width=True)

    if run_btn:
        if not uploaded and not company_text.strip():
            st.error("Please upload at least one document or enter a company description.")
            return

        st.session_state["uploaded_files_data"] = [(f.name, f.read()) for f in (uploaded or [])]
        st.session_state["company_text"] = company_text
        st.session_state["results"] = None
        st.session_state["error"] = None

        deps = load_heavy_deps()
        if "error" in deps:
            st.error(f"Dependency import failed: {deps['error']}")
            st.info(
                "Run: pip install streamlit langchain langchain-community langchain-openai "
                "langchain-huggingface crewai chromadb sentence-transformers pypdf docx2txt"
            )
            return

        with st.spinner("📚 Building RAG pipeline (embeddings + vector store)…"):
            try:
                retriever = build_rag(
                    st.session_state["uploaded_files_data"],
                    company_text,
                    deps,
                )
                st.session_state["retriever"] = retriever
            except Exception as e:
                st.error(f"RAG pipeline error: {e}\n\n{traceback.format_exc()}")
                return

        with st.spinner("🤖 Running multi-agent analysis (Research → Analysis → Strategy → Content)…"):
            try:
                results = run_crew(
                    st.session_state["retriever"],
                    company_text,
                    deps,
                )
                st.session_state["results"] = results
            except Exception as e:
                st.error(f"CrewAI pipeline error: {e}\n\n{traceback.format_exc()}")
                return

        st.session_state["page"] = "results"
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS PAGE
# ══════════════════════════════════════════════════════════════════════════════
def page_results():
    st.title("📊 Analysis Results")

    if st.button("← Back to Input"):
        st.session_state["page"] = "input"
        st.rerun()

    results = st.session_state.get("results")
    if not results:
        st.warning("No results found. Please go back and run the analysis.")
        return

    st.divider()

    # ── Section 1: Key Insights ───────────────────────────────────────────────
    st.subheader("🔍 Key Insights")
    research_out = results.get("research", "").strip()
    if research_out:
        lines = [l.strip() for l in research_out.splitlines() if l.strip()]
        bullet_lines = [l for l in lines if l.startswith("-") or l.startswith("•") or l.startswith("*")]
        display_lines = bullet_lines if bullet_lines else lines
        for line in display_lines[:7]:
            clean = re.sub(r"^[-•*]\s*", "", line)
            st.markdown(f"- {clean}")
    else:
        st.info("No research output available.")

    st.divider()

    # ── Section 2: Pain Points Table ─────────────────────────────────────────
    st.subheader("⚠️ Pain Points & Gaps")
    analysis_out = results.get("analysis", "").strip()
    if analysis_out:
        rows = parse_pain_points(analysis_out)
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows)

            def colour_priority(val):
                colours = {"High": "#ff4b4b", "Medium": "#ffa500", "Low": "#21c354"}
                c = colours.get(val.strip(), "#888888")
                return f"color: {c}; font-weight: bold;"

            styled = df.style.applymap(colour_priority, subset=["Priority"])
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.markdown(analysis_out)
    else:
        st.info("No analysis output available.")

    st.divider()

    # ── Section 3: Strategy Suggestions ──────────────────────────────────────
    st.subheader("💡 Strategy Recommendations")
    strategy_out = results.get("strategy", "").strip()
    if strategy_out:
        strategies = parse_strategies(strategy_out)
        if strategies:
            num_cols = min(len(strategies), 3)
            cols = st.columns(num_cols)
            for i, strat in enumerate(strategies[:5]):
                with cols[i % num_cols]:
                    with st.container(border=True):
                        st.markdown(f"**{strat['title']}**")
                        for step in strat["steps"]:
                            st.markdown(f"- {step}")
                        if strat["outcome"]:
                            st.caption(f"✅ {strat['outcome']}")
        else:
            st.markdown(strategy_out)
    else:
        st.info("No strategy output available.")

    st.divider()

    # ── Section 4: Generated Output Tabs ─────────────────────────────────────
    st.subheader("📝 Generated Output")
    content_out = results.get("content", "").strip()

    if content_out:
        sections = parse_content_sections(content_out)
        has_parsed = any(sections.values())

        tab_summary, tab_email, tab_report = st.tabs(["📋 Summary", "✉️ Email", "📄 Full Report"])

        with tab_summary:
            summary_text = sections.get("summary", "") if has_parsed else ""
            if summary_text:
                lines = [l.strip() for l in summary_text.splitlines() if l.strip()]
                bullets = [l for l in lines if l.startswith("-") or l.startswith("•") or l.startswith("*")]
                display = bullets if bullets else lines
                for line in display[:5]:
                    clean = re.sub(r"^[-•*]\s*", "", line)
                    st.markdown(f"- {clean}")
            else:
                st.markdown(content_out)

        with tab_email:
            email_text = sections.get("email", "") if has_parsed else ""
            if email_text:
                st.markdown(email_text)
            else:
                st.markdown(content_out)

        with tab_report:
            report_text = sections.get("report", "") if has_parsed else ""
            if report_text:
                st.markdown(report_text)
            else:
                st.markdown(content_out)
    else:
        st.info("No content output available.")

    st.divider()

    # ── Download ──────────────────────────────────────────────────────────────
    full_report = "\n\n".join(filter(None, [
        "# AI Research & Strategy Assistant Report\n",
        "## Key Insights\n" + results.get("research", ""),
        "## Pain Points & Gaps\n" + results.get("analysis", ""),
        "## Strategy Suggestions\n" + results.get("strategy", ""),
        "## Generated Output\n" + results.get("content", ""),
    ]))

    st.download_button(
        label="⬇️ Download Full Report (TXT)",
        data=full_report,
        file_name="ai_strategy_report.txt",
        mime="text/plain",
        use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════
def main():
    page = st.session_state.get("page", "input")
    if page == "results" and st.session_state.get("results"):
        page_results()
    else:
        page_input()


if __name__ == "__main__":
    main()