# AI Research & Strategy Assistant 🚀

A powerful, AI-driven business analysis tool that transforms company documents and descriptions into actionable strategic insights. Built with **Streamlit**, **CrewAI**, and **LangChain**.

---

## 🌟 Features

- **Document Processing**: Upload PDF, TXT, or DOCX files for deep analysis.
- **RAG Pipeline**: Uses a Retrieval-Augmented Generation (RAG) system with ChromaDB and HuggingFace embeddings.
- **Multi-Agent Analysis**: Leveraging CrewAI with specialized agents:
    - 🔍 **Research Analyst**: Extracts key business insights.
    - 📊 **Business Expert**: Identifies pain points and structures them by impact and priority.
    - 💡 **Strategic Consultant**: Provides actionable strategy recommendations.
    - ✍️ **Content Writer**: Generates summaries, professional emails, and executive reports.
- **Professional UI**: A sleek, custom-styled Streamlit interface for seamless interaction.
- **Export Options**: Download your analysis results in **TXT**, **PDF**, or **Word (DOCX)** formats.

---

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd AI-Strategy-Assistant
```

### 2. Install Dependencies
Make sure you have Python 3.9+ installed, then run:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory and add your API keys:
```env
GROQ_API_KEY=your_groq_api_key_here
HF_TOKEN=your_huggingface_token_here
```
*Note: The app uses **Groq** for high-performance inference (Llama 3.3).*

### 4. Run the Application
```bash
streamlit run app.py
```

---

## 🛠️ How it Works

1. **Input**: Provide a company description or upload business documents.
2. **Process**: The app builds a vector store from your inputs and kicks off a CrewAI process.
3. **Analysis**: Four specialized AI agents work sequentially to research, analyze, and strategize.
4. **Results**: View insights, pain points, and recommendations in real-time.
5. **Report**: Export the final "Executive Report" for your stakeholders.

---

## 📦 Tech Stack

- **Frontend**: [Streamlit](https://streamlit.io/)
- **Orchestration**: [CrewAI](https://www.crewai.com/)
- **LLM Framework**: [LangChain](https://www.langchain.com/)
- **Embeddings**: [HuggingFace](https://huggingface.co/)
- **Vector Database**: [ChromaDB](https://www.trychroma.com/)
- **LLM Provider**: [Groq](https://groq.com/) (Llama 3.3)

---

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.
