import pandas as pd
import streamlit as st
from datasketch import MinHash, MinHashLSH

st.title("Name Matching (Exact + Trigram Jaccard) — CSV Only (Clean + Unmatched)")


# ---------- Helpers ----------

def read_csv(uploaded):
    try:
        return pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        return None


def clean_series(s: pd.Series) -> pd.Series:
    # Critical: drop NaN BEFORE astype(str) so NaN doesn't become "nan"
    s = s.dropna()
    s = s.astype(str)

    # Normalize tricky whitespace / invisible chars
    s = s.str.replace("\u00A0", " ", regex=False)  # NBSP
    s = s.str.replace("\u200b", "", regex=False)   # zero-width space
    s = s.str.replace("\ufeff", "", regex=False)   # BOM

    s = s.str.strip()
    s = s[s != ""]
    return s


def normalize(s: str) -> str:
    return str(s).strip().lower()


def trigram_tokens(s: str):
    s = f" {s} "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def build_minhash(tokens, num_perm=128):
    mh = MinHash(num_perm=num_perm)
    for t in tokens:
        mh.update(t.encode("utf-8"))
    return mh


def filter_df(df, type_col):
    if type_col != "<none>":
        df = df[df[type_col].astype(str).str.strip().str.lower() != "episodic"]
    return df.copy()


def choose_columns(df, key_prefix: str):
    cols = list(df.columns)

    default_name = [c for c in cols if c.lower() in {"label", "name"}]
    name_col = st.selectbox(
        "Name column",
        cols,
        index=cols.index(default_name[0]) if default_name else 0,
        key=f"{key_prefix}_name_col",
    )

    count_candidates = [c for c in cols if c.lower() in {"count", "freq", "frequency", "n"}]
    count_col = st.selectbox(
        "Count column (optional)",
        ["<none>"] + count_candidates,
        key=f"{key_prefix}_count_col",
    )

    type_candidates = [c for c in cols if c.lower() in {"type", "node_type"}]
    type_col = st.selectbox(
        "Type column (optional)",
        ["<none>"] + type_candidates,
        key=f"{key_prefix}_type_col",
    )

    return name_col, count_col, type_col


def build_name_counts(df, name_col, count_col):
    name_raw = clean_series(df[name_col])

    if count_col == "<none>":
        counts = (
            name_raw.value_counts()
            .rename_axis("name_raw")
            .reset_index(name="count")
        )
    else:
        tmp = df.copy()
        tmp = tmp.loc[name_raw.index].copy()
        tmp["name_raw"] = name_raw
        tmp["count_val"] = pd.to_numeric(tmp[count_col], errors="coerce").fillna(0)
        counts = tmp.groupby("name_raw", as_index=False)["count_val"].sum()
        counts = counts.rename(columns={"count_val": "count"})

    counts["name_norm"] = counts["name_raw"].map(normalize)
    return counts


def best_by_norm(counts_df: pd.DataFrame) -> pd.DataFrame:
    # If multiple raw names collapse to same normalized name, keep the most frequent
    return (
        counts_df.sort_values("count", ascending=False)
        .drop_duplicates("name_norm")
        .reset_index(drop=True)
    )


# ---------- Upload ----------

col1, col2 = st.columns(2)
with col1:
    f1 = st.file_uploader("Upload File A (CSV)", type=["csv"], key="fa")
with col2:
    f2 = st.file_uploader("Upload File B (CSV)", type=["csv"], key="fb")

if not (f1 and f2):
    st.stop()


# ---------- Read ----------

df1 = read_csv(f1)
df2 = read_csv(f2)
if df1 is None or df2 is None:
    st.stop()


# ---------- Column Selection ----------

st.subheader("Select columns")
with st.expander("File A"):
    name1, count1, type1 = choose_columns(df1, "a")
with st.expander("File B"):
    name2, count2, type2 = choose_columns(df2, "b")


# ---------- Filter ----------

df1 = filter_df(df1, type1)
df2 = filter_df(df2, type2)


# ---------- Build unique name tables (name only; counts separate) ----------

a_counts = build_name_counts(df1, name1, count1)   # name_raw, count, name_norm
b_counts = build_name_counts(df2, name2, count2)

a_best = best_by_norm(a_counts)
b_best = best_by_norm(b_counts)

names1 = set(a_best["name_norm"])
names2 = set(b_best["name_norm"])

# Debug / sanity checks
with st.expander("Debug: uniqueness & duplicates"):
    st.write("Unique names A (cleaned):", len(names1))
    st.write("Unique names B (cleaned):", len(names2))

    dupes_a = a_counts["name_norm"].value_counts()
    dupes_a = dupes_a[dupes_a > 1].reset_index()
    dupes_a.columns = ["name_norm", "raw_variants_in_a"]
    st.write("Normalized names in A with multiple raw variants:", len(dupes_a))
    st.dataframe(dupes_a.head(50))

    st.write("Sample of selected name column (A):")
    st.dataframe(df1[[name1]].head(20))


# ---------- Matching ----------

exact_matches = names1 & names2
remaining1 = names1 - exact_matches
remaining2 = names2 - exact_matches

THRESH = st.slider("Fuzzy threshold (Jaccard)", 0.10, 0.99, 0.90, 0.01)
NUM_PERM = 128

# Build LSH on remaining2
lsh = MinHashLSH(threshold=float(THRESH), num_perm=NUM_PERM)
minhashes2 = {}

for n in remaining2:
    mh = build_minhash(trigram_tokens(n), num_perm=NUM_PERM)
    minhashes2[n] = mh
    lsh.insert(n, mh)

fuzzy_pairs = []
for n in remaining1:
    mh = build_minhash(trigram_tokens(n), num_perm=NUM_PERM)
    candidates = lsh.query(mh)

    best = None
    best_j = 0.0
    for cand in candidates:
        j = mh.jaccard(minhashes2[cand])
        if j > best_j:
            best_j = j
            best = cand

    if best is not None and best_j >= float(THRESH):
        fuzzy_pairs.append((n, best, best_j))

matched_b = {b for _, b, _ in fuzzy_pairs}
unmatched1 = remaining1 - {a for a, _, _ in fuzzy_pairs}
unmatched2 = remaining2 - matched_b


# ---------- Display Tables (raw + counts) ----------

# Exact
exact_df = pd.DataFrame({"name_norm": sorted(exact_matches)})
exact_df = exact_df.merge(
    a_best[["name_norm", "name_raw", "count"]].rename(columns={"name_raw": "name_a", "count": "count_a"}),
    on="name_norm",
    how="left",
).merge(
    b_best[["name_norm", "name_raw", "count"]].rename(columns={"name_raw": "name_b", "count": "count_b"}),
    on="name_norm",
    how="left",
)

# Fuzzy
fuzzy_df = pd.DataFrame(fuzzy_pairs, columns=["name_norm_a", "name_norm_b", "jaccard"])
fuzzy_df = fuzzy_df.merge(
    a_best[["name_norm", "name_raw", "count"]].rename(columns={"name_norm": "name_norm_a", "name_raw": "name_a", "count": "count_a"}),
    on="name_norm_a",
    how="left",
).merge(
    b_best[["name_norm", "name_raw", "count"]].rename(columns={"name_norm": "name_norm_b", "name_raw": "name_b", "count": "count_b"}),
    on="name_norm_b",
    how="left",
)

# Unmatched A/B (with counts)
unmatched_a_df = (
    pd.DataFrame({"name_norm": sorted(unmatched1)})
    .merge(a_best[["name_norm", "name_raw", "count"]], on="name_norm", how="left")
    .rename(columns={"name_raw": "name_a", "count": "count_a"})
)

unmatched_b_df = (
    pd.DataFrame({"name_norm": sorted(unmatched2)})
    .merge(b_best[["name_norm", "name_raw", "count"]], on="name_norm", how="left")
    .rename(columns={"name_raw": "name_b", "count": "count_b"})
)


# ---------- Results ----------

st.subheader("Summary")
st.write(f"Unique names A (cleaned): {len(names1)} | Unique names B (cleaned): {len(names2)}")
st.write(f"Exact matches: {len(exact_matches)}")
st.write(f"Fuzzy matches (≥ {THRESH:.2f}): {len(fuzzy_pairs)}")
st.write(f"Unmatched in A: {len(unmatched_a_df)} | Unmatched in B: {len(unmatched_b_df)}")

st.subheader("Exact Matches (with counts)")
st.dataframe(exact_df[["name_a", "count_a", "name_b", "count_b"]])

st.subheader("Fuzzy Matches (A → B, with counts)")
st.dataframe(fuzzy_df[["name_a", "count_a", "name_b", "count_b", "jaccard"]])

st.subheader("Unmatched Names (with counts)")
st.write("### A only")
st.dataframe(unmatched_a_df[["name_a", "count_a"]])

st.write("### B only")
st.dataframe(unmatched_b_df[["name_b", "count_b"]])


# ---------- Downloads ----------

st.download_button(
    "Download exact matches (CSV)",
    data=exact_df[["name_a", "count_a", "name_b", "count_b"]].to_csv(index=False),
    file_name="exact_matches.csv",
    mime="text/csv",
)

st.download_button(
    "Download fuzzy matches (CSV)",
    data=fuzzy_df[["name_a", "count_a", "name_b", "count_b", "jaccard"]].to_csv(index=False),
    file_name="fuzzy_matches.csv",
    mime="text/csv",
)

st.download_button(
    "Download unmatched A-only (CSV)",
    data=unmatched_a_df[["name_a", "count_a"]].to_csv(index=False),
    file_name="unmatched_a_only.csv",
    mime="text/csv",
)

st.download_button(
    "Download unmatched B-only (CSV)",
    data=unmatched_b_df[["name_b", "count_b"]].to_csv(index=False),
    file_name="unmatched_b_only.csv",
    mime="text/csv",
)
