import io
import pandas as pd
import streamlit as st

st.title("Entity Counts by Label")

uploaded = st.file_uploader("Upload TSV/CSV file", type=["tsv", "csv"])
if not uploaded:
    st.stop()

# Load with TSV first, fallback to CSV
raw = uploaded.read()
df = None

for sep in ("\t", ","):
    try:
        df = pd.read_csv(io.BytesIO(raw), sep=sep)
        break
    except Exception:
        df = None

if df is None or df.empty:
    st.error("Could not read the file—check the format.")
    st.stop()

# Pick label column (default to label/name if present)
default_label_cols = [c for c in df.columns if c.lower() in {"label", "name"}]

label_col = st.selectbox(
    "Choose label column",
    df.columns,
    index=df.columns.get_indexer(default_label_cols).tolist()[:1][0]
    if default_label_cols
    else 0,
)

# Optional type column to filter out Episodic rows
type_candidates = [c for c in df.columns if c.lower() in {"type", "node_type"}]

type_col = st.selectbox(
    "Type column (optional)",
    ["<none>"] + type_candidates,
)

filtered = df.copy()
if type_col != "<none>":
    filtered = filtered[
        filtered[type_col]
        .astype(str)
        .str.strip()
        .str.lower()
        != "episodic"
    ]

counts = (
    filtered[label_col]
    .astype(str)
    .str.strip()
    .value_counts()
    .rename_axis("entity")
    .reset_index(name="count")
)

total_nodes = len(filtered)
unique_nodes = len(counts)

st.subheader("Summary")
st.write(f"Total nodes (after filtering): {total_nodes}")
st.write(f"Unique entities: {unique_nodes}")

st.subheader("Counts")
st.dataframe(counts)

st.download_button(
    "Download counts as CSV",
    data=counts.to_csv(index=False),
    file_name="entity_counts.csv",
    mime="text/csv",
)
