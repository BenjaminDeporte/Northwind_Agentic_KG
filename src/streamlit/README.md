# Streamlit demonstration

The Streamlit app uses the shared runtime factory. The sidebar selects the
registered architecture and Cypher model; the conversational model remains
fixed by environment configuration. Architecture/model selections are included
in the MLflow run metadata. The app displays the answer and structured result;
the detailed result artifact remains in MLflow.

Start the two services on the remote server:

```bash
uv run mlflow server --host 0.0.0.0 --port 5000
uv run streamlit run src/streamlit/app.py --server.address 0.0.0.0 --server.port 8501
```

Forward both ports from a local machine:

```bash
ssh -N \
  -L 8501:127.0.0.1:8501 \
  -L 5000:127.0.0.1:5000 \
  user@remote-host
```

Open `http://localhost:8501` for Streamlit and `http://localhost:5000` for
MLflow. Each completed chat turn includes an **Open MLflow run** link.

For the manual Phase 7 check, use representative questions from the benchmark:

- `How many customers do we have ?`
- `How many orders placed customer ALFKI ?`
- `Which employee handled the most orders ?`
- `Give me all your data`
- `How are you ?`

Compare the Streamlit answer with the linked MLflow `runtime_result.json`
artifact and structured result.
