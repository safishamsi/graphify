# Graph Report - .  (2026-04-19)

## Corpus Check
- Corpus is ~12,382 words - fits in a single context window. You may not need a graph.

## Summary
- 74 nodes · 79 edges · 16 communities detected
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 8 edges (avg confidence: 0.74)
- Token cost: 3,200 input · 2,800 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Product Overview & Deployment|Product Overview & Deployment]]
- [[_COMMUNITY_Agent Processing Nodes|Agent Processing Nodes]]
- [[_COMMUNITY_FastAPI REST Layer|FastAPI REST Layer]]
- [[_COMMUNITY_LangGraph Orchestration|LangGraph Orchestration]]
- [[_COMMUNITY_ML Explainability & LLM|ML Explainability & LLM]]
- [[_COMMUNITY_Churn Prediction Module|Churn Prediction Module]]
- [[_COMMUNITY_Agent State Management|Agent State Management]]
- [[_COMMUNITY_Email Delivery|Email Delivery]]
- [[_COMMUNITY_Graph Construction|Graph Construction]]
- [[_COMMUNITY_Web Server Runtime|Web Server Runtime]]
- [[_COMMUNITY_Agent Tests|Agent Tests]]
- [[_COMMUNITY_Email Tests|Email Tests]]
- [[_COMMUNITY_Agent Tools|Agent Tools]]
- [[_COMMUNITY_NumPy|NumPy]]
- [[_COMMUNITY_Joblib|Joblib]]
- [[_COMMUNITY_Config & Secrets|Config & Secrets]]

## God Nodes (most connected - your core abstractions)
1. `Churn Agent` - 22 edges
2. `SHAP Explainability` - 6 edges
3. `Groq + Llama 3.3 70B LLM` - 5 edges
4. `SHAP` - 4 edges
5. `Random Forest Classifier` - 4 edges
6. `LangGraph Agent` - 4 edges
7. `Human-in-the-Loop Approval` - 4 edges
8. `Risk-Based Routing (High/Medium/Low)` - 4 edges
9. `train_model()` - 3 edges
10. `AgentResponse` - 3 edges

## Surprising Connections (you probably didn't know these)
- `CSV Audit Trail` --semantically_similar_to--> `LangSmith`  [INFERRED] [semantically similar]
  README.md → requirements_full.txt
- `Churn Agent` --references--> `FastAPI`  [EXTRACTED]
  README.md → requirements.txt
- `Churn Agent` --references--> `Groq SDK`  [EXTRACTED]
  README.md → requirements.txt
- `Churn Agent` --references--> `Pydantic`  [INFERRED]
  README.md → requirements_full.txt
- `train_model()` --calls--> `predict()`  [INFERRED]
  ml/train.py → api/main.py

## Hyperedges (group relationships)
- **Churn Prediction to Email Pipeline** — readme_random_forest, readme_shap_explainability, readme_groq_llm, readme_human_in_the_loop, readme_gmail_smtp [EXTRACTED 1.00]
- **LangGraph Conditional Risk Routing Architecture** — readme_langgraph_agent, readme_risk_routing, readme_configurable_thresholds, technical_separate_risk_nodes_rationale [EXTRACTED 1.00]
- **Human Oversight and Audit Compliance Pattern** — readme_human_in_the_loop, readme_csv_audit_trail, technical_hitl_rationale [EXTRACTED 1.00]
- **Churn Prediction to Email Pipeline** — readme_random_forest, readme_shap_explainability, readme_groq_llm, readme_human_in_the_loop, readme_gmail_smtp [EXTRACTED 1.00]
- **LangGraph Conditional Risk Routing Architecture** — readme_langgraph_agent, readme_risk_routing, readme_configurable_thresholds, technical_separate_risk_nodes_rationale [EXTRACTED 1.00]
- **Human Oversight and Audit Compliance Pattern** — readme_human_in_the_loop, readme_csv_audit_trail, technical_hitl_rationale [EXTRACTED 1.00]

## Communities

### Community 0 - "Product Overview & Deployment"
Cohesion: 0.17
Nodes (17): Churn Agent, Configurable Risk Thresholds, CSV Audit Trail, Docker Deployment on Hugging Face Spaces, Gmail SMTP Email Delivery, Human-in-the-Loop Approval, Random Forest Classifier, Telco Customer Churn Dataset (+9 more)

### Community 1 - "Agent Processing Nodes"
Cohesion: 0.2
Nodes (0): 

### Community 2 - "FastAPI REST Layer"
Cohesion: 0.27
Nodes (6): BaseModel, AgentResponse, CustomerRequest, predict(), load_and_clean(), train_model()

### Community 3 - "LangGraph Orchestration"
Cohesion: 0.22
Nodes (9): LangGraph Agent, Risk-Based Routing (High/Medium/Low), Groq SDK, LangChain, LangChain-Groq, LangGraph, Rationale: Why LangGraph over simple script, Open/Closed Principle in Agent Architecture (+1 more)

### Community 4 - "ML Explainability & LLM"
Cohesion: 0.29
Nodes (8): Groq + Llama 3.3 70B LLM, SHAP Explainability, Numba, SHAP, Rationale: Why Groq over OpenAI, llama-3.3-70b-versatile, Rationale: Why SHAP for explainability, shap.TreeExplainer

### Community 5 - "Churn Prediction Module"
Cohesion: 0.4
Nodes (4): batch_predict(), predict_single(), Run churn prediction on a single customer.     Returns probability and risk leve, Run churn prediction on an entire DataFrame.     Returns DataFrame with probabil

### Community 6 - "Agent State Management"
Cohesion: 0.67
Nodes (2): ChurnAgentState, TypedDict

### Community 7 - "Email Delivery"
Cohesion: 1.0
Nodes (0): 

### Community 8 - "Graph Construction"
Cohesion: 1.0
Nodes (0): 

### Community 9 - "Web Server Runtime"
Cohesion: 1.0
Nodes (2): FastAPI, Uvicorn

### Community 10 - "Agent Tests"
Cohesion: 1.0
Nodes (0): 

### Community 11 - "Email Tests"
Cohesion: 1.0
Nodes (0): 

### Community 12 - "Agent Tools"
Cohesion: 1.0
Nodes (0): 

### Community 13 - "NumPy"
Cohesion: 1.0
Nodes (1): NumPy

### Community 14 - "Joblib"
Cohesion: 1.0
Nodes (1): Joblib

### Community 15 - "Config & Secrets"
Cohesion: 1.0
Nodes (1): python-dotenv

## Knowledge Gaps
- **17 isolated node(s):** `Run churn prediction on a single customer.     Returns probability and risk leve`, `Run churn prediction on an entire DataFrame.     Returns DataFrame with probabil`, `Uvicorn`, `Pandas`, `NumPy` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Email Delivery`** (2 nodes): `app.py`, `send_email()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Graph Construction`** (2 nodes): `graph.py`, `build_graph()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Web Server Runtime`** (2 nodes): `FastAPI`, `Uvicorn`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent Tests`** (1 nodes): `test_agent.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Email Tests`** (1 nodes): `test_email.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent Tools`** (1 nodes): `tools.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `NumPy`** (1 nodes): `NumPy`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Joblib`** (1 nodes): `Joblib`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Config & Secrets`** (1 nodes): `python-dotenv`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Churn Agent` connect `Product Overview & Deployment` to `Web Server Runtime`, `LangGraph Orchestration`, `ML Explainability & LLM`?**
  _High betweenness centrality (0.193) - this node is a cross-community bridge._
- **Why does `Groq + Llama 3.3 70B LLM` connect `ML Explainability & LLM` to `Product Overview & Deployment`, `LangGraph Orchestration`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Why does `Risk-Based Routing (High/Medium/Low)` connect `LangGraph Orchestration` to `Product Overview & Deployment`, `ML Explainability & LLM`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **What connects `Run churn prediction on a single customer.     Returns probability and risk leve`, `Run churn prediction on an entire DataFrame.     Returns DataFrame with probabil`, `Uvicorn` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._