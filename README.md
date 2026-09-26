<div align="center">

# ✈️ PostPilot AI

### Your multi-agent co-pilot for LinkedIn posts worth reading

*Research → Draft → Critique → Revise. Four specialized AI agents, one polished post.*

<br/>

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

</div>

---

## 💡 The Problem

Writing a good LinkedIn post is harder than it looks. It has to be **accurate**, **engaging**, **on-brand**, and **written for the right audience**, and it has to do all of that in a few hundred words.

Most AI writing tools try to handle this with **one giant prompt**. You get something that is fluent but generic: vague claims, recycled hooks, and a tone that doesn't sound like anyone in particular.

## 🚀 The Idea

**PostPilot AI takes a different approach.** Instead of asking one model to do everything at once, it splits the job across a small team of **specialized agents**, each responsible for one thing, the way a real content team works:

> 🔎 A **researcher** gathers the facts.
> ✍️ A **writer** drafts the post.
> 🧐 A **critic** reviews it for accuracy and engagement.
> ✨ An **editor** turns the feedback into a polished final version.

The result is content that has been **researched, reviewed, and revised** before you see it.

---

## 🧠 How It Works

```mermaid
flowchart LR
    U([👤 User<br/>topic · audience · tone]) --> R[🔎 Research Agent]
    R -->|key facts & angles| D[✍️ Draft Agent]
    D -->|first draft| C[🧐 Critique Agent]
    C -->|scores + feedback| V[✨ Revision Agent]
    V -->|needs another pass?| C
    V --> F([📬 Final LinkedIn Post])

    style U fill:#0A66C2,color:#fff,stroke:none
    style F fill:#0A66C2,color:#fff,stroke:none
```

### The Agent Crew

| Agent | Role | What it produces |
|:--|:--|:--|
| 🔎 **Research Agent** | Explores the topic, pulls out key facts, trends, and angles worth writing about | A structured research brief |
| ✍️ **Draft Agent** | Turns the brief into a first draft with a hook, body, and call-to-action | Draft v1 |
| 🧐 **Critique Agent** | Reviews the draft for **technical accuracy** and **engagement potential** | Scores and actionable feedback |
| ✨ **Revision Agent** | Applies the critique and tailors the post to the target **audience** and **tone** | The final, ready-to-post version |

### 🔁 The Feedback Loop

The critique-and-revise step is what makes PostPilot different. Instead of stopping at the first draft, the system **critiques its own work**, much like a human editor would:

1. **Accuracy check:** Are the claims correct? Is any technical detail wrong or overstated?
2. **Engagement check:** Does the hook grab attention? Is it skimmable? Is there a clear takeaway?
3. **Audience fit:** Is it pitched at the right level for recruiters, engineers, founders, or whoever the reader is?
4. **Revision:** The Revision Agent applies the feedback and produces the final version in the tone you chose (professional, conversational, storytelling, thought-leadership, and so on).

---

## ✨ Features

- 🤖 **Multi-agent orchestration:** four specialized agents instead of one catch-all prompt
- 🎯 **Audience targeting:** tailor the same topic for engineers, executives, job seekers, or founders
- 🎨 **Tone control:** professional, casual, inspirational, technical, storytelling
- 🧪 **Built-in quality gate:** every draft is critiqued for accuracy and engagement before it reaches you
- 👀 **Transparent pipeline:** see the research brief, the first draft, and the critique, not just the final output
- ⚡ **Lean stack:** FastAPI backend with a lightweight Streamlit UI, all in Python

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Streamlit UI                        │
│   Topic input · Audience/Tone pickers · Live pipeline   │
│   view · Draft vs. Final comparison · Copy to clipboard │
└───────────────────────────┬─────────────────────────────┘
                            │  REST / JSON
┌───────────────────────────▼─────────────────────────────┐
│                    FastAPI Backend                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Agent Orchestrator                   │  │
│  │   Research ─► Draft ─► Critique ─► Revision       │  │
│  └───────────────────────────────────────────────────┘  │
│        Prompt templates · Pydantic schemas · Config     │
└───────────────────────────┬─────────────────────────────┘
                            │
                     ┌──────▼──────┐
                     │  LLM API    │
                     └─────────────┘
```

### Tech Stack

| Layer | Technology |
|:--|:--|
| **Backend** | Python 3.12, FastAPI, Pydantic |
| **Agent Orchestration** | Custom sequential pipeline with a critique → revision feedback loop |
| **UI** | Streamlit |
| **LLM** | Pluggable LLM provider via API |

### Proposed Project Structure

```
postpilot-ai/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── api/                 # Route handlers
│   │   ├── agents/
│   │   │   ├── research.py      # 🔎 Research Agent
│   │   │   ├── draft.py         # ✍️ Draft Agent
│   │   │   ├── critique.py      # 🧐 Critique Agent
│   │   │   └── revision.py      # ✨ Revision Agent
│   │   ├── orchestrator.py      # Runs the pipeline
│   │   ├── prompts/             # Prompt templates per agent
│   │   └── schemas.py           # Pydantic request/response models
├── streamlit_app.py             # 🖥️ Streamlit UI
├── requirements.txt
└── README.md
```

---

## ⚙️ Getting Started

> **Note:** PostPilot AI is under active development. The steps below describe the intended setup.

### Prerequisites

- Python **3.12+**
- An API key for your LLM provider

### 1. Clone the repo

```bash
git clone https://github.com/<your-username>/postpilot-ai.git
cd postpilot-ai
```

### 2. Set up the environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # add your LLM API key
```

### 3. Start the backend

```bash
uvicorn backend.app.main:app --reload
```

The API will be live at **http://localhost:8000** and the interactive docs at **http://localhost:8000/docs**.

### 4. Launch the Streamlit app

In a second terminal:

```bash
streamlit run streamlit_app.py
```

The app opens at **http://localhost:8501**. Enter a topic, pick an audience and tone, and watch the agents work.

### 5. Or call the API directly 🎉

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
        "topic": "Why multi-agent systems beat single prompts",
        "audience": "software engineers",
        "tone": "thought-leadership"
      }'
```

---

## 🗺️ Roadmap

- [x] Accounts: sign up, log in, log out
- [x] Post requests API (`/api/posts`) and Streamlit form for topic, audience, tone, and length, with post history
- [ ] Research, Draft, Critique, and Revision agents
- [ ] Sequential orchestrator with a critique → revision loop
- [ ] FastAPI `/generate` endpoint
- [ ] Streamlit UI: topic, audience, and tone inputs plus final output

---

## 🎓 What This Project Demonstrates

PostPilot AI is more than a content tool. It is a hands-on case study in **structured AI coordination**:

- **Separation of concerns for LLMs:** small, focused agents are easier to prompt, debug, and improve than one monolithic prompt.
- **Self-critique as a quality mechanism:** building a reviewer into the loop catches weak hooks and shaky claims before a human ever sees them.
- **Production-minded design:** typed schemas, a clean API boundary, and a simple Streamlit UI that makes the agents' reasoning visible.

> *Good writing is rarely a first draft. PostPilot AI brings the same research → draft → review → revise workflow that human writers use to an AI pipeline.*

---

## 🤝 Contributing

Contributions, ideas, and feedback are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-idea`
3. Commit your changes: `git commit -m "Add amazing idea"`
4. Push the branch: `git push origin feature/amazing-idea`
5. Open a Pull Request 🚀

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for details.

---

<div align="center">

### 👋 Let's Connect

If this project interests you, I'd love to hear your thoughts!

**[LinkedIn](https://www.linkedin.com/in/sbnraju/)** · **[Medium](https://medium.com/@sbnraju)** · **[GitHub](https://github.com/sbn-raju)**

⭐ **If you found this useful, consider starring the repo!** ⭐

<sub>Built with ☕ and a small team of very opinionated AI agents.</sub>

</div>
